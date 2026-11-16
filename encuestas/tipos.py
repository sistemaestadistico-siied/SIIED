"""
Registro de tipos de pregunta (§5.2).

Cada tipo describe: etiqueta, si tiene opciones, cómo valida/limpia el
valor del POST (sin `mark_safe` ni `safe` — el HTML lo construye el
widget con escapado) y su partial de plantilla.
"""
import re
from decimal import Decimal, InvalidOperation

TIPOS = {}


class TipoPregunta:
    clave = ''
    etiqueta = ''
    tiene_opciones = False
    tiene_otro = False
    usa_lista = False          # leer con post.getlist
    necesita_archivo = False   # leer desde request.FILES
    partial = 'encuestas/widgets/texto.html'

    def limpiar(self, valor, pregunta, form):
        """Valida y normaliza el valor del POST. Retorna el valor a
        guardar o None; usa form.add_error() ante error."""
        raise NotImplementedError

    def valor_desde_post(self, post, files, key, p, form):
        """Extrae y limpia el valor del POST. Los tipos simples lo
        heredan; matriz/archivo lo sobreescriben."""
        bruto = post.getlist(key) if self.usa_lista else post.get(key)
        return self.limpiar(bruto, p, form)


def registrar(cls):
    TIPOS[cls.clave] = cls
    return cls


class _Texto(TipoPregunta):
    def limpiar(self, valor, p, form):
        return (valor or '').strip() or None


@registrar
class TextoCorto(_Texto):
    clave = 'texto_corto'
    etiqueta = 'Texto corto'


@registrar
class TextoLargo(_Texto):
    clave = 'texto_largo'
    etiqueta = 'Texto largo (párrafo)'
    partial = 'encuestas/widgets/textarea.html'


@registrar
class Numero(_Texto):
    clave = 'numero'
    etiqueta = 'Número'
    partial = 'encuestas/widgets/numero.html'

    def limpiar(self, valor, p, form):
        v = (valor or '').strip()
        if not v:
            return None
        try:
            n = Decimal(v)
        except InvalidOperation:
            form.add_error(f'«{v}» no es un número válido.')
            return None
        mn, mx = p.config.get('min'), p.config.get('max')
        if mn is not None and n < Decimal(str(mn)):
            form.add_error(f'Mínimo {mn}.')
        if mx is not None and n > Decimal(str(mx)):
            form.add_error(f'Máximo {mx}.')
        return float(n)


@registrar
class Correo(_Texto):
    clave = 'correo'
    etiqueta = 'Correo'
    partial = 'encuestas/widgets/correo.html'

    def limpiar(self, valor, p, form):
        v = (valor or '').strip()
        if v and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v):
            form.add_error('Correo inválido.')
            return None
        return v or None


@registrar
class Fecha(_Texto):
    clave = 'fecha'
    etiqueta = 'Fecha'
    partial = 'encuestas/widgets/fecha.html'

    def limpiar(self, valor, p, form):
        from django.utils.dateparse import parse_date
        v = (valor or '').strip()
        if not v:
            return None
        if not parse_date(v):
            form.add_error('Fecha inválida.')
            return None
        return v


class _Eleccion(TipoPregunta):
    tiene_opciones = True

    def opciones_vivas(self, p):
        return list(p.opciones.all())


@registrar
class SeleccionUnica(_Eleccion):
    clave = 'seleccion_unica'
    etiqueta = 'Selección única'
    tiene_otro = True
    partial = 'encuestas/widgets/radio.html'

    def limpiar(self, valor, p, form):
        v = (valor or '').strip()
        if not v:
            return None
        viva = {str(o.id): o for o in self.opciones_vivas(p)}
        if v not in viva:
            form.add_error('Opción inválida.')
            return None
        return {'opcion_id': int(v), 'texto': viva[v].texto}


@registrar
class SeleccionMultiple(_Eleccion):
    clave = 'seleccion_multiple'
    etiqueta = 'Selección múltiple'
    tiene_otro = True
    usa_lista = True
    partial = 'encuestas/widgets/checkbox.html'

    def limpiar(self, valores, p, form):
        """`valores` es una lista."""
        vs = [v for v in (valores or []) if str(v).strip()]
        if not vs:
            return None
        viva = {str(o.id): o for o in self.opciones_vivas(p)}
        for v in vs:
            if v not in viva:
                form.add_error('Opción inválida.')
                return None
        return [{'opcion_id': int(v), 'texto': viva[v].texto}
                for v in vs]


@registrar
class Desplegable(SeleccionUnica):
    clave = 'desplegable'
    etiqueta = 'Desplegable'
    partial = 'encuestas/widgets/select.html'


@registrar
class SiNo(SeleccionUnica):
    clave = 'si_no'
    etiqueta = 'Sí / No'
    partial = 'encuestas/widgets/sino.html'

    def limpiar(self, valor, p, form):
        v = (valor or '').strip()
        if v not in ('si', 'no'):
            if not v:
                return None
            form.add_error('Opción inválida.')
            return None
        return {'opcion_id': v, 'texto': 'Sí' if v == 'si' else 'No'}


@registrar
class Escala(_Texto):
    clave = 'escala'
    etiqueta = 'Escala (1 a N)'
    partial = 'encuestas/widgets/escala.html'

    def limpiar(self, valor, p, form):
        v = (valor or '').strip()
        if not v:
            return None
        mn = int(p.config.get('min', 1))
        mx = int(p.config.get('max', 5))
        try:
            n = int(v)
        except ValueError:
            form.add_error('Valor fuera de la escala.')
            return None
        if not (mn <= n <= mx):
            form.add_error(f'La escala va de {mn} a {mx}.')
            return None
        return n


@registrar
class TextoInformativo(TipoPregunta):
    """No guarda respuesta: es texto de ayuda dentro del formulario."""
    clave = 'informativo'
    etiqueta = 'Texto informativo'
    partial = 'encuestas/widgets/informativo.html'

    def limpiar(self, valor, p, form):
        return None


# =============================================================================
# Tipos complejos (adoptados de FICED/Taller + patrones estadísticos)
# =============================================================================

@registrar
class Url(_Texto):
    """URL de evidencia o referencia (patrón P23 del FICED)."""
    clave = 'url'
    etiqueta = 'URL / enlace'
    partial = 'encuestas/widgets/url.html'

    def limpiar(self, valor, p, form):
        v = (valor or '').strip()
        if v and not re.match(r'^https?://\S+$', v):
            form.add_error('Debe ser una URL (inicia con http:// o https://).')
            return None
        return v or None


@registrar
class Telefono(_Texto):
    clave = 'telefono'
    etiqueta = 'Teléfono'
    partial = 'encuestas/widgets/telefono.html'

    def limpiar(self, valor, p, form):
        v = (valor or '').strip()
        if v and not re.match(r'^[\d\s()+-]{7,20}$', v):
            form.add_error('Teléfono inválido.')
            return None
        return v or None


@registrar
class FechaHora(_Texto):
    clave = 'fecha_hora'
    etiqueta = 'Fecha y hora'
    partial = 'encuestas/widgets/fecha_hora.html'

    def limpiar(self, valor, p, form):
        from django.utils.dateparse import parse_datetime
        v = (valor or '').strip()
        if not v:
            return None
        if not parse_datetime(v):
            form.add_error('Fecha y hora inválidas.')
            return None
        return v


@registrar
class Matriz(TipoPregunta):
    """Cuadrícula filas × columnas, una respuesta por fila (patrón de
    los módulos de cuestionarios DANE). `config.filas` y
    `config.columnas`: [{'id': str, 'texto': str}]."""
    clave = 'matriz'
    etiqueta = 'Matriz (filas × columnas)'
    partial = 'encuestas/widgets/matriz.html'

    def _limpiar_fila(self, filas, columnas, fid, col, form):
        f = filas[fid]
        if col not in columnas:
            form.add_error(f'Fila «{f["texto"]}»: columna inválida.')
            return None
        return {'columna_id': col, 'columna_texto': columnas[col]['texto']}

    def valor_desde_post(self, post, files, key, p, form):
        filas = {str(f['id']): f for f in p.config.get('filas', [])}
        columnas = {str(c['id']): c for c in p.config.get('columnas', [])}
        valor, faltan = {}, []
        for fid, f in filas.items():
            col = (post.get(f'{key}_{fid}') or '').strip()
            if col:
                celda = self._limpiar_fila(filas, columnas, fid, col, form)
                if celda:
                    valor[fid] = celda
            elif p.obligatoria:
                faltan.append(f['texto'])
        if faltan:
            form.add_error(
                'Faltan filas: ' + ', '.join(faltan[:4]) + '.')
        return valor or None

    def limpiar(self, bruto, p, form):
        """Importación offline: `bruto` es {fila_id: columna_id} o
        {fila_id: {'columna_id': …}} ya guardado en el respaldo."""
        if not isinstance(bruto, dict):
            return None
        filas = {str(f['id']): f for f in p.config.get('filas', [])}
        columnas = {str(c['id']): c for c in p.config.get('columnas', [])}
        valor = {}
        for fid, raw in bruto.items():
            if fid not in filas:
                continue
            col = (raw.get('columna_id') if isinstance(raw, dict)
                   else raw)
            celda = self._limpiar_fila(filas, columnas, fid,
                                       str(col or ''), form)
            if celda:
                valor[fid] = celda
        return valor or None


@registrar
class Ordenar(_Eleccion):
    """Ranking de las opciones: valor = lista ordenada de opciones."""
    clave = 'ordenar'
    etiqueta = 'Ordenar (ranking)'
    tiene_otro = False
    partial = 'encuestas/widgets/ordenar.html'

    def limpiar(self, valor, p, form):
        """`valor` es una cadena de ids por coma, o una lista de ids o
        de dicts {'opcion_id': …} (importación offline)."""
        if isinstance(valor, list):
            ids = [str(v.get('opcion_id') if isinstance(v, dict) else v)
                   for v in valor]
            ids = [v for v in ids if v and v != 'None']
        else:
            ids = [v.strip() for v in str(valor or '').split(',')
                   if v.strip()]
        if not ids:
            return None
        viva = {str(o.id): o for o in self.opciones_vivas(p)}
        if any(v not in viva for v in ids):
            form.add_error('Opción inválida.')
            return None
        if p.obligatoria and len(ids) < len(viva):
            form.add_error('Ordene todas las opciones.')
            return None
        return [{'opcion_id': int(v), 'texto': viva[v].texto,
                 'pos': i + 1}
                for i, v in enumerate(ids)]


_CATALOGOS = {
    'organismo': ('indicadores', 'Organismo', 'nombre'),
    'suborganismo': ('indicadores', 'Suborganismo', 'nombre'),
    'equipo': ('indicadores', 'EquipoOrganismo', 'nombre'),
}


@registrar
class Catalogo(TipoPregunta):
    """Selección desde un catálogo del sistema (config.catalogo:
    organismo | suborganismo | equipo). Alinea la respuesta con los
    estándares del sistema en vez de texto libre."""
    clave = 'catalogo'
    etiqueta = 'Catálogo del sistema'
    partial = 'encuestas/widgets/catalogo.html'

    def catalogo_clave(self, p):
        return p.config.get('catalogo', 'organismo')

    def opciones_catalogo(self, p):
        app, modelo, campo = _CATALOGOS.get(
            self.catalogo_clave(p), (None, None, None))
        if not app:
            return []
        from django.apps import apps
        Modelo = apps.get_model(app, modelo)
        return list(Modelo.objects
                    .order_by(campo).values('id', campo))

    def limpiar(self, valor, p, form):
        if isinstance(valor, dict):
            v = str(valor.get('id') or '')
        else:
            v = str(valor or '').strip()
        if not v:
            return None
        app, modelo, campo = _CATALOGOS.get(
            self.catalogo_clave(p), (None, None, None))
        if not app:
            form.add_error('Catálogo no configurado.')
            return None
        from django.apps import apps
        Modelo = apps.get_model(app, modelo)
        try:
            obj = Modelo.objects.get(pk=int(v))
        except (Modelo.DoesNotExist, ValueError):
            form.add_error('Valor inválido del catálogo.')
            return None
        return {'catalogo': self.catalogo_clave(p),
                'id': obj.pk, 'texto': str(obj)}


@registrar
class Archivo(TipoPregunta):
    """Adjunto como evidencia. `config.extensiones` (default pdf, png,
    jpg, jpeg, doc, docx, xlsx, csv) y `config.max_mb` (default 5).
    Solo disponible en modo web — no se captura en el offline."""
    clave = 'archivo'
    etiqueta = 'Archivo adjunto'
    necesita_archivo = True
    partial = 'encuestas/widgets/archivo.html'

    def valor_desde_post(self, post, files, key, p, form):
        f = (files or {}).get(key)
        if f is None:
            return None
        nombre = f.name.lower()
        ext = nombre.rsplit('.', 1)[-1] if '.' in nombre else ''
        permitidas = [e.lower() for e in p.config.get(
            'extensiones',
            ['pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'xlsx', 'csv'])]
        if ext not in permitidas:
            form.add_error(
                f'Extensión .{ext} no permitida ({", ".join(permitidas)}).')
            return None
        max_mb = float(p.config.get('max_mb', 5))
        if f.size > max_mb * 1024 * 1024:
            form.add_error(f'El archivo supera {max_mb:g} MB.')
            return None
        return {'archivo': f}

    def limpiar(self, valor, p, form):
        """Importación offline: no se capturan archivos fuera de
        línea — el respaldo nunca incluye este valor."""
        return None


def tipo_de(pregunta):
    """Devuelve la clase del tipo, o TextoCorto como fallback."""
    return TIPOS.get(pregunta.tipo, TextoCorto)


def choices():
    return [(k, t.etiqueta) for k, t in TIPOS.items()]
