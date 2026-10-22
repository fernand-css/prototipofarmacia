/*
 * Componentes Alpine del tótem de turnos.
 *
 * Este archivo se carga ANTES de Alpine (bloque "scripts" de base.html): los componentes se
 * registran cuando Alpine avisa con `alpine:init`.
 */
document.addEventListener('alpine:init', () => {
  const LARGO_MAXIMO = 9; // cuerpo de hasta 8 dígitos + dígito verificador
  const LARGO_MINIMO = 8; // cuerpo de 7 dígitos + dígito verificador
  const LARGO_MINIMO_PARA_K = 7; // la K solo puede ser el dígito verificador

  /*
   * Teclado numérico para digitar el RUT. Solo habilita las teclas que tienen sentido y se
   * vacía tras un rato sin tocarlo, para que el RUT de un paciente no quede a la vista del
   * siguiente. Lo que se envía es el texto crudo; el servidor lo normaliza y lo valida.
   */
  Alpine.data('teclado', ({ inactividad }) => ({
    rut: '',
    temporizador: null,

    init() {
      this.reiniciarReloj();
    },

    get tieneK() {
      return this.rut.includes('K');
    },
    get puedeDigito() {
      return this.rut.length < LARGO_MAXIMO && !this.tieneK;
    },
    get puedeK() {
      return this.puedeDigito && this.rut.length >= LARGO_MINIMO_PARA_K;
    },
    get completo() {
      return this.rut.length >= LARGO_MINIMO;
    },
    get formateado() {
      if (this.rut.length < 2) return this.rut;
      const cuerpo = this.rut.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
      return `${cuerpo}-${this.rut.slice(-1)}`;
    },
    get ayuda() {
      if (!this.rut) return 'Puede escribirlo sin puntos ni guion.';
      if (!this.completo) return 'Siga escribiendo hasta completar su RUT, con el dígito verificador.';
      return 'Si está correcto, presione Confirmar.';
    },

    agregar(tecla) {
      const permitida = tecla === 'K' ? this.puedeK : this.puedeDigito;
      if (!permitida) return;
      this.rut += tecla;
      this.reiniciarReloj();
    },
    borrar() {
      this.rut = this.rut.slice(0, -1);
      this.reiniciarReloj();
    },
    reiniciarReloj() {
      clearTimeout(this.temporizador);
      this.temporizador = setTimeout(() => {
        this.rut = '';
      }, inactividad * 1000);
    },
  }));

  /* Cuenta regresiva de las pantallas de resultado: al llegar a cero vuelve al inicio. */
  Alpine.data('reinicio', ({ segundos, destino }) => ({
    restante: segundos,

    init() {
      const reloj = setInterval(() => {
        this.restante -= 1;
        if (this.restante <= 0) {
          clearInterval(reloj);
          window.location.href = destino;
        }
      }, 1000);
    },
  }));
});
