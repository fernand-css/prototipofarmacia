"""Modelos del domicilio: uno por paciente, estado inicial e historial ordenado."""
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from cuentas.models import Rol
from reparto.models import AccionDomicilio, CambioDomicilio, Domicilio, EstadoDomicilio, Sector
from turnos.tests.helpers import crear_paciente, crear_usuario


class DomicilioTests(TestCase):
    def setUp(self):
        self.encargado = crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)
        self.paciente = crear_paciente(edad=85)

    def domicilio(self, **extra):
        datos = {"paciente": self.paciente, "direccion": "Camino a Dadinco km 4", "actualizado_por": self.encargado}
        datos.update(extra)
        return Domicilio.objects.create(**datos)

    def test_nace_pendiente_y_sin_coordenadas(self):
        domicilio = self.domicilio(sector=Sector.VERDE)
        self.assertEqual(domicilio.estado, EstadoDomicilio.PENDIENTE)
        self.assertFalse(domicilio.tiene_coordenadas)
        self.assertIsNone(domicilio.verificado_en)
        self.assertEqual(self.paciente.domicilio, domicilio)

    def test_un_paciente_no_admite_dos_domicilios(self):
        self.domicilio()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.domicilio(direccion="Otra dirección")

    def test_coordenadas_con_seis_decimales(self):
        domicilio = self.domicilio(latitud=Decimal("-36.499912"), longitud=Decimal("-72.212834"))
        domicilio.refresh_from_db()
        self.assertTrue(domicilio.tiene_coordenadas)
        self.assertEqual(domicilio.latitud, Decimal("-36.499912"))

    def test_el_historial_va_del_mas_reciente_al_mas_antiguo(self):
        domicilio = self.domicilio()
        ahora = timezone.now()
        antiguo = CambioDomicilio.objects.create(
            domicilio=domicilio, usuario=self.encargado, accion=AccionDomicilio.CREADO,
            datos={}, en=ahora - timedelta(minutes=5),
        )
        reciente = CambioDomicilio.objects.create(
            domicilio=domicilio, usuario=self.encargado, accion=AccionDomicilio.EDITADO, datos={}, en=ahora,
        )
        self.assertEqual(list(domicilio.cambios.all()), [reciente, antiguo])
