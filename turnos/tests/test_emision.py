"""Emisión de turnos: categoría, turno vigente, domicilio, bloqueo por receta y correlativos."""
from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from turnos.models import Categoria, EstadoTurno, Turno
from turnos.servicios import TipoResultado, emitir_turno
from turnos.tests.helpers import crear_paciente, crear_receta, rut_valido


class EmitirTurnoTests(TestCase):
    def setUp(self):
        self.rut = "12345678-5"

    def test_rut_desconocido_recibe_turno_general_sin_paciente(self):
        resultado = emitir_turno(self.rut)
        self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertEqual(resultado.turno.numero, "G-001")
        self.assertIsNone(resultado.turno.paciente)
        self.assertEqual(resultado.turno.rut, self.rut)

    def test_paciente_comun_recibe_turno_general(self):
        paciente = crear_paciente(self.rut, edad=35)
        resultado = emitir_turno(self.rut)
        self.assertEqual(resultado.turno.categoria, Categoria.GENERAL)
        self.assertEqual(resultado.turno.paciente, paciente)

    def test_paciente_preferencial_recibe_turno_con_letra_p(self):
        crear_paciente(self.rut, edad=70)
        self.assertEqual(emitir_turno(self.rut).turno.numero, "P-001")

    def test_rut_invalido_lanza_error_y_no_crea_turno(self):
        with self.assertRaises(ValidationError):
            emitir_turno("12.345.678-0")
        with self.assertRaises(ValidationError):
            emitir_turno("abc")
        self.assertEqual(Turno.objects.count(), 0)

    def test_distintos_formatos_del_rut_dan_el_mismo_turno_vigente(self):
        primero = emitir_turno("12.345.678-5")
        segundo = emitir_turno("123456785")
        self.assertEqual(primero.tipo, TipoResultado.EMITIDO)
        self.assertEqual(segundo.tipo, TipoResultado.VIGENTE)
        self.assertEqual(primero.turno.pk, segundo.turno.pk)
        self.assertEqual(Turno.objects.count(), 1)

    def test_turno_vigente_en_cualquier_estado_activo(self):
        for estado in (EstadoTurno.LLAMADO, EstadoTurno.EN_ATENCION):
            Turno.objects.all().delete()
            emitir_turno(self.rut)
            Turno.objects.update(estado=estado)
            self.assertEqual(emitir_turno(self.rut).tipo, TipoResultado.VIGENTE)

    def test_turno_cerrado_permite_sacar_uno_nuevo(self):
        emitir_turno(self.rut)
        for estado in (EstadoTurno.ATENDIDO, EstadoTurno.AUSENTE):
            Turno.objects.filter(rut=self.rut).update(estado=estado)
            resultado = emitir_turno(self.rut)
            self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertEqual(Turno.objects.count(), 3)

    def test_postrado_o_mayor_de_80_recibe_aviso_de_domicilio_sin_turno(self):
        crear_paciente(self.rut, edad=55, es_postrado=True)
        crear_paciente(rut_valido("10000002"), edad=84)
        for rut in (self.rut, rut_valido("10000002")):
            resultado = emitir_turno(rut)
            self.assertEqual(resultado.tipo, TipoResultado.DOMICILIO)
            self.assertEqual(resultado.paciente.rut, rut)
        self.assertEqual(Turno.objects.count(), 0)

    def test_insistir_en_domicilio_emite_el_turno(self):
        crear_paciente(self.rut, edad=84)
        resultado = emitir_turno(self.rut, insistir_domicilio=True)
        self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertEqual(resultado.turno.categoria, Categoria.PREFERENCIAL)

    def test_receta_agotada_o_vencida_bloquea_el_turno(self):
        agotada = crear_paciente(self.rut, edad=40)
        crear_receta(agotada, maximas=3, realizadas=3)
        vencida = crear_paciente(rut_valido("10000002"), edad=40)
        crear_receta(vencida, meses_atras=8, vigencia=6)
        for rut in (self.rut, rut_valido("10000002")):
            self.assertEqual(emitir_turno(rut).tipo, TipoResultado.BLOQUEADO)
        self.assertEqual(Turno.objects.count(), 0)

    def test_insistir_en_domicilio_no_salta_el_bloqueo(self):
        paciente = crear_paciente(self.rut, edad=84)
        crear_receta(paciente, maximas=2, realizadas=2)
        resultado = emitir_turno(self.rut, insistir_domicilio=True)
        self.assertEqual(resultado.tipo, TipoResultado.BLOQUEADO)

    def test_sin_recetas_no_hay_bloqueo_ni_receta_asociada(self):
        crear_paciente(self.rut, edad=40)
        self.assertIsNone(emitir_turno(self.rut).turno.receta)

    def test_asocia_la_receta_utilizable_mas_antigua(self):
        paciente = crear_paciente(self.rut, edad=40)
        crear_receta(paciente, maximas=2, realizadas=2, meses_atras=5)
        antigua = crear_receta(paciente, meses_atras=3)
        crear_receta(paciente, meses_atras=1)
        turno = emitir_turno(self.rut).turno
        self.assertEqual(turno.receta, antigua)
        self.assertTrue(turno.es_cronico)

    def test_correlativos_son_independientes_por_letra(self):
        crear_paciente(rut_valido("10000002"), edad=70)
        crear_paciente(rut_valido("10000003"), edad=70)
        numeros = [
            emitir_turno(self.rut).turno.numero,
            emitir_turno(rut_valido("10000002")).turno.numero,
            emitir_turno(rut_valido("10000001")).turno.numero,
            emitir_turno(rut_valido("10000003")).turno.numero,
        ]
        self.assertEqual(numeros, ["G-001", "P-001", "G-002", "P-002"])

    def test_el_correlativo_se_reinicia_cada_dia(self):
        ayer = timezone.localdate() - timedelta(days=1)
        Turno.objects.create(fecha=ayer, categoria=Categoria.GENERAL, correlativo=45, rut=self.rut)
        self.assertEqual(emitir_turno(self.rut).turno.numero, "G-001")

    def test_reintenta_si_el_correlativo_choca(self):
        original = Turno.objects.create
        llamadas = []

        def create_con_choque(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 1:
                raise IntegrityError("choque simulado")
            return original(*args, **kwargs)

        with mock.patch.object(Turno.objects, "create", side_effect=create_con_choque):
            resultado = emitir_turno(self.rut)
        self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertEqual(len(llamadas), 2)

    def test_deja_de_reintentar_tras_tres_choques(self):
        with mock.patch.object(Turno.objects, "create", side_effect=IntegrityError("choque")) as create:
            with self.assertRaises(IntegrityError):
                emitir_turno(self.rut)
        self.assertEqual(create.call_count, 3)


class EmitirUrgenciaTests(TestCase):
    def setUp(self):
        self.rut = "12345678-5"

    def test_emite_turno_de_urgencia(self):
        resultado = emitir_turno(self.rut, desde_panel=True)
        self.assertEqual(resultado.turno.numero, "U-001")

    def test_no_aplica_domicilio_ni_bloqueo(self):
        paciente = crear_paciente(self.rut, edad=84, es_postrado=True)
        crear_receta(paciente, maximas=1, realizadas=1)
        resultado = emitir_turno(self.rut, desde_panel=True)
        self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertIsNone(resultado.turno.receta)

    def test_asocia_la_receta_si_hay_una_utilizable(self):
        paciente = crear_paciente(self.rut, edad=40)
        receta = crear_receta(paciente)
        self.assertEqual(emitir_turno(self.rut, desde_panel=True).turno.receta, receta)

    def test_anula_el_turno_en_espera_del_mismo_rut(self):
        anterior = emitir_turno(self.rut).turno
        resultado = emitir_turno(self.rut, desde_panel=True)
        anterior.refresh_from_db()
        self.assertEqual(anterior.estado, EstadoTurno.ANULADO)
        self.assertIsNotNone(anterior.cierre_en)
        self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertEqual(resultado.turno.numero, "U-001")

    def test_no_emite_si_el_turno_ya_esta_llamado_o_en_atencion(self):
        for estado in (EstadoTurno.LLAMADO, EstadoTurno.EN_ATENCION):
            Turno.objects.all().delete()
            emitir_turno(self.rut)
            Turno.objects.update(estado=estado)
            resultado = emitir_turno(self.rut, desde_panel=True)
            self.assertEqual(resultado.tipo, TipoResultado.VIGENTE)
            self.assertEqual(Turno.objects.count(), 1)
            self.assertEqual(Turno.objects.get().estado, estado)

    def test_no_duplica_una_urgencia_en_espera(self):
        primera = emitir_turno(self.rut, desde_panel=True)
        segunda = emitir_turno(self.rut, desde_panel=True)
        self.assertEqual(segunda.tipo, TipoResultado.VIGENTE)
        self.assertEqual(segunda.turno.pk, primera.turno.pk)
