from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from indicadores.cuentas import emitir_password_temporal
from indicadores.models import Organismo, PerfilRecolector


def _usuario(username, rol='delegado', debe_cambiar=False, email='u@x.co'):
    user = User.objects.create_user(username, email, 'Clave-Inicial-2026')
    PerfilRecolector.objects.create(
        user=user, rol=rol, institucion='X',
        debe_cambiar_password=debe_cambiar)
    return user


class RolesNuevosTests(TestCase):
    def test_metodos_de_rol(self):
        for rol, metodo in [('gestor_formularios', 'es_gestor'),
                            ('diligenciador', 'es_diligenciador'),
                            ('encuestador', 'es_encuestador')]:
            perfil = _usuario(f'u_{rol}', rol=rol).perfil_recolector
            self.assertTrue(getattr(perfil, metodo)())
            perfil.activo = False
            self.assertFalse(getattr(perfil, metodo)())

    def test_gestor_no_es_validador_ni_delegado(self):
        perfil = _usuario('g', rol='gestor_formularios').perfil_recolector
        self.assertFalse(perfil.es_validador())
        self.assertFalse(perfil.es_delegado())


class UnicidadRolesTests(TestCase):
    def setUp(self):
        self.org = Organismo.objects.create(nombre='Org Test', codigo='org-test')
        self.org2 = Organismo.objects.create(nombre='Org Dos', codigo='org-dos')

    def _perfil(self, username, rol, organismo, subrol='', activo=True):
        user = User.objects.create_user(username, f'{username}@x.co', 'x')
        return PerfilRecolector(
            user=user, rol=rol, institucion='X', organismo=organismo,
            subrol_ficed=subrol, activo=activo)

    def test_un_solo_validador_activo_por_organismo(self):
        self._perfil('v1', 'validador_organismo', self.org).save()
        segundo = self._perfil('v2', 'validador_organismo', self.org)
        with self.assertRaises(ValidationError):
            segundo.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            segundo.save()

    def test_validador_inactivo_u_otro_organismo_permitido(self):
        self._perfil('v1', 'validador_organismo', self.org).save()
        self._perfil('v2', 'validador_organismo', self.org,
                     activo=False).save()
        self._perfil('v3', 'validador_organismo', self.org2).save()
        self.assertEqual(PerfilRecolector.objects.filter(
            rol='validador_organismo').count(), 3)

    def test_un_delegado_activo_por_subrol(self):
        self._perfil('d1', 'delegado', self.org, 'ETPP').save()
        self._perfil('d2', 'delegado', self.org, 'ETOBS').save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._perfil('d3', 'delegado', self.org, 'ETPP').save()

    def test_delegados_sin_subrol_no_se_restringen(self):
        self._perfil('d1', 'delegado', self.org).save()
        self._perfil('d2', 'delegado', self.org).save()
        self.assertEqual(PerfilRecolector.objects.filter(
            rol='delegado', organismo=self.org).count(), 2)


class EmitirPasswordTemporalTests(TestCase):
    @mock.patch('indicadores.cuentas.notificar_acceso_usuario',
                return_value=True)
    def test_envio_exitoso_guarda_y_marca(self, _m):
        user = _usuario('a')
        self.assertEqual(emitir_password_temporal(user), 'enviado')
        user.refresh_from_db()
        self.assertFalse(user.check_password('Clave-Inicial-2026'))
        self.assertTrue(user.perfil_recolector.debe_cambiar_password)

    @mock.patch('indicadores.cuentas.notificar_acceso_usuario',
                return_value=False)
    def test_envio_fallido_no_toca_nada(self, _m):
        user = _usuario('b')
        self.assertEqual(emitir_password_temporal(user), 'fallido')
        user.refresh_from_db()
        self.assertTrue(user.check_password('Clave-Inicial-2026'))
        self.assertFalse(
            PerfilRecolector.objects.get(user=user).debe_cambiar_password)

    def test_sin_correo(self):
        user = _usuario('c', email='')
        self.assertEqual(emitir_password_temporal(user), 'sin_correo')


class CambioPasswordObligatorioTests(TestCase):
    def setUp(self):
        self.url = reverse('indicadores:cuenta_cambiar_contrasena')

    def test_redirige_si_tiene_temporal(self):
        user = _usuario('d', debe_cambiar=True)
        self.client.force_login(user)
        r = self.client.get(reverse('indicadores:acceso_modulos'))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r['Location'].startswith(self.url))

    def test_json_recibe_403(self):
        user = _usuario('e', debe_cambiar=True)
        self.client.force_login(user)
        r = self.client.get(reverse('indicadores:acceso_modulos'),
                            HTTP_ACCEPT='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['redirect'], self.url)

    def test_vista_y_logout_quedan_libres(self):
        user = _usuario('f', debe_cambiar=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        r = self.client.get(reverse('indicadores:logout'))
        self.assertNotIn(self.url, r.get('Location', ''))

    def test_sin_temporal_no_redirige(self):
        user = _usuario('g2')
        self.client.force_login(user)
        r = self.client.get(reverse('indicadores:acceso_modulos'))
        self.assertEqual(r.status_code, 200)

    def test_cambiar_limpia_flag_y_mantiene_sesion(self):
        user = _usuario('h', debe_cambiar=True)
        self.client.force_login(user)
        r = self.client.post(self.url, {
            'old_password': 'Clave-Inicial-2026',
            'new_password1': 'Nueva-Clave-Segura-77',
            'new_password2': 'Nueva-Clave-Segura-77',
            'next': reverse('indicadores:acceso_modulos'),
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], reverse('indicadores:acceso_modulos'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('Nueva-Clave-Segura-77'))
        self.assertFalse(user.perfil_recolector.debe_cambiar_password)
        r = self.client.get(reverse('indicadores:acceso_modulos'))
        self.assertEqual(r.status_code, 200)

    def test_next_externo_se_ignora(self):
        user = _usuario('i', debe_cambiar=True)
        self.client.force_login(user)
        r = self.client.post(self.url, {
            'old_password': 'Clave-Inicial-2026',
            'new_password1': 'Nueva-Clave-Segura-77',
            'new_password2': 'Nueva-Clave-Segura-77',
            'next': 'https://malicioso.example/',
        })
        self.assertEqual(r['Location'], reverse('indicadores:acceso_modulos'))
