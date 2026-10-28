from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cuentas.validators import calcular_dv
from turnos.models import Paciente, RecetaCronica, Ventanilla, sumar_meses

CANTIDAD_VENTANILLAS = 4

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

        self.stdout.write(self.style.SUCCESS(
            f"Listo: {Ventanilla.objects.count()} ventanillas, "
            f"{Paciente.objects.count()} pacientes y {RecetaCronica.objects.count()} recetas."
        ))
        self.stdout.write("RUT de prueba:")
        for paciente in Paciente.objects.filter(apellidos__startswith="Demo"):
            self.stdout.write(f"  {paciente.rut:<11} {paciente.nombre_completo}")
