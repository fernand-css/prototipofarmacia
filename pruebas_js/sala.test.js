/*
 * Pruebas de las funciones puras de la sala de espera (static/js/sala.js), sin navegador: qué se
 * anuncia, con qué frase y con qué voz. Se corren con `node --test "pruebas_js/*.test.js"`; usan
 * solo el ejecutor de pruebas que trae Node.
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');

const { identificador, llamadosNuevos, textoDelAnuncio, elegirVoz } = require('../static/js/sala.js');

const VIGENCIA = 30; // TURNOS_SEGUNDOS_VIGENCIA_ANUNCIO

const hora = (hhmmss) => `2026-10-24T${hhmmss}.000-03:00`;

function llamado(turnoId, numero, ventanilla, hhmmss, veces = 1) {
  return { turno_id: turnoId, numero, ventanilla, veces_llamado: veces, ultimo_llamado_en: hora(hhmmss) };
}

/* Una respuesta de /sala/estado/: `recientes` va del más reciente al más antiguo, como la entrega el servidor. */
function instantanea(servidor, recientes) {
  return { fecha: '2026-10-24', servidor_en: hora(servidor), actual: recientes[0] ?? null, recientes };
}

const vistos = (estado) => estado.recientes.map(identificador);
const numeros = (llamados) => llamados.map((l) => `${l.numero}:${l.veces_llamado}`);

// --- Qué se anuncia ---------------------------------------------------------------------------

const G045 = llamado(40, 'G-045', 1, '17:08:31');
const P012 = llamado(42, 'P-012', 2, '17:09:58');
const BASE = instantanea('17:10:00', [P012, G045]);

test('el identificador combina turno, vez y hora del llamado', () => {
  assert.equal(identificador(P012), '42:1:2026-10-24T17:09:58.000-03:00');
  assert.notEqual(identificador({ ...P012, veces_llamado: 2 }), identificador(P012));
});

test('la línea base no anuncia nada, aunque sus llamados sean recientes', () => {
  assert.deepEqual(llamadosNuevos(vistos(BASE), BASE, VIGENCIA), []);
});

test('tres instantáneas sin cambios no producen anuncios', () => {
  let previos = vistos(BASE);
  for (const servidor of ['17:10:02', '17:10:04', '17:10:06']) {
    const estado = instantanea(servidor, [P012, G045]);
    assert.deepEqual(llamadosNuevos(previos, estado, VIGENCIA), []);
    previos = vistos(estado);
  }
});

test('un llamado nuevo produce un anuncio', () => {
  const estado = instantanea('17:10:02', [llamado(43, 'G-046', 3, '17:10:01'), P012, G045]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['G-046:1']);
});

test('un re-llamado produce un anuncio nuevo del mismo número', () => {
  const rellamado = llamado(40, 'G-045', 1, '17:10:01', 2);
  const estado = instantanea('17:10:02', [rellamado, P012]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['G-045:2']);
});

test('dos llamados nuevos en la misma instantánea producen dos anuncios, del más antiguo al más reciente', () => {
  const estado = instantanea('17:10:04', [
    llamado(44, 'U-003', 4, '17:10:03'),
    llamado(43, 'G-046', 3, '17:10:01'),
    P012,
    G045,
  ]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['G-046:1', 'U-003:1']);
});

test('con la misma hora, se anuncia primero el turno de id menor, como desempata el servidor', () => {
  const estado = instantanea('17:10:04', [llamado(44, 'U-003', 4, '17:10:03'), llamado(43, 'G-046', 3, '17:10:03'), P012]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['G-046:1', 'U-003:1']);
});

test('un llamado más antiguo que la vigencia no se anuncia', () => {
  const estado = instantanea('17:10:40', [llamado(43, 'G-046', 3, '17:10:09'), P012, G045]);
  assert.deepEqual(llamadosNuevos(vistos(BASE), estado, VIGENCIA), []);
});

test('un llamado justo en el límite de la vigencia sí se anuncia', () => {
  const estado = instantanea('17:10:40', [llamado(43, 'G-046', 3, '17:10:10'), P012, G045]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['G-046:1']);
});

test('una reconexión tras un corte largo no anuncia nada', () => {
  const estado = instantanea('17:15:00', [
    llamado(45, 'G-047', 2, '17:12:30'),
    llamado(44, 'U-003', 4, '17:11:00'),
    llamado(43, 'G-046', 3, '17:10:20'),
    P012,
    G045,
  ]);
  assert.deepEqual(llamadosNuevos(vistos(BASE), estado, VIGENCIA), []);
});

test('tras una reconexión solo se anuncian los llamados dentro de la vigencia', () => {
  const estado = instantanea('17:11:00', [llamado(44, 'U-003', 4, '17:10:45'), llamado(43, 'G-046', 3, '17:10:20'), P012]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['U-003:1']);
});

test('dos re-llamados del mismo turno entre dos sondeos se anuncian una vez (límite conocido)', () => {
  const estado = instantanea('17:10:04', [llamado(40, 'G-045', 1, '17:10:03', 3), P012]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['G-045:3']);
});

test('no depende del reloj del monitor', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2031-01-01T00:00:00Z') });
  const estado = instantanea('17:10:02', [llamado(43, 'G-046', 3, '17:10:01'), P012, G045]);
  assert.deepEqual(numeros(llamadosNuevos(vistos(BASE), estado, VIGENCIA)), ['G-046:1']);
});

// --- La frase del anuncio ---------------------------------------------------------------------

test('la frase dice la letra, el número sin ceros a la izquierda y la ventanilla', () => {
  assert.equal(textoDelAnuncio('P-012', 2), 'Turno P 12, ventanilla 2.');
  assert.equal(textoDelAnuncio('U-003', 4), 'Turno U 3, ventanilla 4.');
  assert.equal(textoDelAnuncio('G-045', 1), 'Turno G 45, ventanilla 1.');
});

test('la frase conserva los ceros que no están a la izquierda y los números de cuatro cifras', () => {
  assert.equal(textoDelAnuncio('G-100', 3), 'Turno G 100, ventanilla 3.');
  assert.equal(textoDelAnuncio('G-1000', 12), 'Turno G 1000, ventanilla 12.');
});

// --- La voz -----------------------------------------------------------------------------------

const voz = (name, lang, localService) => ({ name, lang, localService });
const ES_CL_LOCAL = voz('Chile local', 'es-CL', true);
const ES_CL_EN_LINEA = voz('Chile en línea', 'es-CL', false);
const ES_MX_LOCAL = voz('México local', 'es-MX', true);
const ES_ES_EN_LINEA = voz('España en línea', 'es-ES', false);
const EN_US_LOCAL = voz('Inglés local', 'en-US', true);

test('prefiere una voz de Chile local', () => {
  const voces = [EN_US_LOCAL, ES_ES_EN_LINEA, ES_MX_LOCAL, ES_CL_EN_LINEA, ES_CL_LOCAL];
  assert.equal(elegirVoz(voces), ES_CL_LOCAL);
});

test('una voz de Chile en línea va antes que otra voz española local', () => {
  assert.equal(elegirVoz([EN_US_LOCAL, ES_MX_LOCAL, ES_CL_EN_LINEA]), ES_CL_EN_LINEA);
});

test('sin voz de Chile, prefiere otra voz española local', () => {
  assert.equal(elegirVoz([ES_ES_EN_LINEA, EN_US_LOCAL, ES_MX_LOCAL]), ES_MX_LOCAL);
});

test('sin voces locales en español, usa una en línea', () => {
  assert.equal(elegirVoz([EN_US_LOCAL, ES_ES_EN_LINEA]), ES_ES_EN_LINEA);
});

test('reconoce el idioma escrito con guion bajo o en minúsculas', () => {
  const android = voz('Android', 'es_CL', true);
  assert.equal(elegirVoz([ES_MX_LOCAL, android]), android);
  const minusculas = voz('Minúsculas', 'es-cl', false);
  assert.equal(elegirVoz([ES_ES_EN_LINEA, minusculas]), minusculas);
  const generica = voz('Español', 'es', true);
  assert.equal(elegirVoz([EN_US_LOCAL, generica]), generica);
});

test('sin ninguna voz en español devuelve null', () => {
  assert.equal(elegirVoz([EN_US_LOCAL, voz('Euskera', 'eu-ES', true), voz('Estonio', 'et-EE', true)]), null);
  assert.equal(elegirVoz([]), null);
});
