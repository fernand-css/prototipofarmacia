"""Importación del padrón: lectura, validación, vista previa, confirmación y cancelación."""
import hashlib
import io
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook

from cuentas.models import Rol
from turnos.importacion import (
    COLUMNAS,
    ErrorDeArchivo,
    ErrorDeCarga,
    FilaLeida,
    cancelar_carga,
    confirmar_carga,
    descartar_cargas_vencidas,
    leer_archivo,
    normalizar_encabezado,
    preparar_carga,
    validar_filas,
)
from turnos.models import CargaPadron, EstadoCarga, Paciente, RecetaCronica
from turnos.servicios import TipoResultado, emitir_turno
from turnos.tests.helpers import crear_usuario

ENCABEZADO = (
    "rut;nombres;apellidos;fecha_nacimiento;discapacidad;embarazada;postrado;"
    "folio;fecha_emision;vigencia_meses;entregas_maximas;entregas_realizadas"
)
FILA = "12.345.678-5;Ana;Prueba;01-02-1950;no;no;si;R-000001;15-09-2026;6;6;2"


def archivo_csv(texto, nombre="padron.csv", codificacion="utf-8"):
    return SimpleUploadedFile(nombre, texto.encode(codificacion))


def archivo_xlsx(filas, nombre="padron.xlsx"):
    libro = Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return SimpleUploadedFile(nombre, salida.getvalue())


class NormalizarEncabezadoTests(SimpleTestCase):
    def test_quita_mayusculas_tildes_y_espacios_a_los_lados(self):
        self.assertEqual(normalizar_encabezado("  Fecha_Emisión "), "fecha_emision")
        self.assertEqual(normalizar_encabezado("RUT"), "rut")


class LeerCsvTests(SimpleTestCase):
    def test_separador_punto_y_coma(self):
        lectura = leer_archivo(archivo_csv(f"{ENCABEZADO}\n{FILA}\n"))
        self.assertEqual(len(lectura.filas), 1)
        fila = lectura.filas[0]
        self.assertEqual(fila.numero, 2)
        self.assertEqual(fila.valores["rut"], "12.345.678-5")
        self.assertEqual(fila.valores["fecha_emision"], "15-09-2026")
        self.assertEqual(fila.valores["entregas_realizadas"], "2")

    def test_separador_coma(self):
        texto = f"{ENCABEZADO.replace(';', ',')}\n{FILA.replace(';', ',')}\n"
        self.assertEqual(leer_archivo(archivo_csv(texto)).filas[0].valores["nombres"], "Ana")

    def test_utf8_con_bom(self):
        texto = f"{ENCABEZADO}\n{FILA.replace('Prueba', 'Muñoz Peña')}\n"
        lectura = leer_archivo(archivo_csv(texto, codificacion="utf-8-sig"))
        self.assertEqual(lectura.encabezados[0], "rut")
        self.assertEqual(lectura.filas[0].valores["apellidos"], "Muñoz Peña")

    def test_windows_1252_con_tildes_y_enie(self):
        texto = f"{ENCABEZADO}\n{FILA.replace('Ana', 'Inés').replace('Prueba', 'Ñúñez')}\n"
        lectura = leer_archivo(archivo_csv(texto, codificacion="cp1252"))
        self.assertEqual(lectura.filas[0].valores["nombres"], "Inés")
        self.assertEqual(lectura.filas[0].valores["apellidos"], "Ñúñez")

    def test_encabezados_con_mayusculas_tildes_y_espacios(self):
        encabezado = ENCABEZADO.upper().replace("FECHA_EMISION", " Fecha_Emisión ")
        lectura = leer_archivo(archivo_csv(f"{encabezado}\n{FILA}\n"))
        self.assertIn("fecha_emision", lectura.encabezados)
        self.assertEqual(lectura.filas[0].valores["fecha_emision"], "15-09-2026")

    def test_columnas_extra_se_ignoran(self):
        lectura = leer_archivo(archivo_csv(f"comuna;{ENCABEZADO}\nCalera;{FILA}\n"))
        self.assertNotIn("comuna", lectura.filas[0].valores)
        self.assertEqual(lectura.filas[0].valores["rut"], "12.345.678-5")

    def test_columnas_opcionales_ausentes_quedan_vacias(self):
        encabezado = "rut;nombres;apellidos;fecha_nacimiento;folio;fecha_emision;vigencia_meses;entregas_maximas"
        fila = "12345678-5;Ana;Prueba;01-02-1950;R-1;15-09-2026;6;6"
        valores = leer_archivo(archivo_csv(f"{encabezado}\n{fila}\n")).filas[0].valores
        self.assertEqual(valores["postrado"], "")
        self.assertEqual(valores["entregas_realizadas"], "")

    def test_filas_vacias_se_ignoran_y_conservan_el_numero(self):
        lectura = leer_archivo(archivo_csv(f"{ENCABEZADO}\n;;;;;;;;;;;\n\n{FILA}\n"))
        self.assertEqual([fila.numero for fila in lectura.filas], [4])

    def test_fila_mas_corta_que_el_encabezado(self):
        lectura = leer_archivo(archivo_csv(f"{ENCABEZADO}\n12345678-5;Ana;Prueba;01-02-1950\n"))
        self.assertEqual(lectura.filas[0].valores["folio"], "")


class LeerXlsxTests(SimpleTestCase):
    def test_lee_la_primera_hoja_con_celdas_de_fecha_y_numeros(self):
        archivo = archivo_xlsx([
            ENCABEZADO.split(";"),
            ["12345678-5", "Ana", "Prueba", datetime(1950, 2, 1), None, None, True,
             "R-000001", date(2026, 9, 15), 6, 6.0, 2],
        ])
        valores = leer_archivo(archivo).filas[0].valores
        self.assertEqual(valores["fecha_nacimiento"], "1950-02-01")
        self.assertEqual(valores["fecha_emision"], "2026-09-15")
        self.assertEqual(valores["postrado"], "1")
        self.assertEqual(valores["discapacidad"], "")
        self.assertEqual(valores["entregas_maximas"], "6")

    def test_numero_de_fila_como_en_excel(self):
        archivo = archivo_xlsx([ENCABEZADO.split(";"), [None] * 12, FILA.split(";")])
        self.assertEqual([fila.numero for fila in leer_archivo(archivo).filas], [3])


class ErrorDeArchivoTests(SimpleTestCase):
    def assertRechaza(self, archivo, texto):
        with self.assertRaises(ErrorDeArchivo) as contexto:
            leer_archivo(archivo)
        self.assertIn(texto, str(contexto.exception))

    def test_extension_no_admitida(self):
        self.assertRechaza(archivo_csv(f"{ENCABEZADO}\n{FILA}\n", nombre="padron.xls"), ".csv o .xlsx")

    @override_settings(TURNOS_PADRON_BYTES_MAXIMOS=100)
    def test_archivo_demasiado_grande(self):
        self.assertRechaza(archivo_csv(f"{ENCABEZADO}\n{FILA}\n"), "pesa más de")

    def test_archivo_vacio(self):
        self.assertRechaza(archivo_csv(""), "vacío")
        self.assertRechaza(archivo_csv("\n;;;\n"), "vacío")

    def test_xlsx_danado(self):
        self.assertRechaza(SimpleUploadedFile("padron.xlsx", b"esto no es un excel"), "no es un Excel")

    def test_codificacion_ilegible(self):
        contenido = (ENCABEZADO + "\n").encode() + b"\x81\x8d\x8f\x90\x9d;\xff\xfe\n"
        self.assertRechaza(SimpleUploadedFile("padron.csv", contenido), "codificación")

    @override_settings(TURNOS_PADRON_FILAS_MAXIMAS=2)
    def test_demasiadas_filas(self):
        self.assertRechaza(archivo_csv(f"{ENCABEZADO}\n{FILA}\n{FILA}\n{FILA}\n"), "más de 2 filas")

    @override_settings(TURNOS_PADRON_FILAS_MAXIMAS=2)
    def test_justo_el_maximo_de_filas(self):
        self.assertEqual(len(leer_archivo(archivo_csv(f"{ENCABEZADO}\n{FILA}\n{FILA}\n")).filas), 2)

    def test_faltan_columnas_obligatorias_y_las_nombra(self):
        encabezado = ENCABEZADO.replace("folio;", "").replace("nombres;", "")
        with self.assertRaises(ErrorDeArchivo) as contexto:
            leer_archivo(archivo_csv(f"{encabezado}\n{FILA}\n"))
        mensaje = str(contexto.exception)
        self.assertIn("nombres", mensaje)
        self.assertIn("folio", mensaje)


HOY = date(2026, 10, 28)
SIN_RECETA = {
    "folio": "",
    "fecha_emision": "",
    "vigencia_meses": "",
    "entregas_maximas": "",
    "entregas_realizadas": "",
}


def fila(numero=2, **valores):
    """Una fila leída válida (paciente con receta); los argumentos reemplazan columnas."""
    base = {
        "rut": "12.345.678-5",
        "nombres": "Ana",
        "apellidos": "Prueba",
        "fecha_nacimiento": "01-02-1950",
        "discapacidad": "no",
        "embarazada": "",
        "postrado": "Sí",
        "folio": "R-000001",
        "fecha_emision": "15/09/2026",
        "vigencia_meses": "6",
        "entregas_maximas": "6",
        "entregas_realizadas": "2",
    }
    base.update(valores)
    return FilaLeida(numero, {columna: base.get(columna, "") for columna in COLUMNAS})


class ValidarFilasTests(SimpleTestCase):
    def validar(self, *filas):
        return validar_filas(list(filas), hoy=HOY)

    def motivo(self, *filas):
        validacion = self.validar(*filas)
        self.assertEqual(len(validacion.rechazos), 1)
        return validacion.rechazos[0]["motivo"]

    def test_fila_valida_queda_normalizada(self):
        validacion = self.validar(fila())
        self.assertEqual(validacion.rechazos, [])
        self.assertEqual(validacion.validas, [{
            "fila": 2,
            "rut_original": "12.345.678-5",
            "rut": "12345678-5",
            "nombres": "Ana",
            "apellidos": "Prueba",
            "fecha_nacimiento": "1950-02-01",
            "tiene_discapacidad": False,
            "esta_embarazada": False,
            "es_postrado": True,
            "receta": {
                "folio": "R-000001",
                "fecha_emision": "2026-09-15",
                "vigencia_meses": 6,
                "entregas_maximas": 6,
                "entregas_realizadas": 2,
            },
        }])

    def test_paciente_sin_receta(self):
        validacion = self.validar(fila(**SIN_RECETA))
        self.assertEqual(validacion.rechazos, [])
        self.assertIsNone(validacion.validas[0]["receta"])

    def test_entregas_realizadas_vacia_es_cero(self):
        receta = self.validar(fila(entregas_realizadas="")).validas[0]["receta"]
        self.assertEqual(receta["entregas_realizadas"], 0)

    def test_formatos_de_fecha_y_banderas(self):
        validacion = self.validar(
            fila(2, fecha_nacimiento="1950-02-01", folio="R-1", discapacidad="SI", embarazada="1"),
            fila(3, fecha_nacimiento="01/02/1950", folio="R-2", discapacidad="si", embarazada="1"),
        )
        self.assertEqual(validacion.rechazos, [])
        self.assertEqual({v["fecha_nacimiento"] for v in validacion.validas}, {"1950-02-01"})
        self.assertTrue(all(v["tiene_discapacidad"] and v["esta_embarazada"] for v in validacion.validas))

    # 1. RUT

    def test_rut_vacio(self):
        self.assertEqual(self.motivo(fila(rut="")), "Falta el RUT.")

    def test_rut_con_digito_verificador_invalido(self):
        self.assertIn("dígito verificador", self.motivo(fila(rut="12.345.678-9")))

    def test_rut_con_formato_invalido(self):
        self.assertIn("RUT válido", self.motivo(fila(rut="abc")))

    def test_rechazo_conserva_el_rut_tal_como_venia(self):
        rechazo = self.validar(fila(7, rut="12.345.678-9")).rechazos[0]
        self.assertEqual((rechazo["fila"], rechazo["rut"]), (7, "12.345.678-9"))

    def test_una_fila_invalida_no_detiene_las_demas(self):
        validacion = self.validar(fila(2, rut="12.345.678-9"), fila(3))
        self.assertEqual([r["fila"] for r in validacion.rechazos], [2])
        self.assertEqual([v["fila"] for v in validacion.validas], [3])

    # 2. Formato de los campos

    def test_campo_obligatorio_vacio(self):
        self.assertEqual(self.motivo(fila(nombres="")), "Falta el campo nombres.")
        self.assertEqual(self.motivo(fila(fecha_nacimiento="")), "Falta el campo fecha_nacimiento.")

    def test_texto_demasiado_largo(self):
        self.assertIn("100 caracteres", self.motivo(fila(apellidos="x" * 101)))

    def test_fecha_invalida(self):
        self.assertIn("no es una fecha válida", self.motivo(fila(fecha_nacimiento="31-02-1950")))
        self.assertIn("no es una fecha válida", self.motivo(fila(fecha_emision="ayer")))

    def test_fecha_futura(self):
        self.assertIn("futura", self.motivo(fila(fecha_nacimiento="29-10-2026")))
        self.assertIn("futura", self.motivo(fila(fecha_emision="2027-01-01")))

    def test_bandera_invalida(self):
        self.assertEqual(self.motivo(fila(postrado="tal vez")), "El campo postrado debe ser sí o no.")

    def test_numeros_fuera_de_rango_o_con_formato_invalido(self):
        self.assertIn("de 1 a 24", self.motivo(fila(vigencia_meses="0")))
        self.assertIn("de 1 a 24", self.motivo(fila(entregas_maximas="25")))
        self.assertIn("de 1 a 24", self.motivo(fila(vigencia_meses="6.5")))
        self.assertIn("de 0 a 24", self.motivo(fila(entregas_realizadas="-1")))

    def test_folio_con_espacios_o_demasiado_largo(self):
        self.assertIn("sin espacios", self.motivo(fila(folio="R 1")))
        self.assertIn("20 caracteres", self.motivo(fila(folio="R" * 21)))

    def test_el_rut_se_revisa_antes_que_los_demas_campos(self):
        self.assertIn("dígito verificador", self.motivo(fila(rut="12.345.678-9", nombres="")))

    # 3. Receta incompleta

    def test_receta_incompleta(self):
        motivo = self.motivo(fila(fecha_emision="", entregas_maximas=""))
        self.assertEqual(motivo, "Receta incompleta: falta fecha_emision y entregas_maximas.")

    def test_solo_entregas_realizadas_es_receta_incompleta(self):
        motivo = self.motivo(fila(**{**SIN_RECETA, "entregas_realizadas": "1"}))
        self.assertIn("Receta incompleta", motivo)

    # 4. Entregas realizadas sobre el máximo

    def test_entregas_realizadas_sobre_el_maximo(self):
        motivo = self.motivo(fila(entregas_maximas="3", entregas_realizadas="4"))
        self.assertEqual(motivo, "Las entregas realizadas (4) superan las entregas máximas (3).")

    def test_entregas_realizadas_igual_al_maximo_se_acepta(self):
        self.assertEqual(self.validar(fila(entregas_maximas="3", entregas_realizadas="3")).rechazos, [])

    # 5. Un mismo RUT con datos de paciente distintos

    def test_rut_con_y_sin_puntos_es_el_mismo_paciente_con_dos_recetas(self):
        validacion = self.validar(fila(2, rut="12.345.678-5"), fila(3, rut="123456785", folio="R-000002"))
        self.assertEqual(validacion.rechazos, [])
        self.assertEqual({v["rut"] for v in validacion.validas}, {"12345678-5"})
        self.assertEqual([v["receta"]["folio"] for v in validacion.validas], ["R-000001", "R-000002"])

    def test_mismo_rut_con_datos_distintos_rechaza_todas_sus_filas(self):
        validacion = self.validar(
            fila(12),
            fila(40, rut="12345678-5", nombres="Anita", folio="R-000002"),
            fila(41, rut="11.111.111-1", folio="R-000003"),
        )
        self.assertEqual([r["fila"] for r in validacion.rechazos], [12, 40])
        self.assertEqual(
            {r["motivo"] for r in validacion.rechazos},
            {"Datos del paciente distintos en las filas 12 y 40."},
        )
        self.assertEqual([v["fila"] for v in validacion.validas], [41])

    def test_otra_fecha_de_nacimiento_tambien_es_conflicto(self):
        validacion = self.validar(fila(2), fila(3, fecha_nacimiento="02-02-1950", folio="R-000002"))
        self.assertEqual(len(validacion.rechazos), 2)

    def test_una_fila_ya_rechazada_no_genera_conflicto(self):
        validacion = self.validar(fila(2), fila(3, nombres="", folio="R-000002"))
        self.assertEqual([r["fila"] for r in validacion.rechazos], [3])
        self.assertEqual([v["fila"] for v in validacion.validas], [2])

    # 6. Un folio repetido en el archivo

    def test_folio_repetido_rechaza_todas_sus_filas(self):
        validacion = self.validar(
            fila(2),
            fila(3, rut="11.111.111-1"),
            fila(4, rut="11.111.111-1", folio="R-000009"),
        )
        self.assertEqual([r["fila"] for r in validacion.rechazos], [2, 3])
        self.assertEqual(validacion.rechazos[0]["motivo"], "El folio R-000001 se repite en las filas 2 y 3.")
        self.assertEqual([v["fila"] for v in validacion.validas], [4])

    def test_conflicto_de_paciente_tiene_prioridad_sobre_folio_repetido(self):
        validacion = self.validar(fila(2), fila(3, nombres="Anita"))
        self.assertEqual(len(validacion.rechazos), 2)
        self.assertTrue(all(r["motivo"].startswith("Datos del paciente") for r in validacion.rechazos))


def linea(rut, nombres="Ana", folio="", nacimiento="01-02-1950", postrado="no", receta=("01-09-2026", 6, 6, 2)):
    """Una línea del CSV de prueba; sin folio, la fila no trae receta."""
    if folio:
        emision, vigencia, maximas, realizadas = receta
        datos_receta = f"{folio};{emision};{vigencia};{maximas};{realizadas}"
    else:
        datos_receta = ";;;;"
    return f"{rut};{nombres};Prueba;{nacimiento};no;no;{postrado};{datos_receta}"


def csv_de(*lineas):
    return archivo_csv("\n".join((ENCABEZADO,) + lineas) + "\n")


def en_la_base(rut, nombres="Ana", folio=None, realizadas=2, vigencia=6):
    """Un paciente (y su receta, si se da folio) igual al que describe `linea` con sus valores."""
    paciente = Paciente.objects.get_or_create(
        rut=rut,
        defaults={"nombres": nombres, "apellidos": "Prueba", "fecha_nacimiento": date(1950, 2, 1)},
    )[0]
    if folio:
        RecetaCronica.objects.create(
            paciente=paciente,
            folio=folio,
            fecha_emision=date(2026, 9, 1),
            vigencia_meses=vigencia,
            entregas_maximas=6,
            entregas_realizadas=realizadas,
        )
    return paciente


class PrepararCargaTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("9876543-3", Rol.QF)

    def preparar(self, *lineas):
        return preparar_carga(csv_de(*lineas), self.qf)

    def test_no_escribe_pacientes_ni_recetas(self):
        en_la_base("12345678-5", nombres="Otra", folio="R-1", realizadas=1)
        antes = (Paciente.objects.count(), RecetaCronica.objects.count())
        self.preparar(linea("12.345.678-5", folio="R-1"), linea("11.111.111-1", folio="R-2"))
        self.assertEqual((Paciente.objects.count(), RecetaCronica.objects.count()), antes)
        self.assertEqual(Paciente.objects.get(rut="12345678-5").nombres, "Otra")
        self.assertEqual(RecetaCronica.objects.get(folio="R-1").entregas_realizadas, 1)

    def test_crea_la_carga_pendiente_con_bitacora_del_archivo(self):
        archivo = csv_de(linea("12.345.678-5", folio="R-1"))
        contenido = archivo.read()
        carga = preparar_carga(archivo, self.qf)
        self.assertEqual(carga.estado, EstadoCarga.PENDIENTE)
        self.assertEqual(carga.usuario, self.qf)
        self.assertEqual(carga.nombre_archivo, "padron.csv")
        self.assertEqual(carga.bytes_archivo, len(contenido))
        self.assertEqual(carga.huella_archivo, hashlib.sha256(contenido).hexdigest())
        self.assertEqual(carga.filas_totales, 1)
        self.assertEqual(carga.filas_validas[0]["rut"], "12345678-5")

    def test_conteos_previstos_de_un_archivo_conocido(self):
        en_la_base("12345678-5", folio="R-1")
        en_la_base("11111111-1", nombres="Otra", folio="R-2")
        carga = self.preparar(
            linea("12.345.678-5", folio="R-1"),  # paciente y receta sin cambios
            linea("12.345.678-5", folio="R-3"),  # receta nueva del mismo paciente
            linea("11.111.111-1", folio="R-2", receta=("01-09-2026", 12, 6, 2)),  # ambos actualizados
            linea("22.222.222-2"),  # paciente nuevo, sin receta
            linea("12.345.678-9", folio="R-4"),  # rechazada por el RUT
        )
        self.assertEqual(
            (carga.pacientes_creados, carga.pacientes_actualizados, carga.pacientes_sin_cambios),
            (1, 1, 1),
        )
        self.assertEqual(
            (carga.recetas_creadas, carga.recetas_actualizadas, carga.recetas_sin_cambios),
            (1, 1, 1),
        )
        self.assertEqual((carga.filas_totales, carga.filas_rechazadas), (5, 1))
        self.assertEqual(len(carga.filas_validas), 4)

    def test_folio_de_otro_rut_en_la_base_se_rechaza(self):
        en_la_base("11111111-1", folio="R-1")
        carga = self.preparar(linea("12.345.678-5", folio="R-1"), linea("22.222.222-2", folio="R-2"))
        self.assertEqual(carga.rechazos, [{
            "fila": 2, "rut": "12.345.678-5", "motivo": "El folio R-1 ya está registrado para otro RUT.",
        }])
        self.assertEqual([f["fila"] for f in carga.filas_validas], [3])
        self.assertEqual(carga.pacientes_creados, 1)

    def test_contador_local_mayor_produce_advertencia_y_no_cuenta_como_cambio(self):
        en_la_base("12345678-5", folio="R-1", realizadas=4)
        carga = self.preparar(linea("12.345.678-5", folio="R-1"))
        self.assertEqual(carga.recetas_sin_cambios, 1)
        self.assertEqual(len(carga.advertencias), 1)
        self.assertEqual((carga.advertencias[0]["fila"], carga.advertencias[0]["folio"]), (2, "R-1"))
        self.assertIn("se conservan 4", carga.advertencias[0]["mensaje"])

    def test_contador_del_archivo_mayor_cuenta_como_actualizacion(self):
        en_la_base("12345678-5", folio="R-1", realizadas=1)
        carga = self.preparar(linea("12.345.678-5", folio="R-1"))
        self.assertEqual((carga.recetas_actualizadas, carga.advertencias), (1, []))

    def test_rechazos_de_todas_las_reglas_ordenados_por_fila(self):
        en_la_base("11111111-1", folio="R-1")
        carga = self.preparar(linea("12.345.678-5", folio="R-1"), linea("12.345.678-9", folio="R-2"))
        self.assertEqual([r["fila"] for r in carga.rechazos], [2, 3])
        self.assertEqual(carga.filas_rechazadas, 2)

    def test_archivo_sin_columnas_no_crea_carga(self):
        with self.assertRaises(ErrorDeArchivo):
            preparar_carga(archivo_csv("rut;nombres\n12345678-5;Ana\n"), self.qf)
        self.assertFalse(CargaPadron.objects.exists())


class ConfirmarCargaTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("9876543-3", Rol.QF)

    def preparar(self, *lineas):
        return preparar_carga(csv_de(*lineas), self.qf)

    def confirmar(self, carga):
        return confirmar_carga(carga, self.qf)

    def test_crea_y_actualiza_lo_previsto(self):
        en_la_base("12345678-5", folio="R-1")
        en_la_base("11111111-1", nombres="Otra", folio="R-2")
        carga = self.preparar(
            linea("12.345.678-5", folio="R-1"),
            linea("12.345.678-5", folio="R-3"),
            linea("11.111.111-1", folio="R-2", receta=("01-09-2026", 12, 6, 2)),
            linea("22.222.222-2", postrado="si"),
        )
        previstos = (carga.pacientes_creados, carga.pacientes_actualizados, carga.recetas_creadas,
                     carga.recetas_actualizadas, carga.recetas_sin_cambios)
        carga = self.confirmar(carga)

        self.assertEqual(carga.estado, EstadoCarga.APLICADA)
        self.assertIsNotNone(carga.aplicada_en)
        self.assertIsNone(carga.filas_validas)
        self.assertEqual(
            (carga.pacientes_creados, carga.pacientes_actualizados, carga.recetas_creadas,
             carga.recetas_actualizadas, carga.recetas_sin_cambios),
            previstos,
        )
        nuevo = Paciente.objects.get(rut="22222222-2")
        self.assertTrue(nuevo.es_postrado)
        self.assertEqual(nuevo.fecha_nacimiento, date(1950, 2, 1))
        self.assertEqual(Paciente.objects.get(rut="11111111-1").nombres, "Ana")
        self.assertEqual(RecetaCronica.objects.get(folio="R-2").vigencia_meses, 12)
        receta_nueva = RecetaCronica.objects.get(folio="R-3")
        self.assertEqual(receta_nueva.paciente.rut, "12345678-5")
        self.assertEqual((receta_nueva.fecha_emision, receta_nueva.entregas_realizadas), (date(2026, 9, 1), 2))

    def test_deja_la_carga_en_lo_creado_y_modificado(self):
        en_la_base("12345678-5", folio="R-1")
        en_la_base("11111111-1", nombres="Otra")
        carga = self.confirmar(self.preparar(
            linea("12.345.678-5", folio="R-1"),
            linea("11.111.111-1", folio="R-2"),
            linea("22.222.222-2"),
        ))
        self.assertIsNone(Paciente.objects.get(rut="12345678-5").carga)  # sin cambios
        self.assertIsNone(RecetaCronica.objects.get(folio="R-1").carga)  # sin cambios
        self.assertEqual(Paciente.objects.get(rut="11111111-1").carga, carga)
        self.assertEqual(Paciente.objects.get(rut="22222222-2").carga, carga)
        self.assertEqual(RecetaCronica.objects.get(folio="R-2").carga, carga)

    def test_no_toca_lo_que_no_viene_en_el_archivo(self):
        ausente = en_la_base("11111111-1", nombres="Ausente", folio="R-9", realizadas=5)
        self.confirmar(self.preparar(linea("12.345.678-5", folio="R-1")))
        ausente.refresh_from_db()
        self.assertEqual(ausente.nombres, "Ausente")
        self.assertEqual(RecetaCronica.objects.get(folio="R-9").entregas_realizadas, 5)

    def test_dos_confirmaciones_aplican_una_sola_vez(self):
        carga = self.preparar(linea("12.345.678-5", folio="R-1"))
        otra_copia = CargaPadron.objects.get(pk=carga.pk)
        self.confirmar(carga)
        with self.assertRaises(ErrorDeCarga):
            self.confirmar(otra_copia)
        self.assertEqual(Paciente.objects.count(), 1)
        self.assertEqual(RecetaCronica.objects.count(), 1)

    def test_carga_vencida_no_se_aplica_y_queda_descartada(self):
        carga = self.preparar(linea("12.345.678-5", folio="R-1"))
        CargaPadron.objects.filter(pk=carga.pk).update(creada_en=timezone.now() - timedelta(minutes=61))
        with self.assertRaises(ErrorDeCarga) as contexto:
            self.confirmar(carga)
        self.assertIn("se descartó", str(contexto.exception))
        carga.refresh_from_db()
        self.assertEqual(carga.estado, EstadoCarga.DESCARTADA)
        self.assertIsNone(carga.filas_validas)
        self.assertFalse(Paciente.objects.exists())

    def test_carga_cancelada_no_se_puede_confirmar(self):
        carga = cancelar_carga(self.preparar(linea("12.345.678-5", folio="R-1")))
        self.assertEqual(carga.estado, EstadoCarga.CANCELADA)
        self.assertIsNone(carga.filas_validas)
        with self.assertRaises(ErrorDeCarga):
            self.confirmar(carga)
        self.assertFalse(Paciente.objects.exists())

    def test_solo_se_cancela_una_carga_pendiente(self):
        carga = self.confirmar(self.preparar(linea("12.345.678-5", folio="R-1")))
        with self.assertRaises(ErrorDeCarga):
            cancelar_carga(carga)
        carga.refresh_from_db()
        self.assertEqual(carga.estado, EstadoCarga.APLICADA)

    def test_el_contador_nunca_baja_y_deja_advertencia(self):
        en_la_base("12345678-5", folio="R-1", realizadas=4)
        carga = self.confirmar(self.preparar(
            linea("12.345.678-5", folio="R-1", receta=("01-09-2026", 12, 6, 2))
        ))
        receta = RecetaCronica.objects.get(folio="R-1")
        self.assertEqual((receta.vigencia_meses, receta.entregas_realizadas), (12, 4))
        self.assertEqual(len(carga.advertencias), 1)

    def test_el_contador_sube_si_el_archivo_trae_mas(self):
        en_la_base("12345678-5", folio="R-1", realizadas=1)
        self.confirmar(self.preparar(linea("12.345.678-5", folio="R-1")))
        self.assertEqual(RecetaCronica.objects.get(folio="R-1").entregas_realizadas, 2)

    def test_respeta_una_entrega_registrada_entre_la_vista_previa_y_la_confirmacion(self):
        en_la_base("12345678-5", folio="R-1", realizadas=1)
        carga = self.preparar(linea("12.345.678-5", folio="R-1", receta=("01-09-2026", 12, 6, 2)))
        RecetaCronica.objects.filter(folio="R-1").update(entregas_realizadas=3)
        self.confirmar(carga)
        self.assertEqual(RecetaCronica.objects.get(folio="R-1").entregas_realizadas, 3)

    def test_revalida_contra_la_base_al_confirmar(self):
        carga = self.preparar(linea("12.345.678-5", folio="R-1"), linea("22.222.222-2", folio="R-2"))
        en_la_base("11111111-1", folio="R-1")  # otra carga u otro cambio entre medio
        carga = self.confirmar(carga)
        self.assertEqual([r["fila"] for r in carga.rechazos], [2])
        self.assertEqual(carga.filas_rechazadas, 1)
        self.assertFalse(Paciente.objects.filter(rut="12345678-5").exists())
        self.assertTrue(RecetaCronica.objects.filter(folio="R-2").exists())

    def test_receta_con_folio_nuevo_desbloquea_al_paciente(self):
        en_la_base("12345678-5", folio="R-1", realizadas=6)  # agotada: 6 de 6
        self.assertEqual(emitir_turno("12345678-5").tipo, TipoResultado.BLOQUEADO)
        self.confirmar(self.preparar(
            linea("12.345.678-5", folio="R-1", receta=("01-09-2026", 6, 6, 6)),
            linea("12.345.678-5", folio="R-2", receta=("15-10-2026", 6, 6, 0)),
        ))
        resultado = emitir_turno("12345678-5")
        self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertEqual(resultado.turno.receta.folio, "R-2")

    def test_si_falla_la_escritura_no_queda_nada_y_vuelve_a_pendiente(self):
        en_la_base("11111111-1", nombres="Otra", folio="R-9")
        carga = self.preparar(linea("12.345.678-5", folio="R-1"), linea("11.111.111-1", folio="R-9"))
        with mock.patch.object(RecetaCronica.objects, "bulk_create", side_effect=RuntimeError("disco lleno")):
            with self.assertRaises(RuntimeError):
                self.confirmar(carga)
        self.assertFalse(Paciente.objects.filter(rut="12345678-5").exists())
        self.assertEqual(Paciente.objects.get(rut="11111111-1").nombres, "Otra")
        carga.refresh_from_db()
        self.assertEqual(carga.estado, EstadoCarga.PENDIENTE)
        self.assertIsNotNone(carga.filas_validas)
        self.confirmar(carga)  # se puede volver a intentar
        self.assertTrue(Paciente.objects.filter(rut="12345678-5").exists())


class DescartarCargasVencidasTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("9876543-3", Rol.QF)

    def test_descarta_solo_las_pendientes_vencidas(self):
        vieja = preparar_carga(csv_de(linea("12.345.678-5", folio="R-1")), self.qf)
        reciente = preparar_carga(csv_de(linea("12.345.678-5", folio="R-1")), self.qf)
        aplicada = confirmar_carga(preparar_carga(csv_de(linea("11.111.111-1")), self.qf), self.qf)
        hace_dos_horas = timezone.now() - timedelta(hours=2)
        CargaPadron.objects.filter(pk__in=[vieja.pk, aplicada.pk]).update(creada_en=hace_dos_horas)

        self.assertEqual(descartar_cargas_vencidas(), 1)
        estados = dict(CargaPadron.objects.values_list("pk", "estado"))
        self.assertEqual(estados[vieja.pk], EstadoCarga.DESCARTADA)
        self.assertEqual(estados[reciente.pk], EstadoCarga.PENDIENTE)
        self.assertEqual(estados[aplicada.pk], EstadoCarga.APLICADA)
        self.assertIsNone(CargaPadron.objects.get(pk=vieja.pk).filas_validas)


class GenerarPadronSinteticoTests(TestCase):
    def setUp(self):
        self.qf = crear_usuario("9876543-3", Rol.QF)
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.carpeta = Path(carpeta.name)

    def generar(self, nombre, **opciones):
        ruta = self.carpeta / nombre
        call_command("generar_padron_sintetico", salida=str(ruta), stdout=io.StringIO(), **opciones)
        return ruta

    def preparar(self, ruta):
        return preparar_carga(SimpleUploadedFile(ruta.name, ruta.read_bytes()), self.qf)

    def test_rechaza_exactamente_las_filas_invalidas_pedidas(self):
        for extension in ("csv", "xlsx"):
            for invalidas in (0, 7, 13):
                with self.subTest(extension=extension, invalidas=invalidas):
                    ruta = self.generar(f"p{invalidas}.{extension}", pacientes=20, invalidas=invalidas)
                    carga = self.preparar(ruta)
                    self.assertEqual(carga.filas_rechazadas, invalidas)
                    self.assertEqual(carga.pacientes_creados, 20)
                    self.assertEqual(len(carga.filas_validas), carga.filas_totales - invalidas)
                    self.assertEqual(carga.recetas_creadas, len(carga.filas_validas))

    def test_cubre_los_motivos_1_a_6(self):
        carga = self.preparar(self.generar("p.csv", pacientes=5, invalidas=8))
        motivos = " ".join(rechazo["motivo"] for rechazo in carga.rechazos)
        for texto in ("dígito verificador", "fecha válida", "Receta incompleta", "superan",
                      "Datos del paciente distintos", "se repite"):
            self.assertIn(texto, motivos)

    def test_proporcion_de_postrados_y_mayores_de_80(self):
        carga = self.preparar(self.generar("p.csv", pacientes=67, invalidas=0))
        confirmar_carga(carga, self.qf)
        pacientes = list(Paciente.objects.all())
        self.assertEqual(len(pacientes), 67)
        self.assertEqual(sum(p.es_postrado for p in pacientes), 7)
        self.assertTrue(all(p.edad > 80 for p in pacientes if not p.es_postrado))
        self.assertTrue(all(p.es_despacho_domicilio for p in pacientes))
        self.assertTrue(all(r.es_utilizable for r in RecetaCronica.objects.all()))
        self.assertTrue(all(r.folio.startswith("SIN-") for r in RecetaCronica.objects.all()))

    def test_la_misma_semilla_produce_el_mismo_archivo(self):
        for extension in ("csv", "xlsx"):
            with self.subTest(extension=extension):
                primero = self.generar(f"a.{extension}", pacientes=30, semilla=1).read_bytes()
                segundo = self.generar(f"b.{extension}", pacientes=30, semilla=1).read_bytes()
                otra = self.generar(f"c.{extension}", pacientes=30, semilla=2).read_bytes()
                self.assertEqual(primero, segundo)
                self.assertNotEqual(primero, otra)

    def test_no_choca_con_los_datos_de_demostracion(self):
        call_command("cargar_datos_demo", stdout=io.StringIO())
        carga = self.preparar(self.generar("p.csv", pacientes=50, invalidas=0))
        self.assertEqual((carga.filas_rechazadas, carga.pacientes_actualizados), (0, 0))

    def test_extension_no_admitida(self):
        with self.assertRaises(CommandError):
            self.generar("p.txt")
