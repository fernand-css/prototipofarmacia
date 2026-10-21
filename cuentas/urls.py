from django.contrib.auth.views import LogoutView
from django.urls import path

from cuentas import views

app_name = "cuentas"

urlpatterns = [
    path("", views.EntrarView.as_view(), name="entrar"),
    path("salir/", LogoutView.as_view(), name="salir"),
    path("inicio/", views.inicio, name="inicio"),
    path("panel/", views.panel_funcionario, name="panel_funcionario"),
    path("cambiar-password/", views.cambiar_password, name="cambiar_password"),
    path("usuarios/", views.UsuariosListaView.as_view(), name="usuarios"),
    path("usuarios/nuevo/", views.UsuarioCrearView.as_view(), name="usuario_crear"),
    path("usuarios/<int:pk>/editar/", views.UsuarioEditarView.as_view(), name="usuario_editar"),
    path("usuarios/<int:pk>/estado/", views.UsuarioCambiarEstadoView.as_view(), name="usuario_cambiar_estado"),
    path("usuarios/<int:pk>/clave/", views.UsuarioResetearPasswordView.as_view(), name="usuario_resetear_password"),
]
