/*
 * Pruebas de las funciones puras del domicilio (static/js/reparto.js), sin navegador: cómo se leen
 * las coordenadas escritas o pegadas, igual que `reparto.servicios.leer_coordenadas` en el
 * servidor. Se corren con `node --test "pruebas_js/*.test.js"`.
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');

const { leerCoordenadas, puntoDeLosCampos, distanciaEnMetros, textoDistancia } = require('../static/js/reparto.js');

test('lee una coordenada con punto o con coma decimal', () => {
  assert.deepEqual(leerCoordenadas('-36.4999'), [-36.4999]);
  assert.deepEqual(leerCoordenadas('-36,4999'), [-36.4999]);
  assert.deepEqual(leerCoordenadas('  -72.21  '), [-72.21]);
});

test('lee las dos coordenadas pegadas de un mapa', () => {
  assert.deepEqual(leerCoordenadas('-36.499912, -72.212834'), [-36.499912, -72.212834]);
  assert.deepEqual(leerCoordenadas('-36,499912, -72,212834'), [-36.499912, -72.212834]);
  assert.deepEqual(leerCoordenadas('-36,499912; -72,212834'), [-36.499912, -72.212834]);
  assert.deepEqual(leerCoordenadas('-36.499912 -72.212834'), [-36.499912, -72.212834]);
});

test('un texto vacío no tiene coordenadas', () => {
  assert.deepEqual(leerCoordenadas(''), []);
  assert.deepEqual(leerCoordenadas('   '), []);
  assert.deepEqual(leerCoordenadas(undefined), []);
});

test('rechaza lo que no es una coordenada', () => {
  for (const texto of ['abc', '-36.5 sur', '1, 2, 3', "36°30'S"]) {
    assert.equal(leerCoordenadas(texto), null, texto);
  }
});

test('arma el punto desde los dos campos', () => {
  assert.deepEqual(puntoDeLosCampos('-36.5', '-72.2'), [-36.5, -72.2]);
  assert.deepEqual(puntoDeLosCampos('-36,5', '-72,2'), [-36.5, -72.2]);
});

test('las dos pegadas en la latitud mandan sobre la longitud', () => {
  assert.deepEqual(puntoDeLosCampos('-36.50, -72.21', ''), [-36.5, -72.21]);
  assert.deepEqual(puntoDeLosCampos('-36.50, -72.21', '-72.99'), [-36.5, -72.21]);
  assert.deepEqual(puntoDeLosCampos('-36.50, -72.21', 'sur'), [-36.5, -72.21]);
});

test('sin un punto completo y válido no hay marcador', () => {
  assert.equal(puntoDeLosCampos('', ''), null);
  assert.equal(puntoDeLosCampos('-36.5', ''), null);
  assert.equal(puntoDeLosCampos('-91', '-72.2'), null);
  assert.equal(puntoDeLosCampos('-36.5', '-181'), null);
  assert.equal(puntoDeLosCampos('sur', '-72.2'), null);
});

test('mide la distancia en línea recta entre dos puntos', () => {
  assert.equal(distanciaEnMetros([-36.5, -72.2], [-36.5, -72.2]), 0);
  // Un grado de latitud son unos 111,2 km en cualquier parte.
  assert.ok(Math.abs(distanciaEnMetros([-36, -72.2], [-37, -72.2]) - 111195) < 10);
  // Del centro de San Nicolás a Camino a Dadinco km 4: unos 2,3 km.
  const metros = distanciaEnMetros([-36.4999, -72.2128], [-36.481234, -72.198765]);
  assert.ok(metros > 2300 && metros < 2500, metros);
});

test('redondea la distancia a lo que sirve para orientarse', () => {
  assert.equal(textoDistancia(3), '10 m');
  assert.equal(textoDistancia(347), '350 m');
  assert.equal(textoDistancia(997), '1 km');
  assert.equal(textoDistancia(1234), '1,2 km');
  assert.equal(textoDistancia(2000), '2 km');
  assert.equal(textoDistancia(12600), '13 km');
});
