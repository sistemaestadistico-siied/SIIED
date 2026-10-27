# Auditoría frontend — principios Apple Design (skill de Emil Kowalski)

**Fecha:** 23 de octubre de 2026
**Stack auditado:** Django templates + Tailwind (CDN) + JS vanilla — sin framework JS, por decisión de diseño.
**Fuente:** `.windsurf/skills/apple-design/SKILL.md` (WWDC *Designing Fluid Interfaces* + *UI Typography* + 8 principios).

## Superficie auditada

| Dimensión | Dato |
|---|---|
| Templates | 292 |
| Clases Tailwind de motion/hover | 917 usos en ~150 archivos |
| `transition:`/`@keyframes` propios | 318 en 67 archivos (`chat.html` 63, `presentacion.html` 17, `home.html` 16, explorer 15, `base.html` 9) |
| `prefers-reduced-motion` | solo 8 archivos (~3 % de cobertura) |
| `backdrop-filter` | casi nulo — chrome opaco |
| Pointer Events propios | solo `chat`, `presentacion`, `subtema_3d`, `home`; resto = clicks |
| Reglas `:active` en CSS propio | 7 · clases `active:*` de Tailwind: **0** |
| `transition: all` | **116 ocurrencias** |
| Easing dominante | `ease-in-out` (32) — incorrecto como default de UI |
| Tipografía | Inter fija (300–700), sin tracking por tamaño |

## Hallazgos por principio

### §1 Response — kill latency → **CRÍTICO**

Sin feedback en `pointerdown`: el usuario presiona y nada cambia hasta el `click`
(+ navegación). 0 clases `active:*` en todo el frontend. En iOS/Android además
aparece el tap-highlight gris por defecto.

**Fix:** regla global `:active` con `scale(.97)` + `transition 100ms ease-out`
sobre `a, button, [role=button], summary` + `-webkit-tap-highlight-color:
transparent`.

### §11 Frame-level smoothness → **ALTO**

`transition: all` en 116 puntos: anima `width`, `padding`, `margin`, `top/left`
— propiedades que causan layout por frame, fuera del compositor.

**Fix:** reemplazo masivo `transition: all X` → lista explícita
`color, background-color, border-color, opacity, box-shadow, transform`
conservando duración/easing.

### §14 Reduced motion / accesibilidad → **ALTO**

`prefers-reduced-motion` existe en solo 8 archivos. El resto del portal anima
siempre — incumple WCAG y el principio de Flexibility.

**Fix:** regla global en `base.html`:
`@media (prefers-reduced-motion: reduce)` → duraciones ~0 + desactivar
transformaciones grandes. Alternativa menos brusca: cross-fades.

### §4/§3 Springs e interruptibilidad → **MEDIO**

Sin librería de springs ni gestos drag propios — decisión coherente con el stack
(no framework). Las transiciones CSS son interruptibles de forma nativa al
revertirse desde el valor actual, lo cual cubre el caso hover/focus.
Carousels (Swiper) ya traen momentum + rubber-band nativos.

**Fix aplicable sin framework:** corregir la *dirección* del easing —
`ease-in-out` → `ease-out` en transiciones de UI (la entrada debe ser rápida al
inicio y asentarse suave; `ease-in-out` acelera lento = sensación de lag).

### §12 Materials & depth → **MEDIO**

Nav sticky (`base.html:243`) es opaco (`bg-white shadow-md`) — consume una franja
fija sin transmitir jerarquía de capas.

**Fix:** `backdrop-filter: blur(20px) saturate(180%)` + fondo
`rgba(255,255,255,.72)`, contenido scrolleando debajo. Fallback
`prefers-reduced-transparency` y `@supports not (backdrop-filter)` → sólido.

### §15 Typography → **MEDIO**

- Sin tracking diferenciado por tamaño: títulos grandes (`text-4xl+`, h1–h3)
  sin `letter-spacing` negativo → leen "espaciados de más".
- Inter cargada en pesos fijos (no variable) → `font-optical-sizing` no aplica,
  pero el tracking sí.
- `leading` razonable (`leading-tight` en h1 del header ✓).

**Fix:** regla global `h1, h2 { letter-spacing: -0.02em }`, `h3 { -0.01em }`,
`small/.text-xs { letter-spacing: .01em }` (tracking positivo en texto pequeño).

### §7 Spatial consistency → **BAJO / verificación puntual**

Modales/menús deben entrar y salir por el mismo camino y con
`transform-origin` en el trigger. Revisar `chat.html` (63 transiciones — el más
denso) y dropdowns del nav en iteración posterior.

### §16 Foundations (feedback/wayfinding/labels) → **BAJO**

- Wayfinding resuelto (nav consolidado + Sistemas de Consulta).
- Confirmación solo en acciones destructivas — el admin/editorial ya lo hace.
- Hit-padding ~10px en targets pequeños: pendiente puntual en icon-buttons.

### No aplica (documentado)

- §2/§5/§6/§9 (drag 1:1, velocity handoff, momentum projection, rubber-banding):
  no hay gestos drag propios; Swiper/OrbitControls ya los implementan.
- §13 multimodal (sonido/haptics): no aplica al portal web institucional.
- §8 hint de trayectoria: evaluar cuando exista el primer sheet/drawer propio.

## Cambios implementados (esta iteración)

1. `base.html` — capa global de motion + materiales + tipografía + reduced-motion
   (ver bloque `<style>` "capa apple-motion").
2. Sed masivo `transition: all` → propiedades explícitas compositor-safe.
3. Sed `ease-in-out` → `ease-out` en transiciones CSS propias.

## Pendientes conscientes

- Migrar modales de `chat.html` a entrada/salida simétrica con origin en trigger.
- Sheet/drawer con spring + momentum si aparece un caso de uso real.
- Hit-padding en icon-buttons densos (barras de herramientas admin).

---

## Auditoría capilar de templates (292 archivos)

### Mapa de herencia

- `indicadores/base.html` → 75 hijas (chrome público normalizado).
- `editorial/base_editorial.html` → 32 · `validacion/base_validacion.html` → 22
  · `recoleccion/base_recoleccion.html` → 21 · `analitica/base_analitica.html` → 20
  · `delegado/base_delegado.html` → 16 · `reportes/base_reportes.html` → 7.
- `admin/base_site.html` → 11 · `taller/base.html` → 9 · `taller/wizard_base.html` → 6.
- 19 sin `extends` (bases, parciales `_*.html`, presentaciones y páginas standalone).
- `delegado/base.html`, `reportes/base.html`, `validacion/base.html`: bases huérfanas
  (ningún template las extiende).

### Barrido mecánico aplicado (≈150 archivos tocados)

- `font-serif` eliminado → Inter en todo el sistema.
- `gray-*` → `slate-*` (paleta única).
- `rounded-3xl` → `rounded-2xl`; `shadow-xl` → `shadow-lg` (elevación más contenida).
- `bg-gradient-to-* from-X …` → `bg-X` plano (salvo `bg-clip-text`).
- `variante:from-A variante:to-B` → `variante:bg-*` sólido; residuos `from/to/via` y
  prefijos huérfanos eliminados.
- Reparados: `bg-clip-text` sin gradiente en `home.html` y
  `conjuntos_datos_explorer.html` (texto invisible).

### Identidad por módulo (chrome = color real interno)

- Delegado, Recolección, Reportes, Validación → **emerald** (era su color dominante
  en ~500 usos internos; portal, login y nav unificados a emerald).
- Editorial → **fuchsia** · Analítica → **violet** (secciones: cyan SIIED BI,
  emerald Don Datico, amber taller) · Admin Django → **cyan** SIIED.

### Cluster `taller/` (sistema propio)

- `#004b87` → `#155e75`, `#007bb5` → `#0891b2`, `#003366` → `#164e63` en 16 archivos.
- Montserrat → Inter (link de Google Fonts actualizado en `base.html` y `cerrado.html`).

### Verificación

- `manage.py check`: 0 issues. Smoke test: /, acceso-modulos, noticias, eventos,
  catalogo, conjuntos-datos/explorer, taller (2), 6 logins, admin → 200.
