/*
 * Domicilios de los pacientes con despacho a domicilio: el mapa a pantalla completa de la lista,
 * la ficha y el formulario, y la ubicación del GPS.
 *
 * Arriba, las funciones puras: cómo se leen las coordenadas escritas o pegadas (la misma regla que
 * `reparto.servicios.leer_coordenadas` en el servidor, que es quien valida) y la distancia en línea
 * recta. No tocan el DOM ni Alpine, y se prueban en Node con `node --test "pruebas_js/*.test.js"`,
 * que carga este mismo archivo. Abajo, los componentes Alpine, que solo se registran en el navegador.
 *
 * El mapa es una ayuda: lo que se guarda son siempre los campos de latitud y longitud. El mapa los
 * llena al tocarlo o al arrastrar el marcador, y se mueve cuando se escriben. Si las teselas de
 * OpenStreetMap no cargan (sin señal o sin internet), avisa y el formulario sigue funcionando.
 *
 * Movimiento: al abrir una página, la cámara vuela desde donde quedó en la página anterior (se
 * guarda en sessionStorage) hasta lo que hay que mirar, y recién ahí caen los marcadores. Es el
 * único movimiento que no responde a un toque; con `prefers-reduced-motion`, el mapa aparece ya en
 * su lugar y los marcadores no caen.
 *
 * Este archivo se carga ANTES de Alpine (bloque "scripts" de base.html), después de Leaflet.
 */
(() => {
  const NUMERO = /-?\d+(?:[.,]\d+)?/g;
  const SEPARADORES = /[\s,;]*/g;
  const RADIO_TIERRA = 6371000;

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

  /* Distancia en línea recta entre dos puntos [lat, lon], en metros (fórmula del semiverseno). */
  function distanciaEnMetros([lat1, lon1], [lat2, lon2]) {
    const rad = (grados) => (grados * Math.PI) / 180;
    const a = Math.sin(rad(lat2 - lat1) / 2) ** 2
      + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
    return 2 * RADIO_TIERRA * Math.asin(Math.sqrt(a));
  }

  /* «40 m», «350 m», «1,2 km» o «12 km»: redondeada a lo que sirve para orientarse en terreno. */
  function textoDistancia(metros) {
    const redondos = Math.max(10, Math.round(metros / 10) * 10);
    if (redondos < 1000) return `${redondos} m`;
    if (metros < 10000) return `${(Math.round(metros / 100) / 10).toString().replace('.', ',')} km`;
    return `${Math.round(metros / 1000)} km`;
  }

  if (typeof module !== 'undefined') {
    module.exports = { leerCoordenadas, puntoDeLosCampos, distanciaEnMetros, textoDistancia };
  }
  if (typeof document === 'undefined') return;

  const DECIMALES = 6;
  const ZOOM_COMUNA = 13;
  const SEGUNDOS_DE_VUELO = 1.1;
  const TESELAS = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  const ATRIBUCION = '© colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
  const CLAVE_VISTA = 'reparto:vista';
  const GPS = { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 };
  const CASA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 11 12 5l7.5 6v8.5h-5v-5h-5v5h-5z"/></svg>';
  const VISTO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5.5 12.5 4 4 9-9"/></svg>';

  const quieto = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hayGps = () => window.isSecureContext && 'geolocation' in navigator;

  /* Dónde quedó la cámara en la página anterior de domicilios, para volar desde ahí. */
  function vistaGuardada() {
    try {
      const vista = JSON.parse(sessionStorage.getItem(CLAVE_VISTA));
      if (Number.isFinite(vista?.lat) && Number.isFinite(vista?.lon) && Number.isFinite(vista?.zoom)) {
        return { centro: [vista.lat, vista.lon], zoom: vista.zoom };
      }
    } catch {
      // Sin sessionStorage (ventana privada, datos bloqueados): se parte desde la comuna.
    }
    return null;
  }

  function guardarVista(mapa) {
    try {
      const { lat, lng } = mapa.getCenter();
      sessionStorage.setItem(CLAVE_VISTA, JSON.stringify({ lat, lon: lng, zoom: mapa.getZoom() }));
    } catch {
      // Igual que arriba: guardar la vista es una comodidad.
    }
  }

  /* El mapa de la página, sin los controles de Leaflet: los botones van en la plantilla. */
  function crearMapa(componente, { centro, zoom }) {
    const mapa = L.map(componente.$refs.mapa, { zoomControl: false }).setView(centro, zoom);
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
      componente.sinMapa = true;
    });
    capa.on('tileload', () => {
      componente.sinMapa = false;
    });
    mapa.on('moveend', () => guardarVista(mapa));
    return mapa;
  }

  /*
   * Lleva la cámara a unos límites, sin dejarlos bajo la hoja: en pantalla ancha la hoja flota
   * sobre el lado izquierdo del mapa. `alLlegar` corre cuando la cámara se detiene.
   */
  function volarA(mapa, limites, { maxZoom, hoja }, alLlegar = () => {}) {
    const flota = hoja && getComputedStyle(hoja).position === 'absolute';
    const izquierda = flota ? hoja.offsetLeft + hoja.offsetWidth : 0;
    const opciones = { paddingTopLeft: [izquierda + 40, 56], paddingBottomRight: [88, 40], maxZoom };
    if (quieto()) {
      mapa.fitBounds(limites, { ...opciones, animate: false });
      alLlegar();
      return;
    }
    let llego = false;
    const llegar = () => {
      if (llego) return;
      llego = true;
      alLlegar();
    };
    mapa.once('moveend', llegar);
    setTimeout(llegar, SEGUNDOS_DE_VUELO * 1000 + 600); // por si Leaflet no anima (ya estaba ahí)
    mapa.flyToBounds(limites, { ...opciones, duration: SEGUNDOS_DE_VUELO });
  }

  const limitesDe = (...puntos) => L.latLngBounds(puntos);

  /*
   * El marcador de un domicilio: una gota con la casa. Pendiente va blanca y punteada (como su
   * insignia) y verificado, llena. En la ficha lleva al lado la placa con la dirección: dice adónde,
   * como la placa de ventanilla de la sala. La dirección entra como texto, nunca como HTML.
   */
  function icono({ estado = 'pendiente', placa = '', chico = false, llega = false, retraso = 0 }) {
    const pin = document.createElement('div');
    pin.className = `pin pin--${estado}${chico ? ' pin--chico' : ''}${llega ? ' pin--llega' : ''}`;
    if (retraso) pin.style.animationDelay = `${retraso}ms`;
    pin.innerHTML = `<span class="pin__onda"></span><span class="pin__sombra"></span>`
      + `<span class="pin__gota">${chico && estado === 'verificado' ? VISTO : CASA}</span>`;
    if (placa) {
      const texto = document.createElement('span');
      texto.className = 'pin__placa';
      texto.textContent = placa;
      pin.append(texto);
    }
    const [ancho, alto] = chico ? [28, 34] : [40, 48];
    return L.divIcon({ className: 'pin-icono', html: pin, iconSize: [ancho, alto], iconAnchor: [ancho / 2, alto], tooltipAnchor: [0, -alto] });
  }

  /* Un salto corto del marcador cuando se mueve: muestra que tomó el punto nuevo. */
  function saltar(marcador) {
    const pin = marcador.getElement()?.querySelector('.pin');
    if (!pin || quieto()) return;
    pin.classList.remove('pin--llega', 'pin--salta');
    void pin.offsetWidth; // reinicia la animación
    pin.classList.add('pin--salta');
  }

  /*
   * «Mostrar mi ubicación»: el punto de quien mira el mapa, con el círculo de la precisión del GPS.
   * Solo se ofrece en un contexto seguro (HTTPS o localhost), donde el navegador permite el GPS.
   */
  function ubicador(componente, obtenerMapa, alUbicar) {
    let punto = null;
    let precision = null;
    return () => {
      componente.ubicando = true;
      componente.mensaje = '';
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          componente.ubicando = false;
          const mapa = obtenerMapa();
          const aqui = [coords.latitude, coords.longitude];
          if (punto) {
            punto.setLatLng(aqui);
            precision.setLatLng(aqui).setRadius(coords.accuracy);
          } else {
            precision = L.circle(aqui, { radius: coords.accuracy, interactive: false, className: 'yo__precision' }).addTo(mapa);
            punto = L.marker(aqui, {
              icon: L.divIcon({ className: 'pin-icono', html: '<span class="yo"></span>', iconSize: [22, 22], iconAnchor: [11, 11] }),
              keyboard: false,
              interactive: false,
              zIndexOffset: -100,
            }).addTo(mapa);
          }
          alUbicar(aqui);
        },
        (error) => {
          componente.ubicando = false;
          componente.mensaje = error.code === error.PERMISSION_DENIED
            ? 'No se dio permiso para usar la ubicación.'
            : 'No se pudo leer la ubicación. Intente de nuevo al aire libre.';
        },
        GPS,
      );
    };
  }

  document.addEventListener('alpine:init', () => {
    /*
     * Mapa de la ficha y del formulario. En la ficha (`editable: false`) muestra el marcador con la
     * placa de la dirección, que se toma de `data-placa`. En el formulario, los campos con id
     * `campoLatitud` y `campoLongitud` y el marcador se mantienen iguales en los dos sentidos. Sin
     * coordenadas, el mapa se centra en la comuna, sin marcador. El mapa y el marcador viven en la
     * clausura: no son estado reactivo de Alpine.
     */
    Alpine.data('mapaDomicilio', ({ punto, centro, zoom, estado = 'pendiente', editable = false, campoLatitud, campoLongitud }) => {
      let mapa = null;
      let marcador = null;

      return {
        sinMapa: false,
        mensaje: '',
        distancia: '',
        ubicando: false,
        // En el formulario, el GPS llena los campos con «Usar mi ubicación actual».
        puedeUbicarme: !editable && hayGps(),

        init() {
          const hoja = this.$refs.hoja;
          const latitud = editable ? document.getElementById(campoLatitud) : null;
          const longitud = editable ? document.getElementById(campoLongitud) : null;
          const inicial = editable ? puntoDeLosCampos(latitud.value, longitud.value) : punto;
          const placa = editable ? '' : this.$el.dataset.placa ?? '';

          mapa = crearMapa(this, vistaGuardada() ?? { centro, zoom: ZOOM_COMUNA });

          const ubicar = (nuevo, { llega = false } = {}) => {
            if (marcador) {
              marcador.setLatLng(nuevo);
              saltar(marcador);
              return;
            }
            marcador = L.marker(nuevo, {
              icon: icono({ estado: editable ? 'editando' : estado, placa, llega: llega && !quieto() }),
              draggable: editable,
              keyboard: editable,
              title: 'Domicilio',
            }).addTo(mapa);
            if (editable) marcador.on('dragend', () => escribir(marcador.getLatLng()));
          };

          const escribir = ({ lat, lng }) => {
            latitud.value = lat.toFixed(DECIMALES);
            longitud.value = lng.toFixed(DECIMALES);
          };

          if (inicial) {
            volarA(mapa, limitesDe(inicial, inicial), { maxZoom: zoom, hoja }, () => ubicar(inicial, { llega: true }));
          } else {
            volarA(mapa, limitesDe(centro, centro), { maxZoom: ZOOM_COMUNA, hoja });
          }

          this.ubicarme = ubicador(this, () => mapa, (aqui) => {
            if (!punto) {
              volarA(mapa, limitesDe(aqui, aqui), { maxZoom: zoom - 1, hoja });
              return;
            }
            volarA(mapa, limitesDe(aqui, punto), { maxZoom: zoom, hoja });
            this.distancia = `Usted está a ${textoDistancia(distanciaEnMetros(aqui, punto))} en línea recta.`;
          });

          if (!editable) return;

          mapa.on('click', (evento) => {
            ubicar(evento.latlng, { llega: true });
            escribir(evento.latlng);
          });
          // Al escribir, pegar o usar el GPS, el marcador sigue a los campos (después de una pausa,
          // para no volar con cada tecla). Si en la latitud se pegaron las dos, se reparten.
          let espera = null;
          const seguirCampos = () => {
            clearTimeout(espera);
            espera = setTimeout(() => {
              const nuevo = puntoDeLosCampos(latitud.value, longitud.value);
              if (!nuevo) return;
              if (leerCoordenadas(latitud.value)?.length === 2) {
                latitud.value = nuevo[0].toFixed(DECIMALES);
                longitud.value = nuevo[1].toFixed(DECIMALES);
              }
              ubicar(nuevo, { llega: true });
              volarA(mapa, limitesDe(nuevo, nuevo), { maxZoom: Math.max(mapa.getZoom(), zoom), hoja });
            }, 400);
          };
          latitud.addEventListener('input', seguirCampos);
          longitud.addEventListener('input', seguirCampos);
        },

        ubicarme() {},
        acercar() { mapa?.zoomIn(); },
        alejar() { mapa?.zoomOut(); },
      };
    });

    /*
     * Mapa de la lista: un marcador por domicilio con coordenadas (los datos llegan con
     * json_script, en el elemento con id `puntos`). Al pasar por una fila de la hoja, o al llegar a
     * ella con el teclado, su marcador se destaca y muestra la dirección; tocar un marcador abre la
     * ficha. La lista sigue siendo el camino principal: los marcadores no reciben el foco.
     */
    Alpine.data('mapaDomicilios', ({ puntos: idPuntos, centro, zoom }) => {
      let mapa = null;
      const marcadores = new Map();

      return {
        sinMapa: false,
        mensaje: '',
        distancia: '',
        ubicando: false,
        puedeUbicarme: hayGps(),

        init() {
          const hoja = this.$refs.hoja;
          const puntos = JSON.parse(document.getElementById(idPuntos).textContent);
          mapa = crearMapa(this, vistaGuardada() ?? { centro, zoom: ZOOM_COMUNA });

          const poner = () => puntos.forEach((p, i) => {
            const marcador = L.marker([p.latitud, p.longitud], {
              icon: icono({ estado: p.estado, chico: true, llega: !quieto(), retraso: Math.min(i * 30, 450) }),
              keyboard: false,
              title: '',
            });
            const etiqueta = document.createElement('span');
            etiqueta.textContent = p.direccion;
            marcador.bindTooltip(etiqueta, { direction: 'top', className: 'pin-etiqueta' });
            marcador.on('click', () => window.location.assign(p.url));
            marcador.addTo(mapa);
            marcadores.set(String(p.id), marcador);
          });

          if (puntos.length) {
            const limites = limitesDe(...puntos.map((p) => [p.latitud, p.longitud]));
            volarA(mapa, limites, { maxZoom: zoom - 1, hoja }, poner);
          } else {
            volarA(mapa, limitesDe(centro, centro), { maxZoom: ZOOM_COMUNA, hoja });
          }

          // La fila y su marcador: uno destacado a la vez, y a la vista si quedó fuera del mapa.
          let activa = null;
          const destacar = (fila) => {
            if (fila === activa) return;
            for (const [id, encendido] of [[activa?.dataset.paciente, false], [fila?.dataset.paciente, true]]) {
              const marcador = marcadores.get(id);
              if (!marcador) continue;
              marcador.getElement()?.querySelector('.pin')?.classList.toggle('pin--activo', encendido);
              marcador.setZIndexOffset(encendido ? 1000 : 0);
              if (encendido) {
                marcador.openTooltip();
                const flota = getComputedStyle(hoja).position === 'absolute';
                mapa.panInside(marcador.getLatLng(), { paddingTopLeft: [flota ? hoja.offsetLeft + hoja.offsetWidth + 40 : 40, 60] });
              } else {
                marcador.closeTooltip();
              }
            }
            activa = fila;
          };
          hoja.addEventListener('pointerover', (evento) => destacar(evento.target.closest('[data-paciente]')));
          hoja.addEventListener('pointerleave', () => destacar(null));
          hoja.addEventListener('focusin', (evento) => destacar(evento.target.closest('[data-paciente]')));

          this.ubicarme = ubicador(this, () => mapa, (aqui) => {
            volarA(mapa, limitesDe(aqui, aqui), { maxZoom: zoom - 1, hoja });
          });
        },

        ubicarme() {},
        acercar() { mapa?.zoomIn(); },
        alejar() { mapa?.zoomOut(); },
      };
    });

    /*
     * «Usar mi ubicación actual» del formulario. Solo se ofrece en un contexto seguro. Llena los
     * campos y avisa con un evento `input`, así el mapa se mueve igual que si se hubieran escrito.
     */
    Alpine.data('ubicacionActual', ({ campoLatitud, campoLongitud }) => ({
      disponible: hayGps(),
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
          GPS,
        );
      },
    }));

    /* Copiar las coordenadas para pegarlas en otra aplicación. El portapapeles exige HTTPS. */
    Alpine.data('copiarTexto', (texto) => ({
      disponible: window.isSecureContext && Boolean(navigator.clipboard),
      copiado: false,

      async copiar() {
        try {
          await navigator.clipboard.writeText(texto);
          this.copiado = true;
          setTimeout(() => {
            this.copiado = false;
          }, 2000);
        } catch {
          // Sin permiso para el portapapeles: las coordenadas siguen a la vista para copiarlas a mano.
        }
      },
    }));
  });
})();
