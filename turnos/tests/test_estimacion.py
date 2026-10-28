"""Espera estimada del ticket del tótem (HU-18): orden simulado, promedio, ventanillas y textos."""
from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Rol
from turnos.estimacion import estimar_espera, promedio_de_atencion, texto_de_espera, turnos_por_delante
from turnos.models import Categoria, EstadoTurno, Preparacion, Turno, Ventanilla
from turnos.motor import elegir_siguiente
from turnos.servicios import emitir_turno
from turnos.tests.helpers import crear_paciente, crear_usuario, rut_valido

G, P, U = Categoria.GENERAL, Categoria.PREFERENCIAL, Categoria.URGENCIA


class EstimacionTests(TestCase):
    def setUp(self):
        self.funcionario = crear_usuario("12345678-5", Rol.FUNCIONARIO)
        self.hoy = timezone.localdate()
        self.ahora = timezone.now()
        self.cantidad = 0

    def turno(self, categoria=G, fecha=None, **extra):
        """Un turno con número y RUT únicos; los de hoy se emiten en orden de creación."""
        self.cantidad += 1
        datos = {
            "categoria": categoria,
            "correlativo": self.cantidad,
            "rut": f"{self.cantidad:08d}-0",
            "fecha": fecha or self.hoy,
            "emitido_en": self.ahora - timedelta(hours=2) + timedelta(seconds=self.cantidad),
        }
        datos.update(extra)
        return Turno.objects.create(**datos)

    def historial(self, cantidad, minutos=4, dias_atras=1, con_preparacion=True):
        """Atenciones ya cerradas, de `minutos` desde la recepción hasta la entrega."""
        cierre = self.ahora - timedelta(days=dias_atras)
        for _ in range(cantidad):
            turno = self.turno(
                fecha=timezone.localdate(cierre),
                estado=EstadoTurno.ATENDIDO,
                inicio_atencion_en=cierre - timedelta(minutes=minutos),
                cierre_en=cierre,
            )
            if con_preparacion:
                Preparacion.objects.create(
                    turno=turno, recibida_en=turno.inicio_atencion_en, recibida_por=self.funcionario
                )

    def ventanillas_abiertas(self, cantidad):
        for numero in range(1, cantidad + 1):
            funcionario = crear_usuario(rut_valido(str(20000000 + numero)), Rol.FUNCIONARIO)
            Ventanilla.objects.create(numero=numero, funcionario=funcionario)


class OrdenSimuladoTests(EstimacionTests):
    def llamar_en_orden(self):
        """Llama a todos con `elegir_siguiente`, como lo harían las ventanillas, y devuelve el orden."""
        orden = []
        momento = self.ahora - timedelta(minutes=30)
        while (siguiente := elegir_siguiente(self.hoy)) is not None:
            momento += timedelta(seconds=10)
            Turno.objects.filter(pk=siguiente.pk).update(estado=EstadoTurno.LLAMADO, llamado_en=momento)
            orden.append(siguiente.pk)
        return orden

    def comparar(self, categorias, ya_llamados=()):
        momento = self.ahora - timedelta(hours=1)
        for indice, categoria in enumerate(ya_llamados):
            self.turno(categoria, estado=EstadoTurno.ATENDIDO, llamado_en=momento + timedelta(seconds=indice))
        cola = [self.turno(categoria) for categoria in categorias]
        previstos = {turno.pk: turnos_por_delante(turno) for turno in cola}
        orden = self.llamar_en_orden()
        self.assertEqual({pk: orden.index(pk) for pk in orden}, previstos)

    def test_cola_mezclada_coincide_con_el_motor(self):
        self.comparar([G, P, G, G, U, P, G, G, G, P, U, G, P, P, G])

    def test_respeta_la_racha_de_generales_ya_llamados_hoy(self):
        self.comparar([P, G, G, P, G], ya_llamados=[P, G, G])

    def test_solo_preferenciales_o_solo_generales(self):
        self.comparar([P, P, P])
        Turno.objects.all().delete()
        self.comparar([G, G, U, G])

    def test_un_turno_que_no_esta_en_espera_no_tiene_nadie_delante(self):
        self.assertEqual(turnos_por_delante(self.turno(estado=EstadoTurno.LLAMADO)), 0)


class PromedioTests(EstimacionTests):
    def test_con_19_muestras_no_hay_promedio_y_con_20_si(self):
        self.historial(19, minutos=4)
        self.assertIsNone(promedio_de_atencion(self.ahora))
        self.historial(1, minutos=4)
        self.assertAlmostEqual(promedio_de_atencion(self.ahora), 4)

    def test_promedia_la_atencion_completa(self):
        self.historial(10, minutos=2)
        self.historial(10, minutos=6)
        self.assertAlmostEqual(promedio_de_atencion(self.ahora), 4)

    def test_excluye_las_de_hace_mas_de_30_dias(self):
        self.historial(19, minutos=4)
        self.historial(5, minutos=4, dias_atras=settings.TURNOS_DIAS_HISTORIAL_ESPERA + 1)
        self.assertIsNone(promedio_de_atencion(self.ahora))

    def test_excluye_los_turnos_sin_preparacion(self):
        self.historial(19, minutos=4)
        self.historial(5, minutos=4, con_preparacion=False)
        self.assertIsNone(promedio_de_atencion(self.ahora))


class EstimarEsperaTests(EstimacionTests):
    def test_ejemplo_del_spec_da_10_minutos(self):
        # 4 turnos por delante, 1 en curso, 2 ventanillas abiertas y 4 minutos de promedio.
        self.historial(20, minutos=4)
        self.ventanillas_abiertas(2)
        self.turno(estado=EstadoTurno.EN_ATENCION)
        for _ in range(4):
            self.turno()
        nuevo = self.turno()
        self.assertEqual(turnos_por_delante(nuevo), 4)
        self.assertEqual(estimar_espera(nuevo, self.ahora), 10)

    def test_redondea_hacia_arriba_al_multiplo_de_5(self):
        self.historial(20, minutos=4)
        self.ventanillas_abiertas(1)
        for _ in range(3):
            self.turno()
        self.assertEqual(estimar_espera(self.turno(), self.ahora), 15)  # 3 × 4 = 12

    def test_menos_que_el_redondeo_da_cero(self):
        self.historial(20, minutos=4)
        self.ventanillas_abiertas(1)
        self.assertEqual(estimar_espera(self.turno(), self.ahora), 0)  # nadie delante

    def test_sin_ventanillas_abiertas_no_hay_estimacion(self):
        self.historial(20, minutos=4)
        Ventanilla.objects.create(numero=1)  # habilitada, pero nadie la tiene abierta
        Ventanilla.objects.create(numero=2, habilitada=False, funcionario=self.funcionario)
        self.assertIsNone(estimar_espera(self.turno(), self.ahora))

    def test_sin_historial_suficiente_no_hay_estimacion(self):
        self.historial(19, minutos=4)
        self.ventanillas_abiertas(1)
        self.assertIsNone(estimar_espera(self.turno(), self.ahora))

    def test_un_turno_que_no_esta_en_espera_no_tiene_estimacion(self):
        self.historial(20, minutos=4)
        self.ventanillas_abiertas(1)
        self.assertIsNone(estimar_espera(self.turno(estado=EstadoTurno.LLAMADO), self.ahora))


class TextoDeEsperaTests(TestCase):
    def test_los_dos_textos(self):
        self.assertEqual(texto_de_espera(25), "Espera estimada: unos 25 minutos")
        self.assertEqual(texto_de_espera(0), "Espera estimada: menos de 5 minutos")
        self.assertIsNone(texto_de_espera(None))

    @override_settings(TURNOS_MINUTOS_REDONDEO_ESPERA=10)
    def test_el_texto_sigue_al_redondeo_configurado(self):
        self.assertEqual(texto_de_espera(0), "Espera estimada: menos de 10 minutos")


class TicketDelTotemTests(EstimacionTests):
    def digitar(self, cuerpo):
        return self.client.post(reverse("turnos:totem_turno"), {"rut": rut_valido(cuerpo)})

    def test_con_historial_el_ticket_muestra_la_espera_y_la_hora_para_imprimir(self):
        self.historial(20, minutos=4)
        self.ventanillas_abiertas(1)
        self.digitar("10000001")
        self.digitar("10000002")
        respuesta = self.digitar("10000003")  # 2 por delante × 4 minutos = 8
        self.assertContains(respuesta, "Espera estimada: unos 10 minutos")
        hora = timezone.localtime().strftime("%H:")
        self.assertContains(respuesta, f'<span class="totem__solo-imprimir">, calculada a las {hora}')

    def test_sin_historial_suficiente_no_aparece_la_linea(self):
        self.historial(19, minutos=4)
        self.ventanillas_abiertas(1)
        respuesta = self.digitar("10000001")
        self.assertContains(respuesta, "G-")
        self.assertNotContains(respuesta, "Espera estimada")
        self.assertNotContains(respuesta, "calculada a las")

    def test_volver_a_digitar_el_rut_recalcula_con_la_cola_actual(self):
        self.historial(20, minutos=4)
        self.ventanillas_abiertas(1)
        self.assertContains(self.digitar("10000001"), "Espera estimada: menos de 5 minutos")
        emitir_turno(rut_valido("10000002"), desde_panel=True)
        emitir_turno(rut_valido("10000003"), desde_panel=True)  # dos urgencias se adelantan
        respuesta = self.digitar("10000001")
        self.assertContains(respuesta, "Usted ya tiene un turno")
        self.assertContains(respuesta, "Espera estimada: unos 10 minutos")

    def test_el_aviso_de_domicilio_no_lleva_estimacion(self):
        self.historial(20, minutos=4)
        self.ventanillas_abiertas(1)
        crear_paciente(rut_valido("10000001"), edad=85)
        respuesta = self.digitar("10000001")
        self.assertContains(respuesta, "Su despacho es a domicilio")
        self.assertNotContains(respuesta, "Espera estimada")
