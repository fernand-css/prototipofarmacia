# SPEC 01 — Autenticación por RUT y gestión de cuentas

> **Estado:** Aprobado
> **Depende de:** —
> **Fecha:** 2026-09-07
> **Objetivo:** Levantar el proyecto Django de la farmacia con inicio de sesión por RUT y una interfaz donde la Química Farmacéutica administre las cuentas de los funcionarios.

---

## Por qué existe este spec

El repositorio solo contiene el `README.md`. No hay proyecto Django, así que este spec crea la base sobre la que se montarán los specs siguientes (fila de turnos, pantalla de sala de espera, dashboard de métricas).

Se aprovecha ese punto de partida para definir el modelo de usuario personalizado. Django exige declarar `AUTH_USER_MODEL` **antes** de la primera migración: cambiarlo después obliga a borrar la base de datos. Es la única ventana limpia para hacerlo.

El ámbito se acota a la farmacia del CESFAM San Nicolás, no al recinto completo como sugiere el README. La administradora principal es la Química Farmacéutica (en adelante, QF).

---

## Alcance

**Dentro:**

- Proyecto Django `farmacia_turnos` con app `cuentas`, base SQLite y `requirements.txt`.
- Modelo `Usuario` propio, con el RUT como credencial de acceso en lugar de `username`.
- Tres roles: `QF` (administradora), `FUNCIONARIO` y `ENCARGADO_TERRENO`.
- Validación de RUT con dígito verificador y normalización a un formato único de almacenamiento.
- Vistas de inicio y cierre de sesión con plantillas Django y CSS propio.
- Redirección posterior al login según el rol.
- Cambio de contraseña obligatorio en el primer ingreso.
- Gestión de cuentas para la QF: crear, listar, editar, activar/desactivar y resetear contraseña.
- Página de inicio del funcionario como marcador de posición, hasta que exista el panel de atención.
- Política de sesión: cierre por inactividad y bloqueo temporal tras intentos fallidos.

**Fuera de alcance (para specs futuros):**

- Dashboard de métricas de la QF. Depende del modelo de atenciones, que todavía no existe.
- Generación de tickets, fila de turnos y panel de atención del funcionario.
- Pantalla de sala de espera.
- Cuentas para pacientes. La emisión de tickets y la pantalla quedan públicas, sin login.
- Recuperación de contraseña por correo electrónico. La recuperación la ejecuta la QF.
- Registro de `Usuario` en el admin de Django como interfaz de gestión.
- Permisos propios del Encargado de Terreno. En este spec tiene la misma página de inicio que el funcionario y no administra cuentas; sus funciones se definen en el spec que las necesite.
- Roles adicionales (técnico de farmacia, auxiliar, visor de pantalla).
- Migración a PostgreSQL y despliegue.

---

## Modelo de datos

Archivo `cuentas/models.py`:

```python
class Rol(models.TextChoices):
    QF = "qf", "Química Farmacéutica"
    FUNCIONARIO = "funcionario", "Funcionario"
    ENCARGADO_TERRENO = "encargado_terreno", "Encargado de Terreno"


class Usuario(AbstractBaseUser, PermissionsMixin):
    rut = models.CharField(max_length=10, unique=True)   # normalizado: "12345678-5"
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.FUNCIONARIO)
    debe_cambiar_password = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    fecha_alta = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "rut"
    REQUIRED_FIELDS = ["nombres", "apellidos"]
```

```python
class IntentoFallido(models.Model):
    rut = models.CharField(max_length=10, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    momento = models.DateTimeField(auto_now_add=True)
```

**Convenciones:**

- **Formato de almacenamiento del RUT:** sin puntos, con guion, dígito verificador en mayúscula. `12.345.678-5` y `123456785` se guardan ambos como `12345678-5`.
- La normalización ocurre en el formulario, antes de consultar la base. Nunca se guarda un RUT sin normalizar.
- `debe_cambiar_password` arranca en `True` para toda cuenta creada por la QF, y en `False` para la cuenta creada con `createsuperuser`.
- Las cuentas no se borran: `is_active = False` bloquea el acceso y conserva la fila, porque el historial de atenciones de specs futuros apuntará a ella.
- `IntentoFallido` se purga para un RUT cuando ese RUT inicia sesión correctamente.

---

## Plan de implementación

1. Crear entorno virtual y `requirements.txt` con `Django`. Ejecutar `django-admin startproject farmacia_turnos .`. Añadir `.gitignore` que excluya `venv/`, `__pycache__/`, `db.sqlite3` y `*.pyc`. **Verificación:** `python manage.py runserver` muestra la página de bienvenida de Django.
2. Crear la app `cuentas` y registrarla en `INSTALLED_APPS`. Configurar `LANGUAGE_CODE = "es-cl"` y `TIME_ZONE = "America/Santiago"`. **Verificación:** `python manage.py check` no reporta errores.
3. Escribir `cuentas/validators.py` con `normalizar_rut(valor)` y `validar_rut(valor)`, este último con el cálculo de módulo 11. **Verificación:** en `python manage.py shell`, `normalizar_rut("12.345.678-5")` devuelve `"12345678-5"` y `validar_rut("12345678-0")` lanza `ValidationError`.
4. Escribir `Usuario`, `Rol` y `UsuarioManager` en `cuentas/models.py`. `create_superuser` fuerza `rol=Rol.QF` y `debe_cambiar_password=False`. Declarar `AUTH_USER_MODEL = "cuentas.Usuario"` en settings. Ejecutar `makemigrations cuentas` y `migrate`. **Verificación:** `python manage.py createsuperuser` crea la cuenta de la QF pidiendo el RUT.
5. Crear `templates/base.html` con la estructura común y `static/css/estilos.css` con los estilos del sistema. Configurar `STATICFILES_DIRS` y el directorio `templates` en settings. **Verificación:** una vista de prueba que extiende `base.html` renderiza con los estilos aplicados.
6. Implementar el inicio y cierre de sesión: `LoginRutForm` en `cuentas/forms.py` que normaliza y valida el RUT, la plantilla `cuentas/login.html`, y las rutas `/` y `/salir/` en `cuentas/urls.py`. Configurar `LOGIN_URL`, `LOGIN_REDIRECT_URL` y `LOGOUT_REDIRECT_URL`. **Verificación:** la QF entra con su RUT en cualquier formato y sale con el enlace de cierre.
7. Implementar la vista `inicio`, que redirige a la gestión de usuarios si el rol es `QF` y al panel del funcionario en caso contrario (funcionario y encargado de terreno). Crear la plantilla `cuentas/panel_funcionario.html` como marcador de posición, con el nombre de quien inició sesión y el aviso de que el panel de atención llega en un spec posterior. **Verificación:** cada rol aterriza en su página tras el login.
8. Implementar el cambio de contraseña obligatorio: vista `cambiar_password` y middleware `CambioPasswordObligatorio`, que redirige a esa vista mientras `debe_cambiar_password` sea `True`, dejando pasar el cierre de sesión y los archivos estáticos. Al guardar, el campo pasa a `False`. **Verificación:** una cuenta nueva no puede navegar a ninguna otra página hasta cambiar su clave.
9. Implementar el mixin `SoloQF`, que devuelve 403 a quien no tenga rol `QF`, y la vista `usuarios_lista` con la tabla de funcionarios y su estado. **Verificación:** un funcionario que abre la URL de la lista recibe 403; la QF ve el listado.
10. Implementar `usuario_crear` con `UsuarioCrearForm`: RUT, nombres, apellidos, rol y contraseña inicial. La cuenta nace con `debe_cambiar_password=True`. **Verificación:** la QF crea un funcionario, cierra sesión, entra con esa cuenta y el sistema le exige cambiar la clave.
11. Implementar `usuario_editar` (nombres, apellidos y rol), `usuario_cambiar_estado` (activar y desactivar) y `usuario_resetear_password`, que fija una clave nueva y vuelve a poner `debe_cambiar_password=True`. **Verificación:** una cuenta desactivada no puede iniciar sesión; una reseteada entra y debe cambiar la clave.
12. Configurar la política de sesión en settings: `SESSION_COOKIE_AGE = 1800`, `SESSION_SAVE_EVERY_REQUEST = True` y `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`. **Verificación:** tras 30 minutos sin actividad, la siguiente petición redirige al login.
13. Implementar el bloqueo por intentos fallidos con el modelo `IntentoFallido`: 5 fallos del mismo RUT en 15 minutos bloquean ese RUT durante 15 minutos, con un mensaje que indica el tiempo restante. Un login correcto borra los intentos de ese RUT. **Verificación:** al sexto intento con clave errónea aparece el bloqueo, incluso con la contraseña correcta.
14. Actualizar el `README.md`, cuya sección "Instalación y Uso Local" está cortada a mitad, con los pasos reales de instalación y ejecución.

---

## Criterios de aceptación

- [ ] `python manage.py runserver` arranca sin errores desde un clon limpio siguiendo el README.
- [ ] `12.345.678-5`, `123456785` y `12345678-5` inician sesión en la misma cuenta.
- [ ] Un RUT con dígito verificador incorrecto es rechazado en el formulario, con mensaje visible.
- [ ] Un RUT ya registrado no puede crearse por segunda vez, en ningún formato.
- [ ] La QF, tras iniciar sesión, aterriza en el listado de usuarios.
- [ ] El funcionario, tras iniciar sesión, aterriza en su página de inicio y ve su nombre.
- [ ] Un funcionario que abre la URL de gestión de usuarios recibe 403.
- [ ] La QF puede crear y editar cuentas con el rol Encargado de Terreno; esa cuenta aterriza en la página de inicio del funcionario y recibe 403 en la gestión de usuarios.
- [ ] Una cuenta recién creada por la QF es redirigida al cambio de contraseña en cualquier URL que visite.
- [ ] Tras cambiar la contraseña, esa cuenta navega con normalidad y no vuelve a ser redirigida.
- [ ] Una cuenta desactivada por la QF recibe error al iniciar sesión y sigue apareciendo en el listado.
- [ ] Tras resetear la contraseña, la cuenta entra con la clave nueva y debe cambiarla.
- [ ] Al sexto intento fallido consecutivo, el mismo RUT queda bloqueado aunque la contraseña sea correcta.
- [ ] Un login correcto reinicia el contador de intentos fallidos de ese RUT.
- [ ] Cerrar el navegador y volver a abrirlo exige iniciar sesión de nuevo.
- [ ] Ninguna página del sistema es accesible sin sesión iniciada, salvo el propio login.

---

## Decisiones

- **Sí:** `AbstractBaseUser` con el RUT como `USERNAME_FIELD`. El RUT es el identificador que el funcionario ya conoce y es único por persona. Se decide ahora porque es irreversible tras la primera migración.
- **No:** `User` estándar más un perfil `OneToOne`. Obligaría a duplicar el RUT en `username` o a escribir un backend propio, y cruzaría dos tablas en cada consulta.
- **No:** `AbstractUser` con un campo `rut` añadido. Arrastra el campo `username` sin uso.
- **Sí:** validación de dígito verificador y normalización. Evita cuentas duplicadas con distinto formato del mismo RUT.
- **Sí:** contraseña inicial definida por la QF y cambio obligatorio en el primer ingreso. No requiere servidor de correo, que el CESFAM probablemente no tenga configurado.
- **No:** recuperación por correo. Añade dependencia de SMTP y exige un correo por funcionario, que no todos tienen.
- **Sí:** desactivar en lugar de borrar. El historial de atenciones de specs futuros necesita que el usuario siga existiendo.
- **Sí:** cierre por inactividad y bloqueo por intentos. Los funcionarios comparten el computador del mesón, y una sesión abierta permitiría atender con el nombre de otro.
- **No:** `django-axes` para el bloqueo. Una tabla de intentos y una consulta por ventana de tiempo bastan, sin sumar dependencias al MVP.
- **Sí:** el admin de Django queda solo como acceso técnico del desarrollador. La interfaz de la QF es una vista propia, en español y sin modelos internos a la vista.
- **Sí:** la primera cuenta QF se crea con `manage.py createsuperuser`. Resuelve el arranque sin necesitar una pantalla de registro pública.
- **Sí:** plantillas Django con CSS propio. Es lo que declara el README y no depende de un CDN externo, que en una red restringida de CESFAM podría no cargar.
- **Sí:** Encargado de Terreno como rol propio y no como un funcionario con una marca. Sus funciones difieren de las del mesón, y separarlo ahora evita migrar datos de usuarios cuando se definan. Mientras tanto no tiene permisos distintos a los del funcionario.
- **Sí:** proyecto `farmacia_turnos`. Nombra el dominio realmente acotado y deja espacio limpio para una futura app `turnos`.

---

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Cambiar `AUTH_USER_MODEL` después de migrar obliga a borrar la base | El modelo `Usuario` se define en el paso 4, antes de la primera migración. Ningún paso anterior ejecuta `migrate`. |
| El bloqueo por RUT permite molestar a un funcionario bloqueándolo a propósito | El bloqueo dura 15 minutos y la QF puede resetear la contraseña. Si aparece en uso real, se evalúa bloquear por IP en otro spec. |
| La QF conoce la contraseña inicial de cada funcionario | El cambio obligatorio en el primer ingreso deja la clave definitiva fuera de su alcance. |
| El cierre por inactividad interrumpe una atención en curso | 30 minutos superan con holgura una entrega de medicamentos. El valor queda en `settings.py`, en un solo lugar, para ajustarlo tras probarlo en el mesón. |
| Datos de salud bajo la Ley 19.628 | Este spec no almacena datos de pacientes. La restricción se documenta aquí para el spec de tickets. |

---

## Lo que **no** está en este spec

- Dashboard de métricas de la QF.
- Tickets, fila de turnos y panel de atención.
- Pantalla de sala de espera.
- Cuentas de pacientes.
- Recuperación de contraseña por correo.
- Roles más allá de QF, funcionario y encargado de terreno.
- PostgreSQL y despliegue.

Cada uno de esos, si se hace, va en su propio spec.
