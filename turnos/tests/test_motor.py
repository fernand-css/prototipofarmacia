"""Motor de la fila: urgencia primero y proporción entre generales y preferenciales."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from turnos.models import Categoria, EstadoTurno, Turno
from turnos.motor import elegir_siguiente


class MotorTests(TestCase):
    """Escenarios de simulación de carga del motor (sin ventanillas: solo el orden de llamado)."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.inicio = timezone.now().replace(microsecond=0)
        self.cantidad = 0
        self.llamadas = 0

    def emitir(self, categoria, correlativo, minuto=None, fecha=None):
        self.cantidad += 1
        return Turno.objects.create(
            fecha=fecha or self.hoy,
            categoria=categoria,
            correlativo=correlativo,
            rut=f"{self.cantidad:08d}-0",
            emitido_en=self.inicio + timedelta(minutes=minuto if minuto is not None else self.cantidad),
        )

    def llamar(self, estado=EstadoTurno.LLAMADO):
        """Simula 'llamar siguiente': toma lo que elige el motor y lo marca como llamado."""
        turno = elegir_siguiente(self.hoy)
        if turno:
            self.llamadas += 1
            turno.estado = estado
            turno.llamado_en = turno.ultimo_llamado_en = self.inicio + timedelta(hours=1, seconds=self.llamadas)
            turno.veces_llamado = 1
            turno.save()
        return turno

    def vaciar(self):
        numeros = []
        while (turno := self.llamar()) is not None:
            numeros.append(turno.numero)
        return numeros

    def crear(self, generales=0, preferenciales=0, urgencias=0):
        for n in range(1, generales + 1):
            self.emitir(Categoria.GENERAL, n)
        for n in range(1, preferenciales + 1):
            self.emitir(Categoria.PREFERENCIAL, n)
        for n in range(1, urgencias + 1):
            self.emitir(Categoria.URGENCIA, n)

    def test_sin_nadie_en_espera_no_hay_siguiente(self):
        self.assertIsNone(elegir_siguiente(self.hoy))

    def test_escenario_a_carga_mixta(self):
        self.crear(generales=6, preferenciales=3)
        self.assertEqual(
            self.vaciar(),
            ["G-001", "G-002", "P-001", "G-003", "G-004", "P-002", "G-005", "G-006", "P-003"],
        )

    def test_escenario_b_mayoria_preferencial(self):
        self.crear(generales=1, preferenciales=3)
        self.assertEqual(self.vaciar(), ["G-001", "P-001", "P-002", "P-003"])

    def test_escenario_c_extension_horaria_con_una_urgencia_tardia(self):
        self.crear(generales=3)
        self.emitir(Categoria.URGENCIA, 1)
        self.assertEqual(self.vaciar(), ["U-001", "G-001", "G-002", "G-003"])

    def test_la_proporcion_se_toma_de_la_configuracion(self):
        self.crear(generales=6, preferenciales=3)
        with override_settings(TURNOS_GENERALES_POR_PREFERENCIAL=3):
            self.assertEqual(
                self.vaciar(),
                ["G-001", "G-002", "G-003", "P-001", "G-004", "G-005", "G-006", "P-002", "P-003"],
            )

    def test_la_urgencia_va_primero_aunque_llegue_despues(self):
        self.crear(generales=2, preferenciales=2)
        self.emitir(Categoria.URGENCIA, 1)
        self.emitir(Categoria.URGENCIA, 2)
        self.assertEqual(self.llamar().numero, "U-001")
        self.assertEqual(self.llamar().numero, "U-002")

    def test_la_urgencia_no_cuenta_ni_corta_la_racha_de_generales(self):
        self.crear(generales=3, preferenciales=1)
        self.assertEqual(self.llamar().numero, "G-001")
        self.emitir(Categoria.URGENCIA, 1)
        self.assertEqual(self.vaciar(), ["U-001", "G-002", "P-001", "G-003"])

    def test_dentro_de_cada_categoria_manda_el_orden_de_emision(self):
        self.emitir(Categoria.GENERAL, 2, minuto=10)
        self.emitir(Categoria.GENERAL, 1, minuto=20)
        self.assertEqual(self.llamar().numero, "G-002")

    def test_un_ausente_cuenta_como_llamado_para_la_proporcion(self):
        self.crear(generales=3, preferenciales=1)
        self.llamar(estado=EstadoTurno.AUSENTE)
        self.llamar()
        self.assertEqual(self.llamar().numero, "P-001")

    def test_la_racha_se_reinicia_tras_un_preferencial(self):
        self.crear(generales=5, preferenciales=2)
        self.assertEqual(self.vaciar()[:6], ["G-001", "G-002", "P-001", "G-003", "G-004", "P-002"])

    def test_solo_considera_los_turnos_en_espera_de_la_fecha(self):
        ayer = self.hoy - timedelta(days=1)
        self.emitir(Categoria.URGENCIA, 1, fecha=ayer)
        self.emitir(Categoria.GENERAL, 2, fecha=ayer)
        anulado = self.emitir(Categoria.URGENCIA, 2)
        anulado.estado = EstadoTurno.ANULADO
        anulado.save()
        atendido = self.emitir(Categoria.GENERAL, 1)
        atendido.estado = EstadoTurno.ATENDIDO
        atendido.save()
        self.assertIsNone(elegir_siguiente(self.hoy))

    def test_las_llamadas_de_otro_dia_no_cuentan_para_la_racha(self):
        ayer = self.hoy - timedelta(days=1)
        for n in range(1, 4):
            turno = self.emitir(Categoria.GENERAL, n, fecha=ayer)
            turno.estado = EstadoTurno.ATENDIDO
            turno.llamado_en = self.inicio
            turno.save()
        self.crear(generales=1, preferenciales=1)
        self.assertEqual(self.llamar().numero, "G-001")

    def test_elegir_no_modifica_ningun_dato(self):
        self.crear(generales=2, preferenciales=1)
        antes = list(Turno.objects.values())
        elegir_siguiente(self.hoy)
        self.assertEqual(antes, list(Turno.objects.values()))
