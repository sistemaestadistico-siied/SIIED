/* Mapas de misión. Cada builder rellena el engine (geometría, luces,
 * colisiones, waypoints) y devuelve spec: {spawn, yaw, bounds, wps,
 * tick?} — el tick maneja el decorado ambiental. */
import * as THREE from 'three';
import { lambert, basic, sprite } from './engine.js';

const G = THREE.BoxGeometry;
const cyl = (r1, r2, h, n = 10) => new THREE.CylinderGeometry(r1, r2, h, n);

/* =============== helpers de decorado (portados) =============== */

function casita(e, x, z, ry = 0) {
    const mats = [0xcbd5e1, 0xf1d5a8, 0xd8a48f, 0xb7c4d6, 0xe8e0d0];
    const tejs = [0x9a3412, 0x475569, 0x7f1d1d];
    const w = 2.5 + Math.random() * 1.3, h = 2.0 + Math.random() * 1.0;
    const g = new THREE.Group();
    const cuerpo = new THREE.Mesh(new G(w, h, w * .9),
        lambert(mats[(Math.random() * mats.length) | 0]));
    cuerpo.position.y = h / 2; cuerpo.castShadow = true; g.add(cuerpo);
    const techo = new THREE.Mesh(new THREE.ConeGeometry(w * .75, .7, 4),
        lambert(tejs[(Math.random() * tejs.length) | 0]));
    techo.position.y = h + .32; techo.rotation.y = Math.PI / 4; g.add(techo);
    const v = new THREE.Mesh(new G(.78, .62, .05),
        basic([0xffc977, 0xffd98a, 0xbfd9ff][(Math.random() * 3) | 0]));
    v.position.set(w * .18, h * .55, w * .45 + .03); g.add(v);
    if (Math.random() < .45) { const v2 = v.clone(); v2.position.x = -w * .22; g.add(v2); }
    g.position.set(x, 0, z); g.rotation.y = ry;
    e.add(g);
    // Colisión AABB en el marco del propio grupo (soporta rotación 90°)
    const cx = Math.abs(Math.cos(ry)) > .7 ? w : w * .9;
    const cz = Math.abs(Math.cos(ry)) > .7 ? w * .9 : w;
    e.solido(x, h / 2, z, cx, h, cz, null);
    return { w, h };
}

function farol(e, x, z) {
    const g = new THREE.Group();
    const poste = new THREE.Mesh(cyl(.06, .09, 3.3, 6), lambert(0x5b6d7c));
    poste.position.y = 1.65; g.add(poste);
    const bombilla = new THREE.Mesh(new THREE.SphereGeometry(.2, 8, 8), basic(0xffd98a));
    bombilla.position.y = 3.4; g.add(bombilla);
    const luz = new THREE.PointLight(0xffd98a, 4, 9, 1.8); luz.position.y = 3.2; g.add(luz);
    g.position.set(x, 0, z); e.add(g);
    e.solido(x, 1.65, z, .3, 3.3, .3, null);
}

function avenida(e, x, z, largo, horizontal) {
    const v = new THREE.Mesh(new THREE.PlaneGeometry(horizontal ? largo : 2.4, horizontal ? 2.4 : largo),
        lambert(0x232a30));
    v.rotation.x = -Math.PI / 2; v.position.set(x, .015, z); e.add(v);
    const raya = basic(0xe8d9a0);
    const n = Math.floor(largo / 2.6);
    for (let i = 0; i < n; i++) {
        const r = new THREE.Mesh(new THREE.PlaneGeometry(horizontal ? 1.1 : .13, horizontal ? .13 : 1.1), raya);
        r.rotation.x = -Math.PI / 2;
        const t = (i - (n - 1) / 2) * 2.6;
        r.position.set(horizontal ? x + t : x, .03, horizontal ? z : z + t);
        e.add(r);
    }
}

function cerro(e, x, z, r, h, mat) {
    const c = new THREE.Mesh(new THREE.ConeGeometry(r, h, 7), mat);
    c.position.set(x, h / 2, z);
    e.add(c);
}

function arbol(e, x, z, s = 1) {
    const g = new THREE.Group();
    const t = new THREE.Mesh(cyl(.18, .28, 3 * s, 7), lambert(0x5a3d2b));
    t.position.y = 1.5 * s; t.castShadow = true; g.add(t);
    const copa = new THREE.Mesh(new THREE.SphereGeometry(1.5 * s, 9, 7), lambert(0x1f6b2f));
    copa.position.y = 3.3 * s; copa.scale.y = .85; copa.castShadow = true; g.add(copa);
    g.position.set(x, 0, z); e.add(g);
    e.solido(x, 1.5 * s, z, .5 * s, 3 * s, .5 * s, null);
}

function nube(e, x, y, z, s = 1) {
    const g = new THREE.Group();
    const mat = new THREE.MeshLambertMaterial({ color: 0xb8c8d8, transparent: true, opacity: .8 });
    for (const [dx, dy, r] of [[0, 0, 1.4], [1.3, .2, 1], [-1.2, .15, .9], [.4, .7, .8]]) {
        const p = new THREE.Mesh(new THREE.SphereGeometry(r, 9, 7), mat);
        p.position.set(dx, dy, 0); g.add(p);
    }
    g.scale.setScalar(s); g.position.set(x, y, z);
    e.add(g);
    return g;
}

function iglesia(e, x, z, s = 1) {
    const g = new THREE.Group();
    const nave = new THREE.Mesh(new G(4, 6, 6), lambert(0xe8d4a0));
    nave.position.y = 3; nave.castShadow = true; g.add(nave);
    const techo = new THREE.Mesh(new THREE.ConeGeometry(3.5, 2, 4), lambert(0x8b4513));
    techo.rotation.y = Math.PI / 4; techo.position.y = 7; g.add(techo);
    const torre = new THREE.Mesh(new G(1.5, 8, 1.5), lambert(0xd4c4a0));
    torre.position.set(0, 4, -3.5); g.add(torre);
    const cv = new THREE.Mesh(new G(.2, 2, .2), basic(0xffffff));
    cv.position.set(0, 9, -3.5); g.add(cv);
    const ch = new THREE.Mesh(new G(1, .2, .2), basic(0xffffff));
    ch.position.set(0, 9.3, -3.5); g.add(ch);
    const puerta = new THREE.Mesh(new G(.9, 1.6, .1), basic(0xffd98a));
    puerta.position.set(0, .8, 3.01); g.add(puerta);
    g.scale.setScalar(s); g.position.set(x, 0, z); e.add(g);
    e.solido(x, 3 * s, z, 4 * s, 6 * s, 7.5 * s, null);
    e.solido(x, 4 * s, z - 3.5 * s, 1.5 * s, 8 * s, 1.5 * s, null);
}

function estadio(e, x, z, s = 1) {
    const g = new THREE.Group();
    const cuerpo = new THREE.Mesh(new THREE.CylinderGeometry(10, 11, 7, 18, 1, true, 0, Math.PI * 1.7),
        lambert(0x9aa7b5, { side: THREE.DoubleSide }));
    cuerpo.position.y = 3.5; g.add(cuerpo);
    const campo = new THREE.Mesh(new THREE.CylinderGeometry(8, 8, .2, 18), lambert(0x1d6b2f));
    campo.position.y = .1; g.add(campo);
    for (const [tx, tz] of [[10, 10], [-10, 10], [-10, -10]]) {
        const t = new THREE.Mesh(cyl(.3, .4, 12, 6), lambert(0x77808c));
        t.position.set(tx, 6, tz); g.add(t);
        const l = new THREE.Mesh(new G(1, .5, 1), basic(0xffffaa));
        l.position.set(tx, 12.2, tz); g.add(l);
    }
    g.scale.setScalar(s); g.position.set(x, 0, z); e.add(g);
    e.solido(x, 3.5 * s, z, 21 * s, 7 * s, 21 * s, null);   // bloquea entrada
}

function fuente(e, x, z, s = 1) {
    const g = new THREE.Group();
    const base = new THREE.Mesh(cyl(2, 2.5, .5, 10), lambert(0x9aa7b5));
    base.position.y = .25; g.add(base);
    const agua = new THREE.Mesh(cyl(1.8, 1.8, .6, 10), basic(0x3fc8f0, { transparent: true, opacity: .8 }));
    agua.position.y = .75; g.add(agua);
    const pilar = new THREE.Mesh(cyl(.28, .28, 2, 8), lambert(0x8a97a5));
    pilar.position.y = 1.5; g.add(pilar);
    g.scale.setScalar(s); g.position.set(x, 0, z); e.add(g);
    e.solido(x, .8 * s, z, 4.6 * s, 1.6 * s, 4.6 * s, null);
    return agua;
}

function parque(e, x, z, s = 1) {
    const c = new THREE.Mesh(new G(12, .1, 12), lambert(0x226b2f));
    c.position.set(x, .05, z); e.add(c);
    for (const [ax, az] of [[-4, -4], [4, -4], [-4, 4], [4, 4], [0, 0]])
        arbol(e, x + ax * s, z + az * s, .8 * s);
}

function mall(e, x, z, s = 1) {
    const ed = new THREE.Mesh(new G(8, 6, 10), lambert(0xcbd5e1));
    ed.position.set(x, 3 * s, z); ed.castShadow = true; e.add(ed);
    const letrero = new THREE.Mesh(new G(6, 1, .2), basic(0xff7b2b));
    letrero.position.set(x, 6.5 * s, z + 5.1 * s); e.add(letrero);
    e.solido(x, 3 * s, z, 8 * s, 6 * s, 10 * s, null);
}

function bomberos(e, x, z, s = 1) {
    const ed = new THREE.Mesh(new G(5, 5, 4), lambert(0xb03a2e));
    ed.position.set(x, 2.5 * s, z); ed.castShadow = true; e.add(ed);
    const puerta = new THREE.Mesh(new G(2.5, 3, .1), basic(0xf5f5f5));
    puerta.position.set(x, 1.5 * s, z + 2.05 * s); e.add(puerta);
    e.solido(x, 2.5 * s, z, 5 * s, 5 * s, 4 * s, null);
}

/* Partículas ambientales flotantes (polvo de datos) */
function polvo(e, half, color = 0x46d98b, n = 300, alto = 12) {
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
        pos[i * 3] = (Math.random() - .5) * half * 2;
        pos[i * 3 + 1] = Math.random() * alto;
        pos[i * 3 + 2] = (Math.random() - .5) * half * 2;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const pts = new THREE.Points(g, new THREE.PointsMaterial({
        color, size: .07, transparent: true, opacity: .55, depthWrite: false }));
    pts.frustumCulled = false;
    e.add(pts);
    return pts;
}

/* Farola de spawn (referencia de origen) */
function pad(e, x, z, color) {
    const suelo = new THREE.Mesh(new THREE.CylinderGeometry(3.4, 3.4, .05, 32),
        basic(color, { transparent: true, opacity: .14 }));
    suelo.position.set(x, .03, z); e.add(suelo);
    const aro = new THREE.Mesh(new THREE.TorusGeometry(3.4, .07, 8, 40), basic(color));
    aro.rotation.x = Math.PI / 2; aro.position.set(x, .05, z); e.add(aro);
}

/* ============================================================
 * MAPA 1 — ARENA DE DATOS (la arena de prueba, conservada)
 * ============================================================ */
export function buildArena(e) {
    const H = 22;
    e.scene.background = new THREE.Color(0x0a1622);
    e.scene.fog = new THREE.Fog(0x0a1622, 30, 90);
    e.bounds = { minX: -H, maxX: H, minZ: -H, maxZ: H };

    e.add(new THREE.HemisphereLight(0x8fb8d8, 0x0c1a28, 1.1));
    const sol = new THREE.DirectionalLight(0xffffff, 1.4);
    sol.position.set(20, 35, 15); sol.castShadow = true;
    sol.shadow.mapSize.setScalar(2048);
    sol.shadow.camera.left = sol.shadow.camera.bottom = -30;
    sol.shadow.camera.right = sol.shadow.camera.top = 30;
    e.add(sol);
    const lv = new THREE.PointLight(0x2Bd98b, 70, 55, 1.8); lv.position.set(-18, 7, 0); e.add(lv);
    const lm = new THREE.PointLight(0xa05cff, 70, 55, 1.8); lm.position.set(18, 7, 0); e.add(lm);

    const floor = new THREE.Mesh(new THREE.PlaneGeometry(H * 2, H * 2),
        new THREE.MeshStandardMaterial({ color: 0x0f2a40, roughness: .85 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; e.add(floor);
    const grid = new THREE.GridHelper(H * 2, 22, 0x2b6a8f, 0x18486a);
    grid.position.y = .012; e.add(grid);

    const wallMat = new THREE.MeshStandardMaterial({ color: 0x123a58, roughness: .7 });
    const covMat = new THREE.MeshStandardMaterial({ color: 0x1b4d6e, roughness: .5,
        emissive: 0x0d3352, emissiveIntensity: .6 });
    const B = [
        [0, 2, -H, 2 * H + 2, 4, 1], [0, 2, H, 2 * H + 2, 4, 1],
        [-H, 2, 0, 1, 4, 2 * H + 2], [H, 2, 0, 1, 4, 2 * H + 2],
        [0, 1.5, 0, 4, 3, 4], [-8, 1, -8, 5, 2, 5], [8, 1, 8, 5, 2, 5],
        [8, 1, -8, 4, 2, 4], [-8, 1, 8, 4, 2, 4],
        [0, 1, -14, 12, 2, 2], [0, 1, 14, 12, 2, 2],
        [-14, 1, 0, 2, 2, 12], [14, 1, 0, 2, 2, 12],
        [-14, 2.5, -14, 2, 5, 2], [14, 2.5, 14, 2, 5, 2],
        [14, 2.5, -14, 2, 5, 2], [-14, 2.5, 14, 2, 5, 2],
    ];
    B.forEach((b, i) => e.solido(...b, i < 4 ? wallMat : covMat,
        i < 4 ? {} : { edges: 0x46d98b }));

    pad(e, -18, 0, 0x46d98b);
    polvo(e, H, 0x46d98b, 320, 12);

    const wps = [[-18, -12], [-18, 12], [18, -12], [18, 12], [0, -18], [0, 18],
        [-6, -18], [6, -18], [-6, 18], [6, 18], [-18, 0], [18, 0],
        [0, -6], [0, 6], [-6, 0], [6, 0], [-12, -5], [-12, 5], [12, -5], [12, 5]];
    return {
        spawn: [-18, 0, 0], yaw: -Math.PI / 2, wps,
        zonasSpawn: { verde: [[-18, -4], [-18, 0], [-18, 4]], morado: [[18, 4], [18, 0], [18, -4]] },
    };
}

/* ============================================================
 * MAPA 2 — BARRIO SIIED (noche, portado de presentacion.html)
 * ============================================================ */
export function buildBarrio(e) {
    e.scene.background = new THREE.Color(0x0b1626);
    e.scene.fog = new THREE.Fog(0x0b1626, 45, 130);
    e.bounds = { minX: -34, maxX: 34, minZ: -26, maxZ: 26 };

    // Noche: luna azulada + hemisférica + relleno
    e.add(new THREE.AmbientLight(0xdce9f7, .32));
    e.add(new THREE.HemisphereLight(0x9db8d8, 0x1f2c3a, .5));
    const lunaLuz = new THREE.DirectionalLight(0xcfe0ff, 1.15);
    lunaLuz.position.set(-45, 42, -60); lunaLuz.castShadow = true;
    lunaLuz.shadow.mapSize.setScalar(2048);
    lunaLuz.shadow.camera.left = lunaLuz.shadow.camera.bottom = -45;
    lunaLuz.shadow.camera.right = lunaLuz.shadow.camera.top = 45;
    e.add(lunaLuz);
    const rim = new THREE.DirectionalLight(0xffb37a, .2);
    rim.position.set(55, 10, 40); e.add(rim);

    // Luna + halo + nubes
    const luna = new THREE.Mesh(new THREE.SphereGeometry(4.6, 20, 14), basic(0xf4f8ff));
    luna.position.set(-60, 38, -85); e.add(luna);
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({
        map: (() => { const c = document.createElement('canvas'); c.width = c.height = 128;
            const g = c.getContext('2d'), gr = g.createRadialGradient(64, 64, 10, 64, 64, 64);
            gr.addColorStop(0, 'rgba(200,225,255,.5)'); gr.addColorStop(1, 'rgba(200,225,255,0)');
            g.fillStyle = gr; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c); })(),
        transparent: true, depthWrite: false }));
    halo.scale.setScalar(28); halo.position.copy(luna.position); e.add(halo);
    const nubes = [
        nube(e, -55, 37, -80, 2.4), nube(e, 30, 42, -90, 3), nube(e, 60, 35, -60, 2),
    ];

    // Suelo verde oscuro
    const suelo = new THREE.Mesh(new THREE.PlaneGeometry(160, 120), lambert(0x18281c));
    suelo.rotation.x = -Math.PI / 2; suelo.receiveShadow = true; e.add(suelo);

    // Río perimetral cian luminoso (decorado, fuera de bounds)
    const matRio = basic(0x0dc4d8);
    for (const [rx, rz, rw, rl] of [[0, -29.5, 120, 4], [0, 29.5, 120, 4], [37.5, 0, 4, 60], [-37.5, 0, 4, 60]]) {
        const rio = new THREE.Mesh(new THREE.PlaneGeometry(rw, rl), matRio);
        rio.rotation.x = -Math.PI / 2; rio.position.set(rx, -.01, rz); e.add(rio);
    }

    // Anillo de cerros y monumentos (oeste, como en Cali)
    const montanaMat = lambert(0x4a6741, { flatShading: true });
    for (let x = -80; x <= 80; x += 13) {
        cerro(e, x + Math.sin(x) * 2.5, -44 - (Math.abs(x) % 11), 7 + (Math.abs(x) % 4), 9 + ((x * 7) % 12 + 12) % 12, montanaMat);
        cerro(e, x - Math.sin(x * 1.3) * 2.5, 44 + (Math.abs(x) % 11), 7 + (Math.abs(x) % 4), 9 + ((x * 7) % 12 + 12) % 12, montanaMat);
    }
    for (let z = -38; z <= 38; z += 12) {
        cerro(e, -55 - (Math.abs(z) % 8), z, 7, 10 + (Math.abs(z) % 8), montanaMat);
        cerro(e, 55 + (Math.abs(z) % 8), z, 7, 10 + (Math.abs(z) % 8), montanaMat);
    }
    // Tres Cruces (oeste) + Cristo Rey (suroeste) con sus reflectores
    const blanco = lambert(0xf5f5f5, { emissive: 0x6a7683 });
    cerro(e, -52, 8, 10, 20, montanaMat);
    for (const oz of [-2.6, 0, 2.6]) {
        const pv = new THREE.Mesh(new G(.4, 3.4, .4), blanco);
        pv.position.set(-52, 22, 8 + oz); e.add(pv);
        const ph = new THREE.Mesh(new G(.4, .4, 1.7), blanco);
        ph.position.set(-52, 22.7, 8 + oz); e.add(ph);
    }
    const reflector = new THREE.PointLight(0x7cd8ff, 55, 50, 1.6);
    reflector.position.set(-46, 22, 8); e.add(reflector);
    cerro(e, -56, -40, 12, 24, montanaMat);
    const ped = new THREE.Mesh(cyl(1.3, 1.9, 4, 8), lambert(0xa0a0a0, { emissive: 0x3a4149 }));
    ped.position.set(-56, 26, -40); e.add(ped);
    const tun = new THREE.Mesh(cyl(.9, 1.3, 5.5, 8), blanco);
    tun.position.set(-56, 30.5, -40); e.add(tun);
    const cab = new THREE.Mesh(new THREE.SphereGeometry(.65, 8, 8), blanco);
    cab.position.set(-56, 34, -40); e.add(cab);
    for (const sx of [-1, 1]) {
        const b = new THREE.Mesh(new G(3.2, .55, .55), blanco);
        b.position.set(-56 + sx * 1.7, 32.4, -40); b.rotation.z = sx * .22; e.add(b);
    }
    const ref2 = new THREE.PointLight(0xffd98a, 45, 45, 1.6);
    ref2.position.set(-50, 30, -38); e.add(ref2);

    // Avenidas: rectángulo perimetral + cruz central
    avenida(e, 0, -20, 60, true); avenida(e, 0, 20, 60, true);
    avenida(e, -30, 0, 40, false); avenida(e, 30, 0, 40, false);
    avenida(e, 0, -11, 60, true);                 // calle secundaria N
    avenida(e, -15, 0, 40, false);                // calle secundaria O
    // Plaza central (kiosco SIIED)
    const plaza = new THREE.Mesh(new THREE.CylinderGeometry(6, 6, .1, 24), lambert(0x35404a));
    plaza.position.set(0, .05, 0); e.add(plaza);
    fuente(e, 0, 0, .9);

    // Casitas por cuadrantes (hileras con huecos)
    const filas = [
        { z: -16.5, ry: 0 }, { z: -13.5, ry: Math.PI }, { z: -7, ry: 0 },
        { z: 6.5, ry: Math.PI }, { z: 10, ry: 0 }, { z: 15.5, ry: Math.PI },
    ];
    for (const f of filas) {
        for (let x = -27; x <= 27; x += 4.4) {
            if (Math.abs(x) < 7 || Math.abs(x + 15) < 2.6 || Math.abs(x - 30) < 2.6 || Math.abs(x + 30) < 2.6) continue;
            if (Math.random() < .22) continue;
            casita(e, x + Math.sin(f.z * 1.9 + x) * .3, f.z, f.ry);
        }
    }
    // Landmarks
    iglesia(e, -24, 16.8, .75);
    estadio(e, 21, -15, .55);
    parque(e, -22, -7, .8);
    mall(e, 22, 15.8, .65);
    bomberos(e, -24, 7, .8);
    // Faroles sobre las avenidas
    for (let x = -27; x <= 27; x += 9) { farol(e, x, -18.6); farol(e, x, 18.6); farol(e, x, -9.4); }
    for (let z = -16; z <= 16; z += 10.5) { farol(e, -28.6, z); farol(e, 28.6, z); farol(e, -13.6, z); }

    // Autos ambientales: puntos de luz recorriendo la avenida
    const autos = [];
    const SEGS = [[-30, -20], [30, -20], [30, 20], [-30, 20]];
    const autoMat = basic(0xffe9b0);
    for (let i = 0; i < 7; i++) {
        const a = new THREE.Mesh(new G(.5, .3, .9), autoMat);
        const luz = new THREE.PointLight(0xffe9b0, 3, 5); luz.position.y = .5; a.add(luz);
        a.userData.s = Math.random();
        e.add(a); autos.push(a);
    }
    const posEnVia = (s, out) => {
        const lados = 4, sN = s * lados, i = Math.floor(sN) % lados, u = sN - Math.floor(sN);
        const [ax, az] = SEGS[i], [bx, bz] = SEGS[(i + 1) % 4];
        out.set(ax + (bx - ax) * u, .35, az + (bz - az) * u);
    };
    const _a = new THREE.Vector3();

    // Partículas nocturnas + waypoints en las calles
    polvo(e, 33, 0x7cd8ff, 260, 10);
    const wps = [];
    for (let x = -28; x <= 28; x += 7) { wps.push([x, -20], [x, 20], [x, -11]); }
    for (let z = -17; z <= 17; z += 7) { wps.push([-30, z], [30, z], [-15, z]); }

    return {
        spawn: [0, 0, 23], yaw: 0, wps,
        zonaKiosco: [0, 0],
        puntosPickup: [
            [-8, -14], [-12, -16], [8, -13], [12, -16.5], [24, -11], [-19, -12],
            [10, 4], [-10, 7], [16, 9], [-18, 13], [5, 14], [26, 17],
            [-5, 18], [14, 16.5],
        ],
        tick(dt, t) {
            for (const a of autos) {
                a.userData.s = (a.userData.s + dt * .012) % 1;
                posEnVia(a.userData.s, _a); a.position.copy(_a);
                posEnVia(a.userData.s + .001, _a); a.lookAt(_a);
            }
            nubes.forEach((n, i) => { n.position.x += dt * (.25 + i * .1); if (n.position.x > 90) n.position.x = -95; });
            reflector.color.setHSL((t * .05) % 1, .7, .6);
            ref2.color.setHSL((t * .05 + .5) % 1, .7, .6);
        },
    };
}

/* ============================================================
 * MAPA 3 — PARQUE DE BARRAS (atardecer, torres del subtema 3D)
 * ============================================================ */
export function buildTorres(e) {
    e.scene.background = new THREE.Color(0x1c2f4a);
    e.scene.fog = new THREE.Fog(0x2a3f5c, 40, 150);
    e.bounds = { minX: -34, maxX: 34, minZ: -28, maxZ: 28 };

    // Atardecer dorado
    e.add(new THREE.HemisphereLight(0xffd9a0, 0x1a2438, .7));
    const sol = new THREE.DirectionalLight(0xffb37a, 1.5);
    sol.position.set(-40, 18, 30); sol.castShadow = true;
    sol.shadow.mapSize.setScalar(2048);
    sol.shadow.camera.left = sol.shadow.camera.bottom = -45;
    sol.shadow.camera.right = sol.shadow.camera.top = 45;
    e.add(sol);
    const contra = new THREE.DirectionalLight(0x7cd8ff, .3);
    contra.position.set(30, 25, -40); e.add(contra);

    // Sol visible bajo en el horizonte
    const disco = new THREE.Mesh(new THREE.SphereGeometry(5, 16, 12), basic(0xffcf8a));
    disco.position.set(-70, 14, 55); e.add(disco);

    // Suelo: parque con césped y sendas
    const suelo = new THREE.Mesh(new THREE.PlaneGeometry(150, 110), lambert(0x24513a));
    suelo.rotation.x = -Math.PI / 2; suelo.receiveShadow = true; e.add(suelo);
    avenida(e, 0, 0, 70, true);
    avenida(e, 0, -14, 70, true); avenida(e, 0, 14, 70, true);
    avenida(e, -20, 0, 58, false); avenida(e, 20, 0, 58, false);

    // Torres de datos: columnas tipo barras, alturas variadas,
    // algunas escalables por escalones laterales
    const colores = [0x46d98b, 0x7cd8ff, 0xc98bff, 0xffb37a, 0xff7b9c];
    const matCol = colores.map(c => new THREE.MeshStandardMaterial({ color: c, roughness: .55,
        emissive: c, emissiveIntensity: .14 }));
    // [x, z, altura, colorIdx, ¿torre objetivo?]
    const TORRES = [
        [-24, -18, 4, 0], [-14, -20, 7, 1], [-4, -19, 11, 2, 1], [7, -19, 5, 3], [18, -19, 9, 4],
        [-26, -8, 6, 3], [-12, -7, 13, 0, 1], [0, -7, 3, 4], [12, -7, 8, 1], [25, -7, 5, 2],
        [-25, 5, 8, 4], [-12, 6, 5, 2], [1, 6, 14, 1, 1], [14, 6, 6, 0], [26, 6, 10, 3],
        [-24, 17, 5, 1], [-13, 18, 9, 4], [-2, 18, 6, 0], [10, 18, 12, 2, 1], [22, 17, 5, 3],
    ];
    const objetivos = [];
    TORRES.forEach(([x, z, h, ci, obj]) => {
        const w = 3.4;
        const torre = new THREE.Mesh(new G(w, h, w), matCol[ci]);
        torre.position.set(x, h / 2, z); torre.castShadow = torre.receiveShadow = true;
        e.add(torre);
        e.solido(x, h / 2, z, w, h, w, null);
        // Borde luminoso superior
        const borde = new THREE.LineSegments(new THREE.EdgesGeometry(torre.geometry),
            new THREE.LineBasicMaterial({ color: colores[ci], transparent: true, opacity: .5 }));
        borde.position.copy(torre.position); e.add(borde);
        if (obj) objetivos.push({ x, z, h, w, color: colores[ci] });
    });

    // Árboles del parque
    for (const [x, z] of [[-30, -2], [30, -3], [-30, 12], [30, 12], [-7, 12], [7, -12], [-30, 24], [30, 24], [0, 25]])
        arbol(e, x, z, .9 + Math.random() * .4);

    // Nubes del atardecer
    const nubes = [nube(e, -50, 30, -60, 3.4), nube(e, 20, 34, -70, 4), nube(e, 65, 28, -40, 2.6),
                   nube(e, -20, 32, 70, 3)];
    polvo(e, 34, 0xffcf8a, 300, 16);

    const wps = [];
    for (let x = -28; x <= 28; x += 8) { wps.push([x, 0], [x, -14], [x, 14]); }
    for (let z = -24; z <= 24; z += 8) { wps.push([-20, z], [20, z]); }

    return {
        spawn: [0, 0, 24], yaw: 0, wps, objetivos,
        tick(dt) { nubes.forEach((n, i) => { n.position.x += dt * (.3 + i * .08); if (n.position.x > 95) n.position.x = -95; }); },
    };
}

/* ============================================================
 * MAPA 4 — PATIO DE PILAS (día, clasificación por color)
 * ============================================================ */
export const SERIES = [
    { nombre: 'SERIE GEO', color: 0x46d98b },
    { nombre: 'SERIE SOC', color: 0xffb37a },
    { nombre: 'SERIE ECO', color: 0xc98bff },
    { nombre: 'SERIE DEM', color: 0x7cd8ff },
];

export function buildPila(e) {
    e.scene.background = new THREE.Color(0x12333f);
    e.scene.fog = new THREE.Fog(0x16404f, 40, 140);
    e.bounds = { minX: -30, maxX: 30, minZ: -26, maxZ: 26 };

    e.add(new THREE.HemisphereLight(0xcfe8f0, 0x12303a, .8));
    const sol = new THREE.DirectionalLight(0xfff4d6, 1.5);
    sol.position.set(30, 45, 20); sol.castShadow = true;
    sol.shadow.mapSize.setScalar(2048);
    sol.shadow.camera.left = sol.shadow.camera.bottom = -40;
    sol.shadow.camera.right = sol.shadow.camera.top = 40;
    e.add(sol);

    const suelo = new THREE.Mesh(new THREE.PlaneGeometry(120, 100),
        new THREE.MeshStandardMaterial({ color: 0x17455a, roughness: .85 }));
    suelo.rotation.x = -Math.PI / 2; suelo.receiveShadow = true; e.add(suelo);
    const grid = new THREE.GridHelper(60, 30, 0x2b6a8f, 0x1b4a5a);
    grid.position.y = .015; e.add(grid);

    // Muralla de cobertura media
    const covMat = new THREE.MeshStandardMaterial({ color: 0x1c4a5f, roughness: .5,
        emissive: 0x0a2a38, emissiveIntensity: .5 });
    for (const [x, z, sx, sz] of [
        [-10, -8, 10, 2], [10, -8, 10, 2], [-10, 8, 10, 2], [10, 8, 10, 2],
        [0, -16, 2, 8], [0, 16, 2, 8], [-20, 0, 2, 10], [20, 0, 2, 10],
    ]) e.solido(x, .9, z, sx, 1.8, sz, covMat, { edges: 0x7cd8ff });

    // Torres de series: una por color con slots fantasma
    const torres = [];
    SERIES.forEach((s, i) => {
        const ang = i / SERIES.length * Math.PI * 2 + Math.PI / 4;
        const x = Math.cos(ang) * 16, z = Math.sin(ang) * 16;
        const mat = new THREE.MeshStandardMaterial({ color: s.color, roughness: .5,
            emissive: s.color, emissiveIntensity: .12 });
        const base = new THREE.Mesh(new G(4, 1, 4), new THREE.MeshStandardMaterial({ color: 0x2a3d4a, roughness: .6 }));
        base.position.set(x, .5, z); base.castShadow = true; e.add(base);
        e.solido(x, .5, z, 4.4, 1, 4.4, null);
        // Etiqueta de la serie
        const et = sprite(s.nombre, '#' + s.color.toString(16).padStart(6, '0'), 30);
        et.position.set(x, 8.5, z); e.add(et);
        const haz = new THREE.Mesh(new THREE.CylinderGeometry(.2, 1.6, 18, 10, 1, true),
            basic(s.color, { transparent: true, opacity: .1, blending: THREE.AdditiveBlending,
                depthWrite: false, side: THREE.DoubleSide }));
        haz.position.set(x, 10, z); e.add(haz);
        torres.push({ serie: s, x, z, slots: [], haz });
    });

    polvo(e, 30, 0x7cd8ff, 280, 14);
    const nubes = [nube(e, -40, 26, -55, 3), nube(e, 30, 30, -60, 4), nube(e, 0, 28, 60, 3.4)];

    const wps = [];
    for (let x = -24; x <= 24; x += 8) { wps.push([x, -12], [x, 0], [x, 12]); }
    for (let z = -20; z <= 20; z += 8) { wps.push([-14, z], [14, z]); }

    return {
        spawn: [0, 0, -22], yaw: Math.PI, wps, torres,
        tick(dt) { nubes.forEach((n, i) => { n.position.x += dt * (.4 + i * .1); if (n.position.x > 90) n.position.x = -90; }); },
    };
}

export const MAPAS = {
    arena:   { nombre: 'Arena de Datos',      build: buildArena },
    barrio:  { nombre: 'Barrio SIIED',        build: buildBarrio },
    torres:  { nombre: 'Parque de Barras',    build: buildTorres },
    pila:    { nombre: 'Patio de Pilas',      build: buildPila },
};
