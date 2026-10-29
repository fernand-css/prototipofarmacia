"""Domicilios de demostración de cargar_datos_demo: uno pendiente y uno verificado, sin pisar cambios."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from cuentas.models import Rol
from reparto.models import AccionDomicilio, CambioDomicilio, Domicilio, EstadoDomicilio, FotoDomicilio
from reparto.servicios import guardar_domicilio
from turnos.tests.helpers import crear_usuario


class DomiciliosDeDemoTests(TestCase):
    def cargar(self):
        salida = StringIO()
        call_command("cargar_datos_demo", stdout=salida)
        return salida.getvalue()

    def test_sin_cuenta_qf_avisa_y_no_crea_domicilios(self):
        salida = self.cargar()
        self.assertIn("no se cargaron el historial de atenciones ni los domicilios", salida)
        self.assertFalse(Domicilio.objects.exists())

    def test_deja_octavio_pendiente_y_pablo_verificado(self):
        qf = crear_usuario("22222222-2", Rol.QF)
        self.assertIn("Octavio, pendiente de verificar, y Pablo, verificado", self.cargar())
        octavio = Domicilio.objects.get(paciente__apellidos="Demo Mayor de 80")
        pablo = Domicilio.objects.get(paciente__apellidos="Demo Postrado")

        self.assertEqual(octavio.estado, EstadoDomicilio.PENDIENTE)
        self.assertFalse(octavio.tiene_coordenadas)
        self.assertEqual(octavio.direccion, "Camino a Dadinco km 4")

        self.assertEqual(pablo.estado, EstadoDomicilio.VERIFICADO)
        self.assertTrue(pablo.tiene_coordenadas)
        self.assertEqual(pablo.verificado_por, qf)
        self.assertEqual(
            [c.accion for c in pablo.cambios.all()], [AccionDomicilio.VERIFICADO, AccionDomicilio.CREADO]
        )
        self.assertFalse(FotoDomicilio.objects.exists())

    def test_es_idempotente_y_no_pisa_lo_editado_en_la_ficha(self):
        crear_usuario("22222222-2", Rol.QF)
        self.cargar()
        octavio = Domicilio.objects.get(paciente__apellidos="Demo Mayor de 80")
        encargado = crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)
        guardar_domicilio(octavio.paciente, {"direccion": "Camino a Dadinco km 6"}, encargado)
        antes = (Domicilio.objects.count(), CambioDomicilio.objects.count())

        self.cargar()
        self.assertEqual((Domicilio.objects.count(), CambioDomicilio.objects.count()), antes)
        self.assertEqual(Domicilio.objects.get(pk=octavio.pk).direccion, "Camino a Dadinco km 6")
        self.assertEqual(Domicilio.objects.count(), 2)
