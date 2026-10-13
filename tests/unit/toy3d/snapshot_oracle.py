"""The frozen r7-3d snapshot's animation, transcribed verbatim from its scene.js (poseTim, poseLion,
guoHop/poseGuo, poseDoor, poseBulb, posePuffs, poseBubble, drawScreen's counters, camAt, STILLS.guo),
with its own hard-coded beat times. A test oracle: `toy3d.acting.resolve` on the worked scene (bank
data + the fold) must reproduce it frame by frame. Keys follow the frame spec's layout.

scene.js sha256 4dbdf8e4…0356 (frozen-v7-20261013, SHA256SUMS d9c61f63…5d75).
"""
import math

T = {"door": 2.2, "walk0": 2.3, "arrive": 3.0, "point": 3.0, "bubble": 3.12, "turn": 3.78, "shock": 3.9,
     "sweat": 4.08, "bulbDead": 5.5}
PI = math.pi


def clamp01(x):
    return min(1.0, max(0.0, x))


def seg(t, a, b):
    return clamp01((t - a) / (b - a))


def ease(x):
    return 4 * x * x * x if x < 0.5 else 1 - math.pow(-2 * x + 2, 3) / 2


def ease_out(x):
    return 1 - math.pow(1 - x, 3)


def ease_back(x):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * math.pow(x - 1, 3) + c1 * math.pow(x - 1, 2)


def bump(t, t0, w):
    return math.exp(-math.pow((t - t0) / w, 2))


def lerp(x, y, k):
    return (1 - k) * x + k * y


def lerp3(a, b, k):
    return [lerp(a[i], b[i], k) for i in range(3)]


def d2r(d):
    return d * PI / 180


def sph_pos(piv, az, el, d):
    return [piv[0] + d * math.cos(d2r(el)) * math.sin(d2r(az)), piv[1] + d * math.sin(d2r(el)),
            piv[2] + d * math.cos(d2r(el)) * math.cos(d2r(az))]


TIM_X, TIM_Z = 0.85, -0.5
LION_P0, LION_P1 = [-3.25, 0, -0.7], [-1.15, 0, -0.1]
GUO_POS = [-0.26, 1.04, -1.72]
GUO_TT = [1.85, 0, 0.65]


def tim(t):
    turn_k = ease_back(seg(t, T["turn"], T["turn"] + 0.34))
    shk = ease_out(seg(t, T["shock"], T["shock"] + 0.2))
    typing = t < T["shock"]
    seat_ry = -0.75 * turn_k
    seat_z = TIM_Z - 0.1 * ease_out(seg(t, T["shock"], T["shock"] + 0.35))
    tremble = math.sin(t * 61) * 0.006 * (1 - seg(t, 5.4, 6.2)) if t > T["shock"] + 0.15 else 0
    j = {"hips.px": tremble, "hips.py": 0.02 + 0.07 * math.sin(PI * seg(t, T["shock"], T["shock"] + 0.28)),
         "torso.rx": lerp(0.13 + 0.02 * math.sin(t * 5.0), -0.13, shk),
         "torso.rz": 0.03 * math.sin(t * 3.1) if typing else 0,
         "neck.rx": lerp(0.1 + 0.035 * abs(math.sin(t * 3.8)), -0.1, shk),
         "neck.ry": 0.07 * math.sin(t * 1.3) if typing else 0.12 * shk,
         "neck.rz": 0.06 * math.sin(t * 1.9) if typing else 0}
    for i, side in enumerate("lr"):
        s, ph = (-1 if i == 0 else 1), t * 26 + i * 1.9
        tx, tz, ex = -1.25 + 0.05 * math.sin(ph), -s * 0.3, -0.55 + 0.14 * math.sin(ph + 0.9)
        wig = math.sin(t * 24 + i) * 0.1 * (1 if t > T["shock"] + 0.2 else 0)
        j[f"arm_{side}.j1.rx"], j[f"arm_{side}.j1.rz"] = lerp(tx, 0.45, shk), lerp(tz, s * 1.95, shk)
        j[f"arm_{side}.j2.rx"], j[f"arm_{side}.j2.rz"] = lerp(ex, 0, shk), lerp(0, s * 0.65 + s * wig, shk)
    for i, side in enumerate("lr"):
        swing = 0.25 * math.sin(t * 4.2 + i * PI)
        j[f"leg_{side}.j1.rx"] = lerp(-PI / 2, -PI / 2 - 0.4, shk)
        j[f"leg_{side}.j2.rx"] = lerp(PI / 2 - 0.15 + swing, 0.95, shk)
    blink = (1.25 < t < 1.33) or (3.02 < t < 3.09)
    dk = seg(t, T["sweat"], T["sweat"] + 0.25)
    return {"root": {"pos": [TIM_X, 0.3, seat_z], "yaw": seat_ry},
            "seat": {"spot": "desk_seat", "pos": [TIM_X, 0, seat_z], "yaw": seat_ry},
            "joints": j,
            "face": "tim_shock" if t >= T["shock"] else "tim_blink" if blink else "tim_neutral",
            "sweat": {"scale": max(0.001, ease_back(dk)),
                      "y": 0.08 - 0.07 * ease_out(seg(t, T["sweat"] + 0.2, 6.0))} if dk > 0 else None}


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def lion(t):
    wk = seg(t, T["walk0"], T["arrive"])
    we = ease_out(wk)
    pos = lerp3(LION_P0, LION_P1, we)
    dist = we * _dist(LION_P0, LION_P1) / 1.15
    ph = (dist / 0.2) * PI
    step = 1 if 0 < wk < 1 else max(0, 1 - (t - T["arrive"]) * 6) if wk >= 1 else 0
    pk = ease_back(seg(t, T["point"], T["point"] + 0.2))
    jab = 0.16 * (bump(t, 3.42, 0.06) + bump(t, 3.66, 0.06))
    j = {"hips.py": 0.17 + 0.022 * abs(math.sin(ph)) * step,
         "body.rz": 0.06 * math.sin(ph) * step,
         "body.rx": 0.07 * pk + jab * 0.4 + (0.1 if T["door"] < t < T["walk0"] + 0.2 else 0),
         "neck.rx": 0.09 * pk, "neck.ry": 0.22 * pk}
    for i, side in enumerate("lr"):
        j[f"leg_{side}.j1.rx"] = (1 if i else -1) * 0.5 * math.sin(ph) * step
        j[f"leg_{side}.j2.rx"] = 0.25 * max(0, math.sin(ph + (0 if i else PI))) * step
    swing = 0.4 * math.sin(ph) * step
    j["arm_r.j1.rx"], j["arm_r.j1.rz"] = lerp(-swing, -1.62 - jab, pk), lerp(-0.12, 0.88, pk)
    j["arm_r.j2.rx"], j["arm_r.j2.rz"] = lerp(0, -0.08, pk), 0
    ak = ease(seg(t, T["arrive"] - 0.1, T["arrive"] + 0.2))
    j["arm_l.j1.rx"], j["arm_l.j1.rz"] = lerp(swing, -0.2, ak), lerp(-0.12, -0.85, ak)
    j["arm_l.j2.rx"], j["arm_l.j2.rz"] = 0, lerp(0, 1.95, ak)
    j["tail.rx"], j["tail.ry"] = 0.1 * math.sin(t * 1.7), 0.35 * math.sin(t * 2.3)
    flick = bump(t, T["door"] + 0.05, 0.08)
    j["ear_l.rz"], j["ear_r.rz"] = 0.25 * flick, -0.25 * flick
    return {"root": {"pos": pos, "yaw": lerp(d2r(90), d2r(45), ease(seg(t, 2.75, 3.15)))},
            "joints": j, "finger": pk > 0.05,
            "face": "lion_blink" if 4.6 < t < 4.68 else "lion_stern",
            "bang": 1 + 0.25 * (bump(t, 3.42, 0.07) + bump(t, 3.66, 0.07))}


def _guo_hop(t):
    t0 = T["door"] + 0.03
    return (0.17 * math.sin(PI * seg(t, t0 + 0.06, t0 + 0.44))
            + 0.05 * math.sin(PI * seg(t, T["shock"] + 0.03, T["shock"] + 0.21)))


def guo(t, neutral=False):
    """poseGuo: seated on the shelf in the room; `neutral` is the design view (standing, at GUO_TT)."""
    t0 = T["door"] + 0.03
    shocked = not neutral and t >= t0
    hop_k = 1 if neutral else 0.6
    calm = 0 if neutral else 1 - seg(t, T["door"], T["door"] + 0.1)
    hop = 0 if neutral else hop_k * _guo_hop(t)
    vel = 0 if neutral else hop_k * (_guo_hop(t) - _guo_hop(t - 1 / 120)) * 120

    def aim(x, z):
        return math.atan2(x - GUO_POS[0], z - GUO_POS[2])
    lp = lion(t)["root"]["pos"]
    y_tim, y_lion = aim(TIM_X, TIM_Z), aim(lp[0], lp[2])
    look = lerp(y_tim, y_lion, ease(seg(t, T["door"] + 0.06, T["door"] + 0.32)))
    look = lerp(look, y_tim - 0.3, ease(seg(t, T["shock"] + 0.04, T["shock"] + 0.34)))
    look += 0.12 * math.sin(t * 1.3) * (1 - seg(t, T["door"], T["door"] + 0.1))
    seat_yaw = 0.12
    body_yaw = seat_yaw + 0.35 * (look - seat_yaw)
    head = max(-0.55, min(0.55, look - body_yaw))
    sq = bump(t, t0 + 0.03, 0.03)
    land = bump(t, t0 + 0.47, 0.045) + 0.5 * bump(t, T["shock"] + 0.23, 0.04)
    u = t - (t0 + 0.5)
    wob = math.exp(-u * 6) * math.sin(u * 30) if u > 0 else 0
    sy = 1 if neutral else 1 - 0.14 * sq + 0.1 * min(1, abs(vel) / 1.4) - 0.16 * land + 0.06 * wob

    def fl(ta, tb, hz):
        return math.sin((t - ta) * PI * 2 * hz) * seg(t, ta, ta + 0.06) * (1 - seg(t, tb - 0.25, tb))
    flap = 0 if neutral else fl(t0, t0 + 1.0, 6.5) + 0.7 * fl(T["shock"] + 0.02, T["shock"] + 0.45, 7)
    after = t - (t0 + 1.0)
    jig = 0.12 * math.exp(-after * 5) * math.sin(after * 24) if not neutral and after > 0 else 0
    flippers = []
    for i in range(2):
        s = 1 if i else -1
        flippers.append(s * (0 + (0 if neutral else 0.08 * math.sin(t * 2.6) * calm) + 0.55 * flap + jig
                             + 0.25 * (1 if shocked else 0) * (1 - seg(t, t0 + 1.2, t0 + 1.8))))
    push = -0.45 - 0.22 * vel - 0.5 * land + 0.25 * wob
    whip = 0.5 * math.cos((t - t0) * PI * 2 * 6.5) * (1 if abs(flap) > 0.05 else 0)
    base = GUO_TT if neutral else GUO_POS
    return {"build": "guoguo_standing" if neutral else "guoguo_seated",
            "root": {"pos": list(base), "yaw": 0 if neutral else body_yaw},
            "guo": {"head_yaw": 0 if neutral else head,
                    "body_scale": [1 / math.sqrt(sy), sy, 1 / math.sqrt(sy)],
                    "body_py": hop + (0 if neutral else 0.006 * abs(math.sin(t * 3.2)) * calm),
                    "body_rz": 0 if neutral else 0.035 * math.sin(t * 3.2) * calm
                    + (0.015 * math.sin(t * 47) * (1 - seg(t, 4.6, 5.4)) if shocked else 0),
                    "flippers": flippers,
                    "eye": 1.25 if shocked else 1, "pupil": 0.6 if shocked else 1,
                    "push": push, "flipper_push": push - whip}}


def door(t):
    a = seg(t, T["door"], T["door"] + 0.14)
    ang = 1.9 * ease_out(a)
    if t > T["door"] + 0.14:
        u = t - T["door"] - 0.14
        ang = 1.62 + 0.28 * math.exp(-u * 7) * math.cos(u * 26)
    k = seg(t, T["door"] + 0.06, T["door"] + 0.9)
    return {"angle": ang, "dust": {"k": k, "move": ease_out(k), "grow": 0.4 + 1.4 * ease_out(k), "alpha": 0.7 * (1 - k)}}


FLICKER = [[0, 1], [T["shock"], 0.1], [3.98, 0.9], [4.06, 0.15], [4.12, 0.85], [4.98, 0.15], [5.05, 0.75],
           [5.13, 0.08], [5.19, 0.6], [5.25, 0.05], [5.32, 0.45], [5.37, 0.0], [5.44, 0.25], [T["bulbDead"], 0]]


def bulb(t):
    level = 1
    for t0, lv in FLICKER:
        if t >= t0:
            level = lv
    dead = ease_out(seg(t, T["bulbDead"], T["bulbDead"] + 0.5))
    smoke = []
    for i in range(3):
        k = seg(t, T["bulbDead"] + i * 0.12, T["bulbDead"] + 0.9 + i * 0.12)
        smoke.append({"k": k, "dx": 0.02 * math.sin(i * 2 + t * 3), "rise": 0.1 + 0.3 * k,
                      "grow": 0.6 + 1.6 * k, "alpha": 0.55 * (1 - k)})
    return {"on": "tim", "anchor": [0, 0.76, 0], "level": level, "lit": level > 0.05,
            "bob": 0.025 * math.sin(t * 2.4) - 0.06 * dead, "tilt": 0.05 * math.sin(t * 1.7) + 0.3 * dead,
            "glow": 0.55 + 0.05 * math.sin(t * 5), "rays": 1 + 0.06 * math.sin(t * 6) if level > 0.5 else 0,
            "smoke": smoke}


def bubble(t):
    k = seg(t, T["bubble"], T["bubble"] + 0.32)
    if not k > 0:
        return None
    return {"speaker": "lioness", "icons": ["dishes", "bang"], "right": 0.42, "up": 0.62,
            "bob": 0.025 * math.sin(t * 2.2), "pop": max(0.001, ease_back(k)) * 1.1, "bang": lion(t)["bang"]}


def laptop(t):
    shown = 4 + math.floor(min(t, T["shock"]) * 2.2)
    return {"spot": "desk_seat", "lines": min(shown, 11), "cursor": math.floor(t * 3) % 2 == 0}


PIV0, PIV1 = [-0.15, 0.72, -0.4], [0.12, 0.92, -0.32]
C1 = sph_pos(PIV1, 6, 12, 5.8)
TB, TC, TD, TE = [-1.85, 1.05, -0.5], [-0.95, 1.32, -0.2], [0.78, 1.06, -0.5], [0.8, 1.66, -0.52]
P2 = [-0.2, 1.0, -0.25]
_C1REL = [C1[i] - P2[i] for i in range(3)]
_C1LEN = math.sqrt(sum(c * c for c in _C1REL))
O2 = {"az": math.atan2(_C1REL[0], _C1REL[2]) / d2r(1), "el": math.asin(_C1REL[1] / _C1LEN) / d2r(1), "d": _C1LEN}


def cam(t):
    if t < 2.25:
        k = ease(seg(t, 0, 2.25))
        piv = lerp3(PIV0, PIV1, k)
        return {"pos": sph_pos(piv, lerp(40, 6, k), lerp(27, 12, k), lerp(10.2, 5.8, k)), "target": piv, "fov": 30}
    if t < 3.45:
        a, b = ease(seg(t, 2.3, 2.85)), ease(seg(t, 2.85, 3.4))
        return {"pos": list(C1), "target": lerp3(lerp3(PIV1, TB, a), TC, b), "fov": lerp(30, 25, b)}
    if t < 4.8:
        a, z = ease(seg(t, 3.45, 3.82)), ease(seg(t, 4.0, 4.75))
        return {"pos": list(C1), "target": lerp3(TC, TD, a), "fov": lerp(lerp(25, 28, a), 12.5, z)}
    if t < 5.6:
        k = ease(seg(t, 4.85, 5.45))
        return {"pos": list(C1), "target": lerp3(TD, TE, k), "fov": lerp(12.5, 15, k)}
    k = ease(seg(t, 5.6, 7.6))
    return {"pos": sph_pos(P2, lerp(O2["az"], -13, k), lerp(O2["el"], 4, k), lerp(O2["d"], 4.9, k)),
            "target": lerp3(TE, P2, k), "fov": lerp(15, 30, k)}


GUO_VIEW = {"pos": [1.85 - 0.95, 0.52, 0.65 + 1.1], "target": [1.85, 0.33, 0.65], "fov": 30}   # STILLS.guo
