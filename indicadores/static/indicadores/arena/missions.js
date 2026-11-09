/* Misiones por mapa. Cada misión devuelve:
 *   {titulo, objetivo, nBots} y opcionalmente tick/onPickup/onKill/listaBots.
 * El motor (main.js) gestiona hp/muerte del jugador y llama fin(true/false). */
import * as THREE from 'three';
import { Bot } from './bot.js';
import { Pickup, Zona, Antena, Botiquin } from './objetos.js';
import { GRAV, basic } from './engine.js';
import { SERIES } from './mapas.js';
export { SERIES };

const _pad = new THREE.Vector3();

const NOMBRES_BOT = ['Bot-DANE', 'R2-DECRETO', 'CENSO-2000', 'NORMALIZADOR',
    'IA-NORMAL', 'GeoCoder-X', 'TablaCruzada', 'P30-BOT', 'Error404',
    'UploadBot', 'NullPointer', 'CacheMiss', 'DeadLock', 'Overflow'];

const COLORES_BOT = [0xa05cff, 0xff6a5c, 0xffb37a, 0xff7b9c, 0x7cd8ff];

/* Añade un bot al mundo */
function bot(e, ctx, pos, cfg = {}) {
    const b = new Bot({
        engine: e, scene: e.scene,
        nombre: cfg.nombre || NOMBRES_BOT[(Math.random() * NOMBRES_BOT.length) | 0],
        color: cfg.color ?? COLORES_BOT[(Math.random() * COLORES_BOT.length) | 0],
        hp: cfg.hp ?? 100, pos,
        cfg: Object.assign({ waypoints: ctx.wps || ctx.spec.wps || [] }, cfg),
    });
    e.scene.add(b.group);
    e.bots.push(b);
    e.particulas.emit(b.pos.clone().setY(b.pos.y + .7), b.color, 14, 2.5, .5, 1.6);
    return b;
}

/* Waypoints fuera de colliders (p.ej. el estadio del Barrio cubre algunos).
 * Se cachean en ctx.wps para patrullas y spawns. */
function wpsLibres(e, ctx) {
    if (ctx.wps) return ctx.wps;
    const l = (ctx.spec.wps || []).filter(p => !e.enSolido(p[0], p[1], .7));
    ctx.wps = l.length ? l : (ctx.spec.wps || []);
    return ctx.wps;
}

/* Si el punto cae dentro de un collider, busca un hueco en espiral.
 * Devuelve [x,z] libre o null si no encontró. */
function puntoLibre(e, x, z, pad = .6) {
    if (!e.enSolido(x, z, pad)) return [x, z];
    for (const r of [.9, 1.6, 2.4, 3.4, 4.5]) {
        for (let a = 0; a < Math.PI * 2 - .01; a += Math.PI / 4) {
            const nx = x + Math.cos(a) * r, nz = z + Math.sin(a) * r;
            if (!e.enSolido(nx, nz, pad)) return [nx, nz];
        }
    }
    return null;
}

function lejosJugador(e, pts, dist = 10) {
    const j = e.jugador.pos;
    const libres = pts.filter(p => Math.hypot(p[0] - j.x, p[1] - j.z) > dist);
    const set = libres.length ? libres : pts;
    return set[(Math.random() * set.length) | 0];
}

/* ============ Misión 1: Arena — 3 oleadas ============ */
export function mArena(e, ctx) {
    const RONDAS = [
        { n: 3, hp: 60, dano: 9, cadenciaMin: .9, cadenciaMax: 1.7, precision: .1, vel: 3.6 },
        { n: 4, hp: 80, dano: 11, cadenciaMin: .75, cadenciaMax: 1.5, precision: .08, vel: 4.2 },
        { n: 6, hp: 100, dano: 13, cadenciaMin: .6, cadenciaMax: 1.3, precision: .06, vel: 4.8 },
    ];
    const ctxM = {
        titulo: 'Arena de Datos',
        objetivo: 'Sobrevive las 3 oleadas',
        ronda: 0, entra: 0, espera: 4, vivos: 0, fin: false,
        texto(t) { return `Oleada ${this.ronda}/3 · Enemigos: ${this.vivos}`; },
        iniciar() { e.emit('msg', `Oleada 1 llega en ${Math.ceil(this.espera)}s — prepárate`); this.entra = e.t + this.espera; },
        spawnRonda() {
            const R = RONDAS[this.ronda];
            const spawns = ctx.spec.zonasSpawn.morado;
            for (let i = 0; i < R.n; i++) {
                const s = spawns[i % spawns.length];
                bot(e, ctx, [s[0] + Math.random() * 2 - 1, 0, s[1] + Math.random() * 2 - 1], R);
            }
            this.ronda++;
            e.sfx.wave();
            e.emit('bandera', `OLEADA ${this.ronda}`, `${R.n} HOSTILES SIMULADOS`);
            e.emit('msg', `¡Oleada ${this.ronda}! — ${R.n} hostiles`);
        },
        tick(dt, t) {
            if (this.fin) return;
            this.vivos = e.bots.filter(b => b.vivo).length;
            // Sin enemigos vivos y sin cuenta atrás → armar la siguiente
            // (o cerrar la misión si ya fueron las 3 oleadas).
            if (this.vivos === 0 && !this.entra) {
                if (this.ronda >= RONDAS.length) { this.fin = true; return e.emit('mision_ok'); }
                this.entra = t + (this.ronda === 0 ? this.espera : 6);
                e.emit('msg', this.ronda === 0 ? `Oleada 1 en ${this.espera}s`
                                               : 'Siguiente oleada en 6s');
            }
            if (this.entra && t >= this.entra) {
                this.entra = 0;
                this.spawnRonda();
            }
        },
        textoHud() {
            if (this.entra && this.entra > e.t) return `Siguiente oleada en ${Math.ceil(this.entra - e.t)}s`;
            return `Oleada ${this.ronda}/3 · Enemigos vivos: ${this.vivos}`;
        },
    };
    return ctxM;
}

/* ============ Misión 2: Barrio — recolecta y entrega ============ */
export function mBarrio(e, ctx) {
    const TOTAL = ctx.dif >= 2 ? 14 : ctx.dif >= 1 ? 11 : 8;
    const pickups = [];
    const pts = (ctx.spec.puntosPickup || []).slice();
    // Shuffle y toma TOTAL
    for (let i = pts.length - 1; i > 0; i--) {
        const k = (Math.random() * (i + 1)) | 0; [pts[i], pts[k]] = [pts[k], pts[i]];
    }
    pts.slice(0, TOTAL).forEach(([x, z], i) => {
        const p = puntoLibre(e, x, z);   // casitas aleatorias pueden cubrir el punto
        if (p) pickups.push(new Pickup(e, { x: p[0], y: 0, z: p[1], color: 0xffb37a, nombre: `paquete-${i}` }));
    });
    const totReal = pickups.length;
    const zona = new Zona(e, { x: ctx.spec.zonaKiosco[0], z: ctx.spec.zonaKiosco[1], r: 4, color: 0x46d98b, nombre: 'KIOSCO SIIED' });

    // Patrullas: en cuesta varían conteo y agresividad
    const cfgPat = [
        { n: 3, dano: 9, cadenciaMin: 1.0, cadenciaMax: 1.9, precision: .11, vision: 18 },
        { n: 4, dano: 11, cadenciaMin: .8, cadenciaMax: 1.6, precision: .09, vision: 22 },
        { n: 5, dano: 13, cadenciaMin: .7, cadenciaMax: 1.4, precision: .07, vision: 26 },
    ][Math.min(ctx.dif, 2)];
    const spawns = wpsLibres(e, ctx);
    for (let i = 0; i < cfgPat.n; i++) {
        const s = lejosJugador(e, spawns, 14);
        bot(e, ctx, [s[0], 0, s[1]], cfgPat);
    }

    const M = {
        titulo: 'Barrio SIIED',
        objetivo: `Recupera ${totReal} paquetes de datos y entrégalos en el Kiosco SIIED`,
        lleva: 0, entregados: 0, fin: false,
        esc: false,
        iniciar() {
            e.on('pickup', p => {
                this.lleva += p.valor;
                e.emit('puntos', 5);
                e.emit('msg', `+1 paquete (llevas ${this.lleva}) — al Kiosco`);
            });
            // Botiquines entre casitas
            for (const [x, z] of [[-20, 0], [20, 0]]) new Botiquin(e, { x, z });
        },
        tick(dt, t) {
            if (this.fin) return;
            const j = e.jugador;
            if (zona.contiene(j.pos) && this.lleva > 0) {
                e.emit('puntos', this.lleva * 15, 'entrega');
                this.entregados += this.lleva;
                e.emit('msg', `Entregados ${this.entregados}/${totReal} — ${Math.max(0, totReal - this.entregados)} restantes`);
                this.lleva = 0;
                e.sfx.deliver();
                e.particulas.emit(zona.pos, 0x46d98b, 18, 4, .7, 1.6);
                if (this.entregados >= totReal && !this.esc) {
                    this.esc = true;
                    e.emit('msg', '¡Todos los datos! Refuerzos hostiles en camino — sobrevive 20s');
                    e.sfx.alert();
                    const R = { n: ctx.dif >= 2 ? 4 : 3, hp: 80, dano: 12, cadenciaMin: .8, cadenciaMax: 1.5, precision: .08, vel: 5 };
                    for (let i = 0; i < R.n; i++) {
                        const s = lejosJugador(e, spawns, 12);
                        bot(e, ctx, [s[0], 0, s[1]], R);
                    }
                    this.escapeT = t + 20;
                }
            }
            if (this.esc && t >= this.escapeT) { this.fin = true; e.emit('mision_ok'); }
        },
        textoHud() {
            if (this.esc && this.escapeT > e.t) return `Sobrevive ${Math.ceil(this.escapeT - e.t)}s`;
            if (this.lleva > 0) return `Entregar ${this.lleva} en el Kiosco (${this.entregados}/${totReal})`;
            const quedan = pickups.filter(p => !p.recogido).length;
            return `Paquetes: ${this.entregados}/${totReal} · quedan ${quedan}`;
        },
        marcas() {
            const j = e.jugador.pos;
            const m = [{ x: zona.pos.x, y: 3.2, z: zona.pos.z, color: '#46d98b', icon: '⬢', txt: 'KIOSCO SIIED' }];
            if (this.lleva === 0) {
                const libres = pickups.filter(p => !p.recogido)
                    .sort((a, b) => a.pos.distanceToSquared(j) - b.pos.distanceToSquared(j));
                for (const p of libres.slice(0, 10))
                    m.push({ x: p.pos.x, y: 1.7, z: p.pos.z, color: '#ffb37a', txt: 'paquete' });
            }
            return m;
        },
    };
    return M;
}

/* ============ Misión 3: Torres — activa 4 antenas ============ */
export function mTorres(e, ctx) {
    const antenas = (ctx.spec.objetivos || []).map((o, i) =>
        new Antena(e, { x: o.x, y: o.h, z: o.z, nombre: `Antena ${String.fromCharCode(65 + i)}`, tiempo: 1.8 }));
    // "Ascensor de datos": pad luminoso que impulsa al jugador a la cima
    const pads = (ctx.spec.objetivos || []).map(o => {
        const px = o.x + o.w / 2 + 2.1, pz = o.z;
        const disco = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.5, .1, 24),
            basic(o.color, { transparent: true, opacity: .35 }));
        disco.position.set(px, .06, pz); e.add(disco);
        const aro = new THREE.Mesh(new THREE.TorusGeometry(1.5, .08, 8, 32), basic(o.color));
        aro.rotation.x = Math.PI / 2; aro.position.set(px, .12, pz); e.add(aro);
        const haz = new THREE.Mesh(new THREE.CylinderGeometry(.5, .9, o.h, 10, 1, true),
            basic(o.color, { transparent: true, opacity: .12, blending: THREE.AdditiveBlending,
                depthWrite: false, side: THREE.DoubleSide }));
        haz.position.set(px, o.h / 2, pz); e.add(haz);
        return { x: px, z: pz, h: o.h, aro };
    });
    const cfgPat = [
        { n: 3, dano: 9, cadenciaMin: 1.0, cadenciaMax: 1.8, precision: .11, vision: 16 },
        { n: 4, dano: 11, cadenciaMin: .85, cadenciaMax: 1.6, precision: .09, vision: 20 },
        { n: 5, dano: 13, cadenciaMin: .7, cadenciaMax: 1.4, precision: .07, vision: 24 },
    ][Math.min(ctx.dif, 2)];
    const spawns = wpsLibres(e, ctx);
    for (let i = 0; i < cfgPat.n; i++) {
        const s = lejosJugador(e, spawns, 14);
        bot(e, ctx, [s[0], 0, s[1]], cfgPat);
    }
    for (const [x, z] of [[-14, -7], [14, 6]]) new Botiquin(e, { x, z });

    const M = {
        titulo: 'Parque de Barras',
        objetivo: `Escala las torres marcadas y activa las ${antenas.length} antenas (mantén E)`,
        fin: false,
        iniciar() { e.on('antena', a => { e.emit('puntos', 75, 'antena'); e.emit('msg', `${a.nombre} activada`); }); },
        tick(dt, t) {
            if (this.fin) return;
            const j = e.jugador;
            for (const p of pads) {
                p.aro.scale.setScalar(1 + Math.sin(t * 3) * .07);
                if (j.grounded && t > (j._padCd || 0) &&
                    Math.hypot(j.pos.x - p.x, j.pos.z - p.z) < 1.6) {
                    j._padCd = t + 1;                       // evita rebote en bucle AFK
                    j.vy = Math.sqrt(-2 * GRAV * (p.h + .9));   // impulso hasta la cima
                    j.grounded = false;
                    e.sfx.jump();
                    e.particulas.emit(_pad.set(p.x, .2, p.z), 0x7cd8ff, 14, 4, .6, 1.4);
                    e.emit('msg', 'Ascensor de datos — ¡a la torre!');
                }
            }
            if (antenas.every(a => a.activada)) { this.fin = true; e.emit('mision_ok'); }
        },
        textoHud() {
            const n = antenas.filter(a => a.activada).length;
            const activa = antenas.find(a => a.carga > 0 && !a.activada);
            if (activa) return `Sincronizando… ${Math.round(activa.progreso() * 100)}%`;
            return `Antenas: ${n}/${antenas.length}`;
        },
        marcas() {
            return antenas.filter(a => !a.activada).map(a => ({
                x: a.pos.x, y: a.pos.y + 2.4, z: a.pos.z,
                color: a.carga > 0 ? '#ffd98a' : '#7cd8ff', icon: '⌁', txt: a.nombre }));
        },
    };
    return M;
}

/* ============ Misión 4: Pila — clasifica por serie ============ */
export function mPila(e, ctx) {
    const POR_SERIE = ctx.dif >= 2 ? 4 : 3;
    const pickups = [];
    // Chontaduros de cada serie desperdigados por el patio
    SERIES.forEach((s, si) => {
        for (let i = 0; i < POR_SERIE; i++) {
            const a = Math.random() * Math.PI * 2, r = 8 + Math.random() * 14;
            let x = Math.cos(a) * r, z = Math.sin(a) * r;
            x = THREE.MathUtils.clamp(x, -27, 27); z = THREE.MathUtils.clamp(z, -23, 23);
            const p = puntoLibre(e, x, z);   // puede caer dentro de coberturas
            if (p) pickups.push(new Pickup(e, { x: p[0], y: 0, z: p[1], color: s.color, valor: si }));
        }
    });
    const zonas = ctx.spec.torres.map(t =>
        new Zona(e, { x: t.x, z: t.z, r: 3.4, color: t.serie.color, nombre: t.serie.nombre }));
    // Recuento real: si algún punto quedó sin hueco, no se exige
    const tot = pickups.length;
    const nSeg = {}; SERIES.forEach(s => nSeg[s.nombre] = 0);   // entregas por serie

    const cfgPat = [
        { n: 2, dano: 9, cadenciaMin: 1.1, cadenciaMax: 1.9, precision: .12, vision: 16 },
        { n: 3, dano: 10, cadenciaMin: .9, cadenciaMax: 1.7, precision: .09, vision: 20 },
        { n: 4, dano: 12, cadenciaMin: .8, cadenciaMax: 1.5, precision: .07, vision: 24 },
    ][Math.min(ctx.dif, 2)];
    const spawns = wpsLibres(e, ctx);
    for (let i = 0; i < cfgPat.n; i++) {
        const s = lejosJugador(e, spawns, 14);
        bot(e, ctx, [s[0], 0, s[1]], cfgPat);
    }
    new Botiquin(e, { x: -14, z: -12 }); new Botiquin(e, { x: 14, z: 12 });

    const M = {
        titulo: 'Patio de Pilas',
        objetivo: `Clasifica ${tot} chontaduros: cada color va a la torre de su serie`,
        llevando: null, entregados: 0, fin: false,
        iniciar() { e.on('pickup', p => {
            if (this.llevando) {
                // Rechazar: reinsertar el pickup (su mesh ya se retiró en recoger())
                p.recogido = false;
                e.scene.add(p.group);
                return e.emit('msg', 'Ya llevas uno — entrégalo primero');
            }
            this.llevando = p;
            const s = SERIES[p.valor];
            e.emit('puntos', 5);
            e.emit('msg', `Llevas un chontaduro ${s.nombre} → a su torre`);
        }); },
        tick(dt, t) {
            if (this.fin) return;
            const j = e.jugador;
            if (!this.llevando) return;
            const s = SERIES[this.llevando.valor];
            const zona = zonas[SERIES.indexOf(s)];
            // Torre incorrecta: avisar (con enfriamiento), no entrega
            if (!zona.contiene(j.pos)) {
                const mal = zonas.some((z, i) => i !== SERIES.indexOf(s) && z.contiene(j.pos));
                if (mal && t > (this._avisoT || 0)) {
                    this._avisoT = t + 2.5;
                    e.sfx.wrong();
                    e.emit('msg', `Torre incorrecta — el ${s.nombre} va a la torre de su color`);
                }
            }
            // indicador en el HUD de lo que carga
            if (zona.contiene(j.pos)) {
                this.llevando.recogido = true;
                this.entregados++;
                e.emit('puntos', 30, 'clasificado');
                e.emit('msg', `Clasificado ${s.nombre} · ${this.entregados}/${tot}`);
                e.sfx.deliver();
                e.particulas.emit(zona.pos, s.color, 20, 4, .7, 1.6);
                // La torre crece un slot
                const torre = ctx.spec.torres[SERIES.indexOf(s)];
                const idx = ++nSeg[s.nombre];
                const seg = new THREE.Mesh(new THREE.BoxGeometry(3.4, 1.1, 3.4),
                    new THREE.MeshStandardMaterial({ color: s.color, roughness: .5, emissive: s.color, emissiveIntensity: .25 }));
                seg.position.set(torre.x, 1 + idx * 1.15, torre.z);
                seg.castShadow = true; e.add(seg);
                e.solido(torre.x, 1 + idx * 1.15, torre.z, 3.6, 1.1, 3.6, null);
                this.llevando = null;
                if (this.entregados >= tot) { this.fin = true; e.emit('mision_ok'); }
            }
        },
        textoHud() {
            if (this.llevando) return `Llevando ${SERIES[this.llevando.valor].nombre} · entregados ${this.entregados}/${tot}`;
            return `Clasificados ${this.entregados}/${tot}`;
        },
        marcas() {
            if (this.llevando) {
                const s = SERIES[this.llevando.valor], z = zonas[SERIES.indexOf(s)];
                return [{ x: z.pos.x, y: 4, z: z.pos.z, color: '#' + s.color.toString(16).padStart(6, '0'),
                    icon: '▼', txt: 'ENTREGA AQUÍ · ' + s.nombre }];
            }
            const j = e.jugador.pos;
            const m = zonas.map((z, i) => ({ x: z.pos.x, y: 4, z: z.pos.z,
                color: '#' + SERIES[i].color.toString(16).padStart(6, '0'), icon: '◻', txt: SERIES[i].nombre }));
            const libres = pickups.filter(p => !p.recogido)
                .sort((a, b) => a.pos.distanceToSquared(j) - b.pos.distanceToSquared(j));
            for (const p of libres.slice(0, 8))
                m.push({ x: p.pos.x, y: 1.7, z: p.pos.z,
                    color: '#' + p.color.toString(16).padStart(6, '0'), txt: SERIES[p.valor].nombre });
            return m;
        },
    };
    return M;
}

/* ================================================================
 * MISIONES DE CAMPAÑA — las 8 etapas de la operación estadística
 * ================================================================ */

/* Etapa 1 · DETECCIÓN DE NECESIDADES (barrio)
 * Recorre el territorio y sintoniza cada punto de necesidad de
 * información (mantener E). Patrullas leves del ruido. */
export function mDeteccion(e, ctx) {
    const SPOTS = [            // cerca de los landmarks del barrio
        [-22, 14, 'VECINOS·iglesia'], [19, -12, 'COMERCIANTES·estadio'],
        [20, 13.5, 'MERCADO·mall'], [-20, -5, 'PARQUE'], [-22, 5, 'BOMBEROS'],
    ];
    const sensores = SPOTS.map(([x, z, nombre]) => {
        const p = puntoLibre(e, x, z, 1) || [x, z];
        return new Antena(e, { x: p[0], y: 0, z: p[1], nombre, tiempo: 2.2 });
    });
    const cfgPat = [
        { n: 2, dano: 8, cadenciaMin: 1.2, cadenciaMax: 2.0, precision: .13, vision: 15 },
        { n: 3, dano: 10, cadenciaMin: 1.0, cadenciaMax: 1.8, precision: .10, vision: 19 },
        { n: 4, dano: 12, cadenciaMin: .85, cadenciaMax: 1.6, precision: .08, vision: 22 },
    ][Math.min(ctx.dif, 2)];
    const spawns = wpsLibres(e, ctx);
    for (let i = 0; i < cfgPat.n; i++) {
        const s = lejosJugador(e, spawns, 16);
        bot(e, ctx, [s[0], 0, s[1]], cfgPat);
    }
    new Botiquin(e, { x: 0, z: 6 }); new Botiquin(e, { x: -20, z: -12 });

    const M = {
        titulo: 'Etapa 1 · Detección de necesidades',
        objetivo: `Sintoniza los ${sensores.length} puntos de necesidad de información (mantén E)`,
        fin: false,
        iniciar() { e.on('antena', a => { e.emit('puntos', 60, 'necesidad detectada'); e.emit('msg', `${a.nombre} registrada`); }); },
        tick() { if (!this.fin && sensores.every(s => s.activada)) { this.fin = true; e.emit('mision_ok'); } },
        textoHud() {
            const n = sensores.filter(s => s.activada).length;
            const act = sensores.find(s => s.carga > 0 && !s.activada);
            if (act) return `Detectando… ${Math.round(act.progreso() * 100)}%`;
            return `Necesidades detectadas: ${n}/${sensores.length}`;
        },
        marcas() {
            return sensores.filter(s => !s.activada).map(s => ({
                x: s.pos.x, y: 4, z: s.pos.z,
                color: s.carga > 0 ? '#ffd98a' : '#7cd8ff', icon: '⌁', txt: 'SENSOR ' + s.nombre }));
        },
    };
    return M;
}

/* Etapa 2 · DISEÑO (arena)
 * Cada pieza del instrumento (variable, universo, método, periodicidad,
 * cobertura) se lleva una a una hasta la mesa de diseño. */
export function mDiseno(e, ctx) {
    const PIEZAS = ['Variable', 'Universo', 'Método', 'Periodicidad', 'Cobertura', 'Instrumento'];
    const mesa = new Zona(e, { x: -18, z: 0, r: 4, color: 0x46d98b, nombre: 'MESA DE DISEÑO' });
    const pts = [[-18, -12], [-18, 12], [18, -12], [18, 12], [0, -18], [6, 0], [-6, -18]];
    const pickups = [];
    PIEZAS.forEach((nombre, i) => {
        const p = puntoLibre(e, pts[i][0], pts[i][1]) || [pts[i][0], pts[i][1]];
        const pk = new Pickup(e, { x: p[0], y: 0, z: p[1], color: 0xc98bff, nombre });
        pk.pieza = nombre;
        pickups.push(pk);
    });
    const cfgPat = [
        { n: 1, dano: 8, cadenciaMin: 1.2, cadenciaMax: 2.0, precision: .12, vision: 16 },
        { n: 2, dano: 10, cadenciaMin: 1.0, cadenciaMax: 1.8, precision: .10, vision: 20 },
        { n: 3, dano: 12, cadenciaMin: .9, cadenciaMax: 1.6, precision: .08, vision: 24 },
    ][Math.min(ctx.dif, 2)];
    const spawns = wpsLibres(e, ctx);
    for (let i = 0; i < cfgPat.n; i++) {
        const s = lejosJugador(e, spawns, 12);
        bot(e, ctx, [s[0], 0, s[1]], cfgPat);
    }
    new Botiquin(e, { x: 14, z: -14 });

    const M = {
        titulo: 'Etapa 2 · Diseño',
        objetivo: `Lleva cada pieza del instrumento a la mesa de diseño (una a la vez)`,
        llevando: null, entregadas: 0, fin: false,
        iniciar() { e.on('pickup', p => {
            if (this.llevando) {
                p.recogido = false;
                e.scene.add(p.group);
                return e.emit('msg', 'Ya llevas una pieza — instálala primero');
            }
            this.llevando = p;
            e.emit('msg', `Pieza «${p.pieza}» → a la mesa`);
            e.emit('puntos', 5);
        }); },
        tick() {
            if (this.fin || !this.llevando) return;
            if (mesa.contiene(e.jugador.pos)) {
                this.llevando.recogido = true;
                this.entregadas++;
                e.emit('puntos', 35, 'pieza instalada');
                e.emit('msg', `Pieza instalada · ${this.entregadas}/${pickups.length}`);
                e.sfx.deliver();
                e.particulas.emit(mesa.pos, 0xc98bff, 18, 4, .7, 1.6);
                // El instrumento toma cuerpo: bloque apilado junto a la mesa
                const seg = new THREE.Mesh(new THREE.BoxGeometry(1.6, .55, 1.6),
                    new THREE.MeshStandardMaterial({ color: 0xc98bff, roughness: .5,
                        emissive: 0xc98bff, emissiveIntensity: .3 }));
                seg.position.set(-18, .3 + this.entregadas * .58, -2.5);
                seg.castShadow = true; e.add(seg);
                this.llevando = null;
                if (this.entregadas >= pickups.length) { this.fin = true; e.emit('mision_ok'); }
            }
        },
        textoHud() {
            if (this.llevando) return `Instalando «${this.llevando.pieza}» · ${this.entregadas}/${pickups.length}`;
            return `Piezas instaladas: ${this.entregadas}/${pickups.length}`;
        },
        marcas() {
            const m = [{ x: mesa.pos.x, y: 4, z: mesa.pos.z, color: '#46d98b', icon: '⬢', txt: 'MESA DE DISEÑO' }];
            if (!this.llevando) {
                const j = e.jugador.pos;
                const libres = pickups.filter(p => !p.recogido)
                    .sort((a, b) => a.pos.distanceToSquared(j) - b.pos.distanceToSquared(j));
                for (const p of libres.slice(0, 6))
                    m.push({ x: p.pos.x, y: 1.7, z: p.pos.z, color: '#c98bff', txt: 'pieza' });
            }
            return m;
        },
    };
    return M;
}

/* Etapa 5 · PROCESAMIENTO (pila)
 * Normalización: elimina NULLs y DUPLICADOS (hostiles) pero NO dispares
 * a los REGISTROS VÁLIDOS (verdes, inofensivos — huyen). 3 errores = falla. */
export function mProcesamiento(e, ctx) {
    const RONDAS = [
        { validos: 2, ruido: 3 }, { validos: 2, ruido: 4 }, { validos: 3, ruido: 5 },
    ].map(r => ctx.dif >= 2 ? { validos: r.validos + 1, ruido: r.ruido + 1 } : r);
    const NULOS = ['NULL-%02d', 'DUP-%02d', 'NULO-%02d', 'DUPLICADO-%02d', 'FORMATO-ERR-%02d'];
    const spawns = wpsLibres(e, ctx);
    let rid = 0;
    for (const [x, z] of [[-14, -12], [14, 12]]) new Botiquin(e, { x, z });

    const M = {
        titulo: 'Etapa 5 · Procesamiento',
        objetivo: 'Normaliza: elimina NULLs y duplicados. ¡No dispares a los registros válidos (verdes)!',
        ronda: 0, errores: 0, fin: false, entra: 0,
        iniciar() {
            e.on('acierto', d => {
                if (!d.mato) return;
                if (d.b?.cfg?.inofensivo) {
                    this.errores++;
                    e.emit('puntos', -150, '¡registro válido destruido!');
                    e.emit('bandera', 'ERROR DE NORMALIZACIÓN', `${this.errores}/3 registros válidos eliminados`);
                    e.sfx.wrong();
                    if (this.errores >= 3 && !this.fin) {
                        this.fin = true; this.entra = 0;
                        e.emit('mision_fail', 'La operación quedó degradada: 3 registros válidos perdidos');
                    }
                }
            });
            this.spawnRonda();
        },
        spawnRonda() {
            const R = RONDAS[this.ronda];
            for (let i = 0; i < R.ruido; i++) {
                const s = lejosJugador(e, spawns, 10);
                const n = NULOS[(Math.random() * NULOS.length) | 0].replace('%02d', String(rid++).padStart(2, '0'));
                bot(e, ctx, [s[0], 0, s[1]], { nombre: n, color: 0xe84c3c, hp: 70,
                    dano: 10, cadenciaMin: .9, cadenciaMax: 1.7, precision: .1, vision: 22 });
            }
            for (let i = 0; i < R.validos; i++) {
                const s = lejosJugador(e, spawns, 8);
                bot(e, ctx, [s[0], 0, s[1]], { nombre: `REG-OK-${String(rid++).padStart(2, '0')}`,
                    color: 0x46d98b, hp: 40, inofensivo: true, vel: 5.5 });
            }
            this.ronda++;
            e.sfx.wave();
            e.emit('bandera', `LOTE ${this.ronda}/${RONDAS.length}`, 'Depura: rojos = ruido · verdes = válidos');
        },
        tick(dt, t) {
            if (this.fin) return;
            const ruidoVivo = e.bots.filter(b => b.vivo && !b.cfg.inofensivo).length;
            if (ruidoVivo === 0 && !this.entra) {
                if (this.ronda >= RONDAS.length) { this.fin = true; return e.emit('mision_ok'); }
                this.entra = t + 5;
                e.emit('msg', 'Lote normalizado — siguiente lote en 5s');
            }
            if (this.entra && t >= this.entra) { this.entra = 0; this.spawnRonda(); }
        },
        textoHud() {
            const ruido = e.bots.filter(b => b.vivo && !b.cfg.inofensivo).length;
            const val = e.bots.filter(b => b.vivo && b.cfg.inofensivo).length;
            if (this.entra && this.entra > e.t) return `Siguiente lote en ${Math.ceil(this.entra - e.t)}s`;
            return `Lote ${Math.min(this.ronda, RONDAS.length)}/${RONDAS.length} · ruido: ${ruido} · válidos a salvo: ${val} · errores: ${this.errores}/3`;
        },
        marcas() {
            return e.bots.filter(b => b.vivo && !b.cfg.inofensivo).map(b => ({
                x: b.pos.x, y: 3.6, z: b.pos.z, color: '#e84c3c', txt: 'RUÍDO' }));
        },
    };
    return M;
}

/* Etapa 7 · DIFUSIÓN (barrio)
 * Recoge el informe final y publícalo canal a canal; cada publicación
 * abre el siguiente medio. La desinformación intenta interceptarte. */
export function mDifusion(e, ctx) {
    const CANALES = [
        { x: -22, z: 14, nombre: 'PORTAL WEB', color: 0x7cd8ff },
        { x: 20, z: 13.5, nombre: 'ADDA DISTRITAL', color: 0x46d98b },
        { x: 19, z: -12, nombre: 'BOLETÍN PRENSA', color: 0xffb37a },
        { x: -20, z: -5, nombre: 'MEDIO FÍSICO', color: 0xc98bff },
    ];
    const informe = new Pickup(e, { x: 0, y: 0, z: -5, color: 0xffffff, nombre: 'INFORME-FINAL', escala: 1.3 });
    const zonas = CANALES.map(c => {
        const p = puntoLibre(e, c.x, c.z, 1.2) || [c.x, c.z];
        return { zona: new Zona(e, { x: p[0], z: p[1], r: 3.2, color: c.color, nombre: c.nombre }), nombre: c.nombre, color: c.color };
    });
    const cfgHos = { hp: 80, dano: 11, cadenciaMin: .8, cadenciaMax: 1.6, precision: .09, vision: 30, vel: 5.2 };
    const spawns = wpsLibres(e, ctx);
    new Botiquin(e, { x: -20, z: 0 }); new Botiquin(e, { x: 20, z: 0 });

    const M = {
        titulo: 'Etapa 7 · Difusión',
        objetivo: 'Recoge el informe final y publícalo en los 4 canales de difusión',
        llevando: false, publicados: 0, fin: false,
        iniciar() { e.on('pickup', p => {
            if (p !== informe) return;
            this.llevando = true;
            e.emit('msg', 'Informe de resultados en mano — al primer canal marcado');
            e.emit('puntos', 10);
        }); },
        tick(dt, t) {
            if (this.fin) return;
            const canal = zonas[this.publicados];
            if (canal && this.llevando && canal.zona.contiene(e.jugador.pos)) {
                this.publicados++;
                e.emit('puntos', 80, 'publicado');
                e.emit('msg', `${canal.nombre} publicado · ${this.publicados}/${zonas.length}`);
                e.sfx.deliver();
                e.particulas.emit(canal.zona.pos, canal.color, 22, 4, .8, 1.6);
                canal.zona.apagar();
                // La desinformación intenta interceptar la publicación
                if (this.publicados < zonas.length) {
                    const n = ctx.dif >= 1 ? 2 : 1;
                    for (let i = 0; i < n; i++) {
                        const s = lejosJugador(e, spawns, 12);
                        bot(e, ctx, [s[0], 0, s[1]], { nombre: 'FAKE-NEWS', color: 0xff7b9c, ...cfgHos });
                    }
                    e.emit('msg', '¡Ruido informativo interceptando!');
                    e.sfx.alert();
                } else { this.fin = true; e.emit('mision_ok'); }
            }
        },
        textoHud() {
            if (!this.llevando) return 'Recoge el INFORME FINAL en la plaza';
            const canal = zonas[this.publicados];
            if (!canal) return `Publicados ${this.publicados}/${zonas.length}`;
            return `Informe → ${canal.nombre} · ${this.publicados}/${zonas.length}`;
        },
        marcas() {
            const m = [];
            if (!this.llevando) m.push({ x: informe.pos.x, y: 2.6, z: informe.pos.z, color: '#ffffff', icon: '★', txt: 'INFORME FINAL' });
            const canal = zonas[this.publicados];
            if (canal) m.push({ x: canal.zona.pos.x, y: 4, z: canal.zona.pos.z,
                color: '#' + canal.color.toString(16).padStart(6, '0'), icon: '▼', txt: 'PUBLICAR: ' + canal.nombre });
            return m;
        },
    };
    return M;
}

/* Etapa 8 · EVALUACIÓN (arena)
 * 4 oleadas de revisión + jefe final: EL AUDITOR. Cerrar el ciclo. */
export function mEvaluacion(e, ctx) {
    const RONDAS = [
        { n: 3, hp: 60, dano: 9, cadenciaMin: .9, cadenciaMax: 1.7, precision: .1, vel: 3.6 },
        { n: 4, hp: 80, dano: 11, cadenciaMin: .8, cadenciaMax: 1.5, precision: .08, vel: 4.4 },
        { n: 5, hp: 95, dano: 12, cadenciaMin: .7, cadenciaMax: 1.4, precision: .07, vel: 4.8 },
        { n: 4, hp: 110, dano: 14, cadenciaMin: .6, cadenciaMax: 1.3, precision: .06, vel: 5.2,
          jefe: { nombre: 'EL AUDITOR', color: 0xffd166, hp: 320, escala: 1.55, dano: 18,
                  cadenciaMin: .5, cadenciaMax: 1.1, precision: .05, vel: 5.5, vision: 40 } },
    ];
    const M = {
        titulo: 'Etapa 8 · Evaluación',
        objetivo: 'Resiste la revisión: 4 oleadas. En la última viene EL AUDITOR.',
        ronda: 0, entra: 0, espera: 4, vivos: 0, fin: false,
        iniciar() { e.emit('msg', `Revisión externa en ${this.espera}s — prepárate`); this.entra = e.t + this.espera; },
        spawnRonda() {
            const R = RONDAS[this.ronda];
            const spawns = ctx.spec.zonasSpawn.morado;
            for (let i = 0; i < R.n; i++) {
                const s = spawns[i % spawns.length];
                bot(e, ctx, [s[0] + Math.random() * 2 - 1, 0, s[1] + Math.random() * 2 - 1], R);
            }
            if (R.jefe) {
                const s = spawns[1 % spawns.length];
                const j = bot(e, ctx, [s[0], 0, s[1]], R.jefe);
                j.escala = R.jefe.escala;
                j.hMod = j.escala * .998;
                j.model.scale.setScalar(j.escala);
                j.hpBar.position.y = j.hMod * 1.4;
                if (j.label) j.label.position.y = j.hMod * 1.55;
                e.emit('bandera', 'EL AUDITOR', 'Última revisión — resistir');
            }
            this.ronda++;
            e.sfx.wave();
            e.emit('bandera', `REVISIÓN ${this.ronda}/${RONDAS.length}`, R.jefe ? 'EL AUDITOR en campo' : `${R.n} revisores`);
        },
        tick(dt, t) {
            if (this.fin) return;
            this.vivos = e.bots.filter(b => b.vivo).length;
            if (this.vivos === 0 && !this.entra) {
                if (this.ronda >= RONDAS.length) { this.fin = true; return e.emit('mision_ok'); }
                this.entra = t + (this.ronda === 0 ? this.espera : 6);
                e.emit('msg', this.ronda === 0 ? `Revisión en ${this.espera}s` : 'Siguiente revisión en 6s');
            }
            if (this.entra && t >= this.entra) { this.entra = 0; this.spawnRonda(); }
        },
        textoHud() {
            if (this.entra && this.entra > e.t) return `Siguiente revisión en ${Math.ceil(this.entra - e.t)}s`;
            const auditor = e.bots.find(b => b.vivo && b.nombre === 'EL AUDITOR');
            if (auditor) return `AUDITOR: ${Math.ceil(auditor.hp)}/${auditor.hpMax} · revisores vivos: ${this.vivos}`;
            return `Revisión ${this.ronda}/${RONDAS.length} · enemigos: ${this.vivos}`;
        },
    };
    return M;
}

export const MISIONES = { arena: mArena, barrio: mBarrio, torres: mTorres, pila: mPila,
    deteccion: mDeteccion, diseno: mDiseno, construccion: mTorres, recoleccion: mBarrio,
    procesamiento: mProcesamiento, analisis: mPila, difusion: mDifusion, evaluacion: mEvaluacion };
