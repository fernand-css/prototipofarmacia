import io
import random
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cuentas.validators import calcular_dv
from turnos.importacion import COLUMNAS, csv_para_excel
from turnos.models import sumar_meses

# Proporción del informe: unos 70 pacientes postrados y 600 mayores de 80 años.
POSTRADOS_POR_CADA_670 = 70
# Cuerpos de RUT sintéticos: lejos de los de cargar_datos_demo (10.000.001 a 10.000.010).
RANGO_RUT = (20_000_000, 21_000_000)
NOMBRES = [
    "Ana", "Inés", "José", "María", "Raúl", "Sofía", "Héctor", "Rosa", "Óscar", "Lucía",
    "Ramón", "Elena", "Tomás", "Begoña", "Andrés", "Teresa", "Julián", "Pía", "Germán", "Nélida",
]
APELLIDOS = [
    "Muñoz", "Peña", "Núñez", "Rojas", "González", "Díaz", "Pérez", "Soto", "Contreras", "Silva",
    "Martínez", "Sepúlveda", "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Araya",
    "Castillo", "Ibáñez",
]
# Motivos de rechazo que se generan a propósito (los de validar_filas). Los dos últimos producen
# dos filas rechazadas cada uno: el conflicto necesita dos filas.
MOTIVOS_DE_UNA_FILA = ("rut", "formato", "receta_incompleta", "entregas_sobre_maximo")
MOTIVOS_DE_DOS_FILAS = ("datos_distintos", "folio_repetido")
# Fecha fija dentro del .xlsx: openpyxl guarda la hora de creación, y con ella dos archivos de
# la misma semilla serían distintos.
FECHA_FIJA_XLSX = datetime(2026, 1, 1)


class Generador:
    def __init__(self, semilla, hoy):
        self.azar = random.Random(semilla)
        self.hoy = hoy
        self.cuerpos = iter(self.azar.sample(range(*RANGO_RUT), 100_000))
        self.folios = 0

    def rut(self):
        cuerpo = str(next(self.cuerpos))
        return f"{int(cuerpo):,}".replace(",", ".") + f"-{calcular_dv(cuerpo)}"

    def folio(self):
        self.folios += 1
        return f"SIN-{self.folios:06d}"

    def paciente(self, postrado):
        edad = self.azar.randint(45, 95) if postrado else self.azar.randint(81, 99)
        nacimiento = sumar_meses(self.hoy, -12 * edad) - timedelta(days=self.azar.randint(1, 360))
        return {
            "rut": self.rut(),
            "nombres": self.azar.choice(NOMBRES),
            "apellidos": f"{self.azar.choice(APELLIDOS)} {self.azar.choice(APELLIDOS)}",
            "fecha_nacimiento": nacimiento.strftime("%d-%m-%Y"),
            "discapacidad": "si" if postrado and self.azar.random() < 0.3 else "no",
            "embarazada": "no",
            "postrado": "si" if postrado else "no",
        }

    def receta(self):
        """Una receta vigente: emitida hace menos meses que su vigencia, con entregas por delante."""
        vigencia = self.azar.choice((6, 12))
        meses = self.azar.randint(0, vigencia - 1)
        maximas = vigencia
        return {
            "folio": self.folio(),
            "fecha_emision": sumar_meses(self.hoy, -meses).strftime("%d-%m-%Y"),
            "vigencia_meses": str(vigencia),
            "entregas_maximas": str(maximas),
            "entregas_realizadas": str(min(meses, maximas - 1)),
        }

    def filas_validas(self, cantidad):
        postrados = round(cantidad * POSTRADOS_POR_CADA_670 / 670)
        filas = []
        for indice in range(cantidad):
            paciente = self.paciente(postrado=indice < postrados)
            for _ in range(self.azar.randint(1, 2)):
                filas.append({**paciente, **self.receta()})
        return filas

    def filas_invalidas(self, cantidad):
        """Exactamente `cantidad` filas que validar_filas rechaza, repartidas entre los motivos."""
        filas = []
        motivos = list(MOTIVOS_DE_UNA_FILA + MOTIVOS_DE_DOS_FILAS)
        indice = 0
        while len(filas) < cantidad:
            motivo = motivos[indice % len(motivos)]
            indice += 1
            if motivo in MOTIVOS_DE_DOS_FILAS and cantidad - len(filas) < 2:
                continue
            filas.extend(self.invalida(motivo))
        return filas

    def invalida(self, motivo):
        fila = {**self.paciente(postrado=False), **self.receta()}
        if motivo == "rut":
            cuerpo, dv = fila["rut"].split("-")
            fila["rut"] = f"{cuerpo}-{'0' if dv != '0' else '1'}"
        elif motivo == "formato":
            fila["fecha_nacimiento"] = "31-02-1950"
        elif motivo == "receta_incompleta":
            fila["fecha_emision"] = ""
        elif motivo == "entregas_sobre_maximo":
            fila["entregas_realizadas"] = str(int(fila["entregas_maximas"]) + 1)
        elif motivo == "datos_distintos":
            return [fila, {**fila, "nombres": fila["nombres"] + " Segunda", "folio": self.folio()}]
        elif motivo == "folio_repetido":
            return [fila, {**self.paciente(postrado=False), **self.receta(), "folio": fila["folio"]}]
        return [fila]


def escribir_xlsx(filas):
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Padrón"
    for fila in filas:
        hoja.append(list(fila))
    libro.properties.created = libro.properties.modified = FECHA_FIJA_XLSX
    crudo = io.BytesIO()
    libro.save(crudo)

    # Se reescribe el zip con una fecha fija en cada entrada y en las propiedades del libro
    # (openpyxl pone la hora actual al guardar), para que la salida sea reproducible.
    salida = io.BytesIO()
    with zipfile.ZipFile(crudo) as origen, zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as destino:
        for entrada in origen.infolist():
            contenido = origen.read(entrada.filename)
            if entrada.filename == "docProps/core.xml":
                contenido = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>" + FECHA_FIJA_XLSX.strftime("%Y-%m-%dT%H:%M:%SZ").encode() + rb"\g<2>",
                    contenido,
                )
            info = zipfile.ZipInfo(entrada.filename, date_time=FECHA_FIJA_XLSX.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            destino.writestr(info, contenido)
    return salida.getvalue()


class Command(BaseCommand):
    help = (
        "Escribe un padrón sintético (.csv o .xlsx) para probar la importación: pacientes postrados "
        "y mayores de 80 años con 1 o 2 recetas vigentes, más filas inválidas a propósito. "
        "Con la misma semilla, el mismo día, produce el mismo archivo. No contiene datos reales."
    )

    def add_arguments(self, parser):
        parser.add_argument("--salida", required=True, help="Ruta del archivo, terminada en .csv o .xlsx.")
        parser.add_argument("--pacientes", type=int, default=670, help="Pacientes válidos (670 por defecto).")
        parser.add_argument("--invalidas", type=int, default=10, help="Filas que se deben rechazar (10).")
        parser.add_argument("--semilla", type=int, default=1, help="Semilla del azar (1 por defecto).")

    def handle(self, *args, salida, pacientes, invalidas, semilla, **opciones):
        ruta = Path(salida)
        extension = ruta.suffix.lower()
        if extension not in (".csv", ".xlsx"):
            raise CommandError("La salida debe terminar en .csv o .xlsx.")
        if pacientes < 0 or invalidas < 0:
            raise CommandError("--pacientes e --invalidas no pueden ser negativos.")

        generador = Generador(semilla, timezone.localdate())
        validas = generador.filas_validas(pacientes)
        filas = validas + generador.filas_invalidas(invalidas)
        generador.azar.shuffle(filas)
        tabla = [COLUMNAS, *([fila[columna] for columna in COLUMNAS] for fila in filas)]

        if extension == ".csv":
            ruta.write_bytes(csv_para_excel(tabla).encode("utf-8"))
        else:
            ruta.write_bytes(escribir_xlsx(tabla))
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {ruta} con {pacientes} pacientes sintéticos ({len(validas)} filas válidas) "
            f"y {invalidas} filas inválidas a propósito."
        ))
