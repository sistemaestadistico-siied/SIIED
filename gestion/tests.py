"""
Pruebas de la Fase 0 del módulo Gestión:
permisos por rol, bitácora y ventanas/prórrogas con zona horaria.
"""
import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from indicadores.models import Organismo, PerfilRecolector

from .models import AccionGestion, ProrrogaVentana, VentanaDiligenciamiento
from .services import registrar_accion, ventana_abierta


def _usuario(username, rol=None, organismo=None, staff=False):
    user = User.objects.create_user(username, f'{username}@x.co', 'Clave-Test-1')
    if staff:
        user.is_staff = True
        user.save()
    if rol:
        PerfilRecolector.objects.create(
            user=user, rol=rol, institucion='X', organismo=organismo)
    return user


class PermisosGestionTests(TestCase):
    def setUp(self):
        self.org = Organismo.objects.create(nombre='Org G', codigo='org-g')
        self.url_hub = reverse('gestion:hub')
        self.url_bitacora = reverse('gestion:bitacora')

    def test_anonimo_va_al_login(self):
        r = self.client.get(self.url_hub)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r['Location'].startswith(reverse('gestion:login')))

    def test_gestor_activo_entra(self):
        _usuario('gestor1', rol='gestor_formularios')
        self.client.force_login(User.objects.get(username='gestor1'))
        self.assertEqual(self.client.get(self.url_hub).status_code, 200)
        self.assertEqual(self.client.get(self.url_bitacora).status_code, 200)

    def test_gestor_inactivo_no_entra(self):
        user = _usuario('gestor2', rol='gestor_formularios')
        user.perfil_recolector.activo = False
        user.perfil_recolector.save()
        self.client.force_login(user)
        r = self.client.get(self.url_hub)
        self.assertEqual(r.status_code, 302)
        self.assertIn('acceso-modulos', r['Location'])

    def test_otros_roles_no_entran(self):
        org = self.org
        for i, rol in enumerate(
                ['delegado', 'validador', 'validador_organismo', 'analista',
                 'diligenciador', 'encuestador', 'recolector']):
            _usuario(f'r{i}', rol=rol, organismo=org if rol in (
                'delegado', 'validador_organismo') else None)
        for i in range(7):
            self.client.force_login(User.objects.get(username=f'r{i}'))
            r = self.client.get(self.url_hub)
            self.assertNotEqual(r.status_code, 200, f'rol {i} entró')

    def test_staff_entra(self):
        _usuario('admin1', staff=True)
        self.client.force_login(User.objects.get(username='admin1'))
        self.assertEqual(self.client.get(self.url_hub).status_code, 200)

    def test_login_rechaza_no_gestor_y_acepta_gestor(self):
        _usuario('del1', rol='delegado', organismo=self.org)
        _usuario('gestor3', rol='gestor_formularios')
        url = reverse('gestion:login')
        r = self.client.post(url, {'username': 'del1',
                                   'password': 'Clave-Test-1'})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(url, {'username': 'gestor3',
                                   'password': 'Clave-Test-1'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], self.url_hub)

    def test_login_respeta_next_local_e_ignora_externo(self):
        _usuario('gestor4', rol='gestor_formularios')
        url = reverse('gestion:login')
        r = self.client.post(url, {'username': 'gestor4',
                                   'password': 'Clave-Test-1',
                                   'next': '/gestion/bitacora/'})
        self.assertEqual(r['Location'], '/gestion/bitacora/')
        self.client.get(reverse('gestion:logout'))
        r = self.client.post(url, {'username': 'gestor4',
                                   'password': 'Clave-Test-1',
                                   'next': 'https://malo.example/'})
        self.assertEqual(r['Location'], self.url_hub)


class BitacoraTests(TestCase):
    def test_registrar_accion_guarda_todo(self):
        user = _usuario('gestor5', rol='gestor_formularios')
        a = registrar_accion(
            modulo='ficed', accion='crear_usuario',
            objeto_tipo='PerfilRecolector', objeto_id=42,
            antes={'rol': 'delegado'}, despues={'rol': 'validador_organismo'},
            motivo='Relevo', usuario=user)
        a.refresh_from_db()
        self.assertEqual(a.usuario, user)
        self.assertEqual(a.accion, 'crear_usuario')
        self.assertEqual(a.antes['rol'], 'delegado')
        self.assertEqual(a.motivo, 'Relevo')
        self.assertIsNone(a.ip)

    def test_bitacora_filtra(self):
        g = _usuario('gestor6', rol='gestor_formularios')
        registrar_accion(modulo='ficed', accion='alta', usuario=g)
        registrar_accion(modulo='taller', accion='baja', usuario=g)
        self.client.force_login(g)
        r = self.client.get(reverse('gestion:bitacora'), {'modulo': 'taller'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'baja')
        self.assertNotContains(r, 'alta')


class VentanaTests(TestCase):
    def setUp(self):
        self.org = Organismo.objects.create(nombre='Org V', codigo='org-v')
        self.org2 = Organismo.objects.create(nombre='Org W', codigo='org-w')
        self.hoy = datetime.date(2026, 11, 16)

    def _ventana(self, apertura=None, cierre=None, activa=True, **kw):
        return VentanaDiligenciamiento.objects.create(
            modulo='ficed', referencia='2025-1',
            fecha_apertura=apertura or self.hoy - datetime.timedelta(days=30),
            fecha_cierre=cierre or self.hoy + datetime.timedelta(days=30),
            activa=activa, **kw)

    def test_sin_ventana_configurada_esta_abierta(self):
        e = ventana_abierta('ficed', 'inexistente', hoy=self.hoy)
        self.assertTrue(e.abierta)
        self.assertFalse(e.configurada)

    def test_dentro_del_rango_abierta(self):
        v = self._ventana()
        e = ventana_abierta('ficed', '2025-1', self.org, hoy=self.hoy)
        self.assertTrue(e.abierta)
        self.assertEqual(e.ventana, v)

    def test_bordes_inclusivos(self):
        v = self._ventana(apertura=self.hoy, cierre=self.hoy)
        self.assertTrue(v.esta_abierta(self.org, hoy=self.hoy))

    def test_antes_de_apertura_y_despues_de_cierre_cerrada(self):
        self._ventana()
        self.assertFalse(ventana_abierta(
            'ficed', '2025-1', self.org,
            hoy=self.hoy - datetime.timedelta(days=31)).abierta)
        e = ventana_abierta('ficed', '2025-1', self.org,
                            hoy=self.hoy + datetime.timedelta(days=31))
        self.assertFalse(e.abierta)
        self.assertTrue(e.mensaje)

    def test_ventana_inactiva_cierra(self):
        self._ventana(activa=False)
        e = ventana_abierta('ficed', '2025-1', self.org, hoy=self.hoy)
        self.assertFalse(e.abierta)

    def test_prorroga_extiende_solo_a_su_organismo(self):
        v = self._ventana(cierre=self.hoy - datetime.timedelta(days=1))
        ProrrogaVentana.objects.create(
            ventana=v, organismo=self.org,
            fecha_cierre_extendida=self.hoy + datetime.timedelta(days=10),
            motivo='Pedido del organismo')
        # Con prórroga: abierto para org, cerrado para org2 y para general
        self.assertTrue(ventana_abierta(
            'ficed', '2025-1', self.org, hoy=self.hoy).abierta)
        self.assertFalse(ventana_abierta(
            'ficed', '2025-1', self.org2, hoy=self.hoy).abierta)
        self.assertFalse(ventana_abierta(
            'ficed', '2025-1', None, hoy=self.hoy).abierta)
        # cierre_vigente refleja la prórroga
        self.assertEqual(v.cierre_vigente(self.org),
                         self.hoy + datetime.timedelta(days=10))

    def test_prorroga_pasada_no_reabre(self):
        v = self._ventana(cierre=self.hoy - datetime.timedelta(days=10))
        ProrrogaVentana.objects.create(
            ventana=v, organismo=self.org,
            fecha_cierre_extendida=self.hoy - datetime.timedelta(days=5),
            motivo='Ya venció')
        self.assertFalse(ventana_abierta(
            'ficed', '2025-1', self.org, hoy=self.hoy).abierta)

    def test_mensaje_cerrado_personalizado(self):
        self._ventana(cierre=self.hoy - datetime.timedelta(days=1),
                      mensaje_cerrado='La vigencia 2025-1 está cerrada.')
        e = ventana_abierta('ficed', '2025-1', self.org, hoy=self.hoy)
        self.assertEqual(e.mensaje, 'La vigencia 2025-1 está cerrada.')

    def test_prorroga_no_puede_ser_anterior_al_cierre(self):
        from django.core.exceptions import ValidationError
        v = self._ventana()
        p = ProrrogaVentana(
            ventana=v, organismo=self.org,
            fecha_cierre_extendida=v.fecha_cierre,
            motivo='x')
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_una_ventana_por_modulo_referencia(self):
        from django.db import IntegrityError, transaction
        self._ventana()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._ventana()

    def test_hub_lista_ventanas(self):
        self._ventana()
        g = _usuario('gestor7', rol='gestor_formularios')
        self.client.force_login(g)
        r = self.client.get(reverse('gestion:hub'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '2025-1')
        self.assertContains(r, 'Abierta')


# =============================================================================
# Fase 1 — Submódulo FICED
# =============================================================================

from django.core.exceptions import ValidationError
from gestion.services.usuarios import (actualizar_usuario_ficed,
                                      crear_usuario_ficed)
from gestion.services.formularios_iced import (reabrir_formulario,
                                              reiniciar_formulario,
                                              restaurar_formulario)
from indicadores.models_iced import ICEDFormulario


class UsuariosFicedServiceTests(TestCase):
    def setUp(self):
        self.org = Organismo.objects.create(nombre='Org F', codigo='org-f')
        self.org2 = Organismo.objects.create(nombre='Org F2', codigo='org-f2')

    def test_crear_delegado_ok(self):
        u, estado = crear_usuario_ficed(
            username='del_etpp_orgf', rol='delegado', subrol='ETPP',
            organismo=self.org, enviar_correo=False)
        self.assertTrue(u.pk)
        self.assertEqual(u.perfil_recolector.subrol_ficed, 'ETPP')
        self.assertEqual(estado, 'omitido')
        # Sin correo real: la clave quedó inutilizable
        self.assertFalse(u.has_usable_password())

    def test_delegado_exige_organismo(self):
        with self.assertRaises(ValidationError):
            crear_usuario_ficed(username='d2', rol='delegado',
                                subrol='ETPP', organismo=None)

    def test_validador_exige_organismo(self):
        with self.assertRaises(ValidationError):
            crear_usuario_ficed(username='v2', rol='validador_organismo',
                                subrol='', organismo=None)

    def test_subrol_solo_delegados(self):
        with self.assertRaises(ValidationError):
            crear_usuario_ficed(username='v3', rol='validador_organismo',
                                subrol='ETPP', organismo=self.org)

    def test_segundo_validador_rechazado(self):
        crear_usuario_ficed(username='val1', rol='validador_organismo',
                            subrol='', organismo=self.org)
        with self.assertRaises(ValidationError):
            crear_usuario_ficed(username='val2', rol='validador_organismo',
                                subrol='', organismo=self.org)

    def test_segundo_delegado_mismo_subrol_rechazado(self):
        crear_usuario_ficed(username='d_etpp', rol='delegado', subrol='ETPP',
                            organismo=self.org)
        with self.assertRaises(ValidationError):
            crear_usuario_ficed(username='d_etpp2', rol='delegado',
                                subrol='ETPP', organismo=self.org)
        # Otro subrol u otro organismo sí pueden
        crear_usuario_ficed(username='d_etobs', rol='delegado', subrol='ETOBS',
                            organismo=self.org)
        crear_usuario_ficed(username='d_etpp2', rol='delegado', subrol='ETPP',
                            organismo=self.org2)

    def test_editar_marca_cambios(self):
        u, _ = crear_usuario_ficed(username='d_e', rol='delegado',
                                   subrol='ETGIE', organismo=self.org,
                                   email='a@x.co', enviar_correo=False)
        antes, despues, cambios, _ = actualizar_usuario_ficed(
            u, subrol='ETSGC', aviso_correo=False)
        self.assertEqual(antes['subrol_ficed'], 'ETGIE')
        self.assertEqual(despues['subrol_ficed'], 'ETSGC')
        self.assertTrue(any('Equipo' in c[0] for c in cambios))


class FormulariosFicedServiceTests(TestCase):
    def setUp(self):
        self.org = Organismo.objects.create(nombre='Org R', codigo='org-r')
        self.u = _usuario('del_r', rol='delegado', organismo=self.org)
        self.f = ICEDFormulario.objects.create(
            organismo=self.org, periodo='2026', equipo='ETPP',
            estado='enviado', usuario_diligencia=self.u,
            respuestas_a={'p1': 'x'})

    def test_reabrir_enviado(self):
        antes, despues = reabrir_formulario(self.f)
        self.assertEqual(antes['estado'], 'enviado')
        self.assertEqual(despues['estado'], 'borrador')
        self.assertEqual(
            ICEDFormulario.objects.get(pk=self.f.pk).estado, 'borrador')

    def test_reabrir_bloquea_validado(self):
        self.f.estado = 'validado'
        self.f.save()
        with self.assertRaises(ValidationError):
            reabrir_formulario(self.f)

    def test_reiniciar_borra_y_devuelve_copia(self):
        copia = reiniciar_formulario(self.f)
        self.assertFalse(ICEDFormulario.objects.filter(pk=self.f.pk).exists())
        self.assertEqual(copia['respuestas_a'], {'p1': 'x'})
        self.assertEqual(copia['equipo'], 'ETPP')

    def test_reiniciar_bloqueado_por_consolidado(self):
        ICEDFormulario.objects.create(
            organismo=self.org, periodo='2026', equipo='',
            estado='validado', usuario_diligencia=self.u)
        with self.assertRaises(ValidationError):
            reiniciar_formulario(self.f)

    def test_restaurar_desde_copia(self):
        copia = reiniciar_formulario(self.f)
        nuevo = restaurar_formulario(copia)
        self.assertEqual(nuevo.respuestas_a, {'p1': 'x'})
        self.assertEqual(nuevo.estado, 'enviado')
        # No restaura si ya existe uno nuevo
        with self.assertRaises(ValidationError):
            restaurar_formulario(copia)


class VistasFicedTests(TestCase):
    def setUp(self):
        self.g = _usuario('gestor_f', rol='gestor_formularios')
        self.client.force_login(self.g)
        self.org = Organismo.objects.create(nombre='Org Gf', codigo='org-gf')
        self.u = _usuario('del_gf', rol='delegado', organismo=self.org)

    def test_dashboard_entra(self):
        r = self.client.get(reverse('gestion:ficed_dashboard'))
        self.assertEqual(r.status_code, 200)

    def test_usuarios_lista_y_matriz(self):
        r = self.client.get(reverse('gestion:ficed_usuarios'))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse('gestion:ficed_usuarios'),
                            {'vista': 'matriz'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'sin asignar')

    def test_crear_usuario_por_vista(self):
        r = self.client.post(reverse('gestion:ficed_usuario_crear'), {
            'username': 'nuevo_f', 'rol': 'delegado', 'subrol_ficed': 'ETPP',
            'organismo': str(self.org.pk), 'activo': '1',
            'first_name': 'N', 'last_name': 'U', 'email': ''})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username='nuevo_f').exists())
        self.assertTrue(AccionGestion.objects.filter(
            accion='crear_usuario', modulo='ficed').exists())

    def test_desactivar_y_reactivar(self):
        u = self.u
        url = reverse('gestion:ficed_usuario_accion', args=[u.pk])
        self.client.post(url, {'accion': 'desactivar'})
        u.refresh_from_db()
        self.assertFalse(u.perfil_recolector.activo)
        self.assertFalse(u.is_active)
        self.client.post(url, {'accion': 'activar'})
        u.refresh_from_db()
        self.assertTrue(u.perfil_recolector.activo)

    def test_organismo_flags(self):
        r = self.client.post(
            reverse('gestion:ficed_organismo_flags', args=[self.org.pk]),
            {'sin_pp': '1', 'motivo': 'No publican'})
        self.assertEqual(r.status_code, 302)
        self.org.refresh_from_db()
        self.assertTrue(self.org.sin_pp)
        self.assertFalse(self.org.sin_obs)
        self.assertTrue(AccionGestion.objects.filter(
            accion='editar_organismo_flags',
            objeto_id=str(self.org.pk)).exists())

    def test_reiniciar_requiere_nombre_organismo(self):
        f = ICEDFormulario.objects.create(
            organismo=self.org, periodo='2026', equipo='ETGIE',
            estado='borrador', usuario_diligencia=self.u)
        url = reverse('gestion:ficed_formulario_accion', args=[f.pk])
        self.client.post(url, {'accion': 'reiniciar',
                               'confirmar': 'mal', 'motivo': 'x'})
        self.assertTrue(ICEDFormulario.objects.filter(pk=f.pk).exists())
        self.client.post(url, {'accion': 'reiniciar',
                               'confirmar': self.org.nombre,
                               'motivo': 'reinicio real'})
        self.assertFalse(ICEDFormulario.objects.filter(pk=f.pk).exists())
        reg = AccionGestion.objects.get(accion='reiniciar_formulario')
        self.assertEqual(reg.antes['equipo'], 'ETGIE')
        self.assertEqual(reg.motivo, 'reinicio real')

    def test_ventana_guardar_y_prorroga(self):
        r = self.client.post(reverse('gestion:ficed_ventana_guardar'), {
            'referencia': '2026', 'fecha_apertura': '2026-01-01',
            'fecha_cierre': '2026-03-31', 'activa': '1'})
        self.assertEqual(r.status_code, 302)
        v = VentanaDiligenciamiento.objects.get(modulo='ficed',
                                                referencia='2026')
        self.assertTrue(v.activa)
        r = self.client.post(
            reverse('gestion:ficed_prorroga', args=[v.pk]), {
                'organismo': str(self.org.pk),
                'fecha_cierre_extendida': '2026-05-31',
                'motivo': 'Pedido'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ProrrogaVentana.objects.filter(
            ventana=v, organismo=self.org).exists())


# =============================================================================
# Fase 2 — Submódulo Taller
# =============================================================================

from gestion.services import taller as st
from indicadores.models import EquipoOrganismo, Suborganismo
from indicadores.models_taller import InscripcionTaller


class TallerServiceTests(TestCase):
    def setUp(self):
        self.org = Organismo.objects.create(nombre='Org T', codigo='org-t')
        self.org2 = Organismo.objects.create(nombre='Org T2', codigo='org-t2')
        self.sub = Suborganismo.objects.create(
            organismo=self.org, nombre='Sec Tecnica', codigo='sec-tec')
        self.eq = EquipoOrganismo.objects.create(
            suborganismo=self.sub, nombre='Equipo Datos', codigo='eq-datos')
        self.sub2 = Suborganismo.objects.create(
            organismo=self.org2, nombre='Sec 2', codigo='sec-2')
        self.eq2 = EquipoOrganismo.objects.create(
            suborganismo=self.sub2, nombre='Eq Otro', codigo='eq-otro')

    def test_crear_usuario_taller_ok(self):
        u, estado = st.crear_usuario_taller(
            username='persona.x', rol='delegado', organismo=self.org,
            equipo=self.eq, edicion=2026, enviar_correo=False)
        p = u.perfil_recolector
        self.assertEqual(p.equipo_taller, self.eq)
        self.assertEqual(p.equipo_taller_edicion, 2026)
        self.assertEqual(p.rol, 'delegado')

    def test_equipo_de_otro_organismo_rechazado(self):
        with self.assertRaises(ValidationError):
            st.crear_usuario_taller(
                username='persona.y', rol='delegado', organismo=self.org,
                equipo=self.eq2, enviar_correo=False)

    def test_separacion_cuentas_ficed(self):
        u, _ = crear_usuario_ficed(username='del_ficed', rol='delegado',
                                   subrol='ETPP', organismo=self.org,
                                   enviar_correo=False)
        with self.assertRaises(ValidationError):
            st.asignar_equipo_taller(u.perfil_recolector, self.eq, 2026)

    def test_asignar_equipo_confirma_edicion(self):
        u, _ = st.crear_usuario_taller(
            username='persona.z', rol='delegado', organismo=self.org,
            enviar_correo=False)
        antes, despues = st.asignar_equipo_taller(
            u.perfil_recolector, self.eq, 2027)
        self.assertIsNone(antes['equipo_taller_id'])
        self.assertEqual(despues['equipo_taller_id'], self.eq.pk)
        self.assertEqual(despues['equipo_taller_edicion'], 2027)

    def test_desactivar_estructura(self):
        st.desactivar_equipo(self.eq)
        self.eq.refresh_from_db()
        self.assertFalse(self.eq.activo)
        st.desactivar_suborganismo(self.sub)
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.activo)

    def test_reabrir_inscripcion(self):
        u = _usuario('del_t1', rol='delegado', organismo=self.org)
        ins = InscripcionTaller.objects.create(
            user=u, organismo=self.org, edicion=2026,
            nombre_completo='X', correo='x@x.co',
            estado='completada')
        antes, despues = st.reabrir_inscripcion(ins)
        self.assertEqual(despues['estado'], 'en_progreso')

    def test_reiniciar_inscripcion_copia(self):
        u = _usuario('del_t2', rol='delegado', organismo=self.org)
        ins = InscripcionTaller.objects.create(
            user=u, organismo=self.org, edicion=2026,
            nombre_completo='Y', correo='y@x.co')
        copia = st.reiniciar_inscripcion(ins)
        self.assertFalse(InscripcionTaller.objects.filter(pk=ins.pk).exists())
        self.assertEqual(copia['nombre_completo'], 'Y')

    def test_reasignar_equipo_integridad(self):
        u = _usuario('del_t3', rol='delegado', organismo=self.org)
        ins = InscripcionTaller.objects.create(
            user=u, organismo=self.org, edicion=2026,
            nombre_completo='Z', correo='z@x.co',
            equipo_responsable='escrito a mano')
        # Equipo de otro organismo: rechazado
        with self.assertRaises(ValidationError):
            st.reasignar_inscripcion(ins, equipo=self.eq2)
        # Equipo del organismo: ok
        antes, despues = st.reasignar_inscripcion(ins, equipo=self.eq)
        self.assertEqual(despues['equipo_id'], self.eq.pk)

    def test_conciliacion_lista_sin_equipo(self):
        u = _usuario('del_t4', rol='delegado', organismo=self.org)
        InscripcionTaller.objects.create(
            user=u, organismo=self.org, edicion=2026,
            nombre_completo='W', correo='w@x.co',
            equipo_responsable='texto sin normalizar')
        InscripcionTaller.objects.create(
            user=u, organismo=self.org, edicion=2026,
            nombre_completo='V', correo='v@x.co', equipo=self.eq)
        self.assertEqual(st.inscripciones_sin_equipo().count(), 1)


class VistasTallerTests(TestCase):
    def setUp(self):
        self.g = _usuario('gestor_t', rol='gestor_formularios')
        self.client.force_login(self.g)
        self.org = Organismo.objects.create(nombre='Org Tv', codigo='org-tv')
        self.sub = Suborganismo.objects.create(
            organismo=self.org, nombre='Sub X', codigo='sub-x')
        self.eq = EquipoOrganismo.objects.create(
            suborganismo=self.sub, nombre='Eq X', codigo='eq-x')

    def test_vistas_entran(self):
        for url in ('gestion:taller_usuarios', 'gestion:taller_estructura',
                    'gestion:taller_inscripciones', 'gestion:taller_ventanas',
                    'gestion:taller_conciliacion'):
            r = self.client.get(reverse(url))
            self.assertEqual(r.status_code, 200, url)

    def test_dashboard_redirige_a_analitica(self):
        r = self.client.get(reverse('gestion:taller_dashboard'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('taller/reportes', r['Location'])

    def test_gestor_accede_a_reportes(self):
        r = self.client.get(reverse('indicadores:analitica_taller_reportes'))
        self.assertEqual(r.status_code, 200)

    def test_crear_usuario_taller_por_vista(self):
        r = self.client.post(reverse('gestion:taller_usuario_crear'), {
            'username': 'persona.nueva', 'rol': 'delegado',
            'organismo': str(self.org.pk), 'equipo': str(self.eq.pk),
            'edicion': '2026', 'activo': '1', 'first_name': 'P',
            'last_name': 'N', 'email': ''})
        self.assertEqual(r.status_code, 302)
        p = User.objects.get(username='persona.nueva').perfil_recolector
        self.assertEqual(p.equipo_taller_id, self.eq.pk)
        self.assertTrue(AccionGestion.objects.filter(
            accion='crear_usuario', modulo='taller').exists())

    def test_crear_equipo_por_vista(self):
        r = self.client.post(reverse('gestion:taller_estructura_accion'), {
            'accion': 'crear_equipo', 'suborganismo': str(self.sub.pk),
            'nombre': 'Eq Nuevo'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(EquipoOrganismo.objects.filter(
            suborganismo=self.sub, nombre='Eq Nuevo').exists())

    def test_api_cascada(self):
        r = self.client.get(
            reverse('gestion:taller_api_subs', args=[self.org.pk]))
        self.assertEqual(r.json()['suborganismos'][0]['nombre'], 'Sub X')
        r = self.client.get(
            reverse('gestion:taller_api_equipos', args=[self.sub.pk]))
        self.assertEqual(r.json()['equipos'][0]['nombre'], 'Eq X')

    def test_ventana_taller_guardar(self):
        r = self.client.post(reverse('gestion:taller_ventana_guardar'), {
            'referencia': '2026', 'fecha_apertura': '2026-01-01',
            'fecha_cierre': '2026-12-31', 'activa': '1'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(VentanaDiligenciamiento.objects.filter(
            modulo='taller', referencia='2026').exists())
