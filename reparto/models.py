"""Módulo de reparto a domicilio. Por ahora, el domicilio de cada paciente con despacho (HU-12)."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Sector(models.TextChoices):
    """Sectores territoriales del CESFAM (modelo MAIS)."""

    VERDE = "verde", "Verde"
    AZUL = "azul", "Azul"
    ROJO = "rojo", "Rojo"


class EstadoDomicilio(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente de verificar"
    VERIFICADO = "verificado", "Verificado"


class Domicilio(models.Model):
    """Dónde vive un paciente con despacho a domicilio (HU-12).

    Un paciente con despacho sin fila aquí está «sin dirección». Verificar exige coordenadas, y
    una edición posterior no quita la verificación: para pedir otra se usa «Marcar pendiente».
    """

    paciente = models.OneToOneField(
        "turnos.Paciente", on_delete=models.PROTECT, related_name="domicilio", verbose_name="paciente"
    )
    sector = models.CharField("sector", max_length=10, choices=Sector.choices, blank=True)
    direccion = models.CharField("dirección", max_length=200)
    referencias = models.TextField("referencias", max_length=1000, blank=True)
    latitud = models.DecimalField("latitud", max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField("longitud", max_digits=9, decimal_places=6, null=True, blank=True)
    estado = models.CharField(
        "estado", max_length=12, choices=EstadoDomicilio.choices, default=EstadoDomicilio.PENDIENTE
    )
    verificado_en = models.DateTimeField("verificado en", null=True, blank=True)
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="verificado por",
    )
    actualizado_en = models.DateTimeField("actualizado en", default=timezone.now)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="actualizado por"
    )
    # Última carga del padrón que lo creó o modificó.
    carga = models.ForeignKey(
        "turnos.CargaPadron",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="última carga",
    )

    class Meta:
        verbose_name = "domicilio"
        verbose_name_plural = "domicilios"

    def __str__(self):
        return f"Domicilio de {self.paciente.nombre_completo}"

    @property
    def tiene_coordenadas(self):
        return self.latitud is not None and self.longitud is not None


class FotoDomicilio(models.Model):
    """Foto del domicilio o de su entorno, ya achicada y sin metadatos. Nunca se sirve en público."""

    domicilio = models.ForeignKey(
        Domicilio, on_delete=models.PROTECT, related_name="fotos", verbose_name="domicilio"
    )
    archivo = models.ImageField("archivo", upload_to="domicilios/")  # nombre aleatorio, siempre .jpg
    ancho = models.PositiveIntegerField("ancho (px)")
    alto = models.PositiveIntegerField("alto (px)")
    subida_en = models.DateTimeField("subida en", default=timezone.now)
    subida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="subida por"
    )

    class Meta:
        verbose_name = "foto de domicilio"
        verbose_name_plural = "fotos de domicilios"
        ordering = ["subida_en", "pk"]

    def __str__(self):
        return f"Foto {self.pk} de {self.domicilio}"


class AccionDomicilio(models.TextChoices):
    CREADO = "creado", "Registró el domicilio"
    EDITADO = "editado", "Editó el domicilio"
    VERIFICADO = "verificado", "Verificó el domicilio"
    MARCADO_PENDIENTE = "marcado_pendiente", "Lo marcó pendiente de verificar"
    FOTO_AGREGADA = "foto_agregada", "Agregó una foto"
    FOTO_BORRADA = "foto_borrada", "Borró una foto"
    CARGA_PADRON = "carga_padron", "Cargado desde el padrón"


class CambioDomicilio(models.Model):
    """Historial de un domicilio: cada acción, quién y cuándo, y cómo quedó (HU-12, RNF-01)."""

    domicilio = models.ForeignKey(
        Domicilio, on_delete=models.PROTECT, related_name="cambios", verbose_name="domicilio"
    )
    en = models.DateTimeField("en", default=timezone.now)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="usuario"
    )
    accion = models.CharField("acción", max_length=20, choices=AccionDomicilio.choices)
    # {"sector", "direccion", "referencias", "latitud", "longitud", "estado"} después del cambio.
    datos = models.JSONField("datos")
    motivo = models.CharField("motivo", max_length=300, blank=True)  # solo al marcar pendiente
    carga = models.ForeignKey(
        "turnos.CargaPadron",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="carga",
    )

    class Meta:
        verbose_name = "cambio de domicilio"
        verbose_name_plural = "historial de domicilios"
        ordering = ["-en", "-pk"]

    def __str__(self):
        return f"{self.get_accion_display()} ({self.en:%d-%m-%Y %H:%M})"
