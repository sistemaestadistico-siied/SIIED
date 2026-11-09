/* HUD: mira dinámica según dispersión, munición y recarga del viewmodel,
 * hitmarkers, arcos de daño direccionales, brújula, marcadores 3D
 * proyectados, killfeed, marcador y FPS. */
import * as THREE from 'three';

const $ = id => document.getElementById(id);
const _v = new THREE.Vector3();
const RUMBO = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'];

export class HUD {
    constructor(e) {
        this.e = e;
        this.marcas = [];                       // [{x,y,z,icon,color,txt}]
        this._mPool = [];
        for (let i = 0; i < 12; i++) {
            const d = document.createElement('div');
            d.className = 'wmark';
            d.innerHTML = '<div class="wi">◈</div><div class="wt"></div><div class="wd"></div>';
            $('wmarks').appendChild(d);
            this._mPool.push(d);
        }
        this._arcPool = [];
        for (let i = 0; i < 6; i++) {
            const d = document.createElement('div');
            d.className = 'darc';
            $('darcs').appendChild(d);
            this._arcPool.push(d);
        }
        this._arcIdx = 0;
        this._hp = 100;
    }

    hp(v) {
        const pct = Math.max(0, Math.round(v));
        this._hp = pct;
        $('hpfill').style.width = pct + '%';
        $('hpfill').style.background = pct > 50 ? 'linear-gradient(90deg,#2B7D59,#46d98b)'
            : pct > 25 ? 'linear-gradient(90deg,#a06a1c,#e8a83c)'
            : 'linear-gradient(90deg,#8f1f1f,#e84c3c)';
        $('hpnum').innerHTML = pct < 30 && pct > 0
            ? `<span class="low">⚠ INTEGRIDAD ${pct}%</span><span class="low">CRÍTICO</span>`
            : `<span>INTEGRIDAD ${pct}%</span><span>DT-7</span>`;
        $('vign').classList.toggle('low', pct < 30 && pct > 0);
    }
    obj(t) { $('objtext').textContent = t; }
    score(v) { $('score').textContent = 'PUNTOS ' + String(v).padStart(6, '0'); }

    msg(t) {
        const d = document.createElement('div');
        d.textContent = t;
        $('feed').prepend(d);
        while ($('feed').children.length > 4) $('feed').lastChild.remove();
        setTimeout(() => d.remove(), 6000);
    }
    kill(titular, victima, cabeza = false) {
        const d = document.createElement('div');
        if (cabeza) d.className = 'hs';
        d.innerHTML = `<b>${titular}</b> ▸ ${victima}${cabeza ? ' ◎' : ''}`;
        $('kfeed').prepend(d);
        while ($('kfeed').children.length > 5) $('kfeed').lastChild.remove();
        setTimeout(() => d.remove(), 5200);
    }
    bandera(t, sub = '') {
        const b = $('bandera');
        b.innerHTML = `<div class="bt">${t}</div>${sub ? `<div class="bs">${sub}</div>` : ''}`;
        b.classList.remove('show'); void b.offsetWidth; b.classList.add('show');
    }
    hitmark(cabeza = false, mato = false) {
        const h = $('hitm');
        h.className = (mato ? 'kill' : cabeza ? 'head' : '') + ' show';
    }
    /* Arco de daño desde una posición del mundo */
    danio(desde) {
        const e = this.e, j = e.jugador;
        let ang = 0;
        if (desde) {
            const dx = desde.x - j.pos.x, dz = desde.z - j.pos.z;
            ang = Math.atan2(dx, -dz) - j.yaw;          // 0 = frente
        }
        const d = this._arcPool[this._arcIdx++ % this._arcPool.length];
        d.style.background = `conic-gradient(from ${(ang * 180 / Math.PI - 22 + 360) % 360}deg, rgba(232,76,60,.8) 0deg, transparent 44deg)`;
        d.classList.add('on');
        setTimeout(() => d.classList.remove('on'), 650);
        $('vign').classList.add('dmg');
        setTimeout(() => $('vign').classList.remove('dmg'), 320);
    }
    setMarcas(lista) { this.marcas = lista || []; }

    /* Llamado cada frame */
    tick(dt) {
        const e = this.e, j = e.jugador, vm = e.vm;
        // — Mira: separación = dispersión real proyectada a píxeles
        const fovV = THREE.MathUtils.degToRad(e.camera.fov);
        const px = Math.tan(e.spread) * (innerHeight / 2) / Math.tan(fovV / 2);
        $('cross').style.setProperty('--gap', Math.round(Math.min(56, px) + 4) + 'px');
        $('cross').classList.toggle('ads', j.aim);
        $('cross').classList.toggle('sprint', j.corriendo);
        // — Munición
        if (vm) {
            const rec = vm.estado === 'reload';
            $('magnum').innerHTML = rec ? '—' : `${vm.mag}<small>/${vm.cap}</small>`;
            $('magnum').classList.toggle('vacio', !rec && vm.mag === 0);
            $('magfill').style.width = rec ? `${Math.min(100, vm.tEst / 1.95 * 100)}%` : `${vm.mag / vm.cap * 100}%`;
            $('magfill').style.background = rec ? 'linear-gradient(90deg,#a06a1c,#ffd98a)' : '';
            $('maghint').textContent = rec ? 'RECARGANDO…' : vm.mag === 0 ? '[R] RECARGAR' : vm.mag <= 5 ? 'MUNICIÓN BAJA' : '';
            $('maghint').classList.toggle('on', rec || vm.mag <= 5);
        }
        // — FPS
        $('fps').textContent = Math.round(e.fps || 60) + ' FPS';
        // — Brújula
        this._brujula();
        // — Marcadores 3D
        this._marcas();
    }

    _brujula() {
        const c = $('compass'), g = c.getContext('2d');
        const w = c.width, h = c.height, cx = w / 2;
        g.clearRect(0, 0, w, h);
        g.fillStyle = 'rgba(4,18,30,.55)';
        g.beginPath(); g.roundRect(0, 0, w, h, 10); g.fill();
        const yawDeg = -this.e.jugador.yaw * 180 / Math.PI;   // -z = N
        const pxDeg = w / 140;                              // ±70° visibles
        g.textAlign = 'center'; g.textBaseline = 'middle';
        for (let a = -180; a < 180; a += 15) {
            let off = a - ((yawDeg + 180) % 360) + 180;
            off = ((off % 360) + 360) % 360 - 180;
            const x = cx + off * pxDeg;
            if (x < 8 || x > w - 8) continue;
            const card = a % 45 === 0;
            g.strokeStyle = card ? 'rgba(140,232,255,.8)' : 'rgba(140,232,255,.3)';
            g.beginPath(); g.moveTo(x, card ? h - 12 : h - 7); g.lineTo(x, h - 2); g.stroke();
            if (a % 45 === 0) {
                const card4 = a % 90 === 0;
                g.font = `${card4 ? '700' : '500'} ${card4 ? 10 : 8}px Orbitron`;
                g.fillStyle = card4 ? '#46d98b' : '#7c9cb8';
                g.fillText(RUMBO[((a % 360 + 360) % 360) / 45], x, 6);
            }
        }
        g.fillStyle = '#ffd98a';
        g.beginPath(); g.moveTo(cx - 5, 0); g.lineTo(cx + 5, 0); g.lineTo(cx, 6); g.fill();
    }

    _marcas() {
        const e = this.e, w = innerWidth, h = innerHeight;
        for (let i = 0; i < this._mPool.length; i++) {
            const el = this._mPool[i], m = this.marcas[i];
            if (!m) { el.style.display = 'none'; continue; }
            _v.set(m.x, (m.y ?? 1), m.z).project(e.camera);
            const detras = _v.z > 1;
            let x = (_v.x * .5 + .5) * w, y = (-_v.y * .5 + .5) * h;
            if (detras) { x = w - x; y = h * .9; }
            x = THREE.MathUtils.clamp(x, 30, w - 30); y = THREE.MathUtils.clamp(y, 30, h - 60);
            el.style.display = 'block';
            el.style.left = x + 'px'; el.style.top = y + 'px';
            el.style.color = m.color || '#46d98b';
            el.children[0].textContent = detras ? '➤' : (m.icon || '◈');
            el.children[1].textContent = m.txt || '';
            const d = Math.hypot(m.x - e.jugador.pos.x, m.z - e.jugador.pos.z);
            el.children[2].textContent = detras ? '' : Math.round(d) + ' m';
        }
    }
}
