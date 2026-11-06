"""
Datico Arena — servidor WebSocket del easter egg multijugador.

Team deathmatch Don Datico: bando VERDE vs bando MORADO.
Servidor autoritativo para vida, daño y respawn; el movimiento lo
reportan los clientes (clamp a los límites del arena).

Uso:
    python -m datico_arena.server [--port 8765]

Protocolo JSON:

  client → server
    {"t":"join",  "name": str}
    {"t":"input", "p":[x,y,z], "ry":yaw, "pitch":pitch, "moving":bool}
    {"t":"shoot", "o":[x,y,z], "d":[dx,dy,dz]}          # rayo hitscan
    {"t":"ping"}

  server → client
    {"t":"welcome", "id", "team", "map", "players", "score", "names"}
    {"t":"join",   "id","name","team","p"}
    {"t":"leave",  "id"}
    {"t":"state",  "players":{id:{p,ry,hp,alive}}, "score"}
    {"t":"shot",   "id","o","d","hit":id|null,"wall":[x,y,z]|null}
    {"t":"damage", "id","hp","by"}
    {"t":"kill",   "killer","victim","score"}
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
RESPAWN_S = 3.0
HP_MAX = 100
DMG_DISPARO = 34
FIRE_INTERVAL = 0.18          # cadencia mínima entre disparos
PLAYER_RADIUS = 0.5
PLAYER_HEIGHT = 1.8
TEAMS = ('verde', 'morado')
MAX_PLAYERS = 16
ARENA_HALF = 22.0             # arena 44×44 m
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

# Cajas sobre las que se puede saltar (topes bajos) — el cliente las usa
# para colisión de movimiento; el server solo las usa para bloquear rayos.
SPAWNS = {
    'verde':  [[-18, 0, -4], [-18, 0, 0], [-18, 0, 4], [-16, 0, -8], [-16, 0, 8]],
    'morado': [[18, 0, 4], [18, 0, 0], [18, 0, -4], [16, 0, 8], [16, 0, -8]],
}

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

players = {}          # ws -> dict de estado
clients = {}          # id -> ws
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

    Devuelve (t_ray, dist2). Aproximación estándar resolviendo el
    sistema 2x2 entre las dos rectas y clampeando al segmento."""
    ab = [b[i] - a[i] for i in range(3)]
    ao = [o[i] - a[i] for i in range(3)]
    # d es unitario; ab no necesariamente
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


def _raycast_hit(shooter_id, o, d):
    """Devuelve (victim_id|None, t_wall, wall_point)."""
    t_wall = float('inf')
    for box in MAP_BOXES:
        t = _ray_aabb(o, d, box)
        if t is not None and t < t_wall:
            t_wall = t
    wall_point = ([o[i] + d[i] * t_wall for i in range(3)]
                  if t_wall < float('inf') else None)

    victim, t_victim = None, t_wall
    for p in players.values():
        if p['id'] == shooter_id or not p['alive']:
            continue
        # Cápsula vertical: de pies+0.25 a pies+PLAYER_HEIGHT
        a = [p['p'][0], p['p'][1] + 0.25, p['p'][2]]
        b = [p['p'][0], p['p'][1] + PLAYER_HEIGHT, p['p'][2]]
        t, dist2 = _dist2_ray_segment(o, d, a, b)
        if dist2 < PLAYER_RADIUS ** 2 and 0 <= t < t_victim:
            victim, t_victim = p['id'], t
    return victim, t_wall, wall_point


async def _broadcast(msg, exclude=None):
    data = json.dumps(msg)
    for ws in list(players):
        if ws is exclude:
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


def _score():
    s = {'verde': 0, 'morado': 0}
    for p in players.values():
        s[p['team']] += p['kills']
    return s


def _public_player(p):
    return {'p': p['p'], 'ry': p['ry'], 'hp': p['hp'], 'alive': p['alive']}


def _names():
    return {p['id']: {'name': p['name'], 'team': p['team'],
                      'kills': p['kills'], 'deaths': p['deaths']}
            for p in players.values()}


async def _respawn_later(pid):
    await asyncio.sleep(RESPAWN_S)
    ws = clients.get(pid)
    if ws is None:
        return
    p = players.get(ws)
    if p is None or p['alive']:
        return
    p['p'] = _spawn(p['team'])
    p['hp'] = HP_MAX
    p['alive'] = True
    await _broadcast({'t': 'respawn', 'id': pid, 'p': p['p']})


async def _shoot(shooter, msg):
    now = time.monotonic()
    if now - shooter['last_shot'] < FIRE_INTERVAL or not shooter['alive']:
        return
    shooter['last_shot'] = now
    o, d = msg.get('o'), msg.get('d')
    try:
        o = [float(o[i]) for i in range(3)]
        d = [float(d[i]) for i in range(3)]
        n = math.sqrt(sum(c * c for c in d)) or 1.0
        d = [c / n for c in d]
    except (TypeError, ValueError, IndexError):
        return

    shooter_team = shooter['team']
    victim, t_wall, wall_pt = _raycast_hit(shooter['id'], o, d)

    # Resolver la víctima: clients[id] -> ws -> players[ws]
    vws = clients.get(victim) if victim is not None else None
    vp = players.get(vws) if vws else None

    # Sin fuego amigo
    if vp is None or vp['team'] == shooter_team:
        victim = None

    await _broadcast({
        't': 'shot', 'id': shooter['id'], 'o': o, 'd': d,
        'hit': victim,
        'wall': wall_pt,
    })

    if victim is None:
        return
    vp['hp'] = max(0, vp['hp'] - DMG_DISPARO)
    await _send(vws, {'t': 'damage', 'id': victim, 'hp': vp['hp'],
                      'by': shooter['id']})
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


async def _handler(ws):
    global _next_id
    if len(players) >= MAX_PLAYERS:
        await ws.close(4000, 'arena llena')
        return

    me = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            t = msg.get('t')

            if t == 'join' and me is None:
                pid = _next_id
                _next_id += 1
                team = _equipo_menor()
                me = {
                    'id': pid,
                    'name': str(msg.get('name') or f'Datico-{pid}')[:24],
                    'team': team,
                    'p': _spawn(team),
                    'ry': 0.0, 'pitch': 0.0, 'moving': False,
                    'hp': HP_MAX, 'alive': True,
                    'kills': 0, 'deaths': 0,
                    'last_shot': 0.0,
                }
                players[ws] = me
                clients[pid] = ws
                await _send(ws, {
                    't': 'welcome', 'id': pid, 'team': team,
                    'map': {'half': ARENA_HALF, 'boxes': MAP_BOXES,
                            'spawns': SPAWNS},
                    'players': {p['id']: _public_player(p)
                                for p in players.values()},
                    'score': _score(), 'names': _names(),
                })
                await _broadcast({
                    't': 'join', 'id': pid, 'name': me['name'],
                    'team': team, 'p': me['p'], 'names': _names(),
                }, exclude=ws)
                await _broadcast({'t': 'feed',
                                  'msg': f"{me['name']} entró al arena "
                                         f"— equipo {team}"})
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
                await _shoot(me, msg)
            elif t == 'ping':
                await _send(ws, {'t': 'pong'})
    finally:
        if me is not None:
            players.pop(ws, None)
            clients.pop(me['id'], None)
            await _broadcast({'t': 'leave', 'id': me['id'],
                              'names': _names()})
            await _broadcast({'t': 'feed',
                              'msg': f"{me['name']} abandonó el arena"})


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
        print(f"[datico-arena] ws://0.0.0.0:{port}  "
              f"(tick {TICK_HZ} Hz, max {MAX_PLAYERS} jugadores)")
        await asyncio.Future()          # correr para siempre


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    args = ap.parse_args()
    try:
        asyncio.run(main(args.port))
    except KeyboardInterrupt:
        pass
