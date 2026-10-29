from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("cuentas.urls")),
    path("", include("turnos.urls")),
    path("", include("reparto.urls")),
]
