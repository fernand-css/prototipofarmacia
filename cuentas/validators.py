import re

from django.core.exceptions import ValidationError

FORMATO_RUT = re.compile(r"\d{7,8}[\dK]")


def normalizar_rut(valor):
    """Lleva cualquier formato de RUT al de almacenamiento: sin puntos, con guion y K mayúscula."""
    limpio = re.sub(r"[.\s\-]", "", str(valor or "")).upper()
    if not FORMATO_RUT.fullmatch(limpio):
        raise ValidationError(
            "Ingrese un RUT válido, con 7 u 8 dígitos más el dígito verificador."
        )
    return f"{limpio[:-1]}-{limpio[-1]}"


def calcular_dv(cuerpo):
    """Dígito verificador por módulo 11, con multiplicadores cíclicos del 2 al 7."""
    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut(valor):
    """Valida el dígito verificador. Acepta el RUT en cualquier formato."""
    normalizado = normalizar_rut(valor)
    cuerpo, dv = normalizado.split("-")
    if dv != calcular_dv(cuerpo):
        raise ValidationError(
            "El RUT ingresado no es válido: el dígito verificador no corresponde."
        )
