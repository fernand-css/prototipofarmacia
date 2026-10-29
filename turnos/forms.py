from django import forms

from cuentas.validators import normalizar_rut, validar_rut
from turnos.models import Paciente


class PacienteAdminForm(forms.ModelForm):
    """Acepta el RUT en cualquier formato (con puntos y guion) y lo guarda normalizado."""

    rut = forms.CharField(label="RUT", max_length=15)

    class Meta:
        model = Paciente
        fields = "__all__"

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])
        validar_rut(rut)
        return rut


class CargaPadronForm(forms.Form):
    """Archivo del padrón exportado de Rayén. Su contenido lo valida `turnos.importacion`."""

    archivo = forms.FileField(
        label="Archivo del padrón",
        help_text="Archivo .csv o .xlsx de hasta 5 MB y 5.000 filas, con los encabezados de la plantilla.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
    )


class RutForm(forms.Form):
    """RUT digitado en el tótem o en el panel: se acepta en cualquier formato y se entrega normalizado."""

    rut = forms.CharField(label="RUT", max_length=15)

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])
        validar_rut(rut)
        return rut
