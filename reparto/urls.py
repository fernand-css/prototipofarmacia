from django.urls import path

from reparto import views

app_name = "reparto"

urlpatterns = [
    path("domicilios/", views.DomiciliosView.as_view(), name="domicilios"),
    path("domicilios/<int:paciente_id>/", views.FichaView.as_view(), name="ficha"),
    path("domicilios/<int:paciente_id>/editar/", views.EditarView.as_view(), name="editar"),
    path("domicilios/<int:paciente_id>/verificar/", views.VerificarView.as_view(), name="verificar"),
    path("domicilios/<int:paciente_id>/pendiente/", views.MarcarPendienteView.as_view(), name="marcar_pendiente"),
    path("domicilios/<int:paciente_id>/fotos/", views.SubirFotoView.as_view(), name="subir_foto"),
    path("domicilios/fotos/<int:pk>/", views.FotoView.as_view(), name="foto"),
    path("domicilios/fotos/<int:pk>/borrar/", views.BorrarFotoView.as_view(), name="borrar_foto"),
]
