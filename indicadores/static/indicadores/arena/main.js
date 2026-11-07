/* Don Datico — Misiones · arranque, menú, HUD y ciclo de misión.
 * Single-player: sin red, progreso en localStorage. */
import { Engine } from './engine.js';
import { cargarDatico } from './datico.js';
import { MAPAS } from './mapas.js';
import { MISIONES } from './missions.js';

const $ = id => document.getElementById(id);
const LS_KEY = 'dd_misiones_v1';
const DIFS = ['Recluta', 'Operador', 'Analista'];   // 0 fácil / 1 normal / 2 difícil
const GLB_URL = window.GLB_URL;

const NIVELES = [
    { id: 'arena', icon: '⚔️', desc: 'Combate puro: sobrevive 3 oleadas en el arena de prueba.' },
    { id: 'barrio', icon: '🌃', desc: 'Cali de noche: recupera paquetes de datos por el barrio y llévalos al Kiosco SIIED.' },
    { id: 'torres', icon: '🗼', desc: 'Atardecer en el Parque de Barras: escala las torres marcadas y activa 4 antenas.' },
    { id: 'pila', icon: '🗂️', desc: 'Clasifica chontaduros por color en las torres de su serie.' },
];

const engine = new Engine($('game'));
const e = engine;
let mision = null, nivel = null, dif = 1, tIni = 0, killsIni = 0;
let enPantalla = null;   // overlay visible
let guardTimer = null;

/* ---------- Progreso ---------- */
function progreso() {
    try { return JSON.parse(localStorage.getItem(LS_KEY)) || {}; } catch (e) { return {}; }
}
function guardar(id, data) {
    const p = progreso();
    p[id] = Object.assign(p[id] || {}, data);
    try { localStorage.setItem(LS_KEY, JSON.stringify(p)); } catch (e) {}
}

/* ---------- HUD ---------- */
const hud = {
    hp(v) {
        const pct = Math.max(0, Math.round(v));
        $('hpfill').style.width = pct + '%';
        $('hpfill').style.background = pct > 50 ? 'linear-gradient(90deg,#2B7D59,#46d98b)'
            : pct > 25 ? 'linear-gradient(90deg,#a06a1c,#e8a83c)'
            : 'linear-gradient(90deg,#8f1f1f,#e84c3c)';
        $('hpnum').textContent = `INTEGRIDAD ${pct}%`;
    },
    obj(t) { $('objtext').textContent = t; },
    msg(t) {
        const d = document.createElement('div');
        d.textContent = t;
        $('feed').prepend(d);
        while ($('feed').children.length > 5) $('feed').lastChild.remove();
        setTimeout(() => d.remove(), 6500);
    },
    hitmark() { $('cross').classList.add('hit'); setTimeout(() => $('cross').classList.remove('hit'), 110); },
    danio() {
        $('vign').classList.add('dmg');
        setTimeout(() => $('vign').classList.remove('dmg'), 340);
    },
    timer(t0) {
        clearInterval(guardTimer);
        guardTimer = setInterval(() => {
            if (!mision) return;
            const s = Math.floor(e.t - t0);
            $('timer').textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
        }, 500);
    },
};

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

function pantallaMenu() {
    e.activo = false; e.unlock(); cerrarOverlay();
    const p = progreso();
    const cards = NIVELES.map(n => {
        const r = p[`${n.id}_d${dif}`];
        const hecho = r ? `✓ mejor ${r.t}s` : '';
        return `<button class="nivel" data-id="${n.id}">
            <div class="nicon">${n.icon}</div>
            <div class="nname">${MAPAS[n.id].nombre}</div>
            <div class="ndesc">${n.desc}</div>
            <div class="nbest">${hecho}</div>
        </button>`;
    }).join('');
    const o = overlay(`
    <div class="card menu">
      <h1>⚡ DON DATICO</h1>
      <div class="sub">Misiones del SIIED — un jugador</div>
      <div class="difs">${DIFS.map((d, i) =>
          `<button class="dif ${i === dif ? 'on' : ''}" data-d="${i}">${d}</button>`).join('')}
      </div>
      <div class="niveles">${cards}</div>
      <div class="ctrl">WASD mover · Shift correr · Espacio saltar · Click disparar · E interactuar · Esc menú de pausa</div>
      <div class="ctrl dim">Progreso guardado en este navegador · sin conexión al servidor</div>
    </div>`);
    o.querySelectorAll('.dif').forEach(b => b.onclick = () => { dif = +b.dataset.d; pantallaMenu(); });
    o.querySelectorAll('.nivel').forEach(b => b.onclick = () => iniciarMision(b.dataset.id));
    document.body.classList.add('menuOpen');
}

function pantallaPausa() {
    const o = overlay(`
    <div class="card">
      <h2>PAUSA</h2>
      <div class="objmini">${mision?.titulo || ''} — ${DIFS[dif]}</div>
      <div class="obj">${mision?.objetivo || ''}</div>
      <button class="btn" id="bcont">CONTINUAR</button>
      <button class="btn ghost" id="bmenu">SALIR AL MENÚ</button>
    </div>`);
    o.querySelector('#bcont').onclick = () => { cerrarOverlay(); e.lock(); };
    o.querySelector('#bmenu').onclick = () => { mision = null; e.limpiar(); pantallaMenu(); };
}

function pantallaFin(ok, stats = '') {
    const p = progreso();
    const idx = NIVELES.findIndex(n => n.id === nivel);
    const next = ok && idx >= 0 && idx < NIVELES.length - 1 ? NIVELES[idx + 1] : null;
    const o = overlay(`
    <div class="card fin ${ok ? 'ok' : 'ko'}">
      <div class="big">${ok ? '🏆' : '☠'}</div>
      <h2>${ok ? 'MISIÓN CUMPLIDA' : 'MISIÓN FALLIDA'}</h2>
      <div class="objmini">${mision?.titulo || ''}</div>
      <div class="stats">${stats}</div>
      ${ok ? `<button class="btn" id="bsig">${next ? 'SIGUIENTE: ' + MAPAS[next.id].nombre : 'REPETIR'}</button>` : ''}
      <button class="btn ${ok ? 'ghost' : ''}" id="brep">REINTENTAR</button>
      <button class="btn ghost" id="bmenu">MENÚ</button>
    </div>`);
    o.querySelector('#brep').onclick = () => iniciarMision(nivel);
    o.querySelector('#bmenu').onclick = () => { mision = null; e.limpiar(); pantallaMenu(); };
    o.querySelector('#bsig')?.addEventListener('click', () => iniciarMision(next ? next.id : nivel));
}

/* ---------- Ciclo de misión ---------- */
function iniciarMision(id) {
    nivel = id;
    cerrarOverlay(); document.body.classList.remove('menuOpen');
    e.limpiar();
    const spec = MAPAS[id].build(e);
    e.mapa = spec;
    e.spawn(spec.spawn, spec.yaw ?? 0);
    e.dmg = 34;
    const ctx = { spec, dif };
    mision = MISIONES[id](e, ctx);
    mision.iniciar?.();
    tIni = e.t; killsIni = kills();
    e.activo = true;
    hud.obj(mision.objetivo);
    hud.hp(100);
    $('hud').style.display = 'block';
    e.lock();
    e.audio.ambient(id === 'barrio' ? [48, 72, 96] : [55, 82.5, 110]);
    hud.timer(tIni);
    hud.msg(`Misión: ${mision.objetivo}`);
}
function kills() { return e.bots.filter(b => !b.vivo).length; }

function finMision(ok) {
    if (!mision) return;
    e.activo = false; e.unlock();
    const t = Math.max(0, Math.round(e.t - tIni));
    const k = kills() - killsIni;
    const stats = `tiempo ${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')} · bajas ${k}`;
    if (ok) {
        e.sfx.win();
        const key = `${nivel}_d${dif}`;
        const prev = progreso()[key];
        if (!prev || t < prev.t) guardar(key, { t, k });
        setTimeout(() => pantallaFin(true, stats), 900);
    } else {
        e.sfx.lose();
        setTimeout(() => pantallaFin(false, stats), 1400);
    }
    $('hud').style.display = 'none';
    clearInterval(guardTimer);
    mision = { titulo: mision.titulo, objetivo: mision.objetivo };   // conserva datos para overlay
}

/* ---------- Eventos del engine ---------- */
e.on('acierto', b => { hud.hitmark(); e.sfx.hit(); });
e.on('danio', (n, desde, hp) => { hud.hp(hp); hud.danio(); e.sfx.hurt(); });
e.on('hp', hud.hp);
e.on('muerte', () => { e.sfx.death(); finMision(false); });
e.on('mision_ok', () => finMision(true));
e.on('msg', hud.msg);
e.on('avisto', () => e.sfx.alert());
e.on('caida', () => { if (e.jugador.vivo) { e.jugador.pos.set(...e.mapa.spawn); e.jugador.vy = 0; e.daniar(15); } });
e.on('lock', locked => {
    if (!locked && e.activo && !enPantalla) pantallaPausa();
    if (locked && enPantalla?.className.includes('overlay')) cerrarOverlay();
});

engine.iniciar((dt, t) => {
    if (!mision) return;
    mision.tick?.(dt, t);
    // Retirar de la escena los bots cuya muerte terminó
    for (let i = e.bots.length - 1; i >= 0; i--) {
        if (e.bots[i].muerto) { e.scene.remove(e.bots[i].group); e.bots.splice(i, 1); }
    }
    hud.obj(mision.textoHud ? mision.textoHud() : mision.objetivo);
});

/* ---------- Carga del GLB y arranque ---------- */
$('hud').style.display = 'none';
cargarDatico(GLB_URL)
    .then(pantallaMenu)
    .catch(() => {
        overlay(`<div class="card"><h2>Error</h2>
            <div class="obj">No cargó el modelo de Don Datico (dondaticolite.glb).
            Revisa que <code>static/indicadores/models/</code> esté servido.</div>
            <button class="btn" onclick="location.reload()">REINTENTAR</button></div>`);
    });
