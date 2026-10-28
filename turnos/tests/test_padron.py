"""Pantallas del padrón (solo la QF): subida, vista previa, aplicación, cancelación y descargas."""
import csv
import io
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Rol
from turnos.importacion import neutralizar_celda, preparar_carga
from turnos.models import CargaPadron, EstadoCarga, Paciente, RecetaCronica
from turnos.tests.helpers import crear_usuario
from turnos.tests.test_importacion import csv_de, linea


def leer_csv_descargado(respuesta):
    texto = respuesta.content.decode("utf-8")
    assert texto.startswith("﻿"), "el CSV debe ir con BOM para que Excel lea las tildes"
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))


class PadronAccesoTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("9876543-3", Rol.QF)
        self.carga = preparar_carga(csv_de(linea("12.345.678-5", folio="R-1")), self.qf)

    def rutas(self):
        pk = self.carga.pk
        return [
            ("get", reverse("turnos:padron")),
            ("post", reverse("turnos:padron")),
            ("get", reverse("turnos:padron_plantilla")),
            ("get", reverse("turnos:padron_carga", args=[pk])),
            ("post", reverse("turnos:padron_confirmar", args=[pk])),
            ("post", reverse("turnos:padron_cancelar", args=[pk])),
            ("get", reverse("turnos:padron_rechazos", args=[pk])),
        ]

    def test_sin_sesion_redirige_al_login(self):
        for metodo, ruta in self.rutas():
            with self.subTest(ruta=ruta, metodo=metodo):
                respuesta = getattr(self.client, metodo)(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(reverse("cuentas:entrar"), respuesta.url)

    def test_funcionario_y_encargado_de_terreno_reciben_403(self):
        otros = [crear_usuario("12345678-5", Rol.FUNCIONARIO), crear_usuario("11111111-1", Rol.ENCARGADO_TERRENO)]
        for usuario in otros:
            self.client.force_login(usuario)
            for metodo, ruta in self.rutas():
                with self.subTest(rol=usuario.rol, ruta=ruta, metodo=metodo):
                    self.assertEqual(getattr(self.client, metodo)(ruta).status_code, 403)
        self.carga.refresh_from_db()
        self.assertEqual(self.carga.estado, EstadoCarga.PENDIENTE)

    def test_carga_inexistente_da_404(self):
        self.client.force_login(self.qf)
        self.assertEqual(self.client.get(reverse("turnos:padron_carga", args=[999])).status_code, 404)

    def test_la_barra_de_la_qf_lleva_al_padron(self):
        self.client.force_login(self.qf)
        self.assertContains(self.client.get(reverse("turnos:ventanillas")), reverse("turnos:padron"))

    def test_la_barra_del_funcionario_no_lleva_al_padron(self):
        self.client.force_login(crear_usuario("12345678-5", Rol.FUNCIONARIO))
        self.assertNotContains(self.client.get(reverse("turnos:atencion")), reverse("turnos:padron"))


class PadronFlujoTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("9876543-3", Rol.QF)
        self.client.force_login(self.qf)

    def subir(self, archivo):
        return self.client.post(reverse("turnos:padron"), {"archivo": archivo})

    def test_la_pagina_muestra_el_formulario_y_la_plantilla(self):
        respuesta = self.client.get(reverse("turnos:padron"))
        self.assertContains(respuesta, 'enctype="multipart/form-data"')
        self.assertContains(respuesta, reverse("turnos:padron_plantilla"))
        self.assertContains(respuesta, "Todavía no hay cargas")

    def test_subir_muestra_la_vista_previa_sin_escribir(self):
        respuesta = self.subir(csv_de(
            linea("12.345.678-5", folio="R-1", nombres="Inés"), linea("12.345.678-9", folio="R-2")
        ))
        carga = CargaPadron.objects.get()
        self.assertRedirects(respuesta, reverse("turnos:padron_carga", args=[carga.pk]))
        self.assertFalse(Paciente.objects.exists())

        previa = self.client.get(respuesta.url)
        self.assertContains(previa, "vista previa")
        self.assertContains(previa, "Aplicar carga")
        self.assertContains(previa, 'data-confirmar-titulo="¿Aplicar esta carga?"')
        self.assertContains(previa, 'data-confirmar-titulo="¿Cancelar esta carga?"')
        self.assertContains(previa, "Inés Prueba")  # muestra de filas para revisar tildes
        self.assertContains(previa, "Fila 3: 12.345.678-9")
        self.assertContains(previa, "dígito verificador")
        self.assertNotContains(previa, "confirm(")

    def test_aplicar_escribe_y_muestra_el_resultado(self):
        self.subir(csv_de(linea("12.345.678-5", folio="R-1")))
        carga = CargaPadron.objects.get()
        respuesta = self.client.post(reverse("turnos:padron_confirmar", args=[carga.pk]), follow=True)
        self.assertRedirects(respuesta, reverse("turnos:padron_carga", args=[carga.pk]))
        self.assertContains(respuesta, "Carga aplicada")
        self.assertContains(respuesta, "Resultado")
        self.assertNotContains(respuesta, "Aplicar carga")
        self.assertTrue(RecetaCronica.objects.filter(folio="R-1", paciente__rut="12345678-5").exists())
        carga.refresh_from_db()
        self.assertEqual(carga.estado, EstadoCarga.APLICADA)

    def test_aplicar_dos_veces_avisa_sin_duplicar(self):
        self.subir(csv_de(linea("12.345.678-5", folio="R-1")))
        carga = CargaPadron.objects.get()
        self.client.post(reverse("turnos:padron_confirmar", args=[carga.pk]))
        respuesta = self.client.post(reverse("turnos:padron_confirmar", args=[carga.pk]), follow=True)
        self.assertContains(respuesta, "ya no está pendiente")
        self.assertEqual(RecetaCronica.objects.count(), 1)

    def test_cancelar(self):
        self.subir(csv_de(linea("12.345.678-5", folio="R-1")))
        carga = CargaPadron.objects.get()
        respuesta = self.client.post(reverse("turnos:padron_cancelar", args=[carga.pk]), follow=True)
        self.assertRedirects(respuesta, reverse("turnos:padron"))
        self.assertContains(respuesta, "Carga cancelada")
        carga.refresh_from_db()
        self.assertEqual(carga.estado, EstadoCarga.CANCELADA)
        self.assertIsNone(carga.filas_validas)
        self.assertFalse(Paciente.objects.exists())

    def test_la_bitacora_muestra_cada_carga(self):
        self.subir(csv_de(linea("12.345.678-5", folio="R-1")))
        aplicada = CargaPadron.objects.get()
        self.client.post(reverse("turnos:padron_confirmar", args=[aplicada.pk]))
        self.subir(csv_de(linea("11.111.111-1")))
        cancelada = CargaPadron.objects.exclude(pk=aplicada.pk).get()
        self.client.post(reverse("turnos:padron_cancelar", args=[cancelada.pk]))
        self.subir(csv_de(linea("22.222.222-2")))
        descartada = CargaPadron.objects.exclude(pk__in=[aplicada.pk, cancelada.pk]).get()
        CargaPadron.objects.filter(pk=descartada.pk).update(creada_en=timezone.now() - timedelta(hours=2))

        respuesta = self.client.get(reverse("turnos:padron"))
        for estado in ("Aplicada", "Cancelada", "Descartada por tiempo"):
            self.assertContains(respuesta, estado)
        self.assertContains(respuesta, "padron.csv", count=3)
        self.assertContains(respuesta, self.qf.nombre_completo)
        self.assertContains(respuesta, "1 fila, 0 rechazadas")
        self.assertContains(respuesta, "Nuevos: 1 paciente y 1 receta.")
        self.assertEqual(CargaPadron.objects.get(pk=descartada.pk).estado, EstadoCarga.DESCARTADA)

    def test_archivo_sin_columnas_muestra_el_error_sin_crear_carga(self):
        archivo = SimpleUploadedFile("padron.csv", "rut;nombres\n12345678-5;Ana\n".encode())
        respuesta = self.subir(archivo)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Faltan columnas obligatorias")
        self.assertContains(respuesta, "fecha_nacimiento")
        self.assertFalse(CargaPadron.objects.exists())

    def test_extension_no_admitida_muestra_el_error(self):
        respuesta = self.subir(SimpleUploadedFile("padron.pdf", b"%PDF-1.4"))
        self.assertContains(respuesta, ".csv o .xlsx")
        self.assertFalse(CargaPadron.objects.exists())

    def test_sin_archivo_pide_uno(self):
        respuesta = self.client.post(reverse("turnos:padron"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(CargaPadron.objects.exists())

    def test_la_plantilla_subida_sin_cambios_no_tiene_rechazos(self):
        respuesta = self.client.get(reverse("turnos:padron_plantilla"))
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", respuesta["Content-Disposition"])
        filas = leer_csv_descargado(respuesta)
        self.assertEqual(filas[0][:2], ["rut", "nombres"])
        self.assertEqual(len(filas), 2)

        self.subir(SimpleUploadedFile("plantilla-padron.csv", respuesta.content))
        carga = CargaPadron.objects.get()
        self.assertEqual((carga.filas_totales, carga.filas_rechazadas), (1, 0))

    def test_csv_de_rechazos_neutraliza_formulas(self):
        self.subir(csv_de(
            linea("=HYPERLINK(1)", folio="R-1"),
            linea("+56 9 1234", folio="R-2"),
            linea("-1", folio="R-3"),
            linea("@SUM(A1)", folio="R-4"),
            linea("12.345.678-9", folio="R-5"),
        ))
        carga = CargaPadron.objects.get()
        respuesta = self.client.get(reverse("turnos:padron_rechazos", args=[carga.pk]))
        self.assertIn(f"rechazos-carga-{carga.pk}.csv", respuesta["Content-Disposition"])
        filas = leer_csv_descargado(respuesta)
        self.assertEqual(filas[0], ["fila", "rut", "motivo"])
        self.assertEqual(len(filas), 6)
        self.assertEqual([fila[1] for fila in filas[1:5]], ["'=HYPERLINK(1)", "'+56 9 1234", "'-1", "'@SUM(A1)"])
        for fila in filas:
            for celda in fila:
                self.assertFalse(celda.startswith(("=", "+", "-", "@")), celda)

    def test_neutralizar_celda(self):
        self.assertEqual(neutralizar_celda("=1+1"), "'=1+1")
        self.assertEqual(neutralizar_celda("12.345.678-5"), "12.345.678-5")
        self.assertEqual(neutralizar_celda(12), "12")
