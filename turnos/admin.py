from django.contrib import admin

from turnos.forms import PacienteAdminForm
from turnos.models import (
    LETRA_CATEGORIA,
    CargaPadron,
    Paciente,
    Preparacion,
    RecetaCronica,
    Turno,
    Ventanilla,
)


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


@admin.register(Preparacion)
class PreparacionAdmin(admin.ModelAdmin):
    """Preparaciones de cada turno: solo lectura, se registran desde el panel y /preparacion/."""

    list_display = ("turno", "estado", "recibida_en", "lista_en", "retirada_en")
    list_filter = ("estado",)
    list_select_related = ("turno",)
    search_fields = ("turno__rut",)
    date_hierarchy = "recibida_en"

    def get_search_results(self, request, queryset, search_term):
        # El número de turno (G-045) no es un campo: se busca por su letra y correlativo.
        queryset, duplicados = super().get_search_results(request, queryset, search_term)
        letras = {letra: categoria for categoria, letra in LETRA_CATEGORIA.items()}
        partes = search_term.strip().upper().split("-")
        if len(partes) == 2 and partes[0] in letras and partes[1].isdigit():
            queryset |= self.model.objects.filter(
                turno__categoria=letras[partes[0]], turno__correlativo=int(partes[1])
            )
        return queryset, duplicados

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
