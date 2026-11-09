/* Don Datico — personaje humanoide (GLB dondaticolite) con animación
 * procedural sobre el rig: caminar/correr, salto, apuntar, retroceso
 * de disparo, reacción al impacto, muerte y respiración en idle. */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import { sprite, raySegment } from './engine.js';

/* El GLB mira +x; nuestro yaw=0 mira -z → +PI/2 alinea. */
const MODEL_YAW = Math.PI / 2;
const RIG_BONES = ['Hip', 'Pelvis', 'Spine02', 'Head', 'L_Thigh', 'R_Thigh', 'L_Calf', 'R_Calf',
    'L_Foot', 'R_Foot',
    'L_Upperarm', 'R_Upperarm', 'L_Forearm', 'R_Forearm', 'R_Hand', 'L_Hand'];

let glbScene = null;
export function cargarDatico(url) {
    return new Promise((res, rej) => {
        if (glbScene) return res(glbScene);
        new GLTFLoader().load(url, g => { glbScene = g.scene; res(glbScene); }, undefined, rej);
    });
}

const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion();
const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3();
const _q2v = new THREE.Vector3();
const _blanco = new THREE.Color(0xffffff);
const lerp = THREE.MathUtils.lerp, clamp = THREE.MathUtils.clamp;

export class Datico {
    /** @param {object} o {nombre, color, escala, escena} */
    constructor(o = {}) {
        this.nombre = o.nombre || 'Datico';
        this.color = o.color ?? 0xa05cff;
        this.group = new THREE.Group();
        // group (yaw) > tilt (inclinaciones del cuerpo: x=pitch, z=roll) > wrap > model
        // En el marco de tilt el frente es -z y la derecha +x: tilt.x>0 echa
        // el cuerpo hacia atrás, tilt.z>0 lo inclina a la izquierda.
        this.tilt = new THREE.Group();
        this.group.add(this.tilt);
        this.wrap = new THREE.Group();          // gira el GLB al frente
        this.wrap.rotation.y = MODEL_YAW;
        this.tilt.add(this.wrap);
        this.pos = this.group.position;
        this.yaw = 0;
        this.vivo = true;
        this.hp = o.hp ?? 100; this.hpMax = this.hp;
        this.escala = o.escala ?? 1.15;
        this.hMod = this.escala * .998;           // altura real del GLB
        // Estado de animación que alimenta driveRig
        this.anim = { amp: 0, run: 0, ph: Math.random() * 6, aire: 0, aim: 0, retro: 0, hit: 0,
                      hitDir: 1, hitSide: 0, dead: 0, pitch: 0, idleT: Math.random() * 10,
                      flash: 0, spawn: 1, headshot: false,
                      dirF: 1, dirR: 0, vel: 0,          // locomoción direccional
                      alerta: 0, scan: 0, yawJerk: 0,   // reacciones
                      wobble: 0 };
        this.knock = new THREE.Vector3();        // empujón pendiente (mundo)
        this.model = SkeletonUtils.clone(glbScene);
        this.model.scale.setScalar(this.escala);
        this.mats = [];
        this.model.traverse(c => {
            if (c.isMesh || c.isSkinnedMesh) {
                c.castShadow = true; c.frustumCulled = false;
                c.userData.keepGeo = true;          // geometría compartida del GLB
                c.material = c.material.clone();   // para fundido individual
                c.material.transparent = true;
                c.userData.eBase = c.material.emissive.clone();
                c.userData.eInt = c.material.emissiveIntensity ?? 1;
                this.mats.push(c.material);
                c.material.userData.eBase = c.userData.eBase;
                c.material.userData.eInt = c.userData.eInt;
            }
        });
        this.wrap.add(this.model);
        this._rig();
        this._arma();
        if (o.etiqueta !== false) {
            this.label = sprite(this.nombre, o.labelColor || '#c98bff', 30);
            this.label.position.y = this.hMod * 1.55;
            this.group.add(this.label);
        }
        // Halo bajo los pies
        this.halo = new THREE.Mesh(new THREE.RingGeometry(.42, .6, 28),
            new THREE.MeshBasicMaterial({ color: this.color, transparent: true, opacity: .45, side: THREE.DoubleSide }));
        this.halo.rotation.x = -Math.PI / 2; this.halo.position.y = .03;
        this.group.add(this.halo);
        // Barra de vida (sprite escalable)
        this.hpBar = new THREE.Group();
        const bg = new THREE.Mesh(new THREE.PlaneGeometry(1, .09), new THREE.MeshBasicMaterial({ color: 0x0b1420, transparent: true, opacity: .75, depthWrite: false }));
        this.hpFill = new THREE.Mesh(new THREE.PlaneGeometry(1, .07), new THREE.MeshBasicMaterial({ color: 0x46d98b, depthWrite: false }));
        this.hpFill.position.z = .001;
        this.hpBar.add(bg, this.hpFill); this.hpBar.position.y = this.hMod * 1.4;
        this.group.add(this.hpBar);
    }

    /* Mide ejes laterales por hueso desde el bind (en espacio del padre) */
    _rig() {
        const m = this.model; m.updateMatrixWorld(true);
        const bones = {}; RIG_BONES.forEach(n => bones[n] = m.getObjectByName(n));
        const wq = new THREE.Quaternion();
        const aLocal = (b, w) => { b.parent.getWorldQuaternion(wq); return w.clone().applyQuaternion(wq.invert()).normalize(); };
        const pHip = bones.Hip ? bones.Hip.getWorldPosition(new THREE.Vector3()) : new THREE.Vector3();
        const pHead = bones.Head ? bones.Head.getWorldPosition(new THREE.Vector3()) : pHip.clone().setX(pHip.x + 1);
        const frente = pHead.sub(pHip).setY(0).normalize();
        if (frente.lengthSq() < .1) frente.set(1, 0, 0);
        const up = new THREE.Vector3(0, 1, 0);
        const lado = new THREE.Vector3().crossVectors(frente, up).normalize();
        this.rig = { bones, frente, lado, base: {}, lat: {}, fwd: {}, upv: {}, aLocal };
        for (const n of RIG_BONES) {
            const b = bones[n]; if (!b) continue;
            this.rig.base[n] = b.quaternion.clone();
            this.rig.lat[n] = aLocal(b, lado);      // eje de balanceo (swing adelante/atrás)
            this.rig.fwd[n] = aLocal(b, frente);    // eje de roll lateral
            this.rig.upv[n] = aLocal(b, up);        // eje de giro (yaw)
        }
    }
    /* Blaster en la mano derecha, apuntando al frente del modelo */
    _arma() {
        const hand = this.rig.bones.R_Hand; if (!hand) return;
        const g = new THREE.Group();
        const dark = new THREE.MeshStandardMaterial({ color: 0x1a2430, roughness: .35, metalness: .75 });
        const body = new THREE.Mesh(new THREE.BoxGeometry(.09, .13, .4), dark);
        const barrel = new THREE.Mesh(new THREE.CylinderGeometry(.03, .03, .3, 10), dark);
        barrel.rotation.x = Math.PI / 2; barrel.position.z = .28;
        const tip = new THREE.Mesh(new THREE.CylinderGeometry(.042, .042, .05, 10), new THREE.MeshBasicMaterial({ color: this.color }));
        tip.rotation.x = Math.PI / 2; tip.position.z = .44;
        // Orbe de carga: crece mientras el bot telegrafía su disparo
        this.orbe = new THREE.Mesh(new THREE.SphereGeometry(.075, 10, 8),
            new THREE.MeshBasicMaterial({ color: this.color, transparent: true, opacity: 0,
                blending: THREE.AdditiveBlending, depthWrite: false }));
        this.orbe.position.z = .5; g.add(this.orbe);
        const grip = new THREE.Mesh(new THREE.BoxGeometry(.08, .16, .09), dark);
        grip.position.set(0, -.11, -.1); grip.rotation.x = .35;
        this.boca = new THREE.Object3D(); this.boca.position.z = .5;
        g.add(body, barrel, tip, grip, this.boca);
        const dirLocal = this.rig.aLocal(hand, this.rig.frente);
        g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), dirLocal);
        g.position.copy(dirLocal).multiplyScalar(.14);
        hand.add(g); this.gun = g; this.gunTip = tip;
    }
    posBoca(out) { return this.boca ? this.boca.getWorldPosition(out) : out.copy(this.pos).setY(this.pos.y + this.hMod * .85); }
    posPecho(out) { return out.copy(this.pos).setY(this.pos.y + this.hMod * .62); }
    posOjos(out) { return out.copy(this.pos).setY(this.pos.y + this.hMod * .88); }
    posCabeza(out) { return out.copy(this.pos).setY(this.pos.y + this.hMod * .87); }

    /* k 0..1: brillo del orbe de carga (telegrafía) */
    cargando(k) {
        if (!this.orbe) return;
        this.orbe.material.opacity = Math.min(1, k);
        this.orbe.scale.setScalar(.3 + k * 2.2);
        this.gunTip.material.color.setHex(k > .5 ? 0xffffff : this.color);
    }

    /* Impacto de hitscan: esfera de cabeza + cápsula corporal.
     * Devuelve {t, cabeza} del impacto más cercano o null. */
    impacto(o, d) {
        const hp = this.hMod;
        // Cabeza: esfera (el casco es grande, perdonamos algo)
        const c = _v.set(this.pos.x, this.pos.y + hp * .87, this.pos.z);
        const oc = _q2v.subVectors(c, o);
        const tca = oc.dot(d);
        let mejor = null;
        if (tca > 0) {
            const d2 = oc.lengthSq() - tca * tca, r2 = hp * .2 * (hp * .2);
            if (d2 < r2) mejor = { t: tca - Math.sqrt(r2 - d2), cabeza: true };
        }
        // Cuerpo: cápsula de tobillos a cuello
        const a = _v2.set(this.pos.x, this.pos.y + .08, this.pos.z);
        const b2 = _v3.set(this.pos.x, this.pos.y + hp * .8, this.pos.z);
        const { t, d2 } = raySegment(o, d, a, b2);
        const rc = .36;
        if (d2 < rc * rc && t > 0 && (!mejor || t < mejor.t)) mejor = { t, cabeza: false };
        return mejor;
    }

    _set(n, angLat = 0, angFwd = 0, angUp = 0) {
        const b = this.rig.bones[n]; if (!b) return;
        b.quaternion.copy(this.rig.base[n]);
        if (angUp) { _q.setFromAxisAngle(this.rig.upv[n], angUp); b.quaternion.premultiply(_q); }
        if (angFwd) { _q.setFromAxisAngle(this.rig.fwd[n], angFwd); b.quaternion.premultiply(_q); }
        if (angLat) { _q.setFromAxisAngle(this.rig.lat[n], angLat); b.quaternion.premultiply(_q); }
    }

    /** Actualiza el rig.
     * s: {moviendo, corriendo, aire, aim(bool), pitch,
     *     vel (m/s real), dirF (-1..1 adelante/atrás), dirR (-1..1 derecha/izq),
     *     scan (bool: barrer con la cabeza), alerta (bool: acaba de avistar)} */
    animar(dt, s = {}) {
        const a = this.anim;
        const k = x => Math.min(1, dt * x);
        a.amp = lerp(a.amp, (this.vivo && s.moviendo) ? 1 : 0, k(9));
        a.run = lerp(a.run, (this.vivo && s.corriendo) ? 1 : 0, k(6));
        a.aire = lerp(a.aire, (this.vivo && s.aire) ? 1 : 0, k(10));
        a.aim = lerp(a.aim, (this.vivo && s.aim) ? 1 : 0, k(7));
        a.pitch = lerp(a.pitch, clamp(s.pitch ?? 0, -.6, .6), k(6));
        a.scan = lerp(a.scan, (this.vivo && s.scan) ? 1 : 0, k(4));
        if (s.moviendo) {
            a.dirF = lerp(a.dirF, clamp(s.dirF ?? 1, -1, 1), k(10));
            a.dirR = lerp(a.dirR, clamp(s.dirR ?? 0, -1, 1), k(10));
        }
        a.vel = lerp(a.vel, s.vel ?? (s.moviendo ? 3 : 0), k(8));
        a.retro = Math.max(0, a.retro - dt * 9);
        a.hit = Math.max(0, a.hit - dt * 4);
        a.alerta = Math.max(0, a.alerta - dt * 2.2);
        a.wobble = Math.max(0, a.wobble - dt * 2.5);
        a.idleT += dt;
        // Fase ligada a la velocidad real: ~1.45 m por ciclo (2 pasos) → sin patinar
        a.ph += dt * (a.amp > .15 ? Math.max(1.6, a.vel) * 4.4 : 1.8);
        const s1 = Math.sin(a.ph), c1 = Math.cos(a.ph);
        const A = a.amp * (1 - a.aire), R = a.run;
        const idle = 1 - a.amp;
        const F = a.dirF, Lt = a.dirR;                       // componentes de dirección
        const aF = Math.abs(F), aL = Math.abs(Lt);
        const fw = F >= 0 ? 1 : -1;                            // hacia atrás invierte la zancada

        if (!this.vivo) { this._muerte(dt); return; }

        // ——— Piernas ———
        // Adelante/atrás: balanceo (eje lat) + rodilla que flexiona en la fase de vuelo.
        // Lateral: las piernas se abren/cierran (eje fwd = roll) → paso de lado.
        const zan = (.48 + .27 * R) * aF;
        const rodL = Math.max(0, c1) * (.55 + .3 * R) * aF + Math.max(0, s1) * .3 * aL;
        const rodR = Math.max(0, -c1) * (.55 + .3 * R) * aF + Math.max(0, -s1) * .3 * aL;
        const lean = -Lt * .34 * s1 * A;                       // ambas piernas se inclinan al lado
        const abre = aL * .16 * A;                             // separación de piernas al desplazarse de lado
        this._set('L_Thigh', zan * s1 * fw * A + .55 * a.aire, lean + abre);
        this._set('R_Thigh', -zan * s1 * fw * A + .45 * a.aire, lean - abre);
        this._set('L_Calf', -rodL * A - .9 * a.aire - .06 * idle * (1 + Math.sin(a.idleT * .7)));
        this._set('R_Calf', -rodR * A - .8 * a.aire - .06 * idle * (1 - Math.sin(a.idleT * .7)));
        this._set('L_Foot', (-zan * s1 * fw * .8 - .18) * A + .5 * a.aire, -lean * .6);
        this._set('R_Foot', (zan * s1 * fw * .8 - .18) * A + .45 * a.aire, -lean * .6);

        // ——— Brazos ———
        const brazo = (.3 + .22 * R) * s1 * A * aF;
        const al = a.alerta, alB = al * al;                    // sobresalto al avistar
        const aimR = a.aim * (-1.35 + a.pitch * .9) * (1 + .18 * alB);
        const retro = a.retro * .28;
        // Sway del arma al moverse apuntando: no queda congelado
        const swayA = a.aim * A * .05, swayF = a.aim * A * .035;
        const brL = -brazo * (1 - a.aim * .5) + a.aim * -.55 - .3 * a.aire - .4 * alB;
        this._set('R_Upperarm',
            brazo * (1 - a.aim) + aimR - retro - .25 * a.aire + swayA * Math.sin(a.ph * 2) + .05 * idle * Math.sin(a.idleT * 1.1),
            a.aim * -.25 + swayA * .7 * c1 + .02 * aL * A);
        this._set('R_Forearm', .18 * s1 * A * aF * (1 - a.aim) + a.aim * -.15 - retro * .6 + swayF * c1);
        this._set('L_Upperarm', brL + .05 * idle * Math.sin(a.idleT * 1.1 + 1), a.aim * .35 + .18 * aL * A);
        this._set('L_Forearm', -.18 * s1 * A * aF + a.aim * -.9 - .3 * alB);

        // ——— Tronco ———
        const flinch = a.hit * a.hit;
        const peso = .035 * Math.sin(a.idleT * .7) * idle;      // cambio de peso de pie
        this._set('Pelvis', -.1 * R * A * aF, .05 * s1 * A * aF + peso);
        this._set('Spine02',
            .05 * Math.sin(a.idleT * 1.6) * idle - .15 * R * A * aF - .35 * flinch + a.pitch * .35 * a.aim - .14 * alB,
            .12 * flinch * a.hitSide - peso * .8 + .06 * s1 * A * aL,
            a.aim * .25 + .12 * Math.sin(a.idleT * 2.1) * a.scan);
        // Cabeza: mirada ociosa en idle; barrido en 'buscar'; brinco en alerta
        this._set('Head',
            .04 * Math.sin(a.idleT * .9 + 1) * idle + a.pitch * .4 * a.aim - .2 * flinch - .22 * alB + .05 * a.scan,
            .05 * Math.sin(a.idleT * 2.1 + .5) * a.scan,
            .22 * Math.sin(a.idleT * .45) * idle * (1 - a.scan) + .75 * Math.sin(a.idleT * 2.1) * a.scan);

        // ——— Cuerpo completo ———
        // Bob de zancada; inclinación hacia donde se mueve; tambaleo al recibir daño
        this.model.position.y = Math.abs(s1) * .055 * A - .03 * alB;
        const wob = a.wobble * a.wobble;
        this.tilt.rotation.x = -.09 * R * A * aF * fw - .05 * aF * A * fw * (1 - R)   // adelante al avanzar
            + .12 * alB                                                              // atrás al sobresaltarse
            + .14 * flinch * a.hitDir + .05 * wob * Math.sin(a.idleT * 18);
        this.tilt.rotation.z = -Lt * .085 * A                                        // hacia el lado del strafe
            + Math.sin(a.ph * .5) * .03 * A * aF
            + .1 * flinch * a.hitSide + .05 * wob * Math.cos(a.idleT * 15);
        // Flash al recibir daño + materialización de spawn
        if (a.flash > 0) {
            a.flash = Math.max(0, a.flash - dt * 5);
            for (const m of this.mats) {
                m.emissive.copy(m.userData.eBase).lerp(_blanco, a.flash);
                m.emissiveIntensity = m.userData.eInt + a.flash * 3;
            }
        }
        if (a.spawn < 1) {
            a.spawn = Math.min(1, a.spawn + dt * 1.8);
            const e2 = 1 - Math.pow(1 - a.spawn, 3);
            this.model.scale.setScalar(this.escala * (.3 + .7 * e2));
            for (const m of this.mats) m.opacity = e2;
        }
        // Barra de vida
        const f = this.hp / this.hpMax;
        this.hpFill.scale.x = Math.max(.001, f);
        this.hpFill.position.x = -(1 - f) / 2;
        this.hpFill.material.color.setHex(f > .5 ? 0x46d98b : f > .25 ? 0xe8a83c : 0xe84c3c);
        this.hpBar.visible = f < 1;
    }

    _muerte(dt) {
        const a = this.anim;
        a.dead = Math.min(1, a.dead + dt * (a.headshot ? 2.6 : 1.7));
        const ss = (x, lo, hi) => { const t = clamp((x - lo) / (hi - lo), 0, 1); return t * t * (3 - 2 * t); };
        // Fase 1: desplome — rodillas ceden, cuerpo baja. Fase 2: cae hacia
        // atrás/adelante girando desde los pies con una ligera torsión.
        const b = ss(a.dead, 0, a.headshot ? .3 : .42);
        const e = ss(a.dead, a.headshot ? .12 : .28, 1);
        const ease = 1 - Math.pow(1 - e, 2.2);
        const rebote = a.dead > .92 ? Math.sin((a.dead - .92) / .08 * Math.PI) * .04 : 0;
        this.tilt.rotation.x = a.hitDir * ease * (Math.PI / 2 * .96) - rebote * a.hitDir;
        this.tilt.rotation.z = a.hitSide * ease * (a.headshot ? .45 : .22) + a.hitDir * ease * .08;
        this.model.position.y = -.36 * b - .05 * ease;
        // Piernas: se doblan al ceder y quedan laxas al caer
        this._set('L_Thigh', .55 * b - .2 * ease, .12 * ease);
        this._set('R_Thigh', .45 * b - .05 * ease, -.1 * ease);
        this._set('L_Calf', -1.2 * b + .5 * ease);
        this._set('R_Calf', -1.05 * b + .55 * ease);
        this._set('L_Foot', -.3 * b); this._set('R_Foot', -.25 * b);
        // Brazos: sueltan el arma y se abren
        this._set('L_Upperarm', -.4 * b - .9 * ease, .5 * ease + .2 * b);
        this._set('R_Upperarm', -.5 * b - 1.0 * ease, -.6 * ease - .2 * b);
        this._set('L_Forearm', -.6 * b * (1 - ease)); this._set('R_Forearm', -.5 * b * (1 - ease));
        this._set('Pelvis', .2 * b, 0);
        this._set('Spine02', (a.headshot ? -.25 : .3) * b - .15 * ease, .1 * a.hitSide * ease);
        this._set('Head', (a.headshot ? -.7 : .35) * b + .25 * ease, .2 * a.hitSide * ease, .3 * a.hitSide * ease);
        this.halo.material.opacity = .45 * (1 - e);
        this.hpBar.visible = false;
        if (this.label) this.label.material.opacity = 1 - e;
        // Hundirse y desvanecer tras 2 s
        a.sink = (a.sink ?? -2) + dt;
        if (a.sink > 0) {
            this.group.position.y -= dt * .6;
            const op = Math.max(0, 1 - a.sink / 1.4);
            this.model.traverse(c => { if (c.material) c.material.opacity = op; });
            if (op <= 0) this.terminado = true;
        }
    }

    /* Impacto recibido: dmg, dirección del disparo (para el flinch) */
    recibir(dmg, dir, deJugador = false, cabeza = false) {
        if (!this.vivo) return false;
        this.hp = Math.max(0, this.hp - dmg);
        const a = this.anim;
        a.hit = 1;
        a.flash = 1;
        a.wobble = Math.min(1, a.wobble + .6);
        // Descomponer el disparo en el marco del bot: ¿de frente o por la
        // espalda? (hitDir: 1 = cae hacia atrás) ¿y de qué lado? (hitSide)
        const fwd = _v.set(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
        const right = _v2.set(Math.cos(this.yaw), 0, -Math.sin(this.yaw));
        const dF = fwd.dot(dir), dR = right.dot(dir);
        a.hitDir = dF > 0 ? -1 : 1;
        a.hitSide = clamp(-dR * 1.4, -1, 1);
        // Empujón en la dirección del disparo + sacudida de yaw
        this.knock.set(dir.x, 0, dir.z).normalize().multiplyScalar(cabeza ? 2.4 : 1.3);
        a.yawJerk = (Math.random() - .5) * (cabeza ? .9 : .45);
        if (this.hp <= 0) {
            this.vivo = false; a.dead = 0;
            a.headshot = cabeza;
            this.knock.multiplyScalar(1.6);
            if (this.orbe) this.orbe.material.opacity = 0;
            return true;
        }
        return false;
    }
    aparecer() { this.anim.spawn = 0; }
    /* Pequeño sobresalto al avistar al jugador (cabeza/tronco/arma) */
    sobresalto() { this.anim.alerta = 1; }
    dispararFX() { this.anim.retro = 1; this.cargando(0); }
    mirarHacia(x, z) { this.yaw = Math.atan2(-(x - this.pos.x), -(z - this.pos.z)); }
    aplicarYaw(dt) {
        const a = this.anim;
        a.yawJerk *= Math.max(0, 1 - dt * 7);
        let dy = this.yaw + a.yawJerk - this.group.rotation.y;
        while (dy > Math.PI) dy -= 2 * Math.PI;
        while (dy < -Math.PI) dy += 2 * Math.PI;
        // Giro más vivo cuando está alerta/en combate, más calmo al patrullar
        const vel = this.vivo ? 10 + 8 * a.aim : 4;
        this.group.rotation.y += dy * Math.min(1, dt * vel);
    }
    /* Consume el empujón pendiente desplazando `pos` (quien llama colisiona) */
    aplicarKnock(dt) {
        if (this.knock.lengthSq() < 1e-4) { this.knock.set(0, 0, 0); return false; }
        this.pos.addScaledVector(this.knock, dt);
        this.knock.multiplyScalar(Math.max(0, 1 - dt * 9));
        return true;
    }
}
