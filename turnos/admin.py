from django.contrib import admin

from turnos.forms import PacienteAdminForm
from turnos.models import CargaPadron, Paciente, RecetaCronica, Turno, Ventanilla


class RecetaCronicaInline(admin.TabularInline):
    model = RecetaCronica
    extra = 0


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    form = PacienteAdminForm
    list_display = ("rut", "apellidos", "nombres", "fecha_nacimiento", "es_postrado")
    search_fields = ("rut", "nombres", "apellidos")
    inlines = [RecetaCronicaInline]


@admin.register(RecetaCronica)
class RecetaCronicaAdmin(admin.ModelAdmin):
    list_display = (
        "folio", "paciente", "fecha_emision", "vigencia_meses", "entregas_realizadas", "entregas_maximas"
    )
    list_select_related = ("paciente",)
    search_fields = ("folio", "paciente__rut", "paciente__apellidos")


@admin.register(Ventanilla)
class VentanillaAdmin(admin.ModelAdmin):
    list_display = ("numero", "habilitada", "funcionario")


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ("numero", "fecha", "estado", "rut", "ventanilla", "emitido_en")
    list_filter = ("fecha", "estado", "categoria")
    search_fields = ("rut",)
    date_hierarchy = "fecha"


@admin.register(CargaPadron)
class CargaPadronAdmin(admin.ModelAdmin):
    """Bitácora de importaciones: solo lectura, la carga se hace desde /padron/."""

    list_display = (
        "creada_en", "usuario", "nombre_archivo", "estado", "filas_totales", "filas_rechazadas"
    )
    list_filter = ("estado",)
    list_select_related = ("usuario",)
    date_hierarchy = "creada_en"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
