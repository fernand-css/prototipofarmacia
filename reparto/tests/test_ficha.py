"""Ficha y edición del domicilio: flujo completo, historial, permisos y confirmaciones."""
import shutil
import tempfile
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from cuentas.models import Rol
from reparto.models import AccionDomicilio, Domicilio, EstadoDomicilio, FotoDomicilio
from reparto.servicios import guardar_domicilio
from reparto.tests.test_fotos import imagen
from turnos.tests.helpers import crear_paciente, crear_usuario, rut_valido


class FichaTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=self.media)
        ajuste.enable()
        self.addCleanup(ajuste.disable)

        self.encargado = crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)
        self.qf = crear_usuario("22222222-2", Rol.QF)
        self.paciente = crear_paciente(rut_valido("10000001"), edad=85, nombres="Rosa", apellidos="Núñez")
        self.client.force_login(self.encargado)

    def url(self, nombre, *args):
        return reverse(f"reparto:{nombre}", args=args or [self.paciente.pk])

    def guardar(self, **datos):
        base = {"sector": "verde", "direccion": "Camino a Dadinco km 4", "referencias": "Casa roja", "latitud": "", "longitud": ""}
        base.update(datos)
        return self.client.post(self.url("editar"), base, follow=True)


class FlujoTests(FichaTests):
    def test_registrar_foto_verificar_editar_y_marcar_pendiente(self):
        respuesta = self.guardar()
        self.assertContains(respuesta, "Se guardó el domicilio.")
        self.assertContains(respuesta, "Pendiente de verificar")
        self.assertContains(respuesta, "Para verificar, registre primero las coordenadas")

        respuesta = self.client.post(self.url("subir_foto"), {"foto": imagen()}, follow=True)
        self.assertContains(respuesta, "Se agregó la foto.")
        foto = FotoDomicilio.objects.get()
        self.assertContains(respuesta, reverse("reparto:foto", args=[foto.pk]))

        self.guardar(latitud="-36.499912, -72.212834")  # pegadas las dos en la latitud
        respuesta = self.client.post(self.url("verificar"), follow=True)
        self.assertContains(respuesta, "El domicilio quedó verificado.")
        self.assertContains(respuesta, "Verificado en terreno por Prueba Encargado de Terreno")
        self.assertContains(respuesta, "-36.499912, -72.212834")  # con punto: la coma separa las dos

        respuesta = self.guardar(direccion="Camino a Dadinco km 5", latitud="-36.499912", longitud="-72.212834")
        self.assertEqual(Domicilio.objects.get().estado, EstadoDomicilio.VERIFICADO)

        respuesta = self.client.post(self.url("marcar_pendiente"), {"motivo": "Se cambió de casa"}, follow=True)
        self.assertContains(respuesta, "El domicilio quedó pendiente de verificar.")
        self.assertContains(respuesta, "Motivo: Se cambió de casa")

        acciones = [c.accion for c in Domicilio.objects.get().cambios.all()]
        self.assertEqual(acciones, [
            AccionDomicilio.MARCADO_PENDIENTE,
            AccionDomicilio.EDITADO,
            AccionDomicilio.VERIFICADO,
            AccionDomicilio.EDITADO,
            AccionDomicilio.FOTO_AGREGADA,
            AccionDomicilio.CREADO,
        ])
        contenido = respuesta.content.decode()
        for etiqueta in ("Lo marcó pendiente de verificar", "Verificó el domicilio", "Agregó una foto", "Registró el domicilio"):
            self.assertIn(etiqueta, contenido)
        self.assertLess(contenido.index("Lo marcó pendiente"), contenido.index("Registró el domicilio"))

    def test_borrar_una_foto_desde_la_ficha(self):
        self.guardar()
        self.client.post(self.url("subir_foto"), {"foto": imagen()})
        foto = FotoDomicilio.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(reverse("reparto:borrar_foto", args=[foto.pk]), follow=True)
        self.assertContains(respuesta, "Se borró la foto.")
        self.assertContains(respuesta, "Borró una foto")
        self.assertFalse(FotoDomicilio.objects.exists())

    def test_con_tres_fotos_ya_no_ofrece_subir(self):
        self.guardar()
        for _ in range(3):
            self.client.post(self.url("subir_foto"), {"foto": imagen()})
        respuesta = self.client.get(self.url("ficha"))
        self.assertContains(respuesta, "3 de 3")
        self.assertNotContains(respuesta, "Subir foto")


class FormularioTests(FichaTests):
    def test_las_dos_pegadas_en_la_latitud_mandan_sobre_la_longitud(self):
        self.guardar(latitud="-36.470000, -72.180000", longitud="-72.999999")
        domicilio = Domicilio.objects.get()
        self.assertEqual((domicilio.latitud, domicilio.longitud), (Decimal("-36.470000"), Decimal("-72.180000")))

    def test_las_coordenadas_con_coma_decimal(self):
        self.guardar(latitud="-36,5", longitud="-72,2")
        domicilio = Domicilio.objects.get()
        self.assertEqual((domicilio.latitud, domicilio.longitud), (Decimal("-36.500000"), Decimal("-72.200000")))

    def test_una_latitud_fuera_de_rango_se_rechaza_en_el_formulario(self):
        respuesta = self.guardar(latitud="-91", longitud="-72.2")
        self.assertContains(respuesta, "La latitud debe estar entre -90 y 90.")
        self.assertFalse(Domicilio.objects.exists())

    def test_un_texto_que_no_es_coordenada(self):
        respuesta = self.guardar(latitud="sur", longitud="")
        self.assertContains(respuesta, "no es una coordenada")

    def test_sin_direccion_avisa(self):
        self.assertContains(self.guardar(direccion=""), "Escriba la dirección.")

    def test_editar_trae_los_datos_actuales(self):
        guardar_domicilio(self.paciente, {"direccion": "Villa Los Aromos", "latitud": Decimal("-36.5"), "longitud": Decimal("-72.2")}, self.encargado)
        respuesta = self.client.get(self.url("editar"))
        self.assertContains(respuesta, 'value="Villa Los Aromos"')
        self.assertContains(respuesta, 'value="-36.500000"')

    def test_marcar_pendiente_sin_motivo_avisa(self):
        guardar_domicilio(self.paciente, {"direccion": "x", "latitud": Decimal("-36.5"), "longitud": Decimal("-72.2")}, self.encargado)
        self.client.post(self.url("verificar"))
        respuesta = self.client.post(self.url("marcar_pendiente"), {"motivo": ""}, follow=True)
        self.assertContains(respuesta, "Escriba por qué")
        self.assertEqual(Domicilio.objects.get().estado, EstadoDomicilio.VERIFICADO)

    def test_las_confirmaciones_usan_el_modal(self):
        guardar_domicilio(self.paciente, {"direccion": "x", "latitud": Decimal("-36.5"), "longitud": Decimal("-72.2")}, self.encargado)
        self.client.post(self.url("subir_foto"), {"foto": imagen()})
        self.client.post(self.url("verificar"))
        contenido = self.client.get(self.url("ficha")).content.decode()
        self.assertIn('data-confirmar-titulo="¿Marcar el domicilio pendiente de verificar?"', contenido)
        self.assertIn('data-confirmar-titulo="¿Borrar esta foto?"', contenido)
        self.assertNotIn("confirm(", contenido)


class PermisosTests(FichaTests):
    def acciones(self):
        foto_pk = 1
        return [
            ("get", self.url("editar")),
            ("post", self.url("editar")),
            ("post", self.url("verificar")),
            ("post", self.url("marcar_pendiente")),
            ("post", self.url("subir_foto")),
            ("post", reverse("reparto:borrar_foto", args=[foto_pk])),
        ]

    def test_la_qf_ve_la_ficha_sin_acciones(self):
        guardar_domicilio(self.paciente, {"direccion": "x", "latitud": Decimal("-36.5"), "longitud": Decimal("-72.2")}, self.encargado)
        self.client.force_login(self.qf)
        respuesta = self.client.get(self.url("ficha"))
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Editar", "Verificar</button>", "Subir foto", "Marcar pendiente"):
            self.assertNotContains(respuesta, texto)

    def test_la_qf_y_el_funcionario_reciben_403_en_cada_accion(self):
        for usuario in (self.qf, crear_usuario("33333333-3", Rol.FUNCIONARIO)):
            self.client.force_login(usuario)
            for metodo, url in self.acciones():
                with self.subTest(usuario=usuario.rol, url=url):
                    self.assertEqual(getattr(self.client, metodo)(url).status_code, 403)

    def test_el_funcionario_no_ve_la_ficha(self):
        self.client.force_login(crear_usuario("33333333-3", Rol.FUNCIONARIO))
        self.assertEqual(self.client.get(self.url("ficha")).status_code, 403)

    def test_sin_sesion_todo_redirige_al_login(self):
        self.client.logout()
        for metodo, url in [("get", self.url("ficha")), *self.acciones()]:
            respuesta = getattr(self.client, metodo)(url)
            self.assertEqual(respuesta.status_code, 302, url)
            self.assertIn(reverse("cuentas:entrar"), respuesta.url)

    def test_un_paciente_sin_despacho_da_404(self):
        joven = crear_paciente(rut_valido("10000002"), edad=30)
        self.assertEqual(self.client.get(reverse("reparto:ficha", args=[joven.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("reparto:editar", args=[joven.pk])).status_code, 404)

    def test_la_lista_enlaza_a_cada_ficha(self):
        self.assertContains(self.client.get(reverse("reparto:domicilios")), f'href="{self.url("ficha")}"')
