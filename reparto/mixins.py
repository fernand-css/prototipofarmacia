from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class SoloTerreno(LoginRequiredMixin):
    """Restringe la vista al Encargado de Terreno: solo él registra, edita y verifica domicilios."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.es_encargado_terreno:
            raise PermissionDenied("Solo el Encargado de Terreno registra y verifica domicilios.")
        return super().dispatch(request, *args, **kwargs)


class ConsultaDomicilios(LoginRequiredMixin):
    """Consulta de domicilios: Encargado de Terreno y QF. El resto recibe 403."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.puede_consultar_domicilios:
            raise PermissionDenied("Solo el Encargado de Terreno y la Química Farmacéutica ven los domicilios.")
        return super().dispatch(request, *args, **kwargs)
