from django.urls import path

from turnos import views

app_name = "turnos"

urlpatterns = [
    path("totem/", views.totem, name="totem"),
    path("totem/turno/", views.totem_turno, name="totem_turno"),
    path("sala/", views.sala, name="sala"),
    path("sala/estado/", views.SalaEstadoView.as_view(), name="sala_estado"),
    path("atencion/", views.AtencionView.as_view(), name="atencion"),
    path("atencion/abrir/", views.AbrirVentanillaView.as_view(), name="abrir_ventanilla"),
    path("atencion/cola/", views.ColaView.as_view(), name="cola"),
    path("atencion/llamar/", views.LlamarSiguienteView.as_view(), name="llamar_siguiente"),
    path("atencion/re-llamar/", views.ReLlamarView.as_view(), name="re_llamar"),
    path("atencion/iniciar/", views.IniciarAtencionView.as_view(), name="iniciar_atencion"),
    path("atencion/finalizar/", views.FinalizarAtencionView.as_view(), name="finalizar_atencion"),
    path("atencion/ausente/", views.MarcarAusenteView.as_view(), name="marcar_ausente"),
    path("atencion/no-retiro/", views.RegistrarNoRetiroView.as_view(), name="registrar_no_retiro"),
    path("atencion/preparacion/", views.AtencionPreparacionView.as_view(), name="atencion_preparacion"),
    path("atencion/urgencia/", views.EmitirUrgenciaView.as_view(), name="emitir_urgencia"),
    path("atencion/terminar/", views.TerminarTurnoView.as_view(), name="terminar_turno"),
    path("ventanillas/", views.VentanillasListaView.as_view(), name="ventanillas"),
    path("ventanillas/nueva/", views.VentanillaCrearView.as_view(), name="ventanilla_crear"),
    path(
        "ventanillas/<int:pk>/estado/",
        views.VentanillaCambiarEstadoView.as_view(),
        name="ventanilla_cambiar_estado",
    ),
    path("padron/", views.PadronView.as_view(), name="padron"),
    path("padron/plantilla/", views.PadronPlantillaView.as_view(), name="padron_plantilla"),
    path("padron/<int:pk>/", views.PadronCargaView.as_view(), name="padron_carga"),
    path("padron/<int:pk>/confirmar/", views.PadronConfirmarView.as_view(), name="padron_confirmar"),
    path("padron/<int:pk>/cancelar/", views.PadronCancelarView.as_view(), name="padron_cancelar"),
    path("padron/<int:pk>/rechazos.csv", views.PadronRechazosView.as_view(), name="padron_rechazos"),
    path("recetas/", views.RecetasView.as_view(), name="recetas"),
    path("preparacion/", views.PreparacionView.as_view(), name="preparacion"),
    path("preparacion/fila/", views.PreparacionFilaView.as_view(), name="preparacion_fila"),
    path("preparacion/<int:pk>/lista/", views.PreparacionListaView.as_view(), name="preparacion_lista"),
    path("preparados/", views.PreparadosView.as_view(), name="preparados"),
    path("preparados/<int:pk>/entregar/", views.PreparadoEntregarView.as_view(), name="preparado_entregar"),
]
