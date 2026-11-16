"""
Exportación de respuestas (plan §5.8).

- larga: envío × pregunta (pregunta, enunciado, valor crudo).
- pivot: una fila por envío con una columna por pregunta (`codigo`),
  metadatos de identificación del respondiente primero.
"""
import csv
import io
import json

from ..models import Envio, Pregunta


def _texto_valor(valor):
    """Valor JSON → texto legible para exportar."""
    if valor is None:
        return ''
    if isinstance(valor, list):
        partes = []
        for v in valor:
            if isinstance(v, dict):
                partes.append(v.get('texto')
                              or v.get('otro')
                              or json.dumps(v, ensure_ascii=False))
            else:
                partes.append(str(v))
        return '; '.join(partes)
    if isinstance(valor, dict):
        if 'otro' in valor:
            return f"Otro: {valor['otro']}"
        if 'texto' in valor:
            extra = f" — {valor['otro']}" if valor.get('otro') else ''
            return f"{valor['texto']}{extra}"
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def preguntas_exportables(formulario):
    return list(Pregunta.objects
                .filter(seccion__formulario=formulario)
                .exclude(tipo='informativo')
                .order_by('seccion__orden', 'orden', 'id')
                .select_related('seccion'))


def csv_largo(formulario, envios=None):
    envios = envios if envios is not None else (
        formulario.envios.filter(estado='enviado')
        .select_related('respondiente', 'diligenciado_por')
        .prefetch_related('respuestas__pregunta'))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['envio_id', 'fecha_envio', 'modo',
                'diligenciado_por', 'respondiente', 'documento',
                'pregunta_codigo', 'pregunta', 'valor'])
    for e in envios:
        resp = e.respondiente
        meta = [
            e.pk,
            e.enviado.isoformat() if e.enviado else '',
            e.modo,
            e.diligenciado_por.username if e.diligenciado_por else '',
            str(resp) if resp else '',
            resp.documento if resp else '',
        ]
        for r in e.respuestas.all():
            p = r.pregunta
            w.writerow(meta + [p.codigo or f'p{p.pk}', p.enunciado,
                               _texto_valor(r.valor)])
    return out.getvalue()


def csv_pivot(formulario, envios=None):
    envios = envios if envios is not None else (
        formulario.envios.filter(estado='enviado')
        .select_related('respondiente', 'diligenciado_por')
        .prefetch_related('respuestas__pregunta'))
    preguntas = preguntas_exportables(formulario)
    headers = ([p.codigo or f'p{p.pk}' for p in preguntas])
    id_cols = ['envio_id', 'fecha_envio', 'modo', 'diligenciado_por',
               'nombres', 'apellidos', 'tipo_documento', 'documento',
               'telefono', 'correo', 'territorio', 'organismo']

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(id_cols + headers)
    for e in envios:
        resp = e.respondiente
        fila = [
            e.pk, e.enviado.isoformat() if e.enviado else '', e.modo,
            e.diligenciado_por.username if e.diligenciado_por else '',
            resp.nombres if resp else '',
            resp.apellidos if resp else '',
            resp.tipo_documento if resp else '',
            resp.documento if resp else '',
            resp.telefono if resp else '',
            resp.correo if resp else '',
            resp.territorio if resp else '',
            resp.organismo.nombre if resp and resp.organismo else '',
        ]
        valores = {r.pregunta_id: r.valor for r in e.respuestas.all()}
        fila += [_texto_valor(valores.get(p.pk)) for p in preguntas]
        w.writerow(fila)
    return out.getvalue()


def resumen(formulario):
    """Conteos por tipo de pregunta para el tablero de resultados."""
    preguntas = preguntas_exportables(formulario)
    envios = (formulario.envios.filter(estado='enviado')
              .prefetch_related('respuestas__pregunta')
              .select_related('diligenciado_por'))
    resumen = []
    for p in preguntas:
        conteos = {}
        respondidas = 0
        for e in envios:
            v = next((r.valor for r in e.respuestas.all()
                      if r.pregunta_id == p.pk), None)
            if v is None:
                continue
            respondidas += 1
            if isinstance(v, list):
                for item in v:
                    texto = (item.get('texto') if isinstance(item, dict)
                             else str(item))
                    conteos[texto] = conteos.get(texto, 0) + 1
            elif isinstance(v, dict) and p.tipo == 'matriz':
                filas = {str(f['id']): f['texto']
                         for f in p.config.get('filas', [])}
                for fid, celda in v.items():
                    if isinstance(celda, dict):
                        t = (f"{filas.get(fid, fid)}: "
                             f"{celda.get('columna_texto', '')}")
                        conteos[t] = conteos.get(t, 0) + 1
            elif isinstance(v, dict):
                texto = v.get('texto') or str(v)
                conteos[texto] = conteos.get(texto, 0) + 1
            else:
                texto = str(v)
                conteos[texto] = conteos.get(texto, 0) + 1
        total = sum(conteos.values())
        filas = sorted(
            [{'texto': t, 'n': n,
              'pct': round(n * 100 / total, 1) if total else 0}
             for t, n in conteos.items()],
            key=lambda x: -x['n'])
        resumen.append({
            'pregunta': p, 'respondidas': respondidas,
            'filas': filas[:20], 'n_opciones': len(filas)})
    return resumen, envios


def csv_diccionario(formulario):
    """Diccionario de datos del cuestionario (metadato NTC PE 1000):
    variable, tipo, etiqueta, ayuda, obligatoriedad y dominio."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['variable', 'seccion', 'tipo', 'etiqueta', 'ayuda',
                'obligatoria', 'dominio'])
    for p in preguntas_exportables(formulario):
        dominio = ''
        if p.tipo == 'matriz':
            filas = [f['texto'] for f in p.config.get('filas', [])]
            cols = [c['texto'] for c in p.config.get('columnas', [])]
            dominio = f"filas: {' | '.join(filas)}; columnas: {' | '.join(cols)}"
        elif p.tipo == 'catalogo':
            dominio = f"catalogo: {p.config.get('catalogo', '')}"
        elif p.tipo == 'archivo':
            exts = ','.join(p.config.get('extensiones', [])) or 'todas'
            dominio = f"extensiones: {exts}"
        elif p.tipo in ('escala', 'numero'):
            mn, mx = p.config.get('min'), p.config.get('max')
            if mn is not None or mx is not None:
                dominio = f"rango: {mn}–{mx}"
        elif p.opciones.exists():
            dominio = ' | '.join(p.opciones.values_list('texto', flat=True))
        w.writerow([p.codigo or f'p{p.pk}', p.seccion.titulo, p.tipo,
                    p.enunciado, p.ayuda,
                    'sí' if p.obligatoria else 'no', dominio])
    return out.getvalue()
