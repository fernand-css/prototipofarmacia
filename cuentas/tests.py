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
    def test_encargado_de_terreno_aterriza_en_panel_y_no_administra_cuentas(self):
        usuario = crear_usuario("12345678-5", Rol.ENCARGADO_TERRENO)
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("cuentas:inicio"))
        self.assertRedirects(respuesta, reverse("cuentas:panel_funcionario"))

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
