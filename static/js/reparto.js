/*
 * Domicilios de los pacientes con despacho a domicilio: el mapa de la ficha y la ubicación del GPS.
 *
 * Arriba, la función pura que lee coordenadas escritas o pegadas: no toca el DOM ni Alpine, y se
 * prueba en Node con `node --test "pruebas_js/*.test.js"`, que carga este mismo archivo. Es la
 * misma regla que `reparto.servicios.leer_coordenadas` en el servidor, que es quien valida.
 * Abajo, los componentes Alpine, que solo se registran en el navegador.
 *
 * El mapa es una ayuda: lo que se guarda son siempre los campos de latitud y longitud. El mapa los
 * llena al tocarlo o al arrastrar el marcador, y se mueve cuando se escriben. Si las teselas de
 * OpenStreetMap no cargan (sin señal o sin internet), avisa y el formulario sigue funcionando.
 *
 * Este archivo se carga ANTES de Alpine (bloque "scripts" de base.html), después de Leaflet.
 */
(() => {
  const NUMERO = /-?\d+(?:[.,]\d+)?/g;
  const SEPARADORES = /[\s,;]*/g;

  /*
   * Una o dos coordenadas de un texto: «-36.5», «-36,5» o «-36.50, -72.21» pegado de un mapa.
   * Devuelve un arreglo de números (vacío si el texto está vacío) o null si hay algo que no es un
   * número, o más de dos.
   */
  function leerCoordenadas(texto) {
    const limpio = String(texto ?? '').trim();
    if (!limpio) return [];
    const numeros = limpio.match(NUMERO) ?? [];
    const sobrante = limpio.replace(NUMERO, '').replace(SEPARADORES, '');
    if (!numeros.length || numeros.length > 2 || sobrante) return null;
    return numeros.map((numero) => Number(numero.replace(',', '.')));
  }

  /*
   * Un punto válido para el mapa a partir de los dos campos, o null. Si la latitud trae las dos
   * pegadas, mandan sobre lo que diga la longitud: quien pega las dos quiere reemplazar las dos.
   */
  function puntoDeLosCampos(textoLatitud, textoLongitud) {
    let latitud = leerCoordenadas(textoLatitud);
    let longitud = leerCoordenadas(textoLongitud);
    if (latitud?.length === 2) [latitud, longitud] = [[latitud[0]], [latitud[1]]];
    if (latitud === null || longitud === null) return null;
    if (latitud.length !== 1 || longitud.length !== 1) return null;
    const [lat, lon] = [latitud[0], longitud[0]];
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
    return [lat, lon];
  }

  if (typeof module !== 'undefined') {
    module.exports = { leerCoordenadas, puntoDeLosCampos };
  }
  if (typeof document === 'undefined') return;

  const DECIMALES = 6;
  const ZOOM_COMUNA = 12;
  const TESELAS = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  const ATRIBUCION = '© colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

  document.addEventListener('alpine:init', () => {
    /*
     * Mapa del domicilio. En la ficha (`editable: false`) solo muestra el marcador. En el
     * formulario, los campos con id `campoLatitud` y `campoLongitud` y el marcador se mantienen
     * iguales en los dos sentidos. Sin coordenadas, el mapa se centra en la comuna, sin marcador.
     * El mapa y el marcador viven en la clausura: no son estado reactivo de Alpine.
     */
    Alpine.data('mapaDomicilio', ({ punto, centro, zoom, editable = false, campoLatitud, campoLongitud }) => {
      let mapa = null;
      let marcador = null;

      return {
        sinMapa: false,

        init() {
          const latitud = editable ? document.getElementById(campoLatitud) : null;
          const longitud = editable ? document.getElementById(campoLongitud) : null;
          const inicial = editable ? puntoDeLosCampos(latitud.value, longitud.value) : punto;

          mapa = L.map(this.$refs.mapa, { scrollWheelZoom: false }).setView(inicial || centro, inicial ? zoom : ZOOM_COMUNA);
          mapa.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
          // OpenStreetMap bloquea las teselas que llegan sin Referer (responde con la imagen «Access
          // blocked»), y Django lo quita en todo el sitio con `Referrer-Policy: same-origin`. Aquí se
          // envía solo el origen, nunca la ruta (que lleva el id del paciente).
          const capa = L.tileLayer(TESELAS, {
            maxZoom: 19,
            attribution: ATRIBUCION,
            referrerPolicy: 'strict-origin-when-cross-origin',
          }).addTo(mapa);
          capa.once('tileerror', () => {
            this.sinMapa = true;
          });
          capa.on('tileload', () => {
            this.sinMapa = false;
          });

          const ubicar = (nuevo, centrar) => {
            if (!nuevo) return;
            if (marcador) {
              marcador.setLatLng(nuevo);
            } else {
              marcador = L.marker(nuevo, { draggable: editable, keyboard: editable, title: 'Domicilio' }).addTo(mapa);
              if (editable) marcador.on('dragend', () => escribir(marcador.getLatLng()));
            }
            if (centrar) mapa.setView(nuevo, Math.max(mapa.getZoom(), zoom));
          };

          const escribir = ({ lat, lng }) => {
            latitud.value = lat.toFixed(DECIMALES);
            longitud.value = lng.toFixed(DECIMALES);
          };

          ubicar(inicial, false);
          if (!editable) return;

          mapa.on('click', (evento) => {
            ubicar(evento.latlng, false);
            escribir(evento.latlng);
          });
          // Al escribir, pegar o usar el GPS, el marcador sigue a los campos. Si en la latitud se
          // pegaron las dos, se reparten en los dos campos.
          const seguirCampos = () => {
            const nuevo = puntoDeLosCampos(latitud.value, longitud.value);
            if (nuevo && leerCoordenadas(latitud.value)?.length === 2) {
              latitud.value = nuevo[0].toFixed(DECIMALES);
              longitud.value = nuevo[1].toFixed(DECIMALES);
            }
            ubicar(nuevo, true);
          };
          latitud.addEventListener('input', seguirCampos);
          longitud.addEventListener('input', seguirCampos);
        },
      };
    });

    /*
     * «Usar mi ubicación actual». Solo se ofrece en un contexto seguro (HTTPS o localhost), que es
     * donde el navegador permite el GPS. Llena los campos y avisa con un evento `input`, así el mapa
     * se mueve igual que si se hubieran escrito.
     */
    Alpine.data('ubicacionActual', ({ campoLatitud, campoLongitud }) => ({
      disponible: window.isSecureContext && 'geolocation' in navigator,
      buscando: false,
      mensaje: '',

      usar() {
        this.buscando = true;
        this.mensaje = 'Buscando su ubicación…';
        navigator.geolocation.getCurrentPosition(
          ({ coords }) => {
            const latitud = document.getElementById(campoLatitud);
            const longitud = document.getElementById(campoLongitud);
            latitud.value = coords.latitude.toFixed(DECIMALES);
            longitud.value = coords.longitude.toFixed(DECIMALES);
            latitud.dispatchEvent(new Event('input', { bubbles: true }));
            this.buscando = false;
            this.mensaje = `Ubicación tomada, con una precisión de unos ${Math.round(coords.accuracy)} m. Revísela en el mapa.`;
          },
          (error) => {
            this.buscando = false;
            this.mensaje = error.code === error.PERMISSION_DENIED
              ? 'No se dio permiso para usar la ubicación. Escriba las coordenadas o márquelas en el mapa.'
              : 'No se pudo leer la ubicación. Escriba las coordenadas o márquelas en el mapa.';
          },
          { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
        );
      },
    }));
  });
})();
