"""Iniciar, finalizar y marcar ausente, más el turno de urgencia desde el panel."""
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Rol
from turnos.models import Categoria, EstadoTurno, Turno
from turnos.servicios import (
    ErrorDeAtencion,
    TipoResultado,
    emitir_turno,
    finalizar_atencion,
    iniciar_atencion,
    llamar_siguiente,
    marcar_ausente,
    re_llamar,
    segundos_para_ausente,
)
from turnos.tests.helpers import (
    LlamadoTests,
    TransicionesTests,
    crear_paciente,
    crear_receta,
    crear_usuario,
    rut_valido,
)


class IniciarAtencionTests(TransicionesTests):
    def test_pasa_de_llamado_a_en_atencion_y_guarda_la_hora(self):
        self.turno()
        llamado = llamar_siguiente(self.ana)
        turno = iniciar_atencion(self.ana)
        self.assertEqual(turno.pk, llamado.pk)
        self.assertEqual(turno.estado, EstadoTurno.EN_ATENCION)
        self.assertIsNotNone(turno.inicio_atencion_en)
        self.assertEqual(turno.ventanilla, self.v1)

    def test_sin_turno_llamado_avisa(self):
        with self.assertRaisesMessage(ErrorDeAtencion, "No tiene un turno llamado para iniciar"):
            iniciar_atencion(self.ana)

    def test_no_se_puede_iniciar_dos_veces(self):
        self.turno()
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        inicio = Turno.objects.get().inicio_atencion_en
        with self.assertRaises(ErrorDeAtencion):
            iniciar_atencion(self.ana)
        self.assertEqual(Turno.objects.get().inicio_atencion_en, inicio)

    def test_no_inicia_el_turno_de_otro_funcionario(self):
        self.turno()
        llamar_siguiente(self.ana)
        with self.assertRaises(ErrorDeAtencion):
            iniciar_atencion(self.beto)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)


class FinalizarAtencionTests(TransicionesTests):
    def test_cierra_el_turno_como_atendido(self):
        self.turno()
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        turno = finalizar_atencion(self.ana)
        self.assertEqual(turno.estado, EstadoTurno.ATENDIDO)
        self.assertIsNotNone(turno.cierre_en)

    def test_no_se_puede_finalizar_sin_iniciar(self):
        self.turno()
        llamar_siguiente(self.ana)
        with self.assertRaisesMessage(ErrorDeAtencion, "No tiene una atención en curso"):
            finalizar_atencion(self.ana)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)

    def test_sin_turno_avisa(self):
        with self.assertRaises(ErrorDeAtencion):
            finalizar_atencion(self.ana)

    def test_suma_exactamente_una_entrega_a_la_receta(self):
        receta, _ = self.receta_con_turno_llamado(entregas_realizadas=2)
        iniciar_atencion(self.ana)
        finalizar_atencion(self.ana)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 3)

    def test_finalizar_dos_veces_no_suma_dos_entregas(self):
        receta, _ = self.receta_con_turno_llamado(entregas_realizadas=2)
        iniciar_atencion(self.ana)
        finalizar_atencion(self.ana)
        with self.assertRaises(ErrorDeAtencion):
            finalizar_atencion(self.ana)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 3)

    def test_un_turno_sin_receta_no_toca_ninguna(self):
        paciente = crear_paciente(rut_valido("10000001"), edad=40)
        receta = crear_receta(paciente, realizadas=1)
        self.turno()  # turno sin receta asociada
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        finalizar_atencion(self.ana)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 1)

    def test_si_falla_el_cierre_no_se_suma_la_entrega(self):
        receta, llamado = self.receta_con_turno_llamado(entregas_realizadas=2)
        iniciar_atencion(self.ana)
        with self.assertRaises(ErrorDeAtencion):
            finalizar_atencion(self.beto)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 2)
        self.assertEqual(Turno.objects.get(pk=llamado.pk).estado, EstadoTurno.EN_ATENCION)

    def test_al_llegar_al_maximo_el_paciente_queda_bloqueado_en_el_totem(self):
        paciente = crear_paciente(rut_valido("10000001"), edad=40)
        crear_receta(paciente, maximas=2, realizadas=1)
        emitir_turno(paciente.rut)
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        finalizar_atencion(self.ana)
        self.assertEqual(emitir_turno(paciente.rut).tipo, TipoResultado.BLOQUEADO)

    def test_el_funcionario_queda_libre_para_llamar_al_siguiente(self):
        self.turno(correlativo=1)
        self.turno(correlativo=2)
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        finalizar_atencion(self.ana)
        self.assertEqual(llamar_siguiente(self.ana).numero, "G-002")


class MarcarAusenteTests(TransicionesTests):
    def test_se_rechaza_antes_del_plazo(self):
        self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE - 5)
        with self.assertRaisesMessage(ErrorDeAtencion, "Debe esperar"):
            marcar_ausente(self.ana)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)

    def test_se_acepta_pasado_el_plazo(self):
        llamado = self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 1)
        turno = marcar_ausente(self.ana)
        self.assertEqual(turno.pk, llamado.pk)
        self.assertEqual(turno.estado, EstadoTurno.AUSENTE)
        self.assertIsNotNone(turno.cierre_en)
        self.assertEqual(turno.ventanilla, self.v1)
        self.assertEqual(turno.atendido_por, self.ana)

    def test_un_re_llamado_reinicia_el_plazo(self):
        self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 30)
        re_llamar(self.ana)
        with self.assertRaisesMessage(ErrorDeAtencion, "Debe esperar"):
            marcar_ausente(self.ana)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)

    def test_el_plazo_cuenta_desde_el_ultimo_llamado_y_no_desde_el_primero(self):
        llamado = self.llamado_hace(segundos=10)
        Turno.objects.filter(pk=llamado.pk).update(
            llamado_en=timezone.now() - timedelta(seconds=600)
        )
        with self.assertRaises(ErrorDeAtencion):
            marcar_ausente(self.ana)

    def test_no_se_puede_marcar_ausente_a_quien_esta_en_atencion(self):
        self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 1)
        iniciar_atencion(self.ana)
        with self.assertRaisesMessage(ErrorDeAtencion, "No tiene un turno llamado"):
            marcar_ausente(self.ana)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.EN_ATENCION)

    def test_sin_turno_avisa(self):
        with self.assertRaisesMessage(ErrorDeAtencion, "No tiene un turno llamado"):
            marcar_ausente(self.ana)

    def test_no_modifica_la_receta(self):
        receta, llamado = self.receta_con_turno_llamado(entregas_realizadas=2)
        Turno.objects.filter(pk=llamado.pk).update(
            ultimo_llamado_en=timezone.now() - timedelta(seconds=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 1)
        )
        marcar_ausente(self.ana)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 2)

    def test_el_ausente_es_final_y_el_paciente_saca_un_turno_nuevo(self):
        paciente_rut = rut_valido("10000001")
        emitir_turno(paciente_rut)
        llamar_siguiente(self.ana)
        Turno.objects.update(
            ultimo_llamado_en=timezone.now() - timedelta(seconds=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 1)
        )
        marcar_ausente(self.ana)
        self.assertEqual(emitir_turno(paciente_rut).turno.numero, "G-002")
        self.assertEqual(Turno.objects.get(correlativo=1).estado, EstadoTurno.AUSENTE)

    def test_el_funcionario_queda_libre_para_llamar_al_siguiente(self):
        self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 1)
        self.turno(correlativo=2)
        marcar_ausente(self.ana)
        self.assertEqual(llamar_siguiente(self.ana).numero, "G-002")

    def test_segundos_para_ausente(self):
        llamado = self.llamado_hace(segundos=20)
        faltan = segundos_para_ausente(Turno.objects.get(pk=llamado.pk))
        self.assertIn(faltan, (settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE - 20, settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE - 19))
        Turno.objects.filter(pk=llamado.pk).update(ultimo_llamado_en=timezone.now() - timedelta(hours=1))
        self.assertEqual(segundos_para_ausente(Turno.objects.get(pk=llamado.pk)), 0)


class PanelTransicionesVistasTests(TransicionesTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.ana)

    def test_con_un_turno_llamado_el_panel_ofrece_iniciar_re_llamar_y_ausente(self):
        self.llamado_hace(segundos=10)
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertContains(respuesta, "Iniciar atención")
        self.assertContains(respuesta, "Re-llamar")
        self.assertContains(respuesta, "Ausente")
        self.assertNotContains(respuesta, "Finalizar atención")
        self.assertContains(respuesta, f"faltan: {settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE - 10}")

    def test_pasado_el_plazo_el_contador_del_panel_parte_en_cero(self):
        self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 5)
        self.assertContains(self.client.get(reverse("turnos:atencion")), "faltan: 0")

    def test_en_atencion_el_panel_solo_ofrece_finalizar(self):
        self.llamado_hace(segundos=10)
        iniciar_atencion(self.ana)
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertContains(respuesta, "Finalizar atención")
        self.assertNotContains(respuesta, "Iniciar atención")
        self.assertNotContains(respuesta, "Re-llamar")

    def test_flujo_completo_desde_el_panel(self):
        self.turno()
        self.client.post(reverse("turnos:llamar_siguiente"))
        self.assertContains(self.client.post(reverse("turnos:iniciar_atencion"), follow=True), "Inició la atención del turno G-001")
        self.assertContains(self.client.post(reverse("turnos:finalizar_atencion"), follow=True), "Finalizó la atención del turno G-001")
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.ATENDIDO)

    def test_ausente_enviado_a_mano_antes_del_plazo_se_rechaza(self):
        self.llamado_hace(segundos=5)
        respuesta = self.client.post(reverse("turnos:marcar_ausente"), follow=True)
        self.assertContains(respuesta, "Debe esperar")
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)

    def test_ausente_despues_del_plazo_funciona_desde_el_panel(self):
        self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 1)
        respuesta = self.client.post(reverse("turnos:marcar_ausente"), follow=True)
        self.assertContains(respuesta, "Marcó como ausente al turno G-001")
        self.assertContains(respuesta, "Llamar siguiente")

    def test_encargado_de_terreno_recibe_403_y_sin_sesion_va_al_login(self):
        self.llamado_hace(segundos=settings.TURNOS_SEGUNDOS_MINIMOS_AUSENTE + 1)
        nombres = ("iniciar_atencion", "finalizar_atencion", "marcar_ausente")
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        for nombre in nombres:
            self.assertEqual(self.client.post(reverse(f"turnos:{nombre}")).status_code, 403)
        self.client.logout()
        for nombre in nombres:
            self.assertEqual(self.client.post(reverse(f"turnos:{nombre}")).status_code, 302)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)

    def test_solo_aceptan_post(self):
        for nombre in ("iniciar_atencion", "finalizar_atencion", "marcar_ausente"):
            self.assertEqual(self.client.get(reverse(f"turnos:{nombre}")).status_code, 405)


class UrgenciaDesdeElPanelTests(LlamadoTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.ana)
        self.rut = rut_valido("10000001")
        self.url = reverse("turnos:emitir_urgencia")

    def emitir(self, rut=None, **extra):
        return self.client.post(self.url, {"rut": rut or self.rut, **extra}, follow=True)

    def test_el_panel_ofrece_el_formulario_de_urgencia_con_una_ventanilla_abierta(self):
        self.assertContains(self.client.get(reverse("turnos:atencion")), "Emitir urgencia")

    def test_emite_un_turno_de_urgencia_con_letra_u(self):
        respuesta = self.emitir()
        self.assertContains(respuesta, "Se emitió el turno de urgencia U-001")
        turno = Turno.objects.get()
        self.assertEqual((turno.categoria, turno.estado, turno.rut), (Categoria.URGENCIA, EstadoTurno.EN_ESPERA, self.rut))

    def test_acepta_el_rut_con_puntos(self):
        self.emitir("10.000.001-" + self.rut[-1])
        self.assertEqual(Turno.objects.get().rut, self.rut)

    def test_un_paciente_g045_en_espera_queda_anulado_y_recibe_u001_que_se_llama_primero(self):
        otro = self.turno(correlativo=1)  # un general que llegó antes
        Turno.objects.create(categoria=Categoria.GENERAL, correlativo=45, rut=self.rut)

        respuesta = self.emitir()

        self.assertContains(respuesta, "Se emitió el turno de urgencia U-001")
        self.assertContains(respuesta, "Se anuló el turno G-045")
        self.assertEqual(Turno.objects.get(categoria=Categoria.GENERAL, correlativo=45).estado, EstadoTurno.ANULADO)
        llamado = llamar_siguiente(self.ana)
        self.assertEqual(llamado.numero, "U-001")
        self.assertEqual(llamado.rut, self.rut)
        self.assertEqual(Turno.objects.get(pk=otro.pk).estado, EstadoTurno.EN_ESPERA)

    def test_con_el_turno_ya_llamado_no_emite_urgencia(self):
        Turno.objects.create(categoria=Categoria.GENERAL, correlativo=45, rut=self.rut)
        llamar_siguiente(self.ana)
        respuesta = self.emitir()
        self.assertContains(respuesta, "G-045")
        self.assertContains(respuesta, "no se emite urgencia")
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)

    def test_con_una_urgencia_ya_en_espera_avisa_y_no_duplica(self):
        self.emitir()
        respuesta = self.emitir()
        self.assertContains(respuesta, "ya tiene la urgencia U-001 en espera")
        self.assertEqual(Turno.objects.count(), 1)

    def test_un_rut_invalido_muestra_el_error_y_no_crea_turno(self):
        respuesta = self.emitir("12.345.678-0")
        self.assertContains(respuesta, "el dígito verificador no corresponde")
        self.assertEqual(Turno.objects.count(), 0)

    def test_no_aplica_el_aviso_de_domicilio_ni_el_bloqueo_por_receta(self):
        paciente = crear_paciente(self.rut, edad=84, es_postrado=True)
        crear_receta(paciente, maximas=1, realizadas=1)
        self.emitir()
        self.assertEqual(Turno.objects.get().numero, "U-001")

    def test_la_qf_tambien_puede_emitir(self):
        self.client.force_login(crear_usuario("22222222-2", Rol.QF))
        self.emitir()
        self.assertEqual(Turno.objects.count(), 1)

    def test_encargado_de_terreno_recibe_403_y_sin_sesion_va_al_login(self):
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        self.assertEqual(self.client.post(self.url, {"rut": self.rut}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"rut": self.rut}).status_code, 302)
        self.assertEqual(Turno.objects.count(), 0)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_el_resultado_informa_el_turno_anulado(self):
        anterior = emitir_turno(self.rut).turno
        resultado = emitir_turno(self.rut, desde_panel=True)
        self.assertEqual(resultado.anulado.pk, anterior.pk)
        self.assertIsNone(emitir_turno(rut_valido("10000002"), desde_panel=True).anulado)
