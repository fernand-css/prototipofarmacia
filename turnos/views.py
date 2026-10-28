from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from django.views.generic import ListView

from cuentas.mixins import SondeoAutomatico, SoloQF
from turnos.estimacion import estimar_espera, texto_de_espera
from turnos.forms import BusquedaPreparadosForm, CargaPadronForm, RutForm
from turnos.importacion import (
    ErrorDeArchivo,
    ErrorDeCarga,
    cancelar_carga,
    confirmar_carga,
    csv_de_plantilla,
    csv_de_rechazos,
    descartar_cargas_vencidas,
    preparar_carga,
)
from turnos.mixins import SoloAtencion
from turnos.models import (
    CargaPadron,
    Categoria,
    EstadoCarga,
    EstadoPreparacion,
    EstadoTurno,
    Paciente,
    Preparacion,
    Ventanilla,
)
from turnos.servicios import (
    ErrorDeAtencion,
    TipoResultado,
    abrir_ventanilla,
    cambiar_estado_ventanilla,
    crear_ventanilla,
    emitir_turno,
    entregar_pendiente,
    finalizar_atencion,
    iniciar_atencion,
    llamar_siguiente,
    marcar_ausente,
    marcar_lista,
    obtener_estado_sala,
    preparaciones_del_dia,
    preparados_pendientes,
    re_llamar,
    registrar_no_retiro,
    resumen_cola,
    segundos_para_ausente,
    terminar_turno_de_ventanilla,
    turno_en_curso,
)

# --- Tótem (público, sin login) -----------------------------------------------------------------


def _contexto_totem(**extra):
    return {
        "segundos_inactividad": settings.TURNOS_SEGUNDOS_INACTIVIDAD_TOTEM,
        "segundos_resultado": settings.TURNOS_SEGUNDOS_RESULTADO_TOTEM,
        **extra,
    }


@require_GET
def totem(request):
    return render(request, "turnos/totem.html", _contexto_totem())


@require_POST
def totem_turno(request):
    form = RutForm(request.POST)
    if not form.is_valid():
        error = form.errors["rut"][0]
        return render(request, "turnos/totem.html", _contexto_totem(error=error))

    resultado = emitir_turno(
        form.cleaned_data["rut"],
        insistir_domicilio=request.POST.get("insistir") == "1",
    )
    contexto = _contexto_totem(resultado=resultado, rut=form.cleaned_data["rut"])
    if resultado.tipo in (TipoResultado.EMITIDO, TipoResultado.VIGENTE):
        # Una foto del momento (HU-18): volver a digitar el RUT con el turno vigente la recalcula.
        contexto["espera"] = texto_de_espera(estimar_espera(resultado.turno))
        contexto["espera_calculada"] = timezone.now()
    return render(request, "turnos/totem_resultado.html", contexto)


# --- Sala de espera (pública, sin login) --------------------------------------------------------


@never_cache
@require_GET
def sala(request):
    """Pantalla del televisor de la sala. Trae los llamados incrustados: se ve completa al cargar."""
    return render(
        request,
        "turnos/sala.html",
        {
            "estado": obtener_estado_sala(),
            "segundos_refresco": settings.TURNOS_SEGUNDOS_REFRESCO_SALA,
            "segundos_vigencia": settings.TURNOS_SEGUNDOS_VIGENCIA_ANUNCIO,
            "segundos_reintento_maximo": settings.TURNOS_SEGUNDOS_REINTENTO_MAXIMO_SALA,
            "segundos_resalte": settings.TURNOS_SEGUNDOS_RESALTE_SALA,
        },
    )


@method_decorator(never_cache, name="dispatch")
class SalaEstadoView(SondeoAutomatico, View):
    """Los llamados del día en JSON; la pantalla de la sala lo pide cada pocos segundos."""

    def get(self, request):
        return JsonResponse(obtener_estado_sala())


# --- Ventanillas (solo la QF) -------------------------------------------------------------------


class VentanillasListaView(SoloQF, ListView):
    template_name = "turnos/ventanillas_lista.html"
    context_object_name = "ventanillas"

    def get_queryset(self):
        return Ventanilla.objects.select_related("funcionario")


class VentanillaCrearView(SoloQF, View):
    def post(self, request):
        ventanilla = crear_ventanilla()
        messages.success(request, f"Se creó la ventanilla {ventanilla.numero}.")
        return redirect("turnos:ventanillas")


class VentanillaCambiarEstadoView(SoloQF, View):
    def post(self, request, pk):
        try:
            ventanilla = cambiar_estado_ventanilla(pk)
        except Ventanilla.DoesNotExist:
            raise Http404("La ventanilla no existe.")
        except ErrorDeAtencion as error:
            messages.warning(request, str(error))
        else:
            estado = "habilitada" if ventanilla.habilitada else "deshabilitada"
            messages.success(request, f"La ventanilla {ventanilla.numero} fue {estado}.")
        return redirect("turnos:ventanillas")


# --- Padrón y recetas de Rayén (solo la QF) -----------------------------------------------------

CARGAS_EN_BITACORA = 50  # cuántas cargas lista /padron/, de la más reciente a la más antigua
RECHAZOS_EN_PANTALLA = 100  # el resto se ve en el CSV descargable
MUESTRA_DE_FILAS = 5  # filas que la vista previa muestra para revisar nombres y tildes


def _csv_descargable(contenido, nombre):
    respuesta = HttpResponse(contenido, content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


class PadronView(SoloQF, View):
    template_name = "turnos/padron.html"

    def get(self, request):
        return self.mostrar(request, CargaPadronForm())

    def post(self, request):
        formulario = CargaPadronForm(request.POST, request.FILES)
        if formulario.is_valid():
            try:
                carga = preparar_carga(formulario.cleaned_data["archivo"], request.user)
            except ErrorDeArchivo as error:
                formulario.add_error("archivo", str(error))
            else:
                return redirect("turnos:padron_carga", pk=carga.pk)
        return self.mostrar(request, formulario)

    def mostrar(self, request, formulario):
        descartar_cargas_vencidas()
        cargas = CargaPadron.objects.select_related("usuario")[:CARGAS_EN_BITACORA]
        return render(request, self.template_name, {
            "formulario": formulario,
            "cargas": cargas,
            "cargas_en_bitacora": CARGAS_EN_BITACORA,
        })


class PadronPlantillaView(SoloQF, View):
    def get(self, request):
        return _csv_descargable(csv_de_plantilla(), "plantilla-padron.csv")


class PadronCargaView(SoloQF, View):
    def get(self, request, pk):
        descartar_cargas_vencidas()
        carga = get_object_or_404(CargaPadron.objects.select_related("usuario"), pk=pk)
        pendiente = carga.estado == EstadoCarga.PENDIENTE
        return render(request, "turnos/padron_carga.html", {
            "carga": carga,
            "pendiente": pendiente,
            "vence_en": carga.creada_en + timedelta(minutes=settings.TURNOS_PADRON_MINUTOS_PENDIENTE),
            "muestra": (carga.filas_validas or [])[:MUESTRA_DE_FILAS] if pendiente else [],
            "rechazos": carga.rechazos[:RECHAZOS_EN_PANTALLA],
            "rechazos_ocultos": max(0, len(carga.rechazos) - RECHAZOS_EN_PANTALLA),
        })


class PadronConfirmarView(SoloQF, View):
    def post(self, request, pk):
        carga = get_object_or_404(CargaPadron, pk=pk)
        try:
            carga = confirmar_carga(carga, request.user)
        except ErrorDeCarga as error:
            messages.warning(request, str(error))
        else:
            messages.success(
                request,
                f"Carga aplicada: {carga.pacientes_creados} pacientes y {carga.recetas_creadas} recetas "
                f"nuevos, {carga.pacientes_actualizados} pacientes y {carga.recetas_actualizadas} "
                "recetas actualizados.",
            )
        return redirect("turnos:padron_carga", pk=pk)


class PadronCancelarView(SoloQF, View):
    def post(self, request, pk):
        carga = get_object_or_404(CargaPadron, pk=pk)
        try:
            cancelar_carga(carga)
        except ErrorDeCarga as error:
            messages.warning(request, str(error))
        else:
            messages.success(request, "Carga cancelada: no se guardó ningún paciente ni receta.")
        return redirect("turnos:padron")


class PadronRechazosView(SoloQF, View):
    def get(self, request, pk):
        carga = get_object_or_404(CargaPadron, pk=pk)
        return _csv_descargable(csv_de_rechazos(carga), f"rechazos-carga-{carga.pk}.csv")


# --- Consulta de recetas (funcionario y QF) ----------------------------------------------------


class RecetasView(SoloAtencion, View):
    """Recetas crónicas de un RUT con su avance (HU-21). La búsqueda va por POST: así el RUT no
    queda en la URL, ni en el historial del equipo compartido del mesón."""

    template_name = "turnos/recetas.html"

    def get(self, request):
        return render(request, self.template_name, {"formulario": RutForm()})

    def post(self, request):
        formulario = RutForm(request.POST)
        contexto = {"formulario": formulario}
        if formulario.is_valid():
            paciente = Paciente.objects.filter(rut=formulario.cleaned_data["rut"]).first()
            contexto["buscado"] = True
            contexto["paciente"] = paciente
            contexto["recetas"] = paciente.recetas.order_by("-fecha_emision") if paciente else []
        return render(request, self.template_name, contexto)


# --- Panel de atención (funcionario y QF) -------------------------------------------------------


class AtencionView(SoloAtencion, View):
    """Panel del funcionario: sin ventanilla elige una, con ventanilla ve su puesto."""

    def get(self, request):
        ventanilla = Ventanilla.objects.filter(funcionario=request.user).first()
        if ventanilla is None:
            libres = Ventanilla.objects.filter(habilitada=True, funcionario__isnull=True)
            return render(request, "turnos/atencion.html", {"ventanilla": None, "libres": libres})

        turno = turno_en_curso(request.user)
        contexto = {
            "ventanilla": ventanilla,
            "turno": turno,
            "segundos_refresco": settings.TURNOS_SEGUNDOS_REFRESCO_PANEL,
            "segundos_actividad": settings.TURNOS_SEGUNDOS_ACTIVIDAD_RECIENTE,
            **resumen_cola(),
        }
        if turno and turno.estado == EstadoTurno.LLAMADO:
            contexto["segundos_para_ausente"] = segundos_para_ausente(turno)
        if turno and turno.estado == EstadoTurno.EN_ATENCION:
            contexto["preparacion"] = Preparacion.objects.filter(turno=turno).first()
        return render(request, "turnos/atencion.html", contexto)


class AbrirVentanillaView(SoloAtencion, View):
    def post(self, request):
        try:
            ventanilla_id = int(request.POST.get("ventanilla", ""))
        except ValueError:
            messages.error(request, "Elija una ventanilla.")
            return redirect("turnos:atencion")

        try:
            ventanilla = abrir_ventanilla(request.user, ventanilla_id)
        except ErrorDeAtencion as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Abrió la ventanilla {ventanilla.numero}.")
        return redirect("turnos:atencion")


class TerminarTurnoView(SoloAtencion, View):
    def post(self, request):
        try:
            ventanilla = terminar_turno_de_ventanilla(request.user)
        except ErrorDeAtencion as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Terminó su turno en la ventanilla {ventanilla.numero}.")
        return redirect("turnos:atencion")


class AccionDeAtencionView(SoloAtencion, View):
    """Acción del panel sobre el turno del funcionario: éxito con el número, o aviso del error."""

    accion = None  # staticmethod(servicio): recibe el usuario y devuelve el turno
    mensaje_exito = ""  # admite {numero}

    def post(self, request):
        try:
            turno = self.accion(request.user)
        except ErrorDeAtencion as error:
            messages.warning(request, str(error))
        else:
            messages.success(request, self.mensaje(turno))
        return redirect("turnos:atencion")

    def mensaje(self, turno):
        return self.mensaje_exito.format(numero=turno.numero)


class LlamarSiguienteView(AccionDeAtencionView):
    accion = staticmethod(llamar_siguiente)
    mensaje_exito = "Llamó al turno {numero}."


class ReLlamarView(AccionDeAtencionView):
    accion = staticmethod(re_llamar)
    mensaje_exito = "Re-llamó al turno {numero}."


class IniciarAtencionView(AccionDeAtencionView):
    accion = staticmethod(iniciar_atencion)
    mensaje_exito = "Inició la atención del turno {numero}."


class FinalizarAtencionView(AccionDeAtencionView):
    accion = staticmethod(finalizar_atencion)
    mensaje_exito = "Finalizó la atención del turno {numero}."


class MarcarAusenteView(AccionDeAtencionView):
    accion = staticmethod(marcar_ausente)
    mensaje_exito = "Marcó como ausente al turno {numero}."


class RegistrarNoRetiroView(AccionDeAtencionView):
    accion = staticmethod(registrar_no_retiro)

    def mensaje(self, turno):
        preparacion = Preparacion.objects.filter(turno=turno).first()
        if preparacion and preparacion.estado == EstadoPreparacion.PENDIENTE_RETIRO:
            return f"El turno {turno.numero} quedó ausente y su preparado, pendiente de retiro."
        return f"El turno {turno.numero} quedó ausente y su preparación se anuló."


class EmitirUrgenciaView(SoloAtencion, View):
    """El funcionario emite un turno U-nnn digitando el RUT; anula el turno en espera de ese RUT."""

    def post(self, request):
        form = RutForm(request.POST)
        if not form.is_valid():
            messages.error(request, form.errors["rut"][0])
            return redirect("turnos:atencion")

        resultado = emitir_turno(form.cleaned_data["rut"], desde_panel=True)
        if resultado.tipo == TipoResultado.EMITIDO:
            texto = f"Se emitió el turno de urgencia {resultado.turno.numero}."
            if resultado.anulado:
                texto += f" Se anuló el turno {resultado.anulado.numero} de este RUT."
            messages.success(request, texto)
        elif resultado.turno.categoria == Categoria.URGENCIA:
            messages.warning(request, f"Este RUT ya tiene la urgencia {resultado.turno.numero} en espera.")
        else:
            messages.warning(
                request,
                f"El turno {resultado.turno.numero} de este RUT está "
                f"{resultado.turno.get_estado_display().lower()}: no se emite urgencia.",
            )
        return redirect("turnos:atencion")


@method_decorator(never_cache, name="dispatch")
class ColaView(SondeoAutomatico, SoloAtencion, View):
    """Fragmento HTML con la fila de espera; el panel lo pide cada pocos segundos."""

    def get(self, request):
        return render(request, "turnos/_cola.html", resumen_cola())


@method_decorator(never_cache, name="dispatch")
class AtencionPreparacionView(SondeoAutomatico, SoloAtencion, View):
    """Fragmento HTML con el estado de la preparación del turno en atención; el panel lo pide
    cada pocos segundos hasta que la preparación está lista. Solo trae el estado: los botones
    quedan fijos en el panel, así el modal de «No retiró» nunca pierde su formulario."""

    def get(self, request):
        turno = turno_en_curso(request.user)
        preparacion = None
        if turno and turno.estado == EstadoTurno.EN_ATENCION:
            preparacion = Preparacion.objects.filter(turno=turno).first()
        return render(request, "turnos/_preparacion_turno.html", {"preparacion": preparacion})


# --- Preparación (funcionario y QF) ------------------------------------------------------------


class PreparacionView(SoloAtencion, View):
    """Pantalla de quien prepara: las recetas recibidas en las ventanillas y las ya listas."""

    def get(self, request):
        return render(request, "turnos/preparacion.html", {
            "segundos_refresco": settings.TURNOS_SEGUNDOS_REFRESCO_PANEL,
            "segundos_actividad": settings.TURNOS_SEGUNDOS_ACTIVIDAD_RECIENTE,
            **preparaciones_del_dia(),
        })


@method_decorator(never_cache, name="dispatch")
class PreparacionFilaView(SondeoAutomatico, SoloAtencion, View):
    """Fragmento HTML de la pantalla de preparación; se pide cada pocos segundos."""

    def get(self, request):
        return render(request, "turnos/_preparacion_fila.html", preparaciones_del_dia())


class PreparacionListaView(SoloAtencion, View):
    def post(self, request, pk):
        try:
            preparacion = marcar_lista(pk, request.user)
        except ErrorDeAtencion as error:
            messages.warning(request, str(error))
        else:
            messages.success(request, f"La preparación del turno {preparacion.turno.numero} quedó lista.")
        return redirect("turnos:preparacion")


class PreparadosView(SoloAtencion, View):
    """Preparados pendientes de retiro (HU-17). La búsqueda va por POST, como en /recetas/: el RUT
    no queda en la URL ni en el historial del equipo compartido."""

    template_name = "turnos/preparados.html"

    def get(self, request):
        return render(request, self.template_name, {
            "formulario": BusquedaPreparadosForm(),
            "pendientes": preparados_pendientes(),
        })

    def post(self, request):
        formulario = BusquedaPreparadosForm(request.POST)
        contexto = {"formulario": formulario}
        if formulario.is_valid():
            contexto["buscado"] = True
            contexto["pendientes"] = preparados_pendientes(formulario.cleaned_data["busqueda"])
        else:
            contexto["pendientes"] = preparados_pendientes()
        return render(request, self.template_name, contexto)


class PreparadoEntregarView(SoloAtencion, View):
    def post(self, request, pk):
        try:
            preparacion = entregar_pendiente(pk, request.user)
        except ErrorDeAtencion as error:
            messages.warning(request, str(error))
        else:
            messages.success(request, f"Se entregó el preparado del turno {preparacion.turno.numero}.")
        return redirect("turnos:preparados")
