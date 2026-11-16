# Plan — Módulo «Gestión de Formularios»

Objetivo: que los operadores del SIIED gestionen FICED, Taller de Gestión de
Datos y encuestas propias **sin entrar al admin de Django**, con un rol
dedicado, auditoría de cada acción y un constructor de formularios propio.

---

## 0.1 Estado de implementación (nov-2026)

- **F0 Cimientos** — roles `gestor_formularios`, `diligenciador`,
  `encuestador`; contraseña temporal obligatoria; bitácora
  (`registrar_accion`); ventanas y prórrogas. `c5436ea`, `e4a6256`
- **F1 FICED** — dashboard, usuarios con subrol, organismos,
  formularios, ventanas, carga CSV. `e245a85`, `cf6fcc2`
- **F2 Taller** — inscripciones por equipo, ediciones, reportes.
  `dc0e862`
- **F3 Encuestas** — constructor, distribución (modos, asignaciones,
  invitaciones, enlace público), resultados, CSV larga/pivot.
  `69b21aa`, `4d3e464`
- **Captura offline encuestador** — plantilla HTML autocontenida,
  token HMAC por formulario+usuario, respaldo JSON, sincronización con
  dedupe `offline_id`. `4f7ded1` (migración `0002_envio_offline`)
- **Ficha metodológica DANE/SEN** — `FichaMetodologica` OneToOne con
  campos de la guía SEN 2023; metadata mínima exigida antes de publicar
  (NTC PE 1000 §4.4.2). `465fc54` (migración `0003_ficha_metodologica`)
- **Tipos complejos** — url, teléfono, fecha-hora, matriz (filas ×
  columnas), ranking, catálogo del sistema (Organismo/Suborganismo/
  EquipoOrganismo), archivo adjunto (`Adjunto`, migración `0004`).
  Hook `valor_desde_post` por tipo; render en web y en el offline.
  `fa57f36`
- **Auditoría completa** — `docs/AUDITORIA_GESTION_ENCUESTAS.md`
  (UX por rol, flujo de datos, seguridad + jurídica/metodológica;
  12 hallazgos priorizados).
- **Fixes de la auditoría** — `e134ece`: adjuntos con permiso, invitación
  solo al enviar, token offline con expiración (30 d), versionado real
  (`version++` estructural), `gracias` con token, rate-limit en login,
  escape XSS en offline, `eliminar_envio` (Ley 1581), `envio_detalle`,
  diccionario de datos CSV. 96 tests verdes.

## 0. Estado actual (línea base verificada)

| Tema | Hoy | Implicación |
|---|---|---|
| Roles | `PerfilRecolector.rol` — **un solo rol por usuario** (9 opciones) + `subrol_ficed` | El gestor es un rol nuevo; no se combina con otro rol salvo staff |
| Gestión de usuarios | Solo admin de Django | Hay que construir CRUD propio con reglas de negocio |
| Ventanas de diligenciamiento | **No existen** (FICED: `periodo`; Taller: `edicion`) | Modelo nuevo + aplicarlo en wizard FICED y wizard taller |
| Avance FICED | `validacion_avances_iced` (solo SIIED) | Extraer a servicio y reutilizar |
| Avance Taller | `views_taller.dashboard` (`taller_staff_required`) | Abrir al gestor |
| Flags organismo | `sin_pp` / `sin_obs` solo en admin | Llevar a la UI de gestión |
| Reinicio de formularios | Borrado manual en admin | Acción guiada + respaldo + auditoría |
| Front | Templates Django + JS sin compilar; sin node | El constructor se hace en JS sin build |
| Identidad FICED | `rol` + **`subrol_ficed`** (ETUAG_PSP, ETOBS, ETPP, ETSGC, ETGIE) en `PerfilRecolector`; también se infiere del username | La gestión FICED administra rol **y** subrol |
| Identidad Taller | Jerarquía **Organismo → Suborganismo → EquipoOrganismo**; el vínculo usuario↔equipo vive **solo en `InscripcionTaller`** (no en el perfil) | La gestión Taller administra esa jerarquía y su consistencia |
| Correo de acceso | `notificar_acceso_usuario` + acción admin `enviar_correo_acceso` (contraseña temporal; solo se guarda si el envío fue exitoso) | Se reutiliza desde el módulo, con el mismo principio |

---

## 1. Arquitectura

- **Roles nuevos** en `PerfilRecolector.ROL_CHOICES` (caben en
  `max_length=20`; solo migración de `choices`):

  | Rol | Etiqueta | Qué hace | Organismo |
  |---|---|---|---|
  | `gestor_formularios` | Gestor de Talleres y Formularios | Opera los 3 submódulos; **alcance global** (todos los organismos) | No aplica |
  | `diligenciador` | Diligenciador | Responde encuestas **a su propio nombre**; una respuesta por formulario | Opcional (no necesariamente representa a un organismo) |
  | `encuestador` | Encuestador | Diligencia encuestas **por varias personas** (anonimas o identificadas) | Opcional |

  - `es_gestor()`, `es_diligenciador()`, `es_encuestador()` + decoradores.
    `gestor_required` admite también `is_superuser`.
  - El rol `delegado` se mantiene único para FICED y Taller; cada dominio
    lo especializa por su propio camino (§1, tabla de dominios).
- **Nunca se borra**: usuarios, organismos, suborganismos y equipos solo se
  **desactivan**. El gestor puede crear y editar nombres, correo, rol y
  organismo. La UI no expone «eliminar»; el servicio lo rechaza.
- **Apps nuevas** (para no inflar `indicadores/models.py`, que tiene más de 4.000 líneas):
  - `gestion/` → hub, submódulos FICED y Taller, ventanas, auditoría.
    Opera sobre los modelos existentes de `indicadores`.
  - `encuestas/` → constructor, renderizador, respuestas y resultados.
- **Entrada**: tarjeta «Gestión de Formularios» en `acceso_modulos.html` →
  `/gestion/` con layout `gestion/base_gestion.html` y tres pestañas:
  **FICED · Taller · Encuestas**.
- **Auditoría transversal** — modelo `gestion.AccionGestion`:
  `usuario, fecha, modulo, accion, objeto_tipo, objeto_id, antes (JSON),
  despues (JSON), motivo (obligatorio en acciones destructivas), ip`.
  Toda mutación del módulo pasa por un helper `registrar_accion(...)`.
- **Servicios** (`gestion/services/*.py`): la lógica de negocio queda fuera de
  las vistas para testearla sin HTTP y reutilizarla desde validación.
- **FICED y Taller son dos dominios distintos** (miden cosas distintas, con
  actores e identidad distintos). No se unifican sus pantallas de usuarios:

  | | FICED | Taller |
  |---|---|---|
  | Quién diligencia | Delegado del organismo **con subrol** de equipo técnico | Delegado ligado a un **equipo de trabajo** (Organismo → Suborganismo → Equipo) |
  | Quién revisa | Validador del organismo (concilia/pre-valida) + validador SIIED (decide) | Analistas SIIED (fuentes, retos, catálogo) |
  | Unidad de avance | Organismo × equipos técnicos requeridos | Organismo × suborganismo × equipo, por edición |
  | Ciclo | Periodo (vigencia) | Edición (año) |
  | Especialización del delegado | `subrol_ficed` | Equipo permanente (Organismo → Suborganismo → Equipo) |
  | Cuenta | **Institucional** (nombres predeterminados, como hoy) | **Personal** (la persona) |

  - **Cuentas separadas**: una cuenta FICED nunca se usa para el Taller ni al
    revés. El servicio de alta lo valida (una cuenta con `subrol_ficed` no
    puede tener equipo del taller, y viceversa).

### 1.1 Lineamientos de interfaz (skill *Apple Design*)
- **Propósito y simplicidad**: cada pantalla muestra primero la tarea común
  (buscar usuario, ver avance); opciones avanzadas un nivel más abajo.
- **Wayfinding**: pestañas FICED · Taller · Encuestas siempre visibles, con
  migas (dónde estoy / cómo salgo). Etiquetas específicas («Usuarios FICED»,
  «Equipos del taller»), no genéricas.
- **Agencia y perdón**: acciones reversibles sin diálogo + «Deshacer»
  (reabrir, desactivar). Confirmación **solo** en lo destructivo e
  irreversible (reiniciar formulario), escribiendo el nombre del organismo.
- **Feedback de cuatro tipos**: estado, completado, advertencia y error.
  Validación en línea (al salir del campo), no solo al enviar. Respuesta
  inmediata al presionar (`:active` en ~100 ms).
- **Agrupación y correspondencia**: el control vive junto a lo que afecta
  (subrol al lado del rol; equipo debajo de suborganismo y este debajo de
  organismo, en cascada).
- **Materiales y profundidad**: barra de pestañas y cabecera fijas
  translúcidas (`backdrop-filter`); paneles laterales (propiedades del
  constructor, detalle de usuario) que no bloquean el flujo, sin velo; modal
  con velo solo para tareas modales.
- **Movimiento**: resortes críticamente amortiguados (sin rebote) para paneles
  y reordenamiento; entrada y salida por el mismo camino; arrastre 1:1 en el
  constructor respetando el punto de agarre; interrumpible.
- **Accesibilidad**: `prefers-reduced-motion` (fundidos en vez de
  desplazamientos), `prefers-reduced-transparency`, `prefers-contrast`;
  espaciado en `rem`; tipografía del sistema con tracking negativo en títulos.

---

## 2. Fase 0 — Cimientos

1. Roles `gestor_formularios`, `diligenciador`, `encuestador` + métodos
   `es_*` + decoradores.
1b. **Cambio obligatorio de contraseña temporal** (§3.2): campos en el
   perfil, middleware, vista `/cuenta/cambiar-contrasena/`, y la acción
   del admin `enviar_correo_acceso` marca el flag. Va primero porque
   protege a todos los roles desde ya.
1c. Restricciones únicas condicionales: un `validador_organismo` activo por
   organismo; un delegado activo por organismo × subrol. **Antes de
   migrar**, script de diagnóstico que liste los duplicados actuales para
   resolverlos (la migración fallaría si existen).
2. App `gestion` registrada; `urls` bajo `/gestion/`; login propio
   (patrón de `validacion/login.html`).
3. Modelo `AccionGestion` + helper + vista «Bitácora» filtrable.
4. Tarjeta en Acceso a Módulos + layout con pestañas.
5. Modelo `VentanaDiligenciamiento`:
   `modulo (ficed|taller|encuesta), referencia (periodo/edición/id),
   fecha_apertura, fecha_cierre, activa, mensaje_cerrado`.
   Y `ProrrogaVentana`: `ventana, organismo, fecha_cierre_extendida, motivo`.
   - Servicio `ventana_abierta(modulo, referencia, organismo)`.

**Pruebas:** permisos por rol (gestor sí / delegado, validador y analista no);
flag de contraseña redirige y se limpia al cambiarla;
segundo validador de organismo rechazado;
`ventana_abierta` con fechas límite, prórroga y zona horaria (`America/Bogota`);
auditoría creada en cada mutación.

---

## 3. Fase 1 — Submódulo FICED

### 3.1 Dashboard de avance
- Extraer el cálculo de `validacion_avances_iced` a
  `services/avance_iced.py`; la vista actual y la nueva lo consumen.
- Por organismo: chips por equipo (estado + % respondido), consolidado,
  **equipos requeridos** según `sin_pp` / `sin_obs` (misma regla que la
  conciliación), semáforo y filtros por estado/periodo. Exportar a Excel.

### 3.2 Usuarios FICED (rol + subrol)
- Lista filtrable (organismo, rol, **subrol**, activo) y vista **matriz por
  organismo**: columnas = 5 equipos técnicos + validador; cada celda muestra
  el delegado asignado o un hueco «sin asignar» (los equipos eximidos por
  `sin_pp` / `sin_obs` aparecen como «no aplica»).
- Crear/editar: nombre, correo, organismo, rol ∈ {`delegado`,
  `validador_organismo`, `validador`}, `subrol_ficed`.
- **Crear validador del organismo**: el gestor crea el usuario, le asigna
  el rol `validador_organismo` y su organismo. Nada más.
- **Relevo de la persona** detrás de una cuenta institucional: se edita el
  nombre y el correo y se envían credenciales nuevas (la cuenta y su
  formulario se conservan).
- Reglas:
  - `delegado` y `validador_organismo` **exigen organismo**.
  - **Un solo `validador_organismo` activo por organismo**: validado en el
    servicio y con restricción en BD (índice único condicional sobre
    `organismo` cuando `rol='validador_organismo'` y `activo=True`). Para
    reemplazarlo se desactiva el anterior en la misma operación.
  - Un solo delegado activo por organismo × subrol (misma restricción).
  - `subrol_ficed` solo aplica a `delegado` y es **obligatorio** para
    delegados FICED (vacío = formulario completo, solo con confirmación).
  - **Cambio de subrol con formulario existente**: el `ICEDFormulario` está
    ligado al equipo; se muestra el impacto y se exige decidir (mantener el
    formulario en el equipo anterior o reiniciarlo). Nunca se re-etiqueta en
    silencio.
  - Aviso si el organismo queda sin validador.
- **Correos automáticos** (servicio `gestion/services/correos.py` sobre
  `notifications._send_email`):
  - **Alta de usuario** → correo de bienvenida con usuario, contraseña
    temporal, rol/subrol y enlace al portal (opcional al crear; activado por
    defecto).
  - **Restablecer contraseña** → nueva temporal; mismo principio del admin:
    solo se guarda si el envío fue exitoso.
  - **Cambio de rol, subrol u organismo** → aviso al usuario.
  - **Envío masivo** de credenciales a una selección (p. ej. todos los
    delegados de un organismo).
  - Cada envío queda en la bitácora (sin la contraseña) con su resultado.
- **Cambio obligatorio de contraseña temporal** (aplica a todos los roles,
  se construye en Fase 0):
  - Campo `PerfilRecolector.debe_cambiar_password` (bool). La temporal
    **no vence**: sirve hasta que el usuario la cambie.
  - Se marca cada vez que se emite una temporal (módulo de gestión **y** la
    acción del admin `enviar_correo_acceso`).
  - Middleware: si está marcado, toda petición autenticada redirige a
    `/cuenta/cambiar-contrasena/` (salvo esa vista, logout y estáticos).
  - Al cambiarla se desmarca, se registra en bitácora y se cierra el resto de
    sesiones (`update_session_auth_hash`). Se aplican los validadores de
    contraseña de Django.
- **Cambiar de organismo**: si el usuario tiene formularios, mostrar el impacto
  y exigir decidir entre mantenerlos o reasignarlos. Nunca moverlos en silencio.
- **Habilitar validador** = cambiar el rol a `validador_organismo` (auditado).
- Activar/desactivar (no borrar usuarios) y restablecer contraseña / enviar
  correo de acceso (se reutiliza el flujo de correo; depende del deploy de Brevo).
- Carga masiva por CSV con validación previa (dry-run) antes de aplicar.

### 3.3 Organismos
- Editar `sin_pp` / `sin_obs` con explicación del efecto (equipos exigidos
  en la conciliación y confirmación de P29/P33).

### 3.4 Formularios
- **Reiniciar formulario de un equipo**: confirmar escribiendo el nombre del
  organismo y registrar un motivo obligatorio.
  - Antes de borrar se guarda una **copia completa en JSON** en `AccionGestion.antes`.
  - Si el consolidado está `prevalidado`/`validado`, se bloquea; hay que
    revertir primero el consolidado (acción aparte, auditada).
- **Reabrir** (`enviado` → `borrador`) como alternativa no destructiva.
- **Restaurar** desde la bitácora, si el registro no ha sido recreado.

### 3.5 Ventanas FICED
- Abrir y cerrar el periodo, prórrogas por organismo.
- Aplicación en `ICEDWizardView.dispatch`, `iced_guardar_parcial` y `done`:
  con la ventana cerrada se puede **leer, pero no guardar ni enviar**, y se
  muestra un mensaje.
  - Sin ventana configurada se mantiene el comportamiento actual (abierta).

**Pruebas:** reglas de usuario; el reinicio crea la copia y la auditoría y respeta
el bloqueo por consolidado; el wizard rechaza guardar o enviar con la ventana
cerrada y lo permite con prórroga; el dashboard coincide con
`validacion_avances_iced`.

---

## 4. Fase 2 — Submódulo Taller

Actores distintos: **delegados del organismo** (diligencian) y **analistas
SIIED** (rol `analista`, revisan fuentes y retos).

### 4.0 Identidad del Taller: Organismo → Suborganismo → Equipo
- Hoy el usuario se liga a su equipo **solo a través de cada
  `InscripcionTaller`** (`user`, `organismo`, `suborganismo`, `equipo`,
  y `equipo_responsable` como texto original). El perfil solo tiene
  `organismo`.
- **Gestión de la estructura**: CRUD de suborganismos y equipos por
  organismo (activar/desactivar, no borrar si tienen inscripciones), en
  vista de árbol.
- **Asignación usuario ↔ equipo**: selector en cascada Organismo →
  Suborganismo → Equipo, con regla de integridad
  `equipo.suborganismo.organismo == organismo` (validada en servidor).
- **Conciliación de equipos**: inscripciones con `equipo` vacío y solo
  texto en `equipo_responsable` → bandeja para asignarles el equipo
  normalizado (o crear uno nuevo).
- **Equipo permanente en el perfil** (decidido):
  `PerfilRecolector.equipo_taller` (FK `EquipoOrganismo`, nullable) +
  `equipo_taller_edicion` (año en que se confirmó). El organismo y el
  suborganismo se derivan del equipo (regla de integridad con
  `perfil.organismo`).
  - Persiste entre ediciones. Al abrir una edición nueva, el gestor (o el
    delegado al entrar) **confirma o actualiza** el equipo; queda la
    edición nueva.
  - La inscripción se precarga desde el perfil y conserva su propia copia
    (historial por edición).
  - **Si la persona sale**: se desactiva su usuario y se crea uno nuevo para
    quien la reemplaza (las cuentas del taller son personales). Sus
    inscripciones históricas quedan intactas.
  - Migración de datos: poblar `equipo_taller` desde la inscripción más
    reciente de cada usuario.

- **Dashboard**: reutilizar `views_taller.dashboard` y sus exportaciones.
  Acceso: staff, validadores y gestor, **con la visibilidad que ya existe**:
  validador SIIED y gestor ven todos los organismos; el validador del
  organismo ve solo el suyo.
- **Inscripciones**: lista por edición y organismo. Acciones:
  - reasignar usuario u organismo;
  - reabrir (`completada` → `en_progreso`);
  - reiniciar (borrar con copia previa).
- **Usuarios Taller**: alta y edición de delegados (Organismo →
  Suborganismo → Equipo) y de analistas SIIED. Usa los mismos correos
  automáticos de §3.2 pero **sin subrol FICED**. Mover a un delegado de
  equipo u organismo muestra sus inscripciones afectadas y pide decidir si
  se reasignan.
- **Ediciones y ventanas**: crear una edición (año) y abrir/cerrar su ventana.
  Aplicación en `wizard_inicio` y `wizard_paso`.

**Pruebas:** permisos; reinicio y reasignación auditados; wizard del taller con
ventana cerrada.

---

## 5. Fase 3 — Encuestas, sondeos y censos (constructor MVP)

### 5.1 Modelo de datos (`encuestas`)
- `Formulario`: título, slug/uuid, descripción, `tipo` (encuesta | sondeo |
  censo), `estado` (borrador | publicado | cerrado | archivado),
  `una_respuesta_por_respondiente` (por usuario o por documento),
  `permite_editar_tras_envio`, ventana
  (`VentanaDiligenciamiento`), `version`, creador.
- `Seccion` (página): formulario, orden, título, descripción.
- `Pregunta`: sección, orden, `tipo`, enunciado, ayuda, `obligatoria`,
  `config` (JSON: min, max, longitud, regex, escala…), `codigo` (para exportar).
- `Opcion`: pregunta, orden, texto, valor, `es_otro` (abre «¿Cuál?»).
- `Formulario.modo_identificacion`: `anonimo` | `identificado`. En
  identificado, `campos_identificacion` (JSON) elige cuáles se piden y cuáles
  son obligatorios: nombres, apellidos, tipo y número de documento,
  teléfono, correo, municipio/localidad, organismo (opcional).
- `Formulario.modos_diligenciamiento`: cualquier combinación de
  `autodiligenciado` (diligenciador/autenticado), `encuestador` y `publico`.
- `Asignacion`: formulario ↔ usuario con rol (`diligenciador` o
  `encuestador`), meta opcional de encuestas para el encuestador, ventana.
- `Respondiente`: datos de identificación (si el modo es identificado).
  Documento normalizado para detectar duplicados; sin FK a `User` cuando
  lo captura un encuestador.
- `Invitacion`: formulario, correo, token, estado, fechas de envío y
  recordatorio (para acceso público por invitación).
- `Envio`: formulario, versión, `diligenciado_por` (User: diligenciador o
  encuestador, nullable si es público), `respondiente` (nullable si es
  anónimo), `modo` (auto | encuestador | publico), token de sesión anónima,
  estado, creado, enviado, metadatos (IP con hash, user-agent, geolocalización
  opcional para trabajo de campo).
- `RespuestaItem`: envío, pregunta, `valor` (JSON). Índice (envío, pregunta).

### 5.2 Tipos de pregunta del MVP
Texto corto · Párrafo · Número · Correo · Fecha · Selección única (radio) ·
Selección única (desplegable) · Selección múltiple (checkbox, con mínimo y máximo) ·
Escala lineal (1–N con etiquetas) · Sí/No.
Todos admiten la opción «Otro (¿cuál?)» cuando aplica y la marca de obligatoria.

### 5.3 Fuente única de verdad
- Un **registro de tipos** en Python (`encuestas/tipos.py`). Cada tipo
  define: esquema de `config`, campo de formulario de Django, validación y
  serialización para exportar.
- El **renderizador** genera un `forms.Form` dinámico desde el esquema. La
  validación del servidor sale del mismo registro, así que el cliente nunca
  es la última palabra.
- El JS del constructor recibe el catálogo de tipos por JSON (no lo duplica).

### 5.4 Constructor (UI)
- Lienzo con secciones y preguntas. Agregar, duplicar, eliminar, reordenar.
  Reordenar con **arrastre nativo** (Pointer Events + `setPointerCapture`,
  seguimiento 1:1 respetando el punto de agarre, umbral de ~10 px,
  asentamiento con resorte sin rebote e interrumpible). Con
  `prefers-reduced-motion` se usan fundidos. Botones subir/bajar como
  alternativa accesible por teclado. Sin dependencias externas.
  Panel lateral de propiedades según el tipo (sin velo) y vista previa.
- Autoguardado por API JSON (`/gestion/encuestas/<id>/api/...`) con control
  de concurrencia (`version`/`updated_at`).
- **Regla de integridad**: con respuestas recibidas, la estructura queda
  bloqueada. Solo se editan textos; los cambios estructurales exigen
  «nueva versión» o duplicar el formulario.

### 5.5 Distribución y respondientes
- **Diligenciador**: ve en «Mis encuestas» los formularios asignados, responde
  **a su nombre** (los datos de identificación se precargan de su perfil),
  una respuesta por formulario (editable si el formulario lo permite).
- **Encuestador**: ve sus formularios asignados y su avance frente a la
  meta; cada «Nueva encuesta» crea un `Envio` nuevo.
  - Modo anónimo: va directo a las preguntas.
  - Modo identificado: primero el bloque de identificación; si el documento
    ya respondió ese formulario se advierte y se bloquea el duplicado.
  - Antes de capturar datos personales, casilla de **autorización de
    tratamiento de datos** que el encuestador marca en nombre del
    encuestado (queda registrada).
  - Lista de sus envíos (en progreso / enviados) para retomarlos.
- **Público**: enlace (uuid) anónimo o identificado, o invitación por correo
  con token único.
- Panel de respondientes: pendientes, en progreso y enviados; reenviar
  invitación; reiniciar una respuesta (auditado).
- Formularios públicos: texto de **tratamiento de datos (Ley 1581/2012)**
  configurable, honeypot y límite de envíos por IP.

### 5.6 Resultados
- Resumen por pregunta: conteos y porcentajes, gráfico de barras (y de
  torta para única), listado de textos y estadísticos para número y escala.
- Tabla de respuestas con filtros; exportar CSV y Excel (`openpyxl`, una
  columna por pregunta u opción para la múltiple).
- Opcional: publicar como dataset en Superset (integración existente).

**Pruebas:** validación por tipo (obligatoria, min/max, regex, múltiple
mín/máx, «otro»); bloqueo de estructura con respuestas; diligenciador con
una sola respuesta; encuestador con varios envíos, anónimos e identificados;
duplicado por documento; autorización de datos obligatoria en modo
identificado; token inválido o vencido; ventana cerrada; exportación con
columnas estables (identificación separada de respuestas, ocultable);
permisos (solo el gestor construye; diligenciador y encuestador solo ven lo
asignado).

---

## 6. Fase 4 — Tipos avanzados

**Implementado** (`fa57f36`): matriz (filas × columnas), archivo adjunto
(`Adjunto`), catálogo del sistema (Organismo/Suborganismo/EquipoOrganismo),
URL, teléfono, fecha-hora, ranking de opciones; hook `valor_desde_post`;
modo offline del encuestador (`4f7ded1`).

**Pendiente**:

- **Lógica condicional**: mostrar u ocultar preguntas y secciones según
  respuestas, y saltos de sección. Se evalúa también en el servidor.
- **Tabla dinámica**: columnas tipadas (texto, número, sí/no/NA, select,
  fecha, URL, organismo), filas fijas o dinámicas (mín/máx), bloqueo por
  columna de control. Es la generalización del `tabla-compleja` de FICED
  (`iced_widgets.js`, `control_bloqueo`, `opcion_na`, `sin_na`).
- Validaciones cruzadas, respuestas precargadas desde catálogos (OOEE,
  MOP, organismos), cuotas y guardado parcial con reanudación pública.
- Catálogo de selección múltiple.
- Largo plazo (no es meta): evaluar si FICED puede describirse con el
  constructor.

---

## 7. Orden de entrega y dependencias

```
F0 Cimientos ──▶ F1 FICED ──▶ F2 Taller
      └────────────────────▶ F3 Encuestas MVP ──▶ F4 Avanzados
```
- F1 y F3 pueden avanzar en paralelo tras F0.
- Correos (invitaciones, restablecer contraseña) dependen del deploy de Brevo
  con DKIM/SPF.
- Migraciones nuevas: `indicadores` desde 0144 (choices de rol); `gestion` y
  `encuestas` con su propio 0001.
- Cada fase se cierra con pruebas verdes, su manual
  (`docs/MANUAL_GESTION_FORMULARIOS.md`) y deploy.

---

## 8. Decisiones

### Tomadas
| # | Tema | Decisión |
|---|---|---|
| 1 | Alcance del gestor | Global: todos los organismos |
| 2 | Roles | Rol único por usuario. `delegado` diligencia FICED y Taller, especializado por subrol FICED o por equipo del taller. El módulo de encuestas añade `diligenciador` (a su nombre, sin organismo obligatorio) y `encuestador` (por varias personas, anónimas o identificadas) |
| 3 | Borrado | Nunca. Se crean y editan nombres, correo, rol y organismo; solo se desactiva |
| 4 | Validador del organismo | Uno solo activo por organismo (restricción en BD) |
| 5 | Arrastre del constructor | Nativo con Pointer Events, sin SortableJS |
| 6 | Encuestas públicas anónimas | Sí, como modo del formulario |
| 7 | Dashboard del taller | Staff, validadores y gestor. Validador SIIED: todos los organismos; validador del organismo: solo el suyo (como hoy) |
| 8 | Equipo del taller | Permanente en el perfil; se confirma o actualiza cada edición. Si la persona sale, se desactiva y se crea el usuario del reemplazo |
| 9 | Cuentas FICED vs Taller | Separadas. FICED: nombre predeterminado institucional; Taller: personal |
| 10 | Primer ingreso | Cambio obligatorio de la contraseña temporal; la temporal no vence hasta que el usuario la cambia |
| 11 | Validador del organismo | El gestor lo crea, le asigna el rol y el organismo |
| 12 | Encuestador sin conexión | **Implementado**: plantilla HTML autocontenida con token HMAC por formulario+usuario, `localStorage`, respaldo JSON y sincronización con dedupe (`4f7ded1`, migración `0002`) |
