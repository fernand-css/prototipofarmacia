from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from cuentas.models import Usuario
from cuentas.validators import normalizar_rut, validar_rut


class LoginRutForm(AuthenticationForm):
    """Autenticación por RUT. Acepta el RUT con o sin puntos y lo normaliza antes de buscarlo."""

    username = forms.CharField(
        label="RUT",
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "12.345.678-5"}),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"placeholder": "Su contraseña"}),
    )

    error_messages = {
        "invalid_login": "El RUT o la contraseña no son correctos.",
        "inactive": "Esta cuenta está desactivada. Solicite su reactivación a la Química Farmacéutica.",
    }

    def clean_username(self):
        return normalizar_rut(self.cleaned_data["username"])


class UsuarioCrearForm(forms.ModelForm):
    rut = forms.CharField(
        label="RUT",
        max_length=13,
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "12.345.678-5"}),
    )
    password = forms.CharField(
        label="Contraseña inicial",
        widget=forms.PasswordInput,
        help_text="Entréguesela al funcionario. El sistema le exigirá cambiarla en su primer ingreso.",
    )

    class Meta:
        model = Usuario
        fields = ["rut", "nombres", "apellidos", "rol"]

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])
        validar_rut(rut)
        return rut

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data["password"])
        usuario.debe_cambiar_password = True
        if commit:
            usuario.save()
        return usuario


class UsuarioEditarForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["nombres", "apellidos", "rol"]


class ResetearPasswordForm(forms.Form):
    password = forms.CharField(
        label="Contraseña nueva",
        widget=forms.PasswordInput,
        help_text="Entréguesela al funcionario. Deberá cambiarla en su próximo ingreso.",
    )

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password
