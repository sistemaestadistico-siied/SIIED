/* Bot enemigo: Don Datico con IA local.
 * Estados: 'patrulla' (waypoints) → 'alerta' (vio al jugador, pausa
 * breve antes de disparar) → 'combate' (strafe + fuego) → 'buscar'
 * (última posición conocida) → 'patrulla'.
 * La puntería empeora con distancia, movimiento del jugador y si el
 * jugador corre/agacha ritmo — da tiempo justo de reacción. */
import * as THREE from 'three';
import { Datico } from './datico.js';

const _v = new THREE.Vector3(), _o = new THREE.Vector3(), _d = new THREE.Vector3();

const DEFS = {
    vision: 26, oidoDisparo: 24, vel: 4.2, run: 1.0,
    dano: 12, cadenciaMin: .7, cadenciaMax: 1.5, precision: .07,
    reaccion: [.55, 1.1],                // s de pausa al avistar
    alcanceDisparo: 40,
};

let _rid = 0;

export class Bot extends Datico {
    /** o: {nombre,color,scene,engine,pos,waypoints,cfg,slot} */
    constructor(o) {
        super(o);
        this.engine = o.engine;
        this.cfg = Object.assign({}, DEFS, o.cfg || {});
        this.wp = null;
        this.estado = 'patrulla';
        this.lastSeen = null;             // Vector3 última posición vista
        this.vioT = 0;                    // tiempo en combate (primer disparo tardío)
        this.perdioT = 0;                 // tiempo sin ver (buscar)
        this.strafe = Math.random() < .5 ? 1 : -1;
        this.strafeT = 0;
        this.nextShot = 0;
        this.stuck = 0;
        this.muertoT = 0;
        this.pos.set(o.pos[0], o.pos[1], o.pos[2]);
        this.group.position.copy(this.pos);
        this.yaw = Math.random() * Math.PI * 2;
        this.id = 'bot-' + (_rid++);
        this.marca = null;
    }

    /* ——— Sensores ——— */
    _veJugador() {
        const e = this.engine, j = e.jugador;
        if (!j.vivo) return false;
        const d = _v.set(j.pos.x - this.pos.x, 0, j.pos.z - this.pos.z).length();
        if (d > this.cfg.vision) return false;
        // Cono de visión ~200° salvo muy cerca
        if (d > 4) {
            const fwd = _o.set(-Math.sin(this.group.rotation.y), 0, -Math.cos(this.group.rotation.y));
            const dir = _d.set(j.pos.x - this.pos.x, 0, j.pos.z - this.pos.z).normalize();
            if (fwd.dot(dir) < -.25) return false;
        }
        const ojo = this.posOjos(_o);
        const pecho = _d.copy(j.pos); pecho.y += 1.2;
        return e.los(ojo, pecho);
    }
    _oyeDisparo() {
        const e = this.engine;
        if (!e.jugador.vivo || e.t - e.jugador.ultDisparo > .05) return false;
        return _v.set(e.jugador.pos.x - this.pos.x, 0, e.jugador.pos.z - this.pos.z).length() < this.cfg.oidoDisparo;
    }

    /* ——— Movimiento ——— */
    _avanzar(dx, dz, dt, vel) {
        const l = Math.hypot(dx, dz) || 1;
        this.pos.x += dx / l * vel * dt;
        this.pos.z += dz / l * vel * dt;
        this.engine.colisionar(this.pos);
        this.pos.y = this.engine.alturaSuelo(this.pos.x, this.pos.z, this.pos.y + .3);
        this.movReal = Math.hypot(dx, dz) * vel > .01;
        // anti-atasco
        this.stuck = this.movReal && _v.set(this.pos.x - this._px, 0, this.pos.z - this._pz).length() < vel * dt * .3
            ? this.stuck + dt : 0;
        this._px = this.pos.x; this._pz = this.pos.z;
        if (this.stuck > .8) {
            this.stuck = 0;
            const a = Math.random() * Math.PI * 2;
            this.pos.x += Math.cos(a) * .6; this.pos.z += Math.sin(a) * .6;
            this.engine.colisionar(this.pos);
            this.wp = null; this.strafe *= -1;
        }
    }

    _disparar(jugador, dist, e, t) {
        this.nextShot = t + this.cfg.cadenciaMin + Math.random() * (this.cfg.cadenciaMax - this.cfg.cadenciaMin);
        const ojo = this.posOjos(_o);
        // Apuntar al pecho con algo de lead si el jugador corre
        const pecho = _d.copy(jugador.pos); pecho.y += 1.15;
        const lead = jugador.moviendo ? Math.min(.35, dist * .015) : 0;
        if (jugador.moviendo && this._velJ) { pecho.x += this._velJ.x * lead; pecho.z += this._velJ.z * lead; }
        pecho.sub(ojo).normalize();
        // Dispersión que empeora con distancia y movimiento del jugador
        const sp = this.cfg.precision * (1 + dist / 22) * (jugador.moviendo ? 1.5 : 1) * (jugador.corriendo ? 1.3 : 1);
        pecho.x += (Math.random() - .5) * sp; pecho.y += (Math.random() - .5) * sp; pecho.z += (Math.random() - .5) * sp;
        pecho.normalize();
        const { t: tw } = e.rayMuros(ojo, pecho);
        const tj = e.rayCapsula(ojo, pecho, jugador.pos, .55);
        const fin = ojo.clone().addScaledVector(pecho, Math.min(tw, this.cfg.alcanceDisparo));
        const boca = this.posBoca(_v);
        e.trazas.disparo(boca, fin, this.color, .012, .08);
        e.trazas.flash(boca, this.color, .28);
        this.dispararFX();
        e.sfx.botShot();
        if (tj !== null && tj < tw) {
            e.daniar(this.cfg.dano, this.pos);
            e.particulas.emit(fin, 0xff6a5c, 6, 2, .3, .8);
        } else if (tw < Infinity) {
            e.particulas.emit(fin, 0xff9a5c, 5, 1.8, .25, .8);
        }
    }

    /* Waypoint nuevo: preferir puntos a >3 uds con línea de vista
     * (evita elegir objetivos tras un muro y empujarlo en vano).
     * Si ninguno es visible, se elige el más cercano para desatascar. */
    _elegirWaypoint(wps) {
        const ojo = this.posOjos(_o);
        const visibles = wps.filter(p =>
            Math.hypot(p[0] - this.pos.x, p[1] - this.pos.z) > 3 &&
            this.engine.los(ojo, _v.set(p[0], this.pos.y + 1.2, p[1])));
        if (visibles.length) return visibles[(Math.random() * visibles.length) | 0];
        return wps.reduce((a, b) =>
            Math.hypot(b[0] - this.pos.x, b[1] - this.pos.z) <
            Math.hypot(a[0] - this.pos.x, a[1] - this.pos.z) ? b : a);
    }

    tick(dt, t) {
        if (this.terminado) { this.muerto = true; return; }
        const e = this.engine, j = e.jugador;
        this.group.position.copy(this.pos);

        if (!this.vivo) { this.animar(dt, {}); return; }

        const ve = this._veJugador();
        const oye = this._oyeDisparo();
        const dj = _v.set(j.pos.x - this.pos.x, 0, j.pos.z - this.pos.z).length();

        // Velocidad horizontal estimada del jugador (para lead y dispersión)
        this._velJ = this._velJ || new THREE.Vector3();
        if (this._jpx !== undefined && dt > 0) {
            this._velJ.set((j.pos.x - this._jpx) / dt, 0, (j.pos.z - this._jpz) / dt).multiplyScalar(.5)
                .addScaledVector(this._velJ, .5);
        }
        this._jpx = j.pos.x; this._jpz = j.pos.z;

        let moviendo = false;

        if (ve) {
            this.lastSeen = this.lastSeen || new THREE.Vector3();
            this.lastSeen.copy(j.pos);
            if (this.estado !== 'combate' && this.estado !== 'alerta') { this.estado = 'alerta'; this.vioT = 0; e.emit('avisto', this); }
            this.perdioT = 0;
        }

        switch (this.estado) {
            case 'alerta':
                this.mirarHacia(j.pos.x, j.pos.z);
                this.vioT += dt;
                if (this.vioT > this.cfg.reaccion[0] + Math.random() * (this.cfg.reaccion[1] - this.cfg.reaccion[0])) {
                    this.estado = 'combate'; this.vioT = 0;
                }
                break;

            case 'combate': {
                if (!ve) {
                    this.perdioT += dt;
                    if (this.perdioT > 1.6) { this.estado = 'buscar'; this.perdioT = 0; }
                } else this.perdioT = 0;
                this.mirarHacia(j.pos.x, j.pos.z);
                // Strafe perpendicular + ajuste de distancia
                const dx = j.pos.x - this.pos.x, dz = j.pos.z - this.pos.z;
                const l = Math.hypot(dx, dz) || 1;
                if (t > this.strafeT) { this.strafe *= -1; this.strafeT = t + .7 + Math.random() * .9; }
                const hacia = dj > 15 ? .35 : dj < 6 ? -.45 : 0;
                const mvx = (-dz / l) * this.strafe + dx / l * hacia;
                const mvz = (dx / l) * this.strafe + dz / l * hacia;
                this._avanzar(mvx, mvz, dt, this.cfg.vel * .75);
                moviendo = true;
                if (ve && t >= this.nextShot) this._disparar(j, dj, e, t);
                break;
            }

            case 'buscar': {
                const wp = this.lastSeen;
                if (!wp) { this.estado = 'patrulla'; break; }
                const dx = wp.x - this.pos.x, dz = wp.z - this.pos.z;
                if (Math.hypot(dx, dz) < 1.4) {
                    // Mirar alrededor un momento y volver a patrullar
                    this.yaw += dt * 1.6;
                    this.perdioT += dt;
                    if (this.perdioT > 2.2) { this.estado = 'patrulla'; this.lastSeen = null; }
                } else {
                    this._avanzar(dx, dz, dt, this.cfg.vel);
                    this.yaw = Math.atan2(-dx, -dz);
                    moviendo = true;
                }
                break;
            }

            default: { // patrulla
                if (oye && j.vivo) {
                    this.lastSeen = this.lastSeen || new THREE.Vector3();
                    this.lastSeen.copy(j.pos);
                    this.estado = 'buscar'; this.perdioT = 0;
                    break;
                }
                const wps = this.cfg.waypoints || [];
                if (wps.length) {
                    if (!this.wp || Math.hypot(this.wp[0] - this.pos.x, this.wp[1] - this.pos.z) < 1.3) {
                        this.wp = this._elegirWaypoint(wps);
                    }
                    const dx = this.wp[0] - this.pos.x, dz = this.wp[1] - this.pos.z;
                    this._avanzar(dx, dz, dt, this.cfg.vel * .65);
                    this.yaw = Math.atan2(-dx, -dz);
                    moviendo = true;
                }
            }
        }

        this.aplicarYaw(dt);
        this.animar(dt, { moviendo, corriendo: false, aire: false, aim: this.estado === 'combate' || this.estado === 'alerta', pitch: 0 });
    }
}
