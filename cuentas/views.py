from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, FormView, ListView, UpdateView

from cuentas.forms import (
    LoginRutForm,
    ResetearPasswordForm,
    UsuarioCrearForm,
    UsuarioEditarForm,
)
from cuentas.mixins import SoloQF
from cuentas.models import Rol, Usuario

# Orden y nombre de los grupos del listado de usuarios.
GRUPOS_DE_USUARIOS = [
    (Rol.QF, "Química Farmacéutica"),
    (Rol.FUNCIONARIO, "Funcionarios de farmacia"),
    (Rol.ENCARGADO_TERRENO, "Encargados de terreno"),
]


class EntrarView(LoginView):
    template_name = "cuentas/login.html"
    authentication_form = LoginRutForm
    redirect_authenticated_user = True


@login_required
def inicio(request):
    if request.user.es_qf:
        return redirect("cuentas:usuarios")
    if request.user.puede_atender:
        return redirect("turnos:atencion")
    return redirect("cuentas:panel_funcionario")


@login_required
def panel_funcionario(request):
    return render(request, "cuentas/panel_funcionario.html")


@login_required
def cambiar_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            usuario = form.save()
            usuario.debe_cambiar_password = False
            usuario.save(update_fields=["debe_cambiar_password"])
            update_session_auth_hash(request, usuario)
            messages.success(request, "Su contraseña fue actualizada.")
            return redirect("cuentas:inicio")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "cuentas/cambiar_password.html", {"form": form})


class UsuariosListaView(SoloQF, ListView):
    """Las cuentas activas agrupadas por rol y, al final, las desactivadas (siguen en el listado)."""

    model = Usuario
    template_name = "cuentas/usuarios_lista.html"
    context_object_name = "usuarios"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        usuarios = list(contexto["usuarios"])
        contexto["grupos"] = [
            {"nombre": nombre, "usuarios": [u for u in usuarios if u.is_active and u.rol == rol]}
            for rol, nombre in GRUPOS_DE_USUARIOS
        ]
        contexto["desactivadas"] = [u for u in usuarios if not u.is_active]
        return contexto


class UsuarioCrearView(SoloQF, CreateView):
    model = Usuario
    form_class = UsuarioCrearForm
    template_name = "cuentas/usuario_form.html"
    success_url = reverse_lazy("cuentas:usuarios")
    extra_context = {"titulo": "Nuevo funcionario"}

    def form_valid(self, form):
        resultado = super().form_valid(form)
        messages.success(self.request, f"Cuenta creada para {self.object.nombre_completo}.")
        return resultado


class UsuarioEditarView(SoloQF, UpdateView):
    model = Usuario
    form_class = UsuarioEditarForm
    template_name = "cuentas/usuario_form.html"
    success_url = reverse_lazy("cuentas:usuarios")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Editar a {self.object.nombre_completo}"
        return contexto

    def form_valid(self, form):
        resultado = super().form_valid(form)
        messages.success(self.request, f"Datos de {self.object.nombre_completo} actualizados.")
        return resultado


class UsuarioCambiarEstadoView(SoloQF, View):
    def post(self, request, pk):
        usuario = get_object_or_404(Usuario, pk=pk)
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=["is_active"])
        estado = "activada" if usuario.is_active else "desactivada"
        messages.success(request, f"La cuenta de {usuario.nombre_completo} fue {estado}.")
        return redirect("cuentas:usuarios")


class UsuarioResetearPasswordView(SoloQF, FormView):
    form_class = ResetearPasswordForm
    template_name = "cuentas/usuario_form.html"
    success_url = reverse_lazy("cuentas:usuarios")

    def get_usuario(self):
        return get_object_or_404(Usuario, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo"] = f"Restablecer contraseña de {self.get_usuario().nombre_completo}"
        return contexto

    def form_valid(self, form):
        usuario = self.get_usuario()
        usuario.set_password(form.cleaned_data["password"])
        usuario.debe_cambiar_password = True
        usuario.save(update_fields=["password", "debe_cambiar_password"])
        messages.success(self.request, f"Contraseña de {usuario.nombre_completo} restablecida.")
        return super().form_valid(form)
