/* Don Datico — Misiones · motor single-player
 * Render, input, controlador de jugador, colisiones AABB, hitscan,
 * partículas/trazas y audio sintetizado. Sin red: todo corre local. */
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { Arma } from './arma.js';

export const WALK = 6.2, SPRINT = 9.8, CROUCH = 3.2, ADS = 3.9, JUMP_V = 8.3, GRAV = -22, EYE = 1.62, EYE_C = 1.08;
export const RADIUS = 0.45, ALTO = 1.8, ALTO_C = 1.25, STEP = 0.4;
const ACC_SUELO = 70, FRICCION = 11, ACC_AIRE = 14, COYOTE = .11, BUFFER_SALTO = .13;
export const DANO_CUERPO = 26, MULT_CABEZA = 2.4;

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
    off(ev) { delete this._h[ev]; return this; }
    emit(ev, ...a) { (this._h[ev] || []).forEach(f => f(...a)); }
}

/* ---------- Audio sintetizado ---------- */
export class Audio {
    constructor() { this.ac = null; this.muted = false; this.amb = null; this.vol = .8; this.master = null; }
    ctx() {
        if (!this.ac) {
            const ac = this.ac = new (window.AudioContext || window.webkitAudioContext)();
            const comp = ac.createDynamicsCompressor();
            comp.threshold.value = -14; comp.knee.value = 10; comp.ratio.value = 5;
            comp.attack.value = .003; comp.release.value = .18;
            this.master = ac.createGain(); this.master.gain.value = this.vol;
            this.master.connect(comp).connect(ac.destination);
            // Eco corto: cola de los disparos
            this.eco = ac.createDelay(1); this.eco.delayTime.value = .11;
            const fb = ac.createGain(); fb.gain.value = .3;
            const lp = ac.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 1700;
            this.ecoIn = ac.createGain(); this.ecoIn.gain.value = .35;
            this.ecoIn.connect(this.eco); this.eco.connect(lp).connect(fb).connect(this.eco); lp.connect(this.master);
            const n = ac.sampleRate, buf = ac.createBuffer(1, n, n), ch = buf.getChannelData(0);
            for (let i = 0; i < n; i++) ch[i] = Math.random() * 2 - 1;
            this.ruido = buf;
        }
        if (this.ac.state === 'suspended') this.ac.resume();
        return this.ac;
    }
    setVol(v) { this.vol = v; if (this.master) this.master.gain.value = v; }
    _out(node, pan = 0, eco = false) {
        let n = node;
        if (pan && this.ac.createStereoPanner) {
            const p = this.ac.createStereoPanner(); p.pan.value = THREE.MathUtils.clamp(pan, -1, 1);
            n.connect(p); n = p;
        }
        n.connect(this.master); if (eco) n.connect(this.ecoIn);
    }
    beep(f0, f1, dur, type = 'sawtooth', vol = .18, delay = 0, pan = 0, eco = false) {
        if (this.muted || vol <= 0) return;
        try {
            const ac = this.ctx(), t = ac.currentTime + delay;
            const o = ac.createOscillator(), g = ac.createGain();
            o.type = type;
            o.frequency.setValueAtTime(f0, t);
            o.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t + dur);
            g.gain.setValueAtTime(vol, t);
            g.gain.exponentialRampToValueAtTime(.001, t + dur);
            o.connect(g); this._out(g, pan, eco);
            o.start(t); o.stop(t + dur + .02);
        } catch (e) { /* sin audio */ }
    }
    noise(dur, vol = .12, delay = 0, hp = 800, pan = 0, eco = false, lp = 0) {
        if (this.muted || vol <= 0) return;
        try {
            const ac = this.ctx(), t = ac.currentTime + delay;
            const src = ac.createBufferSource(); src.buffer = this.ruido;
            const f = ac.createBiquadFilter(); f.type = 'highpass'; f.frequency.value = hp;
            const g = ac.createGain();
            g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(.001, t + dur);
            let n = src.connect(f);
            if (lp) { const l = ac.createBiquadFilter(); l.type = 'lowpass'; l.frequency.value = lp; n = n.connect(l); }
            n.connect(g); this._out(g, pan, eco);
            src.start(t, Math.random() * .5); src.stop(t + dur + .02);
        } catch (e) {}
    }
    ambient(freqs = [55, 82.5, 110], vol = .03) {
        try {
            if (this.amb) { this.amb.gain.gain.value = vol; return; }
            const ac = this.ctx(), g = ac.createGain();
            g.gain.value = vol; g.connect(this.master);
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
            shoot:   () => {
                b(160, 42, .14, 'sine', .42); n(.1, .24, 0, 900, 0, true);
                b(1700, 260, .07, 'square', .045); n(.025, .06, .015, 4200);
            },
            botShot: (pan = 0, vol = 1) => {
                b(520, 90, .14, 'square', .06 * vol, 0, pan); n(.08, .1 * vol, 0, 700, pan, true, 3000);
            },
            charge:  (pan = 0, vol = 1) => b(320, 980, .26, 'sine', .05 * vol, 0, pan),
            hit:     () => { n(.02, .14, 0, 3000); b(1250, 1250, .035, 'square', .07); },
            head:    () => { b(1900, 1900, .07, 'triangle', .16); b(2850, 2850, .1, 'sine', .12, .04); n(.02, .12, 0, 3000); },
            kill:    () => { [523, 659, 784].forEach((f, i) => b(f, f, .12, 'square', .1, i * .08)); },
            hurt:    () => { b(220, 90, .2, 'sawtooth', .2); b(80, 40, .2, 'sine', .3); },
            reloadOut: () => { n(.03, .12, 0, 3000); b(900, 600, .05, 'square', .04, .02); },
            reloadIn:  () => { n(.025, .14, 0, 2500); n(.02, .12, .07, 3500); b(500, 950, .12, 'sine', .07, .05); },
            rack:    () => { n(.04, .14, 0, 2200); n(.03, .12, .06, 3000); },
            dry:     () => b(2200, 2000, .025, 'square', .06),
            beat:    () => { b(70, 48, .12, 'sine', .32); b(64, 44, .12, 'sine', .25, .18); },
            fall:    (pan = 0) => { n(.14, .12, 0, 150, pan, false, 900); b(90, 40, .16, 'triangle', .12, 0, pan); },
            spawn:   (pan = 0) => { b(200, 1200, .35, 'sine', .06, 0, pan); n(.3, .04, 0, 2000, pan); },
            death:   () => { b(400, 40, .6, 'sawtooth', .25); b(300, 30, .7, 'triangle', .2, .1); },
            respawn: () => { b(300, 900, .25, 'sine', .18); b(500, 1200, .2, 'sine', .12, .12); },
            step:    () => { n(.05, .05, 0, 220 + Math.random() * 260, 0, false, 1300 + Math.random() * 500); },
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

/* ---------- Marcas de impacto en superficies (pool) ---------- */
class Marcas {
    constructor(scene, max = 60) {
        const cv = document.createElement('canvas'); cv.width = cv.height = 64;
        const g = cv.getContext('2d');
        const gr = g.createRadialGradient(32, 32, 1, 32, 32, 30);
        gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(.18, 'rgba(160,255,210,.95)');
        gr.addColorStop(.35, 'rgba(10,20,25,.9)'); gr.addColorStop(1, 'rgba(10,20,25,0)');
        g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
        const tex = new THREE.CanvasTexture(cv);
        this.geo = new THREE.PlaneGeometry(.2, .2);
        this.lista = [];
        for (let i = 0; i < max; i++) {
            const m = new THREE.Mesh(this.geo, new THREE.MeshBasicMaterial({ map: tex, transparent: true,
                depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4 }));
            m.visible = false; m.userData.vida = 0; scene.add(m); this.lista.push(m);
        }
        this.i = 0;
    }
    poner(p, normal) {
        const m = this.lista[this.i = (this.i + 1) % this.lista.length];
        m.position.copy(p).addScaledVector(normal, .012);
        m.lookAt(_v.copy(m.position).add(normal));
        m.rotation.z = Math.random() * 6.28;
        m.scale.setScalar(.7 + Math.random() * .5);
        m.visible = true; m.userData.vida = 9; m.material.opacity = 1;
    }
    tick(dt) {
        for (const m of this.lista) {
            if (!m.visible) continue;
            m.userData.vida -= dt;
            if (m.userData.vida < 2) m.material.opacity = Math.max(0, m.userData.vida / 2);
            if (m.userData.vida <= 0) m.visible = false;
        }
    }
    ocultar() { for (const m of this.lista) m.visible = false; }
}

/* Normal de la cara de una AABB tocada en el punto p */
function normalCaja(b, p, out) {
    const d = [[p.x - b.min.x, -1, 0, 0], [b.max.x - p.x, 1, 0, 0], [p.y - b.min.y, 0, -1, 0],
        [b.max.y - p.y, 0, 1, 0], [p.z - b.min.z, 0, 0, -1], [b.max.z - p.z, 0, 0, 1]];
    let m = d[0]; for (const x of d) if (x[0] < m[0]) m = x;
    return out.set(m[1], m[2], m[3]);
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
        this.ajustes = { sens: 1, fov: 75, vol: .8, calidad: 'alta' };

        this.keys = {};
        this.mouseDown = false; this.mouseDer = false;
        this.mouseDX = 0; this.mouseDY = 0;
        this.trauma = 0; this.spread = 0; this.recoil = { p: 0, y: 0 };
        this.stats = { disparos: 0, aciertos: 0, cabezas: 0, bajas: 0, danioRecibido: 0 };
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
            fovBase: 75, bob: 0, retro: 0, kickPitch: 0, ultDisparo: -99, cadencia: .12,
            vel: new THREE.Vector3(), agachado: false, alto: ALTO, ojo: EYE, coyote: 0, bufSalto: 0,
            ultSuelo: 0, aim: false,
        };
        this.particulas = new Particulas(this.scene);
        this.trazas = new Trazas(this.scene);
        this.marcas = new Marcas(this.scene);
        this.vm = new Arma(this.renderer);
        this.vm.sfx = this.sfx;
        this._post();
        this._input();
        this._loopFn = null;
        this.cuerpos = [];       // ids de meshes del mapa para limpiar
    }

    /* ----- Postproceso (bloom) y calidad ----- */
    _post() {
        this.composer = new EffectComposer(this.renderer);
        this.composer.addPass(new RenderPass(this.scene, this.camera));
        this.bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .55, .5, .82);
        this.composer.addPass(this.bloom);
        this.composer.addPass(new OutputPass());
    }
    aplicarAjustes(a) {
        Object.assign(this.ajustes, a);
        const q = +this.ajustes.calidad;               // .55 baja / .8 media / 1 alta
        this.renderer.setPixelRatio(Math.min(devicePixelRatio, q < .7 ? 1 : q < .95 ? 1.25 : 1.75));
        this.renderer.setSize(innerWidth, innerHeight);
        this.composer.setPixelRatio(this.renderer.getPixelRatio());
        this.composer.setSize(innerWidth, innerHeight);
        const sombras = this.ajustes.sombras !== false && q >= .7;
        if (this.renderer.shadowMap.enabled !== sombras) {
            this.renderer.shadowMap.enabled = sombras;
            this.scene.traverse(o => { if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.needsUpdate = true); });
        }
        this.jugador.fovBase = this.ajustes.fov;
        this.audio.setVol(this.ajustes.vol);
    }
    sacudir(n) { this.trauma = Math.min(1, this.trauma + n); }

    /* ----- Input ----- */
    _input() {
        addEventListener('keydown', e => {
            if (e.code === 'Tab' || (e.code === 'KeyF' && this.locked)) e.preventDefault();
            if (!e.repeat && this.activo && this.locked && this.jugador.vivo) {
                if (e.code === 'KeyR' && this.vm.recargar()) this.emit('recarga');
                if (e.code === 'KeyF') this.vm.inspeccionar();
            }
            this.keys[e.code] = true;
            this.emit('key', e.code, true);
        });
        addEventListener('keyup', e => { this.keys[e.code] = false; this.emit('key', e.code, false); });
        addEventListener('contextmenu', e => { if (this.locked) e.preventDefault(); });
        addEventListener('mousedown', e => {
            if (document.pointerLockElement !== this.dom) return;
            if (e.button === 0) {
                this.mouseDown = true;
                if (this.vm.mag <= 0 && this.activo) { this.sfx.dry(); if (this.vm.recargar()) this.emit('recarga'); }
            }
            if (e.button === 2) this.mouseDer = true;
        });
        addEventListener('mouseup', e => { if (e.button === 0) this.mouseDown = false; if (e.button === 2) this.mouseDer = false; });
        addEventListener('mousemove', e => {
            if (document.pointerLockElement !== this.dom) return;
            const j = this.jugador;
            const s = .0021 * this.ajustes.sens * (this.vm.aim > .5 ? .62 : 1);
            j.yaw -= e.movementX * s;
            j.pitch = THREE.MathUtils.clamp(j.pitch - e.movementY * s, -1.45, 1.45);
            this.mouseDX += e.movementX; this.mouseDY += e.movementY;
        });
        document.addEventListener('pointerlockchange', () => {
            const lock = document.pointerLockElement === this.dom;
            this.emit('lock', lock);
            if (!lock) { this.mouseDown = false; this.mouseDer = false; for (const k in this.keys) this.keys[k] = false; }
        });
        addEventListener('resize', () => {
            this.camera.aspect = innerWidth / innerHeight;
            this.camera.updateProjectionMatrix();
            this.renderer.setSize(innerWidth, innerHeight);
            this.composer.setSize(innerWidth, innerHeight);
            this.vm.resize(innerWidth / innerHeight);
        });
        addEventListener('blur', () => { for (const k in this.keys) this.keys[k] = false; this.mouseDown = false; this.mouseDer = false; });
    }
    lock() { try { this.dom.requestPointerLock?.()?.catch?.(() => {}); } catch (x) {} }
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
        // Bots: se añadieron con scene.add (el GLB comparte geometría
        // entre clones — NO disponer); retirarlos de la escena.
        for (const b of this.bots) this.scene.remove(b.group);
        this.cuerpos = []; this.boxes = []; this.ents = []; this.bots = [];
        // Listeners de misión (pickup/antena/acierto) se re-registran en cada
        // intento — hay que limpiarlos o se acumulan y duplican conteos.
        // main.js re-registra su handler de 'acierto' en iniciarMision().
        this.off('pickup'); this.off('antena'); this.off('acierto');
        this.scene.fog = null;
        this.mapa = null;
        this.marcas.ocultar();
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

    /* Punto (x,z) dentro de algún collider (+margen), en rango vertical */
    enSolido(x, z, pad = .3, y0 = 0, y1 = 1.8) {
        for (const b of this.boxes) {
            if (x > b.min.x - pad && x < b.max.x + pad &&
                z > b.min.z - pad && z < b.max.z + pad &&
                b.max.y > y0 && b.min.y < y1) return true;
        }
        return false;
    }

    /* ----- Física ----- */
    colisionar(p, radius = RADIUS, alto = ALTO) {
        // Dos pasadas: empujar fuera de una caja puede meter en otra.
        for (let pass = 0; pass < 2; pass++)
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
        j.pos.set(pos[0], pos[1], pos[2]); j.vy = 0; j.yaw = yaw; j.pitch = 0; j.vel.set(0, 0, 0);
        j.hp = j.hpMax; j.vivo = true; j.grounded = true; j.ultDanio = -99;
        j.agachado = false; j.alto = ALTO; j.ojo = EYE; j.kickPitch = 0; j.ultDisparo = -99;
        this.recoil.p = this.recoil.y = 0; this.trauma = 0; this.bloomFuego = 0;
        this.camera.fov = j.fovBase; this.vm.sacar();
    }
    daniar(n, desde = null) {
        const j = this.jugador;
        if (!j.vivo) return;
        j.hp = Math.max(0, j.hp - n);
        j.ultDanio = this.t;
        this.stats.danioRecibido += n;
        this.sacudir(.2 + n * .012);
        j.kickPitch += .02;
        this.emit('danio', n, desde, j.hp);
        if (j.hp <= 0) { j.vivo = false; this.emit('muerte'); }
    }
    _techo(j) {
        for (const b of this.boxes) {
            if (j.pos.x + RADIUS > b.min.x && j.pos.x - RADIUS < b.max.x &&
                j.pos.z + RADIUS > b.min.z && j.pos.z - RADIUS < b.max.z &&
                b.min.y > j.pos.y + .1 && b.min.y < j.pos.y + ALTO) return true;
        }
        return false;
    }
    _jugador(dt) {
        const j = this.jugador, k = this.keys, vm = this.vm, lerp = THREE.MathUtils.lerp;
        // Agacharse (C / Ctrl izq.); no se levanta bajo un techo
        if (j.vivo && (k.KeyC || k.ControlLeft)) j.agachado = true;
        else if (j.agachado && !this._techo(j)) j.agachado = false;
        j.alto = j.agachado ? ALTO_C : ALTO;
        j.ojo = lerp(j.ojo, j.agachado ? EYE_C : EYE, Math.min(1, dt * 12));
        j.aim = j.vivo && this.mouseDer && !vm.recargando;

        const f = _v.set(-Math.sin(j.yaw), 0, -Math.cos(j.yaw));
        const r = _v2.set(-f.z, 0, f.x);
        const mv = _v3.set(0, 0, 0);
        if (j.vivo) {
            if (k.KeyW) mv.add(f); if (k.KeyS) mv.sub(f);
            if (k.KeyD) mv.add(r); if (k.KeyA) mv.sub(r);
        }
        const hayInput = mv.lengthSq() > 0;
        if (hayInput) mv.normalize();
        const corriendo = j.vivo && (k.ShiftLeft || k.ShiftRight) && k.KeyW && !k.KeyS && !j.agachado &&
            !j.aim && !this.mouseDown && this.t - j.ultDisparo > .25;
        const vmax = j.agachado ? CROUCH : j.aim ? ADS : corriendo ? SPRINT : WALK;
        // Aceleración + fricción en suelo; control aéreo reducido
        const vh = j.vel;
        if (j.grounded) {
            const sp = vh.length();
            if (sp > 0) vh.multiplyScalar(Math.max(0, sp - sp * FRICCION * dt) / sp);
        }
        if (hayInput) {
            const add = Math.min((j.grounded ? ACC_SUELO : ACC_AIRE) * dt, vmax - vh.dot(mv));
            if (add > 0) vh.addScaledVector(mv, add);
        }
        const latVel = vh.x * r.x + vh.z * r.z;
        j.pos.x += vh.x * dt; j.pos.z += vh.z * dt;
        const velH = Math.hypot(vh.x, vh.z);
        j.moviendo = velH > .6 && j.grounded;
        j.corriendo = corriendo && velH > WALK * .9;

        // Salto con coyote time y buffer de entrada
        if (k.Space && !j._sp && j.vivo) j.bufSalto = BUFFER_SALTO;
        j._sp = !!k.Space;
        j.bufSalto -= dt;
        j.coyote = j.grounded ? COYOTE : j.coyote - dt;
        if (j.bufSalto > 0 && j.coyote > 0 && j.vy <= .1) {
            j.vy = JUMP_V * (j.agachado ? .85 : 1); j.grounded = false; j.coyote = 0; j.bufSalto = 0;
            this.sfx.jump(); vm.impulsoAterrizaje(-.25);
        }
        const enAire = !j.grounded;
        j.vy += GRAV * dt;
        j.pos.y += j.vy * dt;
        const gy = this.alturaSuelo(j.pos.x, j.pos.z, j.pos.y);
        if (j.pos.y <= gy) {
            if (enAire && j.vy < -4) {
                const fz = Math.min(1, -j.vy / 18);
                this.sfx.land(); j.bobImpacto = fz * .16; vm.impulsoAterrizaje(fz); this.sacudir(fz * .12);
            }
            j.pos.y = gy; j.vy = 0; j.grounded = true;
        } else if (j.pos.y > gy + .02) j.grounded = false;
        const px = j.pos.x, pz = j.pos.z;
        this.colisionar(j.pos, RADIUS, j.alto);
        // Deslizar sobre muros: anular la componente que empuja contra ellos
        if (Math.abs(j.pos.x - px) > 1e-4 && Math.sign(j.pos.x - px) !== Math.sign(vh.x)) vh.x = 0;
        if (Math.abs(j.pos.z - pz) > 1e-4 && Math.sign(j.pos.z - pz) !== Math.sign(vh.z)) vh.z = 0;
        if (j.pos.y < -5) { this.emit('caida'); }

        // Pasos
        j.stepT = (j.stepT ?? 0) - dt;
        if (j.moviendo && j.stepT <= 0) {
            this.sfx.step(); j.stepT = j.corriendo ? .27 : j.agachado ? .55 : .4;
            this.particulas.emit(_v.copy(j.pos).setY(j.pos.y + .05), 0x8fb8d8, 2, .8, .3, .4, 1);
        }
        // Regeneración tras 4 s sin daño + latido con vida baja
        if (j.vivo && j.hp < j.hpMax && this.t - j.ultDanio > 4) {
            j.hp = Math.min(j.hpMax, j.hp + 22 * dt);
            this.emit('hp', j.hp);
        }
        j._beat = (j._beat ?? 0) - dt;
        if (j.vivo && j.hp < 30 && j._beat <= 0) { this.sfx.beat(); j._beat = .85; }

        // Cámara: bob, retroceso con recuperación, sacudida, FOV
        const bobVel = j.moviendo ? (j.corriendo ? 13 : j.agachado ? 6.5 : 9.5) * Math.min(1, velH / WALK + .3) : 0;
        j.bob += dt * bobVel;
        const amp = j.moviendo ? (j.corriendo ? .05 : j.agachado ? .018 : .03) * (j.aim ? .35 : 1) : 0;
        j.bobAmp = lerp(j.bobAmp ?? 0, amp, Math.min(1, dt * 8));
        j.bobImpacto = Math.max(0, (j.bobImpacto ?? 0) - dt * 1.2);
        const by = Math.abs(Math.sin(j.bob)) * j.bobAmp - j.bobImpacto;
        const bx = Math.sin(j.bob * .5) * j.bobAmp * .6;
        const rec = this.recoil, recup = Math.min(1, dt * (this.mouseDown ? 3.5 : 9));
        rec.p -= rec.p * recup; rec.y -= rec.y * recup;
        this.trauma = Math.max(0, this.trauma - dt * 1.6);
        const sh = this.trauma * this.trauma, tt = this.t * 26;
        this.camera.position.set(j.pos.x + bx * Math.cos(j.yaw), j.pos.y + j.ojo + by, j.pos.z - bx * Math.sin(j.yaw));
        j.kickPitch = lerp(j.kickPitch, 0, Math.min(1, dt * 12));
        this.camera.rotation.y = j.yaw + rec.y + sh * .035 * Math.sin(tt * 1.1 + 4);
        this.camera.rotation.x = j.pitch + j.kickPitch + rec.p + sh * .035 * Math.sin(tt * 1.3 + 1);
        this.camera.rotation.z = lerp(this.camera.rotation.z, -latVel / WALK * .014, Math.min(1, dt * 6))
            + sh * .04 * Math.sin(tt * .9 + 2);
        const fovObj = j.fovBase + (j.corriendo ? 7 : 0) - vm.aim * 19;
        this.camera.fov = lerp(this.camera.fov, fovObj, Math.min(1, dt * 10));
        this.camera.updateProjectionMatrix();
        this.camera.updateMatrixWorld();

        // Dispersión dinámica (alimenta la mira del HUD)
        this.bloomFuego = Math.max(0, (this.bloomFuego || 0) - dt * .1);
        this.spread = ((j.aim ? .0015 : .011) + Math.min(1, velH / WALK) * (j.aim ? .008 : .028) +
            (j.grounded ? 0 : .045) + this.bloomFuego) * (j.agachado ? .7 : 1);

        vm.tick(dt, { aim: j.aim, sprint: j.corriendo, amp: j.bobAmp * 1.2, ph: j.bob,
            swayX: this.mouseDX, swayY: this.mouseDY, aire: !j.grounded, agachado: j.agachado, vivo: j.vivo });
        this.mouseDX *= .5; this.mouseDY *= .5;
    }

    _bocaMundo() {
        const a = this.vm.aim;
        return new THREE.Vector3(THREE.MathUtils.lerp(.17, 0, a), THREE.MathUtils.lerp(-.14, -.07, a), -.85)
            .applyMatrix4(this.camera.matrixWorld);
    }

    /* Disparo del jugador: hitscan contra muros, suelo y bots (cabeza/cuerpo). */
    disparar() {
        const j = this.jugador, vm = this.vm;
        if (!j.vivo || this.t - j.ultDisparo < j.cadencia) return null;
        if (!vm.puedeDisparar()) {
            if (vm.mag <= 0 && vm.estado === 'idle' && vm.recargar()) this.emit('recarga');
            return null;
        }
        j.ultDisparo = this.t;
        vm.disparo(j.aim);
        this.stats.disparos++;
        this.camera.updateMatrixWorld();
        const o = this.camera.getWorldPosition(new THREE.Vector3());
        const d = this.camera.getWorldDirection(new THREE.Vector3());
        const ang = Math.random() * Math.PI * 2, rad = Math.sqrt(Math.random()) * this.spread;
        const up = _v.set(0, 1, 0).applyQuaternion(this.camera.quaternion);
        const der = _v2.set(1, 0, 0).applyQuaternion(this.camera.quaternion);
        d.addScaledVector(der, Math.cos(ang) * rad).addScaledVector(up, Math.sin(ang) * rad).normalize();
        const { t: tw, box } = this.rayMuros(o, d);
        const tSuelo = d.y < -1e-4 ? -o.y / d.y : Infinity;
        let victima = null, tv = Math.min(tw, tSuelo), cabeza = false;
        for (const b of this.bots) {
            if (!b.vivo) continue;
            const imp = b.impacto(o, d);
            if (imp && imp.t < tv) { tv = imp.t; victima = b; cabeza = imp.cabeza; }
        }
        const fin = o.clone().addScaledVector(d, Math.min(tv, 150));
        this.trazas.disparo(this._bocaMundo(), fin, 0xbfffe0, .01, .06);
        // Retroceso: patrón vertical creciente + deriva lateral en ráfaga
        const kk = (j.aim ? .55 : 1) * (j.agachado ? .75 : 1);
        this._racha = this.t - (this._ultR ?? -9) < .3 ? (this._racha || 0) + 1 : 0; this._ultR = this.t;
        const n = this._racha;
        const kp = (.011 + Math.min(n, 8) * .0015) * kk;
        const ky = (n > 4 ? Math.sin(n * .9) * .006 : (Math.random() - .5) * .004) * kk;
        j.pitch = THREE.MathUtils.clamp(j.pitch + kp * .35, -1.45, 1.45); j.yaw += ky * .35;
        this.recoil.p += kp * .65; this.recoil.y += ky * .65;
        this.bloomFuego = Math.min(.045, (this.bloomFuego || 0) + .006);
        this.sacudir(.035);
        this.sfx.shoot();
        if (victima) {
            const dmg = Math.round(DANO_CUERPO * (cabeza ? MULT_CABEZA : 1));
            const mato = victima.recibir(dmg, d, true, cabeza);
            this.stats.aciertos++; if (cabeza) this.stats.cabezas++;
            if (mato) { this.stats.bajas++; this.sfx.kill(); }
            if (cabeza) this.sfx.head(); else this.sfx.hit();
            this.particulas.emit(fin, cabeza ? 0xffe066 : 0xff8a5c, cabeza ? 18 : 10, 3, .35, 1.2);
            this.emit('acierto', { b: victima, cabeza, mato, dmg, pos: fin });
        } else if (tv < Infinity) {
            const nrm = tSuelo <= tw ? _v3.set(0, 1, 0) : (box ? normalCaja(box, fin, _v3) : null);
            if (nrm) this.marcas.poner(fin, nrm);
            this.particulas.emit(fin, 0x9fd3ff, 8, 2.4, .3, 1);
            if (Math.random() < .35) this.sfx.ricochet();
        }
        return { victima, fin, cabeza };
    }

    /* ----- Loop ----- */
    iniciar(fn) {
        this._loopFn = fn;
        if (this._raf) return;
        const loop = () => {
            this._raf = requestAnimationFrame(loop);
            const dt = Math.min(this.clock.getDelta(), .05);
            if (dt > 0) this.fps = this.fps ? this.fps * .92 + (1 / dt) * .08 : 1 / dt;
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
            this.marcas.tick(dt);
            this.render();
        };
        loop();
    }
    render() {
        const r = this.renderer;
        if (+this.ajustes.calidad < .7) r.render(this.scene, this.camera);
        else this.composer.render();
        if (this.activo) {
            r.autoClear = false; r.clearDepth();
            r.render(this.vm.scene, this.vm.cam);
            r.autoClear = true;
        }
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
