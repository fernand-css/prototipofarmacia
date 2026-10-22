from django.conf import settings

from turnos.models import Categoria, EstadoTurno, Turno


def _mas_antiguo(en_espera, categoria):
    return en_espera.filter(categoria=categoria).order_by("emitido_en", "pk").first()


def _generales_seguidos(fecha):
    """Generales llamados hoy, uno tras otro, desde el último preferencial.

    Las urgencias no cuentan ni cortan la racha. Los ausentes sí cuentan: fueron llamados y
    ocuparon su lugar en la proporción.
    """
    llamados = (
        Turno.objects.filter(fecha=fecha, llamado_en__isnull=False)
        .exclude(categoria=Categoria.URGENCIA)
        .order_by("-llamado_en", "-pk")
        .values_list("categoria", flat=True)
    )
    seguidos = 0
    for categoria in llamados.iterator():
        if categoria != Categoria.GENERAL:
            break
        seguidos += 1
    return seguidos


def elegir_siguiente(fecha):
    """Devuelve el turno que corresponde llamar ahora, o None si no hay nadie en espera.

    No modifica datos: asignar el turno a una ventanilla es tarea de quien llama.
    Orden: urgencia primero; luego preferencial y general en la proporción configurada en
    `TURNOS_GENERALES_POR_PREFERENCIAL`; dentro de cada categoría, por orden de emisión.
    """
    en_espera = Turno.objects.filter(fecha=fecha, estado=EstadoTurno.EN_ESPERA)

    urgencia = _mas_antiguo(en_espera, Categoria.URGENCIA)
    if urgencia:
        return urgencia

    preferencial = _mas_antiguo(en_espera, Categoria.PREFERENCIAL)
    if preferencial and _generales_seguidos(fecha) >= settings.TURNOS_GENERALES_POR_PREFERENCIAL:
        return preferencial

    return _mas_antiguo(en_espera, Categoria.GENERAL) or preferencial
