import calendar

from django.conf import settings
from django.db import models
from django.utils import timezone

from cuentas.validators import normalizar_rut, validar_rut


def sumar_meses(fecha, meses):
    """Suma meses de calendario; si el día no existe en el mes destino usa el último."""
    indice = fecha.month - 1 + meses
    anio = fecha.year + indice // 12
    mes = indice % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


class Categoria(models.TextChoices):
    URGENCIA = "urgencia", "Urgencia"
    PREFERENCIAL = "preferencial", "Preferencial"
    GENERAL = "general", "General"


LETRA_CATEGORIA = {
    Categoria.URGENCIA: "U",
    Categoria.PREFERENCIAL: "P",
    Categoria.GENERAL: "G",
}


class EstadoTurno(models.TextChoices):
    EN_ESPERA = "en_espera", "En espera"
    LLAMADO = "llamado", "Llamado"
    EN_ATENCION = "en_atencion", "En atención"
    ATENDIDO = "atendido", "Atendido"
    AUSENTE = "ausente", "Ausente"
    ANULADO = "anulado", "Anulado"


ESTADOS_ACTIVOS = (EstadoTurno.EN_ESPERA, EstadoTurno.LLAMADO, EstadoTurno.EN_ATENCION)
# Ya salió de la fila y un funcionario lo tiene a su cargo.
ESTADOS_EN_CURSO = (EstadoTurno.LLAMADO, EstadoTurno.EN_ATENCION)


class Paciente(models.Model):
    """Simulación de Rayén: datos mínimos para clasificar al paciente en el tótem."""

    rut = models.CharField("RUT", max_length=10, unique=True, validators=[validar_rut])
    nombres = models.CharField("nombres", max_length=100)
    apellidos = models.CharField("apellidos", max_length=100)
    fecha_nacimiento = models.DateField("fecha de nacimiento")
    tiene_discapacidad = models.BooleanField("tiene discapacidad", default=False)
    esta_embarazada = models.BooleanField("está embarazada", default=False)
    es_postrado = models.BooleanField("es postrado", default=False)

    class Meta:
        verbose_name = "paciente"
        verbose_name_plural = "pacientes"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.rut})"

    def save(self, *args, **kwargs):
        self.rut = normalizar_rut(self.rut)
        super().save(*args, **kwargs)

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}"

    @property
    def edad(self):
        hoy = timezone.localdate()
        nacimiento = self.fecha_nacimiento
        cumplio = (hoy.month, hoy.day) >= (nacimiento.month, nacimiento.day)
        return hoy.year - nacimiento.year - (0 if cumplio else 1)

    @property
    def es_preferencial(self):
        return (
            self.edad >= settings.TURNOS_EDAD_PREFERENCIAL
            or self.tiene_discapacidad
            or self.esta_embarazada
        )

    @property
    def es_despacho_domicilio(self):
        return self.es_postrado or self.edad > settings.TURNOS_EDAD_DESPACHO_DOMICILIO


class RecetaCronica(models.Model):
    """Simulación de Rayén: receta crónica con vigencia y un máximo de entregas parciales."""

    paciente = models.ForeignKey(
        Paciente, on_delete=models.PROTECT, related_name="recetas", verbose_name="paciente"
    )
    fecha_emision = models.DateField("fecha de emisión")
    vigencia_meses = models.PositiveSmallIntegerField("vigencia (meses)")
    entregas_maximas = models.PositiveSmallIntegerField("entregas máximas")
    entregas_realizadas = models.PositiveSmallIntegerField("entregas realizadas", default=0)

    class Meta:
        verbose_name = "receta crónica"
        verbose_name_plural = "recetas crónicas"
        ordering = ["fecha_emision"]

    def __str__(self):
        return f"Receta de {self.paciente.nombre_completo} del {self.fecha_emision:%d-%m-%Y}"

    @property
    def fecha_vencimiento(self):
        return sumar_meses(self.fecha_emision, self.vigencia_meses)

    @property
    def esta_vencida(self):
        return timezone.localdate() > self.fecha_vencimiento

    @property
    def esta_agotada(self):
        return self.entregas_realizadas >= self.entregas_maximas

    @property
    def es_utilizable(self):
        return not self.esta_vencida and not self.esta_agotada


class Ventanilla(models.Model):
    numero = models.PositiveSmallIntegerField("número", unique=True)
    habilitada = models.BooleanField("habilitada", default=True)
    funcionario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ventanilla_abierta",
        verbose_name="funcionario que la tiene abierta",
    )

    class Meta:
        verbose_name = "ventanilla"
        verbose_name_plural = "ventanillas"
        ordering = ["numero"]

    def __str__(self):
        return f"Ventanilla {self.numero}"


class Turno(models.Model):
    fecha = models.DateField("día operativo", default=timezone.localdate)
    categoria = models.CharField("categoría", max_length=15, choices=Categoria.choices)
    correlativo = models.PositiveIntegerField("correlativo")
    rut = models.CharField("RUT", max_length=10, db_index=True)
    paciente = models.ForeignKey(
        Paciente, null=True, blank=True, on_delete=models.PROTECT, verbose_name="paciente"
    )
    receta = models.ForeignKey(
        RecetaCronica, null=True, blank=True, on_delete=models.PROTECT, verbose_name="receta"
    )
    estado = models.CharField(
        "estado", max_length=15, choices=EstadoTurno.choices, default=EstadoTurno.EN_ESPERA
    )
    ventanilla = models.ForeignKey(
        Ventanilla, null=True, blank=True, on_delete=models.PROTECT, verbose_name="ventanilla"
    )
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="atendido por",
    )
    emitido_en = models.DateTimeField("emitido en", default=timezone.now)
    llamado_en = models.DateTimeField("primer llamado", null=True, blank=True)
    ultimo_llamado_en = models.DateTimeField("último llamado", null=True, blank=True)
    veces_llamado = models.PositiveSmallIntegerField("veces llamado", default=0)
    inicio_atencion_en = models.DateTimeField("inicio de la atención", null=True, blank=True)
    cierre_en = models.DateTimeField("cierre", null=True, blank=True)

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["fecha", "emitido_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["fecha", "categoria", "correlativo"],
                name="turno_numero_unico_por_dia",
            ),
            models.UniqueConstraint(
                fields=["fecha", "rut"],
                condition=models.Q(estado__in=ESTADOS_ACTIVOS),
                name="turno_un_activo_por_rut_y_dia",
            ),
        ]

    def __str__(self):
        return self.numero

    @property
    def numero(self):
        return f"{LETRA_CATEGORIA[self.categoria]}-{self.correlativo:03d}"

    @property
    def es_cronico(self):
        return self.receta_id is not None
