# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proyecto

MVP en Django 5.2 del sistema de turnos de la **farmacia del CESFAM San Nicolás** (Chile). Código, plantillas, mensajes y commits están en español; mantén ese idioma. El README describe el MVP completo (tickets, pantalla de sala de espera, panel de atención, historial), pero hoy solo existe la app `cuentas` (spec 01). El resto llega en specs posteriores.

## Comandos

```bash
pip install -r requirements.txt     # Django, asgiref, sqlparse, tzdata
python manage.py migrate
python manage.py runserver          # http://127.0.0.1:8000/
python manage.py test               # cuentas/tests.py (solo cubre roles por ahora)
python manage.py test cuentas.tests.RolesTests.test_qf_crea_un_encargado_de_terreno   # un solo test
python manage.py createsuperuser    # pide RUT, nombres, apellidos y contraseña
```

No hay linter ni build configurados. El `venv/` del repositorio se creó en otro equipo (su `pyvenv.cfg` apunta a un Python que no existe aquí) y está en `.gitignore`: si no arranca, créalo de nuevo con `python -m venv venv` en vez de repararlo. `db.sqlite3` también está ignorado.

## Flujo de trabajo por specs

El trabajo se organiza en `specs/NN-nombre.md` (alcance, modelo, plan, criterios de aceptación, decisiones y riesgos), con una rama por spec (`spec-01-autenticacion-y-cuentas`). Lee el spec correspondiente antes de implementar. Ojo: el spec 01 declara dentro de su alcance un bloqueo temporal tras intentos fallidos de login, que **no está implementado** en el código (ni middleware, ni librería).

## Arquitectura

- `farmacia_turnos/`: configuración. Una sola app, `cuentas`, montada en la raíz (`path("", include("cuentas.urls"))`); el login vive en `/`.
- **Usuario propio** (`cuentas.Usuario`, `AUTH_USER_MODEL`): el **RUT reemplaza al username** (`USERNAME_FIELD = "rut"`). Se guarda normalizado (`12345678-5`, sin puntos, K mayúscula). Toda entrada de RUT pasa por `cuentas/validators.py` (`normalizar_rut` + `validar_rut` con módulo 11); el login (`LoginRutForm.clean_username`) normaliza antes de buscar, y `UsuarioManager.create_user` hace lo mismo. Cambiar `AUTH_USER_MODEL` después de migrar obliga a borrar la BD.
- **Roles** (`Rol`): `qf` (Química Farmacéutica, administradora), `funcionario` y `encargado_terreno`. `inicio` redirige por rol: QF a la gestión de usuarios, cualquier otro rol al panel del funcionario (el Encargado de Terreno aún no tiene permisos ni página propios). `SoloQF` (`mixins.py`) protege las vistas de administración de cuentas con 403 para otros roles. La gestión de cuentas se hace en vistas propias, no en el admin de Django.
- **Cambio de contraseña obligatorio:** `Usuario.debe_cambiar_password` (por defecto `True`) activa el middleware `CambioPasswordObligatorio`, que redirige a `/cambiar-password/` todo lo que no sea esa ruta, el logout o `STATIC_URL`. La QF crea cuentas con contraseña inicial y la resetea con `UsuarioResetearPasswordView`, que vuelve a activar la bandera. Toda ruta nueva queda bloqueada por este middleware hasta que el usuario cambie su clave.
- **Sesión:** política pensada para un equipo compartido en el mesón (30 min de inactividad, renovada en cada request, cierre al cerrar el navegador). Ver el final de `settings.py`.

## Frontend

Plantillas Django sin build step. `templates/base.html` es la base (bloques `titulo`, `clase_body`, `contenido`); las plantillas de cada app viven en `<app>/templates/<app>/`. Los campos de formulario se renderizan con `templates/includes/campo.html` (añade el botón mostrar/ocultar a los campos de contraseña).

- **Alpine.js 3.14.9** está copiado en `static/js/alpine.min.js` (no se usa CDN: el CESFAM puede estar sin internet). Se usa para interacciones pequeñas inline (`x-data`, `@click`); no hay otro JS.
- **CSS** único en `static/css/estilos.css`, con clases en español estilo BEM (`.tarjeta--angosta`, `.boton--secundario`). La paleta es fría (azul petróleo, sin tonos cálidos salvo el rojo de errores y el ámbar de advertencias) y está en variables `:root` (`--primario`, `--acento`, ...). Es la complementaria del naranja de la ilustración del login; el texto blanco sobre el primario cumple contraste (6.0:1). El fondo del login (`static/img/fondo-login.png`) se activa solo con `{% block clase_body %}pagina-login{% endblock %}`.
- `settings.py` usa `es-cl` y `America/Santiago`.
