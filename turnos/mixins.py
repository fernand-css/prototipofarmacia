from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class SoloAtencion(LoginRequiredMixin):
    """Restringe la vista a quienes atienden en ventanilla: funcionario y QF. El resto recibe 403."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.puede_atender:
            raise PermissionDenied("Solo el funcionario y la Química Farmacéutica atienden en ventanilla.")
        return super().dispatch(request, *args, **kwargs)
