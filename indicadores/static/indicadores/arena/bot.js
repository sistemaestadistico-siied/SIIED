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
    inofensivo: false,                   // registro válido: no combate, huye
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
        this.cargaT = 0;                        // telegrafía de disparo
        this.stuck = 0;
        this.muertoT = 0;
        this.velReal = 0;                       // m/s medidos (alimenta la zancada)
        this.plantadoT = 0;                     // en combate: ventanas sin strafe
        this.scanBase = 0;
        this.aparecer();
        this.pos.set(o.pos[0], o.pos[1], o.pos[2]);
        this.group.position.copy(this.pos);
        this.yaw = Math.random() * Math.PI * 2;
        this.id = 'bot-' + (_rid++);
        this.marca = null;
    }

    /* ——— Sensores ——— */
    _pan(e) {
        const j = e.jugador;
        const dx = this.pos.x - j.pos.x, dz = this.pos.z - j.pos.z, d = Math.hypot(dx, dz) || 1;
        // Vector derecha del jugador: (cos yaw, 0, -sin yaw)
        return THREE.MathUtils.clamp((dx * Math.cos(j.yaw) - dz * Math.sin(j.yaw)) / d, -1, 1);
    }
    _volPan(e) {
        const d = Math.hypot(this.pos.x - e.jugador.pos.x, this.pos.z - e.jugador.pos.z);
        return THREE.MathUtils.clamp(1.15 - d / 45, .25, 1);
    }
    _veJugador() {
        const e = this.engine, j = e.jugador;
        if (!j.vivo) return false;
        const d = _v.set(j.pos.x - this.pos.x, 0, j.pos.z - this.pos.z).length();
        if (d > this.cfg.vision * (j.agachado ? .7 : 1)) return false;
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
        const tj = e.rayCapsula(ojo, pecho, jugador.pos, .55, jugador.alto);
        const fin = ojo.clone().addScaledVector(pecho, Math.min(tw, this.cfg.alcanceDisparo));
        const boca = this.posBoca(_v);
        e.trazas.disparo(boca, fin, this.color, .012, .08);
        e.trazas.flash(boca, this.color, .28);
        this.dispararFX();
        e.sfx.botShot(this._pan(e), this._volPan(e));
        if (tj !== null && tj < tw) {
            e.daniar(this.cfg.dano, this.pos);
            e.sfx.hurt();
            e.particulas.emit(fin, 0xff6a5c, 6, 2, .3, .8);
        } else if (tw < Infinity) {
            e.particulas.emit(fin, 0xff9a5c, 5, 1.8, .25, .8);
        }
    }

    /* Patrulla normal por waypoints. Devuelve true si se está moviendo. */
    _patrullar(dt) {
        const wps = this.cfg.waypoints || [];
        if (!wps.length) return false;
        if (!this.wp || Math.hypot(this.wp[0] - this.pos.x, this.wp[1] - this.pos.z) < 1.3) {
            this.wp = this._elegirWaypoint(wps);
        }
        const dx = this.wp[0] - this.pos.x, dz = this.wp[1] - this.pos.z;
        this._avanzar(dx, dz, dt, this.cfg.vel * .65);
        this.yaw = Math.atan2(-dx, -dz);
        return true;
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
        if (!this._sonoSpawn) { this._sonoSpawn = true; e.sfx.spawn(this._pan(e)); }

        // Empujón por impacto (vivo o cayendo): respeta muros
        if (this.aplicarKnock(dt)) {
            e.colisionar(this.pos);
            this.pos.y = e.alturaSuelo(this.pos.x, this.pos.z, this.pos.y + .3);
            this.group.position.copy(this.pos);
        }
        // Posición de referencia: para medir velocidad y dirección reales
        // del desplazamiento voluntario (el empujón no cuenta como zancada)
        const px0 = this.pos.x, pz0 = this.pos.z;

        if (!this.vivo) {
            if (!this._caido && this.anim.dead > .55) { this._caido = true; e.sfx.fall(this._pan(e)); }
            this.animar(dt, {}); return;
        }

        let ve = this._veJugador();
        const oye = this._oyeDisparo();
        const dj = _v.set(j.pos.x - this.pos.x, 0, j.pos.z - this.pos.z).length();

        // Velocidad horizontal estimada del jugador (para lead y dispersión)
        this._velJ = this._velJ || new THREE.Vector3();
        if (this._jpx !== undefined && dt > 0) {
            this._velJ.set((j.pos.x - this._jpx) / dt, 0, (j.pos.z - this._jpz) / dt).multiplyScalar(.5)
                .addScaledVector(this._velJ, .5);
        }
        this._jpx = j.pos.x; this._jpz = j.pos.z;

        let moviendo = false, scan = false;

        // Registro válido (procesamiento): jamás entra en combate ni
        // dispara. Si lo dañan o el jugador se le acerca, huye con zigzag.
        if (this.cfg.inofensivo) {
            ve = false;
            if (this._hpAnt === undefined) this._hpAnt = this.hp;
            if (this.hp < this._hpAnt || dj < 3) {
                this.estado = 'huir'; this.huirT = t + (this.hp < this._hpAnt ? 4 : 2.5);
            }
            this._hpAnt = this.hp;
            if (this.estado === 'huir' && t < this.huirT) {
                const dx = this.pos.x - j.pos.x, dz = this.pos.z - j.pos.z, l = Math.hypot(dx, dz) || 1;
                const zig = Math.sin(t * 3.2) * .55;
                this._avanzar(dx / l - dz / l * zig, dz / l + dx / l * zig, dt, this.cfg.vel * 1.15);
                this.yaw = Math.atan2(-dx, -dz);
                moviendo = true;
            } else {
                if (this.estado === 'huir') this.estado = 'patrulla';
                moviendo = this._patrullar(dt);
            }
            this.aplicarYaw(dt);
            this.animar(dt, {
                moviendo: moviendo && this.velReal > .15,
                corriendo: this.estado === 'huir',
                aire: false, aim: false, pitch: 0,
                vel: this.velReal, dirF: 1, dirR: 0, scan: false,
            });
            this._medirVelocidad(dt, px0, pz0);
            return;
        }

        if (ve) {
            this.lastSeen = this.lastSeen || new THREE.Vector3();
            this.lastSeen.copy(j.pos);
            if (this.estado !== 'combate' && this.estado !== 'alerta') {
                this.estado = 'alerta'; this.vioT = 0; this.sobresalto(); e.emit('avisto', this);
            }
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
                // Strafe perpendicular + ajuste de distancia. Cada cierto
                // tiempo se planta a disparar (ventana sin strafe) para que
                // el movimiento no sea un péndulo constante.
                const dx = j.pos.x - this.pos.x, dz = j.pos.z - this.pos.z;
                const l = Math.hypot(dx, dz) || 1;
                if (t > this.strafeT) {
                    if (this.plantadoT <= 0 && Math.random() < .3) {
                        this.plantadoT = .5 + Math.random() * .7;
                        this.strafeT = t + this.plantadoT;
                    } else {
                        this.strafe *= -1; this.strafeT = t + .7 + Math.random() * .9;
                    }
                }
                this.plantadoT = Math.max(0, this.plantadoT - dt);
                const sf = this.plantadoT > 0 ? 0 : this.strafe;
                const hacia = dj > 15 ? .35 : dj < 6 ? -.45 : 0;
                const mvx = (-dz / l) * sf + dx / l * hacia;
                const mvz = (dx / l) * sf + dz / l * hacia;
                if (Math.hypot(mvx, mvz) > .05) {
                    this._avanzar(mvx, mvz, dt, this.cfg.vel * .75);
                    moviendo = true;
                }
                // Telegrafía: el orbe carga ~.32 s antes del disparo;
                // si el jugador rompe la línea de visión, se disipa.
                if (ve && t >= this.nextShot && this.cargaT <= 0) {
                    this.cargaT = .32;
                    e.sfx.charge(this._pan(e), this._volPan(e));
                }
                if (this.cargaT > 0) {
                    this.cargaT -= dt;
                    if (!ve) { this.cargaT = 0; this.cargando(0); this.nextShot = t + .4; }
                    else if (this.cargaT <= 0) this._disparar(j, dj, e, t);
                    else this.cargando(1 - this.cargaT / .32);
                }
                break;
            }

            case 'buscar': {
                const wp = this.lastSeen;
                if (!wp) { this.estado = 'patrulla'; break; }
                const dx = wp.x - this.pos.x, dz = wp.z - this.pos.z;
                if (Math.hypot(dx, dz) < 1.4) {
                    // Barrer con la cabeza/tronco (scan) y girar el cuerpo
                    // suavemente a lado y lado antes de volver a patrullar
                    if (this.perdioT === 0) this.scanBase = this.yaw;
                    this.perdioT += dt;
                    this.yaw = this.scanBase + Math.sin(this.perdioT * 1.4) * .9;
                    scan = true;
                    if (this.perdioT > 2.6) { this.estado = 'patrulla'; this.lastSeen = null; }
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
                moviendo = this._patrullar(dt);
            }
        }

        this.aplicarYaw(dt);
        this._medirVelocidad(dt, px0, pz0);

        const combate = this.estado === 'combate' || this.estado === 'alerta';
        this.animar(dt, {
            moviendo: moviendo && this.velReal > .15,
            corriendo: this.estado === 'buscar',
            aire: false, aim: combate, pitch: 0,
            vel: this.velReal, dirF: this._dirF, dirR: this._dirR, scan,
        });
    }

    /* Velocidad real y dirección de movimiento en el marco del cuerpo. */
    _medirVelocidad(dt, px0, pz0) {
        const mdx = this.pos.x - px0, mdz = this.pos.z - pz0;
        const vInst = dt > 0 ? Math.hypot(mdx, mdz) / dt : 0;
        this.velReal += (vInst - this.velReal) * Math.min(1, dt * 10);
        this._dirF = 1; this._dirR = 0;
        if (vInst > .05) {
            const ry = this.group.rotation.y;
            const fx = -Math.sin(ry), fz = -Math.cos(ry);
            const rx = Math.cos(ry), rz = -Math.sin(ry);
            const l = Math.hypot(mdx, mdz);
            this._dirF = (mdx * fx + mdz * fz) / l;
            this._dirR = (mdx * rx + mdz * rz) / l;
        }
    }
}
