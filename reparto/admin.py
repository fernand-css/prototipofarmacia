from django.contrib import admin

from reparto.models import CambioDomicilio, Domicilio, FotoDomicilio


class SoloLectura(admin.ModelAdmin):
    """Acceso técnico de consulta: los domicilios se registran desde /domicilios/, con su historial."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Domicilio)
class DomicilioAdmin(SoloLectura):
    list_display = ("paciente", "sector", "direccion", "estado", "actualizado_en")
    list_filter = ("estado", "sector")
    list_select_related = ("paciente",)
    search_fields = ("paciente__rut", "paciente__apellidos", "direccion")


@admin.register(FotoDomicilio)
class FotoDomicilioAdmin(SoloLectura):
    list_display = ("domicilio", "ancho", "alto", "subida_en", "subida_por")
    list_select_related = ("domicilio__paciente", "subida_por")


@admin.register(CambioDomicilio)
class CambioDomicilioAdmin(SoloLectura):
    list_display = ("domicilio", "accion", "usuario", "en")
    list_filter = ("accion",)
    list_select_related = ("domicilio__paciente", "usuario")
    date_hierarchy = "en"
