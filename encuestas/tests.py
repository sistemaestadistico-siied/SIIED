# -*- coding: utf-8 -*-
"""Tests del módulo Encuestas."""
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

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


class CicloVidaTests(TestCase):
    def test_crear_y_estructura(self):
        f = _formulario()
        self.assertEqual(f.secciones.count(), 1)
        self.assertFalse(f.estructura_bloqueada)

    def test_publicar_exige_pregunta(self):
        f = _formulario()
        with self.assertRaises(ValidationError):
            sf.publicar(f)
        _con_pregunta(f)
        sf.publicar(f)
        self.assertEqual(f.estado, 'publicado')

    def test_cerrar_y_reabrir(self):
        f = _formulario()
        _con_pregunta(f)
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
