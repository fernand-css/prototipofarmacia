# 🏥 Sistema de Turnos - CESFAM San Nicolás (MVP)

Un Producto Mínimo Viable (MVP) desarrollado en Django para optimizar la gestión de filas y mejorar los tiempos de espera de los pacientes en el Centro de Salud Familiar (CESFAM) San Nicolás. 

Este sistema busca modernizar la entrega de números de atención, proporcionando una interfaz clara tanto para los pacientes en la sala de espera como para los funcionarios de salud.

## ✨ Funcionalidades (MVP)

* **Generación de Tickets:** Creación rápida de números de atención para los pacientes al ingresar al recinto. El ticket indica la espera estimada, calculada con los tiempos reales de atención.
* **Módulo de Pantalla (Sala de Espera):** Pantalla pública con el último turno llamado y su ventanilla, y los llamados anteriores del día. Se actualiza sola cada 2 segundos y avisa cada llamado nuevo con un resalte y, si se activa, con una campanilla y la voz. No muestra datos personales.
* **Panel de Funcionario:** Interfaz para que el personal de salud pueda llamar al siguiente paciente en la fila, pausar atenciones o derivar. Si el paciente trae una receta crónica, muestra en qué entrega va («Entrega 3 de 6») y cuándo vence.
* **Preparación y preparados pendientes de retiro:** Al recibir la receta en la ventanilla, la preparación aparece en una pantalla donde quien prepara la marca «Lista»; recién entonces se puede entregar. Si el paciente se fue antes de recibirla, lo preparado queda en «Preparados» y se le entrega cuando vuelva, sin pasar por la fila.
* **Padrón y recetas de Rayén:** La Química Farmacéutica carga un archivo CSV o Excel con los pacientes crónicos y postrados y sus recetas vigentes, revisa una vista previa (qué se crea, qué se actualiza y qué filas se rechazan, con su motivo) y recién entonces la aplica. Así no se digita cada receta en dos sistemas.
* **Domicilios de los pacientes con despacho a domicilio:** El Encargado de Terreno registra el sector, la dirección y las referencias de cada paciente postrado o mayor de 80 años, marca la casa en un mapa (tocándolo o con el GPS del teléfono), agrega hasta 3 fotos y la verifica en terreno. Cada cambio queda en un historial.
* **Historial Básico:** Registro de tiempos de emisión y atención para métricas futuras.

## 🛠️ Tecnologías Utilizadas

* **Backend:** Python 3.x, Django
* **Base de Datos:** SQLite (Configurado para el MVP, escalable a PostgreSQL)
* **Frontend:** HTML5, CSS3, JavaScript (Plantillas de Django)
* **Control de Versiones:** Git / GitHub

## 🚀 Instalación y Uso Local

Sigue estos pasos para ejecutar el proyecto en tu entorno de desarrollo local.

1. Crea y activa un entorno virtual, e instala las dependencias:

   ```bash
   python -m venv venv
   venv\Scripts\activate          # en Linux/macOS: source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Crea la base de datos y la cuenta de la Química Farmacéutica (administradora). El RUT es el usuario de acceso:

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

3. (Opcional) Carga datos de demostración: 4 ventanillas, pacientes y recetas crónicas simuladas, que hacen las veces de Rayén, 30 atenciones de los 3 días anteriores para que el tótem pueda estimar la espera, y dos domicilios (uno pendiente y uno verificado). Las atenciones y los domicilios quedan a nombre de la primera cuenta de Química Farmacéutica, así que crea la cuenta antes (paso 2); sin ella el comando avisa y carga el resto. Imprime los RUT de prueba y se puede ejecutar más de una vez (otro día agrega las atenciones de los días que falten). No lo uses con datos reales:

   ```bash
   python manage.py cargar_datos_demo
   ```

4. Levanta el servidor y abre <http://127.0.0.1:8000/>:

   ```bash
   python manage.py runserver
   ```

5. Para correr las pruebas automatizadas (unos segundos). Las de JavaScript cubren qué anuncia la pantalla de la sala y necesitan Node 21 o superior, sin instalar nada más:

   ```bash
   python manage.py test
   node --test "pruebas_js/*.test.js"
   ```

### Rutas principales

| Ruta | Quién | Qué hace |
| --- | --- | --- |
| `/` | Todos | Inicio de sesión con RUT |
| `/totem/` | Público, sin login | Tótem donde el paciente digita su RUT y recibe su turno (se puede imprimir) |
| `/sala/` | Público, sin login | Pantalla de la sala de espera: último llamado, llamados anteriores y anuncio con voz |
| `/atencion/` | Funcionario y QF | Panel de atención: abrir ventanilla, llamar, re-llamar, iniciar, finalizar, ausente, turno de urgencia y fila de espera |
| `/preparacion/` | Funcionario y QF | Recetas recibidas en las ventanillas: se marcan «Lista» cuando están preparadas |
| `/preparados/` | Funcionario y QF | Preparados que el paciente no retiró: buscar por RUT o apellido y entregar sin pasar por la fila |
| `/recetas/` | Funcionario y QF | Recetas crónicas de un RUT: entregas realizadas y restantes, vencimiento y estado |
| `/domicilios/` | Encargado de Terreno (edita) y QF (consulta) | Domicilios de los pacientes con despacho a domicilio: lista, ficha con mapa y fotos, verificación e historial |
| `/ventanillas/` | QF | Crear, habilitar y deshabilitar ventanillas |
| `/padron/` | QF | Cargar el padrón y las recetas vigentes desde un archivo de Rayén, con vista previa y bitácora |
| `/usuarios/` | QF | Gestión de cuentas |
| `/admin/` | Acceso técnico | Correcciones puntuales de pacientes, recetas y turnos |

### Cómo se ordena la fila

El paciente solo digita su RUT y el sistema deduce su categoría: **preferencial** (60 años o más, discapacidad o embarazo), **general** en otro caso, y **urgencia**, que emite un funcionario desde el panel. Los pacientes de despacho a domicilio (postrados o mayores de 80 años) reciben un aviso, y quienes tienen recetas crónicas vencidas o con las entregas agotadas son derivados al mesón para su renovación.

Al llamar, la urgencia va primero y luego se intercalan **2 generales por cada preferencial** (se ajusta con `TURNOS_GENERALES_POR_PREFERENCIAL` en `farmacia_turnos/settings.py`); dentro de cada categoría manda el orden de llegada. Un paciente marcado como ausente (se habilita 60 segundos después del último llamado) debe sacar un turno nuevo.

### Preparación de recetas y preparados pendientes de retiro

La receta se prepara mientras el paciente espera en la ventanilla:

1. **Recepción.** Al pulsar «Iniciar atención», la receta queda recibida y aparece en «Preparación», con el número de turno, la ventanilla y el paciente. Las urgencias van primero.
2. **Lista.** Quien prepara (puede ser otra persona) pulsa «Marcar lista». El panel de la ventanilla lo ve en unos segundos, sin recargar.
3. **Entrega.** «Finalizar atención» se habilita recién con la preparación lista: registra la entrega y, si hay receta crónica, suma una entrega.
4. **No retiró.** Si el paciente se fue antes de recibir sus medicamentos, el funcionario pulsa «No retiró» y el turno queda ausente. Si la preparación ya estaba lista, pasa a «Preparados»; si no, se anula y el paciente que vuelva saca un turno nuevo.
5. **Retiro posterior.** En «Preparados» se busca al paciente por RUT o apellido y se pulsa «Entregar». Se conserva la fecha original de la preparación. Si entretanto la receta crónica se agotó, la entrega se rechaza y hay que consultar con la Química Farmacéutica.

Los preparados pendientes no vencen: quedan en la lista hasta que se entregan.

### Espera estimada en el ticket

El ticket del tótem dice, por ejemplo, «Espera estimada: unos 25 minutos». Se calcula al emitirlo:

> (turnos que se llamarán antes + turnos en atención) × tiempo promedio de atención ÷ ventanillas abiertas

* **Turnos por delante:** se cuentan en el orden real de la fila (urgencia primero y 2 generales por cada preferencial).
* **Promedio:** el tiempo desde la recepción hasta la entrega de las atenciones de los últimos 30 días. Con menos de 20 atenciones registradas, o sin ventanillas abiertas, el ticket no muestra estimación.
* **Redondeo:** hacia arriba, a múltiplos de 5 minutos. Si da menos, dice «menos de 5 minutos».
* **Al imprimir:** lleva «calculada a las HH:MM», porque el papel no se actualiza. Volver a digitar el RUT en el tótem muestra el mismo turno con la estimación recalculada.

Las constantes `TURNOS_DIAS_HISTORIAL_ESPERA`, `TURNOS_MUESTRAS_MINIMAS_ESPERA` y `TURNOS_MINUTOS_REDONDEO_ESPERA` están al final de `farmacia_turnos/settings.py`.

### Domicilios de los pacientes con despacho a domicilio

Los pacientes postrados y los mayores de 80 años reciben sus medicamentos en casa. En «Domicilios», el **Encargado de Terreno** (que entra directo a esa página) registra dónde vive cada uno; la Química Farmacéutica puede consultarlo, pero no editarlo.

* **La lista** muestra cuántos domicilios están verificados (el indicador IG04) y cuántos pacientes siguen sin dirección. Se filtra por sector (Verde, Azul, Rojo) y por estado, y se busca por RUT o apellido.
* **La ficha** de cada paciente tiene el sector, la dirección, las referencias («casa roja frente a la escuela»), las coordenadas en un mapa, las fotos y el historial de cambios.
* **Para marcar la casa en el mapa**, al editar se toca el mapa o se arrastra el marcador, y las coordenadas se llenan solas. También se pueden escribir, o pegar las dos desde otro mapa en el campo de latitud («-36.50, -72.21»). Con HTTPS aparece además «Usar mi ubicación actual», que toma el GPS del teléfono.
* **Verificar** significa haber estado en el lugar, y exige coordenadas. Editar después un domicilio verificado lo deja verificado; si ya no corresponde (por ejemplo, el paciente se cambió de casa), se usa «Marcar pendiente» con un motivo, que queda en el historial.
* **Fotos:** hasta 3 por domicilio, JPEG o PNG de hasta 10 MB. El sistema las achica y les quita los datos que guarda el teléfono (la ubicación exacta y el modelo), y solo se ven con sesión de Encargado de Terreno o QF: no hay una dirección pública para abrirlas. Se guardan en la carpeta `media/`, que no se sube al repositorio.
* **El mapa** usa OpenStreetMap, gratis y sin clave. Necesita internet: sin conexión, avisa «No se pudo cargar el mapa» y las coordenadas se escriben a mano.
* **Por ahora, el padrón de Rayén no trae direcciones:** se registran desde la ficha. Agregarlas a la importación queda para una etapa posterior.
* **La búsqueda** es por RUT (con o sin puntos) o por apellido; buscar por nombre queda para una etapa posterior.

#### Probar el GPS desde un teléfono

El navegador solo deja usar el GPS en una página con HTTPS (o en `localhost`). Para probarlo desde un teléfono conectado a la misma red que el computador:

```bash
pip install -r requirements-dev.txt
set TURNOS_HOSTS_LOCALES=192.168.1.20       # la IP del computador en la red local (en PowerShell: $env:TURNOS_HOSTS_LOCALES="192.168.1.20")
python manage.py runserver_plus 0.0.0.0:8443 --cert-file certs/dev.crt
```

En el teléfono, abre `https://192.168.1.20:8443/` (con tu IP). La primera vez el navegador advierte que el certificado no es de confianza, porque es autofirmado: acéptalo para seguir. **Es solo para pruebas**: el certificado se genera en `certs/` y no se sube al repositorio.

### Padrón y recetas de Rayén

Rayén no ofrece una integración, así que los pacientes crónicos y postrados y sus recetas vigentes se cargan desde un archivo exportado. En «Padrón» (solo la Química Farmacéutica):

1. **Prepara el archivo.** Se acepta `.csv` (separado por `;` o `,`, en UTF-8 o en la codificación con que guarda Excel en Windows) o `.xlsx` (se lee la primera hoja), de hasta 5 MB y 5.000 filas. «Descargar plantilla» entrega un CSV con los encabezados y una fila de ejemplo.
2. **Súbelo con «Revisar archivo».** Todavía no se guarda nada: el sistema muestra cuántos pacientes y recetas se crean, se actualizan o quedan sin cambios, las primeras filas (para ver que las tildes y la «ñ» se lean bien) y cada fila rechazada con su motivo. Los rechazos se pueden descargar en CSV.
3. **Aplica la carga** antes de una hora, o cancélala. Pasada la hora se descarta y hay que subir el archivo de nuevo.

Columnas (la primera fila son los encabezados; no importan mayúsculas, tildes ni el orden, y las columnas extra se ignoran):

| Columna | Obligatoria | Formato |
| --- | --- | --- |
| `rut` | Sí | Con o sin puntos y guion |
| `nombres`, `apellidos` | Sí | Texto, hasta 100 caracteres |
| `fecha_nacimiento` | Sí | `dd-mm-aaaa`, `dd/mm/aaaa`, `aaaa-mm-dd` o fecha de Excel |
| `discapacidad`, `embarazada`, `postrado` | No | `si`, `no`, `1`, `0` o vacía (vacía es no) |
| `folio` | Si hay receta | El folio de la receta en Rayén, hasta 20 caracteres sin espacios |
| `fecha_emision` | Si hay receta | Igual que `fecha_nacimiento` |
| `vigencia_meses`, `entregas_maximas` | Si hay receta | Entero de 1 a 24 |
| `entregas_realizadas` | No | Entero de 0 al máximo; vacía es 0 |

Cada fila es un paciente con a lo sumo una receta: un paciente con dos recetas va en dos filas con los mismos datos, y uno sin receta va con esas columnas vacías. Reglas de la carga:

* El paciente se reconoce por su RUT y la receta por su folio. Lo que ya existe se actualiza con lo que trae el archivo, y **lo que no viene en el archivo no se toca** (no se borra ni se desactiva).
* **El contador de entregas nunca baja:** si el sistema registra más entregas que el archivo, se conservan las del sistema y la vista previa lo advierte.
* **Una renovación médica es una receta con folio nuevo.** Al cargarla, el tótem vuelve a dar turno al paciente que estaba bloqueado.
* Las filas inválidas no detienen la carga de las válidas. Un archivo sin alguna columna obligatoria, demasiado grande o ilegible se rechaza entero.
* El archivo subido no se guarda en el servidor. La bitácora conserva quién lo subió, cuándo, su nombre, tamaño y huella, y el resultado.

Para probar sin datos reales, `generar_padron_sintetico` escribe un padrón inventado de 670 pacientes (70 postrados y 600 mayores de 80 años, con 1 o 2 recetas cada uno) más 10 filas inválidas a propósito:

```bash
python manage.py generar_padron_sintetico --salida padron.csv      # o padron.xlsx
python manage.py generar_padron_sintetico --salida padron.csv --pacientes 50 --invalidas 4 --semilla 2
```

### Pantalla de la sala de espera

Abre `/sala/` en el televisor o monitor de la sala, a pantalla completa (F11). Muestra en grande el último turno llamado con su ventanilla y, al lado, los 4 llamados anteriores del día. Se actualiza sola cada 2 segundos: no hay que recargarla. Nunca muestra nombres, RUT, categoría ni estado de los turnos.

* **Ábrela en un navegador sin sesión** (o en una ventana privada). Si en ese navegador hay una sesión de funcionario abierta, la pantalla igual funciona, pero esa sesión queda expuesta en un equipo público, y si tiene un cambio de contraseña pendiente, la sala termina en esa página.
* **Voz:** el botón «Activar voz», abajo a la derecha, se maneja con el mouse, con un toque o con el teclado (Tab y luego Enter o Espacio). Con la voz activa, cada llamado nuevo suena con una campanilla y la frase «Turno P 12, ventanilla 2» dicha dos veces. El monitor recuerda la elección, pero al reiniciar el navegador este no deja sonar hasta que alguien interactúa con la página: la pantalla muestra «Toque la pantalla para reactivar la voz» y basta un toque, un clic o una tecla.
* **Voces:** se usan las del navegador. Conviene tener una voz en español instalada en el sistema operativo, porque las voces en línea del navegador fallan si el CESFAM se queda sin internet. Si no hay ninguna voz en español, suena solo la campanilla y la pantalla lo indica.
* **Modo kiosco (opcional):** para no tener que tocar la pantalla cada vez que se reinicia el equipo, se puede abrir el navegador en modo kiosco y con permiso para sonar sin interacción. En Windows, con Edge:

  ```bash
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --kiosk http://127.0.0.1:8000/sala/ --edge-kiosk-type=fullscreen --autoplay-policy=no-user-gesture-required
  ```

  Pruébalo en el equipo de la sala antes de dejarlo así: depende de cómo se abra el navegador.
* **Sin conexión:** si la pantalla pierde contacto con el servidor, conserva lo último que mostró y avisa «Sin conexión. Información pendiente de actualización.». Se reconecta sola. Al volver anuncia solo los llamados de los últimos 30 segundos; los anteriores quedan a la vista en la lista, sin anunciarse.
* **Después de actualizar el sistema, recarga la sala** (F5): puede pasar días abierta con la versión anterior de la página.

### Demostración: del tótem a la sala

Con los datos de demostración, en un solo equipo:

1. `python manage.py cargar_datos_demo` y `python manage.py runserver`.
2. Abre <http://127.0.0.1:8000/sala/> en una ventana privada y pulsa «Activar voz».
3. En otra ventana, abre <http://127.0.0.1:8000/totem/> y digita uno de los RUT de prueba que imprimió `cargar_datos_demo`: el tótem entrega el número de turno.
4. En otra ventana normal, inicia sesión en <http://127.0.0.1:8000/> con la cuenta de la Química Farmacéutica (o de un funcionario), entra a «Atención», elige una ventanilla y pulsa «Llamar siguiente».
5. En unos 2 segundos la sala muestra el número y la ventanilla, la tarjeta pulsa, aparece «Nuevo llamado» y se anuncia con la voz.

### Demostración: del padrón al panel

1. `python manage.py cargar_datos_demo` y `python manage.py generar_padron_sintetico --salida padron.csv`.
2. Con la cuenta de la Química Farmacéutica, entra a «Padrón», sube `padron.csv` con «Revisar archivo» y revisa la vista previa: 670 pacientes y 1.009 recetas nuevos, y 10 filas rechazadas con su motivo. Pulsa «Aplicar carga».
3. En «Recetas», busca el RUT 10.000.008-3 (Agustín, paciente de demostración con la receta agotada): su receta dice «Agotada» y el tótem no le da turno.
4. Descarga la plantilla y reemplaza la fila de ejemplo por una de ese paciente con un **folio nuevo** (la receta renovada), con `entregas_realizadas` en 0. Súbela y aplícala: ahora `/totem/` le entrega un turno.
5. Llámalo desde «Atención»: el turno en curso muestra «Entrega 1 de» las entregas máximas que pusiste, y la fecha de vencimiento.

### Demostración: preparación, «No retiró» y espera estimada

1. Con la cuenta de la Química Farmacéutica creada, `python manage.py cargar_datos_demo` y `python manage.py runserver`.
2. Inicia sesión, entra a «Atención» y elige una ventanilla.
3. En <http://127.0.0.1:8000/totem/>, digita `10000007-5` (Carla, receta crónica vigente): el ticket muestra la espera estimada.
4. En «Atención», «Llamar siguiente» e «Iniciar atención»: el turno dice «En preparación» y «Finalizar atención» está deshabilitado.
5. En otra pestaña, «Preparación» muestra la receta: pulsa «Marcar lista». En unos segundos el panel dice «Lista».
6. Pulsa «No retiró» y confirma. En «Preparados», busca «Demo» o `10000007-5` y pulsa «Entregar»: «Recetas» muestra una entrega más.

### Demostración: domicilios

1. Con la cuenta de la Química Farmacéutica creada, `python manage.py cargar_datos_demo` y `python manage.py runserver`.
2. Con esa cuenta, en «Usuarios», crea una cuenta de **Encargado de Terreno**, y entra con ella (te pedirá cambiar la contraseña).
3. «Domicilios» muestra 1 de 2 domicilios verificados. Abre a Octavio (pendiente, sin coordenadas): «Verificar» está deshabilitado.
4. «Editar», toca el mapa sobre la casa y guarda. Ahora sí puedes pulsar «Verificar».
5. Sube una foto y revisa el historial. Con la cuenta de la Química Farmacéutica, la misma ficha se ve sin botones.

Cada cambio de alcance está documentado en `specs/`.
