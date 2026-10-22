"""Funciones y clases base que comparten las pruebas de turnos."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from cuentas.models import Rol, Usuario
from cuentas.validators import calcular_dv
from turnos.models import Categoria, Paciente, RecetaCronica, Turno, Ventanilla, sumar_meses
from turnos.servicios import llamar_siguiente


def nacido_hace(anios, dias_extra=0):
    hoy = timezone.localdate()
    return hoy.replace(year=hoy.year - anios) - timedelta(days=dias_extra)


def crear_paciente(rut="12345678-5", edad=40, **extra):
    return Paciente.objects.create(
        rut=rut, nombres="Ana", apellidos="Prueba", fecha_nacimiento=nacido_hace(edad), **extra
    )


def rut_valido(cuerpo):
    return f"{cuerpo}-{calcular_dv(cuerpo)}"


def crear_receta(paciente, meses_atras=1, vigencia=6, maximas=6, realizadas=0):
    return RecetaCronica.objects.create(
        paciente=paciente,
        fecha_emision=sumar_meses(timezone.localdate(), -meses_atras),
        vigencia_meses=vigencia,
        entregas_maximas=maximas,
        entregas_realizadas=realizadas,
    )


def crear_usuario(rut, rol):
    return Usuario.objects.create_user(
        rut=rut,
        nombres="Prueba",
        apellidos=rol.label,
        password="clave-de-prueba-2026",
        rol=rol,
        debe_cambiar_password=False,
    )


class LlamadoTests(TestCase):
    def setUp(self):
        self.ana = crear_usuario("12345678-5", Rol.FUNCIONARIO)
        self.beto = crear_usuario("11111111-1", Rol.FUNCIONARIO)
        self.v1 = Ventanilla.objects.create(numero=1, funcionario=self.ana)
        self.v2 = Ventanilla.objects.create(numero=2, funcionario=self.beto)
        self.cantidad = 0

    def turno(self, categoria=Categoria.GENERAL, correlativo=1, **extra):
        self.cantidad += 1
        return Turno.objects.create(
            categoria=categoria, correlativo=correlativo, rut=f"{self.cantidad:08d}-0", **extra
        )


class TransicionesTests(LlamadoTests):
    def llamado_hace(self, segundos, **extra):
        """Un turno ya llamado por Ana, cuyo último llamado fue hace `segundos`."""
        self.turno(**extra)
        llamado = llamar_siguiente(self.ana)
        Turno.objects.filter(pk=llamado.pk).update(
            ultimo_llamado_en=timezone.now() - timedelta(seconds=segundos)
        )
        return llamado

    def receta_con_turno_llamado(self, entregas_realizadas=1, entregas_maximas=6):
        paciente = crear_paciente(rut_valido("10000001"), edad=40)
        receta = crear_receta(paciente, maximas=entregas_maximas, realizadas=entregas_realizadas)
        self.turno(paciente=paciente, receta=receta)
        return receta, llamar_siguiente(self.ana)
