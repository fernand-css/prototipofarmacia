# 🏥 Sistema de Turnos - CESFAM San Nicolás (MVP)

Un Producto Mínimo Viable (MVP) desarrollado en Django para optimizar la gestión de filas y mejorar los tiempos de espera de los pacientes en el Centro de Salud Familiar (CESFAM) San Nicolás. 

Este sistema busca modernizar la entrega de números de atención, proporcionando una interfaz clara tanto para los pacientes en la sala de espera como para los funcionarios de salud.

## ✨ Funcionalidades (MVP)

* **Generación de Tickets:** Creación rápida de números de atención para los pacientes al ingresar al recinto.
* **Módulo de Pantalla (Sala de Espera):** Vista actualizada en tiempo real con los números que están siendo llamados y el box de atención correspondiente.
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

5. Para correr las pruebas automatizadas (unos segundos):

   ```bash
   python manage.py test
   ```

### Rutas principales

| Ruta | Quién | Qué hace |
| --- | --- | --- |
| `/` | Todos | Inicio de sesión con RUT |
| `/totem/` | Público, sin login | Tótem donde el paciente digita su RUT y recibe su turno (se puede imprimir) |
| `/atencion/` | Funcionario y QF | Panel de atención: abrir ventanilla, llamar, re-llamar, iniciar, finalizar, ausente, turno de urgencia y fila de espera |
| `/ventanillas/` | QF | Crear, habilitar y deshabilitar ventanillas |
| `/usuarios/` | QF | Gestión de cuentas |
| `/admin/` | Acceso técnico | Pacientes y recetas simulados, y corrección de turnos |

### Cómo se ordena la fila

El paciente solo digita su RUT y el sistema deduce su categoría: **preferencial** (60 años o más, discapacidad o embarazo), **general** en otro caso, y **urgencia**, que emite un funcionario desde el panel. Los pacientes de despacho a domicilio (postrados o mayores de 80 años) reciben un aviso, y quienes tienen recetas crónicas vencidas o con las entregas agotadas son derivados al mesón para su renovación.

Al llamar, la urgencia va primero y luego se intercalan **2 generales por cada preferencial** (se ajusta con `TURNOS_GENERALES_POR_PREFERENCIAL` en `farmacia_turnos/settings.py`); dentro de cada categoría manda el orden de llegada. Un paciente marcado como ausente (se habilita 60 segundos después del último llamado) debe sacar un turno nuevo.

Cada cambio de alcance está documentado en `specs/`.
