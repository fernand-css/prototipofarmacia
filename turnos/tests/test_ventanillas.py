"""Ventanillas: permisos, administración por la QF y apertura y cierre por el funcionario."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.views import View

from cuentas.models import Rol
from turnos.mixins import SoloAtencion
from turnos.models import Categoria, EstadoTurno, Turno, Ventanilla
from turnos.servicios import ErrorDeAtencion, cambiar_estado_ventanilla, crear_ventanilla
from turnos.tests.helpers import crear_usuario


class VistaDePrueba(SoloAtencion, View):
    def get(self, request):
        return HttpResponse("ok")


class SoloAtencionTests(TestCase):
    def pedir(self, usuario=None):
        peticion = RequestFactory().get("/prueba/")
        peticion.user = usuario or AnonymousUser()
        return VistaDePrueba.as_view()(peticion)

    def test_funcionario_y_qf_pasan(self):
        self.assertEqual(self.pedir(crear_usuario("12345678-5", Rol.FUNCIONARIO)).status_code, 200)
        self.assertEqual(self.pedir(crear_usuario("11111111-1", Rol.QF)).status_code, 200)

    def test_encargado_de_terreno_recibe_403(self):
        with self.assertRaises(PermissionDenied):
            self.pedir(crear_usuario("12345678-5", Rol.ENCARGADO_TERRENO))

    def test_sin_sesion_redirige_al_login(self):
        respuesta = self.pedir()
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("cuentas:entrar"), respuesta.url)


class VentanillasQFTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("11111111-1", Rol.QF)
        self.funcionario = crear_usuario("12345678-5", Rol.FUNCIONARIO)
        self.client.force_login(self.qf)

    def cambiar_estado(self, ventanilla):
        return self.client.post(reverse("turnos:ventanilla_cambiar_estado", args=[ventanilla.pk]))

    def test_la_qf_ve_la_lista(self):
        Ventanilla.objects.create(numero=1)
        respuesta = self.client.get(reverse("turnos:ventanillas"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Habilitada")

    def test_la_qf_crea_ventanillas_con_el_numero_siguiente(self):
        for _ in range(5):
            self.client.post(reverse("turnos:ventanilla_crear"))
        self.assertEqual(list(Ventanilla.objects.values_list("numero", flat=True)), [1, 2, 3, 4, 5])
        self.assertTrue(Ventanilla.objects.get(numero=5).habilitada)

    def test_la_qf_deshabilita_y_vuelve_a_habilitar(self):
        ventanilla = Ventanilla.objects.create(numero=5)
        self.cambiar_estado(ventanilla)
        ventanilla.refresh_from_db()
        self.assertFalse(ventanilla.habilitada)
        self.cambiar_estado(ventanilla)
        ventanilla.refresh_from_db()
        self.assertTrue(ventanilla.habilitada)

    def test_deshabilitar_una_ventanilla_abierta_la_libera(self):
        ventanilla = Ventanilla.objects.create(numero=1, funcionario=self.funcionario)
        self.cambiar_estado(ventanilla)
        ventanilla.refresh_from_db()
        self.assertFalse(ventanilla.habilitada)
        self.assertIsNone(ventanilla.funcionario)

    def test_no_deshabilita_con_un_turno_en_curso(self):
        ventanilla = Ventanilla.objects.create(numero=1, funcionario=self.funcionario)
        for estado in (EstadoTurno.LLAMADO, EstadoTurno.EN_ATENCION):
            Turno.objects.all().delete()
            Turno.objects.create(
                categoria=Categoria.GENERAL, correlativo=1, rut="12345678-5",
                estado=estado, ventanilla=ventanilla, atendido_por=self.funcionario,
            )
            respuesta = self.cambiar_estado(ventanilla)
            ventanilla.refresh_from_db()
            self.assertTrue(ventanilla.habilitada)
            self.assertEqual(ventanilla.funcionario, self.funcionario)
            self.assertContains(self.client.get(respuesta.url), "turno en curso")

    def test_un_turno_ya_atendido_no_impide_deshabilitar(self):
        ventanilla = Ventanilla.objects.create(numero=1)
        Turno.objects.create(
            categoria=Categoria.GENERAL, correlativo=1, rut="12345678-5",
            estado=EstadoTurno.ATENDIDO, ventanilla=ventanilla, atendido_por=self.funcionario,
        )
        self.cambiar_estado(ventanilla)
        ventanilla.refresh_from_db()
        self.assertFalse(ventanilla.habilitada)

    def test_funcionario_y_encargado_reciben_403_en_todas_las_rutas(self):
        ventanilla = Ventanilla.objects.create(numero=1)
        for usuario in (self.funcionario, crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO)):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse("turnos:ventanillas")).status_code, 403)
            self.assertEqual(self.client.post(reverse("turnos:ventanilla_crear")).status_code, 403)
            self.assertEqual(self.cambiar_estado(ventanilla).status_code, 403)
        self.assertEqual(Ventanilla.objects.count(), 1)
        self.assertTrue(Ventanilla.objects.get().habilitada)

    def test_sin_sesion_redirige_al_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("turnos:ventanillas"))
        self.assertRedirects(respuesta, f"{reverse('cuentas:entrar')}?next={reverse('turnos:ventanillas')}")


class AtencionVentanillaTests(TestCase):
    def setUp(self):
        self.ana = crear_usuario("12345678-5", Rol.FUNCIONARIO)
        self.beto = crear_usuario("11111111-1", Rol.FUNCIONARIO)
        self.v1 = Ventanilla.objects.create(numero=1)
        self.v2 = Ventanilla.objects.create(numero=2)
        self.v3 = Ventanilla.objects.create(numero=3, habilitada=False)
        self.client.force_login(self.ana)

    def abrir(self, ventanilla):
        return self.client.post(reverse("turnos:abrir_ventanilla"), {"ventanilla": ventanilla.pk}, follow=True)

    def terminar(self):
        return self.client.post(reverse("turnos:terminar_turno"), follow=True)

    def test_sin_ventanilla_ofrece_solo_las_habilitadas_y_libres(self):
        self.v2.funcionario = self.beto
        self.v2.save()
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertContains(respuesta, "Ventanilla 1")
        self.assertNotContains(respuesta, "Ventanilla 2")
        self.assertNotContains(respuesta, "Ventanilla 3")

    def test_abre_una_ventanilla_y_ve_su_puesto(self):
        respuesta = self.abrir(self.v1)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.funcionario, self.ana)
        self.assertContains(respuesta, "Abrió la ventanilla 1")
        self.assertContains(respuesta, "Terminar turno")
        self.assertNotContains(respuesta, "Elija la ventanilla")

    def test_dos_funcionarios_no_pueden_abrir_la_misma_ventanilla(self):
        self.abrir(self.v1)
        self.client.force_login(self.beto)
        respuesta = self.abrir(self.v1)
        self.assertContains(respuesta, "ya no está disponible")
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.funcionario, self.ana)
        self.assertFalse(Ventanilla.objects.filter(funcionario=self.beto).exists())

    def test_no_se_puede_abrir_una_ventanilla_deshabilitada(self):
        respuesta = self.abrir(self.v3)
        self.assertContains(respuesta, "ya no está disponible")
        self.v3.refresh_from_db()
        self.assertIsNone(self.v3.funcionario)

    def test_un_funcionario_no_puede_tener_dos_ventanillas(self):
        self.abrir(self.v1)
        respuesta = self.abrir(self.v2)
        self.assertContains(respuesta, "Ya tiene una ventanilla abierta")
        self.v2.refresh_from_db()
        self.assertIsNone(self.v2.funcionario)

    def test_un_valor_invalido_no_rompe_el_panel(self):
        for valor in ("", "abc"):
            respuesta = self.client.post(reverse("turnos:abrir_ventanilla"), {"ventanilla": valor}, follow=True)
            self.assertContains(respuesta, "Elija una ventanilla")
        self.assertEqual(Ventanilla.objects.filter(funcionario__isnull=False).count(), 0)

    def test_terminar_turno_libera_la_ventanilla(self):
        self.abrir(self.v1)
        respuesta = self.terminar()
        self.assertContains(respuesta, "Terminó su turno en la ventanilla 1")
        self.v1.refresh_from_db()
        self.assertIsNone(self.v1.funcionario)
        self.assertContains(respuesta, "Elija la ventanilla")

    def test_otro_funcionario_puede_tomar_la_ventanilla_liberada(self):
        self.abrir(self.v1)
        self.terminar()
        self.client.force_login(self.beto)
        self.abrir(self.v1)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.funcionario, self.beto)

    def test_no_termina_con_un_turno_en_curso(self):
        self.abrir(self.v1)
        for estado in (EstadoTurno.LLAMADO, EstadoTurno.EN_ATENCION):
            Turno.objects.all().delete()
            Turno.objects.create(
                categoria=Categoria.GENERAL, correlativo=1, rut="22222222-2",
                estado=estado, ventanilla=self.v1, atendido_por=self.ana,
                llamado_en=timezone.now(), ultimo_llamado_en=timezone.now(), veces_llamado=1,
            )
            respuesta = self.terminar()
            self.assertContains(respuesta, "Tiene un turno en curso")
            self.v1.refresh_from_db()
            self.assertEqual(self.v1.funcionario, self.ana)

    def test_terminar_sin_ventanilla_abierta_avisa(self):
        self.assertContains(self.terminar(), "No tiene una ventanilla abierta")

    def test_la_qf_tambien_puede_atender(self):
        self.client.force_login(crear_usuario("22222222-2", Rol.QF))
        self.assertEqual(self.client.get(reverse("turnos:atencion")).status_code, 200)
        self.abrir(self.v1)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.funcionario.rol, Rol.QF)

    def test_el_encargado_de_terreno_recibe_403(self):
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        self.assertEqual(self.client.get(reverse("turnos:atencion")).status_code, 403)
        self.assertEqual(self.abrir(self.v1).status_code, 403)
        self.assertEqual(self.terminar().status_code, 403)
        self.v1.refresh_from_db()
        self.assertIsNone(self.v1.funcionario)

    def test_sin_sesion_redirige_al_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertRedirects(respuesta, f"{reverse('cuentas:entrar')}?next={reverse('turnos:atencion')}")

    def test_la_deshabilitacion_por_la_qf_libera_la_ventanilla_abierta(self):
        self.abrir(self.v1)
        self.client.force_login(crear_usuario("22222222-2", Rol.QF))
        self.client.post(reverse("turnos:ventanilla_cambiar_estado", args=[self.v1.pk]))
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertContains(respuesta, "Elija la ventanilla")
        self.assertNotContains(respuesta, "Ventanilla 1")


class CrearVentanillaTests(TestCase):
    def test_numera_a_partir_de_la_ultima_y_la_deja_habilitada(self):
        self.assertEqual(crear_ventanilla().numero, 1)
        self.assertEqual(crear_ventanilla().numero, 2)
        Ventanilla.objects.filter(numero=2).delete()
        self.assertEqual(crear_ventanilla().numero, 2)
        self.assertTrue(Ventanilla.objects.get(numero=2).habilitada)

    def test_respeta_los_huecos_sin_reutilizarlos(self):
        Ventanilla.objects.create(numero=7)
        self.assertEqual(crear_ventanilla().numero, 8)

    def test_reintenta_si_otro_creo_el_mismo_numero_a_la_vez(self):
        original = Ventanilla.objects.create
        llamadas = []

        def create_con_choque(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 1:
                raise IntegrityError("choque simulado")
            return original(*args, **kwargs)

        with mock.patch.object(Ventanilla.objects, "create", side_effect=create_con_choque):
            ventanilla = crear_ventanilla()
        self.assertEqual(ventanilla.numero, 1)
        self.assertEqual(len(llamadas), 2)


class CambiarEstadoVentanillaTests(TestCase):
    def setUp(self):
        self.ana = crear_usuario("12345678-5", Rol.FUNCIONARIO)

    def turno_en_curso(self, ventanilla, estado):
        return Turno.objects.create(
            categoria=Categoria.GENERAL, correlativo=1, rut="22222222-2", estado=estado,
            ventanilla=ventanilla, atendido_por=self.ana,
        )

    def test_habilita_una_ventanilla_deshabilitada(self):
        ventanilla = Ventanilla.objects.create(numero=1, habilitada=False)
        self.assertTrue(cambiar_estado_ventanilla(ventanilla.pk).habilitada)
        ventanilla.refresh_from_db()
        self.assertTrue(ventanilla.habilitada)

    def test_deshabilita_y_libera_a_quien_la_tenia_abierta(self):
        ventanilla = Ventanilla.objects.create(numero=1, funcionario=self.ana)
        resultado = cambiar_estado_ventanilla(ventanilla.pk)
        self.assertFalse(resultado.habilitada)
        ventanilla.refresh_from_db()
        self.assertFalse(ventanilla.habilitada)
        self.assertIsNone(ventanilla.funcionario)

    def test_no_deshabilita_con_un_turno_llamado_o_en_atencion(self):
        ventanilla = Ventanilla.objects.create(numero=1, funcionario=self.ana)
        for estado in (EstadoTurno.LLAMADO, EstadoTurno.EN_ATENCION):
            Turno.objects.all().delete()
            self.turno_en_curso(ventanilla, estado)
            with self.assertRaisesMessage(ErrorDeAtencion, "La ventanilla 1 tiene un turno en curso"):
                cambiar_estado_ventanilla(ventanilla.pk)
            ventanilla.refresh_from_db()
            self.assertTrue(ventanilla.habilitada)
            self.assertEqual(ventanilla.funcionario, self.ana)

    def test_un_turno_en_curso_de_otro_dia_no_lo_impide(self):
        ventanilla = Ventanilla.objects.create(numero=1)
        turno = self.turno_en_curso(ventanilla, EstadoTurno.LLAMADO)
        Turno.objects.filter(pk=turno.pk).update(fecha=timezone.localdate() - timedelta(days=1))
        self.assertFalse(cambiar_estado_ventanilla(ventanilla.pk).habilitada)

    def test_una_ventanilla_inexistente_lanza_does_not_exist(self):
        with self.assertRaises(Ventanilla.DoesNotExist):
            cambiar_estado_ventanilla(9999)

    def test_la_vista_responde_404_si_la_ventanilla_no_existe(self):
        self.client.force_login(crear_usuario("11111111-1", Rol.QF))
        respuesta = self.client.post(reverse("turnos:ventanilla_cambiar_estado", args=[9999]))
        self.assertEqual(respuesta.status_code, 404)
