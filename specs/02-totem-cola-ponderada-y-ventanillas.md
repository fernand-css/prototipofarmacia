# SPEC 02 — Tótem de turnos, cola ponderada y ventanillas

> **Estado:** Implementado
> **Depende de:** SPEC 01
> **Fecha:** 2026-10-21
> **Objetivo:** Permitir que el paciente saque su turno digitando el RUT en un tótem y que el funcionario lo llame, re-llame, atienda o marque ausente desde una ventanilla, con un motor que ordena la fila según la categoría del paciente.

---

## Por qué existe este spec

El spec 01 dejó las cuentas y el login. Este es el primer spec con el dominio de la farmacia: la fila de turnos que hoy se resuelve con dos rollos de papel. Sale del informe del Proyecto de Título (historias HU-04, HU-05, HU-06, HU-07, HU-10 y HU-21), acotado a lo que cabe en un spec.

Se pidió originalmente incluir también la estimación de espera y toda la interacción con recetas. Se decidió partir el trabajo: este spec es el **núcleo** (emitir, ordenar, llamar) y el spec 03 será la estimación de espera y lo que depende de tiempos de preparación de recetas. Aquí entra solo el mínimo de recetas que el tótem necesita para clasificar y bloquear, porque sin él no se puede deducir si un paciente es crónico.

Rayén (el sistema clínico del CESFAM) **no se integra**. Los pacientes y sus recetas crónicas son una base simulada, propia del sistema, tal como declara el informe.

---

## Alcance

**Dentro:**

- App Django `turnos`, montada en la raíz junto a `cuentas`.
- Base de pacientes y recetas crónicas **simuladas** (modelos `Paciente` y `RecetaCronica`), administrables desde el admin de Django y cargables con un comando de datos de demostración.
- Tótem público en `/totem/`: teclado numérico en pantalla, validación del RUT con los validadores del spec 01, emisión de turno y botón para imprimirlo.
- Deducción automática de la categoría: el paciente solo digita el RUT.
- Motor de cola ponderada: urgencia absoluta, y entre preferencial y general una proporción fija configurable (por defecto 2 generales por cada 1 preferencial). Dentro de cada categoría, orden de llegada.
- Ventanillas: la QF las crea y las habilita o deshabilita; el funcionario abre una ventanilla libre al comenzar y la cierra con "Terminar turno".
- Panel de atención del funcionario: llamar siguiente, re-llamar, iniciar atención, finalizar, marcar ausente y emitir turno de urgencia por RUT.
- Bloqueo de turno cuando el paciente tiene recetas crónicas y ninguna es utilizable (vencidas o con las entregas agotadas), y suma de una entrega al finalizar la atención de un turno con receta.
- Aviso en el tótem para pacientes de despacho a domicilio (postrados o mayores de 80 años), con botón para pedir turno igual.
- Cola visible en el panel, refrescada por polling.
- Pruebas automatizadas, incluidos tres escenarios de simulación de carga del motor.
- Ajuste a lo del spec 01: el funcionario aterriza en el panel de atención y la barra superior muestra los enlaces que correspondan al rol.

**Fuera de alcance (para specs futuros):**

- **Estimación de tiempo de espera** (HU-18) y cualquier registro de tiempos de preparación de recetas. Spec 03.
- Marca "receta preparada", listado de "preparados pendientes de retiro" (HU-17) y panel de mermas (HU-20). Spec 03 o posteriores.
- Registrar una renovación médica desde una pantalla. Por ahora se hace editando la receta en el admin.
- Pantalla de la sala de espera, voz y alertas sonoras (HU-08, HU-09), y sincronización por WebSocket. Spec aparte. Este spec deja el llamado guardado en `Turno` para que esa pantalla lo consuma.
- Proporción dinámica según las ventanillas habilitadas, y proporción editable por la QF desde la interfaz.
- Tipos de atención asignados por ventanilla (parte de HU-10), eliminar ventanillas e historial de aperturas y cierres de ventanilla.
- Reingreso del ausente: el ausente es un estado final y debe sacar un turno nuevo.
- Alerta por superar los 15 minutos de espera (HU-11).
- Módulo de entregas a domicilio (HU-12 a HU-16, HU-19, HU-22). El tótem solo avisa que el paciente es de despacho a domicilio.
- Integración real con Rayén.
- Impresora térmica dedicada. Se usa la impresión del navegador.
- Funciones propias del Encargado de Terreno. Sigue con la página de inicio de marcador de posición.

---

## Modelo de datos

Archivo `turnos/models.py`. Todo RUT se normaliza con `cuentas.validators.normalizar_rut` y se valida con `validar_rut`, igual que en el spec 01.

```python
class Categoria(models.TextChoices):
    URGENCIA = "urgencia", "Urgencia"              # letra U
    PREFERENCIAL = "preferencial", "Preferencial"  # letra P
    GENERAL = "general", "General"                 # letra G


class EstadoTurno(models.TextChoices):
    EN_ESPERA = "en_espera", "En espera"
    LLAMADO = "llamado", "Llamado"
    EN_ATENCION = "en_atencion", "En atención"
    ATENDIDO = "atendido", "Atendido"
    AUSENTE = "ausente", "Ausente"
    ANULADO = "anulado", "Anulado"
```

```python
class Paciente(models.Model):                       # simulación de Rayén
    rut = models.CharField(max_length=10, unique=True, validators=[validar_rut])
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    tiene_discapacidad = models.BooleanField(default=False)
    esta_embarazada = models.BooleanField(default=False)
    es_postrado = models.BooleanField(default=False)
    # Propiedades: edad, es_preferencial, es_despacho_domicilio
```

```python
class RecetaCronica(models.Model):                  # simulación de Rayén
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="recetas")
    fecha_emision = models.DateField()
    vigencia_meses = models.PositiveSmallIntegerField()
    entregas_maximas = models.PositiveSmallIntegerField()
    entregas_realizadas = models.PositiveSmallIntegerField(default=0)
    # Propiedades: fecha_vencimiento, esta_vencida, esta_agotada, es_utilizable
```

```python
class Ventanilla(models.Model):
    numero = models.PositiveSmallIntegerField(unique=True)
    habilitada = models.BooleanField(default=True)
    funcionario = models.OneToOneField(           # quién la tiene abierta ahora
        Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name="ventanilla_abierta"
    )
```

```python
class Turno(models.Model):
    fecha = models.DateField(default=timezone.localdate)   # día operativo
    categoria = models.CharField(max_length=15, choices=Categoria.choices)
    correlativo = models.PositiveIntegerField()
    rut = models.CharField(max_length=10, db_index=True)   # siempre se guarda, haya o no Paciente
    paciente = models.ForeignKey(Paciente, null=True, blank=True, on_delete=models.PROTECT)
    receta = models.ForeignKey(RecetaCronica, null=True, blank=True, on_delete=models.PROTECT)
    estado = models.CharField(max_length=15, choices=EstadoTurno.choices, default=EstadoTurno.EN_ESPERA)
    ventanilla = models.ForeignKey(Ventanilla, null=True, blank=True, on_delete=models.PROTECT)
    atendido_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT)
    emitido_en = models.DateTimeField(default=timezone.now)
    llamado_en = models.DateTimeField(null=True, blank=True)          # primer llamado
    ultimo_llamado_en = models.DateTimeField(null=True, blank=True)   # llamado o re-llamado más reciente
    veces_llamado = models.PositiveSmallIntegerField(default=0)
    inicio_atencion_en = models.DateTimeField(null=True, blank=True)
    cierre_en = models.DateTimeField(null=True, blank=True)           # atendido, ausente o anulado

    class Meta:
        constraints = [
            UniqueConstraint(fields=["fecha", "categoria", "correlativo"], name="turno_numero_unico_por_dia"),
            UniqueConstraint(
                fields=["fecha", "rut"],
                condition=Q(estado__in=["en_espera", "llamado", "en_atencion"]),
                name="turno_un_activo_por_rut_y_dia",
            ),
        ]
    # Propiedades: numero ("P-012"), es_cronico (receta_id is not None)
```

Constantes nuevas en `farmacia_turnos/settings.py`:

```python
TURNOS_EDAD_PREFERENCIAL = 60                # 60 años o más
TURNOS_EDAD_DESPACHO_DOMICILIO = 80          # estrictamente mayor de 80
TURNOS_GENERALES_POR_PREFERENCIAL = 2
TURNOS_SEGUNDOS_MINIMOS_AUSENTE = 60
TURNOS_SEGUNDOS_REFRESCO_PANEL = 5
TURNOS_SEGUNDOS_ACTIVIDAD_RECIENTE = 60       # el sondeo renueva la sesión si hubo actividad en este plazo
TURNOS_SEGUNDOS_RESULTADO_TOTEM = 15
TURNOS_SEGUNDOS_INACTIVIDAD_TOTEM = 30
```

**Convenciones:**

- **Número de turno:** letra de la categoría más correlativo de tres dígitos (`U-003`, `P-012`, `G-045`). El correlativo es independiente por letra y se reinicia cada día (`fecha`).
- **Día operativo:** todo lo que mira el motor y el tótem filtra por `fecha = hoy`. Un turno que quedó abierto el día anterior no bloquea al paciente ni entra a la cola.
- **Categoría, deducida al emitir:** `PREFERENCIAL` si el paciente tiene 60 años o más, discapacidad o embarazo; `GENERAL` en otro caso, incluido un RUT válido que no existe en `Paciente` (el turno guarda el `rut` y deja `paciente` en nulo). `URGENCIA` solo la emite un funcionario desde el panel.
- **Crónico:** no es una categoría, es una etiqueta (`Turno.receta` no nulo). No tiene peso en el motor; sirve para el bloqueo y para contar la entrega.
- **Receta utilizable:** no vencida (`hoy <= fecha_emision + vigencia_meses`) y con `entregas_realizadas < entregas_maximas`. Al emitir se asigna al turno la utilizable más antigua. El cálculo de meses se hace sin librerías nuevas.
- **Bloqueo:** el paciente tiene al menos una receta y ninguna es utilizable. Sin recetas no hay bloqueo.
- **Despacho a domicilio:** `es_postrado` o edad estrictamente mayor que `TURNOS_EDAD_DESPACHO_DOMICILIO`.
- **Orden del motor:**
  1. Si hay urgencias en espera, la más antigua.
  2. Si no, se cuentan los turnos generales llamados **consecutivamente** hoy desde el último preferencial llamado (ordenados por `llamado_en`, ignorando urgencias). Si ese conteo es `>= TURNOS_GENERALES_POR_PREFERENCIAL` y hay preferenciales en espera, el más antiguo.
  3. Si no, el general más antiguo.
  4. Si no hay generales, el preferencial más antiguo. Si no hay nadie, no hay siguiente.
  Los ausentes cuentan como llamados, porque ocuparon su lugar en la proporción.
- **Transiciones válidas:**
  - `en_espera → llamado` (llamar siguiente).
  - `llamado → llamado` (re-llamar: suma `veces_llamado` y renueva `ultimo_llamado_en`; conserva ventanilla y funcionario).
  - `llamado → en_atencion` (iniciar).
  - `llamado → ausente` (solo si pasaron `TURNOS_SEGUNDOS_MINIMOS_AUSENTE` desde `ultimo_llamado_en`; lo valida el servidor).
  - `en_atencion → atendido` (finalizar; si hay `receta`, suma 1 a `entregas_realizadas`).
  - `en_espera → anulado` (cuando un funcionario emite una urgencia para el mismo RUT).
- Un funcionario tiene como máximo un turno `llamado` o `en_atencion` a la vez. Un turno nunca cambia de ventanilla ni de funcionario.
- El llamado queda en `Turno` (`estado`, `ventanilla`, `ultimo_llamado_en`, `veces_llamado`). No hay tabla de eventos aparte.

---

## Plan de implementación

1. Crear la app con `python manage.py startapp turnos`, registrarla en `INSTALLED_APPS`, añadir las constantes `TURNOS_*` a `settings.py` y montar `path("", include("turnos.urls"))` en `farmacia_turnos/urls.py` con un `turnos/urls.py` vacío (`app_name = "turnos"`). **Verificación:** `python manage.py check` no reporta errores.
2. Escribir `Paciente` y `RecetaCronica` con sus propiedades. `save()` normaliza el RUT. Migración y registro de ambos modelos en `turnos/admin.py`. **Verificación:** desde el admin se crea un paciente con RUT `12.345.678-5` y queda guardado como `12345678-5`; un RUT con dígito verificador malo es rechazado.
3. Escribir `Categoria`, `EstadoTurno`, `Ventanilla` y `Turno` con sus restricciones, migración y registro de `Ventanilla` y `Turno` en el admin como acceso técnico. **Verificación:** `python manage.py migrate` aplica sin errores; un test crea dos turnos activos para el mismo RUT el mismo día y la base rechaza el segundo.
4. Escribir el comando `turnos/management/commands/cargar_datos_demo.py`: 4 ventanillas y pacientes que cubran cada caso (general, adulto mayor, embarazada, con discapacidad, mayor de 80, postrado, crónico con receta utilizable, crónico con receta agotada, crónico con receta vencida). Los RUT demo se calculan con el módulo 11 para que sean válidos. Es idempotente. **Verificación:** ejecutarlo dos veces seguidas deja las mismas cantidades de filas.
5. Escribir `turnos/servicios.py::emitir_turno(rut, *, desde_panel=False, insistir_domicilio=False)`, que normaliza y valida el RUT y devuelve un resultado con uno de cuatro tipos: `EMITIDO`, `VIGENTE`, `DOMICILIO`, `BLOQUEADO`. Orden de comprobaciones: turno vigente del día, despacho a domicilio (salvo `insistir_domicilio`), bloqueo por receta, emisión. Desde el panel (urgencia) no se aplican ni el aviso de domicilio ni el bloqueo, y se anula el turno `en_espera` previo del mismo RUT; si ese RUT está `llamado` o `en_atencion` no se emite. El correlativo se calcula dentro de `transaction.atomic()` y se reintenta hasta 3 veces ante `IntegrityError`. **Verificación:** tests que cubren cada rama, que `12.345.678-5` y `123456785` dan el mismo turno vigente y que el correlativo se reinicia al cambiar la fecha.
6. Implementar el tótem: vistas públicas `totem` (`GET /totem/`) y `totem_turno` (`POST /totem/turno/`), plantillas `turnos/totem.html` y `turnos/totem_resultado.html`, y estilos en `static/css/estilos.css` bajo `{% block clase_body %}pagina-totem{% endblock %}` (letra grande, alto contraste, sin barra superior). El teclado numérico lleva dígitos, `K`, borrar y confirmar, y se limpia tras `TURNOS_SEGUNDOS_INACTIVIDAD_TOTEM`. El resultado muestra solo el número y la categoría, nunca el nombre ni el RUT; vuelve al inicio tras `TURNOS_SEGUNDOS_RESULTADO_TOTEM`; incluye "Imprimir" con una hoja de estilos `@media print`. Los casos `DOMICILIO` y `BLOQUEADO` muestran su mensaje; el primero ofrece "Pedir turno igual". **Verificación:** sin sesión iniciada, `/totem/` carga y emite un turno con `12.345.678-5`; con un RUT inválido muestra el error y pide uno válido.
7. Escribir `turnos/motor.py::elegir_siguiente(fecha)` con la regla de orden descrita arriba, sin modificar datos. **Verificación:** tests con los tres escenarios de simulación (ver criterios de aceptación).
8. Escribir el mixin `SoloAtencion` en `turnos/mixins.py` (funcionario y QF pueden atender; el Encargado de Terreno recibe 403) y las vistas de la QF para ventanillas, con `SoloQF`: `ventanillas_lista`, `ventanilla_crear` y `ventanilla_cambiar_estado`. Deshabilitar una ventanilla con un turno `llamado` o `en_atencion` se rechaza con un aviso; si solo está abierta, se libera. Plantilla `turnos/ventanillas_lista.html`. **Verificación:** la QF crea la ventanilla 5 y la deshabilita; un funcionario que abre `/ventanillas/` recibe 403.
9. Implementar el panel de atención `GET /atencion/` y las acciones `abrir` y `terminar`: sin ventanilla abierta, el funcionario elige una habilitada y libre; con una abierta ve su panel; "Terminar turno" libera la ventanilla y se rechaza si hay un turno en curso. **Verificación:** dos funcionarios no pueden abrir la misma ventanilla.
10. Escribir `turnos/servicios.py::llamar_siguiente(usuario)` y `re_llamar(usuario)`. Para evitar que dos ventanillas tomen el mismo turno, `llamar_siguiente` elige con el motor y hace un `UPDATE ... WHERE id = X AND estado = 'en_espera'`; si no actualiza ninguna fila, vuelve a elegir. Botones en el panel. **Verificación:** test con un solo turno en espera y dos funcionarios: el primero lo recibe y el segundo recibe "no hay pacientes en espera".
11. Escribir `iniciar_atencion`, `finalizar_atencion` y `marcar_ausente`, con las transiciones válidas y el plazo de 60 segundos validado en el servidor. `finalizar_atencion` suma la entrega a la receta con `F("entregas_realizadas") + 1` dentro de la misma transacción. **Verificación:** tests de cada transición válida e inválida y del contador de la receta.
12. Añadir en el panel el formulario "Turno de urgencia" (RUT) que usa `emitir_turno(..., desde_panel=True)`. **Verificación:** un paciente `G-045` en espera pasa a `anulado` y recibe `U-001`, que es el siguiente en ser llamado.
13. Mostrar la cola en el panel: contadores y lista de espera por categoría, en el fragmento `turnos/_cola.html` servido por `GET /atencion/cola/`. El panel lo pide con `fetch` cada `TURNOS_SEGUNDOS_REFRESCO_PANEL` segundos desde Alpine, sin librerías nuevas. Esas consultas no renuevan la sesión por sí solas: el navegador envía la cabecera `X-Actividad-Reciente` solo si hubo un clic, una tecla, un toque o movimiento en los últimos `TURNOS_SEGUNDOS_ACTIVIDAD_RECIENTE` segundos, y el middleware `cuentas.middleware.SesionPorActividad` renueva la sesión únicamente en ese caso. **Verificación:** al emitir un turno en el tótem, aparece en el panel sin recargar la página en 5 segundos o menos.
14. Ajustar `cuentas.views.inicio` para que el funcionario vaya al panel de atención (el Encargado de Terreno conserva el marcador de posición), agregar los enlaces de navegación a `templates/base.html` según rol, y actualizar `CLAUDE.md` y `README.md` con la nueva app, el comando de demostración y las rutas. **Verificación:** cada rol aterriza en su página y ve solo los enlaces que le corresponden.

---

## Criterios de aceptación

- [ ] `python manage.py test` pasa completo, incluidos los tests de `cuentas`.
- [ ] `python manage.py cargar_datos_demo` se puede ejecutar dos veces sin duplicar filas.
- [ ] `/totem/` carga sin sesión iniciada y no muestra la barra con el nombre de ningún usuario.
- [ ] `12.345.678-5`, `123456785` y `12345678-5` en el tótem identifican al mismo paciente.
- [ ] Un RUT con dígito verificador incorrecto es rechazado en el tótem con un mensaje visible y no crea ningún turno.
- [ ] Un paciente de 60 años o más, con discapacidad o embarazada recibe un turno con letra `P`.
- [ ] Un paciente menor de 60 sin condiciones, y un RUT válido que no está en `Paciente`, reciben un turno con letra `G`.
- [ ] El número de turno tiene la forma `G-045` y el correlativo de cada letra se reinicia al día siguiente.
- [ ] Un paciente con un turno `en_espera`, `llamado` o `en_atencion` que vuelve a digitar su RUT ve su turno vigente y no se crea otro.
- [ ] Un paciente cuyo último turno quedó `atendido` o `ausente` puede sacar un turno nuevo el mismo día.
- [ ] Un paciente postrado, o mayor de 80 años, ve el aviso de despacho a domicilio y no recibe turno hasta pulsar "Pedir turno igual".
- [ ] Un paciente con recetas crónicas y ninguna utilizable no recibe turno y ve el mensaje de renovación médica.
- [ ] Un paciente con una receta utilizable recibe un turno con esa receta asociada.
- [ ] La pantalla de resultado del tótem y la hoja impresa muestran el número y la categoría, y no el nombre ni el RUT.
- [ ] El tótem vuelve a la pantalla de inicio tras `TURNOS_SEGUNDOS_RESULTADO_TOTEM` segundos.
- [ ] Con urgencias en espera, el siguiente llamado es siempre la urgencia más antigua.
- [ ] Escenario A, carga mixta (6 generales y 3 preferenciales emitidos antes de empezar): el orden de llamado es G, G, P, G, G, P, G, G, P, cada categoría por orden de llegada.
- [ ] Escenario B, mayoría preferencial (1 general y 3 preferenciales): el orden es G, P, P, P.
- [ ] Escenario C, extensión horaria con una ventanilla (3 generales y una urgencia emitida después): el orden es U, G, G, G.
- [ ] Cambiar `TURNOS_GENERALES_POR_PREFERENCIAL` a 3 cambia el orden del escenario A a G, G, G, P, G, G, G, P, P, sin tocar el motor.
- [ ] Dos funcionarios con ventanilla abierta que llaman con un solo turno en espera: uno lo recibe y el otro recibe "no hay pacientes en espera".
- [ ] El mismo turno nunca queda asignado a dos ventanillas.
- [ ] Re-llamar un turno conserva su ventanilla y su funcionario, suma 1 a `veces_llamado` y renueva `ultimo_llamado_en`.
- [ ] "Ausente" se rechaza antes de `TURNOS_SEGUNDOS_MINIMOS_AUSENTE` segundos desde el último llamado o re-llamado, aunque la petición se envíe a mano.
- [ ] Un turno `ausente` no vuelve a la fila ni se puede reingresar.
- [ ] Finalizar la atención de un turno con receta suma exactamente 1 a `entregas_realizadas`; marcarlo ausente no la modifica.
- [ ] Al llegar al máximo de entregas, el mismo paciente es bloqueado en el tótem.
- [ ] Un funcionario no puede llamar un nuevo turno mientras tiene uno `llamado` o `en_atencion`.
- [ ] Un funcionario no puede terminar su turno de ventanilla mientras tiene un turno en curso.
- [ ] Dos funcionarios no pueden abrir la misma ventanilla, y una ventanilla deshabilitada no aparece como opción.
- [ ] Emitir una urgencia para un RUT con turno `en_espera` deja ese turno `anulado`; si el turno está `llamado` o `en_atencion`, no se emite.
- [ ] La QF puede crear, habilitar y deshabilitar ventanillas; un funcionario que abre esas URLs recibe 403.
- [ ] El Encargado de Terreno recibe 403 en el panel de atención y en la gestión de ventanillas.
- [ ] Un turno emitido en el tótem aparece en la cola del panel en 5 segundos o menos, sin recargar.
- [ ] Un usuario sin sesión que abre `/atencion/` o `/ventanillas/` es redirigido al login.
- [ ] Un panel sin actividad del usuario deja vencer la sesión a los 30 minutos aunque siga consultando la fila, y una consulta con actividad reciente la renueva.
- [ ] Un usuario con `debe_cambiar_password` activo sigue siendo redirigido al cambio de clave en las rutas nuevas, y el tótem sigue siendo accesible sin sesión.

---

## Decisiones

- **Sí:** partir el trabajo en dos specs: núcleo (este) y espera/recetas (03). La estimación de espera necesita tiempos de atención reales y de preparación, que solo existen cuando este spec esté funcionando.
- **Sí:** tabla `Paciente` simulada tipo Rayén. El RUT no trae edad ni condiciones, y sin esos datos el motor no puede distinguir preferenciales. Es lo que el informe declara: base y emisión de recetas propias, sin integración real.
- **No:** que el paciente declare su categoría en el tótem. Es fácil de abusar y no sirve para postrados ni crónicos.
- **Sí:** que el sistema deduzca la categoría y el paciente solo digite el RUT. La población es mayoritariamente rural y adulta mayor: una sola pantalla reduce errores.
- **No:** que el paciente elija el "motivo de atención" con botones. Abre la puerta a elegir "Urgencia" sin serlo.
- **Sí:** un RUT válido pero ausente de `Paciente` recibe un turno general. Negarle el turno por no estar en una base simulada dejaría a un paciente real sin atención.
- **Sí:** letra más correlativo diario por categoría (`P-012`). Distingue las filas a simple vista, que es lo que confundía con los dos rollos de papel.
- **Sí:** urgencia absoluta, y proporción fija 2 generales : 1 preferencial en `settings.py`. Es simple, determinista y probable en tres escenarios, que es lo que pide el objetivo específico del informe.
- **No:** proporción dinámica según las ventanillas habilitadas. El informe la menciona, pero no hay una regla definida para calcularla; se evalúa en un spec posterior cuando exista el dato real de operación.
- **No:** proporción editable por la QF. Exige un modelo de configuración y una pantalla que hoy no se justifican.
- **Sí:** crónico como etiqueta y no como categoría. Darle peso propio convertiría la proporción en una tabla y diluiría la preferencia de los adultos mayores.
- **Sí:** el conteo de la proporción se calcula desde los llamados del día y no se guarda en un contador aparte. No hay estado que se pueda desincronizar, y sobrevive a un reinicio del servidor.
- **Sí:** el ausente es un estado final y debe sacar un turno nuevo. Simplifica el motor; el costo es que el paciente pierde su lugar. Se podrá revisar con datos reales.
- **No:** botón "Reingresar". Se había considerado, pero contradice la decisión anterior.
- **Sí:** que el servidor valide los 60 segundos del ausente, contados desde el último llamado o re-llamado. Así el paciente tiene siempre un minuto completo tras oír su número, y el plazo no depende de que el botón esté deshabilitado en pantalla.
- **Sí:** estado `anulado`, añadido a los pedidos. La urgencia por RUT ya impide dejar dos turnos activos para el mismo paciente; sin `anulado` un paciente en espera no podría ser pasado a urgencia.
- **No:** convertir un turno `G-045` a urgente conservando el número. El paciente quedaría con una letra que no coincide con su categoría.
- **Sí:** el tótem muestra el turno vigente si el RUT ya tiene uno. Evita turnos duplicados y ayuda a quien perdió el papel.
- **Sí:** restricción única parcial `(fecha, rut)` sobre los estados activos. La base garantiza lo que la lógica promete aunque dos tótems reciban el mismo RUT a la vez.
- **Sí:** asignación con `UPDATE` condicional y reintento, más restricciones únicas en la base. `select_for_update` no hace nada en SQLite, y esta técnica funciona igual al migrar a PostgreSQL.
- **Sí:** ventanilla como puesto físico que el funcionario abre al comenzar. Calza con el computador compartido del mesón y no ata una ventanilla a una persona.
- **No:** ventanilla fija por funcionario ni tipos de atención por ventanilla. Lo primero no sirve con el equipo compartido; lo segundo agrega configuración que hoy no hace falta.
- **Sí:** ventanillas que se deshabilitan pero no se borran, como las cuentas en el spec 01: los turnos históricos apuntan a ellas.
- **Sí:** deshabilitar una ventanilla con un turno en curso se rechaza. El informe pide confirmación; un rechazo evita dejar un turno `llamado` huérfano y es más simple de implementar y probar.
- **Sí:** funcionario y QF atienden; el Encargado de Terreno no. La QF es la jefatura y cubre al personal cuando falta, algo que el informe señala (seis personas para cuatro ventanillas). El Encargado de Terreno tendrá sus propias funciones. Revisar al aprobar.
- **Sí:** el sondeo de la fila solo renueva la sesión si el navegador informa actividad real del usuario. Con `SESSION_SAVE_EVERY_REQUEST` cada consulta la renovaba, y un panel olvidado en el computador compartido nunca vencía: se anulaba el cierre por inactividad del spec 01.
- **No:** que el sondeo renueve siempre la sesión (más cómodo, pero deja una sesión abierta en un equipo compartido) ni que nunca la renueve (quien solo mira la fila 30 minutos sin moverse perdería la sesión aunque esté frente al panel).
- **Sí:** polling cada 5 segundos para el panel. No suma dependencias y cumple la latencia del informe (2 s) de forma razonable para un MVP; WebSocket llega con la pantalla de sala.
- **No:** Django Channels ni Redis ahora. Complican el despliegue en SQLite y el panel no los necesita.
- **Sí:** el tótem es público y sin login. El spec 01 ya dejó la emisión de tickets sin sesión; este spec limita esa excepción a `/totem/` y sus rutas, y precisa así el criterio "ninguna página es accesible sin sesión" del spec 01.
- **Sí:** el tótem no muestra nombres ni RUT en el resultado ni en la impresión. Son datos personales y de salud (Ley 19.628) en una pantalla pública.
- **Sí:** impresión con el navegador. Cubre la necesidad de llevar el número sin comprar ni integrar hardware.
- **Sí:** Paciente y RecetaCronica se administran desde el admin de Django. Es la simulación de Rayén, no una interfaz de la QF; el admin sigue siendo acceso técnico, igual que en el spec 01.
- **Sí:** el bloqueo por receta incluye las vencidas, no solo las agotadas. El informe nombra el vencimiento como motivo de la regla, pero solo detalla el máximo de entregas en sus criterios.

---

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Cualquier persona puede digitar el RUT de otra en el tótem y enterarse de que es de despacho a domicilio o de que su receta necesita renovación | Los mensajes dicen solo lo necesario para actuar ("su despacho es a domicilio", "requiere renovación médica") y nunca muestran nombre, RUT ni diagnóstico. Si el CESFAM lo considera insuficiente, se agrega una verificación adicional en otro spec. |
| El motor deja esperando mucho a un preferencial cuando hay muchos generales (hasta 2 antes de cada preferencial) | Valor en `settings.py`, ajustable tras probarlo en el mesón. Una proporción dinámica queda para un spec posterior. |
| Un funcionario deja su sesión o cierra el navegador con una ventanilla abierta o un turno `llamado` | Al volver a iniciar sesión recupera su ventanilla (relación uno a uno). La QF puede liberar la ventanilla y corregir el turno desde el admin. Una liberación forzada con pantalla propia queda para otro spec. |
| La sesión del funcionario expira a los 30 minutos sin actividad mientras atiende | El sondeo solo renueva la sesión si hubo actividad del usuario en el último minuto: quien atiende, o mira el panel y mueve el mouse, la mantiene; un panel olvidado vence a los 30 minutos, como pide el spec 01. Si vence, el panel lo detecta y recarga hacia el login. |
| Dos pacientes obtienen el mismo número, o un turno va a dos ventanillas | Restricciones únicas en la base más `UPDATE` condicional con reintento. Hay pruebas para cada caso. |
| Los datos de demostración se confunden con datos reales | El comando imprime una advertencia y los pacientes demo usan nombres evidentes. El comando no está pensado para producción. |
| Pacientes reales sin registro en `Paciente` (por ejemplo, una persona mayor de 80 años) reciben turno general sin su preferencia | Mientras no haya integración con Rayén, el funcionario puede emitirle una urgencia o se carga el paciente en el admin. Se resuelve de raíz con la integración real. |
| Datos de salud bajo la Ley 19.628 | Este spec guarda pacientes y recetas simulados. Antes de usar datos reales se requiere una revisión de protección de datos y de la política de retención. |

---

## Lo que **no** está en este spec

- Estimación del tiempo de espera y tiempos de preparación de recetas (spec 03).
- "Preparados pendientes de retiro" y panel de mermas.
- Pantalla de sala de espera, voz y WebSocket.
- Proporción dinámica o editable, y tipos de atención por ventanilla.
- Reingreso del ausente.
- Módulo de entregas a domicilio.
- Integración real con Rayén e impresora térmica.
- Funciones del Encargado de Terreno.

Cada uno de esos, si se hace, va en su propio spec.
