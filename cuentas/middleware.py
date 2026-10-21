from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class CambioPasswordObligatorio:
    """Retiene al usuario en el cambio de contraseña mientras no haya elegido una propia."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user
        if usuario.is_authenticated and usuario.debe_cambiar_password:
            permitidas = {reverse("cuentas:cambiar_password"), reverse("cuentas:salir")}
            if request.path not in permitidas and not request.path.startswith(settings.STATIC_URL):
                return redirect("cuentas:cambiar_password")
        return self.get_response(request)
