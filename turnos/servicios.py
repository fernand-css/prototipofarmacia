"""Lógica de negocio de los turnos: emisión, ventanillas, llamado y atención, fila y sala de espera.

Las vistas solo traducen peticiones y mensajes; las reglas viven aquí. Una acción que no
corresponde lanza `ErrorDeAtencion`, y su mensaje se muestra tal cual al funcionario.
"""
import math
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from cuentas.validators import normalizar_rut, validar_rut
from turnos.models import (
    ESTADOS_ACTIVOS,
    ESTADOS_EN_CURSO,
    Categoria,
    EstadoTurno,
    Paciente,
    RecetaCronica,
    Turno,
    Ventanilla,
)
from turnos.motor import elegir_siguiente

INTENTOS_ESCRITURA = 3  # reintentos ante un choque con una restricción única
INTENTOS_LLAMADO = 5  # reintentos si otro funcionario se adelanta en la misma elección
TURNOS_VISIBLES_POR_CATEGORIA = 10  # cuántos turnos de cada categoría lista la fila del panel


class ErrorDeAtencion(Exception):
    """Una acción del panel que no corresponde; el mensaje se muestra tal cual al funcionario."""


def _con_reintentos(operacion):
    """Ejecuta `operacion` en una transacción y la repite si choca con una restricción única.

    El choque ocurre cuando dos peticiones calculan a la vez el mismo valor (un correlativo, un
    número de ventanilla): la base rechaza a una y, al reintentar, esta lee el valor actualizado.
    """
    for intento in range(INTENTOS_ESCRITURA):
        try:
            with transaction.atomic():
                return operacion()
        except IntegrityError:
            if intento == INTENTOS_ESCRITURA - 1:
                raise


# --- Emisión de turnos -----------------------------------------------------------------------


class TipoResultado:
    EMITIDO = "emitido"
    VIGENTE = "vigente"
    DOMICILIO = "domicilio"
    BLOQUEADO = "bloqueado"


@dataclass(frozen=True)
class ResultadoEmision:
    tipo: str
    turno: Turno | None = None
    paciente: Paciente | None = None
    anulado: Turno | None = None  # turno en espera que la urgencia reemplazó


def emitir_turno(rut, *, desde_panel=False, insistir_domicilio=False):
    """Emite el turno de un RUT, o explica por qué no.

    Lanza ValidationError si el RUT no es válido. Desde el panel (urgencia) no se aplican el
    aviso de domicilio ni el bloqueo por receta, y el turno en espera del mismo RUT se anula.
    """
    rut = normalizar_rut(rut)
    validar_rut(rut)
    return _con_reintentos(lambda: _emitir(rut, desde_panel, insistir_domicilio))


def _emitir(rut, desde_panel, insistir_domicilio):
    hoy = timezone.localdate()
    paciente = Paciente.objects.filter(rut=rut).first()

    anulado = None
    activo = Turno.objects.filter(fecha=hoy, rut=rut, estado__in=ESTADOS_ACTIVOS).first()
    if activo:
        if not (desde_panel and _se_puede_reemplazar(activo)):
            return ResultadoEmision(TipoResultado.VIGENTE, turno=activo, paciente=paciente)
        anulado = _anular(activo)

    receta = None
    if paciente:
        if not desde_panel and paciente.es_despacho_domicilio and not insistir_domicilio:
            return ResultadoEmision(TipoResultado.DOMICILIO, paciente=paciente)

        recetas = list(paciente.recetas.all())
        utilizables = [r for r in recetas if r.es_utilizable]
        if recetas and not utilizables and not desde_panel:
            return ResultadoEmision(TipoResultado.BLOQUEADO, paciente=paciente)
        receta = utilizables[0] if utilizables else None  # la más antigua: el modelo ordena por emisión

    categoria = _categoria_para(paciente, desde_panel)
    ultimo = Turno.objects.filter(fecha=hoy, categoria=categoria).aggregate(m=Max("correlativo"))["m"]
    turno = Turno.objects.create(
        fecha=hoy,
        categoria=categoria,
        correlativo=(ultimo or 0) + 1,
        rut=rut,
        paciente=paciente,
        receta=receta,
    )
    return ResultadoEmision(TipoResultado.EMITIDO, turno=turno, paciente=paciente, anulado=anulado)


def _se_puede_reemplazar(turno):
    """Una urgencia reemplaza al turno que espera su RUT, salvo que ya sea otra urgencia."""
    return turno.estado == EstadoTurno.EN_ESPERA and turno.categoria != Categoria.URGENCIA


def _anular(turno):
    turno.estado = EstadoTurno.ANULADO
    turno.cierre_en = timezone.now()
    turno.save(update_fields=["estado", "cierre_en"])
    return turno


def _categoria_para(paciente, desde_panel):
    if desde_panel:
        return Categoria.URGENCIA
    if paciente and paciente.es_preferencial:
        return Categoria.PREFERENCIAL
    return Categoria.GENERAL


# --- Ventanillas -----------------------------------------------------------------------------


def crear_ventanilla():
    """Agrega la ventanilla siguiente a la última, ya habilitada."""

    def crear():
        ultimo = Ventanilla.objects.aggregate(m=Max("numero"))["m"] or 0
        return Ventanilla.objects.create(numero=ultimo + 1)

    return _con_reintentos(crear)


def cambiar_estado_ventanilla(ventanilla_id):
    """Habilita una ventanilla deshabilitada, o deshabilita (y libera) una habilitada.

    No se deshabilita mientras tenga un turno en curso. Lanza `Ventanilla.DoesNotExist` si no existe.
    """
    with transaction.atomic():
        ventanilla = Ventanilla.objects.select_for_update().get(pk=ventanilla_id)
        if not ventanilla.habilitada:
            ventanilla.habilitada = True
            ventanilla.save(update_fields=["habilitada"])
            return ventanilla

        en_curso = Turno.objects.filter(
            ventanilla=ventanilla, fecha=timezone.localdate(), estado__in=ESTADOS_EN_CURSO
        ).exists()
        if en_curso:
            raise ErrorDeAtencion(
                f"La ventanilla {ventanilla.numero} tiene un turno en curso. "
                "Espere a que termine la atención para deshabilitarla."
            )
        ventanilla.habilitada = False
        ventanilla.funcionario = None
        ventanilla.save(update_fields=["habilitada", "funcionario"])
        return ventanilla


def abrir_ventanilla(usuario, ventanilla_id):
    """El funcionario toma una ventanilla habilitada y libre. Solo puede tener una abierta."""
    if Ventanilla.objects.filter(funcionario=usuario).exists():
        raise ErrorDeAtencion("Ya tiene una ventanilla abierta.")
    try:
        # UPDATE condicional: si dos funcionarios piden la misma ventanilla, solo uno la obtiene.
        with transaction.atomic():
            tomadas = Ventanilla.objects.filter(
                pk=ventanilla_id, habilitada=True, funcionario__isnull=True
            ).update(funcionario=usuario)
    except IntegrityError:
        raise ErrorDeAtencion("Ya tiene una ventanilla abierta.")
    if not tomadas:
        raise ErrorDeAtencion("Esa ventanilla ya no está disponible.")
    return Ventanilla.objects.get(funcionario=usuario)


def terminar_turno_de_ventanilla(usuario):
    """Libera la ventanilla del funcionario. Se rechaza si tiene un turno en curso."""
    ventanilla = Ventanilla.objects.filter(funcionario=usuario).first()
    if ventanilla is None:
        raise ErrorDeAtencion("No tiene una ventanilla abierta.")
    if turno_en_curso(usuario):
        raise ErrorDeAtencion("Tiene un turno en curso. Termine la atención antes de cerrar la ventanilla.")
    ventanilla.funcionario = None
    ventanilla.save(update_fields=["funcionario"])
    return ventanilla


# --- Llamado y atención ----------------------------------------------------------------------


def turno_en_curso(usuario):
    """El turno que el funcionario tiene llamado o en atención hoy, si lo hay."""
    return Turno.objects.filter(
        atendido_por=usuario, fecha=timezone.localdate(), estado__in=ESTADOS_EN_CURSO
    ).first()


def _turno_en_estado(usuario, estado, mensaje_si_no_hay):
    turno = turno_en_curso(usuario)
    if turno is None or turno.estado != estado:
        raise ErrorDeAtencion(mensaje_si_no_hay)
    return turno


def llamar_siguiente(usuario):
    """Asigna a la ventanilla del funcionario el turno que elige el motor y lo deja llamado.

    Si dos funcionarios eligen el mismo turno a la vez, el UPDATE condicional solo se lo da a
    uno; el otro vuelve a elegir con la fila ya actualizada.
    """
    ventanilla = Ventanilla.objects.filter(funcionario=usuario).first()
    if ventanilla is None:
        raise ErrorDeAtencion("Abra una ventanilla antes de llamar pacientes.")
    if turno_en_curso(usuario):
        raise ErrorDeAtencion("Ya tiene un turno en curso.")

    hoy = timezone.localdate()
    for _ in range(INTENTOS_LLAMADO):
        with transaction.atomic():
            if not Ventanilla.objects.filter(pk=ventanilla.pk, habilitada=True, funcionario=usuario).exists():
                raise ErrorDeAtencion("Su ventanilla fue deshabilitada.")
            candidato = elegir_siguiente(hoy)
            if candidato is None:
                raise ErrorDeAtencion("No hay pacientes en espera.")
            ahora = timezone.now()
            tomados = Turno.objects.filter(pk=candidato.pk, estado=EstadoTurno.EN_ESPERA).update(
                estado=EstadoTurno.LLAMADO,
                ventanilla=ventanilla,
                atendido_por=usuario,
                llamado_en=ahora,
                ultimo_llamado_en=ahora,
                veces_llamado=1,
            )
        if tomados:
            return Turno.objects.get(pk=candidato.pk)
    raise ErrorDeAtencion("No se pudo llamar al siguiente paciente. Inténtelo de nuevo.")


def re_llamar(usuario):
    """Repite el llamado del turno actual. Conserva su ventanilla y su funcionario."""
    ahora = timezone.now()
    actualizados = Turno.objects.filter(
        atendido_por=usuario, fecha=timezone.localdate(), estado=EstadoTurno.LLAMADO
    ).update(ultimo_llamado_en=ahora, veces_llamado=F("veces_llamado") + 1)
    if not actualizados:
        raise ErrorDeAtencion("No tiene un turno llamado para re-llamar.")
    return turno_en_curso(usuario)


def segundos_para_ausente(turno):
    """Segundos que faltan para poder marcar ausente a un turno llamado (0 si ya se puede)."""
    if turno.ultimo_llamado_en is None:  # turno editado a mano en el admin: no bloquear al funcionario
        return 0
    habilitado_desde = turno.ultimo_llamado_en + timedelta(seconds=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE)
    return max(0, math.ceil((habilitado_desde - timezone.now()).total_seconds()))


def iniciar_atencion(usuario):
    """El paciente llegó a la ventanilla: el turno pasa de llamado a en atención."""
    turno = _turno_en_estado(usuario, EstadoTurno.LLAMADO, "No tiene un turno llamado para iniciar.")
    Turno.objects.filter(pk=turno.pk, estado=EstadoTurno.LLAMADO).update(
        estado=EstadoTurno.EN_ATENCION, inicio_atencion_en=timezone.now()
    )
    return Turno.objects.get(pk=turno.pk)


def finalizar_atencion(usuario):
    """Cierra la atención. Si el turno trae una receta crónica, suma una entrega a la receta."""
    with transaction.atomic():
        turno = _turno_en_estado(
            usuario, EstadoTurno.EN_ATENCION, "No tiene una atención en curso para finalizar."
        )
        actualizados = Turno.objects.filter(pk=turno.pk, estado=EstadoTurno.EN_ATENCION).update(
            estado=EstadoTurno.ATENDIDO, cierre_en=timezone.now()
        )
        if actualizados and turno.receta_id:
            RecetaCronica.objects.filter(pk=turno.receta_id).update(
                entregas_realizadas=F("entregas_realizadas") + 1
            )
    return Turno.objects.get(pk=turno.pk)


def marcar_ausente(usuario):
    """El paciente no se presentó. Solo se puede pasado el plazo desde el último llamado."""
    turno = _turno_en_estado(
        usuario, EstadoTurno.LLAMADO, "No tiene un turno llamado para marcar como ausente."
    )
    faltan = segundos_para_ausente(turno)
    if faltan:
        raise ErrorDeAtencion(f"Debe esperar {faltan} segundos más desde el último llamado.")
    # Si entremedio hubo un re-llamado, ultimo_llamado_en cambió y el plazo vuelve a correr.
    limite = timezone.now() - timedelta(seconds=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE)
    actualizados = Turno.objects.filter(
        pk=turno.pk, estado=EstadoTurno.LLAMADO, ultimo_llamado_en__lte=limite
    ).update(estado=EstadoTurno.AUSENTE, cierre_en=timezone.now())
    if not actualizados:
        raise ErrorDeAtencion("El turno cambió mientras tanto. Revise el panel.")
    return Turno.objects.get(pk=turno.pk)


# --- Fila de espera --------------------------------------------------------------------------


def resumen_cola(fecha=None):
    """La fila de hoy para el panel: cuántos esperan por categoría, los primeros de cada una y el siguiente."""
    fecha = fecha or timezone.localdate()
    en_espera = list(
        Turno.objects.filter(fecha=fecha, estado=EstadoTurno.EN_ESPERA).order_by("emitido_en", "pk")
    )
    grupos = []
    for categoria in (Categoria.URGENCIA, Categoria.PREFERENCIAL, Categoria.GENERAL):
        turnos = [t for t in en_espera if t.categoria == categoria]
        grupos.append(
            {
                "categoria": categoria.value,
                "nombre": categoria.label,
                "total": len(turnos),
                "turnos": turnos[:TURNOS_VISIBLES_POR_CATEGORIA],
                "restantes": max(0, len(turnos) - TURNOS_VISIBLES_POR_CATEGORIA),
            }
        )
    return {"total": len(en_espera), "grupos": grupos, "siguiente": elegir_siguiente(fecha)}


# --- Sala de espera --------------------------------------------------------------------------


def _hora_local(momento):
    # Milisegundos: es el formato que lee `Date` de JavaScript y basta para medir la latencia.
    return timezone.localtime(momento).isoformat(timespec="milliseconds")


def obtener_estado_sala(fecha=None):
    """Los últimos llamados del día para la pantalla pública de la sala, del más reciente al más antiguo.

    Cada llamado lleva solo número de turno, número de ventanilla y lo que lo identifica: la
    pantalla es pública y no debe recibir datos del paciente. Un re-llamado sube al turno al
    primer lugar sin repetirlo. No modifica datos.
    """
    fecha = fecha or timezone.localdate()
    llamados = (
        Turno.objects.filter(
            fecha=fecha,
            ultimo_llamado_en__isnull=False,
            ventanilla__isnull=False,
            veces_llamado__gte=1,
        )
        .exclude(estado__in=(EstadoTurno.EN_ESPERA, EstadoTurno.ANULADO))
        .select_related("ventanilla")
        .order_by("-ultimo_llamado_en", "-pk")[: settings.TURNOS_CANTIDAD_LLAMADOS_SALA]
    )
    recientes = [
        {
            "turno_id": turno.pk,
            "numero": turno.numero,
            "ventanilla": turno.ventanilla.numero,
            "veces_llamado": turno.veces_llamado,
            "ultimo_llamado_en": _hora_local(turno.ultimo_llamado_en),
        }
        for turno in llamados
    ]
    return {
        "fecha": fecha.isoformat(),
        "servidor_en": _hora_local(timezone.now()),
        "actual": recientes[0] if recientes else None,
        "recientes": recientes,
    }
