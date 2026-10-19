# -*- coding: utf-8 -*-
"""Servidor MCP del SIIED — capa pública (consulta abierta).

Expone, vía Model Context Protocol, las mismas capacidades de consulta que
usa Don Datico y la API abierta. Cualquier cliente MCP (Claude, ChatGPT,
agentes) puede conectarse sin credenciales a la capa pública.

Los tools delegan en `views_chat.CerebrasToolsService` (los mismos handlers
que usa el chat), por lo que el comportamiento y las URLs generadas son
idénticas al asistente web.

Ejecución:
    python manage.py mcp_server                 # 127.0.0.1:8001, path /mcp
    python manage.py mcp_server --port 9000

En producción se sirve como proceso ASGI aparte (uvicorn) y el proxy dirige
/mcp a ese puerto.
"""
import contextvars
import io
import os
import time
from types import SimpleNamespace

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

import django  # noqa: E402
django.setup()

from asgiref.sync import sync_to_async  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.utils import timezone  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.shared.exceptions import MCPError  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from .models import (  # noqa: E402
    CargaConjuntoDatos, CargaSerieIndicador, ConjuntoDatos, Indicador,
    MCPApiToken, MCPAuditLog, Organismo, Suborganismo)

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False,
    idempotentHint=True, openWorldHint=False,
)

_ESCRITURA = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False,
    idempotentHint=False, openWorldHint=False,
)

# Identidad de la request actual: {'user', 'rol', 'token', 'ip'}.
# La fija el middleware; los tools sincrónicos la leen con .get()
# (anyio propaga contextvars al thread donde corre la tool).
_mcp_identity: contextvars.ContextVar = contextvars.ContextVar(
    'mcp_identity', default=None)

# ----------------------------------------------------------------------
# Gateo por rol — capa pública + capa por roles
# ----------------------------------------------------------------------

_TOOLS_RECOLECTOR = {
    # gestión (lectura)
    'mis_cargas', 'estado_carga', 'mi_contexto',
    # utilidades
    'descargar_plantilla', 'deconstruir_tabla',
    # gestión (escritura — siempre vía borrador a validación)
    'cargar_serie', 'cargar_conjunto_datos', 'cargar_metadata_variables',
}

_TOOLS_VALIDADOR = {
    # consulta FICED / hoja de vida del organismo (solo lectura)
    'listar_organismos_ficed', 'hoja_vida_organismo', 'consultar_ficed',
}

ROLES_TOOLS = {
    'recolector': _TOOLS_RECOLECTOR,
    'ambos': _TOOLS_RECOLECTOR,
    'analista': _TOOLS_RECOLECTOR | _TOOLS_VALIDADOR,
    'editor': set(),                 # Fase D
    'consultor': set(),              # Fase D (reportes)
    'validador': _TOOLS_VALIDADOR,
    'validador_organismo': _TOOLS_VALIDADOR,
    # delegado → sin tools de gestión
}

_TOOLS_PUBLICOS = frozenset({
    'buscar_indicadores', 'consultar_indicador', 'obtener_matriz_indicador',
    'analizar_comparativo', 'explorar_estructura', 'explorar_conjuntos_datos',
    'listar_variables_conjunto_datos', 'obtener_matriz_conjunto_datos',
    'buscar_catalogo_consulta', 'consultar_catalogo_consulta',
    'consultar_sistemas_informacion', 'consultar_operaciones_estadisticas',
    'consultar_ecosistema_datos', 'consultar_producto_academico',
    'buscar_documentos_infraestructura', 'consultar_satisfaccion',
    'consultar_iced',
})


def _tools_del_rol(rol: str) -> set:
    return set(_TOOLS_PUBLICOS) | ROLES_TOOLS.get(rol, set())


async def _resolver_identidad(ctx):
    """Bearer token → {'user', 'rol', 'token', 'ip'}.

    Sin token o token inválido → capa pública (rol 'publico', user None).
    El rol se deriva SIEMPRE del PerfilRecolector vigente del usuario.
    """
    request = getattr(ctx, 'request', None)
    headers = getattr(request, 'headers', None) if request else None
    client = getattr(request, 'client', None) if request else None
    ip = getattr(client, 'host', None) if client else None

    raw = None
    if headers:
        auth = headers.get('authorization', '')
        if auth.lower().startswith('bearer '):
            raw = auth[7:].strip()
    elif not request:
        # Transporte stdio: sin headers HTTP, el token viaja en el entorno
        # del proceso que el cliente spawn-ea (SIIED_MCP_TOKEN).
        raw = os.environ.get('SIIED_MCP_TOKEN') or None
    if raw:
        token = await sync_to_async(MCPApiToken.resolver)(raw)
        if token:
            perfil = getattr(token.user, 'perfil_recolector', None)
            rol = perfil.rol if (perfil and perfil.activo) else 'publico'
            await sync_to_async(token.marcar_uso)(ip)
            return {'user': token.user, 'rol': rol,
                    'token': token, 'ip': ip}
    return {'user': None, 'rol': 'publico', 'token': None, 'ip': ip}


async def _audit(ident, tool, args, exito, duracion_ms, error):
    """Registra la llamada en MCPAuditLog sin tumbar la request."""
    def _crear():
        safe_args = {}
        for k, v in (args or {}).items():
            if isinstance(v, (int, float, bool, list, dict)) or v is None:
                safe_args[k] = v
            else:
                safe_args[k] = str(v)[:300]
        MCPAuditLog.objects.create(
            usuario=ident.get('user'), rol=ident.get('rol', 'publico'),
            tool=str(tool)[:80], argumentos=safe_args, exito=exito,
            duracion_ms=duracion_ms, error=(error or '')[:2000],
            ip=ident.get('ip'))
    try:
        await sync_to_async(_crear)()
    except Exception:
        pass


async def _gate_middleware(ctx, call_next):
    """ServerMiddleware: resuelve identidad, filtra tools/list y veta
    tools/call fuera del rol. Audita cada tools/call en MCPAuditLog."""
    ident = await _resolver_identidad(ctx)
    _mcp_identity.set(ident)

    if ctx.method == 'tools/list':
        result = await call_next(ctx)
        permitidos = _tools_del_rol(ident['rol'])
        tools = getattr(result, 'tools', None)
        if tools is not None:
            return result.model_copy(update={
                'tools': [t for t in tools if t.name in permitidos]})
        if isinstance(result, dict) and 'tools' in result:
            return {**result, 'tools': [
                t for t in result['tools'] if t.get('name') in permitidos]}
        return result

    if ctx.method == 'tools/call':
        params = ctx.params or {}
        nombre = params.get('name', '')
        if nombre not in _tools_del_rol(ident['rol']):
            await _audit(ident, nombre, params.get('arguments'), False, 0,
                         f"Tool vetado para rol '{ident['rol']}'")
            raise MCPError(
                -32001,
                f'El tool "{nombre}" no está disponible para tu nivel de '
                'acceso. Sin token Bearer solo hay tools de consulta pública.')
        t0 = time.monotonic()
        try:
            result = await call_next(ctx)
            ms = int((time.monotonic() - t0) * 1000)
            es_error = bool(
                isinstance(result, dict) and result.get('isError')) or \
                getattr(result, 'isError', False)
            await _audit(ident, nombre, params.get('arguments'),
                         not es_error, ms, 'tool_error' if es_error else '')
            return result
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            await _audit(ident, nombre, params.get('arguments'),
                         False, ms, str(exc)[:2000])
            raise

    return await call_next(ctx)


def _build_server() -> MCPServer:
    """Construye el MCPServer con los tools de la capa pública."""
    from .views_chat import CerebrasToolsService

    service = CerebrasToolsService(
        api_key='mcp-interno',
        base_url=getattr(settings, 'SITE_URL', ''),
    )

    # Helpers del módulo de recolección (import diferido: módulo pesado).
    # Los tools de gestión replican exactamente el flujo de las vistas:
    # generar xlsx → guardar FileField → procesar_* → notificar admins.
    from .views_recoleccion import (
        _dt_process_sheet, _generar_xlsx_datos, _generar_xlsx_variables,
        procesar_conjunto_datos, procesar_serie_indicador)

    server = MCPServer(
        name='siied',
        title='SIIED — Sistema Distrital de Información Estadística',
        description=(
            'Consulta abierta del catálogo estadístico del SIIED: indicadores '
            'con sus series, conjuntos de datos, catálogo de consulta, '
            'estructura de dominios/temas, sistemas de información y más.'
        ),
        instructions=(
            'Herramientas de SOLO LECTURA sobre los datos abiertos del SIIED. '
            'Para encontrar indicadores usa buscar_indicadores o '
            'explorar_estructura; luego consultar_indicador da la ficha y las '
            'series. Los indicadores enlazados al catálogo de consulta no '
            'tienen series: su información son las filas del conjunto '
            '(consultar_catalogo_consulta).'
        ),
        version='1.0.0',
        middleware=[_gate_middleware],
    )

    def call(name, **arguments):
        """Ejecuta un handler del servicio de tools (omite args None)."""
        args = {k: v for k, v in arguments.items() if v is not None}
        tool_call = SimpleNamespace(
            function=SimpleNamespace(name=name, arguments=args))
        return service.execute_tool_call(tool_call)

    # --------------------------------------------------------------
    # Indicadores
    # --------------------------------------------------------------

    @server.tool(annotations=_READ_ONLY)
    def buscar_indicadores(consulta: str, limite: int = 10) -> dict:
        """Busca indicadores activos CON DATOS por nombre, tema o palabras
        clave (búsqueda semántica + texto). Devuelve metadatos básicos y
        enlaces a la ficha ('url' estándar, 'url_3d' didáctica)."""
        return call('buscar_indicadores', consulta=consulta, limite=limite)

    @server.tool(annotations=_READ_ONLY)
    def consultar_indicador(indicador_id: int, ano_inicio: int = None,
                            ano_fin: int = None, limite: int = 100) -> dict:
        """Datos completos de un indicador: valores históricos, metadatos,
        desagregaciones disponibles y últimas cifras. Usa el indicador_id
        devuelto por buscar_indicadores."""
        return call('consultar_indicador', indicador_id=indicador_id,
                    **{'año_inicio': ano_inicio, 'año_fin': ano_fin},
                    limite=limite)

    @server.tool(annotations=_READ_ONLY)
    def obtener_matriz_indicador(indicador_id: int, ano_inicio: int = None,
                                 ano_fin: int = None,
                                 incluir_desagregaciones: bool = True) -> dict:
        """Matriz (tabla) de datos de un indicador con filas por año y
        columnas por desagregación — formato tabular para análisis."""
        return call('obtener_matriz_indicador', indicador_id=indicador_id,
                    **{'año_inicio': ano_inicio, 'año_fin': ano_fin},
                    incluir_desagregaciones=incluir_desagregaciones)

    @server.tool(annotations=_READ_ONLY)
    def analizar_comparativo(indicadores_ids: list,
                             tipo_analisis: str = 'temporal') -> dict:
        """Análisis comparativo entre varios indicadores (por ids).
        tipo_analisis: temporal | desagregacion | correlacion."""
        return call('analizar_comparativo', indicadores_ids=indicadores_ids,
                    tipo_analisis=tipo_analisis)

    # --------------------------------------------------------------
    # Estructura del catálogo
    # --------------------------------------------------------------

    @server.tool(annotations=_READ_ONLY)
    def explorar_estructura(nivel: str = None, dominio_id: int = None,
                            tema_id: int = None,
                            incluir_indicadores: bool = False) -> dict:
        """Explora la jerarquía dominios → temas → subtemas del SIIED.
        nivel: dominios | temas | subtemas. Usar para descubrir QUÉ temas
        existen antes de buscar indicadores concretos."""
        return call('explorar_estructura', nivel=nivel,
                    dominio_id=dominio_id, tema_id=tema_id,
                    incluir_indicadores=incluir_indicadores)

    # --------------------------------------------------------------
    # Conjuntos de datos
    # --------------------------------------------------------------

    @server.tool(annotations=_READ_ONLY)
    def explorar_conjuntos_datos(accion: str = 'listar',
                                 conjunto_datos: str = None) -> dict:
        """Lista los conjuntos de datos o explora uno concreto.
        accion: listar | explorar (requiere conjunto_datos = nombre)."""
        return call('explorar_conjuntos_datos', accion=accion,
                    conjunto_datos=conjunto_datos)

    @server.tool(annotations=_READ_ONLY)
    def listar_variables_conjunto_datos(conjunto_datos_id: int) -> dict:
        """Variables (columnas) disponibles en un conjunto de datos."""
        return call('listar_variables_conjunto_datos',
                    conjunto_datos_id=conjunto_datos_id)

    @server.tool(annotations=_READ_ONLY)
    def obtener_matriz_conjunto_datos(conjunto_datos_id: int,
                                      variables: list = None,
                                      muestra: int = 500) -> dict:
        """Filas (matriz) de un conjunto de datos, opcionalmente solo las
        columnas indicadas en `variables`."""
        return call('obtener_matriz_conjunto_datos',
                    conjunto_datos_id=conjunto_datos_id,
                    variables=variables, muestra=muestra)

    # --------------------------------------------------------------
    # Catálogo de consulta (directorios/listados, ex-anuario CEC)
    # --------------------------------------------------------------

    @server.tool(annotations=_READ_ONLY)
    def buscar_catalogo_consulta(consulta: str, limite: int = 10) -> dict:
        """Busca conjuntos del catálogo de consulta (nomencladores,
        directorios, inventarios, fichas territoriales) por texto."""
        return call('buscar_catalogo_consulta', consulta=consulta,
                    limite=limite)

    @server.tool(annotations=_READ_ONLY)
    def consultar_catalogo_consulta(conjunto_id: int, filtro: str = None,
                                    limite: int = None) -> dict:
        """Filas de un conjunto del catálogo de consulta por id.
        `filtro` reduce las filas a las que contienen el texto."""
        return call('consultar_catalogo_consulta', conjunto_id=conjunto_id,
                    filtro=filtro, limite=limite)

    # --------------------------------------------------------------
    # Otros consultables
    # --------------------------------------------------------------

    @server.tool(annotations=_READ_ONLY)
    def consultar_sistemas_informacion(tipo: str = 'todos',
                                       consulta: str = None) -> dict:
        """Sistemas de consulta y proyectos de información del SIIED y otras
        dependencias: visualizadores, observatorios, aplicaciones."""
        return call('consultar_sistemas_informacion', tipo=tipo,
                    consulta=consulta)

    @server.tool(annotations=_READ_ONLY)
    def consultar_operaciones_estadisticas(consulta: str = None,
                                           organismo: str = None,
                                           limite: int = 15) -> dict:
        """Operaciones estadísticas registradas (encuestas, registros
        administrativos, censos) con su organismo responsable."""
        return call('consultar_operaciones_estadisticas', consulta=consulta,
                    organismo=organismo, limite=limite)

    @server.tool(annotations=_READ_ONLY)
    def consultar_ecosistema_datos(organismo: str,
                                   aspecto: str = 'resumen') -> dict:
        """Ecosistema de datos de un organismo: capacidad, operaciones
        estadísticas y entregas al SIIED."""
        return call('consultar_ecosistema_datos', organismo=organismo,
                    aspecto=aspecto)

    @server.tool(annotations=_READ_ONLY)
    def consultar_producto_academico(consulta: str = None,
                                     producto_id: int = None) -> dict:
        """Productos académicos/publicaciones del SIIED (libros, guías,
        boletines) por texto o por id."""
        return call('consultar_producto_academico', consulta=consulta,
                    producto_id=producto_id)

    @server.tool(annotations=_READ_ONLY)
    def buscar_documentos_infraestructura(consulta: str = None,
                                          area: str = None,
                                          tipo_documento: str = None,
                                          limite: int = 10) -> dict:
        """Documentos de infraestructura estadística: procesos, manuales,
        metodologías, guías y formatos institucionales."""
        return call('buscar_documentos_infraestructura', consulta=consulta,
                    area=area, tipo_documento=tipo_documento, limite=limite)

    @server.tool(annotations=_READ_ONLY)
    def consultar_satisfaccion(organismo: str = None,
                               periodo_meses: int = 12) -> dict:
        """Resultados de las encuestas de satisfacción del servicio
        estadístico por organismo y periodo."""
        return call('consultar_satisfaccion', organismo=organismo,
                    periodo_meses=periodo_meses)

    @server.tool(annotations=_READ_ONLY)
    def consultar_iced(organismo: str = None, periodo: str = None,
                       incluir_subdimensiones: bool = False) -> dict:
        """Resultados del ICED/FICED (capacidad estadística distrital) por
        organismo y periodo de medición."""
        return call('consultar_iced', organismo=organismo, periodo=periodo,
                    incluir_subdimensiones=incluir_subdimensiones)

    # ==============================================================
    # CAPA POR ROLES — recolector (piloto). Requieren Bearer MCP.
    # ==============================================================

    def _usuario_mcp():
        """Usuario resuelto por el middleware para esta request."""
        ident = _mcp_identity.get() or {}
        return ident.get('user')

    @server.tool(annotations=_READ_ONLY)
    def mis_cargas(limite: int = 20) -> dict:
        """[rol: recolector] Tus cargas de series y conjuntos de datos con
        su estado en el workflow (pendiente → validación → procesado),
        evidencias y resultados."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        limite = max(1, min(int(limite or 20), 100))
        series = (CargaSerieIndicador.objects
                  .filter(usuario=user)
                  .select_related('indicador')
                  .order_by('-fecha_carga')[:limite])
        conjuntos = (CargaConjuntoDatos.objects
                     .filter(usuario=user)
                     .select_related('conjunto_datos')
                     .order_by('-fecha_carga')[:limite])
        return {
            'usuario': user.username,
            'series': [{
                'id': c.pk, 'tipo': 'serie',
                'indicador': c.indicador.nombre if c.indicador_id else None,
                'estado': c.estado,
                'codigo_evidencia': c.codigo_evidencia,
                'fecha_carga': c.fecha_carga.isoformat(),
                'registros': {
                    'procesados': c.registros_procesados,
                    'exitosos': c.registros_exitosos,
                    'error': c.registros_error,
                },
            } for c in series],
            'conjuntos_datos': [{
                'id': c.pk, 'tipo': 'conjunto_datos',
                'conjunto_datos': (c.conjunto_datos.nombre
                                   if c.conjunto_datos_id else None),
                'estado': c.estado,
                'codigo_evidencia': c.codigo_evidencia,
                'fecha_carga': c.fecha_carga.isoformat(),
                'registros': {
                    'procesados': c.registros_procesados,
                    'exitosos': c.registros_exitosos,
                    'error': c.registros_error,
                },
            } for c in conjuntos],
        }

    @server.tool(annotations=_READ_ONLY)
    def mi_contexto() -> dict:
        """[rol: recolector] Tu perfil: organismo, indicadores responsables,
        suborganismos y conjuntos de datos producidos. Útil para orientar
        cargas y actualizaciones."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        perfil = getattr(user, 'perfil_recolector', None)
        org = perfil.organismo if (perfil and perfil.organismo_id) else None
        indicadores = []
        conjuntos = []
        subs = []
        if org:
            indicadores = list(
                Indicador.objects
                .filter(organismo_responsable=org, activo=True)
                .values('id', 'codigo_indicador', 'nombre')
                .order_by('codigo_indicador')[:200])
            subs = list(
                Suborganismo.objects
                .filter(organismo_id=org.pk, activo=True)
                .values('id', 'nombre').order_by('nombre'))
            conjuntos = list(
                ConjuntoDatos.objects
                .filter(organismo_productor=org)
                .values('id', 'nombre')
                .order_by('nombre')[:200])
        return {
            'usuario': user.username,
            'nombre': user.get_full_name(),
            'rol': perfil.rol if perfil else None,
            'institucion': perfil.institucion if perfil else None,
            'organismo': org.nombre if org else None,
            'suborganismos': subs,
            'indicadores_responsables': indicadores,
            'conjuntos_datos_producidos': conjuntos,
            'nota': ('Sin organismo vinculado en el perfil las listas vienen '
                     'vacías.' if not org else
                     'Son los indicadores/conjuntos de TU organismo; la carga '
                     'puede apuntar a cualquiera de ellos.'),
        }

    @server.tool(annotations=_READ_ONLY)
    def descargar_plantilla(tipo: str) -> dict:
        """[rol: recolector] Estructura de columnas de una plantilla oficial
        de carga y su URL de descarga. tipo: serie_datos | metadata_indicador |
        masiva_datos | masiva_metadata | conjunto_datos | metadata_variables."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        from django.urls import reverse
        base = getattr(settings, 'SITE_URL', '').rstrip('/')
        rutas = {
            'serie_datos': (
                'descargar_plantilla_serie_datos',
                ['Año', 'Valor', '<desagregación 1>', '<desagregación N>']),
            'metadata_indicador': (
                'descargar_plantilla_metadata_indicador',
                None),
            'masiva_datos': ('descargar_plantilla_masiva_datos', None),
            'masiva_metadata': ('descargar_plantilla_masiva_metadata', None),
            'conjunto_datos': (
                'descargar_plantilla_conjunto_datos',
                ['<una columna por variable del microdato>']),
            'metadata_variables': (
                'descargar_plantilla_metadata_variables',
                ['Codigo_Variable', 'Nombre_Variable',
                 'Definicion_Conceptual', 'Tipo_Dato', 'Unidad_Medida',
                 'Periodicidad', 'Fuente_Datos', 'Organismo_Productor',
                 'Observaciones', 'Referencias']),
        }
        if tipo not in rutas:
            return {'error': f'Tipo inválido: {tipo}',
                    'tipos_validos': sorted(rutas)}
        name, cols = rutas[tipo]
        try:
            url = reverse(f'indicadores:{name}')
        except Exception:
            url = None
        return {
            'tipo': tipo,
            'columnas': cols or 'Ver la plantilla oficial para las columnas.',
            'url_descarga': (base + url) if (url and base) else url,
        }

    @server.tool(annotations=_READ_ONLY)
    def deconstruir_tabla(contenido: str,
                          nombres_grupos: dict = None,
                          indicador_id: int = None) -> dict:
        """[rol: recolector] Deconstruye una tabla dinámica (pivot) al
        formato plano que exige la carga de series (Año + desagregaciones +
        Valor). Pega la tabla como texto CSV/TSV en `contenido`.
        nombres_grupos: {'0': 'Clase', '1': 'Subclase', '2': 'Categoria'}
        nombran las columnas de desagregación del resultado."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        if not contenido or not contenido.strip():
            return {'error': 'contenido vacío: pega la tabla como CSV/TSV.'}
        gnames = {str(k): v for k, v in (nombres_grupos or {}).items()}
        codigo = nombre = None
        if indicador_id:
            ind = Indicador.objects.filter(pk=indicador_id).first()
            if ind:
                codigo, nombre = ind.codigo_indicador, ind.nombre
        archivo = io.BytesIO(contenido.encode('utf-8'))
        archivo.name = 'tabla.csv'  # _dt_read_raw detecta el tipo por nombre
        try:
            result = _dt_process_sheet(
                archivo, 0, gnames, codigo, nombre)
        except Exception as e:
            return {'error': f'No se pudo deconstruir la tabla: {e}'}
        if result is None or result.empty:
            return {'error': 'No se generaron datos. Revisa la tabla.'}
        return {
            'filas': len(result),
            'columnas': list(result.columns),
            'csv': result.to_csv(index=False, sep=';'),
            'nota': 'Este CSV plano ya sirve como `filas` de cargar_serie.',
        }

    @server.tool(annotations=_ESCRITURA)
    def cargar_serie(indicador_id: int, filas: list,
                     desagregaciones: list = None,
                     dry_run: bool = True) -> dict:
        """[rol: recolector] Carga filas de una serie de indicador.
        Crea una CargaSerieIndicador que queda PENDIENTE de validación —
        igual que la carga web; nada se publica sin el validador.

        filas: [{'fecha': '2023', 'valor': 12.5, 'des_Localidad': '01'}, ...]
        desagregaciones: nombres de las dimensiones usadas en des_*
        dry_run=True solo valida; dry_run=False crea la carga."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        indicador = Indicador.objects.filter(pk=indicador_id).first()
        if not indicador:
            return {'error': f'Indicador {indicador_id} no existe.'}
        if not filas:
            return {'error': 'filas vacío: envía al menos un registro.'}
        desags = [d.strip() for d in (desagregaciones or []) if str(d).strip()]
        filas_ok = []
        for i, f in enumerate(filas):
            if not isinstance(f, dict) or 'fecha' not in f or 'valor' not in f:
                return {'error': f'Fila {i} sin claves fecha/valor.'}
            filas_ok.append(f)
        if dry_run:
            return {
                'dry_run': True, 'ok': True,
                'indicador': indicador.nombre,
                'filas': len(filas_ok), 'desagregaciones': desags,
                'columnas': ['Año', 'Valor'] + desags,
                'nota': 'Validación OK. Repite con dry_run=False para crear '
                        'la carga (quedará pendiente de validación).',
            }
        try:
            buf = _generar_xlsx_datos(filas_ok, desagregaciones=desags)
            carga = CargaSerieIndicador(
                usuario=user, indicador=indicador,
                estado='procesando', es_carga_delegado=False)
            carga.archivo_datos_xlsx.save(
                f"datos_mcp_{indicador.codigo_indicador}_"
                f"{timezone.now().strftime('%Y%m%d%H%M%S')}.xlsx",
                ContentFile(buf.read()), save=False)
            carga.save()
            procesar_serie_indicador(carga)
            try:
                from .notifications import (
                    notificar_admins_nueva_carga_recoleccion_serie)
                notificar_admins_nueva_carga_recoleccion_serie(carga)
            except Exception:
                pass
            return {
                'ok': carga.estado != 'error',
                'carga_id': carga.pk,
                'estado': carga.estado,
                'codigo_evidencia': carga.codigo_evidencia,
                'registros': carga.registros_procesados,
                'error': carga.mensaje_error,
                'nota': 'La carga quedó pendiente de validación. '
                        'Consulta estado_carga para seguimiento.',
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    @server.tool(annotations=_ESCRITURA)
    def cargar_conjunto_datos(microdata: list, variables: list,
                              tipo_carga: str = 'nueva',
                              indicadores_ids: list = None,
                              conjunto_datos_id: int = None,
                              dry_run: bool = True) -> dict:
        """[rol: recolector] Carga un conjunto de datos (microdata) con la
        metadata de sus variables. Crea CargaConjuntoDatos pendiente de
        validación.

        tipo_carga: nueva (crea conjunto, exige indicadores_ids) |
                    actualizacion (actualiza conjunto_datos_id existente)
        microdata: [{'col1': v, 'col2': v}, ...] — columnas libres
        variables: [{'Codigo_Variable': ..., 'Nombre_Variable': ...,
                     'Definicion_Conceptual': ..., 'Tipo_Dato': ...,
                     'Unidad_Medida': ..., 'Periodicidad': ...,
                     'Fuente_Datos': ..., 'Organismo_Productor': ...,
                     'Observaciones': ..., 'Referencias': ...}, ...]"""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        if not microdata or not variables:
            return {'error': 'Se requieren microdata y variables (metadata).'}
        if tipo_carga == 'nueva':
            ids = [int(i) for i in (indicadores_ids or [])]
            if not ids:
                return {'error': 'tipo_carga=nueva exige indicadores_ids.'}
            existentes = Indicador.objects.filter(id__in=ids).count()
            if existentes != len(ids):
                return {'error': 'Algún ID de indicador no existe.',
                        'ids': ids}
            conjunto = None
        elif tipo_carga == 'actualizacion':
            conjunto = ConjuntoDatos.objects.filter(
                pk=conjunto_datos_id).first()
            if not conjunto:
                return {'error': f'ConjuntoDatos {conjunto_datos_id} '
                                 'no existe.'}
        else:
            return {'error': "tipo_carga debe ser 'nueva' o 'actualizacion'."}
        if dry_run:
            cols_micro = list(dict.fromkeys(
                k for f in microdata for k in f.keys()))
            return {
                'dry_run': True, 'ok': True, 'tipo_carga': tipo_carga,
                'filas_microdata': len(microdata),
                'columnas_microdata': cols_micro,
                'variables': len(variables),
                'conjunto_datos': (conjunto.nombre if conjunto else
                                   '(se creará en validación)'),
                'nota': 'Repite con dry_run=False para crear la carga.',
            }
        try:
            import openpyxl
            cols_micro = list(dict.fromkeys(
                k for f in microdata for k in f.keys()))
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'Microdata'
            ws.append(cols_micro)
            for f in microdata:
                ws.append([f.get(c, '') for c in cols_micro])
            buf_micro = io.BytesIO()
            wb.save(buf_micro)
            buf_micro.seek(0)

            buf_vars = _generar_xlsx_variables(variables)
            ts = timezone.now().strftime('%Y%m%d%H%M%S')
            carga = CargaConjuntoDatos(
                usuario=user, estado='procesando',
                conjunto_datos=conjunto)
            carga.archivo_microdata_xlsx.save(
                f'microdata_mcp_{ts}.xlsx',
                ContentFile(buf_micro.read()), save=False)
            carga.archivo_metadata_variables_xlsx.save(
                f'variables_mcp_{ts}.xlsx',
                ContentFile(buf_vars.read()), save=False)
            carga.save()
            if tipo_carga == 'nueva':
                carga.log_procesamiento = (
                    'Indicadores relacionados: '
                    + ','.join(str(i) for i in indicadores_ids))
                carga.save(update_fields=['log_procesamiento'])
            procesar_conjunto_datos(carga)
            try:
                from .notifications import (
                    notificar_admins_nueva_carga_recoleccion_conjunto_datos)
                notificar_admins_nueva_carga_recoleccion_conjunto_datos(carga)
            except Exception:
                pass
            return {
                'ok': carga.estado != 'error',
                'carga_id': carga.pk, 'estado': carga.estado,
                'codigo_evidencia': carga.codigo_evidencia,
                'registros': carga.registros_procesados,
                'error': carga.mensaje_error,
                'nota': 'La carga quedó pendiente de validación.',
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    @server.tool(annotations=_ESCRITURA)
    def cargar_metadata_variables(variables: list,
                                  carga_id: int = None,
                                  conjunto_datos_id: int = None,
                                  dry_run: bool = True) -> dict:
        """[rol: recolector] Adjunta/actualiza la metadata de variables de un
        conjunto de datos — sobre una carga propia (carga_id) o como carga
        nueva ligada a un conjunto_datos existente (conjunto_datos_id).

        variables: [{'Codigo_Variable': ..., 'Nombre_Variable': ...,
                     'Definicion_Conceptual': ..., 'Tipo_Dato': ...,
                     'Unidad_Medida': ..., 'Periodicidad': ...,
                     'Fuente_Datos': ..., 'Organismo_Productor': ...,
                     'Observaciones': ..., 'Referencias': ...}, ...]
        Si el conjunto ya tiene variables, solo se aceptan Codigo_Variable
        existentes (misma regla que el formulario web)."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        if not variables:
            return {'error': 'variables vacío.'}
        conjunto = None
        if conjunto_datos_id:
            conjunto = ConjuntoDatos.objects.filter(
                pk=conjunto_datos_id).first()
            if not conjunto:
                return {'error': f'ConjuntoDatos {conjunto_datos_id} '
                                 'no existe.'}
        # Regla del formulario web: solo variables ya existentes
        codigos_exist = set()
        if conjunto is not None:
            codigos_exist = set(conjunto.variables.values_list(
                'codigo_variable', flat=True))
        nuevos = [v.get('Codigo_Variable') for v in variables
                  if codigos_exist
                  and v.get('Codigo_Variable') not in codigos_exist]
        if nuevos:
            return {'error': 'Códigos no existentes en el conjunto',
                    'codigos_invalidos': nuevos,
                    'codigos_validos': sorted(codigos_exist)}
        if carga_id:
            carga = CargaConjuntoDatos.objects.filter(
                pk=carga_id, usuario=user).first()
            if not carga:
                return {'error': 'Carga no encontrada entre tus cargas.'}
        else:
            carga = None
        if dry_run:
            return {
                'dry_run': True, 'ok': True,
                'variables': len(variables),
                'destino': (f'carga {carga_id}' if carga else
                            f'conjunto_datos {conjunto_datos_id}'
                            if conjunto else 'carga nueva sin conjunto'),
                'nota': 'Repite con dry_run=False para guardar.',
            }
        try:
            buf = _generar_xlsx_variables(variables)
            ts = timezone.now().strftime('%Y%m%d%H%M%S')
            if carga is None:
                carga = CargaConjuntoDatos(
                    usuario=user, estado='procesando',
                    conjunto_datos=conjunto)
            carga.archivo_metadata_variables_xlsx.save(
                f'variables_mcp_{ts}.xlsx',
                ContentFile(buf.read()), save=False)
            carga.save()
            return {
                'ok': True, 'carga_id': carga.pk, 'estado': carga.estado,
                'codigo_evidencia': carga.codigo_evidencia,
                'variables': len(variables),
                'nota': 'Metadata de variables adjuntada a la carga.',
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ==============================================================
    # CAPA POR ROLES — validador: hoja de vida FICED del organismo.
    # ==============================================================

    def _ficed_payload(f):
        """Resumen de un formulario FICED consolidado."""
        return {
            'id': f.pk, 'periodo': f.periodo, 'estado': f.estado,
            'puntaje_global': (float(f.puntaje_global)
                               if f.puntaje_global is not None else None),
            'puntajes_modulos': {
                'B_entorno_institucional': (float(f.puntaje_b)
                                            if f.puntaje_b is not None
                                            else None),
                'C_infraestructura': (float(f.puntaje_c)
                                      if f.puntaje_c is not None else None),
                'D_metodologia': (float(f.puntaje_d)
                                  if f.puntaje_d is not None else None),
                'E_accesibilidad_uso': (float(f.puntaje_e)
                                        if f.puntaje_e is not None else None),
            },
            'fecha_envio': (f.fecha_envio.isoformat()
                            if f.fecha_envio else None),
            'fecha_validacion': (f.fecha_validacion.isoformat()
                                 if f.fecha_validacion else None),
        }

    @server.tool(annotations=_READ_ONLY)
    def listar_organismos_ficed(periodo: str = None,
                                solo_con_ficed: bool = False) -> dict:
        """[rol: validador] Organismos del ecosistema con su FICED
        consolidado más reciente (o del `periodo` indicado): estado y
        puntaje global. Base para navegar a hoja_vida_organismo."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        from .models_iced import ICEDFormulario

        fichados = {}
        qs = ICEDFormulario.objects.filter(equipo='')
        if periodo:
            qs = qs.filter(periodo=periodo)
        for f in qs.order_by('-periodo').select_related('organismo'):
            if f.organismo_id not in fichados:
                fichados[f.organismo_id] = f
        orgs = Organismo.objects.filter(activo=True).order_by('nombre')
        resultado = []
        for o in orgs:
            f = fichados.get(o.pk)
            if solo_con_ficed and not f:
                continue
            resultado.append({
                'codigo': o.codigo, 'nombre': o.nombre,
                'ficed': (_ficed_payload(f) if f else None),
            })
        return {'total': len(resultado), 'organismos': resultado}

    @server.tool(annotations=_READ_ONLY)
    def hoja_vida_organismo(codigo: str) -> dict:
        """[rol: validador] Hoja de vida completa del organismo:
        indicadores responsables, inscripciones al taller (F1/F2/F3),
        satisfacción, flujos de datos, métricas del ecosistema e historial
        FICED. Equivale a la vista web organismo_detalle."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        from django.db.models import Avg, Count
        from .models import (RespuestaSatisfaccionCompleta,
                             RespuestaSatisfaccionRapida)
        from .models_catalogo import FuenteDatos, FuenteOrigen
        from .models_iced import ICEDFormulario
        from .models_taller import InscripcionTaller
        from .views import (
            calcular_densidad_red, calcular_indice_madurez_ecosistema,
            obtener_diversidad_datos, obtener_flujos_externos,
            obtener_flujos_internos, obtener_roles_identificados)

        org = Organismo.objects.filter(codigo=codigo, activo=True).first()
        if not org:
            return {'error': f'Organismo "{codigo}" no existe o inactivo.'}

        indicadores = list(
            Indicador.objects
            .filter(organismo_responsable=org)
            .values('id', 'codigo_indicador', 'nombre',
                    'fecha_actualizacion_ficha')
            .order_by('-fecha_actualizacion_ficha')[:15])
        sesiones = list(
            InscripcionTaller.objects
            .filter(organismo=org)
            .annotate(num_fuentes=Count('fuentes', distinct=True))
            .values('id', 'estado', 'num_fuentes', 'creado',
                    'suborganismo__nombre', 'equipo__nombre')
            .order_by('-creado')[:15])
        for s in sesiones:
            s['creado'] = s['creado'].isoformat() if s['creado'] else None

        rapidas = RespuestaSatisfaccionRapida.objects.filter(organismo=org)
        completas = RespuestaSatisfaccionCompleta.objects.filter(organismo=org)
        fuentes = FuenteDatos.objects.filter(inscripcion__organismo=org)
        ficed_hist = [_ficed_payload(f) for f in
                      ICEDFormulario.objects
                      .filter(organismo=org, equipo='',
                              estado__in=['validado', 'enviado'])
                      .order_by('-periodo')]

        return {
            'organismo': {'codigo': org.codigo, 'nombre': org.nombre},
            'indicadores_responsables': {
                'total': Indicador.objects.filter(
                    organismo_responsable=org).count(),
                'recientes': indicadores,
            },
            'taller_gestion_datos': {
                'sesiones': len(sesiones), 'detalle': sesiones,
            },
            'satisfaccion': {
                'respuestas_rapidas': rapidas.count(),
                'respuestas_completas': completas.count(),
                'promedio_rapida': (
                    rapidas.aggregate(Avg('calificacion'))[
                        'calificacion__avg'] or 0),
                'distribucion_rapida': {
                    str(c): rapidas.filter(calificacion=c).count()
                    for c in range(1, 6)},
            },
            'ecosistema_datos': {
                'indice_madurez': calcular_indice_madurez_ecosistema(org),
                'roles_identificados': obtener_roles_identificados(org),
                'flujos_internos': obtener_flujos_internos(org),
                'flujos_externos': obtener_flujos_externos(org),
                'densidad_red': calcular_densidad_red(org),
                'diversidad_datos': obtener_diversidad_datos(org),
                'fuentes_caracterizadas': fuentes.count(),
                'fuentes_recibe': fuentes.filter(
                    rol__in=['usuario', 'ambos']).count(),
                'fuentes_envia': fuentes.filter(
                    rol__in=['productor', 'ambos']).count(),
                'fuentes_origen_declaradas': FuenteOrigen.objects.filter(
                    fuente__inscripcion__organismo=org).count(),
            },
            'ficed': {
                'historico': ficed_hist,
                'nota': ('Usa consultar_ficed para ver un formulario '
                         'completo (respuestas A-E, puntajes por '
                         'indicador, RRHH y contactos).'),
            },
        }

    @server.tool(annotations=_READ_ONLY)
    def consultar_ficed(codigo: str = None, periodo: str = None,
                        formulario_id: int = None,
                        incluir_respuestas: bool = False) -> dict:
        """[rol: validador] Formulario FICED consolidado de un organismo:
        puntajes por indicador (con nombre legible), respuestas por módulo
        A-E, equipo humano declarado, contactos y trazabilidad de
        validación. `codigo` = código del organismo."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        from .models_iced import (
            ICEDFormulario, ICEDPersonaContacto, ICEDRecursoHumano)

        if formulario_id:
            f = ICEDFormulario.objects.filter(
                pk=formulario_id, equipo='').first()
        elif codigo:
            qs = ICEDFormulario.objects.filter(
                organismo__codigo=codigo, equipo='')
            if periodo:
                qs = qs.filter(periodo=periodo)
            f = qs.order_by('-periodo').first()
        else:
            return {'error': 'Indica codigo del organismo o formulario_id.'}
        if not f:
            return {'error': 'No hay FICED consolidado para esos filtros.'}

        rrhh = list(ICEDRecursoHumano.objects
                    .filter(formulario=f)
                    .values('nombre_completo', 'correo', 'grupo',
                            'anios_experiencia', 'tipo_vinculacion',
                            'categoria_cargo', 'nivel_formacion',
                            'etapas_proceso', 'funciones_estadisticas'))
        contactos = list(ICEDPersonaContacto.objects
                         .filter(formulario=f).order_by('orden')
                         .values('nombre_completo', 'cargo', 'correo',
                                 'telefono'))

        # Puntajes por indicador con nombre legible
        from .calcular_iced import INDICADOR_LABELS
        detalle = f.puntajes_detalle or {}
        puntajes = {}
        for cod, val in (detalle.get('por_indicador')
                         or detalle.get('indicadores') or {}).items():
            puntajes[cod] = {
                'nombre': INDICADOR_LABELS.get(cod, ''),
                'puntaje': val if not isinstance(val, dict)
                           else val.get('puntaje', val),
            }
        if not puntajes and detalle:
            puntajes = detalle  # forma desconocida: devolver crudo

        payload = {
            'formulario': _ficed_payload(f),
            'organismo': f.organismo.nombre,
            'diligenciado_por': (
                f.usuario_diligencia.get_full_name()
                if f.usuario_diligencia_id else None),
            'observaciones_validador': f.observaciones_validador,
            'puntajes_por_indicador': puntajes,
            'recurso_humano': rrhh,
            'contactos': contactos,
        }
        if incluir_respuestas:
            payload['respuestas'] = {
                'A_identificacion': f.respuestas_a,
                'B_entorno_institucional': f.respuestas_b,
                'C_infraestructura': f.respuestas_c,
                'D_metodologia': f.respuestas_d,
                'E_accesibilidad_uso': f.respuestas_e,
            }
        return payload

    @server.tool(annotations=_READ_ONLY)
    def estado_carga(carga_id: int, tipo: str = 'serie') -> dict:
        """[rol: recolector] Estado detallado de UNA de tus cargas:
        registros, errores y observaciones del validador.
        tipo: serie | conjunto_datos."""
        user = _usuario_mcp()
        if not user:
            return {'error': 'Requiere token MCP con rol autorizado.'}
        if tipo == 'conjunto_datos':
            carga = (CargaConjuntoDatos.objects
                     .filter(pk=carga_id, usuario=user)
                     .select_related('conjunto_datos', 'validado_por')
                     .first())
            objeto = carga.conjunto_datos.nombre if (
                carga and carga.conjunto_datos_id) else None
        else:
            carga = (CargaSerieIndicador.objects
                     .filter(pk=carga_id, usuario=user)
                     .select_related('indicador', 'validado_por')
                     .first())
            objeto = carga.indicador.nombre if (
                carga and carga.indicador_id) else None
        if not carga:
            return {'error': 'Carga no encontrada entre tus cargas.',
                    'carga_id': carga_id, 'tipo': tipo}
        return {
            'id': carga.pk, 'tipo': tipo, 'objeto': objeto,
            'estado': carga.estado,
            'codigo_evidencia': carga.codigo_evidencia,
            'fecha_carga': carga.fecha_carga.isoformat(),
            'fecha_procesamiento': (
                carga.fecha_procesamiento.isoformat()
                if carga.fecha_procesamiento else None),
            'registros': {
                'procesados': carga.registros_procesados,
                'exitosos': carga.registros_exitosos,
                'error': carga.registros_error,
            },
            'mensaje_error': carga.mensaje_error,
            'validado_por': (
                carga.validado_por.get_full_name()
                if carga.validado_por_id else None),
            'fecha_validacion': (
                carga.fecha_validacion.isoformat()
                if carga.fecha_validacion else None),
            'observaciones_validador': carga.observaciones_validador,
        }

    return server


# Instancia única para `python manage.py mcp_server` y para uvicorn.
server = _build_server()

# ASGI app (streamable HTTP, JSON sin sesiones) para `uvicorn ...:app`
app = server.streamable_http_app(
    streamable_http_path='/mcp', json_response=True, stateless_http=True,
    host='127.0.0.1')
