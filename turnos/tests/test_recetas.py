"""Avance de las recetas crónicas (HU-21): propiedades del modelo y consulta /recetas/ por RUT."""
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Rol
from turnos.tests.helpers import crear_paciente, crear_receta, crear_usuario


class AvanceDeRecetaTests(TestCase):
    def setUp(self):
        self.paciente = crear_paciente()

    def test_entrega_en_curso_y_restantes(self):
        receta = crear_receta(self.paciente, maximas=6, realizadas=2)
        self.assertEqual((receta.entrega_en_curso, receta.entregas_restantes), (3, 4))

    def test_agotada_no_pasa_del_maximo(self):
        receta = crear_receta(self.paciente, maximas=6, realizadas=6)
        self.assertEqual((receta.entrega_en_curso, receta.entregas_restantes), (6, 0))

    def test_estado(self):
        self.assertEqual(crear_receta(self.paciente).estado, "vigente")
        self.assertEqual(crear_receta(self.paciente, maximas=3, realizadas=3).estado, "agotada")
        self.assertEqual(crear_receta(self.paciente, meses_atras=7, vigencia=6).estado, "vencida")


class RecetasVistaTests(TestCase):
    def setUp(self):
        self.funcionario = crear_usuario("9876543-3", Rol.FUNCIONARIO)
        self.paciente = crear_paciente("12345678-5")
        self.vigente = crear_receta(self.paciente, maximas=6, realizadas=2)
        self.vigente.folio = "R-VIGENTE"
        self.vigente.save()
        crear_receta(self.paciente, meses_atras=2, maximas=3, realizadas=3)
        crear_receta(self.paciente, meses_atras=8, vigencia=6, maximas=6, realizadas=1)

    def buscar(self, rut):
        return self.client.post(reverse("turnos:recetas"), {"rut": rut})

    def test_sin_sesion_redirige_al_login(self):
        for respuesta in (self.client.get(reverse("turnos:recetas")), self.buscar("12345678-5")):
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn(reverse("cuentas:entrar"), respuesta.url)

    def test_encargado_de_terreno_recibe_403(self):
        self.client.force_login(crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO))
        self.assertEqual(self.client.get(reverse("turnos:recetas")).status_code, 403)
        self.assertEqual(self.buscar("12345678-5").status_code, 403)

    def test_funcionario_y_qf_pueden_consultar(self):
        for usuario in (self.funcionario, crear_usuario("11111111-1", Rol.QF)):
            self.client.force_login(usuario)
            with self.subTest(rol=usuario.rol):
                self.assertEqual(self.client.get(reverse("turnos:recetas")).status_code, 200)
                self.assertContains(self.buscar("12345678-5"), "Ana Prueba")

    def test_la_barra_lleva_a_recetas(self):
        self.client.force_login(self.funcionario)
        self.assertContains(self.client.get(reverse("turnos:atencion")), reverse("turnos:recetas"))

    def test_busqueda_con_y_sin_puntos(self):
        self.client.force_login(self.funcionario)
        for rut in ("12.345.678-5", "123456785", "12345678-5"):
            with self.subTest(rut=rut):
                respuesta = self.buscar(rut)
                self.assertContains(respuesta, "12.345.678-5")
                self.assertContains(respuesta, "Receta R-VIGENTE")

    def test_lista_cada_receta_con_su_avance_y_estado(self):
        self.client.force_login(self.funcionario)
        respuesta = self.buscar("12345678-5")
        self.assertContains(respuesta, "2 de 6 entregas realizadas, quedan 4.")
        self.assertContains(respuesta, "3 de 3 entregas realizadas, quedan 0.")
        self.assertContains(respuesta, "1 de 6 entregas realizadas, quedan 5.")
        self.assertContains(respuesta, f"vence el {self.vigente.fecha_vencimiento:%d-%m-%Y}")
        self.assertContains(respuesta, f"Emitida el {self.vigente.fecha_emision:%d-%m-%Y}")
        for estado in ("Vigente", "Agotada", "Vencida"):
            self.assertContains(respuesta, f">{estado}</span>")
        self.assertContains(respuesta, "Receta sin folio", count=2)

    def test_rut_invalido_muestra_el_error(self):
        self.client.force_login(self.funcionario)
        respuesta = self.buscar("12.345.678-9")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "dígito verificador")
        self.assertNotContains(respuesta, "Ana Prueba")

    def test_rut_sin_paciente(self):
        self.client.force_login(self.funcionario)
        self.assertContains(self.buscar("11.111.111-1"), "No hay recetas registradas para este RUT")

    def test_paciente_sin_recetas(self):
        crear_paciente("11111111-1")
        self.client.force_login(self.funcionario)
        self.assertContains(self.buscar("11111111-1"), "No hay recetas registradas para este RUT")

    def test_el_rut_no_queda_en_la_url(self):
        self.client.force_login(self.funcionario)
        respuesta = self.client.get(reverse("turnos:recetas"))
        self.assertContains(respuesta, 'method="post"')
        self.assertContains(respuesta, f'action="{reverse("turnos:recetas")}"')
        respuesta = self.buscar("12345678-5")
        self.assertEqual(respuesta.status_code, 200)  # responde ahí mismo, sin redirigir a una URL con el RUT
        self.assertEqual(respuesta.request["PATH_INFO"], reverse("turnos:recetas"))
        self.assertEqual(respuesta.request["QUERY_STRING"], "")
