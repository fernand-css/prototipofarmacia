"""Llamar al siguiente paciente y re-llamar."""
from datetime import timedelta
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from cuentas.models import Rol
from turnos.models import Categoria, EstadoTurno, Turno, Ventanilla
from turnos.servicios import ErrorDeAtencion, llamar_siguiente, re_llamar
from turnos.tests.helpers import LlamadoTests, crear_usuario


class LlamarSiguienteTests(LlamadoTests):
    def test_llama_al_turno_que_elige_el_motor_y_lo_asigna(self):
        general = self.turno(Categoria.GENERAL, 1)
        urgencia = self.turno(Categoria.URGENCIA, 1)
        llamado = llamar_siguiente(self.ana)
        self.assertEqual(llamado.pk, urgencia.pk)
        self.assertEqual(llamado.estado, EstadoTurno.LLAMADO)
        self.assertEqual(llamado.ventanilla, self.v1)
        self.assertEqual(llamado.atendido_por, self.ana)
        self.assertEqual(llamado.veces_llamado, 1)
        self.assertIsNotNone(llamado.llamado_en)
        self.assertEqual(llamado.llamado_en, llamado.ultimo_llamado_en)
        general.refresh_from_db()
        self.assertEqual(general.estado, EstadoTurno.EN_ESPERA)

    def test_sin_ventanilla_abierta_no_llama(self):
        self.turno()
        Ventanilla.objects.filter(pk=self.v1.pk).update(funcionario=None)
        with self.assertRaisesMessage(ErrorDeAtencion, "Abra una ventanilla"):
            llamar_siguiente(self.ana)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.EN_ESPERA)

    def test_sin_nadie_en_espera_avisa(self):
        with self.assertRaisesMessage(ErrorDeAtencion, "No hay pacientes en espera"):
            llamar_siguiente(self.ana)

    def test_ignora_los_turnos_de_otros_dias(self):
        self.turno(fecha=timezone.localdate() - timedelta(days=1))
        with self.assertRaisesMessage(ErrorDeAtencion, "No hay pacientes en espera"):
            llamar_siguiente(self.ana)

    def test_no_llama_otro_mientras_tiene_un_turno_en_curso(self):
        self.turno(correlativo=1)
        self.turno(correlativo=2)
        llamar_siguiente(self.ana)
        with self.assertRaisesMessage(ErrorDeAtencion, "Ya tiene un turno en curso"):
            llamar_siguiente(self.ana)
        self.assertEqual(Turno.objects.filter(estado=EstadoTurno.EN_ESPERA).count(), 1)

    def test_con_un_solo_turno_dos_funcionarios_no_lo_reciben_los_dos(self):
        self.turno()
        recibido = llamar_siguiente(self.ana)
        with self.assertRaisesMessage(ErrorDeAtencion, "No hay pacientes en espera"):
            llamar_siguiente(self.beto)
        self.assertEqual(recibido.ventanilla, self.v1)
        self.assertEqual(Turno.objects.filter(ventanilla=self.v2).count(), 0)

    def test_con_dos_turnos_cada_ventanilla_recibe_uno_distinto(self):
        self.turno(correlativo=1)
        self.turno(correlativo=2)
        primero = llamar_siguiente(self.ana)
        segundo = llamar_siguiente(self.beto)
        self.assertNotEqual(primero.pk, segundo.pk)
        self.assertEqual({primero.ventanilla, segundo.ventanilla}, {self.v1, self.v2})

    def test_si_otro_se_adelanta_en_la_misma_eleccion_vuelve_a_elegir(self):
        primero = self.turno(correlativo=1)
        segundo = self.turno(correlativo=2)
        desactualizado = Turno.objects.get(pk=primero.pk)  # lo que vio Beto antes de que Ana lo llamara
        llamar_siguiente(self.ana)
        with mock.patch("turnos.servicios.elegir_siguiente", side_effect=[desactualizado, segundo]) as motor:
            recibido = llamar_siguiente(self.beto)
        self.assertEqual(motor.call_count, 2)
        self.assertEqual(recibido.pk, segundo.pk)
        primero.refresh_from_db()
        self.assertEqual(primero.ventanilla, self.v1)

    def test_si_siempre_se_adelantan_se_rinde_con_un_mensaje(self):
        primero = self.turno()
        desactualizado = Turno.objects.get(pk=primero.pk)
        llamar_siguiente(self.ana)
        with mock.patch("turnos.servicios.elegir_siguiente", return_value=desactualizado):
            with self.assertRaisesMessage(ErrorDeAtencion, "No se pudo llamar"):
                llamar_siguiente(self.beto)

    def test_una_ventanilla_deshabilitada_no_recibe_turnos(self):
        self.turno()
        Ventanilla.objects.filter(pk=self.v1.pk).update(habilitada=False)
        with self.assertRaisesMessage(ErrorDeAtencion, "fue deshabilitada"):
            llamar_siguiente(self.ana)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.EN_ESPERA)

    def test_respeta_la_proporcion_entre_llamados_sucesivos(self):
        for n in range(1, 4):
            self.turno(Categoria.GENERAL, n)
        self.turno(Categoria.PREFERENCIAL, 1)
        numeros = []
        for _ in range(4):
            turno = llamar_siguiente(self.ana)
            numeros.append(turno.numero)
            Turno.objects.filter(pk=turno.pk).update(estado=EstadoTurno.ATENDIDO)
        self.assertEqual(numeros, ["G-001", "G-002", "P-001", "G-003"])


class ReLlamarTests(LlamadoTests):
    def test_suma_un_llamado_y_conserva_ventanilla_y_funcionario(self):
        self.turno()
        original = llamar_siguiente(self.ana)
        antes = timezone.now() - timedelta(seconds=30)
        Turno.objects.filter(pk=original.pk).update(ultimo_llamado_en=antes)

        repetido = re_llamar(self.ana)

        self.assertEqual(repetido.pk, original.pk)
        self.assertEqual(repetido.veces_llamado, 2)
        self.assertGreater(repetido.ultimo_llamado_en, antes)
        self.assertEqual(repetido.llamado_en, original.llamado_en)
        self.assertEqual(repetido.ventanilla, self.v1)
        self.assertEqual(repetido.atendido_por, self.ana)
        self.assertEqual(repetido.estado, EstadoTurno.LLAMADO)

    def test_se_puede_re_llamar_varias_veces(self):
        self.turno()
        llamar_siguiente(self.ana)
        re_llamar(self.ana)
        self.assertEqual(re_llamar(self.ana).veces_llamado, 3)

    def test_sin_turno_llamado_avisa(self):
        with self.assertRaisesMessage(ErrorDeAtencion, "No tiene un turno llamado"):
            re_llamar(self.ana)

    def test_no_re_llama_un_turno_en_atencion(self):
        self.turno()
        llamado = llamar_siguiente(self.ana)
        Turno.objects.filter(pk=llamado.pk).update(estado=EstadoTurno.EN_ATENCION)
        with self.assertRaisesMessage(ErrorDeAtencion, "No tiene un turno llamado"):
            re_llamar(self.ana)
        self.assertEqual(Turno.objects.get().veces_llamado, 1)

    def test_no_toca_el_turno_de_otro_funcionario(self):
        self.turno()
        llamar_siguiente(self.ana)
        with self.assertRaises(ErrorDeAtencion):
            re_llamar(self.beto)
        self.assertEqual(Turno.objects.get().veces_llamado, 1)


class PanelLlamadoVistasTests(LlamadoTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.ana)

    def test_el_panel_ofrece_llamar_siguiente_sin_turno_en_curso(self):
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertContains(respuesta, "Llamar siguiente")
        self.assertNotContains(respuesta, "Re-llamar")

    def test_llamar_muestra_el_turno_y_el_boton_de_re_llamar(self):
        self.turno(Categoria.PREFERENCIAL, 12)
        respuesta = self.client.post(reverse("turnos:llamar_siguiente"), follow=True)
        self.assertContains(respuesta, "Llamó al turno P-012")
        self.assertContains(respuesta, "P-012")
        self.assertContains(respuesta, "Re-llamar")
        self.assertNotContains(respuesta, "Llamar siguiente")

    def test_re_llamar_actualiza_el_contador_en_pantalla(self):
        self.turno()
        self.client.post(reverse("turnos:llamar_siguiente"))
        respuesta = self.client.post(reverse("turnos:re_llamar"), follow=True)
        self.assertContains(respuesta, "Re-llamó al turno G-001")
        self.assertContains(respuesta, "Llamado 2 veces")

    def test_sin_pacientes_muestra_el_aviso(self):
        respuesta = self.client.post(reverse("turnos:llamar_siguiente"), follow=True)
        self.assertContains(respuesta, "No hay pacientes en espera")

    def test_el_encargado_de_terreno_recibe_403_y_sin_sesion_va_al_login(self):
        self.turno()
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        for nombre in ("llamar_siguiente", "re_llamar"):
            self.assertEqual(self.client.post(reverse(f"turnos:{nombre}")).status_code, 403)
        self.client.logout()
        for nombre in ("llamar_siguiente", "re_llamar"):
            self.assertEqual(self.client.post(reverse(f"turnos:{nombre}")).status_code, 302)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.EN_ESPERA)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(reverse("turnos:llamar_siguiente")).status_code, 405)
        self.assertEqual(self.client.get(reverse("turnos:re_llamar")).status_code, 405)
