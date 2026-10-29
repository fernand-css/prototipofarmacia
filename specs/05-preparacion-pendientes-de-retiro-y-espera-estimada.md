# SPEC 05 — Preparación de recetas, preparados pendientes de retiro y espera estimada

> **Estado:** Aprobado
> **Depende de:** SPEC 01, SPEC 02 y SPEC 04
> **Fecha:** 2026-10-28
> **Objetivo:** Registrar cuándo se recibe y cuándo queda lista la preparación de cada atención, guardar los preparados que el paciente no retiró para entregarlos después sin pasar por la fila, y mostrar en el ticket del tótem una espera estimada calculada con los tiempos reales.

---

## Por qué existe este spec

Los SPEC 02, 03 y 04 fueron enviando a un spec posterior la estimación de espera (HU-18), los preparados pendientes de retiro (HU-17) y las mermas (HU-20). Las tres dependen de registrar cuándo una receta queda preparada, un estado que hoy no existe. Este spec crea ese registro y cierra HU-17 y HU-18. Las mermas (HU-20) quedan para un spec propio, que podrá consultar la tabla nueva.

Texto de las historias, tal como está en el informe:

- **HU-17 — Gestión de medicamentos preparados no retirados** (Técnico en Farmacia, Must). Registrar y consultar los medicamentos ya preparados, pero no retirados por exceso de tiempo de espera, para ubicarlos rápidamente cuando el paciente regrese sin perder el trabajo de preparación. Criterios:
  - Cuando un turno se marca como ausente (HU-06) y la receta ya fue preparada, el sistema mueve el registro a un listado de «preparados pendientes de retiro».
  - El listado permite buscar por RUT o apellido del paciente.
  - Al encontrar el registro, el técnico puede marcar la entrega como completada, sin pasar nuevamente por la fila.
  - El registro conserva la fecha original de preparación para fines de trazabilidad de mermas.
- **HU-18 — Estimación de tiempo de espera por volumen de cola** (Paciente y Técnico en Farmacia, Must). Ver un tiempo estimado de espera calculado según el volumen real de recetas en cola (no solo las personas presentes en sala), para decidir si espera en el lugar o vuelve en otro momento. Criterios:
  - El sistema registra el tiempo real que toma cada preparación, desde la recepción hasta quedar lista.
  - Con ese historial, calcula un tiempo promedio de preparación por receta, actualizado periódicamente.
  - Al emitir el turno (HU-07), el sistema calcula la estimación en base a la cantidad de recetas pendientes y el tiempo promedio histórico, y la muestra al paciente.
  - La estimación se actualiza a medida que avanza la cola.

**Flujo de la farmacia que este spec supone** (confirmado con el equipo). La receta se prepara **durante la atención**, mientras el paciente espera en la ventanilla:

1. El funcionario llama al turno y, cuando el paciente llega, pulsa «Iniciar atención». Ese momento es la **recepción**: la preparación entra a la pantalla nueva `/preparacion/`.
2. Quien prepara (puede ser otra persona) la marca «Lista» en `/preparacion/`.
3. En la ventanilla, «Finalizar» se habilita recién cuando la preparación está lista, y registra la entrega.
4. Si el paciente se fue antes de recibir sus medicamentos, el funcionario pulsa «No retiró». El turno queda `ausente`. Si la preparación ya estaba lista, pasa a «preparados pendientes de retiro»; si no, se anula.
5. Cuando el paciente vuelve, el técnico lo busca en `/preparados/` y registra la entrega sin que saque turno.

Esto agrega un ausente desde `en_atencion`, que hoy no existe: en el SPEC 02 el ausente solo se marca desde `llamado`, y por eso nunca había nada preparado al marcarlo.

**Auditoría previa.** Se hizo al redactar este spec, sin modificar código. Existente, de los SPEC 02 y 04, que este spec usa:

- `Turno` con `inicio_atencion_en` y `cierre_en`. `iniciar_atencion` pasa de `llamado` a `en_atencion`. `finalizar_atencion` pasa a `atendido` y suma 1 a `RecetaCronica.entregas_realizadas` con `F()`. `marcar_ausente` solo acepta turnos `llamado` y exige `TURNOS_SEGUNDOS_MINIMOS_AUSENTE`.
- `motor.elegir_siguiente(fecha)` y su auxiliar `_generales_seguidos(fecha)`.
- `Ventanilla.funcionario` (quién la tiene abierta) y `Ventanilla.habilitada`.
- `ColaView` con `SondeoAutomatico` y el componente `filaEnVivo` de `panel.js`, que recibe `url` y `segundos`.
- `SoloAtencion`, el modal de confirmación (`data-confirmar-*`), el filtro `rut_legible` y las listas `.lista`.

Requiere aprobación: un cambio a una regla del SPEC 02. «Ausente» deja de ser solo «no se presentó al llamado»: también lo es un paciente que se fue durante la atención. Sigue siendo un estado final, y el paciente que vuelve sin haber dejado un preparado saca un turno nuevo. `Turno` no cambia de campos ni de estados.

---

## Alcance

**Dentro:**

- Modelo nuevo `Preparacion`, uno a uno con `Turno`, con su propio ciclo de estados.
- Recepción automática al iniciar la atención de cualquier turno, incluida la urgencia.
- Pantalla `/preparacion/` (funcionario y QF): preparaciones del día en curso y listas, con el botón «Marcar lista», actualizada sola cada `TURNOS_SEGUNDOS_REFRESCO_PANEL` segundos.
- En el panel de atención: el estado de la preparación del turno en curso («En preparación» o «Lista») actualizado solo, «Finalizar» habilitado solo con la preparación lista y el botón nuevo «No retiró».
- Pantalla `/preparados/` (funcionario y QF): preparados pendientes de retiro de cualquier día, con búsqueda por RUT o apellido y el botón «Entregar».
- La entrega desde `/preparados/` suma la entrega a la receta crónica, igual que «Finalizar».
- Espera estimada en el ticket del tótem (emitido y vigente), también al imprimir.
- Cálculo de la estimación en un módulo nuevo `turnos/estimacion.py`, sin cambiar `motor.py`.
- Datos de demostración: `cargar_datos_demo` agrega un historial sintético de atenciones con preparación, para que la estimación aparezca al probar.
- Pruebas de Django de los servicios, las vistas, los permisos y la estimación.
- Actualización de `README.md` y `CLAUDE.md`.

**Fuera de alcance (para specs futuros):**

- Panel de mermas por período (HU-20) y derivación de un no retirado al reparto a domicilio.
- Vencimiento de los preparados pendientes, devolución a stock o cualquier otra salida que no sea «Entregar». Quedan en la lista hasta que se entregan.
- Estimación de espera en la pantalla de la sala o en el panel de atención. `/sala/estado/` no cambia su contrato.
- Llamar dos veces a un turno (uno para recibir la receta y otro para entregarla) y liberar la ventanilla mientras se prepara.
- Registrar cuántas recetas trae cada paciente: una atención es una preparación.
- Un promedio guardado o recalculado por una tarea programada.
- Inventario, medicamentos o lotes de lo preparado.
- El bloqueo temporal tras intentos fallidos de login que declara el SPEC 01.

---

## Modelo de datos

Cambios en `turnos/models.py` y una migración `0004`:

```python
class EstadoPreparacion(models.TextChoices):
    EN_PREPARACION = "en_preparacion", "En preparación"
    LISTA = "lista", "Lista"
    ENTREGADA = "entregada", "Entregada"
    PENDIENTE_RETIRO = "pendiente_retiro", "Pendiente de retiro"
    ANULADA = "anulada", "Anulada"


class Preparacion(models.Model):
    """Lo que la farmacia prepara para un turno, desde la recepción hasta la entrega (HU-17, HU-18)."""

    turno = models.OneToOneField(Turno, on_delete=models.PROTECT, related_name="preparacion")
    estado = models.CharField(
        "estado", max_length=16, choices=EstadoPreparacion.choices, default=EstadoPreparacion.EN_PREPARACION
    )
    recibida_en = models.DateTimeField("recibida en", default=timezone.now)
    recibida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    lista_en = models.DateTimeField("lista en", null=True, blank=True)
    preparada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Momento en que la ventanilla registró «No retiró». Con estado ENTREGADA, indica un retiro posterior.
    no_retirada_en = models.DateTimeField("no retirada en", null=True, blank=True)
    retirada_en = models.DateTimeField("retirada en", null=True, blank=True)
    retirada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["recibida_en"]
```

**Ciclo de una preparación.** Cada paso se hace con un `UPDATE` condicional sobre `estado` (el patrón del SPEC 02), así dos clics simultáneos no lo aplican dos veces:

| Paso | Desde | Hacia | Quién y dónde | Efecto en `Turno` |
| --- | --- | --- | --- | --- |
| Recepción | (no existe) | `en_preparacion` | `iniciar_atencion`, en el panel | `llamado → en_atencion` (sin cambios) |
| Marcar lista | `en_preparacion` | `lista` | `/preparacion/` | Ninguno |
| Finalizar | `lista` | `entregada` | `finalizar_atencion`, en el panel | `en_atencion → atendido` y suma 1 entrega a la receta |
| No retiró, ya lista | `lista` | `pendiente_retiro` | `registrar_no_retiro`, en el panel | `en_atencion → ausente`, sin sumar entrega |
| No retiró, sin terminar | `en_preparacion` | `anulada` | `registrar_no_retiro`, en el panel | `en_atencion → ausente`, sin sumar entrega |
| Entregar un pendiente | `pendiente_retiro` | `entregada` | `entregar_pendiente`, en `/preparados/` | Ninguno: el turno sigue `ausente` y suma 1 entrega a la receta |

Reglas:

- **Tiempo de preparación** (HU-18): `lista_en − recibida_en`. **Tiempo de atención**: `Turno.cierre_en − Turno.inicio_atencion_en` de los turnos `atendido` que tienen preparación.
- `lista_en` es la **fecha original de preparación** de HU-17: no cambia al entregar un pendiente.
- Un pendiente entregado queda `entregada` con `no_retirada_en` lleno. Así el spec de mermas distingue «no retiró y volvió» de «no retiró y nunca volvió» (`pendiente_retiro`).
- Un turno `en_atencion` sin preparación (iniciado antes de migrar, o editado en el admin) se puede finalizar como hoy. No entra a la estimación.
- `entregar_pendiente` suma la entrega con `UPDATE ... WHERE entregas_realizadas < entregas_maximas`. Si la receta ya está agotada (el paciente sacó otro turno y recibió esa entrega entremedio), se rechaza con un `ErrorDeAtencion`: «La receta ya no tiene entregas disponibles. Consulte con la Química Farmacéutica.» y el pendiente no cambia.
- Un turno de un RUT que no está en el padrón (`Turno.paciente` nulo) también tiene preparación. En `/preparados/` se muestra con su RUT y sin nombre, y solo se encuentra por RUT.

**Estimación de espera** (`turnos/estimacion.py`). Se calcula al mostrar el ticket, sin guardar nada:

- **Promedio:** media del tiempo de atención de los turnos `atendido` con preparación cuyo `cierre_en` cae en los últimos `TURNOS_DIAS_HISTORIAL_ESPERA` días. Con menos de `TURNOS_MUESTRAS_MINIMAS_ESPERA` muestras no hay estimación.
- **Por delante:** cuántos turnos `en_espera` del día serían llamados antes que este, simulando el orden de `elegir_siguiente` (urgencia primero, luego la proporción de generales por preferencial a partir de `_generales_seguidos`, y orden de emisión dentro de cada categoría). La simulación no modifica datos y no cambia `motor.py`.
- **En curso:** turnos del día `llamado` o `en_atencion`.
- **Ventanillas abiertas:** habilitadas y con funcionario. Si no hay ninguna, no hay estimación.
- **Fórmula:** `(por delante + en curso) × promedio ÷ ventanillas abiertas`, redondeada hacia arriba a múltiplos de `TURNOS_MINUTOS_REDONDEO_ESPERA`.
- **Texto en el ticket:** «Espera estimada: unos 25 minutos». Si el resultado es menor que el redondeo, dice «Espera estimada: menos de 5 minutos». Sin estimación, la línea no aparece. Al imprimir, la línea va con «calculada a las HH:MM», porque el papel no se actualiza.
- **«Se actualiza a medida que avanza la cola»:** el ticket es una foto del momento. Cada emisión calcula con la cola de ese instante, y un paciente que vuelve a digitar su RUT en el tótem ve su turno vigente con la estimación recalculada.

**Constantes nuevas** al final de `settings.py`:

```python
TURNOS_DIAS_HISTORIAL_ESPERA = 30            # días de atenciones que entran al promedio
TURNOS_MUESTRAS_MINIMAS_ESPERA = 20          # con menos atenciones no se muestra estimación
TURNOS_MINUTOS_REDONDEO_ESPERA = 5           # la espera se redondea hacia arriba a este múltiplo
```

**Rutas nuevas** en `turnos/urls.py`:

| Ruta | Método | Acceso | Nombre |
| --- | --- | --- | --- |
| `/atencion/preparacion/` | GET | Funcionario y QF | `turnos:atencion_preparacion` (fragmento, `SondeoAutomatico`) |
| `/atencion/no-retiro/` | POST | Funcionario y QF | `turnos:registrar_no_retiro` |
| `/preparacion/` | GET | Funcionario y QF | `turnos:preparacion` |
| `/preparacion/fila/` | GET | Funcionario y QF | `turnos:preparacion_fila` (fragmento, `SondeoAutomatico`) |
| `/preparacion/<pk>/lista/` | POST | Funcionario y QF | `turnos:preparacion_lista` |
| `/preparados/` | GET, POST | Funcionario y QF | `turnos:preparados` |
| `/preparados/<pk>/entregar/` | POST | Funcionario y QF | `turnos:preparado_entregar` |

---

## Plan de implementación

1. **Modelo.** Agregar `EstadoPreparacion` y `Preparacion` con la migración `0004`. Registrar `Preparacion` en `turnos/admin.py` como solo lectura, con búsqueda por número de turno y RUT. **Verificación:** `migrate` aplica sin errores sobre una base con datos de demostración y turnos del SPEC 02; un turno no admite dos preparaciones; la suite existente pasa.

2. **Recepción y finalización.** En `servicios.py`, `iniciar_atencion` crea la `Preparacion` (`recibida_por` = el funcionario) en la misma transacción que el cambio de estado del turno. `finalizar_atencion` exige la preparación `lista` (mensaje: «La preparación aún no está lista.») y la pasa a `entregada` con `retirada_en` y `retirada_por`. Un turno sin preparación se finaliza como hoy. **Verificación:** en `turnos/tests/test_preparacion.py`, iniciar crea una preparación `en_preparacion`; finalizar con la preparación sin terminar falla y no suma la entrega; finalizar con la preparación lista deja turno `atendido`, preparación `entregada` y suma exactamente 1; un turno sin preparación se finaliza igual que antes. Se ajustan las pruebas existentes de `test_atencion.py` que finalizan sin marcar lista.

3. **Marcar lista y «No retiró».** Escribir `marcar_lista(preparacion_id, usuario)` y `registrar_no_retiro(usuario)` en `servicios.py`, con `UPDATE` condicional y `ErrorDeAtencion` para los casos inválidos. `registrar_no_retiro` solo acepta el turno `en_atencion` del funcionario, no exige plazo y aplica las dos filas «No retiró» de la tabla del ciclo. **Verificación:** pruebas de que marcar lista dos veces la marca una vez y guarda `lista_en` y `preparada_por`; de que «No retiró» con la preparación lista deja `pendiente_retiro` con `no_retirada_en` y el turno `ausente`; de que sin terminar la deja `anulada`; de que ninguno de los dos suma entregas; y de que el paciente puede sacar un turno nuevo en el tótem después.

4. **Entregar un pendiente.** Escribir `preparados_pendientes(busqueda=None)` (filtra por RUT normalizado o por apellido sin distinguir mayúsculas ni tildes, ordena por `lista_en` del más antiguo al más reciente) y `entregar_pendiente(preparacion_id, usuario)` con la regla de la receta agotada. **Verificación:** pruebas de la búsqueda por RUT con y sin puntos, por apellido con y sin tilde, de un pendiente de otro día que sigue en la lista, de que entregar suma 1, conserva `lista_en`, deja el turno `ausente` y no se puede repetir, y del rechazo con receta agotada.

5. **Pantalla de preparación.** Vista `/preparacion/` con `SoloAtencion` y el fragmento `/preparacion/fila/` (`SondeoAutomatico`, `_preparacion_fila.html`), refrescado con `filaEnVivo`. Dos secciones `.lista`: «En preparación» (urgencias primero y luego por `recibida_en`) y «Listas para entregar». Cada fila lleva el número de turno, la ventanilla, la insignia de categoría, el nombre del paciente (o su RUT si no está en el padrón), «Entrega N de M» si hay receta crónica y los minutos desde la recepción. Las en preparación llevan el botón de texto «Marcar lista», sin modal (no es destructivo y se hace muchas veces al día). Agregar «Preparación» a la barra del funcionario y la QF, y las reglas en una sección nueva de `estilos.css`. **Verificación:** `turnos/tests/test_preparacion.py` cubre las redirecciones al login, el 403 al Encargado de Terreno en cada ruta, el orden de las secciones y que el fragmento no renueva la sesión sin `X-Actividad-Reciente`.

6. **Panel de atención.** En `_turno_actual.html`, cuando el turno está `en_atencion`, el estado de la preparación pasa a un fragmento `_preparacion_turno.html` servido por `/atencion/preparacion/` (una insignia con texto, «En preparación» o «Lista», y `data-estado`). Los botones «Finalizar» (deshabilitado hasta que esté lista) y «No retiró» (con el modal de confirmación y `data-confirmar-peligro`; el texto avisa si la preparación queda pendiente de retiro o se anula) quedan fijos fuera del fragmento. Un componente nuevo de `panel.js`, `preparacionEnVivo`, con la misma regla de sesión que `filaEnVivo`, reemplaza el fragmento, habilita «Finalizar» y cambia el texto de «No retiró» al ver «lista», y deja de consultar. No cambian la forma de ticket ni el papel de turno. *Ajustado al implementar:* el plan original refrescaba con `filaEnVivo` también los botones, pero ese componente reemplaza todo el HTML en cada consulta, y un modal abierto perdía su formulario y no lo enviaba. **Verificación:** pruebas de vista de que el fragmento muestra cada estado y el botón correcto, y de que `/atencion/no-retiro/` responde a POST; captura del panel a 1366 px en los dos estados.

7. **Pantalla de preparados pendientes.** Vista `/preparados/` con `SoloAtencion`: lista de todos los pendientes y un formulario de una línea (`.tarjeta--formulario`) que busca por RUT o apellido **por POST**. Cada fila: nombre, RUT con `rut_legible`, turno y su fecha, «Preparado el dd-mm-aaaa a las HH:MM», quién preparó y la receta si la hay. «Entregar» usa el modal de confirmación con el nombre del paciente como objeto. Sin pendientes: «No hay preparados pendientes de retiro.»; sin resultados: «No hay preparados pendientes para esa búsqueda.» Agregar «Preparados» a la barra del funcionario y la QF. **Verificación:** pruebas de acceso por rol, de la búsqueda por POST (el RUT no queda en la URL), de los dos mensajes vacíos y del flujo «No retiró» → buscar → entregar.

8. **Estimación.** Escribir `turnos/estimacion.py` con `promedio_de_atencion(ahora)`, `turnos_por_delante(turno)`, `estimar_espera(turno)` (devuelve minutos redondeados o `None`) y `texto_de_espera(minutos)`. Las constantes van en `settings.py`. **Verificación:** `turnos/tests/test_estimacion.py` comprueba que, para una cola de prueba con urgencias, preferenciales y generales, el orden simulado coincide con el de llamar a `elegir_siguiente` una y otra vez; que con 19 muestras no hay estimación y con 20 sí; que se excluyen las atenciones de hace más de 30 días y los turnos sin preparación; que sin ventanillas abiertas no hay estimación; el redondeo y los dos textos.

9. **Ticket del tótem.** En `totem_resultado.html`, para `emitido` y `vigente`, mostrar la línea de espera bajo la categoría del ticket, y en `@media print` agregar «calculada a las HH:MM». Volver a medir que el tótem quepa sin desplazarse con un error a la vista, en vertical y horizontal. **Verificación:** pruebas de vista con y sin historial suficiente; capturas del tótem a 1080×1920 y 1920×1080 sin barra de desplazamiento.

10. **Datos de demostración.** `cargar_datos_demo` agrega, si no existen, 30 turnos `atendido` de días anteriores con su preparación y tiempos sintéticos, para que el tótem muestre una estimación al probar. Sigue siendo idempotente. **Verificación:** ejecutarlo dos veces deja las mismas filas, y después el tótem muestra «Espera estimada».

11. **Documentación y registro.** En `README.md`: las rutas `/preparacion/` y `/preparados/`, el flujo recepción → lista → entrega o «No retiró», la espera estimada y cómo se calcula, y una demostración. En `CLAUDE.md`: `Preparacion` y su ciclo, `turnos/estimacion.py`, el ausente desde `en_atencion`, las vistas nuevas con `SondeoAutomatico` y la numeración de specs (HU-20 sigue pendiente). Agregar al final de este spec el Registro de verificación. **Verificación:** una persona del equipo sigue la demostración del README desde cero.

---

## Criterios de aceptación

Regresión de los SPEC 01 a 04:

- [ ] `python manage.py test` pasa completo, incluidas las pruebas existentes de `cuentas` y `turnos` (con los ajustes del paso 2).
- [ ] `node --test "pruebas_js/*.test.js"` sigue pasando.
- [ ] No cambian `turnos/motor.py`, `emitir_turno` ni `llamar_siguiente`.
- [ ] `/sala/estado/` mantiene exactamente su contrato de claves y la sala no muestra la estimación.
- [ ] «Ausente» desde `llamado` sigue exigiendo `TURNOS_SEGUNDOS_MINIMOS_AUSENTE`.

Preparación:

- [ ] Iniciar la atención de cualquier turno, también de urgencia, crea exactamente una preparación `en_preparacion` con `recibida_en` y `recibida_por`.
- [ ] La preparación aparece en `/preparacion/` en menos de `TURNOS_SEGUNDOS_REFRESCO_PANEL` + 1 segundos sin recargar, y las urgencias van primero.
- [ ] «Marcar lista» guarda `lista_en` y `preparada_por`, y marcarla dos veces seguidas no cambia el primer `lista_en`.
- [ ] El panel muestra «En preparación» y, sin recargar, «Lista» cuando se marca en `/preparacion/`.
- [ ] «Finalizar» está deshabilitado y el servidor lo rechaza mientras la preparación no está lista.
- [ ] Finalizar con la preparación lista deja turno `atendido`, preparación `entregada` y suma exactamente 1 entrega a la receta.
- [ ] Un turno `en_atencion` sin preparación se finaliza como antes de este spec.

Preparados pendientes (HU-17):

- [ ] «No retiró» con la preparación lista deja el turno `ausente` y la preparación `pendiente_retiro`, sin sumar entrega.
- [ ] «No retiró» con la preparación sin terminar deja el turno `ausente` y la preparación `anulada`, que no aparece en `/preparados/`.
- [ ] «No retiró» usa el modal de confirmación, no `confirm()`.
- [ ] `/preparados/` encuentra un pendiente por RUT con y sin puntos, y por apellido con y sin tilde.
- [ ] La búsqueda se envía por POST: el RUT no queda en la URL.
- [ ] Un pendiente de un día anterior sigue en la lista.
- [ ] «Entregar» deja la preparación `entregada` con `retirada_en` y `retirada_por`, conserva `lista_en` y `no_retirada_en`, suma exactamente 1 entrega y el paciente no saca turno.
- [ ] Entregar dos veces el mismo pendiente lo entrega una sola vez.
- [ ] Con la receta agotada, «Entregar» se rechaza con el mensaje del spec y el pendiente sigue en la lista.

Estimación (HU-18):

- [ ] El orden simulado de la cola coincide con llamar a `elegir_siguiente` repetidamente sobre la misma cola.
- [ ] Con al menos 20 atenciones con preparación en los últimos 30 días y una ventanilla abierta, el ticket emitido muestra «Espera estimada: unos N minutos» con N múltiplo de 5.
- [ ] Con 19 atenciones, sin ventanillas abiertas o solo con atenciones de hace más de 30 días, el ticket no muestra la línea.
- [ ] Con 4 turnos por delante, 1 en curso, 2 ventanillas abiertas y un promedio de 4 minutos, la estimación es 10 minutos.
- [ ] Volver a digitar el RUT con un turno vigente muestra la estimación recalculada con la cola actual.
- [ ] El ticket impreso incluye la estimación y «calculada a las HH:MM».
- [ ] El tótem cabe sin desplazarse a 1080×1920 y a 1920×1080 con la línea de espera.

Acceso:

- [ ] Todas las rutas nuevas redirigen al login sin sesión y responden 403 al Encargado de Terreno.
- [ ] Los fragmentos `/atencion/preparacion/` y `/preparacion/fila/` no renuevan la sesión sin `X-Actividad-Reciente: 1`.

Datos:

- [ ] `cargar_datos_demo` ejecutado dos veces deja las mismas filas y permite ver la estimación en el tótem.
- [ ] Toda la verificación usa datos sintéticos.

---

## Decisiones

- **Sí:** HU-17 y HU-18 en este spec, y HU-20 en uno propio. Las dos primeras comparten el registro de la preparación. Las mermas son un panel de indicadores con otro usuario (Dirección y Jefatura) y dependen del módulo de reparto.
- **No:** las tres historias juntas. Serían decisiones en cuatro dominios en un solo spec.
- **Sí:** la receta se prepara durante la atención y el paciente espera en la ventanilla. Es el flujo actual de la farmacia, según el equipo.
- **No:** dos llamados por turno (recibir y retirar) con la ventanilla libre mientras se prepara. Cambia el motor, la sala y el ciclo de `Turno`.
- **Sí:** un ausente desde `en_atencion` («No retiró»). Sin él, HU-17 no se cumple nunca, porque hoy el ausente solo existe antes de la recepción.
- **Sí:** «No retiró» sin plazo mínimo. El plazo del SPEC 02 protege del paciente que viene en camino tras el llamado. Aquí el paciente ya llegó y el funcionario lo vio irse.
- **Sí:** «No retiró» antes de «Lista» anula la preparación. No hay nada que guardar, y un preparado a medias no debe aparecer como pendiente de retiro.
- **Sí:** modelo nuevo `Preparacion`, uno a uno con `Turno`. `Turno` no cambia de campos ni de estados, y el spec de mermas consulta una sola tabla.
- **No:** campos de preparación en `Turno`. Mezcla el ciclo del turno con el del preparado, que sigue después de que el turno termina (ausente y luego entregado).
- **Sí:** toda atención es una preparación, incluida la urgencia. Las recetas agudas en papel no están en el padrón, y la urgencia también necesita medicamentos.
- **No:** contar recetas por atención. Exigiría que el funcionario digite un número más en cada recepción.
- **Sí:** una pantalla aparte `/preparacion/` para marcar «Lista». Quien prepara puede no ser quien atiende.
- **Sí:** «Finalizar» exige la preparación lista. Así se registra siempre el tiempo de preparación que pide HU-18.
- **No:** que finalizar marque lista automáticamente. El tiempo de preparación quedaría igual al de atención.
- **Sí:** sondeo cada `TURNOS_SEGUNDOS_REFRESCO_PANEL` segundos en `/preparacion/` (con `filaEnVivo`) y en el estado del panel (con `preparacionEnVivo`), ambos con `SondeoAutomatico`. Es el patrón de la fila; quien atiende ve el cambio a «Lista» sin recargar.
- **Sí:** en el panel, solo el estado de la preparación se actualiza solo; los botones quedan fijos y `preparacionEnVivo` deja de consultar al ver «lista». Decidido al implementar el paso 6.
- **No:** refrescar los botones con `filaEnVivo`. Reemplaza el HTML en cada consulta (el `csrf_token` cambia siempre, así que no se puede comparar), y el modal de «No retiró» perdía su formulario y el foco saltaba cada 5 segundos.
- **Sí:** «Marcar lista» sin modal de confirmación. Se repite muchas veces al día y no borra nada.
- **Sí:** los pendientes no vencen y solo salen con «Entregar». Qué hacer con un preparado que nunca se retira es la merma, y la decide HU-20.
- **Sí:** la entrega de un pendiente deja el turno `ausente` y la preparación `entregada` con `no_retirada_en`. Es el dato que HU-20 necesita («ausentes sin retiro posterior»).
- **Sí:** rechazar la entrega de un pendiente si la receta ya está agotada. Evita entregar de más cuando el paciente recibió esa entrega con otro turno entremedio, igual que la regla del contador del SPEC 04.
- **Sí:** la búsqueda de `/preparados/` por POST. Es la regla de `/recetas/`: el RUT no queda en el historial del equipo compartido.
- **Sí:** la estimación divide por las ventanillas abiertas y respeta el orden del motor. Es más fiel que multiplicar las recetas pendientes por el promedio, que sobreestima con varias ventanillas.
- **Sí:** el promedio usa el tiempo de atención completo (recepción a entrega). La ventanilla queda ocupada todo ese tiempo, no solo mientras se prepara. El tiempo de preparación se registra igual (HU-18, primer criterio) y queda disponible para otros indicadores.
- **No:** el promedio literal de HU-18 (solo la preparación por las recetas pendientes). Ignora el tiempo de la ventanilla y las ventanillas en paralelo.
- **Sí:** promedio de los últimos 30 días calculado al vuelo, con mínimo de 20 muestras. «Actualizado periódicamente» sin tareas programadas, y sin historial suficiente es mejor no mostrar nada que mostrar un número inventado.
- **No:** un promedio guardado y recalculado por una tarea. El proyecto no tiene tareas programadas.
- **No:** promedio solo del día. Es inestable en la mañana.
- **Sí:** redondeo hacia arriba a 5 minutos y el texto «unos N minutos». Una estimación no es una promesa, y es mejor que el paciente espere menos de lo anunciado.
- **Sí:** la estimación solo en el ticket del tótem. Es donde el paciente decide si espera o vuelve. El papel no se actualiza, así que se imprime con la hora del cálculo, y volver a digitar el RUT la recalcula.
- **No:** la estimación en la sala o en el panel en este spec. La sala tiene un contrato fijo cuidado por pruebas, y cambiarlo merece su propia decisión.
- **Sí:** la simulación del orden vive en `turnos/estimacion.py` y una prueba la compara con `elegir_siguiente`. El motor no cambia, y si cambia, esa prueba avisa.
- **Sí:** historial sintético en `cargar_datos_demo`. Sin él, la estimación no se ve hasta acumular 20 atenciones reales.
- **Sí:** el historial sintético queda a nombre de la primera cuenta QF; sin una, el comando avisa y no lo carga. `Preparacion.recibida_por` es obligatorio y el comando no crea cuentas. Decidido al implementar el paso 10.
- **No:** una cuenta demo desactivada solo para el historial. Se consideró, pero se prefirió no agregar cuentas.
- **Sí:** `estimar_espera` devuelve 0 cuando el cálculo da menos que el redondeo («menos de 5 minutos»), y `None` para un turno vigente ya llamado o en atención: el ticket omite la línea. Decidido al implementar el paso 8.

---

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| El funcionario olvida marcar «Lista» y no puede finalizar | El panel muestra «En preparación» y el mensaje del servidor lo dice. `/preparacion/` está en la barra de la ventanilla. |
| Se marca «Lista» tarde y el tiempo de preparación queda inflado | Se acepta en el prototipo. El promedio de la estimación usa el tiempo de atención completo, que no depende de ese clic. |
| La simulación del orden se desalinea del motor si este cambia | Prueba que compara el orden simulado con llamadas sucesivas a `elegir_siguiente`. |
| Llega una urgencia después de emitir y el paciente espera más de lo estimado | Se acepta: no se pueden prever. El texto dice «unos» y se redondea hacia arriba. |
| Un funcionario abre o cierra su ventanilla y la estimación cambia mucho | Se calcula con las ventanillas abiertas en el momento. Volver a digitar el RUT la recalcula. |
| Un paciente con un pendiente saca otro turno y recibe dos veces | La entrega del pendiente exige que la receta tenga entregas disponibles. Para pacientes sin receta crónica no hay control: queda para el spec de mermas. |
| Los pendientes se acumulan sin fin | Se acepta hasta HU-20. La lista va del más antiguo al más reciente, con la fecha de preparación a la vista. |
| Pantallas con nombre y RUT en un equipo compartido | `/preparacion/` y `/preparados/` exigen sesión (funcionario y QF), la búsqueda va por POST y la sesión vence a los 30 minutos sin actividad. |
| El tótem deja de caber al agregar la línea | Se vuelve a medir en vertical y horizontal (paso 9). |

---

## Lo que **no** está en este spec

- Panel de mermas (HU-20) y derivación al reparto a domicilio.
- Vencimiento, devolución a stock o descarte de preparados pendientes.
- Estimación de espera en la sala o en el panel, y cambios a `/sala/estado/`.
- Dos llamados por turno y ventanilla libre durante la preparación.
- Cantidad de recetas por atención, inventario y lotes.
- Promedios guardados o tareas programadas.
- Cambios al motor de cola y a las reglas de emisión del SPEC 02.

Cada uno de esos, si se hace, va en su propio spec.

---

## Registro de verificación

Completado el 2026-10-28, durante la implementación. Condiciones comunes:

- **Equipo:** Windows 11, Python 3.13.15 y Django 6.1.2 (el `requirements.txt` fija la 5.2.17; la del equipo es la que estaba instalada), SQLite, Node 24.19.0.
- **Bases:** las pruebas automáticas usan la base de pruebas de Django. Las comprobaciones en el navegador usan una base aparte en el directorio temporal, con `migrate`, `cargar_datos_demo` y una cuenta de funcionario. La base local de desarrollo (`db.sqlite3`) no se tocó: el paso 1 y el paso 10 se probaron sobre una copia.
- **Navegador:** Edge sin cabeza controlado por el protocolo de DevTools desde Node, con `document.visibilityState` simulado como `hidden` (ver `CLAUDE.md`).

| Comprobación | Condiciones | Resultado |
| --- | --- | --- |
| Suite completa | `python manage.py test` y `node --test "pruebas_js/*.test.js"` | Cumple. 439 pruebas de Django y 21 de JavaScript, sin fallas |
| Migración `0004` sobre datos existentes | Copia de la base local con 6 turnos y 11 pacientes | Cumple. Aplica sin errores; los turnos siguen siendo 6 y no se crea ninguna preparación |
| El orden simulado detecta un cambio del motor | Mutación: la simulación ignora la racha de generales ya llamados hoy | Cumple. Falla `test_respeta_la_racha_de_generales_ya_llamados_hoy`; sin la mutación, pasa |
| Panel en preparación y paso a «Lista» sin recargar | Turno crónico (entrega 3 de 6) en atención; la preparación se marca lista desde otro proceso; 1366 px | Cumple. «Finalizar atención» deshabilitado con «En preparación»; unos 6 s después de marcarla, «Lista», «Finalizar» habilitado y el texto de «No retiró» cambiado, sin recargar la página |
| Modal de «No retiró» abierto durante una consulta automática | Modal abierto mientras el panel consulta el estado (6,5 s) | Cumple. El modal sigue abierto y su formulario sigue en la página. Al aceptar con la preparación lista, el turno queda ausente y el preparado, pendiente de retiro |
| Pantallas de preparación y preparados | `/preparacion/` y `/preparados/` a 1366 px, y `/preparados/` a 500 px | Cumple. A 500 px, «Entregar» pasa bajo los datos, como en las demás listas |
| Ticket con la espera estimada | 20 atenciones de 6 minutos, 1 ventanilla abierta y 2 turnos por delante; 1080×1920 y 1920×1080 | Cumple. «Espera estimada: unos 15 minutos.» (2 × 6 ÷ 1 = 12, redondeado a 15). Alto del contenido igual al de la pantalla en las dos orientaciones; con el turno vigente, la estimación se recalcula |
| Ticket impreso | `@media print` emulado | Cumple. Negro sobre blanco, con «…, calculada a las 18:34.» |
| Tótem con un error a la vista | RUT con dígito verificador inválido; 1080×1920 y 1920×1080 | Cumple. Sin desplazamiento (la pantalla del teclado no cambió en este spec) |
| `cargar_datos_demo` dos veces | Copia de la base local, con su cuenta QF | Cumple. Las dos veces quedan 36 turnos y 30 preparaciones; promedio de atención de 6,0 minutos |

Pendiente: que una persona del equipo siga la demostración del README desde cero (verificación del paso 11), y oír y usar las pantallas en el equipo real del mesón.
