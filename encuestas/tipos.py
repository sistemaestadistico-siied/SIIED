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
    partial = 'encuestas/widgets/texto.html'

    def limpiar(self, valor, pregunta, form):
        """Valida y normaliza el valor del POST. Retorna el valor a
        guardar o None; usa form.add_error() ante error."""
        raise NotImplementedError


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


def tipo_de(pregunta):
    """Devuelve la clase del tipo, o TextoCorto como fallback."""
    return TIPOS.get(pregunta.tipo, TextoCorto)


def choices():
    return [(k, t.etiqueta) for k, t in TIPOS.items()]
