"""Preparación de cada atención: recepción, lista, entrega y «No retiró» (HU-17, HU-18)."""
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Rol

from turnos.models import (
    Categoria,
    EstadoPreparacion,
    EstadoTurno,
    Preparacion,
    RecetaCronica,
    Turno,
    Ventanilla,
)
from turnos.servicios import (
    ErrorDeAtencion,
    TipoResultado,
    emitir_turno,
    entregar_pendiente,
    finalizar_atencion,
    iniciar_atencion,
    llamar_siguiente,
    marcar_lista,
    preparados_pendientes,
    registrar_no_retiro,
)
from turnos.tests.helpers import (
    TransicionesTests,
    crear_paciente,
    crear_receta,
    crear_usuario,
    dejar_lista,
    rut_valido,
)
from turnos.tests.test_sesion import META_ACTIVIDAD


class RecepcionTests(TransicionesTests):
    def test_iniciar_la_atencion_crea_la_preparacion(self):
        self.turno()
        llamar_siguiente(self.ana)
        turno = iniciar_atencion(self.ana)
        preparacion = Preparacion.objects.get()
        self.assertEqual(preparacion.turno, turno)
        self.assertEqual(preparacion.estado, EstadoPreparacion.EN_PREPARACION)
        self.assertEqual(preparacion.recibida_en, turno.inicio_atencion_en)
        self.assertEqual(preparacion.recibida_por, self.ana)

    def test_la_urgencia_tambien_se_prepara(self):
        self.turno(categoria=Categoria.URGENCIA)
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        self.assertEqual(Preparacion.objects.get().turno.categoria, Categoria.URGENCIA)

    def test_iniciar_dos_veces_no_crea_dos_preparaciones(self):
        self.turno()
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        with self.assertRaises(ErrorDeAtencion):
            iniciar_atencion(self.ana)
        self.assertEqual(Preparacion.objects.count(), 1)

    def test_llamar_no_crea_preparacion(self):
        self.turno()
        llamar_siguiente(self.ana)
        self.assertFalse(Preparacion.objects.exists())


class FinalizarConPreparacionTests(TransicionesTests):
    def test_con_la_preparacion_sin_terminar_no_se_finaliza(self):
        receta, llamado = self.receta_con_turno_llamado(entregas_realizadas=2)
        iniciar_atencion(self.ana)
        with self.assertRaisesMessage(ErrorDeAtencion, "La preparación aún no está lista."):
            finalizar_atencion(self.ana)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 2)
        self.assertEqual(Turno.objects.get(pk=llamado.pk).estado, EstadoTurno.EN_ATENCION)
        self.assertEqual(Preparacion.objects.get().estado, EstadoPreparacion.EN_PREPARACION)

    def test_con_la_preparacion_lista_entrega_y_suma_una_entrega(self):
        receta, _ = self.receta_con_turno_llamado(entregas_realizadas=2)
        iniciar_atencion(self.ana)
        dejar_lista(self.ana)
        turno = finalizar_atencion(self.ana)
        self.assertEqual(turno.estado, EstadoTurno.ATENDIDO)
        preparacion = Preparacion.objects.get()
        self.assertEqual(preparacion.estado, EstadoPreparacion.ENTREGADA)
        self.assertEqual(preparacion.retirada_en, turno.cierre_en)
        self.assertEqual(preparacion.retirada_por, self.ana)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 3)

    def test_un_turno_sin_preparacion_se_finaliza_como_antes(self):
        receta, llamado = self.receta_con_turno_llamado(entregas_realizadas=2)
        # Un turno que quedó en atención antes de este spec, o editado en el admin.
        Turno.objects.filter(pk=llamado.pk).update(estado=EstadoTurno.EN_ATENCION)
        turno = finalizar_atencion(self.ana)
        self.assertEqual(turno.estado, EstadoTurno.ATENDIDO)
        self.assertFalse(Preparacion.objects.exists())
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 3)


class MarcarListaTests(TransicionesTests):
    def en_preparacion(self):
        self.turno()
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        return Preparacion.objects.get()

    def test_guarda_la_hora_y_quien_preparo(self):
        preparacion = marcar_lista(self.en_preparacion().pk, self.beto)
        self.assertEqual(preparacion.estado, EstadoPreparacion.LISTA)
        self.assertIsNotNone(preparacion.lista_en)
        self.assertEqual(preparacion.preparada_por, self.beto)

    def test_marcarla_dos_veces_conserva_el_primer_momento(self):
        preparacion = self.en_preparacion()
        primera = marcar_lista(preparacion.pk, self.beto)
        with self.assertRaisesMessage(ErrorDeAtencion, "ya estaba lista"):
            marcar_lista(preparacion.pk, self.ana)
        preparacion.refresh_from_db()
        self.assertEqual(preparacion.lista_en, primera.lista_en)
        self.assertEqual(preparacion.preparada_por, self.beto)

    def test_una_preparacion_anulada_no_se_marca(self):
        preparacion = self.en_preparacion()
        registrar_no_retiro(self.ana)
        with self.assertRaisesMessage(ErrorDeAtencion, "ya no está en curso"):
            marcar_lista(preparacion.pk, self.beto)
        preparacion.refresh_from_db()
        self.assertEqual(preparacion.estado, EstadoPreparacion.ANULADA)
        self.assertIsNone(preparacion.lista_en)

    def test_una_preparacion_que_no_existe_avisa(self):
        with self.assertRaisesMessage(ErrorDeAtencion, "no existe"):
            marcar_lista(999, self.beto)


class NoRetiroTests(TransicionesTests):
    def test_con_la_preparacion_lista_queda_pendiente_de_retiro(self):
        receta, llamado = self.receta_con_turno_llamado(entregas_realizadas=2)
        iniciar_atencion(self.ana)
        lista = dejar_lista(self.ana)
        turno = registrar_no_retiro(self.ana)
        self.assertEqual(turno.pk, llamado.pk)
        self.assertEqual(turno.estado, EstadoTurno.AUSENTE)
        self.assertIsNotNone(turno.cierre_en)
        preparacion = Preparacion.objects.get()
        self.assertEqual(preparacion.estado, EstadoPreparacion.PENDIENTE_RETIRO)
        self.assertEqual(preparacion.no_retirada_en, turno.cierre_en)
        self.assertEqual(preparacion.lista_en, lista.lista_en)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 2)

    def test_con_la_preparacion_sin_terminar_se_anula(self):
        receta, _ = self.receta_con_turno_llamado(entregas_realizadas=2)
        iniciar_atencion(self.ana)
        turno = registrar_no_retiro(self.ana)
        self.assertEqual(turno.estado, EstadoTurno.AUSENTE)
        preparacion = Preparacion.objects.get()
        self.assertEqual(preparacion.estado, EstadoPreparacion.ANULADA)
        self.assertIsNone(preparacion.no_retirada_en)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 2)

    def test_no_exige_plazo_desde_el_llamado(self):
        self.llamado_hace(segundos=1)
        iniciar_atencion(self.ana)
        self.assertEqual(registrar_no_retiro(self.ana).estado, EstadoTurno.AUSENTE)

    def test_solo_acepta_un_turno_en_atencion(self):
        self.llamado_hace(segundos=1)
        with self.assertRaisesMessage(ErrorDeAtencion, "No tiene una atención en curso"):
            registrar_no_retiro(self.ana)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.LLAMADO)

    def test_no_toca_el_turno_de_otro_funcionario(self):
        self.turno()
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        with self.assertRaises(ErrorDeAtencion):
            registrar_no_retiro(self.beto)
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.EN_ATENCION)

    def test_despues_ya_no_se_puede_finalizar(self):
        self.turno()
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        dejar_lista(self.ana)
        registrar_no_retiro(self.ana)
        with self.assertRaises(ErrorDeAtencion):
            finalizar_atencion(self.ana)
        self.assertEqual(Preparacion.objects.get().estado, EstadoPreparacion.PENDIENTE_RETIRO)

    def test_el_paciente_puede_sacar_un_turno_nuevo_en_el_totem(self):
        paciente_rut = rut_valido("10000001")
        emitir_turno(paciente_rut)
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        dejar_lista(self.ana)
        registrar_no_retiro(self.ana)
        resultado = emitir_turno(paciente_rut)
        self.assertEqual(resultado.tipo, TipoResultado.EMITIDO)
        self.assertEqual(resultado.turno.numero, "G-002")

    def test_el_funcionario_queda_libre_para_llamar_al_siguiente(self):
        self.turno(correlativo=1)
        self.turno(correlativo=2)
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        registrar_no_retiro(self.ana)
        self.assertEqual(llamar_siguiente(self.ana).numero, "G-002")


class ConPendientesTests(TransicionesTests):
    def pendiente(self, cuerpo, apellidos="Prueba", con_paciente=True, **receta):
        """Un preparado que el paciente dejó sin retirar: llamado, recibido, listo y «No retiró»."""
        rut = rut_valido(cuerpo)
        paciente = crear_paciente(rut, apellidos=apellidos) if con_paciente else None
        receta_creada = crear_receta(paciente, **receta) if receta else None
        self.cantidad += 1
        Turno.objects.create(
            categoria=Categoria.GENERAL,
            correlativo=self.cantidad,
            rut=rut,
            paciente=paciente,
            receta=receta_creada,
        )
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        dejar_lista(self.ana)
        turno = registrar_no_retiro(self.ana)
        return turno.preparacion


class PreparadosPendientesTests(ConPendientesTests):
    def test_sin_busqueda_lista_todos_del_mas_antiguo_al_mas_reciente(self):
        primero = self.pendiente("10000001")
        segundo = self.pendiente("10000002")
        Preparacion.objects.filter(pk=segundo.pk).update(lista_en=primero.lista_en - timedelta(minutes=5))
        self.assertEqual(preparados_pendientes(), [segundo, primero])

    def test_busca_por_rut_con_y_sin_puntos(self):
        buscado = self.pendiente("10000001")
        self.pendiente("10000002")
        rut = rut_valido("10000001")
        self.assertEqual(preparados_pendientes(rut), [buscado])
        self.assertEqual(preparados_pendientes(f"10.000.001-{rut[-1]}"), [buscado])
        self.assertEqual(preparados_pendientes(rut.replace("-", "")), [buscado])

    def test_busca_por_apellido_sin_mayusculas_ni_tildes(self):
        buscado = self.pendiente("10000001", apellidos="Núñez Pérez")
        self.pendiente("10000002", apellidos="Soto")
        self.assertEqual(preparados_pendientes("núñez"), [buscado])
        self.assertEqual(preparados_pendientes("NUNEZ"), [buscado])
        self.assertEqual(preparados_pendientes("perez"), [buscado])
        self.assertEqual(preparados_pendientes("Rojas"), [])

    def test_un_rut_fuera_del_padron_solo_se_encuentra_por_rut(self):
        buscado = self.pendiente("10000001", con_paciente=False)
        self.assertEqual(preparados_pendientes(rut_valido("10000001")), [buscado])
        self.assertEqual(preparados_pendientes("Prueba"), [])

    def test_un_pendiente_de_otro_dia_sigue_en_la_lista(self):
        pendiente = self.pendiente("10000001")
        ayer = timezone.localdate() - timedelta(days=1)
        Turno.objects.filter(pk=pendiente.turno_id).update(fecha=ayer)
        self.assertEqual(preparados_pendientes(), [pendiente])

    def test_las_anuladas_y_entregadas_no_aparecen(self):
        self.turno(correlativo=90)
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        registrar_no_retiro(self.ana)  # anulada
        entregado = self.pendiente("10000001")
        entregar_pendiente(entregado.pk, self.beto)
        self.assertEqual(preparados_pendientes(), [])

    def test_entregar_suma_una_entrega_y_conserva_la_fecha_de_preparacion(self):
        pendiente = self.pendiente("10000001", realizadas=2, maximas=6)
        entregado = entregar_pendiente(pendiente.pk, self.beto)
        self.assertEqual(entregado.estado, EstadoPreparacion.ENTREGADA)
        self.assertEqual(entregado.retirada_por, self.beto)
        self.assertIsNotNone(entregado.retirada_en)
        self.assertEqual(entregado.lista_en, pendiente.lista_en)
        self.assertEqual(entregado.no_retirada_en, pendiente.no_retirada_en)
        self.assertEqual(entregado.turno.estado, EstadoTurno.AUSENTE)
        self.assertEqual(entregado.turno.receta.entregas_realizadas, 3)

    def test_sin_receta_cronica_se_entrega_igual(self):
        pendiente = self.pendiente("10000001")
        self.assertEqual(entregar_pendiente(pendiente.pk, self.beto).estado, EstadoPreparacion.ENTREGADA)

    def test_no_se_puede_entregar_dos_veces(self):
        pendiente = self.pendiente("10000001", realizadas=2, maximas=6)
        entregar_pendiente(pendiente.pk, self.beto)
        with self.assertRaisesMessage(ErrorDeAtencion, "ya no está pendiente"):
            entregar_pendiente(pendiente.pk, self.beto)
        pendiente.turno.receta.refresh_from_db()
        self.assertEqual(pendiente.turno.receta.entregas_realizadas, 3)

    def test_con_la_receta_agotada_se_rechaza_y_sigue_pendiente(self):
        pendiente = self.pendiente("10000001", realizadas=5, maximas=6)
        # Entremedio el paciente sacó otro turno y recibió la última entrega.
        RecetaCronica.objects.filter(pk=pendiente.turno.receta_id).update(
            entregas_realizadas=6
        )
        with self.assertRaisesMessage(
            ErrorDeAtencion,
            "La receta ya no tiene entregas disponibles. Consulte con la Química Farmacéutica.",
        ):
            entregar_pendiente(pendiente.pk, self.beto)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, EstadoPreparacion.PENDIENTE_RETIRO)
        self.assertIsNone(pendiente.retirada_en)
        self.assertEqual(preparados_pendientes(), [pendiente])


class PantallaDePreparacionTests(TransicionesTests):
    def rutas(self):
        return [
            ("get", reverse("turnos:preparacion")),
            ("get", reverse("turnos:preparacion_fila")),
            ("post", reverse("turnos:preparacion_lista", args=[1])),
        ]

    def recibir(self, usuario, categoria=Categoria.GENERAL):
        """Un turno llamado por `usuario` y recibido en su ventanilla."""
        self.turno(categoria=categoria, correlativo=self.cantidad + 1)
        llamar_siguiente(usuario)
        iniciar_atencion(usuario)
        return Preparacion.objects.get(turno__atendido_por=usuario, estado=EstadoPreparacion.EN_PREPARACION)

    def test_sin_sesion_redirige_al_login(self):
        for metodo, url in self.rutas():
            respuesta = getattr(self.client, metodo)(url)
            self.assertEqual(respuesta.status_code, 302, url)
            self.assertIn(reverse("cuentas:entrar"), respuesta.url)

    def test_encargado_de_terreno_recibe_403(self):
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        for metodo, url in self.rutas():
            self.assertEqual(getattr(self.client, metodo)(url).status_code, 403, url)

    def test_funcionario_y_qf_la_ven_y_esta_en_la_barra(self):
        for usuario in (self.ana, crear_usuario("22222222-2", Rol.QF)):
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse("turnos:preparacion"))
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, f'href="{reverse("turnos:preparacion")}"')

    def test_sin_preparaciones_lo_dice(self):
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("turnos:preparacion"))
        self.assertContains(respuesta, "No hay recetas en preparación.")
        self.assertContains(respuesta, "No hay recetas listas esperando su entrega.")

    def test_urgencias_primero_y_las_listas_aparte(self):
        general = self.recibir(self.ana)
        urgencia = self.recibir(self.beto, categoria=Categoria.URGENCIA)
        Preparacion.objects.filter(pk=urgencia.pk).update(recibida_en=general.recibida_en + timedelta(minutes=3))
        tercero = crear_usuario("33333333-3", Rol.FUNCIONARIO)
        Ventanilla.objects.create(numero=3, funcionario=tercero)
        lista = self.recibir(tercero)
        marcar_lista(lista.pk, self.ana)

        self.client.force_login(self.ana)
        contenido = self.client.get(reverse("turnos:preparacion_fila")).content.decode()
        en_curso, listas = contenido.split("Listas para entregar")
        self.assertLess(en_curso.index(urgencia.turno.numero), en_curso.index(general.turno.numero))
        self.assertNotIn(lista.turno.numero, en_curso)
        self.assertIn(lista.turno.numero, listas)
        self.assertNotIn("Marcar lista", listas)
        self.assertIn("Ventanilla 1", en_curso)

    def test_cada_fila_lleva_paciente_entrega_y_minutos(self):
        receta, _ = self.receta_con_turno_llamado(entregas_realizadas=2, entregas_maximas=6)
        iniciar_atencion(self.ana)
        Preparacion.objects.update(recibida_en=timezone.now() - timedelta(minutes=4, seconds=10))
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("turnos:preparacion_fila"))
        self.assertContains(respuesta, receta.paciente.nombre_completo)
        self.assertContains(respuesta, "Entrega 3 de 6.")
        self.assertContains(respuesta, "Recibida hace 4 minutos.")

    def test_un_rut_fuera_del_padron_se_muestra_por_rut(self):
        rut = rut_valido("10000001")
        Turno.objects.create(categoria=Categoria.GENERAL, correlativo=1, rut=rut)
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("turnos:preparacion_fila")), f"RUT 10.000.001-{rut[-1]}.")

    def test_marcar_lista_desde_la_pantalla(self):
        preparacion = self.recibir(self.ana)
        self.client.force_login(self.beto)
        respuesta = self.client.post(reverse("turnos:preparacion_lista", args=[preparacion.pk]), follow=True)
        self.assertContains(respuesta, f"La preparación del turno {preparacion.turno.numero} quedó lista.")
        preparacion.refresh_from_db()
        self.assertEqual(preparacion.estado, EstadoPreparacion.LISTA)
        self.assertEqual(preparacion.preparada_por, self.beto)

    def test_marcarla_dos_veces_avisa_sin_fallar(self):
        preparacion = self.recibir(self.ana)
        marcar_lista(preparacion.pk, self.ana)
        self.client.force_login(self.beto)
        respuesta = self.client.post(reverse("turnos:preparacion_lista", args=[preparacion.pk]), follow=True)
        self.assertContains(respuesta, "ya estaba lista")

    def test_el_fragmento_no_renueva_la_sesion_sin_actividad(self):
        self.client.force_login(self.ana)
        clave = self.client.session.session_key
        Session.objects.filter(session_key=clave).update(expire_date=timezone.now() + timedelta(seconds=60))
        url = reverse("turnos:preparacion_fila")
        self.assertEqual(self.client.get(url).status_code, 200)
        restantes = (Session.objects.get(session_key=clave).expire_date - timezone.now()).total_seconds()
        self.assertLess(restantes, 61)
        self.client.get(url, **{META_ACTIVIDAD: "1"})
        restantes = (Session.objects.get(session_key=clave).expire_date - timezone.now()).total_seconds()
        self.assertGreater(restantes, 61)


class PanelConPreparacionTests(TransicionesTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.ana)
        self.turno()
        llamar_siguiente(self.ana)
        iniciar_atencion(self.ana)

    def panel(self):
        return self.client.get(reverse("turnos:atencion"))

    def fragmento(self):
        return self.client.get(reverse("turnos:atencion_preparacion"))

    def test_en_preparacion_el_panel_muestra_el_estado_y_finalizar_deshabilitado(self):
        respuesta = self.panel()
        self.assertContains(respuesta, "En preparación")
        self.assertContains(respuesta, "lista: false")
        self.assertRegex(respuesta.content.decode(), r'!lista"\s+disabled>Finalizar atención')
        self.assertContains(respuesta, "No retiró")
        self.assertContains(respuesta, "la preparación, que aún no está lista, se anula")

    def test_con_la_preparacion_lista_finalizar_queda_habilitado(self):
        dejar_lista(self.ana)
        respuesta = self.panel()
        self.assertContains(respuesta, "La preparación está lista")
        self.assertContains(respuesta, "lista: true")
        self.assertRegex(respuesta.content.decode(), r'!lista"\s+>Finalizar atención')
        self.assertContains(respuesta, "pasa a «Preparados», pendiente de retiro")

    def test_el_fragmento_trae_cada_estado_sin_botones(self):
        respuesta = self.fragmento()
        self.assertContains(respuesta, 'data-estado="en_preparacion"')
        self.assertContains(respuesta, "En preparación")
        self.assertNotContains(respuesta, "<form")
        dejar_lista(self.ana)
        respuesta = self.fragmento()
        self.assertContains(respuesta, 'data-estado="lista"')
        self.assertContains(respuesta, "Lista")
        self.assertNotContains(respuesta, "<form")

    def test_sin_turno_en_atencion_el_fragmento_viene_sin_estado(self):
        registrar_no_retiro(self.ana)
        self.assertContains(self.fragmento(), 'data-estado=""')

    def test_el_fragmento_no_renueva_la_sesion_sin_actividad(self):
        clave = self.client.session.session_key
        Session.objects.filter(session_key=clave).update(expire_date=timezone.now() + timedelta(seconds=60))
        self.assertEqual(self.fragmento().status_code, 200)
        restantes = (Session.objects.get(session_key=clave).expire_date - timezone.now()).total_seconds()
        self.assertLess(restantes, 61)

    def test_finalizar_sin_la_preparacion_lista_avisa(self):
        respuesta = self.client.post(reverse("turnos:finalizar_atencion"), follow=True)
        self.assertContains(respuesta, "La preparación aún no está lista.")
        self.assertEqual(Turno.objects.get().estado, EstadoTurno.EN_ATENCION)

    def test_no_retiro_con_la_preparacion_lista(self):
        dejar_lista(self.ana)
        respuesta = self.client.post(reverse("turnos:registrar_no_retiro"), follow=True)
        self.assertContains(respuesta, "El turno G-001 quedó ausente y su preparado, pendiente de retiro.")
        self.assertEqual(Preparacion.objects.get().estado, EstadoPreparacion.PENDIENTE_RETIRO)

    def test_no_retiro_sin_terminar(self):
        respuesta = self.client.post(reverse("turnos:registrar_no_retiro"), follow=True)
        self.assertContains(respuesta, "El turno G-001 quedó ausente y su preparación se anuló.")
        self.assertEqual(Preparacion.objects.get().estado, EstadoPreparacion.ANULADA)

    def test_no_retiro_solo_por_post(self):
        self.assertEqual(self.client.get(reverse("turnos:registrar_no_retiro")).status_code, 405)

    def test_un_turno_sin_preparacion_muestra_finalizar_como_antes(self):
        Preparacion.objects.all().delete()
        respuesta = self.panel()
        self.assertContains(respuesta, "Finalizar atención")
        self.assertNotContains(respuesta, "No retiró")
        self.assertNotContains(respuesta, "preparacionEnVivo")


class AccesoPanelPreparacionTests(TransicionesTests):
    def test_sin_sesion_redirige_y_encargado_recibe_403(self):
        rutas = [("get", reverse("turnos:atencion_preparacion")), ("post", reverse("turnos:registrar_no_retiro"))]
        for metodo, url in rutas:
            respuesta = getattr(self.client, metodo)(url)
            self.assertEqual(respuesta.status_code, 302, url)
            self.assertIn(reverse("cuentas:entrar"), respuesta.url)
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        for metodo, url in rutas:
            self.assertEqual(getattr(self.client, metodo)(url).status_code, 403, url)


class PantallaDePreparadosTests(ConPendientesTests):
    def buscar(self, busqueda):
        return self.client.post(reverse("turnos:preparados"), {"busqueda": busqueda})

    def test_sin_sesion_redirige_y_encargado_recibe_403(self):
        rutas = [
            ("get", reverse("turnos:preparados")),
            ("post", reverse("turnos:preparados")),
            ("post", reverse("turnos:preparado_entregar", args=[1])),
        ]
        for metodo, url in rutas:
            respuesta = getattr(self.client, metodo)(url)
            self.assertEqual(respuesta.status_code, 302, url)
            self.assertIn(reverse("cuentas:entrar"), respuesta.url)
        self.client.force_login(crear_usuario("22222222-2", Rol.ENCARGADO_TERRENO))
        for metodo, url in rutas:
            self.assertEqual(getattr(self.client, metodo)(url).status_code, 403, url)

    def test_funcionario_y_qf_la_ven_y_esta_en_la_barra(self):
        for usuario in (self.ana, crear_usuario("22222222-2", Rol.QF)):
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse("turnos:preparados"))
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, f'href="{reverse("turnos:preparados")}"')

    def test_sin_pendientes_lo_dice(self):
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("turnos:preparados")), "No hay preparados pendientes de retiro.")

    def test_lista_todos_con_sus_datos(self):
        pendiente = self.pendiente("10000001", apellidos="Núñez", realizadas=2, maximas=6)
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("turnos:preparados"))
        lista_en = timezone.localtime(pendiente.lista_en)
        self.assertContains(respuesta, "Ana Núñez")
        self.assertContains(respuesta, f"10.000.001-{rut_valido('10000001')[-1]}")
        self.assertContains(respuesta, f"Turno {pendiente.turno.numero} del {pendiente.turno.fecha:%d-%m-%Y}.")
        self.assertContains(respuesta, f"Preparado el {lista_en:%d-%m-%Y} a las {lista_en:%H:%M} por Prueba Funcionario.")
        self.assertContains(respuesta, "entrega 3 de 6.")
        self.assertContains(respuesta, 'data-confirmar-titulo="¿Entregar este preparado?"')

    def test_busca_por_post_y_el_rut_no_queda_en_la_url(self):
        self.pendiente("10000001", apellidos="Núñez")
        self.pendiente("10000002", apellidos="Soto")
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("turnos:preparados")), 'method="post"')
        respuesta = self.buscar(rut_valido("10000001"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.request["PATH_INFO"], reverse("turnos:preparados"))
        self.assertEqual(respuesta.request["QUERY_STRING"], "")
        self.assertContains(respuesta, "Ana Núñez")
        self.assertNotContains(respuesta, "Ana Soto")
        self.assertContains(respuesta, "Ver todos los pendientes")

    def test_busca_por_apellido(self):
        self.pendiente("10000001", apellidos="Núñez")
        self.pendiente("10000002", apellidos="Soto")
        self.client.force_login(self.ana)
        respuesta = self.buscar("nunez")
        self.assertContains(respuesta, "Ana Núñez")
        self.assertNotContains(respuesta, "Ana Soto")

    def test_sin_resultados_lo_dice(self):
        self.pendiente("10000001")
        self.client.force_login(self.ana)
        self.assertContains(self.buscar("Rojas"), "No hay preparados pendientes para esa búsqueda.")

    def test_busqueda_vacia_avisa_y_muestra_todos(self):
        self.pendiente("10000001")
        self.client.force_login(self.ana)
        respuesta = self.buscar("")
        self.assertContains(respuesta, "Escriba un RUT o un apellido.")
        self.assertContains(respuesta, "Todos los pendientes")

    def test_flujo_no_retiro_buscar_y_entregar(self):
        paciente = crear_paciente(rut_valido("10000001"), apellidos="Núñez")
        receta = crear_receta(paciente, realizadas=2, maximas=6)
        Turno.objects.create(categoria=Categoria.GENERAL, correlativo=1, rut=paciente.rut, paciente=paciente, receta=receta)
        self.client.force_login(self.ana)
        self.client.post(reverse("turnos:llamar_siguiente"))
        self.client.post(reverse("turnos:iniciar_atencion"))
        dejar_lista(self.ana)
        self.client.post(reverse("turnos:registrar_no_retiro"))

        self.client.force_login(self.beto)
        respuesta = self.buscar("Núñez")
        preparacion = Preparacion.objects.get()
        self.assertContains(respuesta, reverse("turnos:preparado_entregar", args=[preparacion.pk]))
        respuesta = self.client.post(reverse("turnos:preparado_entregar", args=[preparacion.pk]), follow=True)
        self.assertContains(respuesta, "Se entregó el preparado del turno G-001.")
        self.assertContains(respuesta, "No hay preparados pendientes de retiro.")
        preparacion.refresh_from_db()
        self.assertEqual(preparacion.estado, EstadoPreparacion.ENTREGADA)
        self.assertEqual(preparacion.retirada_por, self.beto)
        receta.refresh_from_db()
        self.assertEqual(receta.entregas_realizadas, 3)

    def test_entregar_con_la_receta_agotada_avisa(self):
        pendiente = self.pendiente("10000001", realizadas=5, maximas=6)
        RecetaCronica.objects.update(entregas_realizadas=6)
        self.client.force_login(self.ana)
        respuesta = self.client.post(reverse("turnos:preparado_entregar", args=[pendiente.pk]), follow=True)
        self.assertContains(respuesta, "La receta ya no tiene entregas disponibles.")
        self.assertContains(respuesta, "Ana Prueba")
