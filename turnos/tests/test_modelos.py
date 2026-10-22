"""Modelos de turnos: pacientes, recetas, turnos, ventanillas y datos de demostración."""
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from cuentas.validators import validar_rut
from turnos.forms import PacienteAdminForm
from turnos.models import (
    Categoria,
    EstadoTurno,
    Paciente,
    RecetaCronica,
    Turno,
    Ventanilla,
    sumar_meses,
)
from turnos.tests.helpers import crear_paciente, nacido_hace


class PacienteTests(TestCase):
    def test_save_normaliza_el_rut(self):
        paciente = crear_paciente(rut="12.345.678-5")
        self.assertEqual(paciente.rut, "12345678-5")

    def test_edad_antes_y_despues_del_cumpleanos(self):
        hoy = timezone.localdate()
        self.assertEqual(Paciente(fecha_nacimiento=nacido_hace(60)).edad, 60)
        manana = hoy + timedelta(days=1)
        por_cumplir = date(hoy.year - 60, manana.month, manana.day) if manana.year == hoy.year else nacido_hace(59)
        self.assertEqual(Paciente(fecha_nacimiento=por_cumplir).edad, 59)

    def test_preferencial_por_edad_discapacidad_o_embarazo(self):
        self.assertFalse(crear_paciente("11111111-1", edad=59).es_preferencial)
        self.assertTrue(crear_paciente("22222222-2", edad=60).es_preferencial)
        self.assertTrue(crear_paciente("33333333-3", edad=30, tiene_discapacidad=True).es_preferencial)
        self.assertTrue(crear_paciente("44444444-4", edad=30, esta_embarazada=True).es_preferencial)

    def test_despacho_domicilio_por_postrado_o_mayor_de_80(self):
        self.assertFalse(crear_paciente("11111111-1", edad=80).es_despacho_domicilio)
        self.assertTrue(crear_paciente("22222222-2", edad=81).es_despacho_domicilio)
        self.assertTrue(crear_paciente("33333333-3", edad=50, es_postrado=True).es_despacho_domicilio)


class PacienteAdminFormTests(TestCase):
    def datos(self, rut):
        return {
            "rut": rut,
            "nombres": "Ana",
            "apellidos": "Prueba",
            "fecha_nacimiento": "1960-01-01",
        }

    def test_acepta_rut_con_puntos_y_lo_guarda_normalizado(self):
        form = PacienteAdminForm(self.datos("12.345.678-5"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().rut, "12345678-5")

    def test_rechaza_digito_verificador_incorrecto(self):
        form = PacienteAdminForm(self.datos("12.345.678-0"))
        self.assertFalse(form.is_valid())
        self.assertIn("rut", form.errors)

    def test_rechaza_rut_repetido_en_otro_formato(self):
        crear_paciente("12345678-5")
        form = PacienteAdminForm(self.datos("12.345.678-5"))
        self.assertFalse(form.is_valid())
        self.assertIn("rut", form.errors)


class RecetaCronicaTests(TestCase):
    def receta(self, meses_atras=1, vigencia=6, maximas=6, realizadas=0):
        paciente = Paciente.objects.get_or_create(
            rut="12345678-5",
            defaults={"nombres": "Ana", "apellidos": "Prueba", "fecha_nacimiento": date(1960, 1, 1)},
        )[0]
        emision = sumar_meses(timezone.localdate(), -meses_atras)
        return RecetaCronica.objects.create(
            paciente=paciente,
            fecha_emision=emision,
            vigencia_meses=vigencia,
            entregas_maximas=maximas,
            entregas_realizadas=realizadas,
        )

    def test_sumar_meses_ajusta_fin_de_mes(self):
        self.assertEqual(sumar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(sumar_meses(date(2026, 11, 15), 3), date(2027, 2, 15))

    def test_receta_vigente_con_entregas_es_utilizable(self):
        self.assertTrue(self.receta().es_utilizable)

    def test_receta_vencida_no_es_utilizable(self):
        receta = self.receta(meses_atras=7, vigencia=6)
        self.assertTrue(receta.esta_vencida)
        self.assertFalse(receta.es_utilizable)

    def test_receta_agotada_no_es_utilizable(self):
        receta = self.receta(maximas=3, realizadas=3)
        self.assertTrue(receta.esta_agotada)
        self.assertFalse(receta.es_utilizable)


class TurnoTests(TestCase):
    def turno(self, **campos):
        datos = {"categoria": Categoria.GENERAL, "correlativo": 1, "rut": "12345678-5"}
        datos.update(campos)
        return Turno.objects.create(**datos)

    def test_numero_usa_letra_de_la_categoria_y_tres_digitos(self):
        self.assertEqual(self.turno(categoria=Categoria.URGENCIA, correlativo=3).numero, "U-003")
        self.assertEqual(self.turno(categoria=Categoria.PREFERENCIAL, correlativo=12, rut="11111111-1").numero, "P-012")
        self.assertEqual(self.turno(correlativo=45, rut="22222222-2").numero, "G-045")

    def test_rechaza_dos_turnos_activos_para_el_mismo_rut_el_mismo_dia(self):
        self.turno()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.turno(correlativo=2)

    def test_permite_otro_turno_si_el_anterior_ya_no_esta_activo(self):
        for indice, estado in enumerate([EstadoTurno.ATENDIDO, EstadoTurno.AUSENTE, EstadoTurno.ANULADO], start=1):
            self.turno(correlativo=indice, estado=estado)
        self.assertTrue(self.turno(correlativo=4).pk)

    def test_permite_el_mismo_rut_activo_en_otro_dia(self):
        self.turno()
        ayer = timezone.localdate() - timedelta(days=1)
        self.assertTrue(self.turno(fecha=ayer).pk)

    def test_rechaza_numero_repetido_en_el_mismo_dia(self):
        self.turno()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.turno(rut="11111111-1")

    def test_correlativo_se_repite_entre_letras_distintas(self):
        self.turno()
        self.assertTrue(self.turno(categoria=Categoria.PREFERENCIAL, rut="11111111-1").pk)

    def test_es_cronico_depende_de_la_receta(self):
        self.assertFalse(self.turno().es_cronico)


class VentanillaTests(TestCase):
    def test_numero_es_unico(self):
        Ventanilla.objects.create(numero=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ventanilla.objects.create(numero=1)


class CargarDatosDemoTests(TestCase):
    def cargar(self):
        call_command("cargar_datos_demo", stdout=StringIO())

    def cantidades(self):
        return (Ventanilla.objects.count(), Paciente.objects.count(), RecetaCronica.objects.count())

    def test_es_idempotente(self):
        self.cargar()
        primera = self.cantidades()
        self.cargar()
        self.assertEqual(primera, self.cantidades())
        self.assertEqual(primera, (4, 10, 4))

    def test_no_pisa_el_avance_de_las_entregas(self):
        self.cargar()
        receta = RecetaCronica.objects.get(paciente__apellidos="Demo Crónica Vigente")
        RecetaCronica.objects.filter(pk=receta.pk).update(entregas_realizadas=5)
        self.cargar()
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 5)

    def test_los_pacientes_cubren_cada_caso(self):
        self.cargar()
        por_apellido = {p.apellidos: p for p in Paciente.objects.all()}
        self.assertFalse(por_apellido["Demo General"].es_preferencial)
        self.assertTrue(por_apellido["Demo Adulta Mayor"].es_preferencial)
        self.assertTrue(por_apellido["Demo Embarazada"].es_preferencial)
        self.assertTrue(por_apellido["Demo Discapacidad"].es_preferencial)
        self.assertTrue(por_apellido["Demo Mayor de 80"].es_despacho_domicilio)
        self.assertTrue(por_apellido["Demo Postrado"].es_despacho_domicilio)
        recetas = {r.paciente.apellidos: r for r in RecetaCronica.objects.select_related("paciente")}
        self.assertTrue(recetas["Demo Crónica Vigente"].es_utilizable)
        self.assertTrue(recetas["Demo Receta Agotada"].esta_agotada)
        self.assertTrue(recetas["Demo Receta Vencida"].esta_vencida)
        self.assertTrue(recetas["Demo Mayor Crónico"].es_utilizable)

    def test_los_rut_demo_son_validos(self):
        self.cargar()
        for paciente in Paciente.objects.all():
            validar_rut(paciente.rut)
