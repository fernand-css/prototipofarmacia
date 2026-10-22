from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from cuentas.validators import normalizar_rut, validar_rut


class Rol(models.TextChoices):
    QF = "qf", "Química Farmacéutica"
    FUNCIONARIO = "funcionario", "Funcionario"
    ENCARGADO_TERRENO = "encargado_terreno", "Encargado de Terreno"


class UsuarioManager(BaseUserManager):
    def create_user(self, rut, nombres, apellidos, password=None, **extra):
        rut = normalizar_rut(rut)
        validar_rut(rut)
        usuario = self.model(rut=rut, nombres=nombres, apellidos=apellidos, **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, rut, nombres, apellidos, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        extra["rol"] = Rol.QF
        extra["debe_cambiar_password"] = False
        return self.create_user(rut, nombres, apellidos, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    rut = models.CharField("RUT", max_length=10, unique=True, validators=[validar_rut])
    nombres = models.CharField("nombres", max_length=100)
    apellidos = models.CharField("apellidos", max_length=100)
    rol = models.CharField("rol", max_length=20, choices=Rol.choices, default=Rol.FUNCIONARIO)
    debe_cambiar_password = models.BooleanField("debe cambiar la contraseña", default=True)
    is_active = models.BooleanField("activo", default=True)
    is_staff = models.BooleanField("acceso al admin", default=False)
    fecha_alta = models.DateTimeField("fecha de alta", default=timezone.now)

    objects = UsuarioManager()

    USERNAME_FIELD = "rut"
    REQUIRED_FIELDS = ["nombres", "apellidos"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.rut})"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}"

    @property
    def es_qf(self):
        return self.rol == Rol.QF

    @property
    def puede_atender(self):
        """Atienden en ventanilla el funcionario y la QF; el Encargado de Terreno no."""
        return self.rol in (Rol.FUNCIONARIO, Rol.QF)
