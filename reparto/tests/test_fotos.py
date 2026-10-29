"""Fotos del domicilio: procesamiento con Pillow, tope, borrado y entrega privada."""
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from cuentas.models import Rol
from reparto.models import AccionDomicilio, FotoDomicilio
from reparto.servicios import ErrorDeDomicilio, agregar_foto, borrar_foto, guardar_domicilio
from turnos.tests.helpers import crear_paciente, crear_usuario, rut_valido

ORIENTACION, FABRICANTE, GPS = 0x0112, 0x010F, 0x8825


def imagen(ancho=400, alto=200, formato="JPEG", modo="RGB", exif=None, nombre="foto.jpg"):
    salida = BytesIO()
    color = (200, 30, 30, 128) if modo == "RGBA" else (200, 30, 30)
    opciones = {"exif": exif} if exif is not None else {}
    Image.new(modo, (ancho, alto), color).save(salida, formato, **opciones)
    return SimpleUploadedFile(nombre, salida.getvalue(), content_type=f"image/{formato.lower()}")


def exif_de_telefono():
    """Un EXIF como el de una foto de teléfono: girada, con el modelo y la ubicación."""
    exif = Image.Exif()
    exif[ORIENTACION] = 6  # la cámara estaba de lado: hay que girar 90° a la derecha
    exif[FABRICANTE] = "Telefono de prueba"
    exif.get_ifd(GPS).update({1: "S", 2: (36.0, 30.0, 0.0), 3: "W", 4: (72.0, 12.0, 0.0)})
    return exif


class FotosTests(TestCase):
    def setUp(self):
        # Un MEDIA_ROOT por prueba: deshacer la transacción no borra los archivos del disco.
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=self.media)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.encargado = crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)
        self.paciente = crear_paciente(rut_valido("10000001"), edad=85)
        guardar_domicilio(self.paciente, {"direccion": "Camino a Dadinco km 4"}, self.encargado)

    def subir(self, archivo=None):
        return agregar_foto(self.paciente, archivo or imagen(), self.encargado)

    def abrir(self, foto):
        with foto.archivo.open("rb") as archivo:
            guardada = Image.open(BytesIO(archivo.read()))
            guardada.load()
        return guardada


class ProcesamientoTests(FotosTests):
    def test_gira_segun_el_exif_y_lo_quita(self):
        foto = self.subir(imagen(400, 200, exif=exif_de_telefono()))
        guardada = self.abrir(foto)
        self.assertEqual(guardada.format, "JPEG")
        self.assertEqual(guardada.size, (200, 400))
        self.assertEqual((foto.ancho, foto.alto), (200, 400))
        self.assertEqual(len(guardada.getexif()), 0)
        self.assertNotIn("exif", guardada.info)

    def test_un_png_con_transparencia_queda_en_jpeg_con_fondo_blanco(self):
        foto = self.subir(imagen(300, 300, formato="PNG", modo="RGBA", nombre="foto.png"))
        guardada = self.abrir(foto)
        self.assertEqual(guardada.format, "JPEG")
        self.assertEqual(guardada.mode, "RGB")
        self.assertTrue(foto.archivo.name.endswith(".jpg"))

    def test_una_grande_queda_en_1600_de_lado_mayor(self):
        foto = self.subir(imagen(3000, 2000))
        self.assertEqual(self.abrir(foto).size, (1600, 1067))

    def test_una_chica_no_se_agranda(self):
        foto = self.subir(imagen(300, 200))
        self.assertEqual(self.abrir(foto).size, (300, 200))

    def test_el_nombre_es_aleatorio(self):
        foto = self.subir(imagen(nombre="casa de la señora.jpg"))
        self.assertNotIn("señora", foto.archivo.name)
        self.assertRegex(Path(foto.archivo.name).name, r"^[0-9a-f]{32}\.jpg$")

    def test_deja_el_cambio_en_el_historial(self):
        foto = self.subir()
        cambio = foto.domicilio.cambios.first()
        self.assertEqual(cambio.accion, AccionDomicilio.FOTO_AGREGADA)
        self.assertEqual(cambio.usuario, self.encargado)


class RechazosTests(FotosTests):
    def rechazada(self, archivo, mensaje):
        with self.assertRaisesMessage(ErrorDeDomicilio, mensaje):
            self.subir(archivo)
        self.assertFalse(FotoDomicilio.objects.exists())
        self.assertEqual(list(Path(self.media).rglob("*.jpg")), [])

    def test_un_archivo_que_no_es_imagen(self):
        self.rechazada(SimpleUploadedFile("foto.jpg", b"no soy una foto"), "no es una foto JPEG o PNG")

    def test_un_formato_distinto_de_jpeg_o_png(self):
        self.rechazada(imagen(formato="GIF", modo="P", nombre="foto.gif"), "no es una foto JPEG o PNG")

    @override_settings(REPARTO_BYTES_MAXIMOS_FOTO=1000)
    def test_una_foto_demasiado_pesada(self):
        self.rechazada(imagen(1000, 1000), "La foto pesa más de")

    @override_settings(REPARTO_PIXELES_MAXIMOS_ENTRADA=10_000)
    def test_una_foto_con_demasiados_pixeles(self):
        self.rechazada(imagen(200, 100), "demasiados píxeles")

    def test_la_cuarta_foto_se_rechaza(self):
        for _ in range(3):
            self.subir()
        with self.assertRaisesMessage(ErrorDeDomicilio, "Este domicilio ya tiene 3 fotos. Borre una para subir otra."):
            self.subir()
        self.assertEqual(FotoDomicilio.objects.count(), 3)

    def test_sin_domicilio_no_se_sube(self):
        otro = crear_paciente(rut_valido("10000002"), edad=85)
        with self.assertRaisesMessage(ErrorDeDomicilio, "todavía no tiene un domicilio"):
            agregar_foto(otro, imagen(), self.encargado)


class BorrarTests(FotosTests):
    def test_borra_el_archivo_y_lo_deja_en_el_historial(self):
        foto = self.subir()
        ruta = Path(foto.archivo.path)
        self.assertTrue(ruta.exists())
        with self.captureOnCommitCallbacks(execute=True):
            domicilio = borrar_foto(foto.pk, self.encargado)
        self.assertFalse(ruta.exists())
        self.assertFalse(FotoDomicilio.objects.exists())
        self.assertEqual(domicilio.cambios.first().accion, AccionDomicilio.FOTO_BORRADA)

    def test_despues_de_borrar_se_puede_subir_otra(self):
        fotos = [self.subir() for _ in range(3)]
        with self.captureOnCommitCallbacks(execute=True):
            borrar_foto(fotos[0].pk, self.encargado)
        self.assertTrue(self.subir().pk)

    def test_una_foto_que_no_existe_avisa(self):
        with self.assertRaisesMessage(ErrorDeDomicilio, "ya no existe"):
            borrar_foto(999, self.encargado)


class EntregaDeLaFotoTests(FotosTests):
    def test_el_encargado_y_la_qf_la_ven_en_privado(self):
        foto = self.subir()
        url = reverse("reparto:foto", args=[foto.pk])
        for usuario in (self.encargado, crear_usuario("22222222-2", Rol.QF)):
            self.client.force_login(usuario)
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta["Content-Type"], "image/jpeg")
            self.assertEqual(respuesta["Cache-Control"], "private")
            self.assertTrue(b"".join(respuesta.streaming_content).startswith(b"\xff\xd8"))

    def test_el_funcionario_recibe_403_y_sin_sesion_va_al_login(self):
        url = reverse("reparto:foto", args=[self.subir().pk])
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("cuentas:entrar"), respuesta.url)
        self.client.force_login(crear_usuario("33333333-3", Rol.FUNCIONARIO))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_una_foto_que_no_existe_da_404(self):
        self.client.force_login(self.encargado)
        self.assertEqual(self.client.get(reverse("reparto:foto", args=[999])).status_code, 404)

    def test_no_hay_una_url_publica_de_media(self):
        foto = self.subir()
        self.client.force_login(self.encargado)
        self.assertEqual(self.client.get(f"/media/{foto.archivo.name}").status_code, 404)
        self.assertEqual(self.client.get(f"/{foto.archivo.name}").status_code, 404)
