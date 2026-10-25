# 🏥 Sistema de Turnos - CESFAM San Nicolás (MVP)

Un Producto Mínimo Viable (MVP) desarrollado en Django para optimizar la gestión de filas y mejorar los tiempos de espera de los pacientes en el Centro de Salud Familiar (CESFAM) San Nicolás. 

Este sistema busca modernizar la entrega de números de atención, proporcionando una interfaz clara tanto para los pacientes en la sala de espera como para los funcionarios de salud.

## ✨ Funcionalidades (MVP)

* **Generación de Tickets:** Creación rápida de números de atención para los pacientes al ingresar al recinto.
* **Módulo de Pantalla (Sala de Espera):** Pantalla pública con el último turno llamado y su ventanilla, y los llamados anteriores del día. Se actualiza sola cada 2 segundos y avisa cada llamado nuevo con un resalte y, si se activa, con una campanilla y la voz. No muestra datos personales.
* **Panel de Funcionario:** Interfaz para que el personal de salud pueda llamar al siguiente paciente en la fila, pausar atenciones o derivar.
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

3. (Opcional) Carga datos de demostración: 4 ventanillas y pacientes y recetas crónicas simuladas, que hacen las veces de Rayén. Imprime los RUT de prueba y se puede ejecutar más de una vez. No lo uses con datos reales:

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
| `/ventanillas/` | QF | Crear, habilitar y deshabilitar ventanillas |
| `/usuarios/` | QF | Gestión de cuentas |
| `/admin/` | Acceso técnico | Pacientes y recetas simulados, y corrección de turnos |

### Cómo se ordena la fila

El paciente solo digita su RUT y el sistema deduce su categoría: **preferencial** (60 años o más, discapacidad o embarazo), **general** en otro caso, y **urgencia**, que emite un funcionario desde el panel. Los pacientes de despacho a domicilio (postrados o mayores de 80 años) reciben un aviso, y quienes tienen recetas crónicas vencidas o con las entregas agotadas son derivados al mesón para su renovación.

Al llamar, la urgencia va primero y luego se intercalan **2 generales por cada preferencial** (se ajusta con `TURNOS_GENERALES_POR_PREFERENCIAL` en `farmacia_turnos/settings.py`); dentro de cada categoría manda el orden de llegada. Un paciente marcado como ausente (se habilita 60 segundos después del último llamado) debe sacar un turno nuevo.

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

Cada cambio de alcance está documentado en `specs/`.
