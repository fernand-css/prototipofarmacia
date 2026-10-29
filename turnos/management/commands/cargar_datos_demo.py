from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cuentas.models import Rol, Usuario
from cuentas.validators import calcular_dv
from turnos.models import (
    Categoria,
    EstadoPreparacion,
    EstadoTurno,
    Paciente,
    Preparacion,
    RecetaCronica,
    Turno,
    Ventanilla,
    sumar_meses,
)

CANTIDAD_VENTANILLAS = 4

# Historial sintético de atenciones con preparación, para que el tótem muestre la espera estimada
# (spec 05): ATENCIONES_POR_DIA en cada uno de los DIAS_HISTORIAL días anteriores a hoy. Usan los
# números G-901 en adelante para no chocar con los turnos reales de esos días.
DIAS_HISTORIAL = 3
ATENCIONES_POR_DIA = 10
PRIMER_CORRELATIVO_HISTORIAL = 901

# (cuerpo del RUT, nombres, apellidos, edad, banderas, receta)
# receta: None o (meses desde la emisión, vigencia en meses, entregas máximas, entregas realizadas)
PACIENTES_DEMO = [
    ("10000001", "Gabriela", "Demo General", 35, {}, None),
    ("10000002", "Adela", "Demo Adulta Mayor", 72, {}, None),
    ("10000003", "Elena", "Demo Embarazada", 28, {"esta_embarazada": True}, None),
    ("10000004", "Diego", "Demo Discapacidad", 40, {"tiene_discapacidad": True}, None),
    ("10000005", "Octavio", "Demo Mayor de 80", 84, {}, None),
    ("10000006", "Pablo", "Demo Postrado", 55, {"es_postrado": True}, None),
    ("10000007", "Carla", "Demo Crónica Vigente", 45, {}, (1, 6, 6, 2)),
    ("10000008", "Agustín", "Demo Receta Agotada", 50, {}, (2, 6, 3, 3)),
    ("10000009", "Valeria", "Demo Receta Vencida", 48, {}, (8, 6, 6, 1)),
    ("10000010", "Mario", "Demo Mayor Crónico", 68, {}, (1, 12, 6, 1)),
]


class Command(BaseCommand):
    help = (
        "Carga ventanillas y pacientes simulados (Rayén) para probar el tótem y el panel. "
        "Se puede ejecutar varias veces. No es para producción."
    )

    @transaction.atomic
    def handle(self, *args, **opciones):
        self.stdout.write(self.style.WARNING(
            "Datos de demostración: no use este comando en un ambiente con datos reales."
        ))

        for numero in range(1, CANTIDAD_VENTANILLAS + 1):
            Ventanilla.objects.get_or_create(numero=numero)

        hoy = timezone.localdate()
        for cuerpo, nombres, apellidos, edad, banderas, receta in PACIENTES_DEMO:
            rut = f"{cuerpo}-{calcular_dv(cuerpo)}"
            paciente, _ = Paciente.objects.update_or_create(
                rut=rut,
                defaults={
                    "nombres": nombres,
                    "apellidos": apellidos,
                    # Seis meses pasado el cumpleaños, para que la edad sea exacta durante el año.
                    "fecha_nacimiento": sumar_meses(hoy, -(12 * edad + 6)),
                    "tiene_discapacidad": False,
                    "esta_embarazada": False,
                    "es_postrado": False,
                    **banderas,
                },
            )
            if not receta:
                continue
            folio = f"DEMO-{cuerpo[-3:]}"
            # Las recetas se crean una sola vez: no se pisan los contadores ya avanzados.
            if not paciente.recetas.exists():
                meses, vigencia, maximas, realizadas = receta
                RecetaCronica.objects.create(
                    paciente=paciente,
                    fecha_emision=sumar_meses(hoy, -meses),
                    vigencia_meses=vigencia,
                    entregas_maximas=maximas,
                    entregas_realizadas=realizadas,
                    folio=folio,
                )
            elif not RecetaCronica.objects.filter(folio=folio).exists():
                # Recetas de demostración creadas antes de que existiera el folio.
                sin_folio = paciente.recetas.filter(folio__isnull=True).first()
                if sin_folio:
                    sin_folio.folio = folio
                    sin_folio.save(update_fields=["folio"])

        self.cargar_historial(hoy)

        self.stdout.write(self.style.SUCCESS(
            f"Listo: {Ventanilla.objects.count()} ventanillas, "
            f"{Paciente.objects.count()} pacientes y {RecetaCronica.objects.count()} recetas."
        ))
        self.stdout.write("RUT de prueba:")
        for paciente in Paciente.objects.filter(apellidos__startswith="Demo"):
            self.stdout.write(f"  {paciente.rut:<11} {paciente.nombre_completo}")

    def cargar_historial(self, hoy):
        """Atenciones ya cerradas en días anteriores, con su preparación. Se atribuyen a la primera
        cuenta QF; sin una, no se cargan. Cada atención se crea una sola vez (por fecha y número)."""
        qf = Usuario.objects.filter(rol=Rol.QF).order_by("pk").first()
        if qf is None:
            self.stdout.write(self.style.WARNING(
                "No hay una cuenta QF: no se cargó el historial de atenciones y el tótem no mostrará "
                "la espera estimada. Cree una con createsuperuser y vuelva a ejecutar este comando."
            ))
            return

        pacientes = list(Paciente.objects.filter(apellidos__startswith="Demo").order_by("rut"))
        zona = timezone.get_current_timezone()
        for dias_atras in range(1, DIAS_HISTORIAL + 1):
            fecha = hoy - timedelta(days=dias_atras)
            for indice in range(ATENCIONES_POR_DIA):
                # De 9:00 en adelante, cada 20 minutos; la atención dura de 4 a 8 minutos.
                inicio = datetime.combine(fecha, time(9), tzinfo=zona) + timedelta(minutes=20 * indice)
                duracion = timedelta(minutes=4 + indice % 5)
                paciente = pacientes[indice % len(pacientes)]
                turno, creado = Turno.objects.get_or_create(
                    fecha=fecha,
                    categoria=Categoria.GENERAL,
                    correlativo=PRIMER_CORRELATIVO_HISTORIAL + indice,
                    defaults={
                        "rut": paciente.rut,
                        "paciente": paciente,
                        "estado": EstadoTurno.ATENDIDO,
                        "atendido_por": qf,
                        "emitido_en": inicio - timedelta(minutes=15),
                        "llamado_en": inicio - timedelta(minutes=1),
                        "ultimo_llamado_en": inicio - timedelta(minutes=1),
                        "veces_llamado": 1,
                        "inicio_atencion_en": inicio,
                        "cierre_en": inicio + duracion,
                    },
                )
                if creado:
                    Preparacion.objects.create(
                        turno=turno,
                        estado=EstadoPreparacion.ENTREGADA,
                        recibida_en=inicio,
                        recibida_por=qf,
                        lista_en=inicio + duracion - timedelta(minutes=1),
                        preparada_por=qf,
                        retirada_en=inicio + duracion,
                        retirada_por=qf,
                    )
        self.stdout.write(
            f"Historial de espera: {DIAS_HISTORIAL * ATENCIONES_POR_DIA} atenciones de los "
            f"{DIAS_HISTORIAL} días anteriores, atribuidas a {qf.nombre_completo}."
        )
