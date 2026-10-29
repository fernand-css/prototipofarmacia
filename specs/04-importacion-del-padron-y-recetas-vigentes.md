# SPEC 04 — Importación del padrón y recetas vigentes

> **Estado:** Implementado
> **Depende de:** SPEC 01 y SPEC 02
> **Fecha:** 2026-10-28
> **Objetivo:** Permitir que la QF cargue desde un archivo CSV o Excel exportado de Rayén el padrón de pacientes crónicos y postrados con sus recetas vigentes, con vista previa, reporte de filas rechazadas y bitácora, y que el técnico vea en qué entrega va cada receta.

---

## Por qué existe este spec

Hoy los pacientes y sus recetas crónicas solo entran al sistema con `cargar_datos_demo` o digitándolos uno a uno en el admin de Django. Sin integración con Rayén, eso obliga a escribir cada receta en dos sistemas. El informe agregó la historia **HU-23** (importación del padrón y recetas vigentes, Must) y el requerimiento **RNF-07** (interoperabilidad con Rayén por archivos, ligado a HU-23 y HU-21). Este spec implementa los dos.

También cierra **HU-21** (control de entregas parciales de receta crónica). El SPEC 02 dejó el contador de entregas, el bloqueo del tótem con receta vencida o agotada y la suma de una entrega al finalizar la atención. Faltaban dos cosas:

- **Registrar una renovación médica.** El SPEC 02 la dejaba en el admin. Con este spec, una receta renovada en Rayén llega como receta nueva (con otro folio) en la siguiente carga, y el tótem vuelve a emitir turno.
- **Que el técnico vea en cualquier momento cuántas entregas lleva y le quedan a una receta.** Hoy el panel solo muestra la insignia «Crónico».

**Numeración.** El SPEC 03 enviaba al SPEC 04 «o posteriores» la estimación de espera (HU-18), los preparados pendientes de retiro (HU-17) y las mermas (HU-20). Las tres dependen de registrar cuándo una receta queda preparada, un estado que hoy no existe en `Turno`, así que van juntas en un spec posterior. Este 04 trata solo las recetas y el padrón, que esos specs y el reparto a domicilio también necesitan. El SPEC 03 no se edita. El cambio queda registrado aquí y en `CLAUDE.md` al implementar.

**Auditoría previa.** Se hizo al redactar este spec, sin modificar código.

Existente, del SPEC 02, que este spec usa:

- `Paciente` (`rut` único y normalizado en `save()`, `nombres`, `apellidos`, `fecha_nacimiento`, `tiene_discapacidad`, `esta_embarazada`, `es_postrado`) y `RecetaCronica` (`paciente`, `fecha_emision`, `vigencia_meses`, `entregas_maximas`, `entregas_realizadas`, con las propiedades `fecha_vencimiento`, `esta_vencida`, `esta_agotada` y `es_utilizable`).
- `servicios._emitir` asigna al turno la receta utilizable más antigua y bloquea (`BLOQUEADO`) si el paciente tiene recetas y ninguna es utilizable. `finalizar_atencion` suma 1 a `entregas_realizadas` con `F()`.
- `Turno.paciente` y `Turno.receta` son `PROTECT`: un paciente o receta con turnos no se puede borrar.
- `cuentas/validators.py` (`normalizar_rut`, `validar_rut`) y `cuentas.mixins.SoloQF`; `turnos.mixins.SoloAtencion`.

Pendiente, y es lo que hace este spec: el folio de la receta, la lectura y validación del archivo, la carga con vista previa y confirmación, la bitácora, el reporte de rechazos, el generador del padrón sintético, el avance de la receta en el panel y la consulta de recetas por RUT.

Requiere aprobación: ningún cambio a las reglas del SPEC 01 ni del SPEC 02. Cambia una regla de `CLAUDE.md`: «Paciente y receta se administran desde el admin de Django». El admin se mantiene como acceso técnico, pero la carga habitual pasa a ser la importación, que sí es una interfaz de la QF.

El sistema es un **prototipo académico** con datos sintéticos. El archivo imita una exportación de Rayén; no hay conexión con Rayén ni se cargan datos reales.

---

## Alcance

**Dentro:**

- Campo `folio` en `RecetaCronica`, la clave con que Rayén identifica la receta.
- Página `/padron/`, solo para la QF: formulario para subir el archivo, botón para descargar la plantilla y la bitácora de cargas.
- Lectura de archivos `.csv` (separador `;` o `,`, en UTF-8, con o sin BOM, o en Windows-1252) y `.xlsx` (primera hoja), con `openpyxl`.
- Validación del archivo completo: extensión, tamaño (`TURNOS_PADRON_BYTES_MAXIMOS`), cantidad de filas (`TURNOS_PADRON_FILAS_MAXIMAS`) y columnas obligatorias. Si algo de eso falla, se rechaza el archivo entero y no se crea una carga pendiente.
- Validación por fila: RUT con dígito verificador, campos obligatorios, fechas, números, banderas, coherencia de la receta, duplicados dentro del archivo y conflictos con la base. Una fila inválida se rechaza sola y las válidas siguen.
- Vista previa sin escribir pacientes ni recetas: cuántos pacientes y recetas se crean, se actualizan o quedan sin cambios, y el detalle de las filas rechazadas.
- Confirmación: vuelve a validar contra la base, aplica las filas válidas en una transacción y deja el reporte final.
- Cancelación de una carga pendiente, y descarte automático de las que pasan `TURNOS_PADRON_MINUTOS_PENDIENTE` sin confirmar.
- Reporte de filas rechazadas (número de fila, RUT tal como venía y motivo) en pantalla y descargable en CSV.
- Bitácora: cada carga guarda quién la subió, cuándo, el nombre, el tamaño y la huella SHA-256 del archivo, su estado y sus conteos. Los pacientes y recetas guardan cuál fue la última carga que los creó o modificó.
- Regla del contador: al actualizar una receta existente, `entregas_realizadas` queda en el mayor entre el valor local y el del archivo.
- Plantilla CSV descargable con los encabezados y una fila de ejemplo sintética.
- Comando `generar_padron_sintetico`, que escribe un archivo `.csv` o `.xlsx` con 670 pacientes sintéticos (70 postrados y 600 mayores de 80 años) y algunas filas inválidas a propósito.
- Cierre de HU-21: el turno en curso del panel muestra «Entrega N de M» y la fecha de vencimiento si el turno trae receta, y una consulta `/recetas/` (funcionario y QF) busca un RUT y lista sus recetas con su avance y su estado.
- Folios en las recetas de `cargar_datos_demo`.
- Pruebas de Django para la lectura, la validación, la carga, la bitácora, los permisos, el panel y la consulta.
- Actualización de `README.md`, `CLAUDE.md` y `requirements.txt`.

**Fuera de alcance (para specs futuros):**

- Integración por API con Rayén, cargas programadas o automáticas y lectura de archivos desde una carpeta compartida.
- Borrar o desactivar pacientes y recetas que no vienen en una carga. La carga solo crea y actualiza.
- Guardar el archivo subido o reprocesar una carga antigua.
- Direcciones, sectores y referencias de domicilio (HU-12) y todo el módulo de reparto (HU-13 a HU-16, HU-19, HU-22).
- Estimación de espera (HU-18), preparados pendientes de retiro (HU-17) y mermas (HU-20).
- Editar una receta o registrar una renovación a mano desde una pantalla de la QF. Para casos puntuales sigue el admin.
- Formatos `.xls` (Excel antiguo), `.ods` y hojas distintas de la primera.
- Deshacer una carga ya aplicada.
- El bloqueo temporal tras intentos fallidos de login que declara el SPEC 01.

---

## Modelo de datos

Cambios en `turnos/models.py` y una migración `0003`:

```python
class EstadoCarga(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente de confirmar"
    APLICANDO = "aplicando", "Aplicándose"
    APLICADA = "aplicada", "Aplicada"
    CANCELADA = "cancelada", "Cancelada"
    DESCARTADA = "descartada", "Descartada por tiempo"


class CargaPadron(models.Model):
    """Bitácora de una importación del padrón y sus recetas (HU-23)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cargas_padron")
    creada_en = models.DateTimeField("subida en", default=timezone.now)
    aplicada_en = models.DateTimeField("aplicada en", null=True, blank=True)
    estado = models.CharField("estado", max_length=12, choices=EstadoCarga.choices, default=EstadoCarga.PENDIENTE)

    nombre_archivo = models.CharField("archivo", max_length=255)
    bytes_archivo = models.PositiveIntegerField("tamaño (bytes)")
    huella_archivo = models.CharField("SHA-256", max_length=64)

    filas_totales = models.PositiveIntegerField("filas", default=0)
    filas_rechazadas = models.PositiveIntegerField("filas rechazadas", default=0)
    pacientes_creados = models.PositiveIntegerField(default=0)
    pacientes_actualizados = models.PositiveIntegerField(default=0)
    pacientes_sin_cambios = models.PositiveIntegerField(default=0)
    recetas_creadas = models.PositiveIntegerField(default=0)
    recetas_actualizadas = models.PositiveIntegerField(default=0)
    recetas_sin_cambios = models.PositiveIntegerField(default=0)

    # Filas válidas ya normalizadas; existe solo mientras la carga está pendiente.
    filas_validas = models.JSONField(null=True, blank=True)
    # [{"fila": 12, "rut": "12.345.678-9", "motivo": "..."}], se conserva siempre.
    rechazos = models.JSONField(default=list)
    # [{"fila": 30, "folio": "R-000123", "mensaje": "..."}], por ejemplo el contador local mayor que el de Rayén.
    advertencias = models.JSONField(default=list)

    class Meta:
        ordering = ["-creada_en"]
```

En `Paciente` y `RecetaCronica` se agrega la última carga que los creó o modificó:

```python
carga = models.ForeignKey(
    "CargaPadron", null=True, blank=True, on_delete=models.SET_NULL,
    related_name="+", verbose_name="última carga",
)
```

En `RecetaCronica`:

```python
folio = models.CharField("folio Rayén", max_length=20, unique=True, null=True, blank=True)
```

`folio` es nulo para las recetas creadas antes de este spec o a mano en el admin. La importación siempre lo exige. Como es `unique` y nulo, varias recetas sin folio pueden convivir.

**Columnas del archivo.** La primera fila son los encabezados. Se comparan sin distinguir mayúsculas, tildes ni espacios a los lados, y las columnas extra se ignoran.

| Columna | Obligatoria | Formato |
| --- | --- | --- |
| `rut` | Sí | Con o sin puntos y guion; se normaliza con `normalizar_rut` y se valida con `validar_rut`. |
| `nombres` | Sí | Texto, hasta 100 caracteres. |
| `apellidos` | Sí | Texto, hasta 100 caracteres. |
| `fecha_nacimiento` | Sí | `dd-mm-aaaa`, `dd/mm/aaaa` o `aaaa-mm-dd`, o celda de fecha en Excel. No puede ser futura. |
| `discapacidad` | No | `si`, `sí`, `no`, `1`, `0` o vacía (vacía = no). |
| `embarazada` | No | Igual que `discapacidad`. |
| `postrado` | No | Igual que `discapacidad`. |
| `folio` | Si hay receta | Texto, hasta 20 caracteres, sin espacios. |
| `fecha_emision` | Si hay receta | Mismo formato que `fecha_nacimiento`. No puede ser futura. |
| `vigencia_meses` | Si hay receta | Entero de 1 a 24. |
| `entregas_maximas` | Si hay receta | Entero de 1 a 24. |
| `entregas_realizadas` | No | Entero de 0 a `entregas_maximas`; vacía = 0. |

Las columnas obligatorias del encabezado son `rut`, `nombres`, `apellidos`, `fecha_nacimiento`, `folio`, `fecha_emision`, `vigencia_meses` y `entregas_maximas`. Cada fila trae un paciente y, como máximo, una receta. Un paciente con dos recetas viene en dos filas. Un paciente sin receta viene con las cuatro columnas de receta vacías. Si alguna viene llena y otra vacía, la fila se rechaza.

**Reglas de la carga:**

- El paciente se identifica por RUT normalizado y la receta por `folio`.
- Una fila crea el paciente si el RUT no existe, lo actualiza si algún campo cambió y lo cuenta «sin cambios» si es igual. Lo mismo con la receta.
- Al actualizar una receta, el archivo manda en `fecha_emision`, `vigencia_meses` y `entregas_maximas`. `entregas_realizadas` queda en `max(local, archivo)`. Si el local es mayor, se agrega una advertencia y la receta no cuenta como actualizada por ese solo motivo.
- Una receta nueva toma `entregas_realizadas` del archivo, o 0 si viene vacía.
- La renovación médica es una receta con folio nuevo. La anterior queda como está (vencida o agotada), y el tótem usa la nueva porque es utilizable.
- Pacientes y recetas que no vienen en el archivo no se tocan.

**Motivos de rechazo de una fila.** Cada fila rechazada lleva un solo motivo, el primero que falla, en este orden:

1. RUT vacío o con dígito verificador inválido.
2. Campo obligatorio vacío, texto demasiado largo, fecha, número o bandera con formato inválido, o valor fuera de rango.
3. Receta incompleta (algunas columnas de receta llenas y otras vacías).
4. `entregas_realizadas` mayor que `entregas_maximas`.
5. El mismo RUT aparece en otras filas con datos de paciente distintos. Se rechazan todas las filas de ese RUT, y el motivo nombra las filas en conflicto.
6. El mismo folio aparece en otra fila del archivo. Se rechazan todas las filas con ese folio.
7. El folio ya existe en la base para otro RUT.

Varias filas del mismo RUT con datos de paciente iguales y folios distintos son normales: son varias recetas del mismo paciente.

**Ciclo de una carga:**

- `pendiente`: se crea al subir un archivo que pasa la validación del archivo completo. Guarda `filas_validas`, `rechazos` y los conteos previstos.
- `aplicando`: estado transitorio al confirmar. Se toma con un `UPDATE` condicional sobre `estado = 'pendiente'` (el mismo patrón del SPEC 02), así dos confirmaciones simultáneas no aplican la carga dos veces.
- `aplicada`: escritura terminada. Los conteos pasan a ser los reales y `filas_validas` se vacía.
- `cancelada`: la QF la canceló. `filas_validas` se vacía.
- `descartada`: pasó `TURNOS_PADRON_MINUTOS_PENDIENTE` sin confirmarse. Se descarta al abrir `/padron/` o al intentar confirmarla, y `filas_validas` se vacía.

Un archivo rechazado entero (sin columnas obligatorias, demasiado grande, ilegible) no crea un `CargaPadron`: no hay filas que guardar y el error se muestra al momento.

**Constantes nuevas** al final de `settings.py`:

```python
TURNOS_PADRON_BYTES_MAXIMOS = 5 * 1024 * 1024
TURNOS_PADRON_FILAS_MAXIMAS = 5000           # sin contar el encabezado
TURNOS_PADRON_MINUTOS_PENDIENTE = 60
```

**Rutas nuevas** en `turnos/urls.py`:

| Ruta | Método | Acceso | Nombre |
| --- | --- | --- | --- |
| `/padron/` | GET, POST | QF | `turnos:padron` |
| `/padron/plantilla/` | GET | QF | `turnos:padron_plantilla` |
| `/padron/<pk>/` | GET | QF | `turnos:padron_carga` |
| `/padron/<pk>/confirmar/` | POST | QF | `turnos:padron_confirmar` |
| `/padron/<pk>/cancelar/` | POST | QF | `turnos:padron_cancelar` |
| `/padron/<pk>/rechazos.csv` | GET | QF | `turnos:padron_rechazos` |
| `/recetas/` | GET, POST | Funcionario y QF | `turnos:recetas` |

---

## Plan de implementación

1. **Dependencia y modelo.** Agregar `openpyxl` y su dependencia `et-xmlfile` a `requirements.txt`, con versiones fijas. Agregar `EstadoCarga`, `CargaPadron`, `RecetaCronica.folio` y la FK `carga` en `Paciente` y `RecetaCronica`, con la migración `0003`. Registrar `CargaPadron` en `turnos/admin.py` como solo lectura, y mostrar y buscar `folio` en el admin de recetas. En `cargar_datos_demo`, dar un folio `DEMO-NNN` a cada receta sin cambiar su idempotencia. **Verificación:** `migrate` aplica sin errores sobre una base con datos de demostración; dos recetas sin folio conviven y dos con el mismo folio no; `cargar_datos_demo` dos veces seguidas deja las mismas filas y todas sus recetas con folio; la suite existente pasa.

2. **Lectura del archivo.** En un módulo nuevo `turnos/importacion.py`, escribir `leer_archivo(archivo)`, que devuelve los encabezados normalizados y las filas como diccionarios de texto, con su número de fila (el encabezado es la fila 1, como en Excel). CSV: detecta UTF-8 (con o sin BOM) y si no Windows-1252, y elige `;` o `,` mirando el encabezado. XLSX: `openpyxl.load_workbook(read_only=True, data_only=True)`, primera hoja, fechas convertidas a `aaaa-mm-dd`, y se detiene al pasar el máximo de filas. Lanza `ErrorDeArchivo` con un mensaje legible si la extensión no es `.csv` ni `.xlsx`, el archivo pesa más del máximo, no se puede leer, viene vacío, pasa el máximo de filas o le faltan columnas obligatorias (nombrándolas). Las filas completamente vacías se ignoran. **Verificación:** `turnos/tests/test_importacion.py` cubre CSV con `;` y con `,`, en UTF-8 con BOM y en Windows-1252 con tildes y «ñ», XLSX generado en memoria con celdas de fecha, encabezados con mayúsculas y tildes, columnas extra, filas vacías y cada causa de `ErrorDeArchivo`.

3. **Validación de filas.** En `turnos/importacion.py`, escribir `validar_filas(filas)`, una función pura que no consulta la base. Devuelve las filas válidas normalizadas (RUT normalizado, fechas ISO, enteros, booleanos) y los rechazos con los motivos 1 a 6 de la sección anterior, en ese orden. **Verificación:** pruebas de cada motivo, de un RUT con puntos y otro sin puntos que son el mismo paciente, de varias recetas del mismo paciente aceptadas, de las filas de un RUT con datos distintos rechazadas todas y de un folio repetido rechazado en todas sus filas.

4. **Preparar la carga (vista previa).** Escribir `preparar_carga(archivo, usuario)`: lee, valida, compara contra la base sin escribir pacientes ni recetas (rechaza el motivo 7 y calcula creados, actualizados, sin cambios y advertencias del contador) y crea el `CargaPadron` en `pendiente` con `filas_validas`, `rechazos`, `advertencias`, los conteos previstos, el nombre, el tamaño y la huella SHA-256. Las consultas a la base se hacen por lotes (`rut__in`, `folio__in`), no una por fila. **Verificación:** tras `preparar_carga` no cambia la cantidad de `Paciente` ni de `RecetaCronica`; los conteos previstos coinciden con un archivo conocido; un folio de la base asignado a otro RUT queda rechazado.

5. **Confirmar y cancelar.** Escribir `confirmar_carga(carga, usuario)` y `cancelar_carga(carga)`. Confirmar toma la carga con `UPDATE ... WHERE estado = 'pendiente'`. Si la carga venció, la descarta y lanza `ErrorDeCarga`. Dentro de `transaction.atomic()` vuelve a comparar contra la base (otra carga pudo cambiarla, y lo que ahora choca pasa a `rechazos`), crea y actualiza con `bulk_create` y `bulk_update`, aplica la regla del contador, deja `carga` en cada paciente y receta tocados, guarda los conteos reales, vacía `filas_validas` y queda en `aplicada` con `aplicada_en`. Ante cualquier excepción la transacción se revierte y la carga vuelve a `pendiente`. Cancelar solo acepta cargas `pendiente`. Escribir también `descartar_cargas_vencidas()`. **Verificación:** pruebas de que confirmar crea y actualiza lo previsto; de que dos confirmaciones seguidas aplican una sola vez; de que una carga vencida no se aplica; de que una carga cancelada no se puede confirmar; de que el contador nunca baja y produce la advertencia; de que una receta con folio nuevo desbloquea al paciente en `emitir_turno`; y de que, si falla la escritura a mitad de camino (forzado en la prueba), no queda ningún paciente ni receta escritos.

6. **Pantallas de la QF.** Escribir el formulario de subida en `turnos/forms.py` y las vistas con `SoloQF`: `/padron/` (subir el archivo, enlace a la plantilla y bitácora como `.lista` con fecha, usuario, archivo, estado en una insignia con texto y conteos; cada fila enlaza a su carga), `/padron/<pk>/` (si está pendiente: conteos previstos, rechazos, advertencias y los botones «Aplicar carga» y «Cancelar», ambos con el modal de confirmación; si no: el reporte final), `/padron/<pk>/confirmar/`, `/padron/<pk>/cancelar/`, `/padron/<pk>/rechazos.csv` y `/padron/plantilla/`. El CSV de rechazos usa `;`, va en UTF-8 con BOM (para que Excel muestre bien las tildes) y antepone `'` a toda celda que empiece con `=`, `+`, `-` o `@`. Agregar «Padrón» a la barra de la QF en `base.html` y las reglas en su sección de `estilos.css`. **Verificación:** `turnos/tests/test_padron.py` cubre las redirecciones al login sin sesión, el 403 para funcionario y Encargado de Terreno en cada ruta, el flujo completo subir → vista previa → aplicar, cancelar, el error de un archivo sin columnas (sin crear carga), la descarga de la plantilla (que al subirla da una carga sin rechazos) y la neutralización de fórmulas en el CSV de rechazos.

7. **Padrón sintético.** Escribir `turnos/management/commands/generar_padron_sintetico.py`: `--salida <ruta.csv|ruta.xlsx>`, `--pacientes 670`, `--invalidas 10` y `--semilla`. Genera 70 postrados y 600 mayores de 80 años (o la misma proporción si cambia `--pacientes`), con RUT válidos por módulo 11 en un rango que no choca con `cargar_datos_demo`, nombres inventados, entre 1 y 2 recetas por paciente con folio `SIN-NNNNNN`, y las filas inválidas repartidas entre los motivos 1 a 6. Con la misma semilla produce el mismo archivo. **Verificación:** una prueba genera un archivo pequeño y comprueba que `preparar_carga` rechaza exactamente las filas inválidas pedidas; a mano, el archivo de 670 pacientes se carga y se mide (ver Registro de verificación).

8. **Avance de la receta (HU-21).** Agregar a `RecetaCronica` las propiedades `entrega_en_curso` (`entregas_realizadas + 1`, hasta `entregas_maximas`) y `entregas_restantes`. En `_turno_actual.html`, si el turno trae receta, mostrar «Entrega N de M» y «Vence el dd-mm-aaaa» junto a la insignia «Crónico», sin cambiar la forma de ticket ni el papel de turno. Escribir `/recetas/` con `SoloAtencion`: un formulario con el RUT (validado con los validadores del SPEC 01) que se envía por POST, y como resultado el nombre del paciente y una `.lista` de sus recetas con folio, fecha de emisión, vencimiento, «N de M entregas realizadas», cuántas quedan y una insignia con texto («Vigente», «Agotada», «Vencida»). Un RUT sin paciente muestra «No hay recetas registradas para este RUT». Agregar «Recetas» a la barra del funcionario y de la QF. **Verificación:** `turnos/tests/test_recetas.py` cubre el acceso por rol, la búsqueda con y sin puntos, un RUT inválido, un RUT sin paciente, los tres estados de la receta y que el RUT no aparece en la URL; `test_atencion.py` comprueba que el turno en curso con receta muestra «Entrega 3 de 6» cuando `entregas_realizadas` es 2.

9. **Documentación y registro.** En `README.md`: las rutas `/padron/` y `/recetas/`, el formato del archivo, la plantilla, `generar_padron_sintetico` y el flujo de demostración (generar → subir → revisar → aplicar → sacar turno en el tótem → ver «Entrega N de M» en el panel). En `CLAUDE.md`: la importación, `turnos/importacion.py`, el folio, la regla del contador, la nueva regla sobre la administración de pacientes y recetas y la numeración de specs. Completar el Registro de verificación de este spec. **Verificación:** una persona del equipo sigue el README desde cero y aplica el padrón sintético.

---

## Criterios de aceptación

Regresión de los SPEC 01, 02 y 03:

- [x] `python manage.py test` pasa completo, incluidas las pruebas existentes de `cuentas` y `turnos`.
- [x] `node --test "pruebas_js/*.test.js"` sigue pasando.
- [x] No cambian `turnos/motor.py` ni las funciones de emisión, llamado y atención de `turnos/servicios.py`.
- [x] El tótem sigue bloqueando a un paciente con recetas y ninguna utilizable, y finalizar una atención con receta sigue sumando exactamente 1.
- [x] `/sala/estado/` mantiene exactamente su contrato de claves.

Archivo:

- [x] Se aceptan `.csv` con `;` y con `,`, en UTF-8 (con y sin BOM) y en Windows-1252, y `.xlsx`.
- [x] Un archivo con otra extensión, de más de 5 MB, con más de 5.000 filas o sin alguna columna obligatoria se rechaza entero con un mensaje que nombra la causa (y las columnas que faltan), sin crear un `CargaPadron`.
- [x] Los encabezados se reconocen sin importar mayúsculas, tildes ni espacios, y las columnas extra se ignoran.

Validación:

- [x] Una fila con un RUT de dígito verificador inválido se rechaza con un motivo que lo dice, y las demás filas siguen.
- [x] `12.345.678-5` y `123456785` en dos filas con los mismos datos y folios distintos dan un solo paciente con dos recetas.
- [x] Dos filas con el mismo RUT y otro nombre o fecha de nacimiento se rechazan las dos, y el motivo nombra ambas filas.
- [x] Dos filas con el mismo folio se rechazan las dos.
- [x] Un folio que ya existe en la base para otro RUT se rechaza.
- [x] Una fila con la receta incompleta, o con `entregas_realizadas` mayor que `entregas_maximas`, se rechaza.
- [x] Una fila de paciente sin columnas de receta se acepta y no crea receta.

Carga:

- [x] Subir un archivo válido no modifica `Paciente` ni `RecetaCronica` hasta confirmar.
- [x] La vista previa muestra los mismos conteos que deja la carga al aplicarse, si la base no cambió entre medio.
- [x] Confirmar crea los pacientes y recetas nuevos, actualiza los cambiados y no toca los que no vienen en el archivo.
- [x] Confirmar dos veces la misma carga la aplica una sola vez.
- [x] Una carga pendiente de más de 60 minutos no se puede aplicar y queda `descartada`.
- [x] Una carga cancelada o descartada no guarda `filas_validas`.
- [x] Si la escritura falla a mitad de camino, no queda ningún paciente ni receta de esa carga y la carga vuelve a `pendiente`.
- [x] Al actualizar una receta, `entregas_realizadas` nunca baja, y cuando el valor local es mayor queda una advertencia.
- [x] Un paciente bloqueado en el tótem por receta agotada recibe turno después de aplicar una carga con una receta nueva (folio nuevo) para su RUT.

Reporte y bitácora:

- [x] Cada carga aplicada, cancelada o descartada queda en la bitácora de `/padron/` con usuario, fecha, nombre del archivo, estado y conteos.
- [x] Cada paciente y receta creado o modificado por una carga apunta a ella en `carga`.
- [x] El reporte de rechazos muestra, por fila, el número de fila, el RUT tal como venía y el motivo, y se descarga en CSV.
- [x] En el CSV descargado, ninguna celda empieza con `=`, `+`, `-` ni `@` sin un `'` antepuesto.
- [x] El servidor no guarda el archivo subido: no queda en disco ni en la base, salvo nombre, tamaño y huella.
- [x] La plantilla descargada, subida sin cambios, produce una carga sin rechazos.

Acceso:

- [x] Todas las rutas `/padron/...` redirigen al login sin sesión y responden 403 a funcionario y Encargado de Terreno.
- [x] `/recetas/` redirige al login sin sesión, responde 403 al Encargado de Terreno y funciona para funcionario y QF.
- [x] La búsqueda de `/recetas/` se envía por POST: el RUT no queda en la URL.
- [x] Las acciones «Aplicar carga» y «Cancelar» usan el modal de confirmación, no `confirm()`.

HU-21:

- [x] El turno en curso del panel con una receta de 2 de 6 entregas realizadas muestra «Entrega 3 de 6» y su fecha de vencimiento; un turno sin receta no muestra nada de eso.
- [x] `/recetas/` lista cada receta del RUT con folio, emisión, vencimiento, entregas realizadas y restantes y una insignia con texto «Vigente», «Agotada» o «Vencida».

Datos y rendimiento:

- [x] `generar_padron_sintetico --semilla 1` produce dos veces el mismo archivo.
- [x] El padrón sintético de 670 pacientes se carga sin errores y solo rechaza las filas inválidas generadas a propósito (RNF-07).
- [x] El Registro de verificación anota cuánto tardan la vista previa y la confirmación de ese padrón, con el equipo usado.
- [x] Toda la verificación usa datos sintéticos.

---

## Decisiones

- **Sí:** importación por archivo, sin API. Es lo que declaran HU-23 y RNF-07: Rayén no ofrece integración.
- **Sí:** aceptar CSV y Excel `.xlsx`, con `openpyxl` como dependencia nueva. HU-23 nombra los dos formatos, y pedirle a la QF que convierta el Excel a CSV es un paso más donde equivocarse. `openpyxl` es Python puro y se instala sin compilar.
- **No:** `.xls`, `.ods` ni varias hojas. Suman librerías o ambigüedad, y Excel guarda `.xlsx` por defecto.
- **Sí:** un solo archivo con una fila por receta, repitiendo los datos del paciente. Una sola carga y un solo reporte, sin depender del orden entre dos archivos.
- **No:** dos archivos (padrón y recetas). Obliga a cargarlos en orden y a cruzar dos reportes.
- **Sí:** el folio de Rayén como clave de la receta, en un campo nuevo único y nulo. Una corrección de fecha o de vigencia actualiza la misma receta en vez de duplicarla. Es nulo para no inventar folios a recetas existentes ni exigirlo en el admin.
- **No:** RUT más fecha de emisión como clave. Choca con dos recetas del mismo día y duplica la receta ante una corrección de fecha.
- **Sí:** `entregas_realizadas` queda en el mayor entre el valor local y el del archivo. El sistema cuenta las entregas que hace la farmacia, y bajarlo habilitaría entregas que ya se hicieron. Si Rayén trae más, se adopta.
- **No:** que el archivo mande siempre en el contador, ni ignorar esa columna. El primero permite entregar de más; el segundo hace partir en 0 recetas que ya llevan entregas.
- **Sí:** la renovación médica es una receta nueva con otro folio en una carga. No hace falta una pantalla aparte, y la receta anterior queda como historia.
- **Sí:** vista previa y confirmación. Un archivo equivocado (otro mes, otro establecimiento) se detecta antes de escribir.
- **Sí:** las filas pendientes van en `CargaPadron.filas_validas` (JSON), en estado `pendiente`. No dependen de la sesión de 30 minutos, y la misma fila sirve de bitácora.
- **No:** guardar las filas en la sesión. Unas 670 filas en la sesión, que se pierden si vence.
- **Sí:** volver a validar contra la base al confirmar. Otra carga u otro cambio en el admin pudo ocurrir entre la vista previa y la confirmación.
- **Sí:** tomar la carga con un `UPDATE` condicional sobre `estado`. Es el patrón de concurrencia del SPEC 02 (`select_for_update` no hace nada en SQLite).
- **Sí:** las filas válidas se cargan y las inválidas se informan, sin detener la carga (RNF-07). Un error de formato del archivo completo sí la detiene, porque ninguna fila sería confiable.
- **Sí:** rechazar todas las filas de un RUT con datos de paciente distintos. El sistema no adivina cuál es la correcta, y el reporte las nombra para corregirlas en origen.
- **Sí:** la carga solo crea y actualiza; no borra ni desactiva. Permite cargas parciales (por ejemplo, solo los postrados), y `Turno` protege a pacientes y recetas con `PROTECT`.
- **No:** marcar inactivos a los ausentes del archivo. Una carga parcial por error dejaría fuera a medio padrón.
- **Sí:** no guardar el archivo subido. Se conservan nombre, tamaño, huella SHA-256, quién, cuándo, conteos y rechazos. Retiene menos datos personales (leyes 19.628 y 21.719), y la huella permite reconocer después si se volvió a subir el mismo archivo.
- **Sí:** la FK `carga` en `Paciente` y `RecetaCronica`. Responde «quién cargó qué» de HU-23 y RNF-01 sin una tabla de historial por campo.
- **No:** un historial completo de cambios por paciente y receta. Es auditoría de otro tamaño, para otro spec si se pide.
- **Sí:** 5 MB y 5.000 filas como límites. Holgados para el padrón de crónicos y postrados, y la vista previa no se vuelve lenta en el equipo del mesón.
- **Sí:** plantilla CSV descargable y comando de padrón sintético. La plantilla evita errores de encabezado; el comando es la prueba del criterio de 670 pacientes del RNF-07 con datos sintéticos.
- **Sí:** los encabezados se comparan sin mayúsculas, tildes ni espacios. Una exportación de Rayén o una edición en Excel suelen cambiar eso sin cambiar el significado.
- **Sí:** la importación vive en un módulo nuevo `turnos/importacion.py`. Paciente y receta están en `turnos`, y `servicios.py` ya concentra la fila de atención.
- **No:** una app nueva. Agregaría una app para dos modelos que dependen de los de `turnos`.
- **Sí:** «Entrega N de M» en el turno en curso del panel y la consulta `/recetas/` para funcionario y QF. Es el «en cualquier momento» de HU-21.
- **Sí:** la búsqueda de `/recetas/` por POST, aunque en la pregunta se planteó `/recetas/?rut=…`. En un equipo compartido del mesón, un RUT en la URL queda en el historial del navegador y en los registros del servidor.
- **Sí:** el admin de Django se mantiene como acceso técnico a pacientes y recetas. Sirve para correcciones puntuales sin esperar otra carga.
- **No:** deshacer una carga aplicada. La reversión exacta exige guardar el estado anterior de cada registro; si hace falta, se corrige con otra carga.

---

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| El archivo de Rayén no tiene las columnas ni el formato que este spec supone | Encabezados tolerantes (mayúsculas, tildes, espacios), varios formatos de fecha y separador, y la plantilla. Cuando se conozca una exportación real, se ajusta el mapeo de columnas en `importacion.py`. |
| Rayén no exporta un folio por receta | Sin folio la fila se rechaza y el reporte lo dice. Si se confirma que no existe, otro spec define una clave alternativa. |
| Un archivo equivocado sobrescribe datos correctos | Vista previa con conteos antes de escribir, confirmación con el modal y la FK `carga` para saber qué tocó cada carga. |
| El contador de entregas de Rayén y el local difieren | Se toma el mayor y se informa como advertencia. Nunca se habilita una entrega de más. |
| Una carga a medias deja la base inconsistente | Una sola transacción por confirmación. Ante un error se revierte todo y la carga vuelve a `pendiente`. |
| Dos QF confirman la misma carga a la vez | `UPDATE` condicional sobre `estado = 'pendiente'`: solo una la toma. |
| Un `.xlsx` malicioso o enorme (bomba de compresión) agota la memoria | Límite de 5 MB antes de abrirlo, lectura en modo `read_only` y corte al pasar 5.000 filas. |
| El CSV de rechazos ejecuta fórmulas al abrirlo en Excel (inyección de fórmulas) | Toda celda que empieza con `=`, `+`, `-` o `@` lleva un `'` antepuesto. |
| Datos de salud retenidos más de lo necesario | No se guarda el archivo. `filas_validas` se borra al aplicar, cancelar o descartar, y solo vive hasta 60 minutos. Las pantallas son solo para la QF y la consulta, para funcionario y QF. |
| La codificación de un CSV se detecta mal y las tildes quedan dañadas | Se prueba UTF-8 estricto y, si falla, Windows-1252. La vista previa muestra nombres de ejemplo para notarlo antes de confirmar. |
| Un paciente deja de venir marcado como postrado y pasa a sacar turno presencial | La carga manda en los datos del paciente que trae. La vista previa cuenta los pacientes actualizados para revisarlos antes de confirmar. |
| El prototipo se interpreta como integración real con Rayén | Datos sintéticos, folios `SIN-` y `DEMO-`, y el README lo declara. |

---

## Lo que **no** está en este spec

- Integración por API, cargas automáticas o programadas con Rayén y datos reales.
- Desactivar o borrar pacientes y recetas ausentes del archivo, y deshacer cargas.
- Guardar archivos subidos o un historial de cambios por campo.
- Direcciones, referencias de domicilio y el módulo de reparto (HU-12 a HU-16, HU-19, HU-22).
- Estimación de espera, preparados pendientes de retiro y mermas (HU-17, HU-18, HU-20).
- Edición de recetas desde una pantalla de la QF.
- Cambios al motor de cola, a la sala o a las reglas de emisión del SPEC 02.

Cada uno de esos, si se hace, va en su propio spec.

---

## Registro de verificación

Completado el 2026-10-28. Condiciones comunes:

- **Equipo:** Windows 11 (AMD64, procesador AMD), Python 3.13.15 y Django 6.1.2 (el `requirements.txt` fija la 5.2.17; la del equipo es la que estaba instalada), SQLite.
- **Base:** una copia de la base local de desarrollo, con la migración `0003` aplicada y `cargar_datos_demo` (10 pacientes y 4 recetas).
- **Padrón:** `generar_padron_sintetico --semilla 1` en `.csv` y en `.xlsx` (mismo contenido): 1.019 filas, 670 pacientes, 1.009 recetas y 10 filas inválidas.
- **Cómo se midió:** las peticiones a `/padron/` y `/padron/<pk>/confirmar/` se hicieron con el cliente de pruebas de Django, en el mismo proceso, con una cuenta QF. El tiempo cubre la vista completa (lectura, validación, consultas y escritura), pero no la red ni `runserver`. Es una medición de laboratorio, no una garantía de producción.

| Comprobación | Condiciones | Resultado |
| --- | --- | --- |
| Vista previa del padrón sintético de 670 pacientes | `POST /padron/` con el `.csv` y, aparte, con el `.xlsx` | Cumple. CSV: 0,06 s. XLSX: 0,41 s. Los dos dan 1.019 filas, 10 rechazadas (una o dos por cada motivo 1 a 6), 670 pacientes y 1.009 recetas nuevos, sin advertencias, y no escriben pacientes ni recetas |
| Confirmación del mismo padrón | `POST /padron/<pk>/confirmar/` de la carga del CSV | Cumple. 0,11 s. Quedan 680 pacientes y 1.013 recetas (los 10 y 4 de la demostración más los nuevos), con los mismos conteos de la vista previa |
| Segunda carga del mismo archivo (todo «sin cambios») | El mismo `.csv`, subido y confirmado otra vez | Cumple. Vista previa en 0,08 s y confirmación en 0,06 s: 670 pacientes y 1.009 recetas sin cambios, 0 nuevos y 0 actualizados, las mismas 10 filas rechazadas |
| CSV en Windows-1252 con tildes y «ñ» | El mismo padrón recodificado a Windows-1252 desde Python (como guarda Excel «CSV (delimitado por comas)»). No se guardó desde un Excel real | Cumple. Se lee sin errores y da 670 pacientes «sin cambios»: los nombres con tilde y «ñ» (Begoña, Óscar, Muñoz, Núñez...) se leen igual que en UTF-8. Queda pendiente probar con un archivo guardado desde Excel |
| Paciente bloqueado en el tótem que recibe turno tras cargar su receta renovada | Paciente de demostración con la receta `DEMO-008` agotada; carga de una fila con su RUT y el folio nuevo `RENOV-008` (6 entregas, 0 realizadas) | Cumple. Antes: `emitir_turno` responde `bloqueado`. La carga crea 1 receta y deja al paciente sin cambios. Después: `emitido`, con el turno `G-001` asociado a `RENOV-008` |
| «Entrega N de M» en el panel y la consulta `/recetas/` | Base de pruebas: turno preferencial `P-012` llamado, con una receta de 2 de 6 entregas, y el mismo RUT con una receta agotada y otra vencida. Capturas con Edge sin cabeza a 1366 px | Cumple. El panel muestra «Entrega 3 de 6» y «Vence el …» junto a «Crónico», sin cambiar el ticket. `/recetas/` lista las tres recetas con «Vigente», «Agotada» y «Vencida», «2 de 6 entregas realizadas, quedan 4.» y las fechas. El ancho de un teléfono no se pudo capturar: Edge sin cabeza no baja de unos 492 px |
