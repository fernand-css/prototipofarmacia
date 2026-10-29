from django import forms

from reparto.models import Sector
from reparto.servicios import ErrorDeDomicilio, leer_coordenadas


class BusquedaDomiciliosForm(forms.Form):
    """Búsqueda en la lista de domicilios: un RUT en cualquier formato o parte del apellido."""

    busqueda = forms.CharField(
        label="RUT o apellido",
        max_length=100,
        error_messages={"required": "Escriba un RUT o un apellido."},
    )


class DomicilioForm(forms.Form):
    """Datos del domicilio. Las coordenadas se escriben con punto o coma decimal, o se pegan las dos
    («-36.50, -72.21») en la latitud. Las reglas (dirección, rango, verificado) están en el servicio."""

    sector = forms.ChoiceField(label="Sector", choices=[("", "Sin sector")] + Sector.choices, required=False)
    direccion = forms.CharField(
        label="Dirección",
        max_length=200,
        error_messages={"required": "Escriba la dirección."},
    )
    referencias = forms.CharField(
        label="Referencias",
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Cómo reconocer la casa: color, portón, quién vive al lado, cómo se llega.",
    )
    latitud = forms.CharField(
        label="Latitud",
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
        help_text="Por ejemplo -36.499912. También puede pegar aquí las dos: «-36.50, -72.21».",
    )
    longitud = forms.CharField(
        label="Longitud",
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
    )

    @classmethod
    def desde(cls, domicilio):
        """El formulario con los datos actuales del domicilio, si existe."""
        if domicilio is None:
            return cls()
        return cls(initial={
            "sector": domicilio.sector,
            "direccion": domicilio.direccion,
            "referencias": domicilio.referencias,
            "latitud": "" if domicilio.latitud is None else str(domicilio.latitud),
            "longitud": "" if domicilio.longitud is None else str(domicilio.longitud),
        })

    def clean(self):
        datos = super().clean()
        try:
            latitud = leer_coordenadas(datos.get("latitud"))
        except ErrorDeDomicilio as error:
            self.add_error("latitud", str(error))
            return datos
        if len(latitud) == 2:  # pegó «lat, lon» en la latitud: mandan sobre la longitud
            latitud, longitud = latitud[:1], latitud[1:]
        else:
            try:
                longitud = leer_coordenadas(datos.get("longitud"))
            except ErrorDeDomicilio as error:
                self.add_error("longitud", str(error))
                return datos
        if len(longitud) > 1:
            self.add_error("longitud", "Escriba solo la longitud.")
        else:
            datos["latitud"] = latitud[0] if latitud else None
            datos["longitud"] = longitud[0] if longitud else None
        return datos


class FotoForm(forms.Form):
    """La foto se valida y se procesa en el servicio (formato, peso, píxeles y metadatos)."""

    foto = forms.FileField(
        label="Foto del domicilio o de su entorno",
        error_messages={"required": "Elija una foto.", "empty": "La foto está vacía."},
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png", "capture": "environment"}),
    )


class MarcarPendienteForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo",
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Por ejemplo: «El paciente se cambió de casa».",
        error_messages={"required": "Escriba por qué el domicilio debe volver a verificarse."},
    )
