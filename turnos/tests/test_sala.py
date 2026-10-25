"""Pantalla de sala de espera: la consulta de los llamados del día, su ruta JSON y la página pública."""
from datetime import date, datetime, timedelta, timezone as tz
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from turnos.models import Categoria, EstadoTurno, Paciente, Turno, Ventanilla
from turnos.servicios import emitir_turno, llamar_siguiente, obtener_estado_sala, re_llamar
from turnos.tests.helpers import LlamadoTests, nacido_hace, rut_valido

CLAVES_DEL_ESTADO = {"fecha", "servidor_en", "actual", "recientes"}
CLAVES_DEL_LLAMADO = {"turno_id", "numero", "ventanilla", "veces_llamado", "ultimo_llamado_en"}


class EstadoSalaTests(LlamadoTests):
    def llamado(self, correlativo, hace=0, estado=EstadoTurno.LLAMADO, **extra):
        """Un turno general ya llamado a la ventanilla 1, cuyo último llamado fue hace `hace` segundos."""
        datos = {
            "estado": estado,
            "ventanilla": self.v1,
            "ultimo_llamado_en": timezone.now() - timedelta(seconds=hace),
            "veces_llamado": 1,
        }
        datos.update(extra)
        return self.turno(Categoria.GENERAL, correlativo, **datos)

    def numeros(self, fecha=None):
        return [llamado["numero"] for llamado in obtener_estado_sala(fecha)["recientes"]]

    def test_sin_llamados_actual_es_nulo_y_recientes_vacio(self):
        self.turno()  # en espera: todavía no lo llaman
        estado = obtener_estado_sala()
        self.assertEqual(estado["fecha"], timezone.localdate().isoformat())
        self.assertIsNone(estado["actual"])
        self.assertEqual(estado["recientes"], [])

    def test_entrega_numero_de_turno_numero_de_ventanilla_y_horas_locales(self):
        ventanilla = Ventanilla.objects.create(numero=7)
        self.assertNotEqual(ventanilla.pk, 7)  # la sala muestra el número, no la clave
        dia = date(2026, 10, 24)
        turno = self.turno(
            Categoria.PREFERENCIAL,
            12,
            fecha=dia,
            estado=EstadoTurno.LLAMADO,
            ventanilla=ventanilla,
            ultimo_llamado_en=datetime(2026, 10, 24, 20, 9, 58, 412000, tzinfo=tz.utc),
            veces_llamado=1,
        )
        with mock.patch("django.utils.timezone.now", return_value=datetime(2026, 10, 24, 20, 10, tzinfo=tz.utc)):
            estado = obtener_estado_sala(dia)
        llamado = {
            "turno_id": turno.pk,
            "numero": "P-012",
            "ventanilla": 7,
            "veces_llamado": 1,
            "ultimo_llamado_en": "2026-10-24T17:09:58.412-03:00",
        }
        self.assertEqual(
            estado,
            {
                "fecha": "2026-10-24",
                "servidor_en": "2026-10-24T17:10:00.000-03:00",
                "actual": llamado,
                "recientes": [llamado],
            },
        )

    def test_muestra_los_ya_llamados_aunque_esten_atendidos_o_ausentes(self):
        estados = [
            EstadoTurno.LLAMADO,
            EstadoTurno.EN_ATENCION,
            EstadoTurno.ATENDIDO,
            EstadoTurno.AUSENTE,
            EstadoTurno.EN_ESPERA,
            EstadoTurno.ANULADO,
        ]
        for n, estado in enumerate(estados, start=1):
            self.llamado(n, hace=n, estado=estado)
        self.assertEqual(self.numeros(), ["G-001", "G-002", "G-003", "G-004"])

    def test_ignora_los_llamados_de_otros_dias(self):
        ayer = timezone.localdate() - timedelta(days=1)
        self.llamado(1, fecha=ayer)
        self.assertEqual(self.numeros(), [])
        self.assertEqual(self.numeros(ayer), ["G-001"])

    def test_un_turno_sin_ventanilla_o_sin_llamado_registrado_no_aparece(self):
        self.llamado(1, ventanilla=None)
        self.llamado(2, ultimo_llamado_en=None)
        self.llamado(3, veces_llamado=0)
        self.assertEqual(self.numeros(), [])

    def test_un_re_llamado_sube_al_turno_al_primer_lugar_sin_duplicarlo(self):
        self.turno(Categoria.GENERAL, 1)
        self.turno(Categoria.GENERAL, 2)
        primero = llamar_siguiente(self.ana)  # G-001 a la ventanilla 1
        segundo = llamar_siguiente(self.beto)  # G-002 a la ventanilla 2
        Turno.objects.filter(pk=primero.pk).update(ultimo_llamado_en=timezone.now() - timedelta(seconds=20))
        Turno.objects.filter(pk=segundo.pk).update(ultimo_llamado_en=timezone.now() - timedelta(seconds=10))
        antes = obtener_estado_sala()["recientes"]
        self.assertEqual([llamado["numero"] for llamado in antes], ["G-002", "G-001"])

        re_llamar(self.ana)
        estado = obtener_estado_sala()
        self.assertEqual(self.numeros(), ["G-001", "G-002"])
        actual = estado["actual"]
        self.assertEqual(actual, estado["recientes"][0])
        self.assertEqual(
            (actual["turno_id"], actual["numero"], actual["ventanilla"]),
            (antes[1]["turno_id"], "G-001", 1),
        )
        self.assertEqual(actual["veces_llamado"], 2)
        self.assertNotEqual(actual["ultimo_llamado_en"], antes[1]["ultimo_llamado_en"])

    def test_muestra_como_maximo_los_cinco_mas_recientes(self):
        for n in range(1, 8):
            self.llamado(n, hace=n)
        self.assertEqual(self.numeros(), ["G-001", "G-002", "G-003", "G-004", "G-005"])
        with override_settings(TURNOS_CANTIDAD_LLAMADOS_SALA=3):
            self.assertEqual(self.numeros(), ["G-001", "G-002", "G-003"])

    def test_con_la_misma_hora_de_llamado_va_primero_el_de_id_mayor(self):
        momento = timezone.now()
        self.llamado(1, ultimo_llamado_en=momento)
        self.llamado(2, ultimo_llamado_en=momento)
        self.assertEqual(self.numeros(), ["G-002", "G-001"])


class VistaSalaTests(LlamadoTests):
    """Base de las pruebas de la página y de la ruta JSON, que son públicas."""

    def paciente_llamado(self):
        """Un paciente con nombre y RUT reconocibles, que sacó turno en el tótem y ya fue llamado."""
        # Solo ASCII: JsonResponse escapa los acentos, y un nombre con tildes no se encontraría aunque se filtrara.
        paciente = Paciente.objects.create(
            rut=rut_valido("15975346"),
            nombres="Herminia",
            apellidos="Valenzuela Soto",
            fecha_nacimiento=nacido_hace(40),
        )
        emitir_turno(paciente.rut)
        return paciente, llamar_siguiente(self.ana)

    def assertSinDatosDelPaciente(self, respuesta, paciente):
        for dato in ["15975346", "15.975.346", paciente.nombres, "Valenzuela", "Soto"]:
            self.assertNotContains(respuesta, dato)


class SalaEstadoVistaTests(VistaSalaTests):
    def setUp(self):
        super().setUp()
        self.url = reverse("turnos:sala_estado")

    def test_responde_json_sin_sesion(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/json")
        self.assertEqual(respuesta.json()["recientes"], [])

    def test_solo_acepta_get(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_no_se_guarda_en_cache(self):
        cache_control = self.client.get(self.url)["Cache-Control"]
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)

    def test_trae_exactamente_las_claves_del_contrato(self):
        self.paciente_llamado()
        estado = self.client.get(self.url).json()
        self.assertEqual(set(estado), CLAVES_DEL_ESTADO)
        self.assertEqual(set(estado["actual"]), CLAVES_DEL_LLAMADO)
        for llamado in estado["recientes"]:
            self.assertEqual(set(llamado), CLAVES_DEL_LLAMADO)

    def test_no_entrega_el_rut_ni_el_nombre_del_paciente(self):
        paciente, turno = self.paciente_llamado()
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, turno.numero)
        self.assertSinDatosDelPaciente(respuesta, paciente)

    def test_un_llamado_desde_el_panel_aparece_en_la_siguiente_respuesta(self):
        self.turno(Categoria.PREFERENCIAL, 12)
        self.assertIsNone(self.client.get(self.url).json()["actual"])

        panel = self.client_class()
        panel.force_login(self.beto)
        panel.post(reverse("turnos:llamar_siguiente"))

        actual = self.client.get(self.url).json()["actual"]
        self.assertEqual((actual["numero"], actual["ventanilla"]), ("P-012", self.v2.numero))


class SalaPaginaTests(VistaSalaTests):
    def setUp(self):
        super().setUp()
        self.url = reverse("turnos:sala")

    def test_carga_sin_sesion(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Último llamado")
        self.assertContains(respuesta, "Llamados anteriores")

    def test_solo_acepta_get(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_no_se_guarda_en_cache(self):
        cache_control = self.client.get(self.url)["Cache-Control"]
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)

    def test_no_muestra_la_barra_ni_el_pie_aunque_haya_una_sesion_abierta(self):
        self.client.force_login(self.ana)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'class="barra"')
        self.assertNotContains(respuesta, "Cerrar sesión")
        self.assertNotContains(respuesta, 'class="pie"')

    def test_no_muestra_el_rut_ni_el_nombre_del_paciente(self):
        paciente, turno = self.paciente_llamado()
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, turno.numero)
        self.assertSinDatosDelPaciente(respuesta, paciente)

    def test_incrusta_los_llamados_de_hoy_con_json_script(self):
        _, turno = self.paciente_llamado()
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, '<script id="estado-sala" type="application/json">')
        self.assertContains(respuesta, f'"numero": "{turno.numero}"')
        self.assertEqual(respuesta.context["estado"]["actual"]["turno_id"], turno.pk)

    def test_sin_llamados_muestra_esperando_llamados(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, '"actual": null')
        self.assertContains(respuesta, "Esperando llamados")

    def test_sin_javascript_avisa_que_lo_necesita(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "<noscript>")
        self.assertContains(respuesta, "Esta pantalla necesita JavaScript para mostrar los llamados.")

    def test_le_pasa_al_componente_la_ruta_y_las_constantes(self):
        respuesta = self.client.get(self.url)
        self.assertContains(
            respuesta,
            f"salaEnVivo({{ url: '{reverse('turnos:sala_estado')}', "
            f"segundos: {settings.TURNOS_SEGUNDOS_REFRESCO_SALA}, "
            f"vigencia: {settings.TURNOS_SEGUNDOS_VIGENCIA_ANUNCIO}, "
            f"reintentoMaximo: {settings.TURNOS_SEGUNDOS_REINTENTO_MAXIMO_SALA}, "
            f"resalte: {settings.TURNOS_SEGUNDOS_RESALTE_SALA} }})",
        )

    def test_trae_la_hora_de_actualizacion_y_el_aviso_sin_conexion(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Actualizado a las")
        self.assertContains(respuesta, "Sin conexión. Información pendiente de actualización.")

    def test_trae_el_control_de_voz_y_sus_avisos(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Activar voz")
        self.assertContains(respuesta, "Toque la pantalla para reactivar la voz")
        self.assertContains(respuesta, "Sin voz en español: suena la campanilla")
        self.assertContains(respuesta, "Este navegador no puede reproducir sonido")
