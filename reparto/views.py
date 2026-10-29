from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from reparto.forms import BusquedaDomiciliosForm, DomicilioForm, FotoForm, MarcarPendienteForm
from reparto.mixins import ConsultaDomicilios, SoloTerreno
from reparto.models import Domicilio, EstadoDomicilio, FotoDomicilio, Sector
from reparto.servicios import (
    ESTADOS_DE_LISTA,
    ErrorDeDomicilio,
    agregar_foto,
    borrar_foto,
    guardar_domicilio,
    marcar_pendiente,
    pacientes_de_despacho,
    resumen_de_verificacion,
    verificar,
)
from turnos.models import Paciente


def _por_sector(pacientes):
    """La lista agrupada como se reparte: por sector, y al final los que no tienen sector (entre
    ellos, los sin dirección). Cada grupo cuenta sus verificados sobre sus domicilios registrados."""
    grupos = []
    for valor, nombre in [*Sector.choices, ("", "")]:
        del_grupo = [p for p in pacientes if (p.domicilio.sector if hasattr(p, "domicilio") else "") == valor]
        if not del_grupo:
            continue
        registrados = [p for p in del_grupo if hasattr(p, "domicilio")]
        grupos.append({
            "titulo": f"Sector {nombre}" if valor else "Sin sector",
            "pacientes": del_grupo,
            "registrados": len(registrados),
            "verificados": sum(p.domicilio.estado == EstadoDomicilio.VERIFICADO for p in registrados),
            "sin_direccion": len(del_grupo) - len(registrados),
        })
    return grupos


def _puntos(pacientes):
    """Los domicilios con coordenadas de la lista, para los marcadores del mapa (va con json_script)."""
    return [
        {
            "id": p.pk,
            "latitud": float(p.domicilio.latitud),
            "longitud": float(p.domicilio.longitud),
            "estado": p.domicilio.estado,
            "direccion": p.domicilio.direccion,
            "url": reverse("reparto:ficha", args=[p.pk]),
        }
        for p in pacientes
        if hasattr(p, "domicilio") and p.domicilio.tiene_coordenadas
    ]


class DomiciliosView(ConsultaDomicilios, View):
    """Lista de los pacientes con despacho a domicilio y el estado de su domicilio (HU-12, IG04).

    Los filtros de sector y estado van en la URL (no tienen datos personales); la búsqueda por
    RUT o apellido va por POST, como en /recetas/, para que el RUT no quede en el historial.
    """

    template_name = "reparto/domicilios.html"

    def filtros(self, request):
        sector = request.GET.get("sector", "")
        estado = request.GET.get("estado", "")
        return {
            "sector": sector if sector in Sector.values else "",
            "estado": estado if estado in dict(ESTADOS_DE_LISTA) else "",
        }

    @staticmethod
    def opciones(filtros, clave, valores):
        """Enlaces de un filtro («Todos» y cada valor), conservando el otro filtro activo."""
        base = reverse("reparto:domicilios")
        opciones = []
        for valor, etiqueta in [("", "Todos"), *valores]:
            parametros = {k: v for k, v in {**filtros, clave: valor}.items() if v}
            url = f"{base}?{urlencode(parametros)}" if parametros else base
            opciones.append({"etiqueta": etiqueta, "url": url, "activo": filtros[clave] == valor})
        return opciones

    def contexto(self, request, formulario, busqueda=None):
        filtros = self.filtros(request)
        pacientes = pacientes_de_despacho(busqueda=busqueda, **filtros)
        return {
            "formulario": formulario,
            "buscado": busqueda is not None,
            "filtrado": any(filtros.values()),
            "total": len(pacientes),
            "grupos": _por_sector(pacientes),
            "puntos": _puntos(pacientes),
            **_mapa(),
            "resumen": resumen_de_verificacion(),
            "opciones_sector": self.opciones(filtros, "sector", Sector.choices),
            "opciones_estado": self.opciones(filtros, "estado", ESTADOS_DE_LISTA),
        }

    def get(self, request):
        return render(request, self.template_name, self.contexto(request, BusquedaDomiciliosForm()))

    def post(self, request):
        formulario = BusquedaDomiciliosForm(request.POST)
        busqueda = formulario.cleaned_data["busqueda"] if formulario.is_valid() else None
        return render(request, self.template_name, self.contexto(request, formulario, busqueda))


def _mapa():
    """Centro de la comuna y acercamiento para el mapa del domicilio (Leaflet y OpenStreetMap)."""
    return {"centro_mapa": settings.REPARTO_CENTRO_MAPA, "zoom_mapa": settings.REPARTO_ZOOM_MAPA}


def _paciente(paciente_id):
    """El paciente de una ficha: con despacho a domicilio, o con un domicilio que se conserva aunque
    ya no lo tenga. Cualquier otro da 404."""
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    if not paciente.es_despacho_domicilio and not Domicilio.objects.filter(paciente=paciente).exists():
        raise Http404("Este paciente no tiene despacho a domicilio.")
    return paciente


class FichaView(ConsultaDomicilios, View):
    """Ficha del domicilio: datos, fotos e historial. Solo el Encargado de Terreno ve las acciones."""

    def get(self, request, paciente_id):
        paciente = _paciente(paciente_id)
        domicilio = (
            Domicilio.objects.select_related("verificado_por", "actualizado_por").filter(paciente=paciente).first()
        )
        contexto = {
            "paciente": paciente,
            "domicilio": domicilio,
            "puede_editar": request.user.es_encargado_terreno,
            "fotos": list(domicilio.fotos.select_related("subida_por")) if domicilio else [],
            "cambios": domicilio.cambios.select_related("usuario") if domicilio else [],
            "fotos_maximas": settings.REPARTO_FOTOS_MAXIMAS,
            "form_foto": FotoForm(),
            "form_pendiente": MarcarPendienteForm(),
            **_mapa(),
        }
        return render(request, "reparto/ficha.html", contexto)


class EditarView(SoloTerreno, View):
    template_name = "reparto/editar.html"

    def get(self, request, paciente_id):
        paciente = _paciente(paciente_id)
        domicilio = Domicilio.objects.filter(paciente=paciente).first()
        contexto = {
            "paciente": paciente,
            "domicilio": domicilio,
            "formulario": DomicilioForm.desde(domicilio),
            **_mapa(),
        }
        return render(request, self.template_name, contexto)

    def post(self, request, paciente_id):
        paciente = _paciente(paciente_id)
        formulario = DomicilioForm(request.POST)
        if formulario.is_valid():
            try:
                guardar_domicilio(paciente, formulario.cleaned_data, request.user)
            except ErrorDeDomicilio as error:
                formulario.add_error(None, str(error))
            else:
                messages.success(request, "Se guardó el domicilio.")
                return redirect("reparto:ficha", paciente_id=paciente.pk)
        domicilio = Domicilio.objects.filter(paciente=paciente).first()
        contexto = {"paciente": paciente, "domicilio": domicilio, "formulario": formulario, **_mapa()}
        return render(request, self.template_name, contexto)


class AccionDeDomicilioView(SoloTerreno, View):
    """Acción del Encargado sobre un domicilio: éxito con un aviso, o el error tal cual."""

    mensaje_exito = ""

    def accion(self, request, paciente):
        raise NotImplementedError

    def post(self, request, paciente_id):
        paciente = _paciente(paciente_id)
        try:
            self.accion(request, paciente)
        except ErrorDeDomicilio as error:
            messages.warning(request, str(error))
        else:
            messages.success(request, self.mensaje_exito)
        return redirect("reparto:ficha", paciente_id=paciente.pk)


class VerificarView(AccionDeDomicilioView):
    mensaje_exito = "El domicilio quedó verificado."

    def accion(self, request, paciente):
        verificar(paciente, request.user)


class MarcarPendienteView(AccionDeDomicilioView):
    mensaje_exito = "El domicilio quedó pendiente de verificar."

    def accion(self, request, paciente):
        marcar_pendiente(paciente, request.POST.get("motivo", ""), request.user)


class SubirFotoView(AccionDeDomicilioView):
    mensaje_exito = "Se agregó la foto."

    def accion(self, request, paciente):
        formulario = FotoForm(request.POST, request.FILES)
        if not formulario.is_valid():
            raise ErrorDeDomicilio(formulario.errors["foto"][0])
        agregar_foto(paciente, formulario.cleaned_data["foto"], request.user)


class BorrarFotoView(SoloTerreno, View):
    def post(self, request, pk):
        foto = get_object_or_404(FotoDomicilio.objects.select_related("domicilio"), pk=pk)
        try:
            borrar_foto(foto.pk, request.user)
        except ErrorDeDomicilio as error:
            messages.warning(request, str(error))
        else:
            messages.success(request, "Se borró la foto.")
        return redirect("reparto:ficha", paciente_id=foto.domicilio.paciente_id)


class FotoView(ConsultaDomicilios, View):
    """Entrega una foto de domicilio. `MEDIA_ROOT` no se sirve por ninguna URL pública: la fachada
    de la casa de un paciente es un dato sensible y solo la ven el Encargado de Terreno y la QF."""

    def get(self, request, pk):
        foto = FotoDomicilio.objects.filter(pk=pk).first()
        if foto is None or not foto.archivo.storage.exists(foto.archivo.name):
            raise Http404("La foto no existe.")
        respuesta = FileResponse(foto.archivo.open("rb"), content_type="image/jpeg")
        respuesta["Cache-Control"] = "private"
        return respuesta
