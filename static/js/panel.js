/*
 * Componentes Alpine del panel de atención.
 *
 * Este archivo se carga ANTES de Alpine (bloque "scripts" de base.html): los componentes se
 * registran cuando Alpine avisa con `alpine:init`.
 */
document.addEventListener('alpine:init', () => {
  const EVENTOS_DE_ACTIVIDAD = ['pointerdown', 'pointermove', 'keydown', 'touchstart', 'wheel'];

  /*
   * Botones de un turno recién llamado. "Ausente" se habilita al terminar la cuenta regresiva;
   * el servidor valida el mismo plazo, esto solo evita un clic que sería rechazado. La
   * confirmación de "Ausente" la declara su formulario (ver static/js/comun.js).
   */
  Alpine.data('turnoLlamado', ({ faltan }) => ({
    faltan,
    enviando: false,

    init() {
      if (this.faltan <= 0) return;
      const reloj = setInterval(() => {
        this.faltan -= 1;
        if (this.faltan <= 0) clearInterval(reloj);
      }, 1000);
    },

    enviar(evento) {
      if (window.confirmarEnvio(evento)) this.enviando = true;
    },
  }));

  /*
   * Registra la actividad real del usuario (clic, tecla, toque o movimiento) y devuelve una
   * función que arma las cabeceras del sondeo: solo con actividad en los últimos
   * `ventanaActividad` segundos avisa al servidor, y solo entonces la sesión se renueva. Así un
   * panel olvidado deja vencer la sesión aunque siga consultando.
   */
  function rastrearActividad(ventanaActividad) {
    let ultimaActividad = Date.now();
    const registrar = () => {
      ultimaActividad = Date.now();
    };
    EVENTOS_DE_ACTIVIDAD.forEach((evento) => document.addEventListener(evento, registrar, { passive: true }));
    return () => (Date.now() - ultimaActividad <= ventanaActividad * 1000 ? { 'X-Actividad-Reciente': '1' } : {});
  }

  /*
   * Pide un fragmento HTML. Devuelve su texto, o null si no se pudo. Si la sesión venció, la
   * petición termina redirigida al login: en ese caso se recarga la página en vez de pegar el
   * login dentro del panel.
   */
  async function pedirFragmento(url, cabeceras) {
    const respuesta = await fetch(url, { credentials: 'same-origin', headers: cabeceras });
    if (respuesta.redirected) {
      window.location.reload();
      return null;
    }
    return respuesta.ok ? respuesta.text() : null;
  }

  /*
   * Fila de espera en vivo (y pantalla de preparación): cada `segundos` pide el fragmento HTML a
   * `url` y reemplaza el contenido del elemento `contenido`.
   */
  Alpine.data('filaEnVivo', ({ url, segundos, ventanaActividad }) => ({
    init() {
      const cabeceras = rastrearActividad(ventanaActividad);
      setInterval(async () => {
        try {
          const html = await pedirFragmento(url, cabeceras());
          if (html !== null) this.$refs.contenido.innerHTML = html;
        } catch (error) {
          // Sin red: se conserva lo que ya está en pantalla.
        }
      }, segundos * 1000);
    },
  }));

  /*
   * Estado de la preparación del turno en atención. Reemplaza solo el fragmento del estado: los
   * botones quedan fijos, así un modal abierto nunca pierde su formulario. Al leer
   * data-estado="lista" habilita «Finalizar atención», cambia el texto de confirmación de
   * «No retiró» por el de data-confirmar-texto-lista y deja de preguntar: ya no cambia sola.
   * Cualquier otro estado (el turno se cerró en otra pestaña) recarga el panel.
   */
  Alpine.data('preparacionEnVivo', ({ url, segundos, ventanaActividad, lista }) => {
    let reloj = null;

    return {
      lista,

      init() {
        if (this.lista) return;
        const cabeceras = rastrearActividad(ventanaActividad);
        reloj = setInterval(() => this.actualizar(cabeceras()), segundos * 1000);
      },

      async actualizar(cabeceras) {
        let html;
        try {
          html = await pedirFragmento(url, cabeceras);
        } catch (error) {
          return; // Sin red: se conserva lo que ya está en pantalla.
        }
        if (html === null || this.lista) return;
        this.$refs.contenido.innerHTML = html;
        const estado = this.$refs.contenido.firstElementChild?.dataset.estado;
        if (estado === 'en_preparacion') return;
        clearInterval(reloj);
        if (estado !== 'lista') {
          window.location.reload();
          return;
        }
        this.lista = true;
        this.$root.querySelectorAll('[data-confirmar-texto-lista]').forEach((formulario) => {
          formulario.dataset.confirmarTexto = formulario.dataset.confirmarTextoLista;
        });
      },
    };
  });
});
