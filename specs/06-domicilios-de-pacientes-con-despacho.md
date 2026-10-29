# SPEC 06 — Domicilios de los pacientes con despacho a domicilio

> **Estado:** Implementado
> **Depende de:** SPEC 01, SPEC 02 y SPEC 04
> **Fecha:** 2026-10-28
> **Objetivo:** Que el Encargado de Terreno registre, complete con coordenadas y fotos, y verifique en terreno el domicilio de cada paciente con despacho a domicilio, a partir de las direcciones que trae el padrón de Rayén y con el historial de cada cambio.

---

## Por qué existe este spec

Es la primera pieza del **módulo de reparto a domicilio**. Según el informe, unos 70 pacientes postrados y 600 mayores de 80 años reciben sus medicamentos en casa. El 57,9 % de la comuna es rural, y los conductores se guían por direcciones vagas («Dadinco, km 2 casa roja») y preguntando a los vecinos. El informe pide «recopilar y almacenar coordenadas, sumado a material fotográfico del entorno», y fija como meta (IG04) que el 100 % de los domicilios registrados tenga la dirección verificada.

Este spec implementa **HU-12** (Encargado de entrega en terreno, Should): «Registrar y actualizar la dirección y las referencias de ubicación, para facilitar la ubicación de los domicilios de pacientes mayores y postrados». Sus criterios son:

- El registro incluye sector, dirección y referencias.
- Se distinguen las direcciones pendientes de verificar de las ya verificadas.
- Se conserva quién realiza la actualización y cuándo.

Las demás historias del módulo quedan para specs posteriores, que usarán los datos de este:

- HU-13 (asignar entregas).
- HU-14 (consulta con mapa y orden de visita): necesita las coordenadas.
- HU-15 (registrar entregas, sin conexión según el RNF-03).
- HU-16 (reprogramar).
- HU-19 (notificar que el despacho va en camino).
- HU-22 (confirmación del paciente).

Es también la primera función propia del rol **Encargado de Terreno**, que desde el SPEC 01 solo llega a una página de marcador de posición.

**Auditoría previa.** Se hizo al redactar este spec, sin modificar código. Lo existente que se usa:

- `Paciente` con `es_postrado`, `edad` y `es_despacho_domicilio` (postrado o mayor de `TURNOS_EDAD_DESPACHO_DOMICILIO`).
- `Rol.ENCARGADO_TERRENO`. `cuentas.views.inicio` lo envía a `cuentas:panel_funcionario`, el marcador de posición.
- La importación del padrón de `turnos/importacion.py` (SPEC 04):
  - columnas `COLUMNAS_PACIENTE`, `COLUMNAS_RECETA` y `COLUMNAS_OBLIGATORIAS`;
  - `validar_filas`, con los motivos 1 a 6;
  - `planificar`, con el motivo 7 y las advertencias;
  - `preparar_carga` y `confirmar_carga`;
  - `CargaPadron`, con sus conteos;
  - la plantilla.
- `generar_padron_sintetico` y `cargar_datos_demo`.
- `SoloQF`, el modal de confirmación, `.lista`, `.tarjeta--formulario`, `rut_legible` y `normalizar_encabezado`.

Hoy no hay manejo de archivos subidos (`MEDIA_ROOT`), ni Pillow, ni HTTPS en desarrollo (`ALLOWED_HOSTS = []`).

*Al final no se hizo:* la importación del padrón con domicilios (columnas `sector`, `direccion` y `referencias`) y el padrón sintético con direcciones salieron de este spec hacia uno posterior, por decisión del equipo (2026-10-28). La importación del SPEC 04 no cambió.

Requería aprobación: un cambio a la importación del SPEC 04. El archivo acepta tres columnas opcionales nuevas, y el motivo 5 («datos del paciente distintos») pasa a comparar también el domicilio. Un archivo sin esas columnas se procesa exactamente igual que hoy. El SPEC 04 no se edita.

El sistema es un **prototipo académico** con datos sintéticos. Las direcciones, coordenadas y fotos de las pruebas son inventadas.

---

## Alcance

**Dentro:**

- App nueva `reparto` con los modelos `Domicilio`, `FotoDomicilio` y `CambioDomicilio` (historial).
- Un domicilio por paciente, solo para los de despacho a domicilio: sector (Verde, Azul o Rojo), dirección, referencias, latitud y longitud, y estado («Pendiente de verificar» o «Verificado»).
- Pantalla `/domicilios/` (Encargado de Terreno y QF):
  - lista de los pacientes con despacho a domicilio, filtrable por sector y por estado («Sin dirección», «Pendiente», «Verificado»);
  - búsqueda por RUT o apellido por POST;
  - el porcentaje de domicilios verificados (IG04).
- Ficha del domicilio: datos, fotos e historial. El Encargado de Terreno la edita, la verifica, la marca pendiente con motivo y sube o borra fotos. La QF solo la consulta.
- Verificación: exige coordenadas. Una edición posterior no la quita. Para pedir que se vuelva a verificar se usa «Marcar pendiente», con motivo.
- **Mapa en la ficha**, dentro del propio sistema:
  - Leaflet copiado en `static/`, sin CDN, como Alpine;
  - calles y caminos de OpenStreetMap, sin clave ni cuenta;
  - la ficha muestra el domicilio con un marcador;
  - al editar, se toca el mapa o se arrastra el marcador para fijar las coordenadas.
- Coordenadas por el mapa, por el GPS del navegador («Usar mi ubicación actual», solo con HTTPS) o escritas a mano, aceptando el formato pegado «-36.50, -72.21».
- Fotos:
  - hasta 3 por domicilio, JPEG o PNG de hasta 10 MB al subirlas;
  - el servidor las achica a 1600 px de lado mayor y les quita los metadatos (EXIF);
  - se guardan en `MEDIA_ROOT` y solo se entregan por una vista con permisos;
  - borrarlas elimina el archivo y queda en el historial.
- Historial completo: cada cambio guarda quién, cuándo, qué acción y el estado del domicilio después del cambio.
- El Encargado de Terreno entra directo a `/domicilios/`, y «Domicilios» aparece en la barra del Encargado y de la QF.
- HTTPS de desarrollo para probar el GPS desde un teléfono en la red local: `runserver_plus` con certificado autofirmado, dependencias en un `requirements-dev.txt` aparte, y la IP local configurable por variable de entorno.
- Domicilios de demostración en `cargar_datos_demo`.
- Pruebas de Django, pruebas de Node para la lectura de coordenadas, y la actualización de `README.md` y `CLAUDE.md`.

**Fuera de alcance (para specs futuros):**

- La importación del padrón con domicilios (columnas opcionales `sector`, `direccion` y `referencias`, con los domicilios verificados protegidos) y el padrón sintético con direcciones. Estaban en este spec (paso 7) y salieron por decisión del equipo durante la implementación. Hoy los domicilios se registran solo desde la ficha.
- Buscar domicilios por nombre. La búsqueda de `/domicilios/` es por RUT o apellido; el equipo pidió buscar también por nombre al probarla, y quedó para un spec posterior.
- Asignar, consultar, registrar y reprogramar entregas (HU-13 a HU-16).
- El mapa general con todos los domicilios o las entregas del día, y el orden de visita sugerido (HU-14). En este spec, el mapa está solo en la ficha de cada domicilio.
- Capa satelital, otros proveedores de mapas y claves de API.
- Mapa sin conexión (teselas guardadas en el teléfono).
- Operación sin conexión: service worker, almacenamiento local y sincronización (RNF-03). En este spec, todo requiere conexión.
- Notificaciones y confirmación del paciente (HU-19 y HU-22), y los datos de contacto del paciente.
- Que la QF o el funcionario editen domicilios. Solo el Encargado de Terreno registra, edita y verifica.
- Domicilios de pacientes sin despacho a domicilio.
- Configurar HTTPS de producción o desplegar el sistema.
- Geocodificar direcciones (convertir texto en coordenadas) y validar que las coordenadas caigan dentro de la comuna.
- Instalar el sistema como PWA en el teléfono (RNF-09).
- El panel de mermas (HU-20) y el bloqueo de login del SPEC 01.

---

## Modelo de datos

App nueva `reparto` (en `INSTALLED_APPS`), con `reparto/models.py` y la migración `0001`:

```python
class Sector(models.TextChoices):
    VERDE = "verde", "Verde"
    AZUL = "azul", "Azul"
    ROJO = "rojo", "Rojo"


class EstadoDomicilio(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente de verificar"
    VERIFICADO = "verificado", "Verificado"


class Domicilio(models.Model):
    """Dónde vive un paciente con despacho a domicilio (HU-12)."""

    paciente = models.OneToOneField("turnos.Paciente", on_delete=models.PROTECT, related_name="domicilio")
    sector = models.CharField("sector", max_length=10, choices=Sector.choices, blank=True)
    direccion = models.CharField("dirección", max_length=200)
    referencias = models.TextField("referencias", max_length=1000, blank=True)
    latitud = models.DecimalField("latitud", max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField("longitud", max_digits=9, decimal_places=6, null=True, blank=True)
    estado = models.CharField("estado", max_length=12, choices=EstadoDomicilio.choices, default=EstadoDomicilio.PENDIENTE)
    verificado_en = models.DateTimeField("verificado en", null=True, blank=True)
    verificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    actualizado_en = models.DateTimeField("actualizado en", default=timezone.now)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    carga = models.ForeignKey("turnos.CargaPadron", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class FotoDomicilio(models.Model):
    domicilio = models.ForeignKey(Domicilio, on_delete=models.PROTECT, related_name="fotos")
    archivo = models.ImageField(upload_to="domicilios/")  # nombre aleatorio (uuid4), siempre .jpg
    ancho = models.PositiveIntegerField()
    alto = models.PositiveIntegerField()
    subida_en = models.DateTimeField(default=timezone.now)
    subida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")


class AccionDomicilio(models.TextChoices):
    CREADO = "creado", "Registró el domicilio"
    EDITADO = "editado", "Editó el domicilio"
    VERIFICADO = "verificado", "Verificó el domicilio"
    MARCADO_PENDIENTE = "marcado_pendiente", "Lo marcó pendiente de verificar"
    FOTO_AGREGADA = "foto_agregada", "Agregó una foto"
    FOTO_BORRADA = "foto_borrada", "Borró una foto"
    CARGA_PADRON = "carga_padron", "Cargado desde el padrón"


class CambioDomicilio(models.Model):
    """Historial de un domicilio: cada acción, quién y cuándo, y cómo quedó (HU-12, RNF-01)."""

    domicilio = models.ForeignKey(Domicilio, on_delete=models.PROTECT, related_name="cambios")
    en = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    accion = models.CharField(max_length=20, choices=AccionDomicilio.choices)
    # {"sector", "direccion", "referencias", "latitud", "longitud", "estado"} después del cambio.
    datos = models.JSONField()
    motivo = models.CharField(max_length=300, blank=True)  # solo en MARCADO_PENDIENTE
    carga = models.ForeignKey("turnos.CargaPadron", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-en", "-pk"]
```

**Reglas del domicilio:**

- Un paciente tiene a lo más un domicilio. Solo se crea y se lista para pacientes con `es_despacho_domicilio`. Si un paciente deja de serlo (por ejemplo, ya no viene marcado como postrado), su domicilio se conserva, pero sale de la lista.
- **Sin dirección:** paciente con despacho a domicilio que todavía no tiene `Domicilio`. No es un estado del modelo: es la ausencia de la fila.
- Crear o editar deja el domicilio con `actualizado_por` y `actualizado_en`, y agrega un `CambioDomicilio`.
- **Verificar** exige latitud y longitud. Guarda `verificado_por` y `verificado_en` y agrega un cambio `VERIFICADO`.
- **Editar un domicilio verificado lo deja verificado.** Las coordenadas de un domicilio verificado no se pueden borrar.
- **Marcar pendiente** solo aplica a uno verificado, exige un motivo de hasta 300 caracteres, limpia `verificado_por` y `verificado_en` y agrega un cambio `MARCADO_PENDIENTE` con el motivo.
- Todo cambio de estado se hace con `UPDATE` condicional sobre `estado`, el patrón del SPEC 02.
- **Coordenadas:** latitud de -90 a 90 y longitud de -180 a 180, con 6 decimales (unos 11 cm). Se aceptan con coma o punto decimal, y si el campo de latitud trae «lat, lon» pegado, se separa y manda sobre lo que diga la longitud (*ajustado al implementar:* quien pega las dos quiere reemplazar las dos; en el navegador se reparten en los dos campos al pegarlas). No se valida que caigan en la comuna.
- **Indicador IG04:** domicilios verificados ÷ domicilios registrados de los pacientes con despacho a domicilio, como dice el informe. La lista muestra también cuántos pacientes están sin dirección, que no entran en ese porcentaje.

**Reglas de las fotos:**

- Hasta `REPARTO_FOTOS_MAXIMAS` por domicilio. La cuarta se rechaza con «Este domicilio ya tiene 3 fotos. Borre una para subir otra.».
- Se aceptan JPEG y PNG de hasta `REPARTO_BYTES_MAXIMOS_FOTO`. Pillow abre y verifica la imagen, y se rechaza la que supera `REPARTO_PIXELES_MAXIMOS_ENTRADA` (una imagen enorme en píxeles puede agotar la memoria al abrirla).
- **Procesamiento:**
  1. se aplica la orientación del EXIF;
  2. se achica a `REPARTO_PIXELES_LADO_MAYOR` de lado mayor (sin agrandar);
  3. se convierte a JPEG (calidad 85, con fondo blanco si había transparencia);
  4. se guarda **sin metadatos**, con un nombre aleatorio.

  El archivo original no se conserva.
- Las fotos solo se entregan por `/domicilios/fotos/<pk>/` (Encargado de Terreno y QF) con `Cache-Control: private`. `MEDIA_ROOT` no se sirve por ninguna URL pública. `media/` va en `.gitignore`.
- Borrar una foto elimina el archivo y la fila, y agrega un cambio `FOTO_BORRADA`. Agregar una agrega `FOTO_AGREGADA`.

**Cambios a la importación del padrón** (`turnos/importacion.py`). *No se implementaron:* salieron de este spec hacia uno posterior junto con el paso 7; quedan como referencia.

| Columna | Obligatoria | Formato |
| --- | --- | --- |
| `sector` | No | `Verde`, `Azul` o `Rojo`, sin distinguir mayúsculas, tildes ni espacios. |
| `direccion` | No | Texto, hasta 200 caracteres. |
| `referencias` | No | Texto, hasta 1000 caracteres. |

- Un archivo sin estas columnas, o con ellas vacías, se procesa igual que en el SPEC 04 y no toca domicilios.
- Un sector que no es Verde, Azul ni Rojo, o un texto demasiado largo, rechaza la fila con el **motivo 2**.
- El **motivo 5** compara también `sector`, `direccion` y `referencias`: dos filas del mismo RUT con domicilios distintos se rechazan las dos.
- **Al planificar y al confirmar**, por cada paciente de la carga que trae algún dato de domicilio:
  - **Paciente sin despacho a domicilio:** no se toca nada y queda una advertencia «El paciente no tiene despacho a domicilio: no se cargó su domicilio.».
  - **Sin domicilio:** se crea `pendiente` si viene la dirección. Si viene sector o referencias sin dirección, queda una advertencia «Falta la dirección: no se creó el domicilio.».
  - **Domicilio pendiente:** se actualiza con lo que trae el archivo. Un campo vacío no borra el valor que ya existe.
  - **Domicilio verificado:**
    - si el archivo trae algo distinto, no se toca y queda una advertencia «El domicilio está verificado en terreno: no se cambió con el padrón.»;
    - si trae lo mismo, cuenta como «sin cambios».
- Cada domicilio creado o actualizado por una carga lleva `carga`, `actualizado_por` (la QF que confirmó) y un cambio `CARGA_PADRON`.
- La escritura va dentro de la misma transacción de `confirmar_carga`, mediante `reparto.servicios.aplicar_domicilios_de_carga(...)`.
- `CargaPadron` suma `domicilios_creados`, `domicilios_actualizados` y `domicilios_sin_cambios` (migración `turnos` `0005`), que se muestran en la vista previa y en el reporte.
- La plantilla agrega las tres columnas, con un domicilio de ejemplo sintético.

**Constantes nuevas** al final de `settings.py`:

```python
REPARTO_FOTOS_MAXIMAS = 3
REPARTO_BYTES_MAXIMOS_FOTO = 10 * 1024 * 1024
REPARTO_PIXELES_LADO_MAYOR = 1600
REPARTO_PIXELES_MAXIMOS_ENTRADA = 40_000_000   # unos 40 megapíxeles
REPARTO_CENTRO_MAPA = (-36.4999, -72.2128)     # San Nicolás: centro del mapa sin coordenadas
REPARTO_ZOOM_MAPA = 17                         # acercamiento con un domicilio marcado
MEDIA_ROOT = BASE_DIR / "media"                # fotos de domicilios; nunca se sirve en público
```

**Mapa:**

- Leaflet (versión fija) va copiado en `static/vendor/leaflet/`, con su CSS, sus imágenes de marcador y su licencia (BSD-2).
- Las teselas se piden a `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, siempre con la atribución «© colaboradores de OpenStreetMap» visible. No requieren clave.
- Las teselas se piden con `referrerPolicy: 'strict-origin-when-cross-origin'`. *Ajustado tras la implementación:* OpenStreetMap bloquea las teselas que llegan sin `Referer` (las reemplaza por la imagen «Access blocked»), y Django lo quita en todo el sitio con `Referrer-Policy: same-origin`. Así se envía solo el origen (`http://127.0.0.1:8000/`), nunca la ruta `/domicilios/<id>/`, que lleva el id del paciente. El resto del sitio sigue con `same-origin`.
- Sin coordenadas, el mapa se centra en `REPARTO_CENTRO_MAPA` con un acercamiento de comuna.
- **Sin conexión,** las teselas no cargan: el mapa queda gris con el aviso «No se pudo cargar el mapa. Puede escribir las coordenadas.», y el formulario sigue funcionando.
- El mapa es una ayuda: las coordenadas que se guardan son siempre las de los campos de latitud y longitud, que el mapa llena y que también se pueden escribir.

**HTTPS de desarrollo:**

- `requirements-dev.txt` incluye `-r requirements.txt` más `django-extensions`, `Werkzeug` y `pyOpenSSL`, con versiones fijas.
- `django_extensions` se agrega a `INSTALLED_APPS` solo si está instalado, así `requirements.txt` sigue bastando para el resto.
- La variable de entorno `TURNOS_HOSTS_LOCALES` (por ejemplo `192.168.1.20`) agrega esas IP a `ALLOWED_HOSTS` y `https://<ip>:8443` a `CSRF_TRUSTED_ORIGINS`.
- El contenido de `certs/` va en `.gitignore` (`certs/*`), y la carpeta queda en el repositorio con un `.gitkeep`. *Ajustado al implementar:* `runserver_plus` no crea la carpeta, y sin ella el comando falla en un repositorio recién clonado.
- Se ejecuta con `python manage.py runserver_plus 0.0.0.0:8443 --cert-file certs/dev.crt`, que genera el certificado autofirmado la primera vez.

**Rutas nuevas** en `reparto/urls.py`, montadas en la raíz:

| Ruta | Método | Acceso | Nombre |
| --- | --- | --- | --- |
| `/domicilios/` | GET (filtros `?sector=` y `?estado=`), POST (búsqueda) | Encargado de Terreno y QF | `reparto:domicilios` |
| `/domicilios/<paciente_id>/` | GET | Encargado de Terreno y QF | `reparto:ficha` |
| `/domicilios/<paciente_id>/editar/` | GET, POST | Encargado de Terreno | `reparto:editar` |
| `/domicilios/<paciente_id>/verificar/` | POST | Encargado de Terreno | `reparto:verificar` |
| `/domicilios/<paciente_id>/pendiente/` | POST | Encargado de Terreno | `reparto:marcar_pendiente` |
| `/domicilios/<paciente_id>/fotos/` | POST | Encargado de Terreno | `reparto:subir_foto` |
| `/domicilios/fotos/<pk>/` | GET | Encargado de Terreno y QF | `reparto:foto` |
| `/domicilios/fotos/<pk>/borrar/` | POST | Encargado de Terreno | `reparto:borrar_foto` |

Mixins nuevos en `reparto/mixins.py`: `SoloTerreno` (Encargado de Terreno) y `ConsultaDomicilios` (Encargado de Terreno y QF). Los demás roles reciben 403.

---

## Plan de implementación

1. **App y modelos.**
   - Crear la app `reparto` y agregarla a `INSTALLED_APPS`.
   - Escribir `Sector`, `EstadoDomicilio`, `Domicilio`, `FotoDomicilio`, `AccionDomicilio` y `CambioDomicilio`, con la migración `0001`.
   - Agregar `Pillow`, con versión fija, a `requirements.txt`, `MEDIA_ROOT` y las constantes `REPARTO_*` a `settings.py`, y `media/` a `.gitignore`.
   - Registrar los tres modelos en `reparto/admin.py` como solo lectura.

   **Verificación:** `migrate` aplica sin errores sobre una base con datos; un paciente no admite dos domicilios; la suite existente pasa.

2. **Servicios del domicilio.**
   - En `reparto/servicios.py`, escribir `guardar_domicilio(paciente, datos, usuario)`, `verificar(paciente, usuario)` y `marcar_pendiente(paciente, motivo, usuario)`. `guardar_domicilio` crea o edita.
   - Escribir las consultas `pacientes_de_despacho(sector=None, estado=None, busqueda=None)` y `resumen_de_verificacion()` (IG04).
   - Escribir `leer_coordenadas(texto)`, que acepta coma o punto decimal y «lat, lon».
   - Los errores son `ErrorDeDomicilio`, cuyo mensaje se muestra tal cual.

   **Verificación:** `reparto/tests/test_servicios.py` cubre:
   - crear y editar con su historial;
   - verificar sin coordenadas (rechazado) y con coordenadas;
   - que una edición no quita la verificación y que no se pueden borrar las coordenadas de un verificado;
   - marcar pendiente con y sin motivo;
   - dos verificaciones seguidas, que se aplican una vez;
   - un paciente sin despacho a domicilio, rechazado;
   - los filtros y la búsqueda por RUT y por apellido sin tildes;
   - el porcentaje IG04 con domicilios sin dirección fuera de la cuenta;
   - las formas de escribir coordenadas, válidas e inválidas.

3. **Fotos.**
   - Escribir `agregar_foto(paciente, archivo, usuario)`, que valida tamaño, tipo y píxeles, procesa con Pillow y aplica el tope, y `borrar_foto(foto, usuario)`.
   - Escribir la vista que entrega la foto con `ConsultaDomicilios` y `Cache-Control: private`.

   **Verificación:** `reparto/tests/test_fotos.py`, con imágenes generadas en memoria y `MEDIA_ROOT` temporal, cubre:
   - un JPEG con EXIF (orientación y GPS) que queda rotado y sin EXIF;
   - un PNG con transparencia que queda en JPEG;
   - una imagen grande que queda en 1600 px y una chica que no se agranda;
   - un archivo que no es imagen, uno de más de 10 MB y uno de demasiados píxeles, todos rechazados;
   - que la cuarta foto se rechaza;
   - que al borrar se elimina el archivo y queda en el historial;
   - que la foto responde 200 al Encargado y a la QF y 403 al funcionario, y redirige al login sin sesión.

4. **Lista de domicilios.**
   - Escribir `reparto/mixins.py` y la vista `/domicilios/`:
     - el resumen IG04 («N de M domicilios verificados (P %)», y «K pacientes sin dirección») en `.resumen`;
     - filtros de sector y estado como enlaces (GET, sin datos personales en la URL);
     - búsqueda por RUT o apellido por POST en `.tarjeta--formulario`;
     - una `.lista` con el nombre, el RUT con `rut_legible`, el sector, la dirección e insignias con texto («Sin dirección», «Pendiente de verificar», «Verificado»). Cada fila enlaza a su ficha.
   - En `cuentas.views.inicio`, el Encargado de Terreno pasa a ir a `reparto:domicilios`.
   - Agregar «Domicilios» a la barra del Encargado de Terreno y de la QF, y una sección «17 · Domicilios» en `estilos.css`, con las insignias `insignia--sin_direccion` y `--verificado`, y reutilizando `--pendiente` (punteada, la misma de las cargas: aún no está confirmado).

   **Verificación:** `reparto/tests/test_vistas.py` cubre:
   - el acceso por rol (sin sesión, funcionario 403, Encargado y QF 200);
   - los filtros y la búsqueda por POST, sin el RUT en la URL;
   - que un paciente sin despacho no aparece;
   - el resumen;
   - la redirección de inicio del Encargado (y se ajusta la prueba de `cuentas` que esperaba el marcador de posición).

5. **Ficha y edición.**
   - **Ficha `/domicilios/<paciente_id>/`:** datos, coordenadas, fotos y el historial como `.lista` con fecha, persona, acción y motivo. El mapa llega en el paso 6; mientras tanto, solo se ven las coordenadas.
   - **Para el Encargado de Terreno, la ficha agrega:**
     - «Editar»;
     - «Verificar», deshabilitado y explicado si faltan coordenadas;
     - «Marcar pendiente», con modal y un campo de motivo;
     - subir foto, con `accept="image/*"` y `capture="environment"` para abrir la cámara en el teléfono;
     - «Borrar» en cada foto, con modal.
   - **Formulario de edición** en `reparto/forms.py`: sector como opciones, dirección, referencias, latitud y longitud.
   - La ficha y el formulario deben usarse en un teléfono de 360 px de ancho sin desplazamiento horizontal.

   **Verificación:** pruebas de vista del flujo completo:
   - registrar → subir foto → verificar → editar (sigue verificado) → marcar pendiente con motivo;
   - el historial con cada paso;
   - que la QF ve la ficha sin botones de acción y recibe 403 en cada POST;
   - que los formularios de «Marcar pendiente» y «Borrar» usan el modal y no `confirm()`.

   Capturas en Edge a 360 y 1366 px.

6. **Mapa, GPS y HTTPS de desarrollo.**
   - Copiar Leaflet en `static/vendor/leaflet/` con su licencia.
   - En `static/js/reparto.js` (cargado antes de Alpine), escribir:
     - el componente `mapaDomicilio`:
       - en la ficha, muestra el marcador (o el centro de la comuna sin coordenadas);
       - en el formulario, al tocar el mapa o soltar el marcador, llena latitud y longitud con 6 decimales;
       - al escribir las coordenadas, mueve el marcador;
       - si las teselas no cargan, muestra el aviso del spec;
     - el componente `ubicacionActual`: muestra «Usar mi ubicación actual» solo si `window.isSecureContext` y `navigator.geolocation` existen, llena latitud y longitud con 6 decimales y avisa si el permiso se niega o la lectura falla;
     - la función pura `leerCoordenadas(texto)`, exportada para Node como en `sala.js`, que separa «lat, lon» pegado en el campo de latitud.
   - Escribir `requirements-dev.txt`, `TURNOS_HOSTS_LOCALES` en `settings.py`, `django_extensions` condicional y `certs/` en `.gitignore`.

   **Verificación:**
   - `pruebas_js/reparto.test.js` cubre `leerCoordenadas`;
   - en Edge, a 360 y 1366 px:
     - tocar el mapa del formulario llena los campos;
     - escribir las coordenadas mueve el marcador;
     - con la red de las teselas bloqueada aparece el aviso y se puede guardar igual;
   - una prueba de Django confirma que sin la variable `ALLOWED_HOSTS` no cambia, y que con ella se agregan la IP y el origen;
   - a mano: `runserver_plus` con certificado, el teléfono en la misma red abre `https://<ip>:8443/`, acepta el certificado y el botón llena las coordenadas. Queda anotado en el Registro de verificación.

7. **Importación con domicilios.** *Fuera de este spec:* el 2026-10-28, durante la implementación, el equipo decidió no cambiar la importación del padrón, y después la pasó a un spec posterior. No se implementó; el plan queda aquí como referencia para ese spec.
   - En `turnos/importacion.py`:
     - las columnas opcionales;
     - la validación del sector (motivo 2);
     - el motivo 5 con el domicilio;
     - el plan de domicilios con sus advertencias y conteos.
   - En `reparto/servicios.py`, `aplicar_domicilios_de_carga`, llamado dentro de la transacción de la confirmación.
   - Los tres conteos en `CargaPadron` (migración `0005`), en la vista previa y en el reporte; las columnas en la plantilla.

   **Verificación:** pruebas en `turnos/tests/test_importacion.py` y `test_padron.py`:
   - un archivo del SPEC 04 sin las columnas da exactamente los mismos conteos que antes y no crea domicilios;
   - un sector inválido rechaza la fila;
   - dos filas del mismo RUT con direcciones distintas se rechazan;
   - se crea un domicilio pendiente;
   - un pendiente se actualiza y un campo vacío no borra;
   - un verificado no se pisa y deja la advertencia;
   - un paciente sin despacho y una fila sin dirección dejan sus advertencias;
   - la vista previa coincide con lo aplicado;
   - si la confirmación falla a mitad, no queda ningún domicilio;
   - la plantilla, subida sin cambios, crea su domicilio de ejemplo sin rechazos.

8. **Datos sintéticos.**
   - **`generar_padron_sintetico`** (*fuera de este spec, junto con el paso 7:* sin las columnas en la importación, esas direcciones no tienen cómo entrar; no se implementó):
     - sector, una dirección rural inventada («Camino a Dadinco km 4», «Sector Puente Ñuble, parcela 12») y referencias para cada paciente con despacho a domicilio;
     - algunos sin dirección;
     - sectores inválidos entre las filas inválidas del motivo 2;
     - con la misma semilla, el mismo archivo.
   - **`cargar_datos_demo`:**
     - Octavio (mayor de 80) con un domicilio pendiente;
     - Pablo (postrado) con uno verificado, con coordenadas inventadas cerca de San Nicolás;
     - los dos sin fotos, a nombre de la primera cuenta QF como el historial del SPEC 05 (sin ella, avisa y no los crea);
     - sigue siendo idempotente.

   **Verificación:** la prueba del padrón sintético sigue rechazando exactamente las filas inválidas pedidas; `cargar_datos_demo` dos veces deja las mismas filas.

9. **Documentación y registro.**
   - **`README.md`:**
     - la ruta `/domicilios/` y qué hace el Encargado de Terreno;
     - las columnas nuevas del padrón;
     - las fotos (privadas, achicadas, sin metadatos);
     - cómo probar el GPS desde un teléfono con `requirements-dev.txt` y `runserver_plus`;
     - una demostración.
   - **`CLAUDE.md`:**
     - la app `reparto` y sus reglas;
     - el cambio a la importación;
     - `MEDIA_ROOT` privado;
     - los mixins nuevos;
     - el inicio del Encargado de Terreno;
     - `reparto.js` y la numeración de specs.
   - Completar el Registro de verificación de este spec.

   **Verificación:** una persona del equipo sigue el README desde cero, registra y verifica un domicilio desde un teléfono.

---

## Criterios de aceptación

Los de la importación del padrón con domicilios y del padrón sintético con direcciones salieron junto con el paso 7 (ver Alcance).

Regresión de los SPEC 01 a 05:

- [x] `python manage.py test` y `node --test "pruebas_js/*.test.js"` pasan completos.
- [x] Un archivo del padrón produce exactamente los mismos conteos, rechazos y advertencias que antes de este spec (la importación no cambió).
- [x] No cambian el tótem, la fila, el panel de atención, la sala ni la preparación.
- [x] `requirements.txt` sigue bastando para levantar el sistema sin HTTPS.

Domicilio:

- [x] Solo los pacientes con despacho a domicilio aparecen en `/domicilios/` y pueden tener domicilio.
- [x] Un paciente no puede tener dos domicilios.
- [x] Registrar y editar guardan sector, dirección, referencias y coordenadas, con quién y cuándo, y dejan un cambio en el historial.
- [x] «Verificar» sin coordenadas se rechaza con un mensaje que lo dice; con coordenadas deja el domicilio «Verificado», con quién y cuándo.
- [x] Editar un domicilio verificado lo deja verificado; borrar sus coordenadas se rechaza.
- [x] «Marcar pendiente» exige un motivo, usa el modal de confirmación y el motivo aparece en el historial.
- [x] Las coordenadas se aceptan con punto o coma decimal y como «-36.50, -72.21» pegado en la latitud; una latitud fuera de -90 a 90 se rechaza.
- [x] El historial de la ficha muestra cada acción con fecha, persona y motivo, de la más reciente a la más antigua.

Fotos:

- [x] Se aceptan hasta 3 fotos por domicilio; la cuarta se rechaza con el mensaje del spec.
- [x] Una foto subida queda en JPEG, con su lado mayor de a lo más 1600 px y sin datos EXIF (ni GPS ni modelo de cámara).
- [x] Un archivo que no es imagen, uno de más de 10 MB o uno de más de 40 megapíxeles se rechaza sin guardar nada.
- [x] Una foto solo se ve con sesión de Encargado de Terreno o QF; no existe una URL pública de `MEDIA_ROOT`.
- [x] Borrar una foto elimina su archivo del disco y deja un cambio en el historial.

Lista e indicador:

- [x] La lista filtra por sector y por estado («Sin dirección», «Pendiente de verificar», «Verificado»), y cada estado se muestra con una insignia con texto.
- [x] La búsqueda por RUT (con o sin puntos) o por apellido (con o sin tilde) se envía por POST y el RUT no queda en la URL.
- [x] El resumen muestra los verificados sobre los registrados con su porcentaje (IG04) y, aparte, los pacientes sin dirección.

Acceso y uso en terreno:

- [x] El Encargado de Terreno entra directo a `/domicilios/` y ve «Domicilios» en la barra; la QF también lo ve.
- [x] Todas las acciones de escritura responden 403 a la QF, al funcionario y a quien no sea Encargado de Terreno, y redirigen al login sin sesión.
- [x] La lista, la ficha y el formulario se usan a 360 px de ancho sin desplazamiento horizontal.
- [x] La ficha muestra el domicilio en un mapa de OpenStreetMap dentro del sistema, con la atribución visible; sin coordenadas, el mapa se centra en San Nicolás.
- [x] Al editar, tocar el mapa o arrastrar el marcador llena latitud y longitud, y escribirlas mueve el marcador.
- [x] Sin conexión a las teselas, el mapa muestra el aviso del spec y el formulario se guarda igual con las coordenadas escritas.
- [x] El mapa no usa ninguna clave de API ni archivos de un CDN: Leaflet se sirve desde `static/`.
- [x] Con HTTPS, «Usar mi ubicación actual» llena latitud y longitud; sin HTTPS, el botón no aparece y las coordenadas se pueden escribir.
- [ ] Con `requirements-dev.txt` y `TURNOS_HOSTS_LOCALES`, un teléfono en la misma red abre el sistema por HTTPS. *Sin verificar con un teléfono real:* se probó desde el mismo equipo, por la IP de la red local y con Edge, con una ubicación simulada.

Datos:

- [x] `cargar_datos_demo` dos veces deja las mismas filas, con un domicilio pendiente y uno verificado.
- [x] Toda la verificación usa datos sintéticos.

---

## Decisiones

- **Sí:** este spec es solo HU-12, la primera pieza del reparto. Asignar, consultar con mapa, registrar entregas, reprogramar, notificar y confirmar son decisiones de otro tamaño. Todas necesitan saber primero dónde vive cada paciente.
- **Sí:** app nueva `reparto`. Es el módulo que crece con HU-13 a HU-16. `turnos` ya concentra la fila, la preparación y el padrón.
- **No:** dentro de `turnos`, como el padrón del SPEC 04. Allí eran dos modelos atados a la fila; aquí empieza otro módulo.
- **Sí:** un domicilio por paciente y solo para los de despacho a domicilio. Es la población de HU-12 (postrados y mayores de 80). Un domicilio que ya existe se conserva si el paciente deja de ser de despacho.
- **Sí:** coordenadas y fotos, además de lo que pide HU-12. El informe pide «recopilar y almacenar coordenadas, sumado a material fotográfico del entorno», y HU-14 necesitará las coordenadas para el mapa y la ruta.
- **Sí:** hasta 3 fotos, achicadas a 1600 px, en JPEG y sin EXIF. Una foto de teléfono pesa de 3 a 8 MB y su EXIF trae la ubicación exacta y el modelo del equipo: datos personales que no hacen falta (leyes 19.628 y 21.719).
- **Sí:** las fotos solo se entregan por una vista con permisos. La fachada de la casa de un paciente postrado es un dato sensible; una URL pública de `media/` la expondría a cualquiera que la adivine.
- **Sí:** borrar una foto elimina el archivo y deja el registro en el historial. Con tope de 3, una foto mala debe poder reemplazarse, y no se retienen imágenes que ya no se usan.
- **No:** conservar los archivos borrados para auditoría. Se retendrían fotos de domicilios sin propósito.
- **Sí:** solo el Encargado de Terreno registra, edita y verifica, y la QF consulta. Es lo que dice HU-12. La verificación implica haber estado en el lugar.
- **No:** que la QF o la ventanilla editen. Quedaría la duda de si un cambio se hizo en terreno.
- **Sí:** «Verificado» exige coordenadas. Verificar es haber estado ahí, y un domicilio verificado sin ubicación no le serviría al mapa de HU-14.
- **Sí:** editar no quita la verificación, y «Marcar pendiente» con motivo es la forma explícita de pedir que se vuelva a verificar. Solo edita quien está en terreno, y el historial guarda cada cambio.
- **Sí:** historial completo en `CambioDomicilio`, con el estado del domicilio después de cada acción. HU-12 pide quién y cuándo, el RNF-01 pide auditoría de quién modifica, y permite ver qué decía la dirección antes de un error.
- **No:** solo `actualizado_por` y `actualizado_en`. Se pierde lo anterior.
- **Sí:** las direcciones vienen del padrón de Rayén como columnas opcionales y se completan en terreno. Escribir 670 domicilios desde cero no es realista, y lo que viene de Rayén entra como «pendiente de verificar».
- **Sí:** una carga nunca pisa un domicilio verificado y lo informa como advertencia. Lo comprobado en terreno vale más que el registro clínico, igual que el contador de entregas del SPEC 04 nunca baja.
- **Sí:** un sector inválido rechaza la fila (motivo 2), y el motivo 5 compara también el domicilio. Es la regla del SPEC 04: el sistema no adivina, y el reporte lo nombra para corregirlo en origen.
- **Sí:** un dato de domicilio para un paciente sin despacho se ignora con una advertencia, en vez de rechazar la fila. El resto de la fila (paciente y receta) es válido. Decidido al redactar el spec, sin pregunta explícita: revisar.
- **Sí:** un campo vacío en el archivo no borra un valor existente del domicilio. Una exportación parcial no debe deshacer lo registrado.
- **Sí:** solo con conexión en este spec. El RNF-03 nombra HU-14 y HU-15, y el modo sin conexión (service worker, cola local, sincronización sin duplicados, fotos pendientes en el teléfono) es un spec en sí mismo.
- **Sí:** «Usar mi ubicación actual» además de escribir las coordenadas. El GPS del navegador solo funciona con HTTPS, y escribirlas a mano o pegarlas desde un mapa siempre funciona.
- **Sí:** HTTPS de desarrollo con `runserver_plus`, en un `requirements-dev.txt` aparte. Permite probar el GPS desde el teléfono en la red local sin tocar las dependencias de ejecución.
- **No:** un proxy externo (Caddy) ni un comando propio con `ssl`. El primero agrega una herramienta fuera de Python, y el segundo es código propio que mantener.
- **Sí:** el indicador IG04 como verificados sobre registrados, mostrando aparte los sin dirección. Es la definición del informe, y separar los sin dirección muestra cuánto falta por registrar.
- **Sí:** mapa dentro del sistema en la ficha de cada domicilio, para ver dónde quedó y para marcarlo tocando el mapa. Así se fijan coordenadas aun sin GPS, y se comprueba a la vista que no estén invertidas. Pedido por el equipo al revisar el borrador.
- **No:** el mapa general con todos los domicilios en este spec. Es el mapa de HU-14, junto con las entregas del día y el orden de visita.
- **Sí (ajustado al implementar):** las tres páginas de domicilios con el mapa a pantalla completa y una hoja blanca que flota sobre él (la lista, la ficha o el formulario), como en las aplicaciones de mapas. Pedido por el equipo con un diseño de referencia, en la paleta del sistema. Por eso la lista sí muestra un marcador por cada domicilio **de la lista** (con sus filtros y su búsqueda): sirve para ubicarse y para ver qué falta verificar. Las entregas del día, la asignación y el orden de visita siguen siendo de HU-14.
- **Sí (ajustado al implementar):** movimiento de mapa al llegar a cada página: la cámara vuela desde donde quedó en la página anterior (guardada en `sessionStorage`) hasta el domicilio o la lista, y el marcador cae con una onda; entre la lista y la ficha, la hoja se transforma con View Transitions donde el navegador lo permite. Es el único movimiento que no responde a un toque, ocurre una vez por página y se apaga con `prefers-reduced-motion`. La placa petróleo con la dirección pasa de estar sobre el mapa a ir al lado del marcador de la ficha.
- **Sí (ajustado al implementar):** «Mostrar mi ubicación» en el mapa de la lista y de la ficha (solo con HTTPS); en la ficha, además, la distancia en línea recta hasta el domicilio. No se guarda ni se envía: es para orientarse en terreno.
- **No:** ruta ni indicaciones paso a paso. Piden un servicio de rutas externo, y el orden de visita es de HU-14.
- **No:** solo un enlace a un mapa externo. Saca al Encargado del sistema y no permite marcar la ubicación.
- **Sí:** Leaflet copiado en `static/` y teselas de OpenStreetMap, sin clave. Gratis, sin cuenta ni facturación, y Leaflet sigue la regla de no usar CDN (como Alpine). El tráfico de un prototipo cabe en la política de uso de OpenStreetMap, que exige la atribución.
- **No:** capa satelital (Mapbox) ni Google Maps. Los dos piden una clave, y Google además una cuenta con facturación. El satélite ayudaría a reconocer casas en el campo: si se pide, va en otro spec con su clave en una variable de entorno.
- **Sí:** las coordenadas guardadas son siempre las de los campos, y el mapa solo las llena. Si el mapa no carga, por falta de señal o de internet, el registro sigue funcionando.
- **Sí:** los filtros de sector y estado van por GET, y la búsqueda de RUT o apellido por POST. Los filtros no contienen datos personales y se pueden marcar; el RUT no debe quedar en el historial del navegador (regla de `/recetas/`).
- **Sí:** la importación del padrón con domicilios sale de este spec. El equipo decidió no cambiar la importación durante la implementación; los domicilios se registran desde la ficha, y la importación va en un spec posterior. Decidido al implementar.
- **No (por ahora):** buscar domicilios por nombre. El spec definió RUT o apellido; se pidió al probarlo y queda para un spec posterior.
- **Sí:** el Encargado de Terreno entra directo a `/domicilios/`. Es su primera función propia y reemplaza al marcador de posición.

---

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| El teléfono no puede leer el GPS porque el sistema corre sin HTTPS | El botón aparece solo en contexto seguro, las coordenadas siempre se pueden escribir o pegar, y `requirements-dev.txt` con `runserver_plus` permite probar con HTTPS en la red local. |
| Coordenadas invertidas o con el signo equivocado | Rango validado, el mapa de la ficha muestra a la vista dónde quedó el marcador, y el formato pegado desde un mapa respeta el orden. |
| El mapa no carga en terreno (sin señal) o en el CESFAM (sin internet) | Las coordenadas se escriben o se toman del GPS igual; el mapa muestra un aviso y no bloquea el formulario. El mapa sin conexión queda para el spec del RNF-03. |
| OpenStreetMap limita el uso de sus servidores de teselas | Uso bajo de un prototipo y atribución visible. Para producción, se evalúa un proveedor de teselas con contrato o un servidor propio. |
| OpenStreetMap bloquea las teselas sin avisar: responde 200 con la imagen «Access blocked», así que el aviso «No se pudo cargar el mapa» no aparece | Las teselas se piden con el origen como `Referer`, que es lo que exige su política. Si vuelve a pasar, el bloqueo se ve en el mapa mismo y las coordenadas se siguen escribiendo. Para producción, un proveedor de teselas con contrato. |
| Al pedir las teselas, OpenStreetMap ve qué zona del mapa se mira | No se envía ningún dato del paciente: solo las coordenadas de las teselas. Se acepta para el prototipo. |
| Una foto revela la ubicación exacta o datos del teléfono | Se quitan todos los metadatos al guardar y nunca se guarda el original. |
| Las fotos quedan expuestas en una URL pública | `MEDIA_ROOT` no se sirve por ninguna URL; solo la vista con permisos entrega cada foto, con `Cache-Control: private`. |
| Una imagen enorme o maliciosa agota la memoria del servidor | Límite de 10 MB antes de abrirla, tope de píxeles de Pillow y verificación de la imagen antes de procesarla. |
| Una carga del padrón deshace una corrección hecha en terreno | Los domicilios verificados nunca se tocan desde una carga; la diferencia queda como advertencia en la vista previa. |
| Rayén no exporta direcciones, o las exporta con otro formato | Las columnas son opcionales; sin ellas todo se registra en terreno. Cuando se conozca una exportación real, se ajusta el mapeo en `importacion.py`. |
| Sin señal en terreno no se puede guardar | Se acepta en este spec. El modo sin conexión es parte del spec de HU-14 y HU-15 (RNF-03). |
| El certificado autofirmado asusta o se instala como si fuera de producción | Solo en `requirements-dev.txt` y documentado como herramienta de prueba; `certs/` no se versiona. |
| Fotos de domicilios en el disco del servidor más tiempo del necesario | Tope de 3, borrar elimina el archivo y solo se toman fotos con propósito de ubicación. La política de retención queda para la puesta en producción. |
| El prototipo se interpreta como datos reales de pacientes | Direcciones, coordenadas y fotos sintéticas en la demostración, y el README lo declara. |

---

## Lo que **no** está en este spec

- Importación del padrón con domicilios y padrón sintético con direcciones (salieron durante la implementación).
- Búsqueda de domicilios por nombre.
- Asignación, mapa general de entregas, orden de visita, registro y reprogramación de entregas (HU-13 a HU-16).
- Capa satelital, mapas con clave de API y mapa sin conexión.
- Operación sin conexión (RNF-03) e instalación como PWA (RNF-09).
- Notificaciones y confirmación del paciente (HU-19, HU-22), y datos de contacto.
- Edición de domicilios por la QF o el funcionario, y domicilios de pacientes sin despacho.
- Geocodificación de direcciones y validación de coordenadas dentro de la comuna.
- HTTPS de producción y despliegue.
- Panel de mermas (HU-20) y bloqueo de login del SPEC 01.

Cada uno de esos, si se hace, va en su propio spec.

---

## Registro de verificación

Completado el 2026-10-28, durante la implementación. El paso 7 (importación con domicilios) y la parte del padrón sintético del paso 8 salieron de este spec por decisión del equipo, y el spec pasó a «Implementado».

Condiciones comunes:

- **Equipo:** Windows 11, Python 3.13.15 y Django 6.1.2 (el `requirements.txt` fija la 5.2.17; la del equipo es la que estaba instalada), Pillow 13.0.0, SQLite y Node 24.19.0.
- **Bases:** las pruebas automáticas usan la base de pruebas de Django. Las comprobaciones en el navegador usan una base aparte en el directorio temporal, con `cargar_datos_demo`, una cuenta de Encargado de Terreno, una de QF, pacientes sintéticos y una foto sintética. Las migraciones y `cargar_datos_demo` se probaron sobre copias de la base local de desarrollo (`db.sqlite3`), que no se tocó.
- **Navegador:** Edge sin cabeza controlado por el protocolo de DevTools desde Node, con `document.visibilityState` simulado como `hidden` (ver `CLAUDE.md`).

| Comprobación | Condiciones | Resultado |
| --- | --- | --- |
| Suite completa | `python manage.py test` y `node --test "pruebas_js/*.test.js"` | Cumple. 534 pruebas de Django y 28 de JavaScript, sin fallas |
| Migración `reparto` `0001` sobre datos existentes | Copia de la base local con 11 pacientes y 37 turnos | Cumple. Aplica sin errores, sin domicilios |
| Fotos sin metadatos | JPEG generado con orientación, fabricante y GPS en el EXIF (comprobados antes de subirlo) | Cumple. Queda derecho, en JPEG y sin EXIF |
| Lista de domicilios | Encargado y QF a 1366 px; Encargado a 360 px | Cumple. Resumen IG04, filtros, insignias con texto. A 360 px, el documento mide 360 px (sin desplazamiento horizontal) |
| Ficha y formulario | Encargado y QF a 1366 px; Encargado a 360 px | Cumple. La QF ve la ficha sin acciones. Sin desplazamiento horizontal a 360 px. Las coordenadas se muestran con punto decimal |
| Mapa en el formulario | Tocar el mapa; pegar «-36.470000, -72.180000» en la latitud con la longitud ya llena; a 1366 y 360 px | Cumple. Tocar llena los campos; lo pegado se reparte en los dos y el marcador se mueve |
| Mapa sin teselas | `Network.setBlockedURLs` con `*tile.openstreetmap.org*` | Cumple. Aparece «No se pudo cargar el mapa. Puede escribir las coordenadas.» y, con las coordenadas escritas con coma decimal, el formulario se guarda |
| Mapa de la ficha | Domicilio con coordenadas en el pueblo | Cumple. Se ven las calles de San Nicolás, el marcador y la atribución «Leaflet \| © colaboradores de OpenStreetMap» |
| Bloqueo de OpenStreetMap en uso real | Encontrado por el equipo en la ficha de Octavio: el mapa mostraba «Access blocked». Causa: sin `Referer` (Django envía `Referrer-Policy: same-origin`); comprobado con `curl`: sin `Referer` llega la imagen de bloqueo y con el origen, la tesela real. En las pruebas anteriores con Edge sin cabeza no había aparecido | Corregido con `referrerPolicy: 'strict-origin-when-cross-origin'` en la capa de teselas. En Edge, las 12 teselas de la ficha y las 9 del formulario salen con `Referer: http://127.0.0.1:8765/` (solo el origen) y el mapa muestra las calles. Falta confirmarlo en el navegador del equipo |
| Rediseño con mapa a pantalla completa (ajustado al implementar) | Edge sin cabeza a 1440×900 y 360×780: lista, ficha y formulario con la base de demostración más dos domicilios | Cumple. La hoja flota sobre el mapa en escritorio y queda bajo el mapa en el teléfono, sin desplazamiento horizontal a 360 px; la cámara llega a los marcadores y la placa queda al lado del de la ficha; sin errores de JavaScript. Falta probar la transición entre páginas y «Mostrar mi ubicación» en un teléfono real |
| Leaflet sin CDN ni clave | Archivos en `static/vendor/leaflet/`; prueba de Django que busca CDN y claves en las páginas | Cumple. La huella SHA-512 del paquete coincide con la del registro de npm |
| GPS con HTTPS | `runserver_plus` con certificado autofirmado en la IP local; Edge con ubicación simulada (`setGeolocationOverride`) | Cumple. Contexto seguro, el botón aparece y llena -36.488123 y -72.205099, con la precisión |
| GPS sin HTTPS | `runserver` por HTTP en la misma IP local | Cumple. No es contexto seguro y el botón no aparece |
| `certs/` fuera del repositorio | `git status --ignored` tras generar el certificado | Cumple. `dev.crt` y `dev.key` ignorados; solo `.gitkeep` se versiona |
| `cargar_datos_demo` dos veces | Copia de la base local, con su cuenta QF | Cumple. Las dos veces quedan 2 domicilios (Octavio pendiente, Pablo verificado) y 3 cambios en el historial |

**Pendiente:**

- Probar el GPS con un **teléfono real** en la misma red: solo se probó con una ubicación simulada en Edge.
- Que una persona del equipo siga la demostración del README desde cero (verificación del paso 9).

