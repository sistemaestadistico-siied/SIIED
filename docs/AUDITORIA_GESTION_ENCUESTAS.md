# Auditoría — apps `gestion` y `encuestas`

**Fecha:** 16-nov-2026 · **Alcance:** módulo Gestión de Formularios
(FICED, Taller, Encuestas) completo, en 3 dimensiones: experiencia de
usuario por rol, flujo de datos, seguridad + base jurídica/metodológica.

---

## 1. Experiencia de usuario por rol

### Gestor (`gestor_formularios` / staff)

Flujo completo y coherente: hub → FICED → Taller → Encuestas;
lista → ficha metodológica → constructor → distribución → resultados →
CSV + anulación. Bitácora en todas las mutaciones.

**Hallazgos**
- No hay vista de **detalle de un envío** (respuestas una a una) — solo
  agregados y CSV. Necesaria para verificación de casos.
- **Bloqueo total tras respuestas**: `api_estructura` rechaza todo el
  POST (incluido `editar_formulario`) cuando `estructura_bloqueada`.
  Cambiar `descripcion`, `limite_envios_por_ip` o el texto de
  tratamiento de datos no es estructura → no debiera bloquearse.
- **Sin rol lector**: `gestor_required` es todo-o-nada. Un analista que
  solo consulte resultados requeriría hoy permisos completos de gestión.

### Encuestador

`pendientes` lista asignaciones; descarga HTML personalizado con token;
sincronización reporta por `offline_id` (importado/duplicado/error).

**Hallazgos**
- Sin vista de **progreso/envíos ya sincronizados** — el único estado es
  el respaldo local.
- Nada indica que el HTML descargado **es una credencial**.

### Diligenciador

`pendientes` + `responder_asignado` + borrador con reanudación. Correcto.

### Público / invitado

Enlace público con límite por IP (hash); invitación con token
`secrets.token_urlsafe(24)`.

**Hallazgos**
- **Bug**: `crear_envio` marca la invitación como `usada` al crear el
  envío aunque sea borrador. Si el invitado abandona, la invitación se
  quema y no puede reentrar → pérdida de respondiente.
- Sin "guardar y continuar" para público anónimo (aceptable, documentar).

### Analista / Validador

Existen en `PerfilRecolector` pero **no tienen vista sobre encuestas**:
los resultados solo los ve el gestor.

---

## 2. Flujo de datos

```
crear → ficha (mínima NTC) → publicar (pregunta con dato + metadata)
      → distribución (modos, asignaciones, invitaciones)
      → responder (puede_responder por modo)
      → _guardar_respuestas (valor_desde_post por tipo)
      → enviado → estructura_bloqueada
      → resultados (resumen por tipo) / CSV (larga/pivot) / anular
```

**Sólido**
- Integridad estructural: todas las mutaciones pasan por
  `estructura_bloqueada`; todos los `get_object_or_404` filtran por
  `formulario=f` (sin IDOR entre formularios).
- `valor_desde_post` normaliza por tipo; matriz/ordenar/catálogo/
  archivo limpian servidor-side; adjuntos en `Adjunto` separado.
- `Respondiente` separado de `RespuestaItem` (PII aparte).
- Duplicar clona estructura + ficha; anular excluye de resultados;
  dedupe por `offline_id` y `una_respuesta_por_respondiente`.
- `permite_editar_tras_envio` habilita corrección en autodiligenciado.

**Hallazgos**
- **`version` es dato muerto**: `Envio.version` captura
  `formulario.version` pero nada lo incrementa al editar la estructura.
  Siempre es 1 → sin trazabilidad de qué cuestionario respondió cada
  envío.
- Invitación quemada en borrador (ver §1).
- **Sin etapa de verificación**: `enviado` va directo a resultados. No
  hay estado intermedio ni rol validador sobre encuestas (la NTC
  describe procesamiento/validación).
- `resumen` cuenta texto libre por valor crudo — una fila por respuesta
  distinta; ruidoso en formularios largos (truncar a top-N).

---

## 3. Seguridad + base jurídica/metodológica

### Seguridad

| Aspecto | Estado |
|---|---|
| Adjuntos | **Sin control de acceso**: `Adjunto.archivo` se serviría por `MEDIA_URL` directa; la ruta contiene ids secuenciales + nombre original. Falta vista `descargar_adjunto` con `gestor_required`. |
| Token offline | El HMAC va **embebido en el HTML descargado** — bearer permanente de ese encuestador+formulario. Documentarlo como credencial; evaluar expiración/rotación. |
| `gracias` | IDOR leve: `GET /encuestas/gracias/<pk>/` por pk secuencial confirma existencia del envío y muestra el título. Debería requerir `Envio.token`. |
| Login | Sin rate-limit ni lockout → fuerza bruta posible. |
| Offline HTML | `p.enunciado`/`titulo`/`ayuda` se inyectan con `innerHTML` sin escapar → XSS gestor→encuestador, exfiltraría el token. |
| `sincronizar` | `csrf_exempt` necesario (file://); la defensa real es el HMAC por usuario+formulario. Correcto. |
| IP | Se guarda **hasheada** (buena privacidad); `user_agent` crudo e indefinido. |

### Jurídica — Ley 1581/2012 (habeas data)

- **Consentimiento**: `texto_tratamiento_datos` + `autoriza_datos`
  persistido en `Respondiente` — cubierto.
- **Supresión**: `anular` excluye de resultados pero conserva datos.
  La ley exige canal de supresión a petición del titular — no existe
  `eliminar_envio` ni anonimización del Respondiente.
- **Retención**: sin plazo ni política; los datos personales permanecen
  indefinidamente.

### Metodológica — NTC PE 1000 / ficha SEN

- **Ficha metodológica mínima exigida antes de publicar** ✓
  (NTC §4.4.2: documentación previa a la recolección).
- **Versionado del instrumento**: exigido; implementado como campo pero
  inerte (ver `version` arriba).
- **Diccionario de datos**: el CSV exporta `codigo`/`enunciado` pero no
  genera el diccionario formal (tipo, dominio, unidad) que la norma pide
  como metadato separado.
- **Verificación de datos**: sin estado intermedio ni rol validador.

---

## 4. Hallazgos priorizados

| # | Severidad | Hallazgo | Fix sugerido |
|---|-----------|----------|--------------|
| 1 | Alta | Adjuntos servidos sin auth | Vista `descargar_adjunto` con `gestor_required` |
| 2 | Alta | Invitación se quema en borrador | Marcar `usada` solo al `enviar` |
| 3 | Alta | Token HMAC como bearer permanente | Documentar + expiración/rotación |
| 4 | Media | XSS enunciados en offline.html | `textContent`/escape en el render JS |
| 5 | Media | `version` nunca incrementa | `+1` en cada mutación estructural |
| 6 | Media | Login sin rate-limit | Throttle por IP/username |
| 7 | Media | `gracias` por pk secuencial | Requerir `Envio.token` |
| 8 | Media | Bloqueo total tras respuestas | Separar `editar_formulario` del bloqueo |
| 9 | Media | Sin supresión de datos personales | `eliminar_envio` / anonimizar |
| 10 | Baja | Sin detalle de envío | Vista `envio_detalle` |
| 11 | Baja | Sin rol lector de resultados | Permiso `ver_resultados` separado |
| 12 | Baja | Sin diccionario de datos | CSV de diccionario por formulario |
