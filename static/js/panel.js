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
   * Fila de espera en vivo: cada `segundos` pide el fragmento HTML a `url` y reemplaza el
   * contenido del elemento `contenido`. Si la sesión venció, la petición termina redirigida al
   * login: en ese caso se recarga la página en vez de pegar el login dentro del panel.
   *
   * El sondeo avisa al servidor cuando hubo actividad real del usuario (clic, tecla, toque o
   * movimiento) en los últimos `ventanaActividad` segundos: solo entonces la sesión se renueva.
   * Así un panel olvidado deja vencer la sesión aunque siga consultando la fila.
   */
  Alpine.data('filaEnVivo', ({ url, segundos, ventanaActividad }) => {
    let ultimaActividad = Date.now();

    return {
      init() {
        const registrar = () => {
          ultimaActividad = Date.now();
        };
        EVENTOS_DE_ACTIVIDAD.forEach((evento) => document.addEventListener(evento, registrar, { passive: true }));
        setInterval(() => this.actualizar(), segundos * 1000);
      },

      hayActividadReciente() {
        return Date.now() - ultimaActividad <= ventanaActividad * 1000;
      },

      async actualizar() {
        const cabeceras = this.hayActividadReciente() ? { 'X-Actividad-Reciente': '1' } : {};
        try {
          const respuesta = await fetch(url, { credentials: 'same-origin', headers: cabeceras });
          if (respuesta.redirected) {
            window.location.reload();
            return;
          }
          if (respuesta.ok) {
            this.$refs.contenido.innerHTML = await respuesta.text();
          }
        } catch (error) {
          // Sin red: se conserva lo que ya está en pantalla.
        }
      },
    };
  });
});
