/* Misiones por mapa. Cada misión devuelve:
 *   {titulo, objetivo, nBots} y opcionalmente tick/onPickup/onKill/listaBots.
 * El motor (main.js) gestiona hp/muerte del jugador y llama fin(true/false). */
import * as THREE from 'three';
import { Bot } from './bot.js';
import { Pickup, Zona, Antena, Botiquin } from './objetos.js';
import { GRAV, basic } from './engine.js';

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
        cfg: Object.assign({ waypoints: ctx.spec.wps || [] }, cfg),
    });
    e.scene.add(b.group);
    e.bots.push(b);
    return b;
}
function lejosJugador(e, pts, dist = 10) {
    const j = e.jugador.pos;
    const libres = pts.filter(p => Math.hypot(p[0] - j.x, p[2] - j.z) > dist);
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
    pts.slice(0, TOTAL).forEach(([x, z], i) =>
        pickups.push(new Pickup(e, { x, y: 0, z, color: 0xffb37a, nombre: `paquete-${i}` })));
    const zona = new Zona(e, { x: ctx.spec.zonaKiosco[0], z: ctx.spec.zonaKiosco[1], r: 4, color: 0x46d98b, nombre: 'KIOSCO SIIED' });

    // Patrullas: en cuesta varían conteo y agresividad
    const cfgPat = [
        { n: 3, dano: 9, cadenciaMin: 1.0, cadenciaMax: 1.9, precision: .11, vision: 18 },
        { n: 4, dano: 11, cadenciaMin: .8, cadenciaMax: 1.6, precision: .09, vision: 22 },
        { n: 5, dano: 13, cadenciaMin: .7, cadenciaMax: 1.4, precision: .07, vision: 26 },
    ][Math.min(ctx.dif, 2)];
    const spawns = ctx.spec.wps;
    for (let i = 0; i < cfgPat.n; i++) {
        const s = lejosJugador(e, spawns, 14);
        bot(e, ctx, [s[0], 0, s[1]], cfgPat);
    }

    const M = {
        titulo: 'Barrio SIIED',
        objetivo: `Recupera ${TOTAL} paquetes de datos y entrégalos en el Kiosco SIIED`,
        lleva: 0, entregados: 0, fin: false,
        esc: false,
        iniciar() {
            e.on('pickup', p => {
                this.lleva += p.valor;
                e.emit('msg', `+1 paquete (llevas ${this.lleva}) — al Kiosco`);
            });
            // Botiquines entre casitas
            for (const [x, z] of [[-20, 0], [20, 0]]) new Botiquin(e, { x, z });
        },
        tick(dt, t) {
            if (this.fin) return;
            const j = e.jugador;
            if (zona.contiene(j.pos) && this.lleva > 0) {
                this.entregados += this.lleva;
                e.emit('msg', `Entregados ${this.entregados}/${TOTAL} — ${Math.max(0, TOTAL - this.entregados)} restantes`);
                this.lleva = 0;
                e.sfx.deliver();
                e.particulas.emit(zona.pos, 0x46d98b, 18, 4, .7, 1.6);
                if (this.entregados >= TOTAL && !this.esc) {
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
            if (this.lleva > 0) return `Entregar ${this.lleva} en el Kiosco (${this.entregados}/${TOTAL})`;
            const quedan = pickups.filter(p => !p.recogido).length;
            return `Paquetes: ${this.entregados}/${TOTAL} · quedan ${quedan}`;
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
    const spawns = ctx.spec.wps;
    for (let i = 0; i < cfgPat.n; i++) {
        const s = lejosJugador(e, spawns, 14);
        bot(e, ctx, [s[0], 0, s[1]], cfgPat);
    }
    for (const [x, z] of [[-14, -7], [14, 6]]) new Botiquin(e, { x, z });

    const M = {
        titulo: 'Parque de Barras',
        objetivo: `Escala las torres marcadas y activa las ${antenas.length} antenas (mantén E)`,
        fin: false,
        iniciar() { e.on('antena', a => e.emit('msg', `${a.nombre} activada`)); },
        tick(dt, t) {
            if (this.fin) return;
            const j = e.jugador;
            for (const p of pads) {
                p.aro.scale.setScalar(1 + Math.sin(t * 3) * .07);
                if (j.grounded && Math.hypot(j.pos.x - p.x, j.pos.z - p.z) < 1.6) {
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
    };
    return M;
}

/* ============ Misión 4: Pila — clasifica por serie ============ */
export const SERIES = [
    { nombre: 'SERIE GEO', color: 0x46d98b },
    { nombre: 'SERIE SOC', color: 0xffb37a },
    { nombre: 'SERIE ECO', color: 0xc98bff },
    { nombre: 'SERIE DEM', color: 0x7cd8ff },
];
export function mPila(e, ctx) {
    const POR_SERIE = ctx.dif >= 2 ? 4 : 3;
    const pickups = [];
    // Chontaduros de cada serie desperdigados por el patio
    SERIES.forEach((s, si) => {
        for (let i = 0; i < POR_SERIE; i++) {
            const a = Math.random() * Math.PI * 2, r = 8 + Math.random() * 14;
            let x = Math.cos(a) * r, z = Math.sin(a) * r;
            x = THREE.MathUtils.clamp(x, -27, 27); z = THREE.MathUtils.clamp(z, -23, 23);
            pickups.push(new Pickup(e, { x, y: 0, z, color: s.color, valor: si }));
        }
    });
    const zonas = ctx.spec.torres.map(t =>
        new Zona(e, { x: t.x, z: t.z, r: 3.4, color: t.serie.color, nombre: t.serie.nombre }));
    const tot = POR_SERIE * SERIES.length;
    const restantes = {}; SERIES.forEach(s => restantes[s.nombre] = POR_SERIE);

    const cfgPat = [
        { n: 2, dano: 9, cadenciaMin: 1.1, cadenciaMax: 1.9, precision: .12, vision: 16 },
        { n: 3, dano: 10, cadenciaMin: .9, cadenciaMax: 1.7, precision: .09, vision: 20 },
        { n: 4, dano: 12, cadenciaMin: .8, cadenciaMax: 1.5, precision: .07, vision: 24 },
    ][Math.min(ctx.dif, 2)];
    const spawns = ctx.spec.wps;
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
            e.emit('msg', `Llevas un chontaduro ${s.nombre} → a su torre`);
        }); },
        tick(dt, t) {
            if (this.fin) return;
            const j = e.jugador;
            if (!this.llevando) return;
            const s = SERIES[this.llevando.valor];
            const zona = zonas[SERIES.indexOf(s)];
            // indicador en el HUD de lo que carga
            if (zona.contiene(j.pos)) {
                this.llevando.recogido = true;
                this.entregados++;
                restantes[s.nombre]--;
                e.emit('msg', `Clasificado ${s.nombre} · ${this.entregados}/${tot}`);
                e.sfx.deliver();
                e.particulas.emit(zona.pos, s.color, 20, 4, .7, 1.6);
                // La torre crece un slot
                const torre = ctx.spec.torres[SERIES.indexOf(s)];
                const idx = POR_SERIE - restantes[s.nombre];
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
    };
    return M;
}

export const MISIONES = { arena: mArena, barrio: mBarrio, torres: mTorres, pila: mPila };
