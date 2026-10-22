from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_vary_headers

CABECERA_ACTIVIDAD = "X-Actividad-Reciente"


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


class SesionPorActividad(SessionMiddleware):
    """SessionMiddleware que no renueva la sesión por las consultas automáticas de una pantalla.

    Con SESSION_SAVE_EVERY_REQUEST cada petición renueva la sesión. Si una pantalla consulta al
    servidor por su cuenta (el sondeo de la fila del panel), un panel olvidado en el computador
    compartido nunca vencería. Las vistas marcadas con `SondeoAutomatico` solo renuevan la sesión
    cuando el navegador informa, con la cabecera X-Actividad-Reciente, que hubo un clic, una tecla o
    un toque hace poco.
    """

    def process_response(self, request, response):
        if self._es_sondeo_sin_actividad(request):
            patch_vary_headers(response, ("Cookie",))
            return response
        return super().process_response(request, response)

    @staticmethod
    def _es_sondeo_sin_actividad(request):
        if not getattr(request, "sondeo_automatico", False):
            return False
        if request.headers.get(CABECERA_ACTIVIDAD) == "1":
            return False
        # Con la sesión vacía (venció) se deja el comportamiento normal: borra la cookie vieja.
        sesion = getattr(request, "session", None)
        return sesion is not None and not sesion.is_empty()
