from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView

from cuentas.mixins import SondeoAutomatico, SoloQF
from turnos.forms import RutForm
from turnos.mixins import SoloAtencion
from turnos.models import Categoria, EstadoTurno, Ventanilla
from turnos.servicios import (
    ErrorDeAtencion,
    TipoResultado,
    abrir_ventanilla,
    cambiar_estado_ventanilla,
    crear_ventanilla,
    emitir_turno,
    finalizar_atencion,
    iniciar_atencion,
    llamar_siguiente,
    marcar_ausente,
    obtener_estado_sala,
    re_llamar,
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
    return render(
        request,
        "turnos/totem_resultado.html",
        _contexto_totem(resultado=resultado, rut=form.cleaned_data["rut"]),
    )


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
            messages.success(request, self.mensaje_exito.format(numero=turno.numero))
        return redirect("turnos:atencion")


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
