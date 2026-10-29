"""Espera estimada que se imprime en el ticket del tótem (HU-18).

Se calcula al mostrar el ticket, sin guardar nada:

    (turnos por delante + turnos en curso) × promedio de atención ÷ ventanillas abiertas

redondeado hacia arriba a `TURNOS_MINUTOS_REDONDEO_ESPERA`. El promedio es el de la atención
completa (de la recepción a la entrega) de los últimos `TURNOS_DIAS_HISTORIAL_ESPERA` días,
porque la ventanilla queda ocupada todo ese tiempo. Sin historial suficiente o sin ventanillas
abiertas no hay estimación: es mejor no mostrar nada que un número inventado.
"""
import math
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from turnos.models import ESTADOS_EN_CURSO, Categoria, EstadoTurno, Turno, Ventanilla
from turnos.motor import _generales_seguidos


def promedio_de_atencion(ahora=None):
    """Minutos promedio entre la recepción y la entrega de las atenciones recientes con
    preparación, o None si son menos de `TURNOS_MUESTRAS_MINIMAS_ESPERA`."""
    ahora = ahora or timezone.now()
    desde = ahora - timedelta(days=settings.TURNOS_DIAS_HISTORIAL_ESPERA)
    tiempos = Turno.objects.filter(
        estado=EstadoTurno.ATENDIDO,
        preparacion__isnull=False,
        inicio_atencion_en__isnull=False,
        cierre_en__gte=desde,
        cierre_en__lte=ahora,
    ).values_list("inicio_atencion_en", "cierre_en")
    duraciones = [(cierre - inicio).total_seconds() for inicio, cierre in tiempos]
    if len(duraciones) < settings.TURNOS_MUESTRAS_MINIMAS_ESPERA:
        return None
    return sum(duraciones) / len(duraciones) / 60


def turnos_por_delante(turno):
    """Cuántos turnos en espera del día se llamarían antes que `turno`.

    Simula sin modificar datos el orden de `motor.elegir_siguiente`: urgencia primero; luego un
    preferencial cada `TURNOS_GENERALES_POR_PREFERENCIAL` generales, a partir de los llamados de
    hoy; dentro de cada categoría, por orden de emisión. Si el motor cambia, la prueba que
    compara los dos órdenes avisa.
    """
    if turno.estado != EstadoTurno.EN_ESPERA:
        return 0
    en_espera = Turno.objects.filter(fecha=turno.fecha, estado=EstadoTurno.EN_ESPERA).order_by("emitido_en", "pk")
    filas = {categoria: [] for categoria in Categoria}
    for pk, categoria in en_espera.values_list("pk", "categoria"):
        filas[categoria].append(pk)

    seguidos = _generales_seguidos(turno.fecha)
    delante = 0
    while True:
        if filas[Categoria.URGENCIA]:
            categoria = Categoria.URGENCIA
        elif filas[Categoria.PREFERENCIAL] and (
            seguidos >= settings.TURNOS_GENERALES_POR_PREFERENCIAL or not filas[Categoria.GENERAL]
        ):
            categoria = Categoria.PREFERENCIAL
            seguidos = 0
        else:
            categoria = Categoria.GENERAL
            seguidos += 1
        if filas[categoria].pop(0) == turno.pk:
            return delante
        delante += 1


def estimar_espera(turno, ahora=None):
    """Minutos estimados de espera de un turno en espera, redondeados hacia arriba, o None si no
    hay estimación. Devuelve 0 si el cálculo da menos que el redondeo («menos de 5 minutos»)."""
    if turno.estado != EstadoTurno.EN_ESPERA:
        return None
    promedio = promedio_de_atencion(ahora)
    if promedio is None:
        return None
    abiertas = Ventanilla.objects.filter(habilitada=True, funcionario__isnull=False).count()
    if not abiertas:
        return None
    en_curso = Turno.objects.filter(fecha=turno.fecha, estado__in=ESTADOS_EN_CURSO).count()
    minutos = (turnos_por_delante(turno) + en_curso) * promedio / abiertas
    redondeo = settings.TURNOS_MINUTOS_REDONDEO_ESPERA
    if minutos < redondeo:
        return 0
    # round() evita que un error de coma flotante (10,0000001) salte al múltiplo siguiente.
    return math.ceil(round(minutos / redondeo, 6)) * redondeo


def texto_de_espera(minutos):
    """«Espera estimada: unos 25 minutos», «… menos de 5 minutos», o None sin estimación."""
    if minutos is None:
        return None
    if minutos == 0:
        return f"Espera estimada: menos de {settings.TURNOS_MINUTOS_REDONDEO_ESPERA} minutos"
    return f"Espera estimada: unos {minutos} minutos"
