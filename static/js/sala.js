/*
 * Pantalla pública de la sala de espera: el último llamado y los anteriores del día.
 *
 * Arriba, las funciones puras que deciden qué se anuncia: no tocan el DOM ni Alpine, y se prueban
 * en Node con `node --test "pruebas_js/*.test.js"`, que carga este mismo archivo. Abajo, el
 * componente Alpine, que solo se registra en el navegador.
 *
 * Este archivo se carga ANTES de Alpine (bloque "scripts" de base.html): el componente se
 * registra cuando Alpine avisa con `alpine:init`.
 */
(() => {
  /* Un llamado se identifica por turno, vez y hora: un re-llamado del mismo número es otro llamado. */
  function identificador(llamado) {
    return `${llamado.turno_id}:${llamado.veces_llamado}:${llamado.ultimo_llamado_en}`;
  }

  /*
   * Los llamados de `estado` que hay que anunciar, del más antiguo al más reciente: los que no
   * estaban entre los identificadores `previos` (los de la última instantánea recibida con éxito)
   * y que, según las dos horas del servidor, ocurrieron hace `vigencia` segundos o menos. Así,
   * tras un corte largo no hay una ráfaga de llamados viejos (siguen visibles en la lista), y el
   * resultado no depende del reloj del monitor.
   */
  function llamadosNuevos(previos, estado, vigencia) {
    const vistos = new Set(previos);
    const ahora = Date.parse(estado.servidor_en);
    return estado.recientes
      .filter((llamado) => !vistos.has(identificador(llamado)))
      .filter((llamado) => ahora - Date.parse(llamado.ultimo_llamado_en) <= vigencia * 1000)
      .reverse() // el servidor los entrega del más reciente al más antiguo
      .sort((a, b) => Date.parse(a.ultimo_llamado_en) - Date.parse(b.ultimo_llamado_en));
  }

  /* La frase del anuncio, sin ceros a la izquierda: ("P-012", 2) → "Turno P 12, ventanilla 2." */
  function textoDelAnuncio(numero, ventanilla) {
    const [letra, cifras] = numero.split('-');
    return `Turno ${letra} ${Number(cifras)}, ventanilla ${ventanilla}.`;
  }

  /*
   * La voz de los anuncios, en este orden: es-CL local, es-CL, otra es-* local, otra es-*; null si
   * no hay ninguna en español. Las locales van primero porque el CESFAM puede estar sin internet,
   * y ahí las voces en línea del navegador fallan.
   */
  function elegirVoz(voces) {
    const idioma = (voz) => voz.lang.replace('_', '-').toLowerCase();
    const esDeChile = (voz) => idioma(voz) === 'es-cl';
    const esEnEspanol = (voz) => idioma(voz) === 'es' || idioma(voz).startsWith('es-');
    const preferencias = [
      (voz) => esDeChile(voz) && voz.localService,
      esDeChile,
      (voz) => esEnEspanol(voz) && voz.localService,
      esEnEspanol,
    ];
    for (const prefiere of preferencias) {
      const voz = voces.find(prefiere);
      if (voz) return voz;
    }
    return null;
  }

  if (typeof module !== 'undefined') {
    module.exports = { identificador, llamadosNuevos, textoDelAnuncio, elegirVoz };
  }
  if (typeof document === 'undefined') return;

  document.addEventListener('alpine:init', () => {
    const ID_ESTADO_INICIAL = 'estado-sala'; // el json_script de turnos/sala.html
    const LARGO_HABITUAL = 5; // "P-012"; desde el turno 1000 del día el número se achica para caber
    const PLAZO_CONSULTA_MS = 5000; // una consulta que no responde en este plazo se aborta
    const NOTAS_CAMPANILLA = [659.25, 523.25]; // mi y do (Hz): "din-don"
    const SEPARACION_NOTAS_S = 0.45;
    const DURACION_NOTA_S = 0.9;
    const PAUSA_ENTRE_REPETICIONES_MS = 600;
    const PLAZO_LOCUCION_MS = 10000; // si el navegador no avisa el fin de una frase, la cola sigue igual
    const PLAZO_VOCES_MS = 3000; // la lista de voces puede llegar tarde, con `voiceschanged`
    const CLAVE_VOZ = 'sala:voz'; // en localStorage del monitor: "1" o "0"
    // Toque, clic o tecla, en los eventos que el navegador cuenta como interacción (en una pantalla
    // táctil es al soltar el dedo, no al apoyarlo).
    const EVENTOS_DE_INTERACCION = ['pointerup', 'touchend', 'keydown'];
    const HAY_WEB_AUDIO = 'AudioContext' in window;
    const HAY_SINTESIS_DE_VOZ = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

    const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

    /* La elección de voz del monitor. Sin almacenamiento (bloqueado o en modo privado) parte apagada. */
    function vozGuardada() {
      try {
        return localStorage.getItem(CLAVE_VOZ) === '1';
      } catch (error) {
        return false;
      }
    }

    function guardarVoz(activa) {
      try {
        localStorage.setItem(CLAVE_VOZ, activa ? '1' : '0');
      } catch (error) {
        // Sin almacenamiento, la elección dura hasta recargar la página.
      }
    }

    /* La campanilla: dos notas con OscillatorNode. Resuelve cuando la segunda se apagó. */
    function sonarCampanilla(audio) {
      const inicio = audio.currentTime + 0.05;
      NOTAS_CAMPANILLA.forEach((frecuencia, i) => {
        const t = inicio + i * SEPARACION_NOTAS_S;
        const oscilador = audio.createOscillator();
        const volumen = audio.createGain();
        oscilador.frequency.value = frecuencia;
        volumen.gain.setValueAtTime(0.0001, t);
        volumen.gain.exponentialRampToValueAtTime(0.4, t + 0.02);
        volumen.gain.exponentialRampToValueAtTime(0.0001, t + DURACION_NOTA_S);
        oscilador.connect(volumen).connect(audio.destination);
        oscilador.start(t);
        oscilador.stop(t + DURACION_NOTA_S);
      });
      const duracion = 0.05 + (NOTAS_CAMPANILLA.length - 1) * SEPARACION_NOTAS_S + DURACION_NOTA_S;
      return esperar(duracion * 1000);
    }

    /* Las voces del navegador. Al cargar la página la lista suele venir vacía y llega después. */
    function vocesDelNavegador() {
      const voces = speechSynthesis.getVoices();
      if (voces.length) return Promise.resolve(voces);
      return new Promise((resolver) => {
        const listas = () => resolver(speechSynthesis.getVoices());
        speechSynthesis.addEventListener('voiceschanged', listas, { once: true });
        setTimeout(listas, PLAZO_VOCES_MS);
      });
    }

    let locucionEnCurso = null; // Chrome puede perder los eventos de una locución que nadie referencia

    /* Dice `texto` con `voz`. Resuelve al terminar, con el código de error si lo hubo. */
    function decir(texto, voz) {
      return new Promise((resolver) => {
        const locucion = new SpeechSynthesisUtterance(texto);
        locucion.voice = voz;
        locucion.lang = voz.lang;
        let plazo = null;
        const terminar = (error) => {
          clearTimeout(plazo);
          locucionEnCurso = null;
          resolver(error);
        };
        plazo = setTimeout(terminar, PLAZO_LOCUCION_MS);
        locucion.onend = () => terminar();
        locucion.onerror = (evento) => terminar(evento.error);
        locucionEnCurso = locucion;
        speechSynthesis.speak(locucion);
      });
    }

    /*
     * Muestra los llamados del día y los mantiene al día consultando `url` cada `segundos`. La
     * siguiente consulta se programa al terminar la anterior, así nunca hay dos en curso. Sin
     * conexión conserva lo que hay en pantalla, lo avisa y espera cada vez el doble antes de
     * reintentar, hasta `reintentoMaximo` segundos.
     *
     * No envía la cabecera X-Actividad-Reciente: la sala no es actividad de nadie, y si el monitor
     * quedara con una sesión abierta, esta debe vencer igual.
     *
     * Cada llamado nuevo (ver `llamadosNuevos`, con `vigencia` en segundos) lleva "Nuevo llamado"
     * durante `resalte` segundos, y si es el último, su tarjeta pulsa. Con la voz activa, además
     * suena: campanilla y la frase dos veces, un anuncio tras otro.
     *
     * El monitor recuerda la voz, pero tras recargar los navegadores no dejan sonar hasta que
     * alguien toca la pantalla: mientras tanto se pide ese toque y solo hay aviso visual.
     */
    Alpine.data('salaEnVivo', ({ url, segundos, vigencia, reintentoMaximo, resalte }) => {
      let audio = null; // AudioContext: se crea al activar la voz, o al cargar si estaba activa
      const cola = []; // llamados por decir en voz, en orden
      let sonando = false;

      return {
        actual: null,
        anteriores: [],
        identificadores: [], // los de la última instantánea recibida con éxito
        resaltados: [], // identificadores que llevan "Nuevo llamado"
        pulsando: false,
        vozActiva: false,
        vozPorReactivar: false, // la voz está elegida, pero el navegador espera un toque para sonar
        hayVozEnEspanol: null, // null mientras el navegador no entrega su lista de voces
        actualizadoA: '',
        sinConexion: false,
        espera: segundos,

        init() {
          // La instantánea con que cargó la página es la línea base: lo que ya estaba no se anuncia.
          this.mostrar(JSON.parse(document.getElementById(ID_ESTADO_INICIAL).textContent));
          this.prepararSonido();
          this.programarConsulta();
        },

        /* Sin Web Audio y sin voz en español, el botón se reemplaza por un aviso. */
        get puedeSonar() {
          return HAY_WEB_AUDIO || this.hayVozEnEspanol !== false;
        },

        get pideToque() {
          return this.vozActiva && this.vozPorReactivar && this.puedeSonar;
        },

        get soloCampanilla() {
          return this.vozActiva && !this.vozPorReactivar && HAY_WEB_AUDIO && this.hayVozEnEspanol === false;
        },

        prepararSonido() {
          if (HAY_SINTESIS_DE_VOZ) {
            const revisarVoces = async () => {
              this.hayVozEnEspanol = elegirVoz(await vocesDelNavegador()) !== null;
            };
            revisarVoces();
            speechSynthesis.addEventListener('voiceschanged', revisarVoces);
          } else {
            this.hayVozEnEspanol = false;
          }

          // El primer toque, clic o tecla en cualquier parte reactiva la voz (antes que el clic del botón).
          const reactivar = () => {
            if (!this.vozPorReactivar) return;
            this.vozPorReactivar = false;
            if (audio) audio.resume();
          };
          EVENTOS_DE_INTERACCION.forEach((evento) => document.addEventListener(evento, reactivar, { capture: true }));

          if (!vozGuardada()) return;
          this.vozActiva = true;
          // Sin un gesto, el AudioContext solo queda en "running" si el navegador deja sonar sin
          // interacción (modo kiosco). Si queda suspendido y nadie ha tocado la página, se pide el toque.
          if (HAY_WEB_AUDIO) audio = new AudioContext();
          const audioLibre = audio !== null && audio.state === 'running';
          const huboInteraccion = Boolean(navigator.userActivation && navigator.userActivation.hasBeenActive);
          this.vozPorReactivar = !audioLibre && !huboInteraccion;
        },

        /* Una instantánea recibida del servidor: se dibuja y se anuncia lo que llegó desde la anterior. */
        recibir(estado) {
          const nuevos = llamadosNuevos(this.identificadores, estado, vigencia);
          this.mostrar(estado);
          nuevos.forEach((llamado) => this.anunciar(llamado, estado));
        },

        anunciar(llamado, estado) {
          const id = identificador(llamado);
          // Desde que el llamado se guardó hasta la respuesta que lo trajo, con horas del servidor.
          const latencia = (Date.parse(estado.servidor_en) - Date.parse(llamado.ultimo_llamado_en)) / 1000;
          console.debug(`Sala: ${llamado.numero} a la ventanilla ${llamado.ventanilla}, latencia ${latencia.toFixed(3)} s`);

          this.resaltados = [...this.resaltados, id];
          setTimeout(() => {
            this.resaltados = this.resaltados.filter((resaltado) => resaltado !== id);
          }, resalte * 1000);
          if (id === identificador(estado.actual)) this.pulsar();
          if (this.vozActiva && !this.vozPorReactivar && this.puedeSonar) {
            cola.push(llamado);
            this.sonarCola();
          }
        },

        /* "Activar voz" / "Desactivar voz". El clic es la interacción que el navegador exige para sonar. */
        alternarVoz() {
          if (this.vozActiva) {
            this.vozActiva = false;
            cola.length = 0;
            if (HAY_SINTESIS_DE_VOZ) speechSynthesis.cancel();
          } else {
            if (HAY_WEB_AUDIO) {
              audio = audio || new AudioContext();
              audio.resume();
            }
            this.vozActiva = true;
          }
          this.vozPorReactivar = false;
          guardarVoz(this.vozActiva);
        },

        /* Dice los anuncios pendientes de a uno: el siguiente espera a que termine el anterior. */
        async sonarCola() {
          if (sonando) return;
          sonando = true;
          while (cola.length && this.vozActiva && !this.vozPorReactivar) {
            try {
              await this.sonar(cola.shift());
            } catch (error) {
              console.warn('Sala: no se pudo reproducir un anuncio.', error);
            }
          }
          sonando = false;
        },

        /* Campanilla y la frase dos veces. Sin voz en español suena solo la campanilla. */
        async sonar(llamado) {
          if (audio) await sonarCampanilla(audio);
          const voz = HAY_SINTESIS_DE_VOZ ? elegirVoz(await vocesDelNavegador()) : null;
          if (!voz || !this.vozActiva) return;
          const texto = textoDelAnuncio(llamado.numero, llamado.ventanilla);
          if ((await decir(texto, voz)) === 'not-allowed') {
            // El navegador exige una interacción antes de hablar: se pide el toque y se descarta lo pendiente.
            this.vozPorReactivar = true;
            cola.length = 0;
            return;
          }
          await esperar(PAUSA_ENTRE_REPETICIONES_MS);
          if (this.vozActiva) await decir(texto, voz);
        },

        /* Reinicia el pulso aunque el anterior no haya terminado: sin la clase un momento, se vuelve a poner. */
        pulsar() {
          this.pulsando = false;
          this.$nextTick(() => {
            void document.body.offsetWidth; // fuerza el cálculo de estilos sin la clase
            this.pulsando = true;
          });
        },

        estaResaltado(llamado) {
          return this.resaltados.includes(identificador(llamado));
        },

        mostrar(estado) {
          // La hora local del servidor tal como viene ("2026-10-24T17:10:00.000-03:00" → "17:10"),
          // sin pasar por el reloj ni la zona horaria del monitor.
          this.actualizadoA = estado.servidor_en.slice(11, 16);
          const identificadores = estado.recientes.map(identificador);
          if (identificadores.join('|') === this.identificadores.join('|')) return;
          this.identificadores = identificadores;
          this.actual = estado.actual;
          this.anteriores = estado.recientes.slice(1);
        },

        programarConsulta() {
          setTimeout(() => this.consultar(), this.espera * 1000);
        },

        async consultar() {
          try {
            const estado = await this.pedirEstado();
            if (estado) {
              this.sinConexion = false;
              this.espera = segundos;
              this.recibir(estado);
            } else {
              // Se conserva lo que hay en pantalla y se reintenta cada vez más espaciado.
              this.sinConexion = true;
              this.espera = Math.min(this.espera * 2, reintentoMaximo);
            }
          } finally {
            this.programarConsulta();
          }
        },

        /* La instantánea de `url`, o null si no llegó: red caída, error del servidor, plazo vencido o JSON inválido. */
        async pedirEstado() {
          const controlador = new AbortController();
          const plazo = setTimeout(() => controlador.abort(), PLAZO_CONSULTA_MS);
          try {
            const respuesta = await fetch(url, { cache: 'no-store', signal: controlador.signal });
            if (!respuesta.ok) return null;
            const estado = await respuesta.json();
            const tieneForma = typeof estado.servidor_en === 'string' && Array.isArray(estado.recientes);
            return tieneForma ? estado : null;
          } catch (error) {
            return null;
          } finally {
            clearTimeout(plazo);
          }
        },

        esLargo(llamado) {
          return llamado.numero.length > LARGO_HABITUAL;
        },
      };
    });
  });
})();
