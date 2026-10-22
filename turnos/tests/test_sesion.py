"""Política de sesión del panel: el sondeo de la fila solo la renueva si hay actividad real del usuario."""
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cuentas.middleware import CABECERA_ACTIVIDAD
from cuentas.models import Rol
from turnos.models import Ventanilla
from turnos.tests.helpers import crear_usuario

# El cliente de pruebas pasa las cabeceras HTTP como META con este formato.
META_ACTIVIDAD = "HTTP_" + CABECERA_ACTIVIDAD.upper().replace("-", "_")


class SesionYSondeoTests(TestCase):
    def setUp(self):
        self.usuario = crear_usuario("12345678-5", Rol.FUNCIONARIO)
        self.client.force_login(self.usuario)
        self.clave = self.client.session.session_key
        self.cola = reverse("turnos:cola")

    def vence_en(self, segundos):
        """Deja la sesión a `segundos` de vencer, como si llevara casi 30 minutos sin actividad."""
        Session.objects.filter(session_key=self.clave).update(
            expire_date=timezone.now() + timedelta(seconds=segundos)
        )

    def segundos_restantes(self):
        return (Session.objects.get(session_key=self.clave).expire_date - timezone.now()).total_seconds()

    def test_el_sondeo_sin_actividad_no_renueva_la_sesion(self):
        self.vence_en(60)
        respuesta = self.client.get(self.cola)
        self.assertEqual(respuesta.status_code, 200)
        self.assertLess(self.segundos_restantes(), 61)

    def test_el_sondeo_con_actividad_la_renueva_a_la_duracion_completa(self):
        self.vence_en(60)
        self.client.get(self.cola, **{META_ACTIVIDAD: "1"})
        self.assertGreater(self.segundos_restantes(), settings.SESSION_COOKIE_AGE - 5)

    def test_una_cabecera_con_otro_valor_no_cuenta_como_actividad(self):
        self.vence_en(60)
        self.client.get(self.cola, **{META_ACTIVIDAD: "0"})
        self.assertLess(self.segundos_restantes(), 61)

    def test_las_demas_paginas_siguen_renovando_la_sesion(self):
        self.vence_en(60)
        self.client.get(reverse("turnos:atencion"))
        self.assertGreater(self.segundos_restantes(), settings.SESSION_COOKIE_AGE - 5)

    def test_una_accion_del_funcionario_renueva_la_sesion(self):
        self.vence_en(60)
        self.client.post(reverse("turnos:llamar_siguiente"))
        self.assertGreater(self.segundos_restantes(), settings.SESSION_COOKIE_AGE - 5)

    def test_el_sondeo_sin_actividad_no_reenvia_la_cookie_de_sesion(self):
        respuesta = self.client.get(self.cola)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, respuesta.cookies)

    def test_el_sondeo_con_actividad_reenvia_la_cookie_de_sesion(self):
        respuesta = self.client.get(self.cola, **{META_ACTIVIDAD: "1"})
        self.assertIn(settings.SESSION_COOKIE_NAME, respuesta.cookies)

    def test_la_respuesta_sin_renovar_sigue_variando_por_cookie(self):
        respuesta = self.client.get(self.cola)
        self.assertIn("Cookie", respuesta["Vary"])

    def test_un_panel_olvidado_vence_aunque_siga_sondeando(self):
        """Sin actividad, aun con 400 consultas seguidas (33 minutos de sondeo), la sesión no se extiende."""
        self.vence_en(30)
        for _ in range(400):
            self.client.get(self.cola)
        self.assertLess(self.segundos_restantes(), 31)

    def test_con_la_sesion_vencida_el_sondeo_lleva_al_login_y_no_falla(self):
        Session.objects.filter(session_key=self.clave).update(expire_date=timezone.now() - timedelta(seconds=1))
        respuesta = self.client.get(self.cola)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("cuentas:entrar"), respuesta.url)

    def test_con_la_sesion_vencida_se_borra_la_cookie_vieja(self):
        Session.objects.filter(session_key=self.clave).update(expire_date=timezone.now() - timedelta(seconds=1))
        respuesta = self.client.get(self.cola)
        self.assertEqual(respuesta.cookies[settings.SESSION_COOKIE_NAME].value, "")

    def test_el_sondeo_sin_sesion_va_al_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.cola).status_code, 302)

    def test_la_configuracion_usa_el_middleware_de_sesion_por_actividad(self):
        self.assertIn("cuentas.middleware.SesionPorActividad", settings.MIDDLEWARE)
        self.assertNotIn("django.contrib.sessions.middleware.SessionMiddleware", settings.MIDDLEWARE)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)

    def test_el_panel_le_pasa_al_navegador_la_ventana_de_actividad(self):
        Ventanilla.objects.create(numero=1, funcionario=self.usuario)
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertContains(respuesta, f"ventanaActividad: {settings.TURNOS_SEGUNDOS_ACTIVIDAD_RECIENTE}")
