# -*- coding: utf-8 -*-
"""Tests del módulo Encuestas."""
import json

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

_EXP = '2099-01-01'


from .models import (Asignacion, Envio, Formulario, Invitacion, Opcion,
                     Pregunta, Respondiente, RespuestaItem, Seccion)
from .services import envios as se
from .services import exportar as sx
from .services import formularios as sf


def _formulario(**kw):
    f = sf.crear_formulario(
        titulo=kw.pop('titulo', 'Encuesta X'),
        tipo=kw.pop('tipo', 'encuesta'))
    for k, v in kw.items():
        setattr(f, k, v)
    f.save()
    return f


def _con_pregunta(f, tipo='texto_corto', enunciado='¿X?',
                  obligatoria=False, **kw):
    sec = f.secciones.first()
    p = sf.agregar_pregunta(sec, tipo=tipo, enunciado=enunciado,
                            obligatoria=obligatoria, **kw)
    return p


def _ficha_minima(f, **kw):
    """Ficha metodológica con la metadata mínima para publicar."""
    from .services import ficha as sficha
    datos = dict(
        tipo_operacion='censo', entidad_responsable='SIIED',
        objetivo_general='Medir X.', unidad_observacion='Persona',
        poblacion_objetivo='Usuarios del sistema',
        cobertura_geografica='Departamental',
        periodo_referencia='2026', periodo_recoleccion='nov-dic 2026',
        metodos_recoleccion=['autodiligenciamiento'])
    datos.update(kw)
    fi = sficha.ficha_de(f)
    for k, v in datos.items():
        setattr(fi, k, v)
    fi.save()
    return fi


class CicloVidaTests(TestCase):
    def test_crear_y_estructura(self):
        f = _formulario()
        self.assertEqual(f.secciones.count(), 1)
        self.assertFalse(f.estructura_bloqueada)

    def test_publicar_exige_pregunta(self):
        f = _formulario()
        _ficha_minima(f)
        with self.assertRaises(ValidationError):
            sf.publicar(f)
        _con_pregunta(f)
        sf.publicar(f)
        self.assertEqual(f.estado, 'publicado')

    def test_publicar_exige_ficha(self):
        """Sin ficha mínima no se puede publicar (NTC §4.4.2)."""
        f = _formulario()
        _con_pregunta(f)
        with self.assertRaises(ValidationError):
            sf.publicar(f)
        _ficha_minima(f)
        sf.publicar(f)
        self.assertEqual(f.estado, 'publicado')

    def test_cerrar_y_reabrir(self):
        f = _formulario()
        _con_pregunta(f)
        _ficha_minima(f)
        sf.publicar(f)
        sf.cerrar(f)
        self.assertFalse(f.acepta_respuestas)
        sf.reabrir(f)
        self.assertTrue(f.acepta_respuestas)

    def test_duplicar_clona_estructura(self):
        f = _formulario()
        p = _con_pregunta(f, 'seleccion_unica')
        Opcion.objects.create(pregunta=p, orden=0, texto='A')
        Opcion.objects.create(pregunta=p, orden=1, texto='B', es_otro=True)
        nuevo = sf.duplicar(f)
        self.assertEqual(nuevo.estado, 'borrador')
        p2 = nuevo.secciones.first().preguntas.first()
        self.assertEqual(p2.opciones.count(), 2)
        self.assertNotEqual(nuevo.slug, f.slug)

    def test_estructura_bloqueada_con_respuestas(self):
        f = _formulario()
        _con_pregunta(f)
        f.estado = 'publicado'
        f.save()
        Envio.objects.create(formulario=f, modo='publico', estado='enviado')
        self.assertTrue(f.estructura_bloqueada)
        with self.assertRaises(ValidationError):
            sf.agregar_pregunta(f.secciones.first(), tipo='numero',
                                enunciado='x')


class EnviosTests(TestCase):
    def setUp(self):
        self.f = _formulario(
            modos_diligenciamiento=['publico', 'autodiligenciado'])
        self.p = _con_pregunta(self.f, obligatoria=True)
        self.f.estado = 'publicado'
        self.f.save()
        self.u = User.objects.create_user('del', password='x')

    def test_crear_envio_publico(self):
        e = se.crear_envio(self.f, modo='publico')
        self.assertEqual(e.estado, 'borrador')

    def test_enviar_valida_obligatorias(self):
        e = se.crear_envio(self.f, modo='publico')

        class _Post:
            def get(self, k, d=None): return d
            def getlist(self, k): return []
        with self.assertRaises(se.ErroresEnvio):
            se.enviar(e, _Post())

    def test_guardar_y_enviar(self):
        e = se.crear_envio(self.f, modo='publico')

        class _Post:
            def get(self, k, d=None):
                return 'respuesta' if k == f'p_{self.p.pk}' else d
            def getlist(self, k):
                return ['respuesta']
            p = self
        post = _Post(); post.p = self.p
        # hack simple: dict-like
        post = {f'p_{self.p.pk}': 'respuesta'}
        # _guardar_respuestas usa post.get/getlist — simular con un mini QueryDict
        from django.http import QueryDict
        q = QueryDict('', mutable=True)
        q[f'p_{self.p.pk}'] = 'respuesta'
        se.enviar(e, q)
        e.refresh_from_db()
        self.assertEqual(e.estado, 'enviado')
        self.assertTrue(RespuestaItem.objects.filter(
            envio=e, pregunta=self.p, valor='respuesta').exists())

    def test_una_respuesta_por_respondiente(self):
        se.crear_envio(self.f, modo='publico')
        # Segundo envío del mismo modo: devuelve el borrador existente
        e2 = se.crear_envio(self.f, modo='publico', usuario=self.u)
        self.assertIsNotNone(e2)

    def test_no_acepta_cuando_cerrado(self):
        self.f.estado = 'cerrado'
        self.f.save()
        with self.assertRaises(ValidationError):
            se.crear_envio(self.f, modo='publico')

    def test_asignacion_diligenciador(self):
        Asignacion.objects.create(formulario=self.f, usuario=self.u,
                                  rol='diligenciador')
        e = se.crear_envio(self.f, modo='auto', usuario=self.u)
        self.assertEqual(e.diligenciado_por, self.u)

    def test_sin_asignacion_rechaza(self):
        with self.assertRaises(ValidationError):
            se.crear_envio(self.f, modo='auto', usuario=self.u)


class ExportacionTests(TestCase):
    def test_csv_pivot(self):
        f = _formulario()
        p = _con_pregunta(f, enunciado='¿A?', codigo='P1')
        e = Envio.objects.create(formulario=f, modo='publico',
                                 estado='enviado')
        RespuestaItem.objects.create(envio=e, pregunta=p, valor='x')
        csv = sx.csv_pivot(f)
        self.assertIn('P1', csv)
        self.assertTrue(csv.rstrip().endswith(',x'))

    def test_resumen_conteos(self):
        f = _formulario()
        p = _con_pregunta(f, 'seleccion_unica', enunciado='¿Elija?')
        o = Opcion.objects.create(pregunta=p, orden=0, texto='OpA')
        e = Envio.objects.create(formulario=f, modo='publico',
                                 estado='enviado')
        RespuestaItem.objects.create(
            envio=e, pregunta=p,
            valor={'opcion_id': o.pk, 'texto': 'OpA'})
        resumen, _ = sx.resumen(f)
        self.assertEqual(resumen[0]['filas'][0]['texto'], 'OpA')
        self.assertEqual(resumen[0]['respondidas'], 1)


class VistasEncuestasTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.g = User.objects.create_user('gestor_enc', password='x')
        from indicadores.models import PerfilRecolector
        PerfilRecolector.objects.create(user=self.g,
                                        rol='gestor_formularios')
        self.client.force_login(self.g)

    def test_lista_gestor(self):
        r = self.client.get(reverse('gestion:encuestas_lista'))
        self.assertEqual(r.status_code, 200)

    def test_crear_por_vista(self):
        r = self.client.post(reverse('gestion:encuestas_crear'), {
            'titulo': 'Encuesta Test', 'tipo': 'encuesta'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Formulario.objects.filter(
            titulo='Encuesta Test').exists())

    def test_constructor_200(self):
        f = _formulario()
        r = self.client.get(reverse('gestion:encuestas_constructor',
                                    args=[f.pk]))
        self.assertEqual(r.status_code, 200)

    def test_responder_publico_publicado(self):
        f = _formulario(modos_diligenciamiento=['publico'])
        _con_pregunta(f)
        f.estado = 'publicado'
        f.save()
        r = self.client.get(
            reverse('encuestas:responder_publico', args=[f.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, f.titulo)

    def test_publico_no_acepta_si_cerrado(self):
        f = _formulario(modos_diligenciamiento=['publico'])
        _con_pregunta(f)
        f.estado = 'cerrado'
        f.save()
        r = self.client.get(
            reverse('encuestas:responder_publico', args=[f.slug]))
        self.assertContains(r, 'no está aceptando', status_code=200)


# =============================================================================
# Captura offline del encuestador
# =============================================================================

from .services import offline as so


class OfflineTests(TestCase):
    def setUp(self):
        self.f = _formulario(
            modos_diligenciamiento=['encuestador'],
            modo_identificacion='identificado')
        self.p = _con_pregunta(self.f, obligatoria=True, codigo='P1')
        self.f.estado = 'publicado'
        self.f.save()
        self.u = User.objects.create_user('encuestador1', password='x')
        Asignacion.objects.create(formulario=self.f, usuario=self.u,
                                  rol='encuestador')

    def _envio_payload(self, oid='uuid-1', respuestas=None):
        return {
            'offline_id': oid,
            'respondiente': {
                'nombres': 'Ana', 'apellidos': 'Ríos',
                'documento': '123', 'autoriza_datos': True},
            'respuestas': respuestas if respuestas is not None
            else {str(self.p.pk): 'respuesta'},
        }

    def test_token_hmac_valido(self):
        token = so.sincro_token(self.f, self.u, _EXP)
        self.assertTrue(so.verificar_sincro(token, self.f, self.u, _EXP))
        self.assertFalse(so.verificar_sincro('otro', self.f, self.u, _EXP))
        otro = User.objects.create_user('otro_e')
        self.assertFalse(so.verificar_sincro(token, self.f, otro, _EXP))

    def test_importar_ok(self):
        token = so.sincro_token(self.f, self.u, _EXP)
        res = so.importar_envios(self.f, self.u, token, [self._envio_payload()], expira=_EXP)
        self.assertEqual(res[0]['estado'], 'importado')
        e = Envio.objects.get(offline_id='uuid-1')
        self.assertEqual(e.estado, 'enviado')
        self.assertEqual(e.modo, 'encuestador')
        self.assertEqual(e.diligenciado_por, self.u)
        self.assertEqual(e.respondiente.documento, '123')

    def test_importar_dedup(self):
        token = so.sincro_token(self.f, self.u, _EXP)
        so.importar_envios(self.f, self.u, token, [self._envio_payload()], expira=_EXP)
        res = so.importar_envios(self.f, self.u, token, [self._envio_payload()], expira=_EXP)
        self.assertEqual(res[0]['estado'], 'duplicado')
        self.assertEqual(Envio.objects.count(), 1)

    def test_importar_respuesta_invalida(self):
        token = so.sincro_token(self.f, self.u, _EXP)
        res = so.importar_envios(self.f, self.u, token, [self._envio_payload(oid='uuid-bad', respuestas={})], expira=_EXP)
        self.assertEqual(res[0]['estado'], 'error')
        self.assertFalse(Envio.objects.exists())
        self.assertFalse(Respondiente.objects.exists())

    def test_sin_asignacion_rechaza(self):
        otro = User.objects.create_user('sin_asig')
        token = so.sincro_token(self.f, otro, _EXP)
        with self.assertRaises(ValidationError):
            so.importar_envios(self.f, otro, token, [self._envio_payload()], expira=_EXP)

    def test_sincronizar_endpoint(self):
        from django.http import QueryDict
        token = so.sincro_token(self.f, self.u, _EXP)
        payload = json.dumps({
            'sincro_token': token, 'sincro_expira': _EXP,
            'formulario_id': self.f.pk,
            'encuestador_id': self.u.pk,
            'envios': [self._envio_payload(oid='uuid-end')]})
        r = Client().post(reverse('encuestas:sincronizar'),
                          data=payload, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['resultados'][0]['estado'], 'importado')

    def test_sincronizar_token_malo(self):
        payload = json.dumps({
            'sincro_token': 'malo', 'formulario_id': self.f.pk,
            'encuestador_id': self.u.pk,
            'envios': [self._envio_payload()]})
        r = Client().post(reverse('encuestas:sincronizar'),
                          data=payload, content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_descargar_offline(self):
        self.client.force_login(self.u)
        r = self.client.get(reverse('encuestas:descargar_offline',
                                    args=[self.f.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertIn(b'sincro_token', r.content)
        self.assertIn(b'localStorage', r.content)

    def test_descargar_sin_asignacion(self):
        otro = User.objects.create_user('sin_a')
        self.client.force_login(otro)
        r = self.client.get(reverse('encuestas:descargar_offline',
                                    args=[self.f.pk]))
        self.assertEqual(r.status_code, 302)


# =============================================================================
# Ficha metodológica (DANE/SEN)
# =============================================================================

from .services import ficha as sficha


class FichaTests(TestCase):
    def setUp(self):
        self.f = _formulario()

    def test_faltantes_sin_ficha(self):
        fi = sficha.ficha_de(self.f)
        self.assertEqual(len(sficha.faltantes_minimos(fi)),
                         len(sficha.MINIMA))
        self.assertEqual(sficha.completitud_minima(fi), 0)

    def test_muestreo_exige_campos_extra(self):
        fi = _ficha_minima(self.f)
        self.assertEqual(sficha.faltantes_minimos(fi), [])
        fi.tipo_operacion = 'muestreo_prob'
        fi.save()
        faltan = sficha.faltantes_minimos(fi)
        self.assertIn('Tamaño de muestra', faltan)
        self.assertIn('Diseño muestral', faltan)
        self.assertIn('Unidad de muestreo', faltan)

    def test_completitud(self):
        fi = _ficha_minima(self.f)
        self.assertEqual(sficha.completitud_minima(fi), 100)

    def test_actualizar_desde_post(self):
        from django.http import QueryDict
        fi = sficha.ficha_de(self.f)
        q = QueryDict('', mutable=True)
        q['f_objetivo_general'] = 'Objetivo nuevo'
        q.setlist('f_metodos_recoleccion', ['autodiligenciamiento', 'dmc'])
        sficha.actualizar_ficha(fi, q)
        self.assertEqual(fi.objetivo_general, 'Objetivo nuevo')
        self.assertEqual(fi.metodos_recoleccion,
                         ['autodiligenciamiento', 'dmc'])

    def test_duplicar_clona_ficha(self):
        _ficha_minima(self.f, sigla='EPS-1')
        nuevo = sf.duplicar(self.f)
        self.assertEqual(nuevo.ficha.sigla, 'EPS-1')
        self.assertEqual(nuevo.ficha.objetivo_general, 'Medir X.')

    def test_vista_ficha_gestor(self):
        g = User.objects.create_user('gestor_ficha', password='x')
        from indicadores.models import PerfilRecolector
        PerfilRecolector.objects.create(user=g,
                                        rol='gestor_formularios')
        self.client.force_login(g)
        r = self.client.get(reverse('gestion:encuestas_ficha',
                                    args=[self.f.pk]))
        self.assertEqual(r.status_code, 200)
        r = self.client.post(
            reverse('gestion:encuestas_ficha', args=[self.f.pk]),
            {'f_objetivo_general': 'Nuevo objetivo'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            self.f.ficha.objetivo_general, 'Nuevo objetivo')


# =============================================================================
# Tipos complejos (url, telefono, fecha_hora, matriz, ordenar, catalogo,
# archivo)
# =============================================================================

class TiposComplejosTests(TestCase):
    def setUp(self):
        self.f = _formulario()
        self.f.estado = 'publicado'
        self.f.save()

    def _enviar(self, post, files=None):
        envio = Envio.objects.create(formulario=self.f, modo='auto',
                                     estado='borrador')
        return envio, se.enviar(envio, post, files)

    def test_url_validacion(self):
        p = _con_pregunta(self.f, tipo='url')
        envio = Envio.objects.create(formulario=self.f, modo='auto')
        errs = se._guardar_respuestas(
            envio, {f'p_{p.pk}': 'no-es-url'},
            validar_obligatorias=False)
        self.assertIn(p.pk, errs)
        errs = se._guardar_respuestas(
            envio, {f'p_{p.pk}': 'https://x.co/d.pdf'},
            validar_obligatorias=False)
        self.assertNotIn(p.pk, errs)
        self.assertEqual(envio.respuestas.get(pregunta=p).valor,
                         'https://x.co/d.pdf')

    def test_telefono_y_fecha_hora(self):
        p1 = _con_pregunta(self.f, tipo='telefono')
        p2 = _con_pregunta(self.f, tipo='fecha_hora')
        envio = Envio.objects.create(formulario=self.f, modo='auto')
        errs = se._guardar_respuestas(
            envio, {f'p_{p1.pk}': '+57 604 555 1234',
                    f'p_{p2.pk}': '2026-11-20T14:30'},
            validar_obligatorias=False)
        self.assertEqual(errs, {})

    def test_matriz(self):
        p = _con_pregunta(self.f, tipo='matriz', obligatoria=True,
                          config={
                              'filas': [{'id': 'f1', 'texto': 'Salud'},
                                        {'id': 'f2', 'texto': 'Educación'}],
                              'columnas': [{'id': 'c1', 'texto': 'Bueno'},
                                           {'id': 'c2', 'texto': 'Malo'}]})
        envio = Envio.objects.create(formulario=self.f, modo='auto')
        errs = se._guardar_respuestas(
            envio, {f'p_{p.pk}_f1': 'c1'},
            validar_obligatorias=True)
        self.assertIn(p.pk, errs)          # falta f2
        errs = se._guardar_respuestas(
            envio, {f'p_{p.pk}_f1': 'c1', f'p_{p.pk}_f2': 'c2'},
            validar_obligatorias=True)
        self.assertNotIn(p.pk, errs)
        v = envio.respuestas.get(pregunta=p).valor
        self.assertEqual(v['f1']['columna_texto'], 'Bueno')
        self.assertEqual(v['f2']['columna_texto'], 'Malo')
        # Importación offline con el dict crudo
        limpio, errs2 = __import__(
            'encuestas.services.offline',
            fromlist=['_limpiar_valor'])._limpiar_valor(
                p, {'f1': 'c2'})
        self.assertEqual(limpio['f1']['columna_id'], 'c2')

    def test_ordenar(self):
        p = _con_pregunta(self.f, tipo='ordenar', obligatoria=True)
        for i, t in enumerate(['A', 'B', 'C']):
            Opcion.objects.create(pregunta=p, orden=i, texto=t)
        envio = Envio.objects.create(formulario=self.f, modo='auto')
        o2, o3 = p.opciones.all()[1], p.opciones.all()[2]
        o1 = p.opciones.all()[0]
        errs = se._guardar_respuestas(
            envio, {f'p_{p.pk}': f'{o2.pk},{o3.pk},{o1.pk}'},
            validar_obligatorias=True)
        self.assertNotIn(p.pk, errs)
        v = envio.respuestas.get(pregunta=p).valor
        self.assertEqual([x['texto'] for x in v], ['B', 'C', 'A'])
        self.assertEqual(v[0]['pos'], 1)

    def test_catalogo(self):
        from indicadores.models import Organismo
        org = Organismo.objects.create(nombre='DANE')
        p = _con_pregunta(self.f, tipo='catalogo',
                          config={'catalogo': 'organismo'})
        envio = Envio.objects.create(formulario=self.f, modo='auto')
        errs = se._guardar_respuestas(
            envio, {f'p_{p.pk}': str(org.pk)},
            validar_obligatorias=False)
        self.assertNotIn(p.pk, errs)
        v = envio.respuestas.get(pregunta=p).valor
        self.assertEqual(v['texto'], 'DANE')
        # id inválido → error
        errs = se._guardar_respuestas(
            envio, {f'p_{p.pk}': '999999'},
            validar_obligatorias=False)
        self.assertIn(p.pk, errs)

    def test_archivo(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        p = _con_pregunta(self.f, tipo='archivo', obligatoria=True)
        envio = Envio.objects.create(formulario=self.f, modo='auto')
        arch = SimpleUploadedFile('evidencia.pdf', b'%PDF-1 fake',
                                  content_type='application/pdf')
        errs = se._guardar_respuestas(
            envio, {}, {f'p_{p.pk}': arch}, validar_obligatorias=True)
        self.assertNotIn(p.pk, errs)
        from .models import Adjunto
        self.assertEqual(envio.adjuntos.count(), 1)
        v = envio.respuestas.get(pregunta=p).valor
        self.assertEqual(v['nombre'], 'evidencia.pdf')
        envio.adjuntos.get().archivo.delete()
        # Extensión prohibida
        arch2 = SimpleUploadedFile('virus.exe', b'x')
        errs = se._guardar_respuestas(
            envio, {}, {f'p_{p.pk}': arch2}, validar_obligatorias=True)
        self.assertIn(p.pk, errs)
