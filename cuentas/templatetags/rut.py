from django import template

register = template.Library()


@register.filter
def rut_legible(rut):
    """Muestra un RUT guardado como 12345678-5 en la forma que se lee en Chile: 12.345.678-5."""
    cuerpo, guion, dv = str(rut or "").partition("-")
    if not guion or not cuerpo.isdigit():
        return rut
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"
