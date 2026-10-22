"""Tótem público: teclado, resultado, avisos y privacidad de la pantalla."""
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Usuario
from turnos.models import Turno
from turnos.tests.helpers import crear_paciente, crear_receta


class TotemTests(TestCase):
    def setUp(self):
        self.rut = "12345678-5"
        self.url = reverse("turnos:totem_turno")

    def digitar(self, rut, **extra):
        return self.client.post(self.url, {"rut": rut, **extra})

    def test_el_totem_carga_sin_sesion(self):
        respuesta = self.client.get(reverse("turnos:totem"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Saque su turno")

    def test_el_totem_no_muestra_la_barra_de_sesion_ni_al_usuario(self):
        usuario = Usuario.objects.create_user("11111111-1", "Rosa", "Funcionaria", "clave-segura-123")
        usuario.debe_cambiar_password = False
        usuario.save()
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("turnos:totem"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Rosa")
        self.assertNotContains(respuesta, "Cerrar sesión")

    def test_emite_un_turno_con_el_rut_en_cualquier_formato(self):
        for formato in ("12.345.678-5", "123456785", "12345678-5"):
            respuesta = self.digitar(formato)
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, "G-001")
        self.assertEqual(Turno.objects.count(), 1)

    def test_segundo_intento_indica_que_ya_tiene_turno(self):
        self.digitar(self.rut)
        respuesta = self.digitar(self.rut)
        self.assertContains(respuesta, "Usted ya tiene un turno")

    def test_rut_con_digito_verificador_malo_muestra_el_error_y_no_crea_turno(self):
        respuesta = self.digitar("12.345.678-0")
        self.assertContains(respuesta, "el dígito verificador no corresponde")
        self.assertContains(respuesta, "Saque su turno")
        self.assertEqual(Turno.objects.count(), 0)

    def test_rut_vacio_muestra_el_error(self):
        respuesta = self.digitar("")
        self.assertContains(respuesta, "totem__error")
        self.assertEqual(Turno.objects.count(), 0)

    def test_el_resultado_no_muestra_nombre_ni_rut(self):
        crear_paciente(self.rut, edad=70)
        respuesta = self.digitar(self.rut)
        self.assertContains(respuesta, "P-001")
        self.assertContains(respuesta, "Atención preferencial")
        self.assertNotContains(respuesta, "Ana")
        self.assertNotContains(respuesta, "Prueba")
        self.assertNotContains(respuesta, "12345678")
        self.assertNotContains(respuesta, "12.345.678")

    def test_el_resultado_ofrece_imprimir_y_vuelve_al_inicio_solo(self):
        respuesta = self.digitar(self.rut)
        self.assertContains(respuesta, "Imprimir")
        self.assertContains(respuesta, "window.print()")
        segundos = settings.TURNOS_SEGUNDOS_RESULTADO_TOTEM
        self.assertContains(respuesta, f"reinicio({{ segundos: {segundos}, destino: '{reverse('turnos:totem')}' }})")

    def test_postrado_ve_el_aviso_de_domicilio_y_puede_pedir_turno_igual(self):
        crear_paciente(self.rut, edad=55, es_postrado=True)
        aviso = self.digitar(self.rut)
        self.assertContains(aviso, "Su despacho es a domicilio")
        self.assertContains(aviso, "Pedir turno igual")
        self.assertNotContains(aviso, "Ana")
        self.assertEqual(Turno.objects.count(), 0)

        turno = self.digitar(self.rut, insistir="1")
        self.assertContains(turno, "G-001")
        self.assertEqual(Turno.objects.count(), 1)

    def test_receta_agotada_muestra_el_mensaje_de_renovacion(self):
        paciente = crear_paciente(self.rut, edad=40)
        crear_receta(paciente, maximas=2, realizadas=2)
        respuesta = self.digitar(self.rut)
        self.assertContains(respuesta, "renovación médica")
        self.assertEqual(Turno.objects.count(), 0)

    def test_solo_acepta_post_en_la_emision(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
