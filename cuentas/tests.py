from django.test import TestCase
from django.urls import reverse

from cuentas.models import Rol, Usuario


def crear_usuario(rut, rol):
    return Usuario.objects.create_user(
        rut=rut,
        nombres="Prueba",
        apellidos=rol.label,
        password="clave-de-prueba-2026",
        rol=rol,
        debe_cambiar_password=False,
    )


class RolesTests(TestCase):
    def test_encargado_de_terreno_aterriza_en_domicilios_y_no_administra_cuentas(self):
        usuario = crear_usuario("12345678-5", Rol.ENCARGADO_TERRENO)
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("cuentas:inicio"))
        self.assertRedirects(respuesta, reverse("reparto:domicilios"))

        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)

    def test_qf_sigue_aterrizando_en_la_gestion_de_usuarios(self):
        self.client.force_login(crear_usuario("11111111-1", Rol.QF))
        respuesta = self.client.get(reverse("cuentas:inicio"))
        self.assertRedirects(respuesta, reverse("cuentas:usuarios"))

    def test_qf_crea_un_encargado_de_terreno(self):
        self.client.force_login(crear_usuario("11111111-1", Rol.QF))
        respuesta = self.client.post(
            reverse("cuentas:usuario_crear"),
            {
                "rut": "12.345.678-5",
                "nombres": "Luis",
                "apellidos": "Soto Mena",
                "rol": Rol.ENCARGADO_TERRENO,
                "password": "Clave-inicial-2026",
            },
        )
        self.assertRedirects(respuesta, reverse("cuentas:usuarios"))
        nuevo = Usuario.objects.get(rut="12345678-5")
        self.assertEqual(nuevo.rol, Rol.ENCARGADO_TERRENO)
        self.assertTrue(nuevo.debe_cambiar_password)


class AterrizajeYNavegacionTests(TestCase):
    def enlaces(self, usuario):
        self.client.force_login(usuario)
        pagina = self.client.get(reverse("cuentas:panel_funcionario"))
        contenido = pagina.content.decode()
        return {
            nombre: reverse(url) in contenido
            for nombre, url in (
                ("usuarios", "cuentas:usuarios"),
                ("ventanillas", "turnos:ventanillas"),
                ("atencion", "turnos:atencion"),
                ("domicilios", "reparto:domicilios"),
            )
        }

    def test_funcionario_aterriza_en_el_panel_de_atencion(self):
        self.client.force_login(crear_usuario("12345678-5", Rol.FUNCIONARIO))
        respuesta = self.client.get(reverse("cuentas:inicio"))
        self.assertRedirects(respuesta, reverse("turnos:atencion"))

    def test_la_qf_ve_sus_cuatro_enlaces(self):
        enlaces = self.enlaces(crear_usuario("11111111-1", Rol.QF))
        self.assertEqual(enlaces, {"usuarios": True, "ventanillas": True, "atencion": True, "domicilios": True})

    def test_el_funcionario_solo_ve_atencion(self):
        enlaces = self.enlaces(crear_usuario("12345678-5", Rol.FUNCIONARIO))
        self.assertEqual(enlaces, {"usuarios": False, "ventanillas": False, "atencion": True, "domicilios": False})

    def test_el_encargado_de_terreno_solo_ve_domicilios(self):
        enlaces = self.enlaces(crear_usuario("12345678-5", Rol.ENCARGADO_TERRENO))
        self.assertEqual(enlaces, {"usuarios": False, "ventanillas": False, "atencion": False, "domicilios": True})

    def test_sin_sesion_no_hay_enlaces(self):
        contenido = self.client.get(reverse("cuentas:entrar")).content.decode()
        self.assertNotIn(reverse("turnos:atencion"), contenido)

    def test_con_cambio_de_clave_pendiente_no_hay_enlaces(self):
        usuario = crear_usuario("12345678-5", Rol.FUNCIONARIO)
        usuario.debe_cambiar_password = True
        usuario.save()
        self.client.force_login(usuario)
        contenido = self.client.get(reverse("cuentas:cambiar_password")).content.decode()
        self.assertNotIn(reverse("turnos:atencion"), contenido)

    def test_la_pagina_actual_queda_marcada(self):
        self.client.force_login(crear_usuario("11111111-1", Rol.QF))
        contenido = self.client.get(reverse("turnos:ventanillas")).content.decode()
        self.assertIn(f'href="{reverse("turnos:ventanillas")}" aria-current="page"', contenido)

    def test_el_totem_no_muestra_navegacion_ni_con_sesion(self):
        self.client.force_login(crear_usuario("11111111-1", Rol.QF))
        contenido = self.client.get(reverse("turnos:totem")).content.decode()
        self.assertNotIn("barra__nav", contenido)


class RutLegibleTests(TestCase):
    def test_agrega_los_puntos_de_miles(self):
        from cuentas.templatetags.rut import rut_legible

        self.assertEqual(rut_legible("12345678-5"), "12.345.678-5")
        self.assertEqual(rut_legible("9602278-6"), "9.602.278-6")
        self.assertEqual(rut_legible("10000001-K"), "10.000.001-K")

    def test_deja_igual_lo_que_no_es_un_rut_guardado(self):
        from cuentas.templatetags.rut import rut_legible

        self.assertEqual(rut_legible(""), "")
        self.assertIsNone(rut_legible(None))
        self.assertEqual(rut_legible("123456785"), "123456785")


class UsuariosListaTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("11111111-1", Rol.QF)
        self.funcionario = crear_usuario("12345678-5", Rol.FUNCIONARIO)
        self.encargado = crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO)
        self.client.force_login(self.qf)

    def pagina(self):
        return self.client.get(reverse("cuentas:usuarios"))

    def test_agrupa_las_cuentas_activas_por_rol(self):
        grupos = self.pagina().context["grupos"]
        self.assertEqual(
            [(g["nombre"], [u.pk for u in g["usuarios"]]) for g in grupos],
            [
                ("Química Farmacéutica", [self.qf.pk]),
                ("Funcionarios de farmacia", [self.funcionario.pk]),
                ("Encargados de terreno", [self.encargado.pk]),
            ],
        )

    def test_las_desactivadas_siguen_en_el_listado_en_su_propia_seccion(self):
        self.funcionario.is_active = False
        self.funcionario.save()
        respuesta = self.pagina()
        self.assertEqual([u.pk for u in respuesta.context["desactivadas"]], [self.funcionario.pk])
        self.assertNotIn(self.funcionario, respuesta.context["grupos"][1]["usuarios"])
        self.assertContains(respuesta, "Cuentas desactivadas")
        self.assertContains(respuesta, "Activar")

    def test_muestra_el_rut_con_puntos(self):
        self.assertContains(self.pagina(), "12.345.678-5")

    def test_la_propia_cuenta_se_marca_y_no_ofrece_desactivarse(self):
        respuesta = self.pagina()
        self.assertContains(respuesta, "Tu cuenta", count=1)
        propia = reverse("cuentas:usuario_cambiar_estado", args=[self.qf.pk])
        ajena = reverse("cuentas:usuario_cambiar_estado", args=[self.funcionario.pk])
        self.assertNotContains(respuesta, f'action="{propia}"')
        self.assertContains(respuesta, f'action="{ajena}"')

    def test_desactivar_pide_confirmacion_en_el_modal(self):
        respuesta = self.pagina()
        self.assertContains(respuesta, 'data-confirmar-titulo="¿Desactivar esta cuenta?"', count=2)
        self.assertNotContains(respuesta, "confirm(")
