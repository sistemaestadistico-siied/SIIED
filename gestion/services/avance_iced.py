"""
Cálculo de avance FICED por organismo y vigencia.

Extraído de `views_validacion.validacion_avances_iced` (plan §3.1) para
que lo consuman el tablero de validación y el dashboard del gestor.
Añade los «equipos requeridos» por organismo según `sin_pp`/`sin_obs`
(misma regla que la conciliación de `views_validacion`).
"""
from django.db.models import Count

from indicadores.models import Organismo
from indicadores.models_iced import ICEDFormulario, ICEDPreguntaEquipo

EQUIPOS_ICED = [eq for eq, _ in ICEDFormulario.EQUIPO_CHOICES if eq]

# Equipo eximido por cada bandera del organismo (regla de conciliación).
_EXENCION = {'sin_pp': 'ETPP', 'sin_obs': 'ETOBS'}


def equipos_requeridos_iced(organismo):
    """Equipos técnicos que deben entregar formulario por el organismo.

    `sin_pp` exime a ETPP y `sin_obs` a ETOBS, igual que la conciliación.
    """
    return [eq for eq in EQUIPOS_ICED
            if not (eq == 'ETPP' and getattr(organismo, 'sin_pp', False))
            and not (eq == 'ETOBS' and getattr(organismo, 'sin_obs', False))]


def periodos_iced():
    """Vigencias con al menos un formulario, más recientes primero."""
    return list(ICEDFormulario.objects.order_by('-periodo')
                .values_list('periodo', flat=True).distinct())


def avance_iced(periodo_sel):
    """Filas de avance por organismo para el periodo dado.

    Cada fila: organismo, equipos (slot con formulario/% o 'no aplica'
    cuando el equipo está eximido por sin_pp/sin_obs), consolidado,
    n_formularios y avance_medio. Los organismos activos sin formularios
    aparecen como «sin iniciar».
    """
    from indicadores.views_validacion import _codigos_respondidos_iced

    esperadas = {eq: set() for eq in EQUIPOS_ICED}
    for eq, cod in ICEDPreguntaEquipo.objects.values_list('equipo', 'codigo'):
        esperadas.setdefault(eq, set()).add(str(cod))
    esperadas_consol = set().union(*esperadas.values()) if esperadas else set()

    formularios = (ICEDFormulario.objects
                   .filter(periodo=periodo_sel)
                   .select_related('organismo', 'usuario_diligencia',
                                   'prevalidado_por')) if periodo_sel \
        else ICEDFormulario.objects.none()

    slots_por_org = {}
    for f in formularios:
        respondidas = _codigos_respondidos_iced(f)
        esp = esperadas_consol if f.equipo == '' else esperadas.get(
            f.equipo, set())
        n_ok = len(respondidas & esp)
        slots_por_org.setdefault(f.organismo_id, {})[f.equipo] = {
            'f': f,
            'respondidas': n_ok,
            'esperadas': len(esp),
            'respondidas_raw': len(respondidas),
            'pct': round(n_ok / len(esp) * 100) if esp else f.completitud,
        }

    filas = []
    for org in Organismo.objects.filter(activo=True).order_by('nombre'):
        slots_org = slots_por_org.get(org.id, {})
        requeridos = set(equipos_requeridos_iced(org))
        equipos = []
        n_formularios = 0
        pcts = []
        for eq in EQUIPOS_ICED:
            slot = slots_org.get(eq)
            if slot:
                n_formularios += 1
                pcts.append(slot['pct'])
            equipos.append({'codigo': eq, 'slot': slot,
                            'requerido': eq in requeridos})
        consolidado = slots_org.get('')
        if consolidado:
            n_formularios += 1
        filas.append({
            'organismo': org,
            'equipos': equipos,
            'consolidado': consolidado,
            'n_requeridos': len(requeridos),
            'n_formularios': n_formularios,
            'avance_medio': (round(sum(pcts) / len(pcts))
                             if pcts else None),
        })

    por_estado = dict(
        formularios.values_list('estado')
        .annotate(n=Count('id')).order_by())
    stats = {
        'con_formularios': sum(1 for r in filas if r['n_formularios']),
        'sin_iniciar': sum(1 for r in filas if not r['n_formularios']),
        'formularios': sum(por_estado.values()),
        'por_estado': por_estado,
    }
    return filas, stats
