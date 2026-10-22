"""Fila de espera del panel."""
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Rol
from turnos.models import Categoria, EstadoTurno, Ventanilla
from turnos.servicios import TURNOS_VISIBLES_POR_CATEGORIA, llamar_siguiente, resumen_cola
from turnos.tests.helpers import LlamadoTests, crear_usuario, rut_valido


class ResumenColaTests(LlamadoTests):
    def test_sin_nadie_en_espera(self):
        resumen = resumen_cola()
        self.assertEqual(resumen["total"], 0)
        self.assertIsNone(resumen["siguiente"])
        self.assertEqual([g["total"] for g in resumen["grupos"]], [0, 0, 0])

    def test_agrupa_por_categoria_en_orden_de_atencion(self):
        self.turno(Categoria.GENERAL, 1)
        self.turno(Categoria.PREFERENCIAL, 1)
        self.turno(Categoria.URGENCIA, 1)
        resumen = resumen_cola()
        self.assertEqual([g["nombre"] for g in resumen["grupos"]], ["Urgencia", "Preferencial", "General"])
        self.assertEqual([g["total"] for g in resumen["grupos"]], [1, 1, 1])
        self.assertEqual(resumen["total"], 3)

    def test_el_siguiente_es_el_que_elige_el_motor(self):
        self.turno(Categoria.GENERAL, 1)
        urgencia = self.turno(Categoria.URGENCIA, 1)
        self.assertEqual(resumen_cola()["siguiente"].pk, urgencia.pk)

    def test_solo_cuenta_los_turnos_en_espera_de_hoy(self):
        self.turno(Categoria.GENERAL, 1)
        self.turno(Categoria.GENERAL, 2, estado=EstadoTurno.LLAMADO)
        self.turno(Categoria.GENERAL, 3, estado=EstadoTurno.ATENDIDO)
        self.turno(Categoria.GENERAL, 4, estado=EstadoTurno.AUSENTE)
        self.turno(Categoria.GENERAL, 5, estado=EstadoTurno.ANULADO)
        self.turno(Categoria.GENERAL, 6, fecha=timezone.localdate() - timedelta(days=1))
        resumen = resumen_cola()
        self.assertEqual(resumen["total"], 1)
        self.assertEqual(resumen["grupos"][2]["turnos"][0].numero, "G-001")

    def test_muestra_los_primeros_y_cuenta_el_resto(self):
        for n in range(1, 13):
            self.turno(Categoria.GENERAL, n)
        general = resumen_cola()["grupos"][2]
        self.assertEqual(general["total"], 12)
        self.assertEqual(len(general["turnos"]), TURNOS_VISIBLES_POR_CATEGORIA)
        self.assertEqual(general["restantes"], 2)
        self.assertEqual(general["turnos"][0].numero, "G-001")


class ColaVistaTests(LlamadoTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.ana)
        self.url = reverse("turnos:cola")

    def test_devuelve_un_fragmento_con_los_turnos_en_espera(self):
        self.turno(Categoria.PREFERENCIAL, 7)
        self.turno(Categoria.GENERAL, 3)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "<html")
        self.assertContains(respuesta, "2 pacientes en espera")
        self.assertContains(respuesta, "P-007")
        self.assertContains(respuesta, "G-003")
        self.assertContains(respuesta, "Siguiente en llamarse")

    def test_singular_con_un_solo_paciente(self):
        self.turno()
        self.assertContains(self.client.get(self.url), "1 paciente en espera")

    def test_un_turno_emitido_en_el_totem_aparece_en_la_cola(self):
        self.assertNotContains(self.client.get(self.url), "G-001")
        cliente_totem = self.client_class()
        cliente_totem.post(reverse("turnos:totem_turno"), {"rut": rut_valido("10000001")})
        self.assertContains(self.client.get(self.url), "G-001")

    def test_un_turno_llamado_sale_de_la_cola(self):
        self.turno()
        llamar_siguiente(self.ana)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "0 pacientes en espera")
        self.assertNotContains(respuesta, "G-001")

    def test_avisa_cuantos_mas_hay_sin_listarlos(self):
        for n in range(1, 13):
            self.turno(Categoria.GENERAL, n)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "y 2 más")
        self.assertNotContains(respuesta, "G-012")

    def test_no_se_guarda_en_cache(self):
        self.assertIn("no-cache", self.client.get(self.url)["Cache-Control"])

    def test_encargado_de_terreno_recibe_403_y_sin_sesion_va_al_login(self):
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_el_panel_trae_la_cola_y_el_intervalo_de_refresco(self):
        self.turno(Categoria.URGENCIA, 2)
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertContains(respuesta, "Fila de espera")
        self.assertContains(respuesta, "U-002")
        segundos = settings.TURNOS_SEGUNDOS_REFRESCO_PANEL
        ventana = settings.TURNOS_SEGUNDOS_ACTIVIDAD_RECIENTE
        self.assertContains(
            respuesta,
            f"filaEnVivo({{ url: '{reverse('turnos:cola')}', segundos: {segundos}, ventanaActividad: {ventana} }})",
        )

    def test_el_panel_sin_ventanilla_no_muestra_la_cola(self):
        Ventanilla.objects.filter(pk=self.v1.pk).update(funcionario=None)
        respuesta = self.client.get(reverse("turnos:atencion"))
        self.assertNotContains(respuesta, "Fila de espera")
