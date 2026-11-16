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
