"""
Datico Arena — servidor WebSocket del easter egg multijugador.

Team deathmatch Don Datico: bando VERDE vs bando MORADO.
Servidor autoritativo para vida, daño y respawn; el movimiento lo
reportan los clientes (clamp a los límites del arena).

Incluye BOTS con IA (line-of-sight, strafe, navegación por waypoints)
para jugar solo o cooperativo — el cliente pide N bots al hacer join.

Uso:
    python -m datico_arena.server [--port 8765]

Protocolo JSON:

  client → server
    {"t":"join",  "name": str, "bots": int}
    {"t":"input", "p":[x,y,z], "ry":yaw, "pitch":pitch, "moving":bool}
    {"t":"shoot", "o":[x,y,z], "d":[dx,dy,dz]}          # rayo hitscan
    {"t":"ping"}

  server → client
    {"t":"welcome", "id", "team", "map", "players", "score", "names"}
    {"t":"join",   "id","name","team","p","names"}
    {"t":"leave",  "id","names"}
    {"t":"state",  "players":{id:{p,ry,hp,alive,moving}}, "score"}
    {"t":"shot",   "id","o","d","hit":id|null,"wall":[x,y,z]|null}
    {"t":"damage", "id","hp","by"}
    {"t":"kill",   "killer","victim","score","names"}
    {"t":"respawn","id","p"}
    {"t":"feed",   "msg"}                                # kill feed
    {"t":"pong"}
"""

import argparse
import asyncio
import json
import math
import random
import time

import websockets

TICK_HZ = 15
BOT_HZ = 10
RESPAWN_S = 3.0
HP_MAX = 100
DMG_DISPARO = 34
FIRE_INTERVAL = 0.18          # cadencia mínima entre disparos (humanos)
BOT_FIRE_MIN, BOT_FIRE_MAX = 0.55, 1.4    # cadencia de bots
BOT_SPREAD = 0.09           # dispersión del aim de bots (unid. dirección)
BOT_SPEED = 4.2
BOT_SIGHT = 30.0            # distancia de visión
PLAYER_RADIUS = 0.5
PLAYER_HEIGHT = 1.8
TEAMS = ('verde', 'morado')
MAX_PLAYERS = 16
ARENA_HALF = 22.0           # arena 44×44 m
MAX_Y = 10.0

# ---------------------------------------------------------------------------
# Arena: muros perimetrales + cobertura interior (cajas AABB).
# El mismo spec viaja al cliente en `welcome.map` — las paredes
# bloquean disparos en el server y movimiento/render en el cliente.
# Cada caja: [cx, cy, cz, sx, sy, sz] (centro + tamaño completo).
# ---------------------------------------------------------------------------
MAP_BOXES = [
    # Perímetro (4 muros de 4 m de alto)
    [0, 2, -ARENA_HALF, 2 * ARENA_HALF + 2, 4, 1],
    [0, 2, ARENA_HALF, 2 * ARENA_HALF + 2, 4, 1],
    [-ARENA_HALF, 2, 0, 1, 4, 2 * ARENA_HALF + 2],
    [ARENA_HALF, 2, 0, 1, 4, 2 * ARENA_HALF + 2],
    # Bloques centrales — "la plaza de datos"
    [0, 1.5, 0, 4, 3, 4],
    [-8, 1, -8, 5, 2, 5],
    [8, 1, 8, 5, 2, 5],
    [8, 1, -8, 4, 2, 4],
    [-8, 1, 8, 4, 2, 4],
    # Pasillos largos
    [0, 1, -14, 12, 2, 2],
    [0, 1, 14, 12, 2, 2],
    [-14, 1, 0, 2, 2, 12],
    [14, 1, 0, 2, 2, 12],
    # Pilares altos en las esquinas medias
    [-14, 2.5, -14, 2, 5, 2],
    [14, 2.5, 14, 2, 5, 2],
    [14, 2.5, -14, 2, 5, 2],
    [-14, 2.5, 14, 2, 5, 2],
]

SPAWNS = {
    'verde':  [[-18, 0, -4], [-18, 0, 0], [-18, 0, 4], [-16, 0, -8], [-16, 0, 8]],
    'morado': [[18, 0, 4], [18, 0, 0], [18, 0, -4], [16, 0, 8], [16, 0, -8]],
}

# Waypoints de navegación para bots (espacios abiertos entre coberturas)
WAYPOINTS = [
    [-18, 0, -12], [-18, 0, 12], [18, 0, -12], [18, 0, 12],
    [0, 0, -18], [0, 0, 18], [-6, 0, -18], [6, 0, -18],
    [-6, 0, 18], [6, 0, 18], [-18, 0, 0], [18, 0, 0],
    [0, 0, -6], [0, 0, 6], [-6, 0, 0], [6, 0, 0],
    [-12, 0, -5], [-12, 0, 5], [12, 0, -5], [12, 0, 5],
]

BOT_NAMES = [
    'Bot-DANE', 'R2-DECRETO', 'CENSO-2000', 'NORMALIZADOR',
    'IA-NORMAL', 'GeoCoder-X', 'TablaCruzada', 'P30-BOT',
    'Error404', 'UploadBot', 'NullPointer', 'CacheMiss',
]

FRASES_KILL = [
    "{k} desintegró a {v} con un rayo de datos",
    "{v} fue normalizado por {k}",
    "{k} le aplicó a {v} el decreto 1078 del caos",
    "{v} salió de la base de datos cortesía de {k}",
    "{k} publicó a {v} en el SIN... en modo offline",
    "{v} no pasó la validación de {k}",
    "{k} archivó a {v} en la papelera del DANE",
    "{v} sufrió un error 500 inducido por {k}",
]

players = {}          # id -> estado de jugador (bots: ws=None)
_next_id = 1


def _equipo_menor():
    verde = sum(1 for p in players.values() if p['team'] == 'verde')
    morado = sum(1 for p in players.values() if p['team'] == 'morado')
    return 'verde' if verde <= morado else 'morado'


def _spawn(team):
    return list(random.choice(SPAWNS[team]))


def _clamp_pos(p):
    try:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
    except (TypeError, ValueError, IndexError):
        return None
    m = ARENA_HALF - 0.6
    return [max(-m, min(m, x)), max(0.0, min(MAX_Y, y)), max(-m, min(m, z))]


def _nuevo_jugador(name, team=None, bot=False, ws=None):
    global _next_id
    pid = _next_id
    _next_id += 1
    team = team or _equipo_menor()
    p = {
        'id': pid, 'ws': ws, 'bot': bot,
        'name': str(name or f'Datico-{pid}')[:24],
        'team': team, 'p': _spawn(team),
        'ry': 0.0, 'pitch': 0.0, 'moving': False,
        'hp': HP_MAX, 'alive': True,
        'kills': 0, 'deaths': 0,
        'last_shot': 0.0,
        # estado de IA
        'wp': None, 'strafe': 1, 'strafe_t': 0.0, 'next_shot': 0.0,
    }
    players[pid] = p
    return p


# --------------------------------------------------------------------------
# Geometría de rayos
# --------------------------------------------------------------------------

def _ray_aabb(o, d, box):
    """Slab test. Devuelve t (>0) del impacto o None."""
    tmin, tmax = 0.0, float('inf')
    for i in range(3):
        lo = box[i] - box[i + 3] / 2.0
        hi = box[i] + box[i + 3] / 2.0
        di = d[i]
        if abs(di) < 1e-9:
            if o[i] < lo or o[i] > hi:
                return None
            continue
        t1 = (lo - o[i]) / di
        t2 = (hi - o[i]) / di
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1)
        tmax = min(tmax, t2)
        if tmin > tmax:
            return None
    return tmin if tmin > 0 else None


def _dist2_ray_segment(o, d, a, b):
    """Distancia² mínima entre el rayo o+t·d (t≥0) y el segmento a-b.

    Devuelve (t_ray, dist2)."""
    ab = [b[i] - a[i] for i in range(3)]
    ao = [o[i] - a[i] for i in range(3)]
    d_ab = sum(d[i] * ab[i] for i in range(3))
    ab_ab = sum(ab[i] * ab[i] for i in range(3))
    d_ao = sum(d[i] * ao[i] for i in range(3))
    ab_ao = sum(ab[i] * ao[i] for i in range(3))
    denom = ab_ab - d_ab * d_ab
    if abs(denom) < 1e-9:                     # rayo paralelo al segmento
        s = 0.0
        t = max(0.0, -d_ao)
    else:
        s = (ab_ao - d_ao * d_ab) / denom     # parámetro sobre el segmento
        s = max(0.0, min(1.0, s))
        t = s * d_ab - d_ao                   # parámetro sobre el rayo
        if t < 0:
            t = 0.0
            s = max(0.0, min(1.0, -ab_ao / ab_ab if ab_ab else 0.0))
    pr = [o[i] + d[i] * t for i in range(3)]
    ps = [a[i] + ab[i] * s for i in range(3)]
    return t, sum((pr[i] - ps[i]) ** 2 for i in range(3))


def _t_wall(o, d):
    """t del primer impacto del rayo contra el mapa (inf si ninguno)."""
    t = float('inf')
    for box in MAP_BOXES:
        tb = _ray_aabb(o, d, box)
        if tb is not None and tb < t:
            t = tb
    return t


def _los(a, b):
    """Line-of-sight entre dos puntos 3D (True si no hay muro entre medio)."""
    d = [b[i] - a[i] for i in range(3)]
    dist = math.sqrt(sum(c * c for c in d))
    if dist < 1e-6:
        return True
    d = [c / dist for c in d]
    return _t_wall(a, d) > dist


def _raycast_hit(shooter_id, o, d):
    """Devuelve (victim_id|None, t_wall, wall_point)."""
    t_w = _t_wall(o, d)
    wall_point = ([o[i] + d[i] * t_w for i in range(3)]
                  if t_w < float('inf') else None)

    victim, t_victim = None, t_w
    for p in players.values():
        if p['id'] == shooter_id or not p['alive']:
            continue
        # Cápsula vertical: de pies+0.25 a pies+PLAYER_HEIGHT
        a = [p['p'][0], p['p'][1] + 0.25, p['p'][2]]
        b = [p['p'][0], p['p'][1] + PLAYER_HEIGHT, p['p'][2]]
        t, dist2 = _dist2_ray_segment(o, d, a, b)
        if dist2 < PLAYER_RADIUS ** 2 and 0 <= t < t_victim:
            victim, t_victim = p['id'], t
    return victim, t_w, wall_point


def _collide_world(p, radius=0.45, height=1.8):
    """Empuja la posición p (list) fuera de las cajas del mapa (eje menor)."""
    for box in MAP_BOXES:
        bx, by, bz, sx, sy, sz = box
        minx, maxx = bx - sx / 2, bx + sx / 2
        miny, maxy = by - sy / 2, by + sy / 2
        minz, maxz = bz - sz / 2, bz + sz / 2
        if (p[0] + radius > minx and p[0] - radius < maxx and
                p[2] + radius > minz and p[2] - radius < maxz and
                p[1] < maxy and p[1] + height > miny):
            dx1 = (maxx + radius) - p[0]
            dx2 = p[0] - (minx - radius)
            dz1 = (maxz + radius) - p[2]
            dz2 = p[2] - (minz - radius)
            m = min(dx1, dx2, dz1, dz2)
            if m == dx1:
                p[0] = maxx + radius
            elif m == dx2:
                p[0] = minx - radius
            elif m == dz1:
                p[2] = maxz + radius
            else:
                p[2] = minz - radius


# --------------------------------------------------------------------------
# Mensajería
# --------------------------------------------------------------------------

async def _broadcast(msg):
    data = json.dumps(msg)
    for p in list(players.values()):
        ws = p['ws']
        if ws is None:
            continue
        try:
            await ws.send(data)
        except websockets.ConnectionClosed:
            pass


async def _send(ws, msg):
    try:
        await ws.send(json.dumps(msg))
    except websockets.ConnectionClosed:
        pass


async def _send_id(pid, msg):
    p = players.get(pid)
    if p and p['ws']:
        await _send(p['ws'], msg)


def _score():
    s = {'verde': 0, 'morado': 0}
    for p in players.values():
        s[p['team']] += p['kills']
    return s


def _public_player(p):
    return {'p': p['p'], 'ry': p['ry'], 'hp': p['hp'],
            'alive': p['alive'], 'moving': p['moving']}


def _names():
    return {p['id']: {'name': p['name'], 'team': p['team'],
                      'kills': p['kills'], 'deaths': p['deaths'],
                      'bot': p['bot']}
            for p in players.values()}


async def _respawn_later(pid):
    await asyncio.sleep(RESPAWN_S)
    p = players.get(pid)
    if p is None or p['alive']:
        return
    p['p'] = _spawn(p['team'])
    p['hp'] = HP_MAX
    p['alive'] = True
    p['wp'] = None
    await _broadcast({'t': 'respawn', 'id': pid, 'p': p['p']})


async def _shoot(shooter, o, d):
    now = time.monotonic()
    if now - shooter['last_shot'] < FIRE_INTERVAL or not shooter['alive']:
        return
    shooter['last_shot'] = now
    n = math.sqrt(sum(c * c for c in d)) or 1.0
    d = [c / n for c in d]

    victim, t_w, wall_pt = _raycast_hit(shooter['id'], o, d)
    vp = players.get(victim) if victim is not None else None

    # Sin fuego amigo
    if vp is None or vp['team'] == shooter['team']:
        victim = None

    await _broadcast({
        't': 'shot', 'id': shooter['id'], 'o': o, 'd': d,
        'hit': victim, 'wall': wall_pt,
    })

    if victim is None:
        return
    vp['hp'] = max(0, vp['hp'] - DMG_DISPARO)
    await _send_id(victim, {'t': 'damage', 'id': victim,
                            'hp': vp['hp'], 'by': shooter['id']})
    if vp['hp'] > 0:
        return

    vp['alive'] = False
    vp['deaths'] += 1
    shooter['kills'] += 1
    frase = random.choice(FRASES_KILL).format(
        k=shooter['name'], v=vp['name'])
    await _broadcast({
        't': 'kill', 'killer': shooter['id'], 'victim': victim,
        'score': _score(), 'names': _names(),
    })
    await _broadcast({'t': 'feed', 'msg': frase})
    asyncio.ensure_future(_respawn_later(victim))


# --------------------------------------------------------------------------
# IA de bots
# --------------------------------------------------------------------------

async def _bot_step(b, dt):
    """Un paso de IA: enemigo visible → strafe + disparo; si no,
    navegar por waypoints (priorizando acercarse al enemigo)."""
    eye = [b['p'][0], b['p'][1] + 1.5, b['p'][2]]

    # Enemigo vivo más cercano
    target, best = None, BOT_SIGHT
    for p in players.values():
        if p['team'] == b['team'] or not p['alive']:
            continue
        dx = p['p'][0] - b['p'][0]
        dz = p['p'][2] - b['p'][2]
        d = math.hypot(dx, dz)
        if d < best:
            best = d
            target = p

    now = time.monotonic()
    b['moving'] = False

    if target is not None:
        chest = [target['p'][0], target['p'][1] + 1.1, target['p'][2]]
        if _los(eye, chest):
            # Combate: mirar al objetivo, strafe perpendicular, disparar
            b['ry'] = math.atan2(-(chest[0] - eye[0]), -(chest[2] - eye[2]))
            if now > b['strafe_t']:
                b['strafe'] *= -1
                b['strafe_t'] = now + random.uniform(0.7, 1.6)
            perp = [-(chest[2] - eye[2]), 0.0, chest[0] - eye[0]]
            pl = math.hypot(perp[0], perp[2]) or 1.0
            # alejarse si está demasiado cerca, acercarse si muy lejos
            toward = 0.35 if best > 14 else (-0.4 if best < 5 else 0.0)
            mvx = (perp[0] / pl) * b['strafe'] + (chest[0] - eye[0]) / best * toward
            mvz = (perp[2] / pl) * b['strafe'] + (chest[2] - eye[2]) / best * toward
            ml = math.hypot(mvx, mvz) or 1.0
            b['p'][0] += mvx / ml * BOT_SPEED * 0.7 * dt
            b['p'][2] += mvz / ml * BOT_SPEED * 0.7 * dt
            b['moving'] = True
            _collide_world(b['p'])
            # Disparo con dispersión
            if now >= b['next_shot']:
                b['next_shot'] = now + random.uniform(BOT_FIRE_MIN, BOT_FIRE_MAX)
                d = [chest[i] - eye[i] for i in range(3)]
                dl = math.sqrt(sum(c * c for c in d)) or 1.0
                d = [c / dl + random.uniform(-BOT_SPREAD, BOT_SPREAD)
                     for c in d]
                await _shoot(b, eye, d)
            return

    # Navegación por waypoints
    wp = b['wp']
    if (wp is None or
            math.hypot(wp[0] - b['p'][0], wp[2] - b['p'][2]) < 1.2):
        # Si el enemigo existe pero sin LOS, acercarse a su zona
        if target is not None and random.random() < 0.4:
            b['wp'] = [target['p'][0] + random.uniform(-4, 4), 0,
                       target['p'][2] + random.uniform(-4, 4)]
        else:
            b['wp'] = list(random.choice(WAYPOINTS))
        wp = b['wp']

    dx, dz = wp[0] - b['p'][0], wp[2] - b['p'][2]
    dl = math.hypot(dx, dz)
    if dl > 1e-6:
        b['p'][0] += dx / dl * BOT_SPEED * dt
        b['p'][2] += dz / dl * BOT_SPEED * dt
        b['ry'] = math.atan2(-dx, -dz)
        b['moving'] = True
    _collide_world(b['p'])
    m = ARENA_HALF - 0.6
    b['p'][0] = max(-m, min(m, b['p'][0]))
    b['p'][2] = max(-m, min(m, b['p'][2]))


async def _bot_tick():
    while True:
        await asyncio.sleep(1.0 / BOT_HZ)
        for b in [p for p in list(players.values())
                  if p['bot'] and p['alive']]:
            try:
                await _bot_step(b, 1.0 / BOT_HZ)
            except Exception:
                pass          # un bot roto no tumba el tick


async def _add_bot(name=None):
    p = _nuevo_jugador(name or random.choice(BOT_NAMES), bot=True)
    await _broadcast({
        't': 'join', 'id': p['id'], 'name': p['name'],
        'team': p['team'], 'p': p['p'], 'names': _names(),
    })
    await _broadcast({'t': 'feed',
                      'msg': f"🤖 {p['name']} se unió — equipo {p['team']}"})
    return p


# --------------------------------------------------------------------------
# Conexión humana
# --------------------------------------------------------------------------

async def _handler(ws):
    me = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            t = msg.get('t')

            if t == 'join' and me is None:
                me = _nuevo_jugador(msg.get('name'), ws=ws)
                await _send(ws, {
                    't': 'welcome', 'id': me['id'], 'team': me['team'],
                    'map': {'half': ARENA_HALF, 'boxes': MAP_BOXES,
                            'spawns': SPAWNS},
                    'players': {p['id']: _public_player(p)
                                for p in players.values()},
                    'score': _score(), 'names': _names(),
                })
                await _broadcast({
                    't': 'join', 'id': me['id'], 'name': me['name'],
                    'team': me['team'], 'p': me['p'], 'names': _names(),
                })
                await _broadcast({'t': 'feed',
                                  'msg': f"{me['name']} entró al arena "
                                         f"— equipo {me['team']}"})
                # Spawn de bots pedidos por el cliente
                try:
                    n_bots = max(0, min(int(msg.get('bots') or 0), 10))
                except (TypeError, ValueError):
                    n_bots = 0
                for _ in range(n_bots):
                    if len(players) >= MAX_PLAYERS:
                        break
                    await _add_bot()
                continue

            if me is None:
                continue
            if t == 'input':
                p = _clamp_pos(msg.get('p'))
                if p is not None:
                    me['p'] = p
                try:
                    me['ry'] = float(msg.get('ry', me['ry']))
                    me['pitch'] = float(msg.get('pitch', me['pitch']))
                except (TypeError, ValueError):
                    pass
                me['moving'] = bool(msg.get('moving'))
            elif t == 'shoot':
                try:
                    o = [float(v) for v in msg['o'][:3]]
                    d = [float(v) for v in msg['d'][:3]]
                except (TypeError, ValueError, KeyError, IndexError):
                    continue
                await _shoot(me, o, d)
            elif t == 'ping':
                await _send(ws, {'t': 'pong'})
    finally:
        if me is not None:
            players.pop(me['id'], None)
            await _broadcast({'t': 'leave', 'id': me['id'],
                              'names': _names()})
            await _broadcast({'t': 'feed',
                              'msg': f"{me['name']} abandonó el arena"})
            # Sin humanos en el arena, los bots se retiran también
            if not any(not p['bot'] for p in players.values()):
                for pid in [p['id'] for p in list(players.values())
                            if p['bot']]:
                    players.pop(pid, None)


async def _tick():
    """Snapshot de posiciones a TICK_HZ — lo que ve cada cliente."""
    while True:
        await asyncio.sleep(1.0 / TICK_HZ)
        if not players:
            continue
        await _broadcast({
            't': 'state',
            'players': {p['id']: _public_player(p) for p in players.values()},
            'score': _score(),
        })


async def main(port):
    async with websockets.serve(_handler, '0.0.0.0', port,
                                ping_interval=20, ping_timeout=30):
        asyncio.ensure_future(_tick())
        asyncio.ensure_future(_bot_tick())
        print(f"[datico-arena] ws://0.0.0.0:{port}  "
              f"(tick {TICK_HZ} Hz, bots {BOT_HZ} Hz, max {MAX_PLAYERS})")
        await asyncio.Future()          # correr para siempre


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    args = ap.parse_args()
    try:
        asyncio.run(main(args.port))
    except KeyboardInterrupt:
        pass
