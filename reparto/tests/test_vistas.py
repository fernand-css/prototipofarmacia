"""Pantallas de domicilios: acceso por rol, lista, filtros, búsqueda por POST y resumen."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from cuentas.models import Rol
from reparto.models import Sector
from reparto.servicios import guardar_domicilio, verificar
from turnos.tests.helpers import crear_paciente, crear_usuario, rut_valido


class DomiciliosVistasTests(TestCase):
    def setUp(self):
        self.encargado = crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)
        self.qf = crear_usuario("22222222-2", Rol.QF)
        self.funcionario = crear_usuario("33333333-3", Rol.FUNCIONARIO)
        self.url = reverse("reparto:domicilios")

        self.nunez = crear_paciente(rut_valido("10000001"), edad=85, nombres="Rosa", apellidos="Núñez")
        self.perez = crear_paciente(rut_valido("10000002"), edad=40, es_postrado=True, nombres="Luis", apellidos="Pérez")
        self.rojas = crear_paciente(rut_valido("10000003"), edad=90, nombres="Elsa", apellidos="Rojas")
        self.joven = crear_paciente(rut_valido("10000004"), edad=30, nombres="Iván", apellidos="Joven")
        guardar_domicilio(
            self.nunez,
            {"sector": Sector.VERDE, "direccion": "Camino a Dadinco km 4",
             "latitud": Decimal("-36.5"), "longitud": Decimal("-72.2")},
            self.encargado,
        )
        verificar(self.nunez, self.encargado)
        guardar_domicilio(self.perez, {"sector": Sector.AZUL, "direccion": "Puente Ñuble, parcela 12"}, self.encargado)

    def ver(self, usuario=None, **parametros):
        self.client.force_login(usuario or self.encargado)
        return self.client.get(self.url, parametros)

    def buscar(self, busqueda, url=None):
        self.client.force_login(self.encargado)
        return self.client.post(url or self.url, {"busqueda": busqueda})


class AccesoTests(DomiciliosVistasTests):
    def test_sin_sesion_redirige_al_login(self):
        for respuesta in (self.client.get(self.url), self.client.post(self.url, {"busqueda": "x"})):
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn(reverse("cuentas:entrar"), respuesta.url)

    def test_el_funcionario_recibe_403(self):
        self.client.force_login(self.funcionario)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"busqueda": "x"}).status_code, 403)

    def test_el_encargado_y_la_qf_la_ven_y_esta_en_su_barra(self):
        for usuario in (self.encargado, self.qf):
            respuesta = self.ver(usuario)
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, f'href="{self.url}" aria-current="page">Domicilios</a>', html=False)

    def test_el_funcionario_no_ve_domicilios_en_la_barra(self):
        self.client.force_login(self.funcionario)
        self.assertNotContains(self.client.get(reverse("turnos:atencion")), self.url)

    def test_el_encargado_entra_directo_a_domicilios(self):
        self.client.force_login(self.encargado)
        self.assertRedirects(self.client.get(reverse("cuentas:inicio")), self.url)


class ListaTests(DomiciliosVistasTests):
    def test_lista_solo_pacientes_con_despacho_con_su_estado(self):
        respuesta = self.ver()
        contenido = respuesta.content.decode()
        self.assertNotIn("Iván Joven", contenido)
        self.assertLess(contenido.index("Rosa Núñez"), contenido.index("Luis Pérez"))
        self.assertLess(contenido.index("Luis Pérez"), contenido.index("Elsa Rojas"))
        self.assertContains(respuesta, '<span class="insignia insignia--verificado">Verificado</span>', html=True)
        self.assertContains(respuesta, '<span class="insignia insignia--pendiente">Pendiente de verificar</span>', html=True)
        self.assertContains(respuesta, '<span class="insignia insignia--sin_direccion">Sin dirección</span>', html=True)
        self.assertContains(respuesta, "Camino a Dadinco km 4")
        self.assertContains(respuesta, "Sin dirección registrada")
        self.assertContains(respuesta, "Postrado.")
        self.assertContains(respuesta, f"10.000.001-{rut_valido('10000001')[-1]}")

    def test_el_resumen_muestra_ig04_y_los_sin_direccion(self):
        respuesta = self.ver()
        self.assertContains(respuesta, "<strong>1</strong> de 2 domicilios verificados en terreno (50 %)", html=False)
        self.assertContains(respuesta, 'style="width: 50%"')
        self.assertContains(respuesta, "<strong>1</strong> paciente todavía sin dirección.", html=False)

    def test_agrupa_por_sector_con_sus_verificados(self):
        contenido = self.ver().content.decode()
        verde, azul, sin_sector = (contenido.index(t) for t in ("Sector Verde", "Sector Azul", "Sin sector"))
        self.assertLess(verde, contenido.index("Rosa Núñez"))
        self.assertLess(contenido.index("Rosa Núñez"), azul)
        self.assertLess(azul, contenido.index("Luis Pérez"))
        self.assertLess(contenido.index("Luis Pérez"), sin_sector)
        self.assertLess(sin_sector, contenido.index("Elsa Rojas"))
        self.assertIn("1 de 1 verificado", contenido)
        self.assertIn("0 de 1 verificados", contenido)
        self.assertIn("1 sin dirección", contenido)
        self.assertNotIn("Sector Rojo", contenido)  # sin pacientes, el grupo no aparece

    def test_filtra_por_sector_y_por_estado(self):
        contenido = self.ver(sector="azul").content.decode()
        self.assertIn("Luis Pérez", contenido)
        self.assertNotIn("Rosa Núñez", contenido)
        contenido = self.ver(estado="sin_direccion").content.decode()
        self.assertIn("Elsa Rojas", contenido)
        self.assertNotIn("Luis Pérez", contenido)
        contenido = self.ver(estado="verificado", sector="verde").content.decode()
        self.assertIn("Rosa Núñez", contenido)
        self.assertNotIn("Luis Pérez", contenido)

    def test_los_enlaces_de_filtro_conservan_el_otro_y_marcan_el_activo(self):
        respuesta = self.ver(sector="azul")
        self.assertContains(respuesta, f'href="{self.url}?sector=azul&amp;estado=pendiente"')
        self.assertContains(respuesta, f'href="{self.url}?sector=azul" class="filtros__opcion" aria-current="true"')

    def test_un_filtro_desconocido_se_ignora(self):
        contenido = self.ver(sector="morado", estado="perdido").content.decode()
        for nombre in ("Rosa Núñez", "Luis Pérez", "Elsa Rojas"):
            self.assertIn(nombre, contenido)

    def test_sin_resultados_lo_dice(self):
        self.assertContains(self.ver(sector="rojo"), "Ningún paciente coincide con esos filtros.")


class BusquedaTests(DomiciliosVistasTests):
    def test_busca_por_rut_por_post_sin_dejarlo_en_la_url(self):
        rut = rut_valido("10000002")
        respuesta = self.buscar(f"10.000.002-{rut[-1]}")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.request["QUERY_STRING"], "")
        self.assertContains(respuesta, "Luis Pérez")
        self.assertNotContains(respuesta, "Rosa Núñez")
        self.assertContains(respuesta, "Resultado de la búsqueda")

    def test_busca_por_apellido_sin_tilde(self):
        respuesta = self.buscar("nunez")
        self.assertContains(respuesta, "Rosa Núñez")
        self.assertNotContains(respuesta, "Elsa Rojas")

    def test_la_busqueda_respeta_los_filtros(self):
        respuesta = self.buscar("rojas", url=f"{self.url}?estado=verificado")
        self.assertContains(respuesta, "Ningún paciente coincide con esa búsqueda.")

    def test_una_busqueda_vacia_avisa_y_muestra_todos(self):
        respuesta = self.buscar("")
        self.assertContains(respuesta, "Escriba un RUT o un apellido.")
        self.assertContains(respuesta, "Elsa Rojas")
