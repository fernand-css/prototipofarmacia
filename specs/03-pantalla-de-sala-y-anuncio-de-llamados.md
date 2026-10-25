# SPEC 03 — Pantalla de sala de espera y anuncio de llamados

> **Estado:** Aprobado
> **Depende de:** SPEC 01 y SPEC 02
> **Fecha:** 2026-10-24
> **Objetivo:** Mostrar en una pantalla pública de la sala de espera el último turno llamado y su ventanilla, junto a los llamados anteriores del día, con un aviso visual y sonoro por cada llamado nuevo y sin exponer datos personales.

---

## Por qué existe este spec

El SPEC 02 dejó el llamado guardado en `Turno` (`estado`, `ventanilla`, `ultimo_llamado_en`, `veces_llamado`) para que una pantalla lo consumiera. Esa pantalla no existe: hoy el paciente no tiene cómo enterarse de que lo llamaron. Este spec la construye (historias HU-08 y HU-09 del informe).

La pantalla es de solo lectura: observa lo que el panel ya guarda y lo anuncia. No elige ni asigna turnos, y no cambia ninguna regla del motor.

**Numeración.** El SPEC 02 reservaba el número 03 para la estimación de espera y las recetas, y dejaba la pantalla para un spec aparte. Por pedido del equipo, el 03 es la pantalla. La estimación de espera (HU-18), los preparados pendientes de retiro (HU-17) y las mermas (HU-20) pasan al SPEC 04 o posteriores. No existe un índice de specs: el cambio queda registrado aquí y en `CLAUDE.md` al implementar. El SPEC 02 está `Implementado` y no se edita.

**Auditoría previa.** Se hizo al redactar este spec, sin modificar código.

Existente, del SPEC 02, que este spec usa sin cambios:

- `Turno` tiene `fecha`, `categoria`, `correlativo` (propiedad `numero`), `estado`, `ventanilla`, `llamado_en`, `ultimo_llamado_en` y `veces_llamado`. `Ventanilla` tiene `numero`.
- `servicios.llamar_siguiente` asigna con un `UPDATE` condicional sobre `estado = 'en_espera'`. Deja `llamado_en = ultimo_llamado_en = ahora`, `veces_llamado = 1` y la ventanilla del funcionario.
- `servicios.re_llamar` suma 1 a `veces_llamado`, renueva `ultimo_llamado_en` y conserva ventanilla y funcionario.
- `servicios.marcar_ausente` exige `TURNOS_SEGUNDOS_MINIMOS_AUSENTE` desde `ultimo_llamado_en`, validado en el servidor.
- `turnos/tests/test_motor.py` ya prueba los escenarios A, B y C, la urgencia primero, el orden de emisión y la proporción tomada de `settings`.
- `turnos/tests/test_llamado.py` ya prueba un solo turno con dos funcionarios, dos turnos para dos ventanillas y el re-llamado.
- `turnos/tests/test_atencion.py` ya prueba el plazo del ausente y su reinicio con un re-llamado.
- `cuentas.mixins.SondeoAutomatico` y `cuentas.middleware.SesionPorActividad` evitan que una consulta automática renueve la sesión.

Pendiente, y es lo que hace este spec: la consulta de solo lectura para la sala, las rutas públicas `/sala/` y `/sala/estado/`, la pantalla y sus anuncios.

Requiere aprobación: ninguna regla del SPEC 01 ni del SPEC 02. Sí cambian dos reglas de identidad visual de `CLAUDE.md` (el papel de turno y el único movimiento automático), aprobadas al definir este spec (ver Decisiones).

El sistema es un **prototipo académico** con datos sintéticos, sin integración con Rayén ni despliegue en el CESFAM. No se prometen mejoras reales en los tiempos de espera.

---

## Alcance

**Dentro:**

- Pantalla pública `GET /sala/`, sin sesión, pensada para un televisor o monitor de la sala. Muestra en grande el último llamado (número y ventanilla) y debajo los 4 llamados anteriores del día.
- Ruta pública `GET /sala/estado/`, que entrega en JSON la instantánea de llamados del día. Solo trae número de turno, número de ventanilla y los datos que identifican cada llamado.
- Consulta de solo lectura `turnos/servicios.py::obtener_estado_sala(fecha=None)`.
- Sondeo cada `TURNOS_SEGUNDOS_REFRESCO_SALA` segundos, con una sola consulta en curso a la vez y espera creciente cuando falla.
- Detección de llamados nuevos y re-llamados sin repetir los ya anunciados. La instantánea de carga es la línea base silenciosa.
- Aviso visual: la tarjeta del último llamado sobre papel de turno, un pulso al llegar un llamado y la etiqueta «Nuevo llamado».
- Aviso sonoro opcional: una campanilla generada con Web Audio y luego la frase «Turno P 12, ventanilla 2» dicha dos veces con `speechSynthesis`.
- Control «Activar voz / Desactivar voz», cuya elección recuerda el monitor.
- Estados de la pantalla: sin llamados («Esperando llamados»), sin conexión, reconexión, voz por reactivar, navegador sin voz y navegador sin JavaScript.
- Pruebas de Django para la consulta, las rutas, la privacidad y la sesión.
- Pruebas de JavaScript con `node --test` para la detección de anuncios, la frase y la elección de voz.
- Registro de la verificación manual (latencia, resoluciones, teclado y voz) al final de este spec.
- Actualización de `README.md` y `CLAUDE.md`.

**Fuera de alcance (para specs futuros):**

- Estimación de tiempos de espera (HU-18), tiempos de preparación y preparados pendientes de retiro (HU-17), y mermas (HU-20). Van al SPEC 04 o posteriores.
- Cambios al motor de cola: proporción dinámica o editable, reingreso de ausentes u otra prioridad.
- WebSocket, Django Channels o Redis, para la sala o para el panel. El panel conserva su sondeo de `TURNOS_SEGUNDOS_REFRESCO_PANEL`.
- Una bitácora de eventos de llamado que garantice anunciar cada re-llamado.
- Mostrar en la sala el estado de cada turno (en atención, atendido, ausente) o su categoría.
- Llamar, re-llamar o cualquier otra acción desde la pantalla pública.
- Una tarjeta por ventanilla. La sala muestra el último llamado y los anteriores, no el estado de cada puesto.
- Archivos de audio, voces pagadas, parlantes o pantallas especiales, y la instalación física en el CESFAM.
- El modo kiosco del navegador como requisito. No impide usarlo.
- Datos personales en la sala, reconocimiento de identidad e integración con Rayén.

---

## Modelo de datos

Este spec no agrega modelos ni migraciones. Lee estos campos del SPEC 02:

```python
Turno.fecha, Turno.categoria, Turno.correlativo   # Turno.numero → "P-012"
Turno.estado                                      # en_espera | llamado | en_atencion | atendido | ausente | anulado
Turno.ventanilla                                  # FK a Ventanilla; la sala muestra Ventanilla.numero
Turno.ultimo_llamado_en                           # llamado o re-llamado más reciente
Turno.veces_llamado                               # 1 en el primer llamado, +1 en cada re-llamado
```

Respuesta de `GET /sala/estado/` (datos ilustrativos). Es también lo que devuelve `obtener_estado_sala` y lo que `/sala/` incrusta con `{{ estado|json_script:"estado-sala" }}`:

```json
{
  "fecha": "2026-10-24",
  "servidor_en": "2026-10-24T17:10:00-03:00",
  "actual": {"turno_id": 42, "numero": "P-012", "ventanilla": 2, "veces_llamado": 1, "ultimo_llamado_en": "2026-10-24T17:09:58-03:00"},
  "recientes": [
    {"turno_id": 42, "numero": "P-012", "ventanilla": 2, "veces_llamado": 1, "ultimo_llamado_en": "2026-10-24T17:09:58-03:00"},
    {"turno_id": 40, "numero": "G-045", "ventanilla": 1, "veces_llamado": 2, "ultimo_llamado_en": "2026-10-24T17:08:31-03:00"}
  ]
}
```

- `ventanilla` es `Ventanilla.numero`, no la clave primaria.
- Las horas van en hora local de Santiago (`timezone.localtime`).
- `actual` es `recientes[0]`, o `null` si no hay llamados. En ese caso `recientes` es `[]`.
- Cada llamado tiene exactamente esas cinco claves. La respuesta nunca incluye `rut`, `paciente`, `receta`, `atendido_por`, `estado` ni `categoria`.

Constantes nuevas en `farmacia_turnos/settings.py`, al final del bloque de turnos:

```python
TURNOS_SEGUNDOS_REFRESCO_SALA = 2            # objetivo de diseño; se mide (ver Registro de verificación)
TURNOS_CANTIDAD_LLAMADOS_SALA = 5            # el último llamado más 4 anteriores
TURNOS_SEGUNDOS_VIGENCIA_ANUNCIO = 30        # un llamado más antiguo que esto ya no se anuncia
TURNOS_SEGUNDOS_REINTENTO_MAXIMO_SALA = 30   # tope de la espera entre reintentos sin conexión
TURNOS_SEGUNDOS_RESALTE_SALA = 10            # cuánto dura la etiqueta «Nuevo llamado»
```

`TURNOS_VOZ_HABILITADA_POR_DEFECTO`, propuesta en el borrador, no se agrega (ver Decisiones).

En el navegador, `static/js/sala.js` guarda la elección de voz en la clave `sala:voz` de `localStorage`, con `"1"` o `"0"`.

**Convenciones:**

- **Día operativo:** `fecha = timezone.localdate()`. A medianoche la lista queda vacía sola.
- **Llamado visible:** turno del día con `ultimo_llamado_en` no nulo, `ventanilla` no nula y `veces_llamado >= 1`. Su estado no es `en_espera` ni `anulado`, así que entran `llamado`, `en_atencion`, `atendido` y `ausente`.
- **Orden:** `ultimo_llamado_en` descendente, con `id` descendente como desempate. Un re-llamado sube al mismo turno al primer lugar sin duplicar su fila.
- **Último llamado:** el primero de `recientes`. Es el último evento de llamado registrado, no una afirmación sobre si ese paciente sigue en la ventanilla. Por eso el rótulo es «Último llamado» y no se muestra el estado.
- **Identificador de anuncio:** `` `${turno_id}:${veces_llamado}:${ultimo_llamado_en}` ``. Un re-llamado produce un identificador nuevo para el mismo número.
- **Llamados nuevos:** los identificadores de `recientes` que no estaban en la última instantánea recibida con éxito, siempre que `servidor_en − ultimo_llamado_en` no supere `TURNOS_SEGUNDOS_VIGENCIA_ANUNCIO`. Se anuncian del más antiguo al más reciente. La resta usa dos horas del servidor, así que no depende del reloj del monitor.
- **Línea base:** la instantánea incrustada en `/sala/` se toma como ya vista. Al cargar no se anuncia nada.
- **Concurrencia:** elegir y asignar turnos sigue siendo exclusivo de `llamar_siguiente`. La sala no escribe en la base.
- **Límite conocido:** si un mismo turno se re-llama dos veces entre dos sondeos, la sala ve solo el último identificador y lo anuncia una vez.
- **Latencia medida:** `servidor_en − ultimo_llamado_en` del primer sondeo que trae un llamado. Mide desde que el llamado se guarda hasta la respuesta que lo entrega; no incluye el dibujo en pantalla, que toma milisegundos.

---

## Plan de implementación

1. **Constantes y consulta.** Agregar las cinco constantes nuevas a `settings.py`. Escribir `obtener_estado_sala(fecha=None)` en una nueva sección «Sala de espera» de `turnos/servicios.py`, junto a `resumen_cola`; devuelve el diccionario del contrato. Crear `turnos/tests/test_sala.py`. **Verificación:** pruebas con turnos de un día anterior, `en_espera`, `anulado`, `llamado`, `en_atencion`, `atendido` y `ausente`; un re-llamado que sube al primer lugar sin duplicarse; el tope de 5; el desempate por `id`; y un turno sin ventanilla que no aparece.
2. **Ruta JSON.** Escribir `SalaEstadoView(SondeoAutomatico, View)` con solo `get`, `never_cache` y `JsonResponse(obtener_estado_sala())`. Montarla en `sala/estado/` con el nombre `turnos:sala_estado`. **Verificación:** pruebas de acceso sin sesión (200), `POST` con 405, `Cache-Control` sin caché, claves exactas del contrato y ausencia del RUT y del nombre del paciente. Otra prueba, como las de `turnos/tests/test_sesion.py`, comprueba que con sesión iniciada la consulta sin `X-Actividad-Reciente` no renueva la sesión.
3. **Página y componente.** Escribir la vista `sala` (`require_GET`, `never_cache`), montada en `sala/` con el nombre `turnos:sala`. La plantilla `turnos/templates/turnos/sala.html` extiende `base.html`, vacía `barra` y `pie`, usa `{% block clase_body %}pagina-sala{% endblock %}`, incrusta el estado con `json_script` y pasa las constantes al componente. `static/js/sala.js` registra en `alpine:init` el componente `salaEnVivo`, que en este paso solo dibuja la instantánea incrustada con `x-text` y `x-for`. Muestra «Último llamado» con el número y «Ventanilla N», «Llamados anteriores» con hasta 4 filas, y «Esperando llamados» si no hay ninguno. Un `<noscript>` dice «Esta pantalla necesita JavaScript para mostrar los llamados.». **Verificación:** pruebas de que `/sala/` carga sin sesión, no muestra la barra ni el RUT o el nombre del paciente, incluye el `json_script` y muestra «Esperando llamados» sin llamados. `node --check static/js/sala.js` pasa.
4. **Estilos.** Crear la sección «15 · Sala de espera» en `static/css/estilos.css` y agregarla al índice. Los tamaños dependen del viewport, como en el tótem, para que todo quepa sin desplazarse. El último llamado va a la izquierda sobre `--papel` y los anteriores a la derecha, en una lista sobria. El número va en peso 800 con cifras tabulares y la ventanilla con su etiqueta explícita. No se usa la forma de ticket, y el estado vacío no usa papel. **Verificación:** captura con Edge sin cabeza (`--window-size`) a 1920×1080 y a 1366×768, sin desplazamiento ni texto cortado, anotada en el Registro de verificación.
5. **Sondeo y conexión.** `salaEnVivo` pide `/sala/estado/` con `fetch` y programa la siguiente consulta con `setTimeout` solo al terminar la anterior, así nunca hay dos en curso. Una consulta que no responde en 5 s se aborta. El componente nunca envía `X-Actividad-Reciente` y solo vuelve a dibujar si cambió la lista de identificadores. Muestra «Actualizado a las HH:MM» con `servidor_en`. Ante un error de red, un estado distinto de 2xx o un JSON inválido, conserva lo que hay en pantalla y muestra «Sin conexión. Información pendiente de actualización.». La espera entre reintentos se duplica hasta `TURNOS_SEGUNDOS_REINTENTO_MAXIMO_SALA`. Al primer éxito vuelve a `TURNOS_SEGUNDOS_REFRESCO_SALA` y quita el aviso. **Verificación manual:** un llamado desde el panel aparece en la sala sin recargar; con `runserver` detenido se mantienen los datos y aparece el aviso; al reiniciarlo, la sala se sincroniza.
6. **Detección de anuncios.** Escribir en `sala.js` las funciones puras `identificador(llamado)` y `llamadosNuevos(previos, estado, vigencia)`, sin DOM ni Alpine. El archivo las exporta con `module.exports` solo si existe `module`, y registra el componente solo si existe `document`, para poder cargarlo en Node. **Verificación:** `node --test "pruebas_js/*.test.js"` con `pruebas_js/sala.test.js` comprueba que la línea base no anuncia nada, que tres instantáneas sin cambios dan cero anuncios y que un re-llamado da uno. También que dos llamados nuevos en la misma instantánea dan dos, en orden cronológico, y que un llamado más antiguo que la vigencia o una reconexión tras un corte largo dan cero.
7. **Aviso visual.** Cuando el último llamado es nuevo, su tarjeta reproduce la animación `sala-llamado`: 3 pulsos en unos 3 s, apagada con `prefers-reduced-motion`. Todo llamado nuevo lleva «Nuevo llamado» durante `TURNOS_SEGUNDOS_RESALTE_SALA`, en la tarjeta o en su fila de anteriores. `sala.js` registra con `console.debug` la latencia de cada llamado detectado. **Verificación manual:** un llamado desde el panel pulsa y muestra la etiqueta una sola vez; con `prefers-reduced-motion` emulado en las herramientas del navegador, solo aparece la etiqueta.
8. **Anuncio sonoro.** Agregar el botón «Activar voz» / «Desactivar voz» (`<button type="button" aria-pressed>`), visible y manejable con Tab, Enter y Espacio. Al activarlo se crea o se reanuda el `AudioContext`. Cada anuncio entra a una cola propia: una campanilla de dos tonos con `OscillatorNode` y luego la frase dos veces. El siguiente anuncio espera a que termine el anterior. La frase la arma la función pura `textoDelAnuncio(numero, ventanilla)`, sin ceros a la izquierda. La voz la elige la función pura `elegirVoz(voces)` en este orden: `es-CL` local, `es-CL`, otra `es-*` local, otra `es-*`. Si la lista de voces aún está vacía, espera `voiceschanged`. **Verificación:** `pruebas_js/sala.test.js` cubre `textoDelAnuncio` y `elegirVoz`; a mano en Edge, un llamado y un re-llamado suenan con campanilla y frase doble.
9. **Recordar la voz y degradar.** La elección se guarda en `sala:voz` dentro de `try/catch`. Si al cargar `sala:voz` vale `"1"` y el navegador exige interacción, aparece «Toque la pantalla para reactivar la voz» hasta el primer toque, clic o tecla. Se detecta con `navigator.userActivation.hasBeenActive` en falso o con el error `not-allowed` de una locución. Sin `speechSynthesis` suena solo la campanilla y la pantalla lo dice. Sin Web Audio ni voz, el botón se reemplaza por «Este navegador no puede reproducir sonido». **Verificación manual:** activar la voz, recargar y reactivarla con un toque; con `localStorage` bloqueado la pantalla funciona y la voz parte desactivada.
10. **Documentación y registro.** En `README.md`: la ruta `/sala/` en la tabla, cómo activar la voz, abrir la sala en un navegador sin sesión, recargarla al actualizar el sistema, el modo kiosco como opción, `node --test "pruebas_js/*.test.js"` y el flujo de demostración tótem → panel → sala con `cargar_datos_demo`. En `CLAUDE.md`: la sala, `sala.js`, `pruebas_js/`, las dos reglas de identidad ampliadas y la nueva numeración de specs. Completar el Registro de verificación de este spec. **Verificación:** una persona del equipo sigue el README desde cero y ve en `/sala/` un llamado hecho desde el panel.

---

## Criterios de aceptación

Regresión de los SPEC 01 y 02:

- [ ] `python manage.py test` pasa completo, incluidas las pruebas existentes de `cuentas` y `turnos`.
- [ ] No cambian `turnos/models.py`, `turnos/motor.py` ni las funciones de llamado y atención de `turnos/servicios.py`, y no hay migraciones nuevas.
- [ ] Siguen pasando los escenarios A, B y C, la prioridad de la urgencia y la prueba de un solo turno con dos funcionarios (`test_motor.py`, `test_llamado.py`).
- [ ] `/atencion/` y `/ventanillas/` siguen redirigiendo al login sin sesión y devolviendo 403 a los roles sin permiso.

Consulta y rutas:

- [ ] `/sala/` y `/sala/estado/` responden 200 sin sesión iniciada.
- [ ] `POST` a `/sala/` y a `/sala/estado/` responde 405.
- [ ] Ambas respuestas llevan cabeceras que impiden guardarlas en caché.
- [ ] La respuesta de `/sala/estado/` tiene exactamente las claves `fecha`, `servidor_en`, `actual` y `recientes`.
- [ ] Cada llamado de la respuesta tiene exactamente las claves `turno_id`, `numero`, `ventanilla`, `veces_llamado` y `ultimo_llamado_en`.
- [ ] Ni `/sala/` ni `/sala/estado/` contienen el RUT, los nombres ni los apellidos del paciente de un turno llamado.
- [ ] Con sesión iniciada, una consulta a `/sala/estado/` sin `X-Actividad-Reciente` no renueva la sesión.
- [ ] `sala.js` nunca envía la cabecera `X-Actividad-Reciente`.
- [ ] Un turno llamado con `POST /atencion/llamar/` aparece en la siguiente respuesta de `/sala/estado/`, con su número y el número de su ventanilla.
- [ ] Sin llamados hoy, `actual` es `null`, `recientes` es `[]` y `/sala/` muestra «Esperando llamados».
- [ ] `recientes` tiene como máximo 5 turnos distintos, todos de hoy.
- [ ] Los turnos de días anteriores, los `en_espera` y los `anulado` nunca aparecen.
- [ ] Un turno `ausente`, `atendido` o `en_atencion` ya llamado puede aparecer, y la sala no muestra el estado ni la categoría de ningún turno.
- [ ] Un re-llamado deja al turno primero en `recientes`, con el mismo número y la misma ventanilla, sin duplicar su fila y con un identificador de anuncio distinto.

Pantalla:

- [ ] `/sala/` no muestra la barra superior ni el pie.
- [ ] La pantalla muestra en grande el último llamado con su ventanilla rotulada, y debajo hasta 4 llamados anteriores.
- [ ] La pantalla cabe sin desplazamiento ni texto cortado a 1920×1080 y a 1366×768, según el Registro de verificación.
- [ ] Sin JavaScript, `/sala/` muestra el mensaje del `<noscript>`.
- [ ] La pantalla se actualiza sin recargar y nunca tiene dos consultas a `/sala/estado/` en curso a la vez.
- [ ] Con el servidor detenido, la pantalla conserva los últimos datos y muestra «Sin conexión. Información pendiente de actualización.».
- [ ] Al volver el servidor, la pantalla quita el aviso y se sincroniza.
- [ ] Sin conexión, la espera entre reintentos crece y no supera `TURNOS_SEGUNDOS_REINTENTO_MAXIMO_SALA`.

Anuncios:

- [ ] `node --test "pruebas_js/*.test.js"` pasa.
- [ ] Al cargar `/sala/` no se anuncia ningún llamado existente.
- [ ] Tres instantáneas sin cambios no producen ningún anuncio.
- [ ] Un llamado nuevo reproduce una vez la animación de resalte y muestra «Nuevo llamado»; los sondeos siguientes sin cambios no la repiten.
- [ ] Con la voz activa, un llamado nuevo suena con una campanilla seguida de la frase dicha dos veces.
- [ ] Un re-llamado produce un anuncio nuevo.
- [ ] Dos llamados nuevos en la misma instantánea producen dos anuncios, del más antiguo al más reciente.
- [ ] Un llamado más antiguo que `TURNOS_SEGUNDOS_VIGENCIA_ANUNCIO` al detectarse no se anuncia.
- [ ] Tras una reconexión solo se anuncian los llamados dentro de ese plazo.
- [ ] `textoDelAnuncio("P-012", 2)` devuelve `"Turno P 12, ventanilla 2."`.
- [ ] `elegirVoz` prefiere `es-CL` y, si no hay, otra voz española, priorizando las locales.
- [ ] Con `prefers-reduced-motion`, un llamado nuevo no anima la tarjeta y sí muestra la etiqueta.

Sonido:

- [ ] El control «Activar voz» / «Desactivar voz» está siempre visible y se maneja solo con el teclado.
- [ ] Tras recargar con la voz activa, la pantalla pide «Toque la pantalla para reactivar la voz», y un toque la reactiva.
- [ ] Sin `localStorage` disponible, la pantalla funciona y la voz parte desactivada.
- [ ] En un navegador sin `speechSynthesis`, la pantalla sigue actualizándose y avisando visualmente, sin errores en la consola.

Medición y datos:

- [ ] El Registro de verificación anota la mediana y el máximo de la latencia en 20 llamados, con el navegador, el equipo y el servidor usados, sin presentarlo como garantía de producción.
- [ ] Toda la verificación se hace con `cargar_datos_demo` u otros datos sintéticos, sin conexión con Rayén.

---

## Decisiones

- **Sí:** el motor del SPEC 02 es la única fuente de selección. La sala no crea una cola paralela ni toca la ponderación.
- **Sí:** quitar del plan los pasos de auditoría y de validación del motor que traía el borrador. La auditoría se hizo al redactar el spec y no dejaba nada que guardar en un commit. Sus garantías quedan como criterios de regresión.
- **Sí:** el título «Pantalla de sala de espera y anuncio de llamados», en vez de «Motor de encolamiento, visualización de pantalla y llamado». El spec no toca el motor y el título no debe sugerirlo.
- **Sí:** llamar y re-llamar solo desde el panel autenticado. La pantalla pública observa y anuncia.
- **Sí:** leer el estado guardado en `Turno`, sin tabla de eventos ni migraciones.
- **Sí:** JSON en `/sala/estado/` y la instantánea inicial incrustada con `json_script`. La pantalla se ve llena desde el primer momento, la línea base sale del mismo dato y `x-text` escapa el contenido.
- **No:** un fragmento HTML como el de la fila del panel. Para detectar anuncios habría que leer atributos del DOM, y la prueba de privacidad sobre claves exactas sería menos directa.
- **Sí:** un solo campo de hora del servidor (`servidor_en`). El `actualizado_en` del borrador tenía el mismo valor.
- **Sí:** `obtener_estado_sala` en `turnos/servicios.py`, junto a `resumen_cola`, que ya es una consulta de solo lectura para una pantalla.
- **Sí:** anunciar todo identificador nuevo en `recientes`, no solo el actual. Con 4 ventanillas, dos llamados en el mismo intervalo de 2 s son esperables, y comparar solo el actual dejaría a uno sin anuncio.
- **Sí:** una vigencia de 30 s, medida con horas del servidor. Tras un corte corto se anuncia lo pendiente; tras uno largo no hay una ráfaga de llamados viejos, que siguen visibles en la lista.
- **No:** tomar cada reconexión como línea base silenciosa. Un paciente llamado durante un corte de pocos segundos no lo oiría.
- **Sí:** el último llamado sobre papel de turno. El papel significa «es su turno», y en la sala eso es literal. Se amplía la regla de `CLAUDE.md`.
- **No:** la forma de ticket en la sala. La sala no entrega un papel, así que la forma sigue reservada al tótem y al panel.
- **Sí:** el pulso del último llamado como segundo movimiento automático. En la sala nadie mira la pantalla cuando llega un llamado, y el movimiento atrae la vista aunque la voz esté apagada. Son 3 pulsos lentos, bajo el umbral de 3 destellos por segundo, que se apagan con `prefers-reduced-motion`. Se amplía la regla «un solo movimiento automático» de `CLAUDE.md`.
- **No:** una sala sobria en verde petróleo, ni un resalte solo con etiqueta. Se ajustan más a las reglas actuales, pero se notan menos desde lejos.
- **Sí:** el último llamado más 4 anteriores, 5 turnos únicos en pantalla. La lista no repite el actual.
- **No:** mostrar el estado o la categoría de cada turno. «Ausente» en una pantalla pública expone que alguien no llegó, y el estado no le sirve al paciente que espera.
- **Sí:** recordar la voz en el `localStorage` del monitor y pedir un toque para reactivarla. Chrome y Edge no dejan hablar sin interacción con la página, tampoco tras recargarla.
- **No:** `TURNOS_VOZ_HABILITADA_POR_DEFECTO`. Una constante del servidor no puede saltarse esa política del navegador.
- **No:** exigir el modo kiosco (`--autoplay-policy=no-user-gesture-required`). Depende de cómo se abra el navegador, así que queda como opción de instalación en el README.
- **Sí:** campanilla generada con Web Audio y la frase dicha dos veces. La campanilla avisa aunque no haya voz en español, y la repetición ayuda a quien no alcanzó a oír la primera.
- **No:** un archivo de audio para la campanilla. Un oscilador basta y no suma un binario ni su licencia.
- **Sí:** preferir voces locales. El CESFAM puede estar sin internet, y ahí las voces en línea del navegador fallan.
- **Sí:** sondeo cada 2 s solo para la sala, con `setTimeout` encadenado. Es compatible con Django y SQLite, y encadenar evita consultas superpuestas. El panel sigue en 5 s.
- **No por ahora:** Channels, Redis o WebSocket. Cambian la infraestructura, y la sala no los necesita para este alcance.
- **Sí:** `/sala/estado/` con `SondeoAutomatico`. Si un monitor queda por error con una sesión abierta, esta vence igual.
- **Sí:** una pantalla anónima, sin sesión. Una cuenta de funcionario abierta en un monitor público permitiría atender con su nombre. Es la segunda excepción, tras el tótem, al criterio del SPEC 01 «ninguna página es accesible sin sesión».
- **Sí:** anunciar solo el número de turno y la ventanilla. Es lo único que el paciente necesita, y el resto son datos personales o de salud (Ley 19.628).
- **Sí:** funciones puras en `sala.js`, probadas con `node --test` desde `pruebas_js/`, fuera de `static/`. Node ya está en el equipo y no suma dependencias. La detección de anuncios es la parte que se puede romper sin que nadie lo note. Fuera de `static/`, las pruebas no se sirven ni las copia `collectstatic`.
- **Sí:** el registro de la verificación manual va al final de este spec. Así la latencia medida y sus condiciones quedan junto a los criterios que la piden.
- **Sí:** no editar el SPEC 02, que está `Implementado`. El cambio de numeración queda en este spec y en `CLAUDE.md`.
- **No:** calcular o mostrar tiempos estimados de espera. Van al SPEC 04 o posterior.
- **No:** reinstalar el proyecto, cambiar las plantillas Django por React, cambiar SQLite por PostgreSQL ni tocar el modelo de cuentas.

---

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| La sala divulga datos de pacientes | La consulta arma cada llamado con cinco campos fijos. Hay pruebas de claves exactas y de ausencia del RUT y el nombre en la página y en el JSON. |
| El navegador bloquea el audio tras una recarga | La pantalla pide «Toque la pantalla para reactivar la voz», y el aviso visual nunca depende del sonido. El README explica el modo kiosco para quien lo quiera. |
| El equipo de la sala no tiene voz en español, o solo voces en línea | `elegirVoz` prioriza las voces locales, y sin voz suena igual la campanilla. Se prueba en el navegador del equipo. |
| Varios llamados seguidos alargan la cola de sonido (unos 7 s por anuncio) | Cada anuncio espera al anterior y la vigencia de 30 s descarta los viejos. La pantalla muestra todos de inmediato aunque el sonido vaya atrasado. |
| Un re-llamado doble entre sondeos se anuncia una sola vez | Es un límite documentado. Una bitácora de eventos o WebSocket se evalúa en otro spec si la prueba en el mesón lo pide. |
| Un corte de red hace pasar por actual información vieja | Aviso «Sin conexión» y hora de la última actualización. Los datos no se borran ni se inventan. |
| El pulso molesta a personas sensibles a los destellos | 3 pulsos lentos por llamado, bajo el umbral de 3 destellos por segundo, y ninguna animación con `prefers-reduced-motion`. |
| Varias pantallas consultando cada 2 s cargan el servidor | La consulta se limita a hoy y a 5 filas, hay una sola en curso por pantalla y la espera crece sin conexión. |
| El monitor de la sala tiene una sesión con cambio de clave pendiente | `CambioPasswordObligatorio` la redirige, igual que al tótem. El README indica abrir la sala en un navegador sin sesión. |
| La sala corre días sin recargarse y queda con un `sala.js` viejo tras actualizar el sistema | El README indica recargar la sala después de cada actualización. |
| La población adulta mayor no distingue los números | Letra grande en peso 800, alto contraste, ventanilla rotulada y redundancia entre aviso visual y sonoro. |
| El prototipo se interpreta como despliegue operativo | Datos sintéticos, y la latencia se informa como medición de laboratorio. |

---

## Lo que **no** está en este spec

- Estimación de espera, preparados pendientes de retiro y mermas (SPEC 04 o posteriores).
- Cambios al motor de cola o a las reglas del SPEC 02.
- WebSocket, Channels, Redis y bitácora de eventos.
- Estado, categoría o datos personales en la sala.
- Acciones desde la pantalla pública.
- Audio grabado, hardware de audio o de pantallas, y la instalación en el CESFAM.
- Integración con Rayén y datos reales.
- Módulo de distribución rural de medicamentos.
- Métricas reales de reducción de esperas.

Cada uno de esos, si se hace, va en su propio spec.

---

## Registro de verificación

Se completa al implementar. Condiciones: `cargar_datos_demo`, `runserver` en el mismo equipo, `/sala/` en un navegador sin sesión y `/atencion/` en otro.

| Comprobación | Condiciones | Resultado |
| --- | --- | --- |
| Latencia en 20 llamados (`servidor_en − ultimo_llamado_en`): mediana y máximo | Edge 156 sin cabeza en Windows 11 Pro; Intel Core i5-9300H, 16 GB; `runserver` de Django 5.2.1 con Python 3.13.3 y SQLite en el mismo equipo, sin red de por medio. 20 llamados reales por HTTP desde el panel, espaciados entre 2,3 y 4,7 s; latencias tomadas del `console.debug` de la sala | Mediana 1,101 s; mínimo 0,066 s; máximo 2,322 s. Cuadra con el sondeo cada 2 s más lo que tarda cada consulta. Es una medición de laboratorio, no una garantía para el CESFAM |
| Pantalla a 1920×1080 sin desplazamiento ni texto cortado | Edge 156 sin cabeza, controlado por el protocolo de DevTools; `runserver` local con `cargar_datos_demo` y 7 llamados sintéticos. Medido en los pasos 4, 5, 7, 8 y 9; el peor caso es el último llamado y los 4 anteriores con «Nuevo llamado», el aviso «Sin conexión», un aviso de voz («Toque la pantalla para reactivar la voz» o «Sin voz en español: suena la campanilla») y «Desactivar voz» | Cumple: la página mide 1920×1080 y ningún elemento de la sala desborda, también en el peor caso (la barra queda en una línea y termina en el píxel 1044). También cumple sin llamados y con números de cuatro cifras (`U-1000`) |
| Pantalla a 1366×768 sin desplazamiento ni texto cortado | Las mismas | Cumple: la página mide 1366×768 y ningún elemento de la sala desborda, también en el peor caso (la barra queda en una línea y termina en el píxel 742). También cumple sin llamados y con números de cuatro cifras |
| Control de voz con Tab, Enter y Espacio | Edge 156 sin cabeza, con las teclas enviadas por el protocolo de DevTools | Cumple: Tab da el foco al botón, y Enter y Espacio lo alternan; `aria-pressed` y el texto cambian entre «Activar voz» y «Desactivar voz» |
| Activar la voz, recargar y reactivarla con un toque | Edge 156 sin cabeza. Ese Edge deja sonar sin interacción, así que la política de un navegador normal se emuló en la página: un `AudioContext` suspendido sin gesto y un `speak` que falla con `not-allowed` | Cumple con la política emulada: con `sala:voz` en "1", recargar muestra «Toque la pantalla para reactivar la voz» y un llamado da solo el aviso visual; un toque lo quita y el siguiente llamado suena. Con `--autoplay-policy=no-user-gesture-required` (modo kiosco) no pide el toque y suena. Falta repetirlo en Edge normal |
| Campanilla y frase doble con un llamado y un re-llamado | Edge 156 sin cabeza, con registro de cada nota y locución desde la página; voz elegida: «Microsoft Catalina Online (Natural) - Spanish (Chile)», la única es-CL de Edge sin cabeza | Pendiente de oírse. Registrado: cada llamado y re-llamado toca las dos notas (659 y 523 Hz) y pide «Turno G 2, ventanilla 1.» dos veces; dos anuncios seguidos esperan su turno, y desactivar la voz corta el anuncio en curso. Edge sin cabeza no sintetiza la voz (`synthesis-failed`): falta oírlo en Edge normal con parlantes |
| Servidor detenido y reiniciado: aviso y sincronización sin ráfaga | Edge 156 sin cabeza. Corte del servidor de 65 s (paso 5) y cortes de la red del monitor de ~10 s y ~73 s (paso 10, con `Network.emulateNetworkConditions`), con el panel llamando durante el corte | Cumple: los datos se conservan, aparece «Sin conexión…» y la espera entre reintentos va 4 → 8 → 16 → 30 → 30 s. Tras el corte de ~10 s, el llamado hecho durante el corte se anuncia al reconectar (latencia 10,1 s). Tras el de ~73 s, los 3 llamados del corte aparecen en la lista sin anunciarse ni llevar etiqueta: no hay ráfaga. En 2 de 4 reinicios de `runserver`, la primera consulta quedó colgada; la sala la abortó a los 5 s y se sincronizó en el reintento siguiente (hasta unos 35 s) |
| Una persona del equipo sigue el README desde cero y ve en `/sala/` un llamado hecho desde el panel | Persona del equipo, en su equipo | Pendiente |

Notas de la implementación:

- **Edge sin cabeza y el sonido.** Deja sonar sin interacción y solo trae voces en línea, que ahí fallan con `synthesis-failed`. Por eso la campanilla y la frase doble quedan pendientes de oírse en Edge normal, y el aviso de toque se probó con la política del navegador emulada en la página.
- **El 404 de `/favicon.ico`.** Aparece en la consola en todas las páginas del sistema, también en la sala, porque el proyecto no tiene favicon. Es anterior a este spec, pero el criterio «sin errores en la consola» sin `speechSynthesis` lo cuenta. Falta decidir si se deja así o se agrega un favicon (`base.html`, fuera de este spec).
- **Decisiones tomadas al implementar.**
  - Las horas del JSON llevan milisegundos, para medir la latencia.
  - Las pruebas de Node se corren con `node --test "pruebas_js/*.test.js"`.
  - Sin voz en español suena solo la campanilla y la pantalla lo indica.
  - Al recargar con la voz activa se prueba el `AudioContext` y se pide el toque solo si queda suspendido. Así el modo kiosco no lo pide.
  - «Actualizado a las HH:MM» va junto al título del último llamado, para que la barra inferior quepa en una línea en el peor caso.

