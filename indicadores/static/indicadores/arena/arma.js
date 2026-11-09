/* Lector DT-7 — arma en primera persona (viewmodel).
 * Escena y cámara propias: se dibuja encima del mundo tras limpiar el
 * depth buffer, así nunca atraviesa paredes. Perfiles extruidos con
 * bisel, mira holográfica, manos con guantes, logo SIIED y animaciones
 * por resortes: desenfundar, disparo, recarga, inspección, sprint, ADS. */
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const LOGO_SIIED = (window.DD_STATIC || '/static/') + 'indicadores/images/unnamed.png';
const lerp = THREE.MathUtils.lerp, clamp = THREE.MathUtils.clamp;
const easeOutBack = x => 1 + 2.4 * Math.pow(x - 1, 3) + 1.4 * Math.pow(x - 1, 2);
const smooth = x => x * x * (3 - 2 * x);
const fase = (t, a, b) => clamp((t - a) / (b - a), 0, 1);

/* Resorte amortiguado 3D (semi-implícito, 2 subpasos) */
class Resorte {
    constructor(k = 170, d = 16) { this.k = k; this.d = d; this.x = new THREE.Vector3(); this.v = new THREE.Vector3(); }
    tick(dt, obj) {
        const h = dt / 2;
        for (let i = 0; i < 2; i++) {
            this.v.x += ((obj.x - this.x.x) * this.k - this.v.x * this.d) * h;
            this.v.y += ((obj.y - this.x.y) * this.k - this.v.y * this.d) * h;
            this.v.z += ((obj.z - this.x.z) * this.k - this.v.z * this.d) * h;
            this.x.addScaledVector(this.v, h);
        }
    }
    impulso(x, y, z) { this.v.x += x; this.v.y += y; this.v.z += z; }
}

/* Perfil 2D (adelante, arriba) extruido en grosor X, adelante = -Z */
function perfil(pts, grosor, mat, bevel = .004) {
    const s = new THREE.Shape();
    s.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) s.lineTo(pts[i][0], pts[i][1]);
    s.closePath();
    const d = Math.max(.002, grosor - 2 * bevel);
    const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: true, bevelThickness: bevel,
        bevelSize: bevel, bevelSegments: 2, curveSegments: 4 });
    g.rotateY(Math.PI / 2); g.translate(-d / 2, 0, 0); g.computeVertexNormals();
    return new THREE.Mesh(g, mat);
}
function caja(w, h, l, mat, x, y, f) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, l), mat); m.position.set(x, y, -f); return m;
}
function tubo(r, f0, f1, mat, y = 0, seg = 16) {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, f1 - f0, seg), mat);
    m.rotation.x = Math.PI / 2; m.position.set(0, y, -(f0 + f1) / 2); return m;
}
/* Segmento cilíndrico entre a y b (brazos) */
function segmento(a, b, r0, r1, mat) {
    const d = new THREE.Vector3().subVectors(b, a), l = d.length();
    const m = new THREE.Mesh(new THREE.CylinderGeometry(r1, r0, l, 12), mat);
    m.position.copy(a).addScaledVector(d, .5);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
    return m;
}
function texReticula() {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    g.strokeStyle = '#46ff9b'; g.fillStyle = '#46ff9b'; g.shadowColor = '#46ff9b'; g.shadowBlur = 8;
    g.lineWidth = 5; g.beginPath(); g.arc(64, 64, 40, 0, Math.PI * 2); g.stroke();
    g.beginPath(); g.arc(64, 64, 5, 0, Math.PI * 2); g.fill();
    for (const [x, y, w, h] of [[62, 6, 4, 16], [62, 106, 4, 16], [6, 62, 16, 4], [106, 62, 16, 4]]) g.fillRect(x, y, w, h);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function texFlash() {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d'); g.translate(64, 64);
    const gr = g.createRadialGradient(0, 0, 2, 0, 0, 60);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(.25, 'rgba(190,255,220,.9)'); gr.addColorStop(1, 'rgba(70,217,139,0)');
    g.fillStyle = gr;
    for (let i = 0; i < 6; i++) {
        g.rotate(Math.PI / 3); g.beginPath();
        g.moveTo(0, -7); g.lineTo(60 - (i % 2) * 22, 0); g.lineTo(0, 7); g.fill();
    }
    g.beginPath(); g.arc(0, 0, 22, 0, Math.PI * 2); g.fill();
    return new THREE.CanvasTexture(c);
}

export class Arma {
    constructor(renderer) {
        this.scene = new THREE.Scene();
        this.cam = new THREE.PerspectiveCamera(56, innerWidth / innerHeight, .01, 10);
        this.scene.add(this.cam);
        const pm = new THREE.PMREMGenerator(renderer);
        this.scene.environment = pm.fromScene(new RoomEnvironment(), .04).texture;
        pm.dispose();
        this.hemi = new THREE.HemisphereLight(0xcfe6ff, 0x1a2430, .9); this.scene.add(this.hemi);
        this.key = new THREE.DirectionalLight(0xffffff, 1.6); this.key.position.set(1, 2, 1); this.scene.add(this.key);
        const rim = new THREE.DirectionalLight(0x7cd8ff, .8); rim.position.set(-2, .5, -1); this.scene.add(rim);
        this.luz = new THREE.PointLight(0x7dffb8, 0, 1.6, 2); this.scene.add(this.luz);

        this.cap = 30; this.mag = 30;
        this.estado = 'draw'; this.tEst = 0;
        this.aim = 0; this.sprint = 0; this.calor = 0;
        this.pos = new Resorte(190, 17); this.rot = new Resorte(160, 14);
        this.sfx = null;
        this.casquillos = [];
        this._modelo();
    }

    _modelo() {
        const M = (c, r, m, ex = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: r, metalness: m, ...ex });
        const metal = M(0x1d2c3c, .32, .85), poli = M(0x1a1f26, .78, .05), acento = M(0x2B7D59, .45, .4);
        const cromo = M(0x9aa8b6, .18, 1), emis = M(0x46d98b, .4, 0, { emissive: 0x46d98b, emissiveIntensity: 2.2 });
        this.matEmis = emis;
        const guante = M(0x20262e, .85, 0), nudillo = M(0x2B7D59, .6, .1);
        const manga = M(0x13314a, .9, 0), puno = M(0x0f2234, .9, 0);

        const R = this.raiz = new THREE.Group();   // posición (resortes)
        const W = this.arma = new THREE.Group();   // modelo del arma
        R.add(W); this.cam.add(R);

        W.add(perfil([[-.13, 0], [.24, 0], [.24, .046], [.05, .052], [-.1, .052], [-.13, .032]], .052, metal));
        W.add(perfil([[-.1, -.046], [.13, -.046], [.15, .002], [-.12, .002]], .046, poli));
        W.add(perfil([[-.07, -.044], [-.026, -.044], [-.044, -.152], [-.096, -.146]], .04, poli));
        W.add(perfil([[-.13, .036], [-.13, -.028], [-.33, -.07], [-.36, -.072], [-.36, .042], [-.29, .047]], .04, poli));
        W.add(caja(.044, .012, .07, poli, 0, -.07, -.005));                                         // guardamonte
        W.add(perfil([[.24, -.03], [.42, -.026], [.42, .042], [.24, .046]], .06, poli));            // guardamanos
        for (let i = 0; i < 4; i++) for (const sx of [-1, 1])
            W.add(caja(.004, .012, .028, emis, sx * .031, .01, .27 + i * .04));                    // ventilas
        for (let i = 0; i < 12; i++) W.add(caja(.03, .007, .012, metal, 0, .057, -.1 + i * .026));  // riel
        W.add(tubo(.013, .42, .58, cromo));
        this.bobinas = [.45, .49, .53].map(f => {
            const t = new THREE.Mesh(new THREE.TorusGeometry(.03, .006, 8, 20), emis);
            t.position.z = -f; W.add(t); return t;
        });
        W.add(tubo(.022, .565, .62, metal));
        for (const sx of [-1, 1]) W.add(caja(.006, .012, .02, emis, sx * .02, 0, .595));
        this.boca = new THREE.Object3D(); this.boca.position.z = -.64; W.add(this.boca);
        // Mira holográfica (ventana centrada en y=.094, f=.06)
        W.add(caja(.036, .012, .1, metal, 0, .061, .06));
        for (const sx of [-1, 1]) W.add(caja(.006, .05, .04, metal, sx * .025, .092, .06));
        W.add(caja(.056, .007, .04, metal, 0, .119, .06));
        const vidrio = new THREE.Mesh(new THREE.PlaneGeometry(.044, .044), new THREE.MeshBasicMaterial({
            map: texReticula(), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: .95 }));
        vidrio.position.set(0, .094, -.07); W.add(vidrio);
        this.ojoMira = new THREE.Vector3(0, .094, 0);
        // Cargador con celda de energía (indica munición)
        this.cargador = new THREE.Group();
        this.cargador.add(perfil([[.045, -.046], [.1, -.046], [.116, -.175], [.06, -.186]], .036, acento));
        this.celda = caja(.038, .1, .008, emis, 0, -.11, .1);
        this.celda.geometry.translate(0, .05, 0); this.celda.position.y = -.165;
        this.cargador.add(this.celda); W.add(this.cargador);
        this.palanca = caja(.03, .012, .02, cromo, .034, .03, .1); W.add(this.palanca);
        // Logo SIIED y placa en el costado visible
        const tl = new THREE.TextureLoader();
        tl.load(LOGO_SIIED, t => {
            t.colorSpace = THREE.SRGBColorSpace;
            const p = new THREE.Mesh(new THREE.PlaneGeometry(.05, .058), new THREE.MeshStandardMaterial({
                map: t, transparent: true, roughness: .5, metalness: .2, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: .25 }));
            p.position.set(-.0285, .022, -.12); p.rotation.y = -Math.PI / 2; W.add(p);
        });
        const cv = document.createElement('canvas'); cv.width = 256; cv.height = 64;
        const g = cv.getContext('2d'); g.fillStyle = '#46d98b'; g.font = 'bold 34px Orbitron, sans-serif';
        g.textBaseline = 'middle'; g.fillText('DT-7 · SIIED', 8, 34);
        const tt = new THREE.CanvasTexture(cv); tt.colorSpace = THREE.SRGBColorSpace;
        const placa = new THREE.Mesh(new THREE.PlaneGeometry(.12, .03), new THREE.MeshBasicMaterial({ map: tt, transparent: true }));
        placa.position.set(-.0315, .008, -.33); placa.rotation.y = -Math.PI / 2; W.add(placa);

        // Manos y brazos
        const V = (x, y, f) => new THREE.Vector3(x, y, -f);
        this.manoD = new THREE.Group();
        this.manoD.add(segmento(V(-.035, -.085, -.04), V(.11, -.3, -.3), .026, .036, guante));
        this.manoD.add(segmento(V(.1, -.28, -.27), V(.2, -.42, -.55), .045, .052, manga));
        this.manoD.add(segmento(V(.085, -.25, -.22), V(.105, -.29, -.28), .041, .041, puno));
        const palmaD = new THREE.Mesh(new THREE.CapsuleGeometry(.028, .05, 4, 10), guante);
        palmaD.position.copy(V(-.05, -.085, -.05)); palmaD.rotation.x = .35; this.manoD.add(palmaD);
        for (let i = 0; i < 3; i++) this.manoD.add(caja(.05, .014, .016, nudillo, -.005, -.065 - i * .022, -.03));
        W.add(this.manoD);
        this.manoI = new THREE.Group();
        const palmaI = new THREE.Mesh(new THREE.CapsuleGeometry(.03, .06, 4, 10), guante);
        palmaI.rotation.z = Math.PI / 2; palmaI.position.copy(V(-.006, -.048, .34)); this.manoI.add(palmaI);
        for (let i = 0; i < 4; i++) this.manoI.add(caja(.012, .03, .014, guante, .034, -.02, .31 + i * .02));
        this.manoI.add(caja(.04, .01, .05, nudillo, -.03, -.03, .34));
        this.manoI.add(segmento(V(-.03, -.07, .33), V(-.12, -.26, .12), .03, .038, guante));
        this.manoI.add(segmento(V(-.11, -.24, .14), V(-.26, -.42, -.15), .046, .054, manga));
        const reloj = caja(.05, .022, .03, emis, -.105, -.24, .15); reloj.rotation.x = .9; this.manoI.add(reloj);
        W.add(this.manoI);
        this.manoIBase = this.manoI.position.clone();

        // Fogonazo
        const fm = new THREE.MeshBasicMaterial({ map: texFlash(), transparent: true, blending: THREE.AdditiveBlending,
            depthWrite: false, side: THREE.DoubleSide });
        this.flash = new THREE.Group();
        const pf = new THREE.Mesh(new THREE.PlaneGeometry(.22, .22), fm); this.flash.add(pf);
        for (const ry of [Math.PI / 2, 0]) {
            const p = new THREE.Mesh(new THREE.PlaneGeometry(.1, .34), fm);
            p.rotation.set(Math.PI / 2, ry, 0); p.position.z = -.12; this.flash.add(p);
        }
        this.flash.position.z = -.66; this.flash.visible = false; W.add(this.flash);
        this.flashT = 0;
        this.geoCasq = new THREE.CylinderGeometry(.006, .006, .03, 8);
        this.hip = new THREE.Vector3(.165, -.165, -.38);
    }

    get recargando() { return this.estado === 'reload'; }
    puedeDisparar() { return (this.estado === 'idle' || this.estado === 'inspect') && this.mag > 0 && this.sprint < .35; }
    sacar() { this._est('draw'); this.mag = this.cap; }
    _est(s) { this.estado = s; this.tEst = 0; }
    recargar() {
        if (this.estado === 'reload' || this.estado === 'draw' || this.mag >= this.cap) return false;
        this._est('reload'); this.sfx?.reloadOut(); this._rq = 0; return true;
    }
    inspeccionar() { if (this.estado === 'idle') this._est('inspect'); }

    disparo(aim) {
        if (this.estado === 'inspect') this._est('idle');
        this.mag--;
        const k = aim ? .45 : 1;
        this.pos.impulso((Math.random() - .5) * .08 * k, .05 * k, .9 * k);
        this.rot.impulso(1.6 * k, (Math.random() - .5) * .9 * k, (Math.random() - .5) * .8 * k);
        this.flash.visible = true; this.flash.rotation.z = Math.random() * Math.PI;
        this.flash.scale.setScalar(.8 + Math.random() * .5); this.flashT = .045;
        this.luz.intensity = 3.5; this.calor = Math.min(1, this.calor + .12);
        // Casquillo energético expulsado
        const m = new THREE.Mesh(this.geoCasq, this.matEmis);
        this.arma.localToWorld(m.position.set(.035, .03, -.1));
        this.cam.worldToLocal(m.position);
        m.userData.v = new THREE.Vector3(1.4 + Math.random() * .6, 1.1 + Math.random() * .5, .3);
        m.userData.w = new THREE.Vector3(Math.random() * 20, Math.random() * 20, 0);
        m.userData.vida = .7; this.cam.add(m); this.casquillos.push(m);
    }
    impulsoAterrizaje(f) { this.pos.impulso(0, -f * 1.2, 0); this.rot.impulso(-f * 4, 0, 0); }

    /* s: {aim, sprint, amp, ph, swayX, swayY, aire, agachado, vivo} */
    tick(dt, s) {
        this.tEst += dt;
        this.aim = lerp(this.aim, s.aim && this.estado !== 'reload' ? 1 : 0, Math.min(1, dt * 12));
        this.sprint = lerp(this.sprint, s.sprint ? 1 : 0, Math.min(1, dt * 8));
        this.calor = Math.max(0, this.calor - dt * .5);
        const a = this.aim, sp = this.sprint * (1 - a);
        // Objetivos de posición/rotación
        const ads = new THREE.Vector3(-this.ojoMira.x, -this.ojoMira.y, -.24);
        const P = new THREE.Vector3().lerpVectors(this.hip, ads, smooth(a));
        const Rr = new THREE.Vector3();
        P.x += sp * -.02; P.y += sp * -.05; Rr.x += sp * -.28; Rr.y += sp * .75; Rr.z += sp * .32;
        if (s.agachado) { P.y -= .012 * (1 - a); Rr.z += .06 * (1 - a); }
        const amp = s.amp * (1 - a * .85);
        P.x += Math.sin(s.ph * .5) * amp * .5; P.y -= Math.abs(Math.sin(s.ph)) * amp * .35;
        Rr.z += Math.sin(s.ph * .5) * amp * .9; Rr.x += Math.abs(Math.sin(s.ph)) * amp * .5;
        const resp = Math.sin(performance.now() * .0016) * .0025 * (1 - a * .8);
        P.y += resp; Rr.x += resp * 2;
        if (s.aire) { P.y += .012; Rr.x -= .04; }
        Rr.y += clamp(-s.swayX * .0012, -.12, .12) * (1 - a * .6);
        Rr.x += clamp(-s.swayY * .0012, -.12, .12) * (1 - a * .6);
        P.x += clamp(-s.swayX * .00025, -.02, .02);

        let t = this.tEst, magY = 0, manoY = 0, manoZ = 0, palanca = 0;
        if (this.estado === 'draw') {
            const e = easeOutBack(fase(t, 0, .55));
            P.y -= (1 - e) * .32; Rr.x -= (1 - e) * 1.1; Rr.z += (1 - e) * .4;
            if (t > .55) this._est('idle');
        } else if (this.estado === 'reload') {
            const tin = smooth(fase(t, 0, .3)) * (1 - smooth(fase(t, 1.6, 1.95)));
            Rr.z += tin * .55; Rr.x += tin * .22; Rr.y -= tin * .2; P.y -= tin * .03; P.x -= tin * .03;
            const sale = smooth(fase(t, .3, .55)), entra = smooth(fase(t, .85, 1.2));
            magY = t < .85 ? -sale * .35 : -(1 - entra) * .35;
            manoY = (t < .55 ? -sale : t < .85 ? -1 : -(1 - entra)) * .22;
            manoZ = (t < .85 ? sale : 1 - entra) * .22;
            if (t > .3 && this._rq === 0) { this._rq = 1; }
            if (t > 1.2 && this._rq === 1) { this._rq = 2; this.mag = this.cap; this.rot.impulso(-2.2, 0, .6); this.sfx?.reloadIn(); }
            palanca = smooth(fase(t, 1.38, 1.48)) * (1 - smooth(fase(t, 1.5, 1.58)));
            if (t > 1.5 && this._rq === 2) { this._rq = 3; this.rot.impulso(1.5, 0, -.4); this.sfx?.rack(); }
            if (t > 1.95) this._est('idle');
        } else if (this.estado === 'inspect') {
            const k = smooth(fase(t, 0, .5)) * (1 - smooth(fase(t, 2.1, 2.6)));
            Rr.y -= k * .9; Rr.z += k * .45; Rr.x += k * .15 + Math.sin(t * 2) * k * .05; P.x -= k * .05; P.y += k * .02;
            if (t > 2.6) this._est('idle');
        }
        if (!s.vivo) { P.y -= .35; Rr.x -= .9; }

        this.pos.tick(dt, P); this.rot.tick(dt, Rr);
        this.raiz.position.copy(this.pos.x);
        this.raiz.rotation.set(this.rot.x.x, this.rot.x.y, this.rot.x.z);
        this.cargador.position.y = magY; this.cargador.visible = magY > -.33;
        this.manoI.position.set(this.manoIBase.x, this.manoIBase.y + manoY, this.manoIBase.z + manoZ);
        this.palanca.position.z = -.1 + palanca * .06;
        this.celda.scale.y = Math.max(.02, this.mag / this.cap);
        this.matEmis.emissiveIntensity = 1.6 + this.calor * 2.5 + (this.mag <= 5 ? Math.sin(performance.now() * .02) * .8 : 0);
        this.bobinas.forEach((b, i) => b.rotation.z += dt * (2 + this.calor * 14) * (i % 2 ? 1 : -1));
        this.cam.fov = lerp(56, 46, a); this.cam.updateProjectionMatrix();
        // Fogonazo + luz
        this.flashT -= dt; if (this.flashT <= 0) this.flash.visible = false;
        this.luz.intensity = Math.max(0, this.luz.intensity - dt * 70);
        this.boca.getWorldPosition(this.luz.position);
        for (let i = this.casquillos.length - 1; i >= 0; i--) {
            const c = this.casquillos[i], u = c.userData;
            u.v.y -= 6 * dt; c.position.addScaledVector(u.v, dt);
            c.rotation.x += u.w.x * dt; c.rotation.y += u.w.y * dt;
            if ((u.vida -= dt) <= 0) { this.cam.remove(c); this.casquillos.splice(i, 1); }
        }
    }
    tintar(color, intensidad = .9) { this.hemi.color.set(color); this.hemi.intensity = intensidad; }
    resize(asp) { this.cam.aspect = asp; this.cam.updateProjectionMatrix(); }
}
