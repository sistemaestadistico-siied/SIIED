/* Objetos de misión: chontaduros recolectables, zonas de entrega,
 * antenas interactivas (mantener E) y balizas de guía. */
import * as THREE from 'three';
import { sprite } from './engine.js';

const _v = new THREE.Vector3();

/* ---------- Chontaduro: racimo de frutos naranja (mini-palma) ---------- */
export function crearChontaduro(color = 0xff8c00, escala = 1) {
    const g = new THREE.Group();
    const matFruto = new THREE.MeshLambertMaterial({ color, emissive: 0x904400, emissiveIntensity: .4 });
    const matTallo = new THREE.MeshLambertMaterial({ color: 0x3f6b1f });
    // Racimo: esfera central + esferitas alrededor
    const centro = new THREE.Mesh(new THREE.SphereGeometry(.34, 12, 10), matFruto);
    centro.scale.y = 1.15;
    g.add(centro);
    for (let i = 0; i < 7; i++) {
        const a = i / 7 * Math.PI * 2;
        const s = new THREE.Mesh(new THREE.SphereGeometry(.13, 8, 6), matFruto);
        s.position.set(Math.cos(a) * .33, .12 * Math.sin(i * 2.1), Math.sin(a) * .33);
        g.add(s);
    }
    const tallo = new THREE.Mesh(new THREE.CylinderGeometry(.03, .05, .5, 6), matTallo);
    tallo.position.y = .4; g.add(tallo);
    // Brillo pulsante
    const brillo = new THREE.Mesh(new THREE.SphereGeometry(.62, 12, 10),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .16, blending: THREE.AdditiveBlending, depthWrite: false }));
    brillo.position.y = .1;
    g.add(brillo);
    g.userData.brillo = brillo;
    g.scale.setScalar(escala);
    return g;
}

/* ---------- Pickup recolectable ---------- */
export class Pickup {
    /** o: {x,y,z,color,valor,escala,nombre} */
    constructor(engine, o) {
        this.engine = engine;
        this.tipo = 'chontaduro';
        this.valor = o.valor ?? 1;
        this.color = o.color ?? 0xff8c00;
        this.recogido = false;
        this.group = new THREE.Group();
        this.mesh = crearChontaduro(this.color, o.escala ?? 1);
        this.group.add(this.mesh);
        this.group.position.set(o.x, o.y, o.z);
        this.mesh.position.y = .55;
        this.fase = Math.random() * 9;
        // Columna de luz que lo delata a distancia
        this.columna = new THREE.Mesh(
            new THREE.CylinderGeometry(.09, .22, 8, 8, 1, true),
            new THREE.MeshBasicMaterial({ color: this.color, transparent: true, opacity: .13,
                blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
        this.columna.position.y = 4;
        this.group.add(this.columna);
        this.engine.add(this.group);
        this.pos = this.group.position;
        engine.ents.push(this);
    }
    tick(dt, t) {
        if (this.recogido) return;
        this.group.rotation.y += dt * 1.4;
        this.mesh.position.y = .55 + Math.sin(t * 2 + this.fase) * .15;
        this.mesh.userData.brillo.scale.setScalar(1 + Math.sin(t * 3 + this.fase) * .18);
        const j = this.engine.jugador;
        if (j.vivo && this.pos.distanceTo(_v.copy(j.pos).setY(j.pos.y + .8)) < 1.5) this.recoger();
    }
    recoger() {
        if (this.recogido) return;
        this.recogido = true;
        this.engine.particulas.emit(this.pos, this.color, 16, 3.5, .6, 1.4);
        this.engine.sfx.pickup();
        this.engine.scene.remove(this.group);
        this.engine.emit('pickup', this);
    }
}

/* ---------- Zona de entrega / llegada ---------- */
export class Zona {
    /** o: {x,y,z,r,color,nombre} */
    constructor(engine, o) {
        this.engine = engine;
        this.r = o.r ?? 3;
        this.pos = new THREE.Vector3(o.x, o.y ?? 0, o.z);
        this.color = o.color ?? 0x46d98b;
        this.activa = true;
        const suelo = new THREE.Mesh(new THREE.CylinderGeometry(this.r, this.r, .06, 36),
            new THREE.MeshBasicMaterial({ color: this.color, transparent: true, opacity: .15 }));
        suelo.position.copy(this.pos).y += .04;
        this.aro = new THREE.Mesh(new THREE.TorusGeometry(this.r, .09, 8, 48),
            new THREE.MeshBasicMaterial({ color: this.color, transparent: true, opacity: .9 }));
        this.aro.rotation.x = Math.PI / 2;
        this.aro.position.copy(this.pos).y += .12;
        engine.add(suelo); engine.add(this.aro);
        this.meshes = [suelo, this.aro];
        if (o.nombre) {
            this.etiqueta = sprite(o.nombre, '#ffffff', 26);
            this.etiqueta.position.copy(this.pos).y += 2.6;
            engine.add(this.etiqueta);
        }
        // Haz de luz alto: se ve tras los muros
        this.haz = new THREE.Mesh(new THREE.CylinderGeometry(.35, this.r * .8, 26, 12, 1, true),
            new THREE.MeshBasicMaterial({ color: this.color, transparent: true, opacity: .08,
                blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
        this.haz.position.copy(this.pos).y += 13;
        engine.add(this.haz);
        this.fase = Math.random() * 9;
        engine.ents.push(this);
    }
    contiene(p) {
        return Math.hypot(p.x - this.pos.x, p.z - this.pos.z) < this.r &&
               Math.abs(p.y - this.pos.y) < 3;
    }
    tick(dt, t) {
        if (!this.activa) return;
        const s = 1 + Math.sin(t * 2.5 + this.fase) * .05;
        this.aro.scale.setScalar(s);
        this.haz.material.opacity = .06 + Math.sin(t * 2 + this.fase) * .025;
    }
    apagar() {
        this.activa = false;
        for (const m of this.meshes) m.visible = false;
        if (this.etiqueta) this.etiqueta.visible = false;
        this.haz.visible = false;
    }
}

/* ---------- Antena interactuable (mantener E cerca) ---------- */
export class Antena {
    /** o: {x,y,z,nombre,tiempo} — y = nivel de suelo donde está el panel */
    constructor(engine, o) {
        this.engine = engine;
        this.pos = new THREE.Vector3(o.x, o.y, o.z);
        this.tiempo = o.tiempo ?? 1.6;
        this.carga = 0;
        this.activada = false;
        this.nombre = o.nombre || 'Antena';
        // Panel + mástil
        const mat = new THREE.MeshLambertMaterial({ color: 0x3a4d63 });
        const mastil = new THREE.Mesh(new THREE.CylinderGeometry(.14, .2, 2.2, 8), mat);
        mastil.position.copy(this.pos).y += 1.1;
        const panel = new THREE.Mesh(new THREE.BoxGeometry(.9, .7, .18),
            new THREE.MeshLambertMaterial({ color: 0x1c2a3d, emissive: 0x8B3FBF, emissiveIntensity: .5 }));
        panel.position.copy(this.pos).y += 1.9;
        this.panel = panel;
        this.luz = new THREE.Mesh(new THREE.SphereGeometry(.14, 10, 8),
            new THREE.MeshBasicMaterial({ color: 0xe84c3c }));
        this.luz.position.copy(this.pos).y += 2.5;
        engine.add(mastil); engine.add(panel); engine.add(this.luz);
        this.etiqueta = sprite(`E · ${this.nombre}`, '#c98bff', 22);
        this.etiqueta.position.copy(this.pos).y += 3.2;
        this.etiqueta.material.opacity = 0;
        engine.add(this.etiqueta);
        this.cerca = false;
        engine.ents.push(this);
    }
    tick(dt, t) {
        const j = this.engine.jugador;
        this.cerca = j.vivo && this.pos.distanceTo(_v.copy(j.pos).setY(j.pos.y + 1)) < 3.2;
        this.etiqueta.material.opacity = this.cerca && !this.activada ? 1 : 0;
        if (this.activada) return;
        if (this.cerca && this.engine.keys.KeyE) {
            this.carga += dt;
            if (this.carga >= this.tiempo) this.activar();
        } else this.carga = Math.max(0, this.carga - dt * 1.5);
        // Progreso: el panel se ilumina con la carga
        this.panel.material.emissiveIntensity = .5 + this.carga / this.tiempo * 2;
        this.luz.material.color.setHex(this.carga > 0 ? 0xf1c40f : 0xe84c3c);
    }
    progreso() { return this.activada ? 1 : this.carga / this.tiempo; }
    activar() {
        this.activada = true;
        this.carga = this.tiempo;
        this.luz.material.color.setHex(0x46d98b);
        this.panel.material.emissive.setHex(0x2B7D59);
        this.engine.particulas.emit(_v.copy(this.pos).setY(this.pos.y + 2.2), 0x46d98b, 20, 4, .7, 1.5);
        this.engine.sfx.deliver();
        this.engine.emit('antena', this);
    }
}

/* ---------- Botiquín ---------- */
export class Botiquin {
    constructor(engine, o) {
        this.engine = engine;
        this.pos = new THREE.Vector3(o.x, o.y ?? 0, o.z);
        this.usado = false;
        const g = new THREE.Group();
        const caja = new THREE.Mesh(new THREE.BoxGeometry(.55, .4, .55),
            new THREE.MeshLambertMaterial({ color: 0xe8e0d0 }));
        const cruzV = new THREE.Mesh(new THREE.BoxGeometry(.32, .1, .12), new THREE.MeshBasicMaterial({ color: 0xe84c3c }));
        cruzV.position.y = .22;
        const cruzH = new THREE.Mesh(new THREE.BoxGeometry(.12, .1, .32), new THREE.MeshBasicMaterial({ color: 0xe84c3c }));
        cruzH.position.y = .22;
        g.add(caja, cruzV, cruzH);
        g.position.copy(this.pos).y += .25;
        engine.add(g);
        this.mesh = g;
        engine.ents.push(this);
    }
    tick(dt, t) {
        if (this.usado) return;
        this.mesh.rotation.y += dt;
        const j = this.engine.jugador;
        if (j.vivo && j.hp < j.hpMax && this.pos.distanceTo(j.pos) < 1.4) {
            this.usado = true;
            j.hp = Math.min(j.hpMax, j.hp + 50);
            this.engine.emit('hp', j.hp);
            this.engine.particulas.emit(this.pos, 0x46d98b, 12, 3, .5, 1.4);
            this.engine.sfx.pickup();
            this.engine.scene.remove(this.mesh);
        }
    }
}
