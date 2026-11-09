"""
Vistas para el módulo ICED v2 — FormWizard con SessionWizardView.

Endpoints:
- /iced/                    → Landing / lista de formularios del organismo
- /iced/formulario/         → Wizard de 11 pasos (A-E + revisión)
- /iced/formulario/<id>/    → Retomar wizard existente (borrador)
- /iced/confirmacion/<id>/  → Confirmación + puntaje tras envío
- /iced/resultado/<id>/     → Resultado detallado del ICED
"""

import json
import logging
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse

from formtools.wizard.views import SessionWizardView

logger = logging.getLogger(__name__)

from .models_iced import (
    ICEDFormulario, ICEDRecursoHumano,
    ICEDMacroProceso, ICEDProceso, ICEDSubproceso, ICEDProcedimiento,
    equipo_desde_username,
)
from .models import OperacionEstadistica, Organismo
from .templatetags.iced_tags import iced_field_label
from django.db.models import Q
from .forms_iced import (
    ICEDModuloAForm, ICEDModuloBForm,
    ICEDModuloC1Form, ICEDModuloC2Form, ICEDModuloC3Form,
    ICEDModuloD1Form, ICEDModuloD2Form, ICEDModuloD3Form,
    ICEDModuloEForm,
    ICED_WIZARD_FORMS, ICED_STEP_LABELS,
)
from .calcular_iced import (
    calcular_iced, aplicar_puntajes, exportar_csv_periodo,
    CSV_HEADERS, resultado_a_fila_csv,
)


# =============================================================================
# WIZARD VIEW
# =============================================================================

class ICEDWizardView(SessionWizardView):
    """
    FormWizard de 11 pasos para el FICED.
    Diez pasos de módulos (A-E) + paso final de revisión y confirmación.
    """
    template_name = 'indicadores/iced/formulario_wizard.html'

    def _paso_tiene_campos(self, step_key):
        """True si el paso tiene al menos un campo visible para el equipo
        del formulario. Los pasos sin preguntas asignadas se saltan (p.ej.
        ETSGC no ve los módulos D y pasa de P22 a observaciones)."""
        equipo = self._equipo_formulario()
        if not equipo:
            return True
        from .models_iced import ICEDPreguntaEquipo
        form_cls = dict(ICED_WIZARD_FORMS).get(step_key)
        if not form_cls:
            return True
        return any(
            ICEDPreguntaEquipo.campo_pertenece_a_equipo(fname, equipo)
            for fname in form_cls.base_fields
        )

    # Estados en los que el formulario aún puede editarse
    ESTADOS_EDITABLES = ('borrador', 'devuelto')
    # El validador SIIED corrige respuestas directamente sobre el
    # consolidado (no hay devolución al organismo): puede editarlo aunque
    # ya esté enviado o pre-validado por el organismo.
    ESTADOS_EDITABLES_SIIED = ('enviado', 'prevalidado')

    @staticmethod
    def _es_validador_sistema(user):
        """Validador SIIED (staff, 'validador' o 'analista'): puede corregir
        cualquier respuesta del consolidado, sin importar el subrol/equipo."""
        if getattr(user, 'is_staff', False):
            return True
        perfil = getattr(user, 'perfil_recolector', None)
        return bool(perfil and perfil.es_validador_sistema())

    def dispatch(self, request, *args, **kwargs):
        """Validar propiedad del formulario y estado editable antes de entrar al wizard."""
        formulario_id = kwargs.get('formulario_id')
        if not formulario_id:
            # Formulario nuevo: el equipo técnico se define en el perfil de
            # usuario (subrol_ficed) o en el username — no se elige en la UI.
            # Sin equipo no puede crear un FICED: equipo='' es el consolidado
            # de validación, no un formulario de respuesta.
            if not request.user.is_staff and _get_user_organismo(request.user) \
                    and not _get_user_equipo(request.user):
                messages.error(
                    request,
                    'Tu usuario no tiene un equipo técnico asignado. '
                    'El administrador del SIIED debe definirlo en tu perfil de usuario.'
                )
                return redirect('indicadores:iced_landing')
        if formulario_id:
            formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
            es_sistema = self._es_validador_sistema(request.user)
            organismo = _get_user_organismo(request.user)
            es_propio = organismo and formulario.organismo_id == organismo.id
            if not es_propio and not es_sistema:
                messages.error(request, 'No tiene permiso para acceder a este formulario.')
                return redirect('indicadores:iced_landing')
            # El formulario pertenece a un equipo técnico: solo ese equipo
            # puede editarlo (equipo='' = consolidado/completo, que tampoco
            # es editable por delegados de equipos). El validador SIIED es
            # la excepción: corrige el consolidado de cualquier organismo.
            equipo_user = _get_user_equipo(request.user)
            if not es_sistema and not equipo_user:
                # Sin equipo en perfil: no puede editar nada (tampoco el
                # consolidado equipo='').
                messages.error(
                    request,
                    'Tu usuario no tiene un equipo técnico asignado. '
                    'El administrador del SIIED debe definirlo en tu perfil de usuario.'
                )
                return redirect('indicadores:iced_landing')
            if (not es_sistema
                    and formulario.equipo != equipo_user):
                messages.error(request, 'Este formulario pertenece a otro equipo técnico.')
                return redirect('indicadores:iced_landing')
            estados = self.ESTADOS_EDITABLES
            if es_sistema:
                estados = estados + self.ESTADOS_EDITABLES_SIIED
            if formulario.estado not in estados:
                messages.info(
                    request,
                    f'Este formulario está en estado '
                    f'"{formulario.get_estado_display()}" y no puede editarse.'
                )
                if es_sistema:
                    return redirect('indicadores:validacion_revisar_iced',
                                    formulario_id=formulario.pk)
                return redirect('indicadores:iced_resultado', formulario_id=formulario.pk)
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _mop_data_json():
        """Serializa la jerarquía MOP (MacroProceso→Proceso→Subproceso→Procedimiento)
        para el widget estructura-mop.

        Incluye 'procedimientos_directos': procedimientos que cuelgan de un
        Proceso sin subproceso intermedio (caso real del MOP).

        Se usa el código MOP como 'id' (los códigos oficiales SP/PR son
        únicos globalmente), lo que mantiene el JSON de respuestas legible
        para el validador.
        """
        data = {
            'macroprocesos': [],
            'procesos': {},
            'subprocesos': {},
            'procedimientos': {},
            'procedimientos_directos': {},
        }
        try:
            macroprocesos = ICEDMacroProceso.objects.filter(activo=True).prefetch_related(
                'procesos__subprocesos__procedimientos',
                'procesos__procedimientos_directos',
            )
            for mp in macroprocesos:
                data['macroprocesos'].append({
                    'id': mp.codigo, 'codigo': mp.codigo, 'nombre': mp.nombre,
                })
                for pr in mp.procesos.all():
                    if not pr.activo:
                        continue
                    data['procesos'].setdefault(mp.codigo, []).append({
                        'id': pr.codigo, 'codigo': pr.codigo, 'nombre': pr.nombre,
                    })
                    for sp in pr.subprocesos.all():
                        if not sp.activo:
                            continue
                        data['subprocesos'].setdefault(pr.codigo, []).append({
                            'id': sp.codigo, 'codigo': sp.codigo, 'nombre': sp.nombre,
                        })
                        for proc in sp.procedimientos.all():
                            if not proc.activo:
                                continue
                            data['procedimientos'].setdefault(sp.codigo, []).append({
                                'id': proc.codigo, 'codigo': proc.codigo, 'nombre': proc.nombre,
                            })
                    for proc in pr.procedimientos_directos.all():
                        if not proc.activo:
                            continue
                        data['procedimientos_directos'].setdefault(pr.codigo, []).append({
                            'id': proc.codigo, 'codigo': proc.codigo, 'nombre': proc.nombre,
                        })
        except Exception as e:
            logger.error(f"Error serializando estructura MOP: {e}")
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _organismos_json():
        """Lista de organismos activos para selects del wizard (P10.2, etc.)."""
        try:
            nombres = list(
                Organismo.objects.filter(activo=True)
                .order_by('nombre')
                .values_list('nombre', flat=True)
            )
        except Exception as e:
            logger.error(f"Error serializando organismos: {e}")
            nombres = []
        return json.dumps(nombres, ensure_ascii=False)

    def get(self, request, *args, **kwargs):
        """Reanudar el wizard en el paso donde quedó el borrador (paso_actual)."""
        formulario_id = kwargs.get('formulario_id')
        if formulario_id and not self.storage.current_step:
            try:
                paso = ICEDFormulario.objects.values_list('paso_actual', flat=True).get(pk=formulario_id)
                if paso and paso in self.form_list:
                    self.storage.current_step = paso
            except ICEDFormulario.DoesNotExist:
                pass
        return super().get(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context['page'] = 'iced'
        context['step_labels'] = ICED_STEP_LABELS
        context['formulario_id'] = self.kwargs.get('formulario_id')
        context['total_steps'] = len(ICED_WIZARD_FORMS)
        context['current_step_index'] = list(ICED_STEP_LABELS.keys()).index(self.steps.current)
        context['current_step_label'] = ICED_STEP_LABELS.get(self.steps.current, '')

        # Manual focalizado de la sección actual (Fase 2 FICED)
        from .iced_manual import MANUAL_POR_PASO
        context['manual_paso'] = MANUAL_POR_PASO.get(self.steps.current)

        # Formulario en edición: permite mostrar estado y observaciones del
        # validador (flujo devuelto → corrección) dentro del wizard.
        formulario_actual = None
        formulario_id = self.kwargs.get('formulario_id')
        if formulario_id:
            formulario_actual = ICEDFormulario.objects.filter(pk=formulario_id).first()
        context['formulario_actual'] = formulario_actual

        # Estructura MOP real para el widget estructura-mop de P7 (paso entorno).
        if self.steps.current == 'entorno':
            context['mop_data_json'] = self._mop_data_json()
            context['organismos_json'] = self._organismos_json()

        # Progreso — solo los pasos visibles para este equipo
        # (condition_dict puede haber saltado módulos sin campos).
        steps_list = list(self.steps.all)
        current_idx = steps_list.index(self.steps.current) if self.steps.current in steps_list else 0
        context['progress_percent'] = int(((current_idx + 1) / len(steps_list)) * 100)
        context['steps_info'] = [
            {
                'key': s,
                'label': ICED_STEP_LABELS[s],
                'index': i,
                'is_current': s == self.steps.current,
                'is_done': i < current_idx,
            }
            for i, s in enumerate(steps_list)
        ]

        # Paso de revisión: resumen de respuestas de todos los pasos previos.
        # Fuente primaria: datos de la sesión del wizard. Respaldo: respuestas
        # guardadas en BD (borradores reanudados en una sesión nueva).
        if self.steps.current == 'revision':
            resumen = []
            for step_key in steps_list:
                if step_key == 'revision':
                    continue
                try:
                    data = self.get_cleaned_data_for_step(step_key) or {}
                except Exception:
                    data = {}
                if not data and formulario_actual:
                    data = self._respuestas_bd_para_paso(formulario_actual, step_key)
                visibles = {k: v for k, v in data.items() if v not in (None, '', [], {})}
                resumen.append({
                    'key': step_key,
                    'label': ICED_STEP_LABELS.get(step_key, step_key),
                    'respuestas': visibles,
                    'total': len(visibles),
                })
            context['resumen_revision'] = resumen
        return context

    @staticmethod
    def _respuestas_bd_para_paso(formulario, step_key):
        """Respuestas guardadas en BD para un paso, filtradas por los campos
        del formulario de ese paso (los módulos C y D comparten campo JSON)."""
        paso_campo = {
            'identificacion': 'respuestas_a',
            'entorno': 'respuestas_b',
            'infraestructura_c1': 'respuestas_c',
            'infraestructura_c2': 'respuestas_c',
            'infraestructura_c3': 'respuestas_c',
            'metodologia_d1': 'respuestas_d',
            'metodologia_d2': 'respuestas_d',
            'metodologia_d3': 'respuestas_d',
            'metodologia_d4': 'respuestas_d',
            'accesibilidad': 'respuestas_e',
        }
        campo = paso_campo.get(step_key)
        if not campo:
            return {}
        respuestas = getattr(formulario, campo, None) or {}
        form_class = dict(ICED_WIZARD_FORMS).get(step_key)
        campos_paso = set(form_class.base_fields.keys()) if form_class else set()
        prefix = f"{step_key}-"
        resultado = {}
        for key, value in respuestas.items():
            nombre = key[len(prefix):] if key.startswith(prefix) else key
            if not campos_paso or nombre in campos_paso:
                resultado[nombre] = value
        return resultado

    def get_form_initial(self, step):
        """Pre-llenar módulo A desde organismo y personas de contacto desde registros existentes."""
        import json as _json
        initial = super().get_form_initial(step)
        
        # PRIMERO: Cargar datos guardados del formulario (si existe formulario_id)
        formulario_id = self.kwargs.get('formulario_id')
        if formulario_id:
            try:
                formulario = ICEDFormulario.objects.get(pk=formulario_id)
                modulo_map = {
                    'identificacion': 'respuestas_a',
                    'entorno': 'respuestas_b',
                    'infraestructura_c1': 'respuestas_c',
                    'infraestructura_c2': 'respuestas_c',
                    'infraestructura_c3': 'respuestas_c',
                    'metodologia_d1': 'respuestas_d',
                    'metodologia_d2': 'respuestas_d',
                    'metodologia_d3': 'respuestas_d',
                    'metodologia_d4': 'respuestas_d',
                    'accesibilidad': 'respuestas_e',
                }
                campo = modulo_map.get(step)
                if campo:
                    respuestas = getattr(formulario, campo, {})
                    if respuestas:
                        # Los datos se guardan con prefijo del paso
                        prefix = f"{step}-"
                        for key, value in respuestas.items():
                            if key.startswith(prefix):
                                field_name = key[len(prefix):]
                                initial[field_name] = value
                            else:
                                initial[key] = value
            except ICEDFormulario.DoesNotExist:
                pass
        
        # DESPUÉS: Establecer campos auto-calculados que NO deben sobrescribirse
        # (como el nombre del organismo que siempre viene del perfil del usuario)
        if step == 'identificacion':
            organismo = self._get_organismo()
            if organismo:
                initial['p1_nombre_organismo'] = organismo.nombre
                initial['p1_nombre_organismo_display'] = organismo.nombre
            
            # Pre-cargar personas de contacto desde tabla auxiliar (no de respuestas)
            if formulario_id:
                try:
                    formulario = ICEDFormulario.objects.get(pk=formulario_id)
                    personas_qs = formulario.personas_contacto.all()
                    if personas_qs.exists():
                        initial['personas_contacto_json'] = _json.dumps([
                            {
                                'nombre_completo': p.nombre_completo,
                                'cargo': p.cargo,
                                'correo': p.correo,
                                'telefono': p.telefono or '',
                                'orden': p.orden,
                            }
                            for p in personas_qs.order_by('orden', 'id')
                        ], ensure_ascii=False)
                except ICEDFormulario.DoesNotExist:
                    pass

        # Pre-llenar P19 (RRHH) desde la tabla auxiliar si existen registros
        if step == 'infraestructura_c2':
            formulario_id = self.kwargs.get('formulario_id')
            if formulario_id:
                try:
                    formulario = ICEDFormulario.objects.get(pk=formulario_id)
                    rrhh_qs = formulario.recursos_humanos.all()
                    if rrhh_qs.exists():
                        import json as _json
                        initial['p19_rrhh_list'] = _json.dumps([
                            {
                                'nombre_completo': r.nombre_completo,
                                'correo': r.correo,
                                'telefono': r.telefono,
                                'grupo': r.grupo,
                                'anios_experiencia': r.anios_experiencia,
                                'inicio_participacion': r.inicio_participacion,
                                'tipo_vinculacion': r.tipo_vinculacion,
                                'categoria_cargo': r.categoria_cargo,
                                'nivel_formacion': r.nivel_formacion,
                                'etapas_proceso': r.etapas_proceso or [],
                                'funciones_estadisticas': r.funciones_estadisticas,
                            }
                            for r in rrhh_qs
                        ], ensure_ascii=False)
                except ICEDFormulario.DoesNotExist:
                    pass
        return initial

    def get_form(self, step=None, data=None, files=None):
        """Obtener formulario con datos iniciales correctamente cargados."""
        form = super().get_form(step, data, files)

        # Filtrar campos según el equipo técnico del formulario: solo se
        # muestran las preguntas asignadas a ese equipo ('' = todas).
        equipo = self._equipo_formulario()
        from .models_iced import ICEDPreguntaEquipo
        if equipo:
            for fname in list(form.fields.keys()):
                if not ICEDPreguntaEquipo.campo_pertenece_a_equipo(fname, equipo):
                    del form.fields[fname]

        # Anotar las preguntas compartidas con las respuestas que ya
        # dieron otros equipos del mismo organismo (se muestran en el
        # template como referencia antes de responder). Va fuera de
        # `if equipo`: el consolidado (equipo='') también debe ver lo que
        # respondió cada subrol durante la conciliación.
        otras = self._respuestas_otros_equipos()
        if otras:
            anotados = set()
            for fname, fld in form.fields.items():
                cod = ICEDPreguntaEquipo.codigo_de_campo(fname)
                if cod and cod in otras and cod not in anotados:
                    fld.otras_respuestas = otras[cod]
                    anotados.add(cod)

        # P23: poblar el select de operaciones estadísticas desde el inventario
        if 'p23_operaciones_estadisticas' in form.fields:
            self._inyectar_opciones_operaciones(form)

        # Si estamos cargando el formulario por primera vez (no es POST/validación),
        # asegurar que los datos iniciales estén establecidos
        if data is None and files is None:
            # Usar self.steps.current si step es None
            current_step = step or self.steps.current
            initial = self.get_form_initial(current_step)
            if initial:
                for field_name, value in initial.items():
                    if field_name in form.fields:
                        form.fields[field_name].initial = value
                        # También establecer en el widget si es JSON
                        if hasattr(form.fields[field_name].widget, 'attrs') and \
                           form.fields[field_name].widget.attrs.get('class', '').startswith('iced-json-field'):
                            form.fields[field_name].widget.attrs['data-initial'] = value
        
        return form

    def _inyectar_opciones_operaciones(self, form):
        """Poblar el select 'nombre_oe' de P23 con el inventario de operaciones estadísticas.

        Filtra por el organismo del usuario (por nombre o código); si no hay
        coincidencias, muestra todas las operaciones activas como respaldo.
        """
        import json as _json
        widget = form.fields['p23_operaciones_estadisticas'].widget
        try:
            config = _json.loads(widget.attrs.get('data-config', '{}'))
        except (ValueError, TypeError):
            return

        qs = OperacionEstadistica.objects.filter(activo=True)
        organismo = self._get_organismo()
        filtrado = qs.none()
        if organismo:
            filtrado = qs.filter(
                Q(organismo__iexact=organismo.nombre) |
                Q(c_organismo__iexact=organismo.codigo)
            )
        propias = list(
            filtrado.order_by('nombre')
            .values_list('nombre', flat=True).distinct()
        )
        opciones = propias or list(
            qs.order_by('nombre').values_list('nombre', flat=True).distinct()
        )

        for col in config.get('columnas', []):
            if col.get('name') == 'nombre_oe':
                col['tipo'] = 'select'
                col['opciones'] = opciones
                break

        # El instrumento lista las OOEE del inventario y el delegado solo
        # marca Sí/No: precargar una fila por operación (las del organismo o,
        # si no tiene propias en el inventario, el inventario completo), con
        # el nombre bloqueado.
        nombres_filas = propias or opciones
        config['filas_iniciales'] = [{'nombre_oe': n} for n in nombres_filas]
        config['filas_bloqueadas'] = len(nombres_filas)
        config['fila_fija_campos'] = ['nombre_oe']
        config['min_filas'] = len(nombres_filas)
        widget.attrs['data-config'] = _json.dumps(config, ensure_ascii=False)

    def done(self, form_list, **kwargs):
        """Guardar formulario completo, calcular puntaje y redirigir."""
        organismo = self._get_organismo()
        if not organismo:
            messages.error(self.request, 'No se pudo determinar el organismo del usuario.')
            return redirect('indicadores:iced_landing')

        # Obtener o crear formulario
        formulario_id = self.kwargs.get('formulario_id')
        es_sistema = self._es_validador_sistema(self.request.user)
        if formulario_id:
            formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
            # Verificación de seguridad: propiedad (organismo del USUARIO),
            # equipo técnico y estado editable
            organismo_usuario = _get_user_organismo(self.request.user)
            es_propio = organismo_usuario and formulario.organismo_id == organismo_usuario.id
            if not es_propio and not es_sistema:
                messages.error(self.request, 'No tiene permiso para modificar este formulario.')
                return redirect('indicadores:iced_landing')
            equipo_user = _get_user_equipo(self.request.user)
            if (not es_sistema
                    and formulario.equipo != equipo_user):
                messages.error(self.request, 'Este formulario pertenece a otro equipo técnico.')
                return redirect('indicadores:iced_landing')
            estados = self.ESTADOS_EDITABLES
            if es_sistema:
                estados = estados + self.ESTADOS_EDITABLES_SIIED
            if formulario.estado not in estados:
                messages.error(
                    self.request,
                    f'Este formulario está en estado '
                    f'"{formulario.get_estado_display()}" y no puede modificarse.'
                )
                if es_sistema:
                    return redirect('indicadores:validacion_revisar_iced',
                                    formulario_id=formulario.pk)
                return redirect('indicadores:iced_resultado', formulario_id=formulario.pk)
        else:
            equipo_user = _get_user_equipo(self.request.user)
            if not self.request.user.is_staff and not equipo_user:
                messages.error(
                    self.request,
                    'Tu usuario no tiene un equipo técnico asignado. '
                    'El administrador del SIIED debe definirlo en tu perfil de usuario.'
                )
                return redirect('indicadores:iced_landing')
            formulario, _ = ICEDFormulario.objects.get_or_create(
                organismo=organismo,
                periodo=str(timezone.now().year),
                equipo=equipo_user,
                defaults={
                    'usuario_diligencia': self.request.user,
                }
            )

        # Guardar respuestas de cada módulo
        # Mapeo de pasos a campos de respuesta (soporta múltiples formularios por módulo)
        step_to_field = {
            'identificacion': 'respuestas_a',
            'entorno': 'respuestas_b',
            'infraestructura_c1': 'respuestas_c',
            'infraestructura_c2': 'respuestas_c',
            'infraestructura_c3': 'respuestas_c',
            'metodologia_d1': 'respuestas_d',
            'metodologia_d2': 'respuestas_d',
            'metodologia_d3': 'respuestas_d',
            'metodologia_d4': 'respuestas_d',
            'accesibilidad': 'respuestas_e',
        }
        
        # Agrupar respuestas por módulo
        respuestas_por_modulo = {
            'respuestas_a': {},
            'respuestas_b': {},
            'respuestas_c': {},
            'respuestas_d': {},
            'respuestas_e': {},
        }
        
        for form in form_list:
            step_name = getattr(form, 'step_name', None)
            if not step_name:
                continue
                
            field_name = step_to_field.get(step_name)
            if not field_name:
                continue
                
            for key, value in form.cleaned_data.items():
                # Convertir Decimal a float para serialización JSON
                from decimal import Decimal as Dec
                if isinstance(value, Dec):
                    respuestas_por_modulo[field_name][key] = float(value)
                else:
                    respuestas_por_modulo[field_name][key] = value
        
        # Guardar cada módulo en su campo correspondiente
        for field_name, respuestas in respuestas_por_modulo.items():
            if respuestas:  # Solo guardar si hay datos
                setattr(formulario, field_name, respuestas)

        # Corrección del validador SIIED sobre el consolidado: conserva
        # su lugar en la cola (estado y fecha de envío del organismo);
        # no se devuelve al organismo ni se re-notifica un envío nuevo.
        edicion_siied = (
            es_sistema and formulario_id
            and formulario.estado in self.ESTADOS_EDITABLES_SIIED)
        if not edicion_siied:
            # Marcar como enviado
            formulario.estado = 'enviado'
            formulario.fecha_envio = timezone.now()
            formulario.usuario_diligencia = self.request.user
        formulario.paso_actual = 'completado'
        formulario.save()

        # Materializar registros de personas de contacto desde respuestas_a
        self._materializar_personas_contacto(formulario)
        
        # Materializar registros de RRHH (P19) desde el JSON de respuestas_c
        self._materializar_rrhh(formulario)

        if edicion_siied:
            messages.success(
                self.request,
                'Respuestas del consolidado actualizadas por el equipo SIIED.'
            )
            return redirect('indicadores:validacion_revisar_iced',
                            formulario_id=formulario.pk)

        # Notificar por correo a validadores/admins (no bloquea el envío si falla)
        try:
            from .notifications import notificar_validadores_nuevo_iced
            notificar_validadores_nuevo_iced(formulario)
        except Exception:
            logger.exception('Error notificando a validadores el envío del ICED %s', formulario.pk)

        messages.success(
            self.request,
            'Formulario ICED enviado exitosamente. Un validador del equipo técnico del SIIED '
            'revisará sus respuestas y ejecutará el proceso de cálculo del índice. '
            'Se le notificará por correo electrónico cuando el proceso haya finalizado.'
        )
        return redirect('indicadores:iced_confirmacion', formulario_id=formulario.pk)

    def _materializar_personas_contacto(self, formulario):
        """
        Convierte el JSON de `respuestas_a['personas_contacto_json']` en registros
        `ICEDPersonaContacto` asociados al formulario.
        Estrategia: borrar todos los existentes y recrear desde el JSON.
        """
        import json as _json
        from .models_iced import ICEDPersonaContacto
        
        raw = (formulario.respuestas_a or {}).get('personas_contacto_json', '[]')
        try:
            personas = _json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
        except (ValueError, TypeError):
            personas = []
        if not isinstance(personas, list):
            return

        # Borrar existentes y recrear
        formulario.personas_contacto.all().delete()

        for i, p in enumerate(personas):
            if not isinstance(p, dict):
                continue
            nombre = (p.get('nombre_completo') or '').strip()
            if not nombre:
                continue  # Saltar filas vacías
            
            ICEDPersonaContacto.objects.create(
                formulario=formulario,
                nombre_completo=nombre[:255],
                cargo=(p.get('cargo') or '')[:150],
                correo=(p.get('correo') or '')[:254],
                telefono=(p.get('telefono') or '')[:20],
                orden=p.get('orden', i),
            )

    def _materializar_rrhh(self, formulario):
        """
        Convierte el JSON de `respuestas_c['p19_rrhh_list']` en registros
        `ICEDRecursoHumano` asociados al formulario. Estrategia: borrar todos
        los existentes y recrear desde el JSON para evitar desincronización.
        """
        import json as _json
        raw = (formulario.respuestas_c or {}).get('p19_rrhh_list', '')
        try:
            personas = _json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
        except (ValueError, TypeError):
            personas = []
        if not isinstance(personas, list):
            return

        formulario.recursos_humanos.all().delete()

        for p in personas:
            if not isinstance(p, dict):
                continue
            nombre = (p.get('nombre_completo') or '').strip()
            if not nombre:
                continue  # Saltamos filas vacías
            try:
                anios = int(p.get('anios_experiencia') or 0)
            except (ValueError, TypeError):
                anios = 0
            etapas = p.get('etapas_proceso') or []
            if not isinstance(etapas, list):
                etapas = []
            ICEDRecursoHumano.objects.create(
                formulario=formulario,
                nombre_completo=nombre[:200],
                correo=(p.get('correo') or '')[:254],
                telefono=(p.get('telefono') or '')[:20],
                grupo=(p.get('grupo') or '')[:100],
                anios_experiencia=max(0, anios),
                inicio_participacion=(p.get('inicio_participacion') or '')[:10],
                tipo_vinculacion=p.get('tipo_vinculacion') or 'contratista',
                categoria_cargo=(p.get('categoria_cargo') or '')[:5],
                nivel_formacion=(p.get('nivel_formacion') or '')[:5],
                etapas_proceso=etapas,
                funciones_estadisticas=bool(p.get('funciones_estadisticas')),
            )

    def _equipo_formulario(self):
        """Equipo técnico del formulario en edición; si es nuevo, el del usuario.

        '' significa formulario completo/consolidado (muestra todas las
        preguntas, comportamiento legado).
        """
        fid = self.kwargs.get('formulario_id')
        if fid:
            eq = ICEDFormulario.objects.filter(pk=fid).values_list(
                'equipo', flat=True).first()
            if eq is not None:
                return eq
        return _get_user_equipo(self.request.user)

    def _respuestas_otros_equipos(self):
        """Respuestas que otros equipos del organismo ya dieron, por pregunta.

        Retorna {codigo: [{'equipo', 'quien', 'campos': {field: valor}}]}.
        Excluye el formulario actual y el consolidado (equipo=''), que es
        producto de la conciliación del validador, no de un delegado.
        """
        from .models_iced import ICEDPreguntaEquipo

        if hasattr(self, '_otros_cache'):
            return self._otros_cache

        cache = {}
        organismo = self._get_organismo()
        equipo = self._equipo_formulario()
        fid = self.kwargs.get('formulario_id')
        periodo = str(timezone.now().year)
        if fid:
            periodo = ICEDFormulario.objects.filter(pk=fid).values_list(
                'periodo', flat=True).first() or periodo

        if organismo:
            qs = (ICEDFormulario.objects
                  .filter(organismo=organismo, periodo=periodo)
                  .exclude(pk=fid)
                  .exclude(equipo='')
                  .exclude(equipo=equipo)
                  .select_related('usuario_diligencia'))
            for f in qs:
                plano = {}
                for attr in ('respuestas_a', 'respuestas_b', 'respuestas_c',
                             'respuestas_d', 'respuestas_e'):
                    plano.update(getattr(f, attr) or {})
                por_codigo = {}
                for k, v in plano.items():
                    # Las claves se guardan con prefijo de paso: 'entorno-p10_x'
                    fname = k.split('-', 1)[1] if '-' in k else k
                    cod = ICEDPreguntaEquipo.codigo_de_campo(fname)
                    if not cod or v in (None, '', [], {}, '[]', '{}'):
                        continue
                    if fname.endswith(('_intro', '_display', '_link')):
                        continue
                    por_codigo.setdefault(cod, {})[fname] = v
                usuario = f.usuario_diligencia
                quien = (usuario.get_full_name() or usuario.username
                         ) if usuario else ''
                mapa_idx = _mapa_campos_iced()
                for cod, campos in por_codigo.items():
                    # Orden del wizard (declaración del campo), no del JSON:
                    # la pregunta principal (p10_participacion) debe salir
                    # antes que sub-campos (p10_actividades).
                    ordenados = sorted(
                        campos.items(),
                        key=lambda kv: mapa_idx.get(kv[0], {}).get('idx', 9999))
                    campos = dict(ordenados)
                    items = [{
                        'field_key': fname,
                        'label': iced_field_label(fname),
                        'respuesta': v,
                    } for fname, v in ordenados]
                    cache.setdefault(cod, []).append({
                        'equipo': f.equipo,
                        'quien': quien,
                        'campos': campos,
                        'items': items,
                    })

        self._otros_cache = cache
        return cache

    def _get_organismo(self):
        """Obtener el organismo asociado al usuario actual."""
        user = self.request.user
        # Primero intentar desde formulario existente (retomar borrador)
        formulario_id = self.kwargs.get('formulario_id')
        if formulario_id:
            try:
                return ICEDFormulario.objects.get(pk=formulario_id).organismo
            except ICEDFormulario.DoesNotExist:
                pass
        # Luego desde perfil_recolector (modelo principal del proyecto)
        if hasattr(user, 'perfil_recolector') and hasattr(user.perfil_recolector, 'organismo'):
            return user.perfil_recolector.organismo
        # Fallbacks por compatibilidad
        if hasattr(user, 'perfil_delegado') and hasattr(user.perfil_delegado, 'organismo'):
            return user.perfil_delegado.organismo
        if hasattr(user, 'perfil') and hasattr(user.perfil, 'organismo'):
            return user.perfil.organismo
        # Fallback: si es staff, buscar primer organismo activo
        if user.is_staff:
            from .models import Organismo
            return Organismo.objects.filter(activo=True).first()
        return None

    # ...
def _condicion_paso(step_key):
    """Fábrica de condiciones del wizard: el paso se muestra solo si tiene
    campos asignados al equipo técnico del formulario (pasos vacíos se saltan).
    'identificacion' y 'revision' siempre se muestran."""
    def cond(wizard):
        return wizard._paso_tiene_campos(step_key)
    return cond


ICED_CONDITIONS = {
    step: _condicion_paso(step)
    for step, _form in ICED_WIZARD_FORMS
    if step not in ('identificacion', 'revision')
}


# =============================================================================
# VISTAS AUXILIARES
# =============================================================================

@login_required
def iced_landing(request):
    """
    Página principal del módulo ICED.
    Muestra formularios existentes del organismo y opción de crear nuevo.
    """
    from .models import Organismo

    organismo = _get_user_organismo(request.user)
    equipo_user = _get_user_equipo(request.user)
    formularios = []
    if organismo:
        formularios = ICEDFormulario.objects.filter(
            organismo=organismo
        )
        # El delegado ve los formularios de su equipo técnico + los
        # VALIDADOS de cualquier equipo del organismo (los resultados
        # validados son públicos dentro del organismo — iced_resultado
        # ya solo filtra por organismo, no por equipo). Los enviados o
        # en borrador de otros equipos siguen siendo privados.
        if not request.user.is_staff:
            formularios = formularios.filter(
                Q(equipo=equipo_user) | Q(estado='validado'))
        formularios = formularios.order_by('-periodo')

    # Para staff: mostrar todos
    if request.user.is_staff and not organismo:
        formularios = ICEDFormulario.objects.all().order_by('-periodo', 'organismo__nombre')

    # Usuario con subrol fijado en el username: solo responde un FICED por
    # año (el de su equipo). Una vez existe el del período actual, se oculta
    # el botón de "nuevo formulario"; reaparece cuando cambia el año.
    equipo_fijo = equipo_desde_username(request.user.username)
    ocultar_nuevo = bool(
        equipo_fijo and organismo and ICEDFormulario.objects.filter(
            organismo=organismo,
            periodo=str(timezone.now().year),
            equipo=equipo_fijo,
        ).exists()
    )

    return render(request, 'indicadores/iced/landing.html', {
        'page': 'iced',
        'organismo': organismo,
        'formularios': formularios,
        'equipo_user': equipo_user,
        'equipo_user_label': (
            dict(ICEDFormulario.EQUIPO_CHOICES).get(equipo_user, equipo_user)
            if equipo_user else ''
        ),
        'periodo_actual': str(timezone.now().year),
        'ocultar_nuevo': ocultar_nuevo,
    })


@login_required
def iced_equipo(request):
    """
    Ruta heredada — ya no se elige equipo en la UI. El equipo técnico se
    define en el perfil de usuario (subrol_ficed) o va fijado en el
    username (p. ej. 'DAP_ETPP'). Esta vista solo sincroniza el equipo
    del username con el perfil y redirige al destino pedido.
    """
    organismo = _get_user_organismo(request.user)
    if not organismo:
        messages.error(request, 'No tienes un organismo asignado.')
        return redirect('indicadores:iced_landing')

    perfil = getattr(request.user, 'perfil_recolector', None)
    destino = request.POST.get('next') or request.GET.get('next') or ''

    equipo_fijo = equipo_desde_username(request.user.username)
    if equipo_fijo and perfil and perfil.subrol_ficed != equipo_fijo:
        perfil.subrol_ficed = equipo_fijo
        perfil.save(update_fields=['subrol_ficed'])

    if not _get_user_equipo(request.user):
        messages.error(
            request,
            'Tu usuario no tiene un equipo técnico asignado. '
            'El administrador del SIIED debe definirlo en tu perfil de usuario.'
        )
        return redirect('indicadores:iced_landing')

    if destino == 'formulario':
        return redirect('indicadores:iced_formulario_nuevo')
    return redirect('indicadores:iced_landing')


@login_required
def iced_confirmacion(request, formulario_id):
    """Vista de confirmación tras enviar el formulario — sin puntajes."""
    formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
    organismo = _get_user_organismo(request.user)
    if not request.user.is_staff and (not organismo or formulario.organismo_id != organismo.id):
        messages.error(request, 'No tiene permiso para acceder a este formulario.')
        return redirect('indicadores:iced_landing')

    return render(request, 'indicadores/iced/confirmacion.html', {
        'page': 'iced',
        'formulario': formulario,
    })


@login_required
def iced_resultado(request, formulario_id):
    """Vista detallada de resultados del ICED."""
    import json as _json
    formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
    organismo = _get_user_organismo(request.user)
    if not request.user.is_staff and (not organismo or formulario.organismo_id != organismo.id):
        messages.error(request, 'No tiene permiso para acceder a este formulario.')
        return redirect('indicadores:iced_landing')
    resultado = calcular_iced(formulario)

    # Los puntajes solo se publican cuando el FICED quedó validado por el
    # equipo SIIED (calificación final). En enviado/prevalidado el organismo
    # ve el estado del trámite, no puntajes parciales ni oficiales.
    mostrar_puntaje = formulario.estado == 'validado'

    # Serializar dimensiones para JS (solo puntaje numérico)
    dims_json = {}
    if mostrar_puntaje:
        for k, puntaje in resultado.get('dimensiones', {}).items():
            dims_json[k] = {'puntaje': float(puntaje)}

    return render(request, 'indicadores/iced/resultado.html', {
        'page': 'iced',
        'formulario': formulario,
        'resultado': resultado,
        'resultado_json': _json.dumps(dims_json),
        'mostrar_puntaje': mostrar_puntaje,
    })


@login_required
def iced_guardar_parcial(request):
    """API para guardado parcial (borrador) desde el wizard vía AJAX."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        return JsonResponse({'error': f'JSON inválido: {str(e)}'}, status=400)

    paso = data.get('paso')
    respuestas = data.get('respuestas', {})
    formulario_id = data.get('formulario_id')

    # Validar que tenemos paso
    if not paso:
        return JsonResponse({'error': 'El campo paso es requerido'}, status=400)

    organismo = _get_user_organismo(request.user)
    es_sistema = ICEDWizardView._es_validador_sistema(request.user)
    if not organismo and not es_sistema:
        return JsonResponse({
            'error': 'No se pudo determinar el organismo del usuario',
            'detail': 'El usuario no tiene un organismo asignado en su perfil'
        }, status=400)

    if formulario_id:
        formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
        # Verificar propiedad: el equipo SIIED corrige el consolidado de
        # cualquier organismo; el resto solo edita lo suyo.
        if not es_sistema and (
                not organismo or formulario.organismo_id != organismo.id):
            return JsonResponse({'error': 'No tiene permiso sobre este formulario'}, status=403)
        equipo_user = _get_user_equipo(request.user)
        if (not es_sistema
                and formulario.equipo != equipo_user):
            return JsonResponse({'error': 'Este formulario pertenece a otro equipo técnico'}, status=403)
        estados = ICEDWizardView.ESTADOS_EDITABLES
        if es_sistema:
            estados = estados + ICEDWizardView.ESTADOS_EDITABLES_SIIED
        if formulario.estado not in estados:
            return JsonResponse({
                'error': f'El formulario está en estado '
                         f'"{formulario.get_estado_display()}" y no puede modificarse'
            }, status=400)
    else:
        if not organismo:
            return JsonResponse({
                'error': 'No se pudo determinar el organismo del usuario'
            }, status=400)
        equipo_user = _get_user_equipo(request.user)
        if not request.user.is_staff and not equipo_user:
            return JsonResponse({
                'error': 'Debes seleccionar tu equipo técnico antes de iniciar el FICED.',
                'redirect': reverse('indicadores:iced_equipo') + '?next=formulario',
            }, status=400)
        formulario, _ = ICEDFormulario.objects.get_or_create(
            organismo=organismo,
            periodo=str(timezone.now().year),
            equipo=equipo_user,
            defaults={
                'usuario_diligencia': request.user,
            }
        )

    # Mapear paso a campo
    paso_campo = {
        'identificacion': 'respuestas_a',
        'entorno': 'respuestas_b',
        'infraestructura_c1': 'respuestas_c',
        'infraestructura_c2': 'respuestas_c',
        'infraestructura_c3': 'respuestas_c',
        'metodologia_d1': 'respuestas_d',
        'metodologia_d2': 'respuestas_d',
        'metodologia_d3': 'respuestas_d',
        'metodologia_d4': 'respuestas_d',
        'accesibilidad': 'respuestas_e',
    }
    campo = paso_campo.get(paso)
    if campo:
        # MERGE con lo existente: los pasos C1-C3 y D1-D4 comparten el mismo
        # campo JSON; sobrescribir borraba las respuestas de los otros pasos
        # del módulo al guardar borrador (IC-03).
        existente = getattr(formulario, campo) or {}
        existente.update(respuestas)
        # Purgar claves de campos auxiliares display-only heredadas de
        # versiones anteriores (p.ej. p25_proyectos_bp_link guardaba el
        # texto del enlace como si fuera una respuesta).
        for k in list(existente):
            fname = k.split('-', 1)[1] if '-' in k else k
            if fname.endswith(('_intro', '_display', '_link')):
                del existente[k]
        setattr(formulario, campo, existente)
        formulario.paso_actual = paso
        formulario.save(update_fields=[campo, 'paso_actual', 'fecha_actualizacion'])
    elif paso == 'revision':
        # El paso de revisión no tiene campo propio; solo registrar posición
        formulario.paso_actual = paso
        formulario.save(update_fields=['paso_actual', 'fecha_actualizacion'])

    return JsonResponse({
        'ok': True,
        'formulario_id': formulario.pk,
        'mensaje': 'Guardado parcial exitoso'
    })


# =============================================================================
# MINI-CHAT DON DATICO — Asistente de diligenciamiento FICED (Fase 3)
# =============================================================================

def _resumen_respuestas_iced(respuestas, max_items=25):
    """'campo: valor' compacto de un dict de respuestas para el prompt.

    Los valores suelen venir como STRINGS JSON (importador/wizard): se
    parsean para que el LLM vea un resumen legible ('opciones: a, b',
    'tabla con N filas') y no el JSON crudo ni un '[]' que leería como
    'sin registros' aunque otros campos sí tengan datos."""
    partes = []
    for k, v in (respuestas or {}).items():
        parsed = v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except (ValueError, TypeError):
                parsed = v
        if parsed in (None, '', [], {}):
            continue
        if isinstance(parsed, dict) and any(
                isinstance(x, dict) and 'seleccion' in x
                for x in parsed.values()):
            sel = [c for c, x in parsed.items()
                   if isinstance(x, dict) and x.get('seleccion')]
            vs = ('opciones marcadas: ' + ', '.join(sel)) if sel \
                else 'ninguna opción marcada'
        elif isinstance(parsed, list):
            if parsed and all(isinstance(x, dict) for x in parsed):
                vs = f'tabla con {len(parsed)} fila(s): ' \
                     + '; '.join(', '.join(f'{kk}={vv}' for kk, vv in x.items())
                                 for x in parsed[:3])
            else:
                vs = ', '.join(str(x) for x in parsed)
        elif isinstance(parsed, dict):
            vs = json.dumps(parsed, ensure_ascii=False)
        else:
            vs = str(v)
        if len(vs) > 180:
            vs = vs[:180] + '…'
        partes.append(f'{k}: {vs}')
        if len(partes) >= max_items:
            break
    return partes


@login_required
def iced_chat(request):
    """Chat flotante de Don Datico dentro del wizard FICED.

    Recibe {pregunta, paso, formulario_id, historial}. Responde texto
    plano orientado a la acción, con contexto de la sección actual del
    wizard, el manual focalizado, las respuestas guardadas del
    formulario actual y los formularios de años anteriores del organismo.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    pregunta = (data.get('pregunta') or '').strip()[:1500]
    paso = (data.get('paso') or '').strip()
    if not pregunta:
        return JsonResponse({'error': 'Escribe una pregunta.'}, status=400)

    organismo = _get_user_organismo(request.user)
    if not organismo:
        return JsonResponse({'error': 'Sin organismo asignado'}, status=403)

    from .iced_manual import manual_texto_paso, resumen_manual
    from .chat_config import get_config

    periodo_actual = str(timezone.now().year)

    # Formulario actual en diligenciamiento (si se identifica)
    formulario = None
    equipo_user = _get_user_equipo(request.user)
    fid = data.get('formulario_id')
    if fid:
        qs = ICEDFormulario.objects.filter(pk=fid, organismo=organismo)
        if not request.user.is_staff:
            qs = qs.filter(equipo=equipo_user)
        formulario = qs.first()
    if not formulario:
        qs = ICEDFormulario.objects.filter(
            organismo=organismo, periodo=periodo_actual, estado='borrador')
        if not request.user.is_staff:
            qs = qs.filter(equipo=equipo_user)
        formulario = qs.order_by('-fecha_actualizacion').first()

    # Respuestas guardadas del formulario actual
    resp_actual = ''
    if formulario:
        partes = []
        for campo in ('respuestas_a', 'respuestas_b', 'respuestas_c',
                      'respuestas_d', 'respuestas_e'):
            partes += _resumen_respuestas_iced(getattr(formulario, campo))
        if partes:
            resp_actual = (
                f"RESPUESTAS YA GUARDADAS del FICED {formulario.periodo} "
                f"(equipo {formulario.equipo or 'general'}, "
                f"estado {formulario.estado}):\n" + '\n'.join(partes[:60]))
    # Formularios de años anteriores: consolidado (equipo='') o el del
    # propio equipo; solo estados con contenido diligenciado real.
    resp_previos = []
    for f_prev in (ICEDFormulario.objects
                   .filter(organismo=organismo,
                           estado__in=['validado', 'enviado', 'prevalidado',
                                       'devuelto'])
                   .filter(Q(equipo='') | Q(equipo=equipo_user))
                   .exclude(periodo=periodo_actual)
                   .order_by('-periodo')[:3]):
        partes = []
        for campo in ('respuestas_a', 'respuestas_b', 'respuestas_c',
                      'respuestas_d', 'respuestas_e'):
            partes += _resumen_respuestas_iced(getattr(f_prev, campo), 15)
        resp_previos.append(
            f"FICED {f_prev.periodo} (equipo {f_prev.equipo or 'general'}, "
            f"{f_prev.estado}):\n" + '\n'.join(partes[:40]))

    seccion = ICED_STEP_LABELS.get(paso, paso or 'sin paso')
    equipo_desc = equipo_user or 'consolidado / sin equipo asignado'
    system_prompt = f"""Eres Don Datico, asistente del SIIED para el diligenciamiento del FICED (Formulario de Índice de Capacidad Estadística Distrital) del organismo "{organismo.nombre}".

Tu ÚNICO propósito es guiar al delegado a responder el FICED correctamente. Responde en español, claro, breve (máx. ~120 palabras) y orientado a la acción. Cita el número de pregunta (P#) cuando sea relevante. Nunca inventes respuestas para el usuario: explica QUÉ debe poner y déjalo diligenciar. Si la pregunta no es del FICED, redirige amablemente al formulario.

EQUIPO DEL USUARIO: {equipo_desc}. El delegado solo ve las preguntas asignadas a su equipo técnico (ETUAG_PSP, ETOBS, ETPP, ETSGC, ETGIE); si pregunta "¿por qué no veo la P#?", puede que esa pregunta no corresponda a su equipo (ej.: ETSGC no responde la P23 y salta de P22 a observaciones). Si ve un bloque "Pregunta compartida" con respuestas de otros equipos, es solo referencia: debe responder desde su propio equipo.

FLUJO Y ESTADOS: borrador (editable) → enviado (el validador del organismo concilia) → pre-validado → validado (puntaje oficial). No hay rechazo: las devoluciones van en cadena — el SIIED devuelve el consolidado al validador del organismo y este devuelve el formulario de un equipo ("devuelto"), que vuelve a ser editable con las observaciones; el SIIED también puede corregir directamente el consolidado y aprobar. El guardado es al avanzar de módulo o con el botón "Guardar borrador".

FORMATOS ESTRICTOS QUE DEBES RECORDAR AL USUARIO:
- Correos: nombre@dominio.com. Teléfonos: máx. 10 dígitos o +57 + 10 (sin letras ni extensión).
- Fechas "inicio de participación": MM/AAAA (ej: 03/2024). Fechas de widgets: selector de calendario AAAA-MM-DD.
- P21: porcentajes 0-100 por rubro cuya suma no pase de 100 (son 13 rubros: 4 hardware, 5 software, 4 personal/capacitación). Años de experiencia: número entero.
- URLs: completas https://…, varias separadas por coma. Códigos BP: separados por coma (ej: 2024001, 2024002).
- P23: si la operación ya no se genera, marque Vigente=NO (las demás columnas quedan NA y la URL se vacía). En P35 son obligatorios tipo, nombre y descripción; código MOP y URL son opcionales.

EVIDENCIA VERIFICABLE: si citas lo que el organismo respondió en años anteriores,
termina tu respuesta con el enlace para que el usuario lo verifique por sí mismo:
/iced/historico/?q=N (reemplaza N por el número de la pregunta, ej: /iced/historico/?q=8).
Escribe el enlace tal cual, en una línea sola.

SECCIÓN ACTUAL DEL USUARIO: {seccion}

GUÍA DE ESTA SECCIÓN:
{manual_texto_paso(paso)}

ÍNDICE DEL MANUAL COMPLETO:
{resumen_manual()}

{resp_actual}

{'FORMULARIOS DE AÑOS ANTERIORES (referencia):' + chr(10) + chr(10).join(resp_previos) if resp_previos else 'No hay formularios de años anteriores.'}"""

    # Historial corto de la conversación (máx. 8 turnos)
    historial = data.get('historial') or []
    messages = [{'role': 'system', 'content': system_prompt}]
    for h in historial[-8:]:
        rol = 'assistant' if h.get('rol') == 'assistant' else 'user'
        texto = (h.get('texto') or '')[:1500]
        if texto:
            messages.append({'role': rol, 'content': texto})
    messages.append({'role': 'user', 'content': pregunta})

    try:
        from .views_chat import ChatService
        service = ChatService(request=request)
        resp = service._call_llm_with_fallback(
            messages,
            stream=False,
            model=get_config('CEREBRAS_MODEL', 'gpt-oss-120b'),
            temperature=0.3,
            max_tokens=700,
        )
        texto = (resp.choices[0].message.content or '').strip()
    except Exception as e:
        logging.getLogger(__name__).warning(f'iced_chat LLM error: {e}')
        return JsonResponse(
            {'error': 'Don Datico no está disponible ahora. Intenta de '
                      'nuevo en unos segundos.'}, status=503)

    if not texto:
        texto = 'No pude generar una respuesta. Reformula tu pregunta.'
    return JsonResponse({'respuesta': texto})


# =============================================================================
# HISTÓRICO FICED — respuestas de años anteriores (evidencia del chat)
# =============================================================================

_MODULOS_JSON = ('respuestas_a', 'respuestas_b', 'respuestas_c',
                 'respuestas_d', 'respuestas_e')
_ESTADO_RANK = {'validado': 0, 'enviado': 1, 'prevalidado': 2,
                'devuelto': 3, 'borrador': 4, 'rechazado': 5}
_MAPA_CAMPOS = None


def _mapa_campos_iced():
    """{campo: {'label', 'modulo'}} desde las clases del wizard (perezoso)."""
    global _MAPA_CAMPOS
    if _MAPA_CAMPOS is not None:
        return _MAPA_CAMPOS
    from .forms_iced import (
        ICEDModuloAForm, ICEDModuloBForm,
        ICEDModuloC1Form, ICEDModuloC2Form, ICEDModuloC3Form,
        ICEDModuloD1Form, ICEDModuloD2Form, ICEDModuloD3Form,
        ICEDModuloD4Form, ICEDModuloEForm,
    )
    mapa = {}
    idx = 0
    for modulo, clases in (
        ('a', (ICEDModuloAForm,)),
        ('b', (ICEDModuloBForm,)),
        ('c', (ICEDModuloC1Form, ICEDModuloC2Form, ICEDModuloC3Form)),
        ('d', (ICEDModuloD1Form, ICEDModuloD2Form, ICEDModuloD3Form,
               ICEDModuloD4Form)),
        ('e', (ICEDModuloEForm,)),
    ):
        for cls in clases:
            for nombre, campo in cls.declared_fields.items():
                idx += 1
                if nombre not in mapa:
                    mapa[nombre] = {
                        'label': campo.label or nombre,
                        'modulo': modulo,
                        'idx': idx,
                    }
    _MAPA_CAMPOS = mapa
    return mapa


def _num_pregunta_iced(nombre, label=''):
    """Número de pregunta desde el nombre del campo (p8_…) o el label (8. …)."""
    m = re.match(r'p(\d+)', nombre or '')
    if m:
        return int(m.group(1))
    m = re.match(r'\s*(\d+)\.', label or '')
    return int(m.group(1)) if m else 999


@login_required
def iced_historico(request):
    """Respuestas FICED de años anteriores del organismo del usuario.

    Una fila por pregunta; una columna por período (formulario del equipo
    del usuario si existe, si no el consolidado). Don Datico la referencia
    con /iced/historico/?q=N para que el delegado verifique la evidencia.
    """
    organismo = _get_user_organismo(request.user)
    if not organismo:
        if not request.user.is_staff:
            messages.error(request, 'No tiene organismo asignado.')
            return redirect('indicadores:iced_landing')
        org_id = request.GET.get('organismo')
        organismo = Organismo.objects.filter(pk=org_id).first() if org_id else None
        if not organismo:
            return render(request, 'indicadores/iced/historico_respuestas.html', {
                'page': 'iced',
                'organismo': None,
                'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
                'columnas': [], 'filas': [], 'q': '', 'modulo_sel': '',
            })
    equipo = _get_user_equipo(request.user)

    # Un formulario por período: el del equipo del usuario si existe,
    # si no el consolidado; en empate, el de mejor estado.
    por_p = {}
    for f in (ICEDFormulario.objects.filter(organismo=organismo)
              .order_by('periodo', 'equipo')):
        por_p.setdefault(f.periodo, []).append(f)
    columnas = []
    for p in sorted(por_p):
        fs = por_p[p]
        pref = ([f for f in fs if f.equipo == equipo]
                or [f for f in fs if f.equipo == ''] or fs)
        columnas.append({'periodo': p,
                         'form': min(pref, key=lambda f: _ESTADO_RANK.get(f.estado, 9))})

    mapa = _mapa_campos_iced()

    def _valor(form, nombre):
        for cj in _MODULOS_JSON:
            resp = getattr(form, cj) or {}
            if nombre in resp:
                return resp[nombre]
        return None

    def _tiene_valor(v):
        """Respuesta no vacía, tolerando strings JSON vacíos ('[]', '{}')."""
        if v in (None, '', [], {}, '[]', '{}'):
            return False
        if isinstance(v, str):
            try:
                return json.loads(v) not in (None, '', [], {})
            except (ValueError, TypeError):
                return True
        return True

    claves = set()
    for col in columnas:
        for cj in _MODULOS_JSON:
            claves.update((getattr(col['form'], cj) or {}).keys())

    q_filtro = (request.GET.get('q') or '').strip().lstrip('pP')
    mod_filtro = (request.GET.get('modulo') or '').strip().lower()
    orden_mod = {m: i for i, m in enumerate('abcde')}
    filas = []
    for nombre in claves:
        info = mapa.get(nombre)
        label = info['label'] if info else nombre
        modulo = info['modulo'] if info else 'z'
        num = _num_pregunta_iced(nombre, label)
        if q_filtro and str(num) != q_filtro:
            continue
        if mod_filtro and modulo != mod_filtro:
            continue
        valores = [_valor(c['form'], nombre) for c in columnas]
        if not any(_tiene_valor(v) for v in valores):
            continue
        filas.append({
            'campo': nombre, 'label': label, 'num': num,
            'modulo': modulo,
            'valores': [{'respuesta': v, 'field_key': nombre}
                        if _tiene_valor(v) else None
                        for v in valores],
        })
    filas.sort(key=lambda r: (orden_mod.get(r['modulo'], 9), r['num'], r['campo']))

    return render(request, 'indicadores/iced/historico_respuestas.html', {
        'page': 'iced',
        'organismo': organismo,
        'columnas': columnas,
        'filas': filas,
        'q': request.GET.get('q', ''),
        'modulo_sel': mod_filtro,
        'equipo': equipo,
    })


def _get_user_equipo(user):
    """Equipo técnico FICED del usuario (subrol); '' = formulario completo.

    Si el username contiene un código de equipo ('DAP_ETPP'), ese código
    manda sobre el subrol_ficed del perfil y no puede cambiarse desde la UI.
    """
    fijo = equipo_desde_username(getattr(user, 'username', ''))
    if fijo:
        return fijo
    perfil = getattr(user, 'perfil_recolector', None)
    return (getattr(perfil, 'subrol_ficed', '') or '') if perfil else ''


def _get_user_organismo(user):
    """Helper para obtener el organismo del usuario."""
    # Verificar perfil_recolector (modelo principal del proyecto)
    if hasattr(user, 'perfil_recolector') and hasattr(user.perfil_recolector, 'organismo'):
        return user.perfil_recolector.organismo
    # Fallbacks por compatibilidad
    if hasattr(user, 'perfil_delegado') and hasattr(user.perfil_delegado, 'organismo'):
        return user.perfil_delegado.organismo
    if hasattr(user, 'perfil') and hasattr(user.perfil, 'organismo'):
        return user.perfil.organismo
    if user.is_staff:
        from .models import Organismo
        return Organismo.objects.filter(activo=True).first()
    return None


    # Las vistas de validación ICED se encuentran en views_validacion.py,
    # integradas al módulo de validación existente del SIIED.


# =============================================================================
# EXPORTACIÓN CSV DE RESULTADOS ICED
# =============================================================================

@login_required
def iced_exportar_csv(request):
    """
    Exporta resultados ICED en formato CSV oficial.
    Accesible por validadores y delegados.
    Parámetros GET: ?periodo=2026 (opcional)
    """
    import csv
    from django.http import HttpResponse

    periodo = request.GET.get('periodo', '')

    # Determinar acceso: validador ve todo, delegado solo su organismo
    user = request.user
    queryset = ICEDFormulario.objects.filter(estado='validado', equipo='')

    if periodo:
        queryset = queryset.filter(periodo=periodo)

    # Si no es staff/validador, filtrar por organismo del usuario
    if not user.is_staff:
        organismo = _get_user_organismo(user)
        if organismo:
            queryset = queryset.filter(organismo=organismo)
        else:
            queryset = queryset.none()

    queryset = queryset.select_related('organismo').order_by('-puntaje_global')

    # Generar respuesta CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f'resultados_iced_{periodo or "todos"}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(CSV_HEADERS)

    for formulario in queryset:
        try:
            resultado = calcular_iced(formulario)
            fila = resultado_a_fila_csv(formulario, resultado)
            writer.writerow(fila)
        except Exception:
            continue

    return response
