/*
 * Lo común a las páginas del personal: formularios que se envían una sola vez y confirmaciones en
 * un modal propio (templates/includes/confirmacion.html), no en el cuadro del navegador.
 *
 * Un formulario pide confirmación si declara data-confirmar-titulo. Los demás textos van en
 * data-confirmar-texto, -accion, -cancelar y -objeto; data-confirmar-peligro pinta la acción en
 * rojo y data-confirmar-turno muestra el objeto como un turno (sobre papel amarillo).
 *
 * Este archivo se carga ANTES de Alpine (bloque de scripts de base.html): los componentes se
 * registran cuando Alpine avisa con `alpine:init`.
 */
(() => {
  /*
   * Devuelve true si el envío puede seguir. Si el formulario pide confirmación y aún no la tiene,
   * detiene el envío y abre el modal; al aceptar, el modal lo vuelve a enviar ya confirmado.
   */
  function confirmarEnvio(evento) {
    const datos = evento.target.dataset;
    if (!datos.confirmarTitulo || datos.confirmado === 'si') {
      delete datos.confirmado;
      return true;
    }
    evento.preventDefault();
    window.dispatchEvent(
      new CustomEvent('confirmar', { detail: { formulario: evento.target, boton: evento.submitter } }),
    );
    return false;
  }

  window.confirmarEnvio = confirmarEnvio;

  document.addEventListener('alpine:init', () => {
    /* Formulario de una sola acción: se deshabilita al enviar, para evitar el doble clic. */
    Alpine.data('envio', () => ({
      enviando: false,

      enviar(evento) {
        if (confirmarEnvio(evento)) this.enviando = true;
      },
    }));

    /* El modal: muestra lo que declara el formulario y, si se acepta, lo vuelve a enviar. */
    Alpine.data('modalConfirmacion', () => ({
      titulo: '',
      texto: '',
      accion: '',
      cancelar: '',
      objeto: '',
      peligro: false,
      turno: false,
      formulario: null,
      boton: null,

      abrir({ formulario, boton }) {
        const datos = formulario.dataset;
        this.titulo = datos.confirmarTitulo;
        this.texto = datos.confirmarTexto || '';
        this.accion = datos.confirmarAccion || 'Confirmar';
        this.cancelar = datos.confirmarCancelar || 'Cancelar';
        this.objeto = datos.confirmarObjeto || '';
        this.peligro = 'confirmarPeligro' in datos;
        this.turno = 'confirmarTurno' in datos;
        this.formulario = formulario;
        this.boton = boton || null;

        if (!this.$refs.dialogo.open) this.$refs.dialogo.showModal();
        // Ante una acción que no se deshace, el foco parte en la opción segura.
        this.$nextTick(() => this.$refs.botonCancelar.focus());
      },

      aceptar() {
        const { formulario, boton } = this;
        this.$refs.dialogo.close();
        formulario.dataset.confirmado = 'si';
        formulario.requestSubmit(boton && boton.form === formulario ? boton : undefined);
      },

      cerrar() {
        if (this.$refs.dialogo.open) this.$refs.dialogo.close();
        if (this.boton) this.boton.focus();
      },
    }));
  });
})();
