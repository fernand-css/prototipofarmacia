"""Mapa del domicilio y HTTPS de desarrollo: Leaflet local, sin claves ni CDN, y hosts de la red local."""
import os
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Rol
from farmacia_turnos import settings as modulo_de_ajustes
from farmacia_turnos.settings import hosts_locales
from reparto.servicios import guardar_domicilio
from turnos.tests.helpers import crear_paciente, crear_usuario, rut_valido

LEAFLET = Path(settings.BASE_DIR) / "static" / "vendor" / "leaflet"


class MapaTests(TestCase):
    def setUp(self):
        self.encargado = crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)
        self.paciente = crear_paciente(rut_valido("10000001"), edad=85)
        self.client.force_login(self.encargado)

    def ficha(self):
        return self.client.get(reverse("reparto:ficha", args=[self.paciente.pk]))

    def test_la_ficha_muestra_el_marcador_en_las_coordenadas(self):
        guardar_domicilio(
            self.paciente,
            {"direccion": "Camino a Dadinco km 4", "latitud": Decimal("-36.481234"), "longitud": Decimal("-72.198765")},
            self.encargado,
        )
        respuesta = self.ficha()
        self.assertContains(respuesta, "mapaDomicilio({ punto: [-36.481234, -72.198765]")
        self.assertContains(respuesta, "centro: [-36.4999, -72.2128], zoom: 17")
        self.assertContains(respuesta, "No se pudo cargar el mapa. Puede escribir las coordenadas.")

    def test_sin_coordenadas_el_mapa_se_centra_en_la_comuna(self):
        guardar_domicilio(self.paciente, {"direccion": "Camino a Dadinco km 4"}, self.encargado)
        respuesta = self.ficha()
        self.assertContains(respuesta, "mapaDomicilio({ punto: null")
        self.assertContains(respuesta, "el mapa muestra la comuna de San Nicolás")

    def test_el_formulario_tiene_mapa_editable_y_gps(self):
        respuesta = self.client.get(reverse("reparto:editar", args=[self.paciente.pk]))
        self.assertContains(respuesta, "mapaDomicilio({ editable: true, campoLatitud: 'id_latitud', campoLongitud: 'id_longitud'")
        self.assertContains(respuesta, "ubicacionActual({ campoLatitud: 'id_latitud'")
        self.assertContains(respuesta, "Usar mi ubicación actual")

    def test_leaflet_se_sirve_desde_static_sin_cdn_ni_claves(self):
        guardar_domicilio(self.paciente, {"direccion": "x"}, self.encargado)
        for respuesta in (self.ficha(), self.client.get(reverse("reparto:editar", args=[self.paciente.pk]))):
            contenido = respuesta.content.decode()
            self.assertIn("/static/vendor/leaflet/leaflet.js", contenido)
            self.assertIn("/static/vendor/leaflet/leaflet.css", contenido)
            for externo in ("unpkg", "jsdelivr", "cdnjs", "googleapis", "mapbox", "api_key", "apikey"):
                self.assertNotIn(externo, contenido.lower())

    def test_los_archivos_de_leaflet_y_su_licencia_estan_en_el_repositorio(self):
        for nombre in ("leaflet.js", "leaflet.css", "LICENSE", "images/marker-icon.png", "images/marker-shadow.png"):
            self.assertTrue((LEAFLET / nombre).exists(), nombre)
        self.assertIn("Leaflet 1.9.4", (LEAFLET / "leaflet.js").read_text(encoding="utf-8")[:200])

    def test_las_teselas_son_de_openstreetmap_con_atribucion_y_sin_clave(self):
        reparto_js = (Path(settings.BASE_DIR) / "static" / "js" / "reparto.js").read_text(encoding="utf-8")
        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", reparto_js)
        self.assertIn("© colaboradores de", reparto_js)
        # OpenStreetMap bloquea las teselas sin Referer; Django lo quita con «same-origin».
        self.assertIn("referrerPolicy: 'strict-origin-when-cross-origin'", reparto_js)
        self.assertNotIn("key", reparto_js.lower().replace("keyboard", ""))


class HostsLocalesTests(TestCase):
    def test_sin_la_variable_no_cambia_nada(self):
        self.assertEqual(hosts_locales(None), ([], []))
        self.assertEqual(hosts_locales("  "), ([], []))
        if not os.environ.get("TURNOS_HOSTS_LOCALES"):
            # El valor del módulo: al probar, Django agrega «testserver» al de django.conf.
            self.assertEqual(modulo_de_ajustes.ALLOWED_HOSTS, [])
            self.assertEqual(modulo_de_ajustes.CSRF_TRUSTED_ORIGINS, [])

    def test_con_ips_agrega_hosts_y_origenes_https(self):
        hosts, origenes = hosts_locales("192.168.1.20, 192.168.1.21")
        self.assertEqual(hosts, ["localhost", "127.0.0.1", "[::1]", "192.168.1.20", "192.168.1.21"])
        self.assertEqual(origenes, ["https://192.168.1.20:8443", "https://192.168.1.21:8443"])
