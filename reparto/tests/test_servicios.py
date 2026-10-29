"""Servicios del domicilio: registrar, editar, verificar, marcar pendiente, consultas e IG04."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from cuentas.models import Rol
from reparto.models import AccionDomicilio, Domicilio, EstadoDomicilio, Sector
from reparto.servicios import (
    SIN_DIRECCION,
    ErrorDeDomicilio,
    _nacidos_hasta_para_despacho,
    guardar_domicilio,
    leer_coordenadas,
    marcar_pendiente,
    pacientes_con_despacho,
    pacientes_de_despacho,
    resumen_de_verificacion,
    verificar,
)
from turnos.models import Paciente
from turnos.tests.helpers import crear_paciente, crear_usuario, nacido_hace, rut_valido

LAT, LON = Decimal("-36.499912"), Decimal("-72.212834")


def datos(**extra):
    base = {
        "sector": Sector.VERDE,
        "direccion": "Camino a Dadinco km 4",
        "referencias": "Casa roja frente a la escuela",
        "latitud": None,
        "longitud": None,
    }
    base.update(extra)
    return base


class ServiciosTests(TestCase):
    def setUp(self):
        self.encargado = crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)
        self.otro = crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO)
        self.paciente = crear_paciente(rut_valido("10000001"), edad=85, apellidos="Núñez Soto")

    def verificado(self):
        guardar_domicilio(self.paciente, datos(latitud=LAT, longitud=LON), self.encargado)
        return verificar(self.paciente, self.encargado)


class GuardarTests(ServiciosTests):
    def test_crea_el_domicilio_pendiente_con_su_historial(self):
        domicilio = guardar_domicilio(self.paciente, datos(), self.encargado)
        self.assertEqual(domicilio.estado, EstadoDomicilio.PENDIENTE)
        self.assertEqual(domicilio.actualizado_por, self.encargado)
        cambio = domicilio.cambios.get()
        self.assertEqual(cambio.accion, AccionDomicilio.CREADO)
        self.assertEqual(cambio.usuario, self.encargado)
        self.assertEqual(cambio.datos["direccion"], "Camino a Dadinco km 4")
        self.assertEqual(cambio.datos["estado"], "pendiente")

    def test_editar_deja_quien_y_cuando_y_un_cambio(self):
        guardar_domicilio(self.paciente, datos(), self.encargado)
        domicilio = guardar_domicilio(self.paciente, datos(referencias="Portón verde"), self.otro)
        self.assertEqual(domicilio.referencias, "Portón verde")
        self.assertEqual(domicilio.actualizado_por, self.otro)
        self.assertEqual(
            [c.accion for c in domicilio.cambios.all()], [AccionDomicilio.EDITADO, AccionDomicilio.CREADO]
        )

    def test_sin_cambios_no_escribe_historial(self):
        guardar_domicilio(self.paciente, datos(), self.encargado)
        domicilio = guardar_domicilio(self.paciente, datos(), self.otro)
        self.assertEqual(domicilio.actualizado_por, self.encargado)
        self.assertEqual(domicilio.cambios.count(), 1)

    def test_exige_la_direccion(self):
        with self.assertRaisesMessage(ErrorDeDomicilio, "Escriba la dirección."):
            guardar_domicilio(self.paciente, datos(direccion="  "), self.encargado)
        self.assertFalse(Domicilio.objects.exists())

    def test_exige_las_dos_coordenadas_o_ninguna(self):
        with self.assertRaisesMessage(ErrorDeDomicilio, "la latitud y la longitud"):
            guardar_domicilio(self.paciente, datos(latitud=LAT), self.encargado)

    def test_rechaza_coordenadas_fuera_de_rango(self):
        with self.assertRaisesMessage(ErrorDeDomicilio, "La latitud debe estar entre -90 y 90."):
            guardar_domicilio(self.paciente, datos(latitud=Decimal("-91"), longitud=LON), self.encargado)
        with self.assertRaisesMessage(ErrorDeDomicilio, "La longitud debe estar entre -180 y 180."):
            guardar_domicilio(self.paciente, datos(latitud=LAT, longitud=Decimal("181")), self.encargado)

    def test_un_paciente_sin_despacho_no_tiene_domicilio(self):
        joven = crear_paciente(rut_valido("10000002"), edad=40)
        with self.assertRaisesMessage(ErrorDeDomicilio, "no tiene despacho a domicilio"):
            guardar_domicilio(joven, datos(), self.encargado)

    def test_un_postrado_joven_si_tiene_despacho(self):
        postrado = crear_paciente(rut_valido("10000002"), edad=40, es_postrado=True)
        self.assertTrue(guardar_domicilio(postrado, datos(), self.encargado).pk)


class VerificarTests(ServiciosTests):
    def test_sin_coordenadas_no_se_verifica(self):
        guardar_domicilio(self.paciente, datos(), self.encargado)
        with self.assertRaisesMessage(ErrorDeDomicilio, "registre primero sus coordenadas"):
            verificar(self.paciente, self.encargado)
        self.assertEqual(Domicilio.objects.get().estado, EstadoDomicilio.PENDIENTE)

    def test_con_coordenadas_queda_verificado_con_quien_y_cuando(self):
        domicilio = self.verificado()
        self.assertEqual(domicilio.estado, EstadoDomicilio.VERIFICADO)
        self.assertEqual(domicilio.verificado_por, self.encargado)
        self.assertIsNotNone(domicilio.verificado_en)
        self.assertEqual(domicilio.cambios.first().accion, AccionDomicilio.VERIFICADO)
        self.assertEqual(domicilio.cambios.first().datos["estado"], "verificado")

    def test_verificar_dos_veces_se_aplica_una(self):
        primera = self.verificado()
        with self.assertRaisesMessage(ErrorDeDomicilio, "ya está verificado"):
            verificar(self.paciente, self.otro)
        domicilio = Domicilio.objects.get()
        self.assertEqual(domicilio.verificado_por, self.encargado)
        self.assertEqual(domicilio.verificado_en, primera.verificado_en)
        self.assertEqual(domicilio.cambios.filter(accion=AccionDomicilio.VERIFICADO).count(), 1)

    def test_sin_domicilio_avisa(self):
        with self.assertRaisesMessage(ErrorDeDomicilio, "todavía no tiene un domicilio"):
            verificar(self.paciente, self.encargado)

    def test_editar_un_verificado_lo_deja_verificado(self):
        self.verificado()
        domicilio = guardar_domicilio(
            self.paciente, datos(direccion="Camino a Dadinco km 5", latitud=LAT, longitud=LON), self.otro
        )
        self.assertEqual(domicilio.estado, EstadoDomicilio.VERIFICADO)
        self.assertEqual(domicilio.verificado_por, self.encargado)
        self.assertEqual(domicilio.direccion, "Camino a Dadinco km 5")

    def test_no_se_pueden_borrar_las_coordenadas_de_un_verificado(self):
        self.verificado()
        with self.assertRaisesMessage(ErrorDeDomicilio, "no puede quedar sin coordenadas"):
            guardar_domicilio(self.paciente, datos(), self.encargado)
        self.assertEqual(Domicilio.objects.get().latitud, LAT)


class MarcarPendienteTests(ServiciosTests):
    def test_vuelve_a_pendiente_con_el_motivo_en_el_historial(self):
        self.verificado()
        domicilio = marcar_pendiente(self.paciente, "  Se cambió de casa  ", self.otro)
        self.assertEqual(domicilio.estado, EstadoDomicilio.PENDIENTE)
        self.assertIsNone(domicilio.verificado_por)
        self.assertIsNone(domicilio.verificado_en)
        self.assertEqual(domicilio.latitud, LAT)  # conserva las coordenadas
        cambio = domicilio.cambios.first()
        self.assertEqual(cambio.accion, AccionDomicilio.MARCADO_PENDIENTE)
        self.assertEqual(cambio.motivo, "Se cambió de casa")
        self.assertEqual(cambio.usuario, self.otro)

    def test_exige_un_motivo(self):
        self.verificado()
        with self.assertRaisesMessage(ErrorDeDomicilio, "Escriba por qué"):
            marcar_pendiente(self.paciente, "   ", self.encargado)
        self.assertEqual(Domicilio.objects.get().estado, EstadoDomicilio.VERIFICADO)

    def test_el_motivo_tiene_un_largo_maximo(self):
        self.verificado()
        with self.assertRaisesMessage(ErrorDeDomicilio, "300 caracteres"):
            marcar_pendiente(self.paciente, "x" * 301, self.encargado)

    def test_uno_pendiente_no_se_vuelve_a_marcar(self):
        guardar_domicilio(self.paciente, datos(), self.encargado)
        with self.assertRaisesMessage(ErrorDeDomicilio, "ya está pendiente"):
            marcar_pendiente(self.paciente, "Motivo", self.encargado)

    def test_despues_se_puede_verificar_otra_vez(self):
        self.verificado()
        marcar_pendiente(self.paciente, "Revisar", self.encargado)
        self.assertEqual(verificar(self.paciente, self.otro).verificado_por, self.otro)


class ResumenVacioTests(ServiciosTests):
    def test_sin_domicilios_el_porcentaje_es_cero(self):
        self.assertEqual(
            resumen_de_verificacion(),
            {"registrados": 0, "verificados": 0, "porcentaje": 0, "sin_direccion": 1},
        )


class CoordenadasTests(TestCase):
    def test_formas_validas(self):
        self.assertEqual(leer_coordenadas(""), ())
        self.assertEqual(leer_coordenadas("-36.4999"), (Decimal("-36.499900"),))
        self.assertEqual(leer_coordenadas("-36,4999"), (Decimal("-36.499900"),))
        self.assertEqual(leer_coordenadas("-36.499912, -72.212834"), (LAT, LON))
        self.assertEqual(leer_coordenadas("-36,499912; -72,212834"), (LAT, LON))
        self.assertEqual(leer_coordenadas("-36,499912, -72,212834"), (LAT, LON))
        self.assertEqual(leer_coordenadas(" -36.499912 -72.212834 "), (LAT, LON))

    def test_redondea_a_seis_decimales(self):
        self.assertEqual(leer_coordenadas("-36.4999125"), (Decimal("-36.499913"),))

    def test_formas_invalidas(self):
        for texto in ("abc", "-36.5 sur", "1, 2, 3", "36°30'S"):
            with self.subTest(texto=texto), self.assertRaises(ErrorDeDomicilio):
                leer_coordenadas(texto)


class ConsultasTests(ServiciosTests):
    def setUp(self):
        super().setUp()
        self.verde = self.paciente  # 85 años
        self.azul = crear_paciente(rut_valido("10000002"), edad=90, apellidos="Pérez")
        self.sin_direccion = crear_paciente(rut_valido("10000003"), edad=40, es_postrado=True, apellidos="Rojas")
        self.joven = crear_paciente(rut_valido("10000004"), edad=50, apellidos="Joven")
        guardar_domicilio(self.verde, datos(sector=Sector.VERDE, latitud=LAT, longitud=LON), self.encargado)
        verificar(self.verde, self.encargado)
        guardar_domicilio(self.azul, datos(sector=Sector.AZUL), self.encargado)

    def test_solo_pacientes_con_despacho_por_apellido(self):
        self.assertEqual(pacientes_de_despacho(), [self.verde, self.azul, self.sin_direccion])

    def test_el_criterio_coincide_con_es_despacho_domicilio(self):
        # Justo 81 años hoy, un día antes de cumplirlos, 80 justos y 81 hace un día.
        hoy = timezone.localdate()
        fechas = [nacido_hace(81), nacido_hace(81) + timedelta(days=1), nacido_hace(80), nacido_hace(81, 1)]
        for indice, fecha in enumerate(fechas, start=1):
            crear_paciente(rut_valido(f"2000000{indice}"), apellidos=f"Borde {indice}", fecha_nacimiento=fecha)
        en_base = set(pacientes_con_despacho())
        for paciente in Paciente.objects.all():
            with self.subTest(paciente=paciente.apellidos, hoy=hoy):
                self.assertEqual(paciente in en_base, paciente.es_despacho_domicilio)

    def test_el_29_de_febrero_usa_el_28(self):
        self.assertEqual(_nacidos_hasta_para_despacho(date(2028, 2, 29)), date(1947, 2, 28))
        self.assertEqual(_nacidos_hasta_para_despacho(date(2026, 10, 28)), date(1945, 10, 28))

    def test_filtra_por_sector_y_estado(self):
        self.assertEqual(pacientes_de_despacho(sector=Sector.AZUL), [self.azul])
        self.assertEqual(pacientes_de_despacho(estado=EstadoDomicilio.VERIFICADO), [self.verde])
        self.assertEqual(pacientes_de_despacho(estado=EstadoDomicilio.PENDIENTE), [self.azul])
        self.assertEqual(pacientes_de_despacho(estado=SIN_DIRECCION), [self.sin_direccion])
        self.assertEqual(pacientes_de_despacho(sector=Sector.ROJO), [])

    def test_busca_por_rut_y_por_apellido_sin_tildes(self):
        rut = rut_valido("10000002")
        self.assertEqual(pacientes_de_despacho(busqueda=f"10.000.002-{rut[-1]}"), [self.azul])
        self.assertEqual(pacientes_de_despacho(busqueda="nunez"), [self.verde])
        self.assertEqual(pacientes_de_despacho(busqueda="PEREZ"), [self.azul])
        self.assertEqual(pacientes_de_despacho(busqueda="Joven"), [])  # sin despacho

    def test_resumen_de_verificacion(self):
        self.assertEqual(
            resumen_de_verificacion(),
            {"registrados": 2, "verificados": 1, "porcentaje": 50, "sin_direccion": 1},
        )
