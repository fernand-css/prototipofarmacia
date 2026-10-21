from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class SoloQF(LoginRequiredMixin):
    """Restringe la vista a la Química Farmacéutica. El resto recibe 403."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.es_qf:
            raise PermissionDenied("Solo la Química Farmacéutica puede administrar cuentas.")
        return super().dispatch(request, *args, **kwargs)
