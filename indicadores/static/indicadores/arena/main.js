/* Don Datico — Misiones · arranque, menú, briefing, HUD y ciclo de misión.
 * Single-player: sin red, progreso y ajustes en localStorage. */
import { Engine } from './engine.js';
import { cargarDatico } from './datico.js';
import { MAPAS } from './mapas.js';
import { MISIONES } from './missions.js';
import { ETAPAS } from './campaign.js';
import { HUD } from './hud.js';

const $ = id => document.getElementById(id);
const LS_KEY = 'dd_misiones_v2';
const LS_CAMP = 'dd_campana_v1';
const LS_AJ = 'dd_ajustes_v1';
const DIFS = ['Recluta', 'Operador', 'Analista'];   // 0 fácil / 1 normal / 2 difícil
const GLB_URL = window.GLB_URL;
const IMG = (window.DD_STATIC || '/static/') + 'indicadores/images/';
const LOGO_SIIED = IMG + 'unnamed.png';
const LOGO_PLAN = IMG + 'planeaci%C3%B3n.png';

const NIVELES = [
    { id: 'arena', icon: '⚔️', desc: 'Combate puro: sobrevive 3 oleadas en el arena de prueba del SIIED.' },
    { id: 'barrio', icon: '🌃', desc: 'Cali de noche: recupera los paquetes de datos y llévalos al Kiosco SIIED.' },
    { id: 'torres', icon: '🗼', desc: 'Atardecer en el Parque de Barras: escala las torres y activa 4 antenas.' },
    { id: 'pila', icon: '🗂️', desc: 'La Pila: clasifica los chontaduros por color en la torre de su serie.' },
];

const engine = new Engine($('game'));
const e = engine;
window.__eng = e;   // hook de depuración/pruebas
const hud = new HUD(e);
let mision = null, nivel = null, dif = 1, tIni = 0, killsIni = 0, disparosIni = 0;
let puntos = 0;
let camp = -1;                 // etapa de campaña activa (-1 = misión suelta)
let enPantalla = null;
let guardTimer = null;

/* ---------- Progreso y ajustes ---------- */
function progreso() {
    try { return JSON.parse(localStorage.getItem(LS_KEY)) || {}; } catch (x) { return {}; }
}
function guardar(id, data) {
    const p = progreso();
    p[id] = Object.assign(p[id] || {}, data);
    try { localStorage.setItem(LS_KEY, JSON.stringify(p)); } catch (x) {}
}
/* Progreso de campaña: {paso, pts, dif} — paso = próxima etapa (0..8) */
function campProgreso() {
    try { return Object.assign({ paso: 0, pts: 0 }, JSON.parse(localStorage.getItem(LS_CAMP)) || {}); }
    catch (x) { return { paso: 0, pts: 0 }; }
}
function campGuardar(d) {
    const c = Object.assign(campProgreso(), d);
    try { localStorage.setItem(LS_CAMP, JSON.stringify(c)); } catch (x) {}
}

function ajustes() {
    const d = { sens: .95, fov: 74, vol: .8, calidad: 1, verFps: true, invertirY: false, sombras: true };
    try { return Object.assign(d, JSON.parse(localStorage.getItem(LS_AJ)) || {}); } catch (x) { return d; }
}
function guardarAj(a) { try { localStorage.setItem(LS_AJ, JSON.stringify(a)); } catch (x) {} }
function aplicarAjustes(a) {
    e.aplicarAjustes(a);
    $('fps').style.display = a.verFps ? '' : 'none';
}

/* ---------- Overlays ---------- */
function overlay(html, cls = '') {
    cerrarOverlay();
    enPantalla = document.createElement('div');
    enPantalla.className = 'overlay ' + cls;
    enPantalla.innerHTML = html;
    document.body.appendChild(enPantalla);
    return enPantalla;
}
function cerrarOverlay() { enPantalla?.remove(); enPantalla = null; }
const marca = () => `<div class="brandline"><img class="siied" src="${LOGO_SIIED}" alt="SIIED"><img class="planea" src="${LOGO_PLAN}" alt="Planeación"></div>`;
const pie = () => `<div class="brandfoot">SIIED · SECRETARÍA DE PLANEACIÓN · SIMULADOR DE ENTRENAMIENTO</div>`;

function htmlAjustes(a) {
    return `
    <h2 style="margin-top:10px;font-size:15px">AJUSTES</h2>
    <div class="ajrow"><label>SENSIBILIDAD</label><input id="ajsens" type="range" min=".2" max="2.4" step=".05" value="${a.sens}"><span class="val" id="v_sens">${a.sens.toFixed(2)}</span></div>
    <div class="ajrow"><label>CAMPO VISUAL</label><input id="ajfov" type="range" min="60" max="100" step="1" value="${a.fov}"><span class="val" id="v_fov">${a.fov}°</span></div>
    <div class="ajrow"><label>VOLUMEN</label><input id="ajvol" type="range" min="0" max="1" step=".05" value="${a.vol}"><span class="val" id="v_vol">${Math.round(a.vol * 100)}%</span></div>
    <div class="ajrow"><label>CALIDAD</label><select id="ajcal">
        <option value=".55" ${a.calidad === .55 ? 'selected' : ''}>Baja</option>
        <option value=".8" ${a.calidad === .8 ? 'selected' : ''}>Media</option>
        <option value="1" ${a.calidad === 1 ? 'selected' : ''}>Alta</option>
    </select><span class="val"></span></div>
    <div class="ajrow"><label>INVERTIR Y</label><select id="ajinv">
        <option value="0" ${!a.invertirY ? 'selected' : ''}>No</option>
        <option value="1" ${a.invertirY ? 'selected' : ''}>Sí</option>
    </select><span class="val"></span></div>
    <div class="ajrow"><label>SOMBRAS</label><select id="ajsom">
        <option value="1" ${a.sombras ? 'selected' : ''}>Activadas</option>
        <option value="0" ${!a.sombras ? 'selected' : ''}>Desactivadas</option>
    </select><span class="val"></span></div>
    <div class="ajrow"><label>MOSTRAR FPS</label><select id="ajfps">
        <option value="1" ${a.verFps ? 'selected' : ''}>Sí</option>
        <option value="0" ${!a.verFps ? 'selected' : ''}>No</option>
    </select><span class="val"></span></div>`;
}
function wireAjustes(o) {
    const a = ajustes();
    const upd = () => {
        a.sens = +o.querySelector('#ajsens').value;
        a.fov = +o.querySelector('#ajfov').value;
        a.vol = +o.querySelector('#ajvol').value;
        a.calidad = +o.querySelector('#ajcal').value;
        a.invertirY = o.querySelector('#ajinv').value === '1';
        a.sombras = o.querySelector('#ajsom').value === '1';
        a.verFps = o.querySelector('#ajfps').value === '1';
        o.querySelector('#v_sens').textContent = a.sens.toFixed(2);
        o.querySelector('#v_fov').textContent = a.fov + '°';
        o.querySelector('#v_vol').textContent = Math.round(a.vol * 100) + '%';
        aplicarAjustes(a); guardarAj(a);
    };
    o.querySelectorAll('#ajsens,#ajfov,#ajvol,#ajcal,#ajinv,#ajsom,#ajfps')
        .forEach(el => el.addEventListener('input', upd));
}

/* ---------- Pantallas ---------- */
function pantallaMenu() {
    e.activo = false; e.unlock(); cerrarOverlay();
    const p = progreso(), a = ajustes(), c = campProgreso();
    const paso = Math.min(c.paso || 0, ETAPAS.length);
    const completa = paso >= ETAPAS.length;
    const track = ETAPAS.map((et, i) => {
        const st = i < paso ? 'ok' : i === paso ? 'now' : 'lock';
        return `<div class="cst ${st}" title="${i + 1}. ${et.etapa}">
            <span class="ci">${i < paso ? '✓' : i === paso ? et.icon : '·'}</span>
            <span class="cn">${et.etapa}</span></div>`;
    }).join('');
    const cards = NIVELES.map(n => {
        const r = p[`${n.id}_d${dif}`];
        const hecho = r ? `✓ mejor ${Math.floor(r.t / 60)}:${String(r.t % 60).padStart(2, '0')}` : '';
        return `<button class="nivel" data-id="${n.id}">
            <div class="nicon">${n.icon}</div>
            <div class="nname">${MAPAS[n.id].nombre}</div>
            <div class="ndesc">${n.desc}</div>
            <div class="nbest">${hecho}</div>
        </button>`;
    }).join('');
    const o = overlay(`
    <div class="card menu">
      ${marca()}
      <h1>DON DATICO</h1>
      <div class="sub">Simulador de misiones del SIIED — un jugador</div>
      <div class="difs">${DIFS.map((d, i) =>
          `<button class="dif ${i === dif ? 'on' : ''}" data-d="${i}">${d}</button>`).join('')}
      </div>
      <div class="campbox">
        <div class="camptit">CAMPAÑA · LA OPERACIÓN ESTADÍSTICA</div>
        <div class="camptrack">${track}</div>
        <button class="btn" id="bcamp">${completa ? '↺ REINICIAR CAMPAÑA'
            : paso > 0 ? `CONTINUAR · ETAPA ${paso + 1}/${ETAPAS.length}` : '▸ COMENZAR CAMPAÑA'}</button>
        ${c.pts ? `<div class="camppts">${c.pts} pts acumulados en la operación</div>` : ''}
      </div>
      <div class="objmini" style="margin-top:14px">— MISIONES SUELTAS —</div>
      <div class="niveles">${cards}</div>
      ${htmlAjustes(a)}
      <div class="ctrl" style="margin-top:10px"><b>WASD</b> mover · <b>Shift</b> correr · <b>C/Ctrl</b> agacharse · <b>Espacio</b> saltar<br>
      <b>Clic izq.</b> disparar · <b>Clic der.</b> apuntar · <b>R</b> recargar · <b>F</b> inspeccionar · <b>E</b> interactuar · <b>Esc</b> pausa</div>
      <div class="ctrl dim">Progreso guardado en este navegador · sin conexión al servidor</div>
      ${pie()}
    </div>`);
    o.querySelectorAll('.dif').forEach(b => b.onclick = () => { dif = +b.dataset.d; pantallaMenu(); });
    o.querySelectorAll('.nivel').forEach(b => b.onclick = () => pantallaBriefing(b.dataset.id));
    o.querySelector('#bcamp').onclick = () => {
        if (completa) { campGuardar({ paso: 0, pts: 0 }); return pantallaMenu(); }
        pantallaBriefing(null, paso);
    };
    wireAjustes(o);
}

function pantallaBriefing(id, campIdx = -1) {
    const et = campIdx >= 0 ? ETAPAS[campIdx] : null;
    const mapId = et ? et.mapa : id;
    const datos = MAPAS[mapId];
    const desc = et ? et.lore : NIVELES.find(x => x.id === id).desc;
    const o = overlay(`
    <div class="card brief">
      ${marca()}
      <div class="objmini">${et ? `CAMPAÑA · ETAPA ${campIdx + 1}/${ETAPAS.length}` : 'MISIÓN'} · ${DIFS[dif].toUpperCase()}</div>
      <h1 style="font-size:26px">${et ? et.etapa.toUpperCase() : datos.nombre.toUpperCase()}</h1>
      ${et ? `<div class="campmapa">${et.icon} territorio: ${datos.nombre}</div>` : ''}
      <div class="objt">BRIEFING</div>
      <div class="objd">${desc}</div>
      ${et ? `<div class="campnota">▸ ${et.nota}</div>` : ''}
      <div class="datos">
        <span>🔫 Lector DT-7 · 30 rondas</span>
        <span>⚠ Hostiles simulados activos</span>
        <span>🎯 ${DIFS[dif]}</span>
      </div>
      <button class="btn" id="bgo">DESPLEGAR ▸</button>
      <button class="btn ghost" id="bback">◂ MENÚ</button>
      ${pie()}
    </div>`);
    o.querySelector('#bgo').onclick = () => iniciarMision(mapId, campIdx);
    o.querySelector('#bback').onclick = pantallaMenu;
}

function pantallaPausa() {
    const a = ajustes();
    const o = overlay(`
    <div class="card">
      <h2>PAUSA</h2>
      <div class="objmini">${mision?.titulo || ''} — ${DIFS[dif]}</div>
      <div class="obj">${mision?.objetivo || ''}</div>
      ${htmlAjustes(a)}
      <button class="btn" id="bcont">CONTINUAR</button>
      <button class="btn ghost" id="bmenu">SALIR AL MENÚ</button>
    </div>`);
    wireAjustes(o);
    o.querySelector('#bcont').onclick = () => { cerrarOverlay(); e.lock(); };
    o.querySelector('#bmenu').onclick = () => { mision = null; e.limpiar(); pantallaMenu(); };
}

function grado(acc, t, k) {
    const p = acc * .6 + Math.min(1, k / 10) * .25 + Math.min(1, 180 / (t + 30)) * .15;
    return p > .85 ? 'S' : p > .7 ? 'A' : p > .5 ? 'B' : 'C';
}

function pantallaFin(ok, st = {}) {
    const idx = NIVELES.findIndex(n => n.id === nivel);
    let next = ok && camp < 0 && idx >= 0 && idx < NIVELES.length - 1 ? NIVELES[idx + 1] : null;
    let sigLabel = next ? 'SIGUIENTE: ' + MAPAS[next.id].nombre : 'REPETIR';
    let sigAccion = () => iniciarMision(next ? next.id : nivel, -1);
    if (camp >= 0) {
        if (ok) {
            const c = campProgreso();
            campGuardar({ paso: Math.max(c.paso || 0, camp + 1), pts: (c.pts || 0) + st.pts, dif });
        }
        const ultima = camp >= ETAPAS.length - 1;
        if (ok && ultima) { sigLabel = 'CERRAR LA OPERACIÓN ▸'; sigAccion = pantallaCampanaFin; }
        else if (ok) {
            const nx = ETAPAS[camp + 1];
            sigLabel = `SIGUIENTE: ETAPA ${camp + 2} · ${nx.etapa}`;
            sigAccion = () => pantallaBriefing(null, camp + 1);
        }
    }
    const stats = `
      <div class="stat"><div class="v">${Math.floor(st.t / 60)}:${String(st.t % 60).padStart(2, '0')}</div><div class="k">TIEMPO</div></div>
      <div class="stat"><div class="v">${st.k}</div><div class="k">BAJAS</div></div>
      <div class="stat"><div class="v">${st.acc}%</div><div class="k">PRECISIÓN</div></div>
      <div class="stat"><div class="v">${st.hs}</div><div class="k">HEADSHOTS</div></div>
      <div class="stat"><div class="v">${st.pts}</div><div class="k">PUNTOS</div></div>`;
    const o = overlay(`
    <div class="card fin ${ok ? 'ok' : 'ko'}">
      ${marca()}
      <h2>${ok ? 'MISIÓN CUMPLIDA' : 'MISIÓN FALLIDA'}</h2>
      <div class="objmini">${mision?.titulo || ''}</div>
      ${ok ? `<div class="grade">${grado(st.acc / 100, st.t, st.k)}</div>` : '<div class="big">✕</div>'}
      <div class="stats">${stats}</div>
      ${ok && st.mejor ? '<div class="nbest" style="font-size:13px">★ ¡NUEVO RÉCORD! ★</div>' : ''}
      ${ok ? `<button class="btn" id="bsig">${sigLabel}</button>` : ''}
      <button class="btn ${ok ? 'ghost' : ''}" id="brep">REINTENTAR</button>
      <button class="btn ghost" id="bmenu">MENÚ</button>
      ${pie()}
    </div>`);
    o.querySelector('#brep').onclick = () => iniciarMision(nivel, camp);
    o.querySelector('#bmenu').onclick = () => { mision = null; e.limpiar(); pantallaMenu(); };
    o.querySelector('#bsig')?.addEventListener('click', sigAccion);
}

/* Cierre de la operación: resumen estilo ICED con los puntos acumulados */
function pantallaCampanaFin() {
    const c = campProgreso();
    const pts = c.pts || 0;
    const ices = Math.min(100, Math.round(pts / 30));      // índice ficticio sobre los puntos
    const etapas = ETAPAS.map((et, i) =>
        `<div class="cst ok wide"><span class="ci">${et.icon}</span><span class="cn">${i + 1}. ${et.etapa}</span></div>`).join('');
    const o = overlay(`
    <div class="card fin ok">
      ${marca()}
      <h2>OPERACIÓN CERRADA</h2>
      <div class="objmini">Las 8 etapas del ciclo estadístico completadas</div>
      <div class="grade">ICED ${ices}</div>
      <div class="objd" style="text-align:center">Índice de Capacidad Estadística simulado · ${pts} puntos de operación</div>
      <div class="camptrack wrap">${etapas}</div>
      <button class="btn" id="breset">↺ NUEVA OPERACIÓN</button>
      <button class="btn ghost" id="bmenu">MENÚ</button>
      ${pie()}
    </div>`);
    o.querySelector('#breset').onclick = () => { campGuardar({ paso: 0, pts: 0 }); pantallaMenu(); };
    o.querySelector('#bmenu').onclick = pantallaMenu;
}

/* ---------- Puntuación ---------- */
function punt(n, msg) {
    puntos += n;
    hud.score(puntos);
    if (msg) hud.msg(`${n >= 0 ? '+' : ''}${n} ${msg}`);
}

/* ---------- Ciclo de misión ---------- */
function iniciarMision(id, campIdx = -1) {
    nivel = id; camp = campIdx;
    cerrarOverlay();
    e.limpiar();
    const spec = MAPAS[id].build(e);
    e.mapa = spec;
    e.spawn(spec.spawn, spec.yaw ?? 0);
    // limpiar() liberó los listeners de 'acierto': re-registrar el global
    // (hitmarker/puntos) ANTES de crear la misión, que puede añadir el suyo.
    e.on('acierto', d => {
        hud.hitmark(d.cabeza, d.mato);
        if (d.mato) {
            punt(d.cabeza ? 150 : 100);
            hud.kill('TÚ', d.b?.nombre || 'Hostil', d.cabeza);
            if (d.cabeza) e.sfx.head();
        } else if (d.cabeza) { punt(15, 'headshot'); e.sfx.head(); }
        else e.sfx.hit();
    });
    const ctx = { spec, dif };
    const mkey = camp >= 0 ? ETAPAS[camp].mision : id;
    mision = MISIONES[mkey](e, ctx);
    mision.iniciar?.();
    tIni = e.t; killsIni = kills(); disparosIni = e.stats.disparos;
    e.stats.aciertos = 0; e.stats.cabezas = 0;
    puntos = 0; hud.score(0); hud.hp(100);
    e.activo = true;
    hud.obj(mision.objetivo);
    $('hud').style.display = 'block';
    e.lock();
    e.audio.ambient(id === 'barrio' ? [48, 72, 96] : [55, 82.5, 110]);
    clearInterval(guardTimer);
    guardTimer = setInterval(() => {
        if (!mision) return;
        const s = Math.floor(e.t - tIni);
        $('timer').textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    }, 500);
    hud.bandera(mision.titulo.toUpperCase(),
        (camp >= 0 ? `ETAPA ${camp + 1}/${ETAPAS.length} · ` : '') + DIFS[dif].toUpperCase() + ' · ' + mision.objetivo);
}
function kills() { return e.bots.filter(b => !b.vivo).length; }

function finMision(ok) {
    if (!mision) return;
    e.activo = false; e.unlock();
    const t = Math.max(0, Math.round(e.t - tIni));
    const k = kills() - killsIni;
    const dis = Math.max(1, e.stats.disparos - disparosIni);
    const acc = Math.round(e.stats.aciertos / dis * 100);
    const st = { t, k, acc: Math.min(100, acc), hs: e.stats.cabezas, pts: puntos };
    if (ok) {
        e.sfx.win();
        const key = `${nivel}_d${dif}`;
        const prev = progreso()[key];
        if (!prev || t < prev.t) { guardar(key, { t, k }); st.mejor = true; }
        hud.bandera('MISIÓN CUMPLIDA', '');
        setTimeout(() => pantallaFin(true, st), 1600);
    } else {
        e.sfx.lose();
        setTimeout(() => pantallaFin(false, st), 1500);
    }
    $('hud').style.display = 'none';
    clearInterval(guardTimer);
    mision = { titulo: mision.titulo, objetivo: mision.objetivo };
}

/* ---------- Eventos del engine ----------
 * Nota: el listener de 'acierto' se registra dentro de iniciarMision()
 * porque limpiar() libera ese canal por misión (ver engine.js). */
e.on('danio', (n, desde, hp) => { hud.hp(hp); hud.danio(desde); });
e.on('hp', v => hud.hp(v));
e.on('muerte', () => { e.sfx.death(); hud.bandera('SEÑAL PERDIDA', 'REINICIALIZANDO'); finMision(false); });
e.on('mision_ok', () => { punt(200); finMision(true); });
e.on('mision_fail', m => { hud.bandera('MISIÓN FALLIDA', m || ''); finMision(false); });
e.on('msg', t => hud.msg(t));
e.on('avisto', () => e.sfx.alert());
e.on('caida', () => { if (e.jugador.vivo) { e.jugador.pos.set(...e.mapa.spawn); e.jugador.vy = 0; e.daniar(15); } });
e.on('lock', locked => {
    if (!locked && e.activo && !enPantalla) pantallaPausa();
    if (locked && enPantalla?.className.includes('overlay')) cerrarOverlay();
});
e.on('puntos', punt);
e.on('bandera', (t, s) => hud.bandera(t, s));

engine.iniciar((dt, t) => {
    if (!mision) return;
    mision.tick?.(dt, t);
    for (let i = e.bots.length - 1; i >= 0; i--) {
        if (e.bots[i].muerto) { e.scene.remove(e.bots[i].group); e.bots.splice(i, 1); }
    }
    hud.obj(mision.textoHud ? mision.textoHud() : mision.objetivo);
    hud.setMarcas(mision.marcas ? mision.marcas() : []);
    if (e.activo && !document.hidden) hud.tick(dt);
});

/* ---------- Carga ---------- */
const lf = $('loadfill');
lf.style.width = '20%';
$('loadmsg').textContent = 'CARGANDO MODELO DE OPERADOR';
cargarDatico(GLB_URL)
    .then(() => {
        lf.style.width = '100%';
        $('loadmsg').textContent = 'LISTO';
        setTimeout(() => { $('loading')?.remove(); aplicarAjustes(ajustes()); pantallaMenu(); }, 350);
    })
    .catch(err => {
        console.error(err);
        $('loading')?.remove();
        overlay(`<div class="card"><h2>Error</h2>
            <div class="obj">No cargó el modelo de Don Datico (dondaticolite.glb).
            Revisa que <code>static/indicadores/models/</code> esté servido.</div>
            <button class="btn" onclick="location.reload()">REINTENTAR</button></div>`);
    });
