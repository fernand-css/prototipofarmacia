"""Reglas del domicilio de los pacientes con despacho a domicilio (HU-12).

Las vistas solo traducen peticiones y mensajes. Una acción que no corresponde lanza
`ErrorDeDomicilio`, y su mensaje se muestra tal cual al Encargado de Terreno. Cada cambio deja
un `CambioDomicilio` con quién, cuándo y cómo quedó el domicilio.
"""
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from cuentas.validators import normalizar_rut
from reparto.models import AccionDomicilio, CambioDomicilio, Domicilio, EstadoDomicilio, FotoDomicilio
from turnos.importacion import normalizar_encabezado
from turnos.models import Paciente

LARGO_MAXIMO_MOTIVO = 300
SEIS_DECIMALES = Decimal("0.000001")
NUMERO = re.compile(r"-?\d+(?:[.,]\d+)?")
SEPARADORES = re.compile(r"[\s,;]*")

# Filtros de estado de la lista: «sin dirección» es un paciente sin fila de Domicilio.
SIN_DIRECCION = "sin_direccion"
ESTADOS_DE_LISTA = (
    (SIN_DIRECCION, "Sin dirección"),
    (EstadoDomicilio.PENDIENTE.value, EstadoDomicilio.PENDIENTE.label),
    (EstadoDomicilio.VERIFICADO.value, EstadoDomicilio.VERIFICADO.label),
)


class ErrorDeDomicilio(Exception):
    """Una acción sobre un domicilio que no corresponde; el mensaje se muestra tal cual."""


# --- Coordenadas --------------------------------------------------------------------------------


def leer_coordenadas(texto):
    """Lee una o dos coordenadas de un texto: «-36.5», «-36,5» o «-36.50, -72.21» pegado de un mapa.

    Devuelve una tupla de `Decimal` con 6 decimales, con uno o dos elementos, o una tupla vacía
    si el texto está vacío. Lanza `ErrorDeDomicilio` si hay algo que no es un número.
    """
    texto = (texto or "").strip()
    if not texto:
        return ()
    numeros = NUMERO.findall(texto)
    sobrante = SEPARADORES.sub("", NUMERO.sub("", texto))
    if not numeros or len(numeros) > 2 or sobrante:
        raise ErrorDeDomicilio(f"«{texto}» no es una coordenada. Escríbala como -36.499912.")
    return tuple(Decimal(n.replace(",", ".")).quantize(SEIS_DECIMALES, ROUND_HALF_UP) for n in numeros)


def validar_coordenadas(latitud, longitud):
    """Las dos o ninguna, dentro de rango. No se valida que caigan en la comuna."""
    if (latitud is None) != (longitud is None):
        raise ErrorDeDomicilio("Escriba la latitud y la longitud, o deje las dos vacías.")
    if latitud is None:
        return
    if not Decimal(-90) <= latitud <= Decimal(90):
        raise ErrorDeDomicilio("La latitud debe estar entre -90 y 90.")
    if not Decimal(-180) <= longitud <= Decimal(180):
        raise ErrorDeDomicilio("La longitud debe estar entre -180 y 180.")


# --- Registro y verificación --------------------------------------------------------------------


def _datos(domicilio):
    """Cómo quedó el domicilio, para el historial (JSON: las coordenadas van como texto)."""
    return {
        "sector": domicilio.sector,
        "direccion": domicilio.direccion,
        "referencias": domicilio.referencias,
        "latitud": None if domicilio.latitud is None else str(domicilio.latitud),
        "longitud": None if domicilio.longitud is None else str(domicilio.longitud),
        "estado": domicilio.estado,
    }


def registrar_cambio(domicilio, usuario, accion, motivo="", carga=None):
    return CambioDomicilio.objects.create(
        domicilio=domicilio, usuario=usuario, accion=accion, datos=_datos(domicilio), motivo=motivo, carga=carga
    )


def _exigir_despacho(paciente):
    if not paciente.es_despacho_domicilio:
        raise ErrorDeDomicilio("Este paciente no tiene despacho a domicilio.")


def guardar_domicilio(paciente, datos, usuario):
    """Registra o edita el domicilio. `datos`: sector, direccion, referencias, latitud y longitud.

    Editar uno verificado lo deja verificado, pero sus coordenadas no se pueden borrar. Si nada
    cambió, no escribe ni deja historial.
    """
    _exigir_despacho(paciente)
    direccion = (datos.get("direccion") or "").strip()
    if not direccion:
        raise ErrorDeDomicilio("Escriba la dirección.")
    latitud, longitud = datos.get("latitud"), datos.get("longitud")
    validar_coordenadas(latitud, longitud)
    nuevos = {
        "sector": datos.get("sector") or "",
        "direccion": direccion,
        "referencias": (datos.get("referencias") or "").strip(),
        "latitud": latitud,
        "longitud": longitud,
    }

    with transaction.atomic():
        domicilio = Domicilio.objects.filter(paciente=paciente).first()
        if domicilio is None:
            domicilio = Domicilio.objects.create(paciente=paciente, actualizado_por=usuario, **nuevos)
            registrar_cambio(domicilio, usuario, AccionDomicilio.CREADO)
            return domicilio

        if domicilio.estado == EstadoDomicilio.VERIFICADO and latitud is None:
            raise ErrorDeDomicilio(
                "Un domicilio verificado no puede quedar sin coordenadas. "
                "Si ya no corresponde, márquelo pendiente de verificar."
            )
        if all(getattr(domicilio, campo) == valor for campo, valor in nuevos.items()):
            return domicilio
        for campo, valor in nuevos.items():
            setattr(domicilio, campo, valor)
        domicilio.actualizado_por = usuario
        domicilio.actualizado_en = timezone.now()
        domicilio.save()
        registrar_cambio(domicilio, usuario, AccionDomicilio.EDITADO)
    return domicilio


def _domicilio_de(paciente):
    domicilio = Domicilio.objects.filter(paciente=paciente).first()
    if domicilio is None:
        raise ErrorDeDomicilio("Este paciente todavía no tiene un domicilio registrado.")
    return domicilio


def verificar(paciente, usuario):
    """Marca el domicilio verificado en terreno. Exige coordenadas."""
    domicilio = _domicilio_de(paciente)
    with transaction.atomic():
        verificados = Domicilio.objects.filter(
            pk=domicilio.pk,
            estado=EstadoDomicilio.PENDIENTE,
            latitud__isnull=False,
            longitud__isnull=False,
        ).update(estado=EstadoDomicilio.VERIFICADO, verificado_en=timezone.now(), verificado_por=usuario)
        domicilio.refresh_from_db()
        if not verificados:
            if domicilio.estado == EstadoDomicilio.VERIFICADO:
                raise ErrorDeDomicilio("Este domicilio ya está verificado.")
            raise ErrorDeDomicilio("Para verificar el domicilio, registre primero sus coordenadas.")
        registrar_cambio(domicilio, usuario, AccionDomicilio.VERIFICADO)
    return domicilio


def marcar_pendiente(paciente, motivo, usuario):
    """Pide que el domicilio se vuelva a verificar, con un motivo que queda en el historial."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorDeDomicilio("Escriba por qué el domicilio debe volver a verificarse.")
    if len(motivo) > LARGO_MAXIMO_MOTIVO:
        raise ErrorDeDomicilio(f"El motivo no puede pasar de {LARGO_MAXIMO_MOTIVO} caracteres.")
    domicilio = _domicilio_de(paciente)
    with transaction.atomic():
        marcados = Domicilio.objects.filter(pk=domicilio.pk, estado=EstadoDomicilio.VERIFICADO).update(
            estado=EstadoDomicilio.PENDIENTE, verificado_en=None, verificado_por=None
        )
        if not marcados:
            raise ErrorDeDomicilio("Este domicilio ya está pendiente de verificar.")
        domicilio.refresh_from_db()
        registrar_cambio(domicilio, usuario, AccionDomicilio.MARCADO_PENDIENTE, motivo=motivo)
    return domicilio


# --- Fotos -------------------------------------------------------------------------------------

FORMATOS_DE_FOTO = ("JPEG", "PNG")
CALIDAD_JPEG = 85


def procesar_foto(archivo):
    """Valida y prepara una foto: JPEG o PNG, sin pasar de los límites de bytes y píxeles.

    Aplica la orientación del EXIF, la achica a `REPARTO_PIXELES_LADO_MAYOR` de lado mayor (sin
    agrandarla) y la guarda en JPEG sin metadatos, con un nombre aleatorio. Devuelve
    `(ContentFile, ancho, alto)`. El original no se conserva.
    """
    if archivo.size > settings.REPARTO_BYTES_MAXIMOS_FOTO:
        megas = settings.REPARTO_BYTES_MAXIMOS_FOTO // (1024 * 1024)
        raise ErrorDeDomicilio(f"La foto pesa más de {megas} MB.")
    no_es_imagen = ErrorDeDomicilio("El archivo no es una foto JPEG o PNG válida.")
    try:
        # `open` solo lee el encabezado: el tamaño se revisa antes de cargar los píxeles.
        imagen = Image.open(archivo)
        if imagen.format not in FORMATOS_DE_FOTO:
            raise no_es_imagen
        if imagen.width * imagen.height > settings.REPARTO_PIXELES_MAXIMOS_ENTRADA:
            raise ErrorDeDomicilio("La foto tiene demasiados píxeles. Tómela con una resolución menor.")
        imagen.verify()
        archivo.seek(0)
        imagen = ImageOps.exif_transpose(Image.open(archivo))
        imagen.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise no_es_imagen from None

    if imagen.mode in ("RGBA", "LA") or (imagen.mode == "P" and "transparency" in imagen.info):
        fondo = Image.new("RGB", imagen.size, "white")
        fondo.paste(imagen.convert("RGBA"), mask=imagen.convert("RGBA").getchannel("A"))
        imagen = fondo
    else:
        imagen = imagen.convert("RGB")
    lado = settings.REPARTO_PIXELES_LADO_MAYOR
    imagen.thumbnail((lado, lado))

    salida = BytesIO()
    # Sin `exif` ni `icc_profile`: Pillow no copia los metadatos del original.
    imagen.save(salida, "JPEG", quality=CALIDAD_JPEG, optimize=True)
    return ContentFile(salida.getvalue(), name=f"{uuid.uuid4().hex}.jpg"), imagen.width, imagen.height


def agregar_foto(paciente, archivo, usuario):
    """Agrega una foto al domicilio, hasta `REPARTO_FOTOS_MAXIMAS`, y la deja en el historial."""
    domicilio = _domicilio_de(paciente)
    maximo = settings.REPARTO_FOTOS_MAXIMAS
    lleno = ErrorDeDomicilio(f"Este domicilio ya tiene {maximo} fotos. Borre una para subir otra.")
    if domicilio.fotos.count() >= maximo:
        raise lleno
    contenido, ancho, alto = procesar_foto(archivo)

    foto = None
    try:
        with transaction.atomic():
            foto = FotoDomicilio.objects.create(
                domicilio=domicilio, archivo=contenido, ancho=ancho, alto=alto, subida_por=usuario
            )
            # Dos subidas a la vez podrían pasar la revisión de arriba: se cuenta de nuevo.
            if domicilio.fotos.count() > maximo:
                raise lleno
            registrar_cambio(domicilio, usuario, AccionDomicilio.FOTO_AGREGADA)
    except Exception:
        if foto is not None:
            foto.archivo.storage.delete(foto.archivo.name)
        raise
    return foto


def borrar_foto(foto_id, usuario):
    """Borra la foto y su archivo, y lo deja en el historial. El archivo no se conserva."""
    foto = FotoDomicilio.objects.select_related("domicilio").filter(pk=foto_id).first()
    if foto is None:
        raise ErrorDeDomicilio("Esa foto ya no existe.")
    almacen, nombre = foto.archivo.storage, foto.archivo.name
    with transaction.atomic():
        foto.delete()
        registrar_cambio(foto.domicilio, usuario, AccionDomicilio.FOTO_BORRADA)
        transaction.on_commit(lambda: almacen.delete(nombre))
    return foto.domicilio


# --- Consultas ----------------------------------------------------------------------------------


def _nacidos_hasta_para_despacho(hoy):
    """Última fecha de nacimiento con más de `TURNOS_EDAD_DESPACHO_DOMICILIO` años cumplidos hoy."""
    anios = settings.TURNOS_EDAD_DESPACHO_DOMICILIO + 1
    try:
        return hoy.replace(year=hoy.year - anios)
    except ValueError:  # hoy es 29 de febrero y ese año no es bisiesto
        return hoy.replace(year=hoy.year - anios, day=28)


def pacientes_con_despacho():
    """Pacientes con despacho a domicilio (postrados o mayores de 80), en la base: es el mismo
    criterio que `Paciente.es_despacho_domicilio`."""
    limite = _nacidos_hasta_para_despacho(timezone.localdate())
    return Paciente.objects.filter(Q(es_postrado=True) | Q(fecha_nacimiento__lte=limite))


def pacientes_de_despacho(sector=None, estado=None, busqueda=None):
    """La lista de /domicilios/: pacientes con despacho, con su domicilio si lo tienen, por apellido.

    `estado` es uno de ESTADOS_DE_LISTA. La búsqueda acepta un RUT, con o sin puntos, o una
    parte del apellido, sin distinguir mayúsculas ni tildes.
    """
    pacientes = pacientes_con_despacho().select_related("domicilio").order_by("apellidos", "nombres", "pk")
    if sector:
        pacientes = pacientes.filter(domicilio__sector=sector)
    if estado == SIN_DIRECCION:
        pacientes = pacientes.filter(domicilio__isnull=True)
    elif estado:
        pacientes = pacientes.filter(domicilio__estado=estado)

    busqueda = (busqueda or "").strip()
    if not busqueda:
        return list(pacientes)
    try:
        return list(pacientes.filter(rut=normalizar_rut(busqueda)))
    except ValidationError:
        pass
    apellido = normalizar_encabezado(busqueda)
    return [p for p in pacientes if apellido in normalizar_encabezado(p.apellidos)]


def resumen_de_verificacion():
    """Indicador IG04: domicilios verificados sobre registrados, y aparte los pacientes sin dirección."""
    pacientes = pacientes_con_despacho()
    registrados = pacientes.filter(domicilio__isnull=False).count()
    verificados = pacientes.filter(domicilio__estado=EstadoDomicilio.VERIFICADO).count()
    return {
        "registrados": registrados,
        "verificados": verificados,
        "porcentaje": round(100 * verificados / registrados) if registrados else 0,
        "sin_direccion": pacientes.filter(domicilio__isnull=True).count(),
    }
