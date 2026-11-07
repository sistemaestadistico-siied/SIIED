/* Don Datico — personaje humanoide (GLB dondaticolite) con animación
 * procedural sobre el rig: caminar/correr, salto, apuntar, retroceso
 * de disparo, reacción al impacto, muerte y respiración en idle. */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import { sprite } from './engine.js';

/* El GLB mira +x; nuestro yaw=0 mira -z → +PI/2 alinea. */
const MODEL_YAW = Math.PI / 2;
const RIG_BONES = ['Hip', 'Pelvis', 'Spine02', 'Head', 'L_Thigh', 'R_Thigh', 'L_Calf', 'R_Calf',
    'L_Upperarm', 'R_Upperarm', 'L_Forearm', 'R_Forearm', 'R_Hand', 'L_Hand'];

let glbScene = null;
export function cargarDatico(url) {
    return new Promise((res, rej) => {
        if (glbScene) return res(glbScene);
        new GLTFLoader().load(url, g => { glbScene = g.scene; res(glbScene); }, undefined, rej);
    });
}

const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _v = new THREE.Vector3();
const lerp = THREE.MathUtils.lerp, clamp = THREE.MathUtils.clamp;

export class Datico {
    /** @param {object} o {nombre, color, escala, escena} */
    constructor(o = {}) {
        this.nombre = o.nombre || 'Datico';
        this.color = o.color ?? 0xa05cff;
        this.group = new THREE.Group();
        this.wrap = new THREE.Group();          // gira el GLB al frente
        this.wrap.rotation.y = MODEL_YAW;
        this.group.add(this.wrap);
        this.pos = this.group.position;
        this.yaw = 0;
        this.vivo = true;
        this.hp = o.hp ?? 100; this.hpMax = this.hp;
        // Estado de animación que alimenta driveRig
        this.anim = { amp: 0, run: 0, ph: Math.random() * 6, aire: 0, aim: 0, retro: 0, hit: 0,
                      hitDir: 1, dead: 0, pitch: 0, pitchObj: 0, idleT: Math.random() * 10, lookYaw: 0 };
        this.model = SkeletonUtils.clone(glbScene);
        this.model.scale.setScalar(o.escala ?? 1.15);
        this.model.traverse(c => {
            if (c.isMesh || c.isSkinnedMesh) {
                c.castShadow = true; c.frustumCulled = false;
                c.userData.keepGeo = true;          // geometría compartida del GLB
                c.material = c.material.clone();   // para fundido individual
                c.material.transparent = true;
            }
        });
        this.wrap.add(this.model);
        this._rig();
        this._arma();
        if (o.etiqueta !== false) {
            this.label = sprite(this.nombre, o.labelColor || '#c98bff', 30);
            this.label.position.y = 2.35;
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
        this.hpBar.add(bg, this.hpFill); this.hpBar.position.y = 2.1;
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
        const grip = new THREE.Mesh(new THREE.BoxGeometry(.08, .16, .09), dark);
        grip.position.set(0, -.11, -.1); grip.rotation.x = .35;
        this.boca = new THREE.Object3D(); this.boca.position.z = .5;
        g.add(body, barrel, tip, grip, this.boca);
        const dirLocal = this.rig.aLocal(hand, this.rig.frente);
        g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), dirLocal);
        g.position.copy(dirLocal).multiplyScalar(.14);
        hand.add(g); this.gun = g; this.gunTip = tip;
    }
    posBoca(out) { return this.boca ? this.boca.getWorldPosition(out) : out.copy(this.pos).setY(this.pos.y + 1.4); }
    posPecho(out) { return out.copy(this.pos).setY(this.pos.y + 1.15); }
    posOjos(out) { return out.copy(this.pos).setY(this.pos.y + 1.55); }

    _set(n, angLat = 0, angFwd = 0, angUp = 0) {
        const b = this.rig.bones[n]; if (!b) return;
        b.quaternion.copy(this.rig.base[n]);
        if (angUp) { _q.setFromAxisAngle(this.rig.upv[n], angUp); b.quaternion.premultiply(_q); }
        if (angFwd) { _q.setFromAxisAngle(this.rig.fwd[n], angFwd); b.quaternion.premultiply(_q); }
        if (angLat) { _q.setFromAxisAngle(this.rig.lat[n], angLat); b.quaternion.premultiply(_q); }
    }

    /** Actualiza el rig. estado: {moviendo, corriendo, aire, aim(bool), pitch} */
    animar(dt, s = {}) {
        const a = this.anim;
        a.amp = lerp(a.amp, (this.vivo && s.moviendo) ? 1 : 0, Math.min(1, dt * 8));
        a.run = lerp(a.run, (this.vivo && s.corriendo) ? 1 : 0, Math.min(1, dt * 6));
        a.aire = lerp(a.aire, (this.vivo && s.aire) ? 1 : 0, Math.min(1, dt * 10));
        a.aim = lerp(a.aim, (this.vivo && s.aim) ? 1 : 0, Math.min(1, dt * 7));
        a.pitch = lerp(a.pitch, clamp(s.pitch ?? 0, -.6, .6), Math.min(1, dt * 6));
        a.retro = Math.max(0, a.retro - dt * 9);
        a.hit = Math.max(0, a.hit - dt * 4);
        a.idleT += dt;
        a.ph += dt * (a.amp > .3 ? 8.5 + a.run * 5 : 2.2);
        const s1 = Math.sin(a.ph), A = a.amp * (1 - a.aire), R = a.run;
        const idle = 1 - a.amp;

        if (!this.vivo) { this._muerte(dt); return; }

        // Piernas: zancada + flexión de rodilla; en el aire se recogen
        const zan = .5 + .25 * R;
        this._set('L_Thigh', zan * s1 * A + .55 * a.aire);
        this._set('R_Thigh', -zan * s1 * A + .45 * a.aire);
        this._set('L_Calf', Math.max(0, -.6 * Math.sin(a.ph - 1)) * A - .9 * a.aire);
        this._set('R_Calf', Math.max(0, -.6 * Math.sin(a.ph - 1 + Math.PI)) * A - .8 * a.aire);

        // Brazos: contrafase al caminar; al apuntar el derecho sube al frente
        const brazo = (.32 + .2 * R) * s1 * A;
        const aimR = a.aim * (-1.35 + a.pitch * .9);          // levantar brazo derecho
        const retro = a.retro * .28;
        this._set('R_Upperarm', brazo * (1 - a.aim) + aimR - retro - .25 * a.aire, a.aim * -.25);
        this._set('R_Forearm', .18 * s1 * A * (1 - a.aim) + a.aim * -.15 - retro * .6);
        this._set('L_Upperarm', -brazo * (1 - a.aim * .5) + a.aim * -.55 - .3 * a.aire, a.aim * .35);
        this._set('L_Forearm', -.18 * s1 * A + a.aim * -.9);

        // Tronco: roll de pelvis al caminar, inclinación al correr,
        // respiración en idle, flinch al recibir impacto
        const flinch = a.hit * a.hit;
        this._set('Pelvis', -.1 * R * A, .05 * s1 * A);
        this._set('Spine02',
            .05 * Math.sin(a.idleT * 1.6) * idle - .15 * R * A - .35 * flinch + a.pitch * .35 * a.aim,
            .12 * flinch * a.hitDir,
            a.aim * .25);
        // Cabeza: mirada ociosa en idle; compensa el pitch al apuntar
        this._set('Head',
            .04 * Math.sin(a.idleT * .9 + 1) * idle + a.pitch * .4 * a.aim - .2 * flinch,
            0,
            .22 * Math.sin(a.idleT * .45) * idle);

        // Cuerpo completo: bob de zancada (solo con pies en el suelo)
        this.model.position.y = Math.abs(Math.sin(a.ph)) * .06 * A;
        this.model.rotation.z = 0;
        this.model.rotation.x = -.06 * R * A;   // ligera inclinación al correr
        // Barra de vida
        const f = this.hp / this.hpMax;
        this.hpFill.scale.x = Math.max(.001, f);
        this.hpFill.position.x = -(1 - f) / 2;
        this.hpFill.material.color.setHex(f > .5 ? 0x46d98b : f > .25 ? 0xe8a83c : 0xe84c3c);
        this.hpBar.visible = f < 1;
    }

    _muerte(dt) {
        const a = this.anim;
        a.dead = Math.min(1, a.dead + dt * 2.2);
        const e = 1 - Math.pow(1 - a.dead, 3);              // ease-out
        this.model.rotation.x = -e * Math.PI / 2 * a.hitDir; // cae hacia atrás/adelante
        this.model.position.y = -e * .2;
        // Miembros sueltos
        this._set('L_Thigh', .2 * e); this._set('R_Thigh', -.15 * e);
        this._set('L_Upperarm', -1.1 * e, .4 * e); this._set('R_Upperarm', -1.3 * e, -.5 * e);
        this._set('Head', .3 * e, .15 * e);
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
    recibir(dmg, dir, deJugador = false) {
        if (!this.vivo) return false;
        this.hp = Math.max(0, this.hp - dmg);
        this.anim.hit = 1;
        // ¿de frente o por la espalda? → cae hacia el lado contrario
        const fwd = _v.set(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
        this.anim.hitDir = fwd.dot(dir) > 0 ? -1 : 1;
        if (this.hp <= 0) { this.vivo = false; this.anim.dead = 0; return true; }
        return false;
    }
    dispararFX() { this.anim.retro = 1; }
    mirarHacia(x, z) { this.yaw = Math.atan2(-(x - this.pos.x), -(z - this.pos.z)); }
    aplicarYaw(dt) {
        let dy = this.yaw - this.group.rotation.y;
        while (dy > Math.PI) dy -= 2 * Math.PI;
        while (dy < -Math.PI) dy += 2 * Math.PI;
        this.group.rotation.y += dy * Math.min(1, dt * 14);
    }
}
