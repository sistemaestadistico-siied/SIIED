/* Don Datico — Misiones · motor single-player
 * Render, input, controlador de jugador, colisiones AABB, hitscan,
 * partículas/trazas y audio sintetizado. Sin red: todo corre local. */
import * as THREE from 'three';

export const WALK = 6.5, SPRINT = 10.5, JUMP_V = 8.5, GRAV = -22, EYE = 1.62;
export const RADIUS = 0.45, ALTO = 1.8, STEP = 0.4;

const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3();

/* ---------- Geometría de rayos ---------- */
export function rayAABB(o, d, min, max) {
    let tmin = 0, tmax = Infinity;
    for (const k of ['x', 'y', 'z']) {
        const di = d[k];
        if (Math.abs(di) < 1e-9) {
            if (o[k] < min[k] || o[k] > max[k]) return null;
            continue;
        }
        let t1 = (min[k] - o[k]) / di, t2 = (max[k] - o[k]) / di;
        if (t1 > t2) [t1, t2] = [t2, t1];
        tmin = Math.max(tmin, t1); tmax = Math.min(tmax, t2);
        if (tmin > tmax) return null;
    }
    return tmin > 0 ? tmin : null;
}

/* Distancia² mínima rayo o+t·d (t≥0) ↔ segmento a-b → {t, d2} */
export function raySegment(o, d, a, b) {
    const ab = _v.subVectors(b, a), ao = _v2.subVectors(o, a);
    const dab = d.dot(ab), abab = ab.dot(ab), dao = d.dot(ao), abao = ab.dot(ao);
    const den = abab - dab * dab;
    let s, t;
    if (Math.abs(den) < 1e-9) { s = 0; t = Math.max(0, -dao); }
    else {
        s = THREE.MathUtils.clamp((abao - dao * dab) / den, 0, 1);
        t = s * dab - dao;
        if (t < 0) { t = 0; s = THREE.MathUtils.clamp(abab ? -abao / abab : 0, 0, 1); }
    }
    const pr = _v3.copy(o).addScaledVector(d, t);
    const ps = a.clone().addScaledVector(ab, s);
    return { t, d2: pr.distanceToSquared(ps) };
}

/* ---------- Emisor de eventos mínimo ---------- */
class Emitter {
    constructor() { this._h = {}; }
    on(ev, fn) { (this._h[ev] ??= []).push(fn); return this; }
    emit(ev, ...a) { (this._h[ev] || []).forEach(f => f(...a)); }
}

/* ---------- Audio sintetizado ---------- */
export class Audio {
    constructor() { this.ac = null; this.muted = false; this.amb = null; }
    ctx() { return this.ac ??= new (window.AudioContext || window.webkitAudioContext)(); }
    beep(f0, f1, dur, type = 'sawtooth', vol = .18, delay = 0) {
        if (this.muted) return;
        try {
            const ac = this.ctx(), t = ac.currentTime + delay;
            const o = ac.createOscillator(), g = ac.createGain();
            o.type = type;
            o.frequency.setValueAtTime(f0, t);
            o.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t + dur);
            g.gain.setValueAtTime(vol, t);
            g.gain.exponentialRampToValueAtTime(.001, t + dur);
            o.connect(g).connect(ac.destination);
            o.start(t); o.stop(t + dur + .02);
        } catch (e) { /* sin audio */ }
    }
    noise(dur, vol = .12, delay = 0, hp = 800) {
        if (this.muted) return;
        try {
            const ac = this.ctx(), t = ac.currentTime + delay;
            const n = Math.floor(ac.sampleRate * dur);
            const buf = ac.createBuffer(1, n, ac.sampleRate);
            const ch = buf.getChannelData(0);
            for (let i = 0; i < n; i++) ch[i] = (Math.random() * 2 - 1) * (1 - i / n);
            const src = ac.createBufferSource(); src.buffer = buf;
            const f = ac.createBiquadFilter(); f.type = 'highpass'; f.frequency.value = hp;
            const g = ac.createGain(); g.gain.value = vol;
            src.connect(f).connect(g).connect(ac.destination);
            src.start(t);
        } catch (e) {}
    }
    ambient(freqs = [55, 82.5, 110], vol = .03) {
        try {
            if (this.amb) { this.amb.gain.gain.value = vol; return; }
            const ac = this.ctx(), g = ac.createGain();
            g.gain.value = vol; g.connect(ac.destination);
            freqs.forEach(f => {
                const o = ac.createOscillator();
                o.type = 'sine'; o.frequency.value = f; o.connect(g); o.start();
            });
            this.amb = { gain: g };
        } catch (e) {}
    }
    get sfx() {
        const b = this.beep.bind(this), n = this.noise.bind(this);
        return {
            shoot:   () => { b(880, 120, .12, 'sawtooth', .12); n(.05, .06, 0, 2000); },
            botShot: () => { b(520, 90, .14, 'square', .07); },
            hit:     () => { b(1400, 1400, .05, 'square', .15); b(2100, 2100, .05, 'square', .12, .05); },
            kill:    () => { [523, 659, 784].forEach((f, i) => b(f, f, .12, 'square', .1, i * .08)); },
            hurt:    () => { b(220, 90, .2, 'sawtooth', .2); },
            death:   () => { b(400, 40, .6, 'sawtooth', .25); b(300, 30, .7, 'triangle', .2, .1); },
            respawn: () => { b(300, 900, .25, 'sine', .18); b(500, 1200, .2, 'sine', .12, .12); },
            step:    () => { n(.04, .035, 0, 400); },
            jump:    () => { b(180, 420, .14, 'sine', .08); },
            land:    () => { b(150, 65, .1, 'triangle', .1); n(.05, .05, 0, 300); },
            pickup:  () => { [660, 880, 1320].forEach((f, i) => b(f, f, .1, 'sine', .14, i * .06)); },
            deliver: () => { [523, 659, 784, 1046].forEach((f, i) => b(f, f, .14, 'triangle', .14, i * .09)); },
            wrong:   () => { b(200, 120, .25, 'square', .12); },
            wave:    () => { [392, 392, 392, 311].forEach((f, i) => b(f, f, .22, 'square', .12, i * .22)); },
            win:     () => { [523, 659, 784, 1046, 1318].forEach((f, i) => b(f, f, .2, 'triangle', .16, i * .11)); },
            lose:    () => { [400, 350, 300, 200].forEach((f, i) => b(f, f * .9, .3, 'sawtooth', .14, i * .25)); },
            tick:    () => b(1000, 1000, .04, 'square', .06),
            alert:   () => { b(700, 900, .08, 'square', .08); b(700, 900, .08, 'square', .08, .12); },
            ricochet:() => { b(2400 + Math.random() * 800, 600, .09, 'sine', .05); },
        };
    }
}

/* ---------- Partículas (pool único de Points) ---------- */
class Particulas {
    constructor(scene, max = 600) {
        this.max = max; this.n = 0;
        this.p = new Float32Array(max * 3);
        this.c = new Float32Array(max * 3);
        this.vel = new Float32Array(max * 3);
        this.life = new Float32Array(max);
        this.life0 = new Float32Array(max);
        this.geo = new THREE.BufferGeometry();
        this.geo.setAttribute('position', new THREE.BufferAttribute(this.p, 3));
        this.geo.setAttribute('color', new THREE.BufferAttribute(this.c, 3));
        this.mat = new THREE.PointsMaterial({ size: .09, vertexColors: true, transparent: true,
            opacity: .95, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true });
        this.pts = new THREE.Points(this.geo, this.mat);
        this.pts.frustumCulled = false;
        scene.add(this.pts);
        this.geo.setDrawRange(0, 0);
        this.col = new THREE.Color();
    }
    emit(pos, color, n = 10, speed = 3, life = .4, up = 1, spread = 1) {
        this.col.set(color);
        for (let k = 0; k < n; k++) {
            if (this.n >= this.max) return;
            const i = this.n++;
            this.p[i * 3] = pos.x; this.p[i * 3 + 1] = pos.y; this.p[i * 3 + 2] = pos.z;
            this.vel[i * 3] = (Math.random() - .5) * speed * spread;
            this.vel[i * 3 + 1] = Math.random() * speed * up;
            this.vel[i * 3 + 2] = (Math.random() - .5) * speed * spread;
            this.c[i * 3] = this.col.r; this.c[i * 3 + 1] = this.col.g; this.c[i * 3 + 2] = this.col.b;
            this.life[i] = this.life0[i] = life * (.6 + Math.random() * .6);
        }
    }
    tick(dt) {
        for (let i = 0; i < this.n; i++) {
            this.life[i] -= dt;
            if (this.life[i] <= 0) {
                const j = --this.n;
                for (let k = 0; k < 3; k++) {
                    this.p[i * 3 + k] = this.p[j * 3 + k];
                    this.vel[i * 3 + k] = this.vel[j * 3 + k];
                    this.c[i * 3 + k] = this.c[j * 3 + k];
                }
                this.life[i] = this.life[j]; this.life0[i] = this.life0[j];
                i--; continue;
            }
            this.vel[i * 3 + 1] -= 9 * dt;
            this.p[i * 3] += this.vel[i * 3] * dt;
            this.p[i * 3 + 1] += this.vel[i * 3 + 1] * dt;
            this.p[i * 3 + 2] += this.vel[i * 3 + 2] * dt;
            if (this.p[i * 3 + 1] < .02) { this.p[i * 3 + 1] = .02; this.vel[i * 3 + 1] *= -.3; }
            const f = this.life[i] / this.life0[i];
            this.c[i * 3] *= .98; this.c[i * 3 + 1] *= .98; this.c[i * 3 + 2] *= .98;
            if (f < .3) { this.c[i * 3] *= .9; this.c[i * 3 + 1] *= .9; this.c[i * 3 + 2] *= .9; }
        }
        this.geo.attributes.position.needsUpdate = true;
        this.geo.attributes.color.needsUpdate = true;
        this.geo.setDrawRange(0, this.n);
    }
}

/* ---------- Trazas de disparo (pool) ---------- */
class Trazas {
    constructor(scene) {
        this.scene = scene; this.pool = []; this.vivas = [];
        this.geo = new THREE.CylinderGeometry(1, 1, 1, 5, 1, true);
        this.flashTex = (() => {
            const cv = document.createElement('canvas'); cv.width = cv.height = 64;
            const g = cv.getContext('2d');
            const gr = g.createRadialGradient(32, 32, 2, 32, 32, 32);
            gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(.3, 'rgba(255,240,180,.9)');
            gr.addColorStop(1, 'rgba(255,200,80,0)');
            g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
            return new THREE.CanvasTexture(cv);
        })();
    }
    _get(color) {
        let t = this.pool.pop();
        if (!t) {
            t = new THREE.Mesh(this.geo, new THREE.MeshBasicMaterial({
                transparent: true, opacity: .9, depthWrite: false, blending: THREE.AdditiveBlending }));
            t.frustumCulled = false;
        }
        t.material.color.set(color);
        return t;
    }
    disparo(a, b, color, grosor = .014, vida = .09) {
        const dir = _v.subVectors(b, a), len = dir.length();
        if (len < .01) return;
        const t = this._get(color);
        t.scale.set(grosor, len, grosor);
        t.position.copy(a).addScaledVector(dir, .5);
        t.quaternion.setFromUnitVectors(_v2.set(0, 1, 0), dir.normalize());
        t.userData.life = t.userData.life0 = vida;
        this.scene.add(t); this.vivas.push(t);
    }
    flash(pos, color, size = .5) {
        const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.flashTex, color,
            transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
        sp.scale.setScalar(size * (.8 + Math.random() * .5));
        sp.position.copy(pos);
        sp.userData.life = sp.userData.life0 = .06;
        sp.userData.sprite = true;
        this.scene.add(sp); this.vivas.push(sp);
    }
    tick(dt) {
        for (let i = this.vivas.length - 1; i >= 0; i--) {
            const t = this.vivas[i];
            t.userData.life -= dt;
            t.material.opacity = Math.max(0, t.userData.life / t.userData.life0) * .9;
            if (t.userData.life <= 0) {
                this.scene.remove(t); this.vivas.splice(i, 1);
                if (t.userData.sprite) t.material.dispose(); else this.pool.push(t);
            }
        }
    }
}

/* ---------- Motor ---------- */
export class Engine extends Emitter {
    constructor(container) {
        super();
        this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
        this.renderer.setSize(innerWidth, innerHeight);
        this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.1;
        container.appendChild(this.renderer.domElement);
        this.dom = this.renderer.domElement;

        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, innerWidth / innerHeight, .05, 400);
        this.camera.rotation.order = 'YXZ';
        this.scene.add(this.camera);
        this.clock = new THREE.Clock();
        this.audio = new Audio();
        this.sfx = this.audio.sfx;

        this.keys = {};
        this.mouseDown = false;
        this.mouseDX = 0; this.mouseDY = 0;
        this.boxes = [];
        this.bounds = { minX: -22, maxX: 22, minZ: -22, maxZ: 22 };
        this.ents = [];          // objetos con tick(dt)
        this.bots = [];
        this.activo = false;     // juego corriendo (no menú)
        this.pausa = false;
        this.t = 0;
        this.mapa = null;

        this.jugador = {
            pos: new THREE.Vector3(), vy: 0, yaw: 0, pitch: 0, grounded: true,
            hp: 100, hpMax: 100, vivo: true, ultDanio: -99, corriendo: false, moviendo: false,
            fovBase: 75, bob: 0, retro: 0, kickPitch: 0, ultDisparo: -99, cadencia: .17,
        };
        this.particulas = new Particulas(this.scene);
        this.trazas = new Trazas(this.scene);
        this._arma();
        this._input();
        this._loopFn = null;
        this.cuerpos = [];       // ids de meshes del mapa para limpiar
    }

    /* ----- Arma en primera persona ----- */
    _arma() {
        const g = new THREE.Group();
        const dark = new THREE.MeshStandardMaterial({ color: 0x1b2a3a, roughness: .35, metalness: .7 });
        const acc = new THREE.MeshStandardMaterial({ color: 0x2B7D59, roughness: .4, metalness: .3,
            emissive: 0x0a3a24, emissiveIntensity: .5 });
        const body = new THREE.Mesh(new THREE.BoxGeometry(.09, .12, .36), dark);
        const top = new THREE.Mesh(new THREE.BoxGeometry(.06, .04, .2), acc); top.position.set(0, .08, -.02);
        const barrel = new THREE.Mesh(new THREE.CylinderGeometry(.02, .03, .24, 10), dark);
        barrel.rotation.x = Math.PI / 2; barrel.position.z = -.28;
        const orb = new THREE.Mesh(new THREE.SphereGeometry(.04, 14, 10),
            new THREE.MeshBasicMaterial({ color: 0x46d98b }));
        orb.position.set(0, .02, -.2);
        const grip = new THREE.Mesh(new THREE.BoxGeometry(.07, .15, .08), dark);
        grip.position.set(0, -.12, .08); grip.rotation.x = .35;
        const boca = new THREE.Object3D(); boca.position.set(0, 0, -.42);
        g.add(body, top, barrel, orb, grip, boca);
        g.position.set(.28, -.26, -.5);
        this.camera.add(g);
        this.arma = g; this.armaOrb = orb; this.armaBoca = boca;
        this.armaBase = g.position.clone();
        this.luzArma = new THREE.PointLight(0x46d98b, 0, 4, 2);
        this.luzArma.position.set(0, 0, -.4);
        g.add(this.luzArma);
    }

    /* ----- Input ----- */
    _input() {
        addEventListener('keydown', e => {
            if (e.code === 'Tab') e.preventDefault();
            this.keys[e.code] = true;
            this.emit('key', e.code, true);
        });
        addEventListener('keyup', e => { this.keys[e.code] = false; this.emit('key', e.code, false); });
        addEventListener('mousedown', e => {
            if (document.pointerLockElement === this.dom && e.button === 0) this.mouseDown = true;
        });
        addEventListener('mouseup', e => { if (e.button === 0) this.mouseDown = false; });
        addEventListener('mousemove', e => {
            if (document.pointerLockElement !== this.dom) return;
            const j = this.jugador;
            j.yaw -= e.movementX * .0021;
            j.pitch = THREE.MathUtils.clamp(j.pitch - e.movementY * .0021, -1.45, 1.45);
            this.mouseDX += e.movementX; this.mouseDY += e.movementY;
        });
        document.addEventListener('pointerlockchange', () => {
            const lock = document.pointerLockElement === this.dom;
            this.emit('lock', lock);
            if (!lock) { this.mouseDown = false; for (const k in this.keys) this.keys[k] = false; }
        });
        addEventListener('resize', () => {
            this.camera.aspect = innerWidth / innerHeight;
            this.camera.updateProjectionMatrix();
            this.renderer.setSize(innerWidth, innerHeight);
        });
        addEventListener('blur', () => { for (const k in this.keys) this.keys[k] = false; this.mouseDown = false; });
    }
    lock() { this.dom.requestPointerLock?.(); }
    unlock() { document.exitPointerLock?.(); }
    get locked() { return document.pointerLockElement === this.dom; }

    /* ----- Mapa: colisiones y limpieza ----- */
    limpiar() {
        for (const o of this.cuerpos) {
            this.scene.remove(o);
            o.traverse?.(c => {
                if (c.geometry && !c.userData.keepGeo) c.geometry.dispose();
                if (c.material && !c.userData.keepMat) {
                    (Array.isArray(c.material) ? c.material : [c.material]).forEach(m => {
                        if (m.map) m.map.dispose(); m.dispose(); });
                }
            });
        }
        this.cuerpos = []; this.boxes = []; this.ents = []; this.bots = [];
        this.scene.fog = null;
        this.mapa = null;
    }
    add(obj) { this.scene.add(obj); this.cuerpos.push(obj); return obj; }
    /* Caja sólida: mesh opcional + AABB de colisión */
    solido(cx, cy, cz, sx, sy, sz, mat = null, opts = {}) {
        const min = new THREE.Vector3(cx - sx / 2, cy - sy / 2, cz - sz / 2);
        const max = new THREE.Vector3(cx + sx / 2, cy + sy / 2, cz + sz / 2);
        const box = { min, max, tag: opts.tag || null };
        this.boxes.push(box);
        if (mat) {
            const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), mat);
            m.position.set(cx, cy, cz);
            m.castShadow = opts.shadow !== false; m.receiveShadow = true;
            if (mat.userData?.shared) m.userData.keepMat = true;
            this.add(m); box.mesh = m;
            if (opts.edges) {
                const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),
                    new THREE.LineBasicMaterial({ color: opts.edges, transparent: true, opacity: .35 }));
                e.position.copy(m.position); this.add(e);
            }
        }
        return box;
    }
    colisionCaja(min, max) { const b = { min, max }; this.boxes.push(b); return b; }

    /* ----- Física ----- */
    colisionar(p, radius = RADIUS, alto = ALTO) {
        for (const b of this.boxes) {
            if (p.x + radius > b.min.x && p.x - radius < b.max.x &&
                p.z + radius > b.min.z && p.z - radius < b.max.z &&
                p.y < b.max.y - .01 && p.y + alto > b.min.y) {
                const dx1 = (b.max.x + radius) - p.x, dx2 = p.x - (b.min.x - radius);
                const dz1 = (b.max.z + radius) - p.z, dz2 = p.z - (b.min.z - radius);
                const m = Math.min(dx1, dx2, dz1, dz2);
                if (m === dx1) p.x = b.max.x + radius;
                else if (m === dx2) p.x = b.min.x - radius;
                else if (m === dz1) p.z = b.max.z + radius;
                else p.z = b.min.z - radius;
            }
        }
        const B = this.bounds;
        p.x = THREE.MathUtils.clamp(p.x, B.minX + .6, B.maxX - .6);
        p.z = THREE.MathUtils.clamp(p.z, B.minZ + .6, B.maxZ - .6);
    }
    alturaSuelo(x, z, pies, radius = RADIUS * .7, step = STEP) {
        let g = 0;
        for (const b of this.boxes) {
            if (x + radius > b.min.x && x - radius < b.max.x &&
                z + radius > b.min.z && z - radius < b.max.z &&
                b.max.y <= pies + step) g = Math.max(g, b.max.y);
        }
        return g;
    }
    rayMuros(o, d, tMax = Infinity) {
        let t = tMax, hit = null;
        for (const b of this.boxes) {
            const tb = rayAABB(o, d, b.min, b.max);
            if (tb !== null && tb < t) { t = tb; hit = b; }
        }
        return { t, box: hit };
    }
    los(a, b) {
        const d = _v.subVectors(b, a), dist = d.length();
        if (dist < 1e-6) return true;
        d.divideScalar(dist);
        return this.rayMuros(a, d, dist).t >= dist;
    }
    /* Rayo contra cápsula vertical (pies p, radio r, alto h) */
    rayCapsula(o, d, pies, r = .5, h = ALTO) {
        const a = pies.clone().setY(pies.y + .25), b = pies.clone().setY(pies.y + h);
        const { t, d2 } = raySegment(o, d, a, b);
        return (d2 < r * r && t > 0) ? t : null;
    }

    /* ----- Jugador ----- */
    spawn(pos, yaw = 0) {
        const j = this.jugador;
        j.pos.set(pos[0], pos[1], pos[2]); j.vy = 0; j.yaw = yaw; j.pitch = 0;
        j.hp = j.hpMax; j.vivo = true; j.grounded = true; j.ultDanio = -99;
    }
    daniar(n, desde = null) {
        const j = this.jugador;
        if (!j.vivo) return;
        j.hp = Math.max(0, j.hp - n);
        j.ultDanio = this.t;
        this.emit('danio', n, desde, j.hp);
        if (j.hp <= 0) { j.vivo = false; this.emit('muerte'); }
    }
    _jugador(dt) {
        const j = this.jugador, k = this.keys;
        const corriendo = (k.ShiftLeft || k.ShiftRight) && (k.KeyW || k.KeyA || k.KeyS || k.KeyD);
        const speed = corriendo ? SPRINT : WALK;
        const f = _v.set(-Math.sin(j.yaw), 0, -Math.cos(j.yaw));
        const r = _v2.set(-f.z, 0, f.x);
        const mv = _v3.set(0, 0, 0);
        if (j.vivo) {
            if (k.KeyW) mv.add(f); if (k.KeyS) mv.sub(f);
            if (k.KeyD) mv.add(r); if (k.KeyA) mv.sub(r);
        }
        const moviendo = mv.lengthSq() > 0;
        if (moviendo) { mv.normalize().multiplyScalar(speed * dt); j.pos.add(mv); }
        j.moviendo = moviendo && j.grounded; j.corriendo = corriendo && moviendo;

        if (j.vivo && k.Space && j.grounded) { j.vy = JUMP_V; j.grounded = false; this.sfx.jump(); }
        const enAire = !j.grounded;
        j.vy += GRAV * dt;
        j.pos.y += j.vy * dt;
        const gy = this.alturaSuelo(j.pos.x, j.pos.z, j.pos.y);
        if (j.pos.y <= gy) {
            if (enAire && j.vy < -6) { this.sfx.land(); j.bobImpacto = Math.min(.25, -j.vy * .02); }
            j.pos.y = gy; j.vy = 0; j.grounded = true;
        } else if (j.pos.y > gy + .02) j.grounded = false;
        this.colisionar(j.pos);
        if (j.pos.y < -5) { this.emit('caida'); }

        // Pasos
        j.stepT = (j.stepT ?? 0) - dt;
        if (j.moviendo && j.stepT <= 0) {
            this.sfx.step(); j.stepT = corriendo ? .26 : .38;
            this.particulas.emit(_v.copy(j.pos).setY(j.pos.y + .05), 0x8fb8d8, 2, .8, .3, .4, 1);
        }
        // Regeneración tras 4 s sin daño
        if (j.vivo && j.hp < j.hpMax && this.t - j.ultDanio > 4) {
            j.hp = Math.min(j.hpMax, j.hp + 22 * dt);
            this.emit('hp', j.hp);
        }

        // Cámara: bob + FOV + kick
        const bobVel = j.moviendo ? (corriendo ? 13 : 9) : 0;
        j.bob += dt * bobVel;
        const amp = j.moviendo ? (corriendo ? .055 : .035) : 0;
        j.bobAmp = THREE.MathUtils.lerp(j.bobAmp ?? 0, amp, Math.min(1, dt * 8));
        j.bobImpacto = Math.max(0, (j.bobImpacto ?? 0) - dt * 1.2);
        const by = Math.abs(Math.sin(j.bob)) * j.bobAmp - j.bobImpacto;
        const bx = Math.sin(j.bob * .5) * j.bobAmp * .6;
        this.camera.position.set(j.pos.x + bx * Math.cos(j.yaw), j.pos.y + EYE + by, j.pos.z - bx * Math.sin(j.yaw));
        j.kickPitch = THREE.MathUtils.lerp(j.kickPitch, 0, Math.min(1, dt * 12));
        this.camera.rotation.y = j.yaw;
        this.camera.rotation.x = j.pitch + j.kickPitch;
        this.camera.rotation.z = THREE.MathUtils.lerp(this.camera.rotation.z,
            (k.KeyA ? .012 : 0) - (k.KeyD ? .012 : 0), Math.min(1, dt * 6));
        const fovObj = j.fovBase + (corriendo ? 8 : 0) + (j.retro * 30);
        this.camera.fov = THREE.MathUtils.lerp(this.camera.fov, fovObj, Math.min(1, dt * 7));
        this.camera.updateProjectionMatrix();

        // Arma: sway + bob + retroceso
        const sw = this.arma;
        const swayX = THREE.MathUtils.clamp(-this.mouseDX * .00045, -.05, .05);
        const swayY = THREE.MathUtils.clamp(this.mouseDY * .00045, -.05, .05);
        this.mouseDX *= .6; this.mouseDY *= .6;
        j.retro = Math.max(0, j.retro - dt * 3.2);
        sw.position.x = THREE.MathUtils.lerp(sw.position.x, this.armaBase.x + swayX + Math.sin(j.bob * .5) * j.bobAmp * .5, Math.min(1, dt * 10));
        sw.position.y = THREE.MathUtils.lerp(sw.position.y, this.armaBase.y + swayY + Math.abs(Math.sin(j.bob)) * j.bobAmp * .5 - (enAire ? .02 : 0), Math.min(1, dt * 10));
        sw.position.z = this.armaBase.z + j.retro * .12;
        sw.rotation.x = j.retro * .35 + (corriendo ? -.08 : 0);
        sw.rotation.z = THREE.MathUtils.lerp(sw.rotation.z, swayX * 1.5 - (corriendo ? .1 : 0), Math.min(1, dt * 8));
        this.luzArma.intensity = Math.max(0, this.luzArma.intensity - dt * 40);
        if (!j.vivo) { sw.rotation.x = THREE.MathUtils.lerp(sw.rotation.x, 1.2, dt * 3); sw.position.y = THREE.MathUtils.lerp(sw.position.y, -.6, dt * 3); }
    }

    /* Disparo del jugador: hitscan contra muros y bots. Devuelve impacto. */
    disparar() {
        const j = this.jugador;
        if (!j.vivo || this.t - j.ultDisparo < j.cadencia) return null;
        j.ultDisparo = this.t;
        const o = this.camera.getWorldPosition(new THREE.Vector3());
        const d = this.camera.getWorldDirection(new THREE.Vector3());
        // Dispersión leve en movimiento / aire
        const sp = (j.moviendo ? .012 : .003) + (j.grounded ? 0 : .02);
        d.x += (Math.random() - .5) * sp; d.y += (Math.random() - .5) * sp; d.z += (Math.random() - .5) * sp;
        d.normalize();
        const { t: tw } = this.rayMuros(o, d);
        let victima = null, tv = tw;
        for (const b of this.bots) {
            if (!b.vivo) continue;
            const t = this.rayCapsula(o, d, b.pos, .5);
            if (t !== null && t < tv) { tv = t; victima = b; }
        }
        const fin = o.clone().addScaledVector(d, Math.min(tv, 120));
        const boca = this.armaBoca.getWorldPosition(new THREE.Vector3());
        this.trazas.disparo(boca, fin, 0xbfffe0, .012, .07);
        this.trazas.flash(boca, 0xcfffe8, .22);
        this.luzArma.intensity = 6;
        j.retro = 1; j.kickPitch += .018;
        this.armaOrb.material.color.setHex(0xffffff);
        setTimeout(() => this.armaOrb.material.color.setHex(0x46d98b), 50);
        this.sfx.shoot();
        if (victima) {
            victima.recibir(this.dmg ?? 34, d, true);
            this.particulas.emit(fin, 0xff8a5c, 10, 3, .35, 1.2);
            this.emit('acierto', victima);
        } else if (tv < Infinity) {
            this.particulas.emit(fin, 0x9fd3ff, 7, 2.2, .3, 1);
            if (Math.random() < .5) this.sfx.ricochet();
        }
        return { victima, fin };
    }

    /* ----- Loop ----- */
    iniciar(fn) {
        this._loopFn = fn;
        if (this._raf) return;
        const loop = () => {
            this._raf = requestAnimationFrame(loop);
            const dt = Math.min(this.clock.getDelta(), .05);
            if (this.activo && !this.pausa) {
                this.t += dt;
                this._jugador(dt);
                if (this.mouseDown) this.disparar();
                for (const e of this.ents) e.tick?.(dt, this.t);
                for (const b of this.bots) b.tick(dt, this.t);
                this.mapa?.tick?.(dt, this.t);
                this._loopFn?.(dt, this.t);
            }
            this.particulas.tick(dt);
            this.trazas.tick(dt);
            this.renderer.render(this.scene, this.camera);
        };
        loop();
    }
}

/* Utilidades de materiales compartidos (no se disponen al limpiar) */
export function matShared(mat) { mat.userData.shared = true; return mat; }
export const lambert = (color, extra = {}) => new THREE.MeshLambertMaterial({ color, ...extra });
export const standard = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, ...extra });
export const basic = (color, extra = {}) => new THREE.MeshBasicMaterial({ color, ...extra });

/* Texto en sprite (etiquetas 3D) */
export function sprite(texto, color = '#eaf2f8', tam = 30, fondo = null) {
    const cv = document.createElement('canvas');
    const g0 = cv.getContext('2d'); g0.font = `bold ${tam}px Segoe UI, system-ui, sans-serif`;
    const w = Math.max(64, Math.ceil(g0.measureText(texto).width) + 28);
    cv.width = w; cv.height = tam + 26;
    const g = cv.getContext('2d');
    if (fondo) { g.fillStyle = fondo; g.beginPath(); g.roundRect(0, 0, w, cv.height, 10); g.fill(); }
    g.font = `bold ${tam}px Segoe UI, system-ui, sans-serif`;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.lineWidth = 6; g.strokeStyle = 'rgba(0,0,0,.8)';
    g.strokeText(texto, w / 2, cv.height / 2);
    g.fillStyle = color; g.fillText(texto, w / 2, cv.height / 2);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv),
        transparent: true, depthWrite: false }));
    sp.scale.set(w / cv.height * .6, .6, 1);
    return sp;
}
