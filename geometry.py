"""Generates the star-shaped reveal path: N evenly (arc-length) spaced points
along an idealized 5-point star with two small "sparkle" wisps bookending the
top tip, plus a jittered "wrong" counterpart for each point used to draw a
scrambled line when a team makes a mistake. Same idealized-template /
arc-length-resample technique as the rocket-reveal game — if the number of
questions changes, the shape's point density just adapts automatically.
"""
import math, random

# idealized star vertices in local, origin-centered space:
#   3 pts — little sparkle wisp BEFORE the top tip
#   11 pts — the star outline itself (5 tips + 5 notches, closing back to
#            the starting tip so the loop reads as a sealed star)
#   3 pts — a second sparkle wisp AFTER the top tip
# Sparkles are anchored right at the top tip so the connecting segments are
# short — no long diagonal "cut" across the shape (a bug hit during
# prototyping when a detail was inserted mid-path instead of bookended).
_R, _r = 100.0, 38.0
_star_core = []
for i in range(5):
    a_out = -math.pi / 2 + i * (2 * math.pi / 5)
    a_in = a_out + math.pi / 5
    _star_core.append((_R * math.cos(a_out), _R * math.sin(a_out)))   # tip
    _star_core.append((_r * math.cos(a_in), _r * math.sin(a_in)))     # notch
_tip1 = _star_core[0]
_star_loop = _star_core + [_tip1]  # close the loop back at the top tip

_tx, _ty = _tip1
_spark_a = [(_tx - 34, _ty - 46), (_tx - 14, _ty - 26), (_tx - 26, _ty - 8)]
_spark_b = [(_tx + 26, _ty - 8), (_tx + 14, _ty - 26), (_tx + 34, _ty - 46)]

STAR_VERTICES_LOCAL = _spark_a + _star_loop + _spark_b  # 17 idealized points

# scale/center the local vertices into the shared 500x420 canvas frame
# (same viewBox size the rocket game uses)
_xs = [p[0] for p in STAR_VERTICES_LOCAL]
_ys = [p[1] for p in STAR_VERTICES_LOCAL]
_w, _h = max(_xs) - min(_xs), max(_ys) - min(_ys)
_scale = min(340 / _w, 360 / _h)
_ox = (500 - _w * _scale) / 2 - min(_xs) * _scale
_oy = (420 - _h * _scale) / 2 - min(_ys) * _scale
STAR_VERTICES = [(round(x * _scale + _ox, 1), round(y * _scale + _oy, 1)) for x, y in STAR_VERTICES_LOCAL]


def _cum_lengths(pts):
    lens = [0.0]
    for i in range(len(pts) - 1):
        lens.append(lens[-1] + math.dist(pts[i], pts[i + 1]))
    return lens

def _point_at(pts, lens, target):
    for i in range(len(lens) - 1):
        if lens[i] <= target <= lens[i + 1]:
            seg = lens[i + 1] - lens[i]
            t = 0 if seg == 0 else (target - lens[i]) / seg
            x = pts[i][0] + t * (pts[i + 1][0] - pts[i][0])
            y = pts[i][1] + t * (pts[i + 1][1] - pts[i][1])
            return (round(x, 1), round(y, 1))
    return pts[-1]

# Hand-tuned exact layout for the default 27-question deck: two short sparkle
# wisps bookending the top tip, then one evenly-subdivided point per star
# edge. Arc-length-resampling the whole 17-vertex path (tried first) skews
# too many points onto the short sparkle segments relative to the long star
# edges, stretching the wisps into a big crossing "X" above the star instead
# of a light flourish — so for n=27 we use this verified-good fixed layout,
# and only fall back to generic resampling if the question count changes.
STAR_POINTS_27 = [
    (198.8, 39.0), (228.9, 69.1), (210.8, 96.3), (250.0, 108.3), (266.8, 160.5),
    (283.7, 212.7), (338.5, 212.6), (393.3, 212.5), (348.9, 244.6), (304.5, 276.8),
    (321.5, 328.9), (338.6, 381.0), (294.3, 348.7), (250.0, 316.3), (205.7, 348.7),
    (161.4, 381.0), (178.5, 328.9), (195.5, 276.8), (151.1, 244.6), (106.7, 212.5),
    (161.5, 212.6), (216.3, 212.7), (233.2, 160.5), (250.0, 108.3), (289.2, 96.3),
    (271.1, 69.1), (301.2, 39.0),
]

def star_points(n=27):
    if n == 27:
        return list(STAR_POINTS_27)
    # generic fallback for a different question count — still a closed star,
    # just without the hand-tuned sparkle proportions above
    lens = _cum_lengths(STAR_VERTICES)
    total = lens[-1]
    pts = []
    for i in range(n):
        target = total * i / (n - 1)
        pts.append(_point_at(STAR_VERTICES, lens, target))
    return pts

def wrong_points(correct_pts, seed=11, jitter=50):
    random.seed(seed)
    out = []
    cx, cy = 250, 210
    for (x, y) in correct_pts:
        dx, dy = x - cx, y - cy
        dist = math.hypot(dx, dy) or 1
        nx, ny = dx / dist, dy / dist
        ang = random.uniform(-0.9, 0.9)
        rx = nx * math.cos(ang) - ny * math.sin(ang)
        ry = nx * math.sin(ang) + ny * math.cos(ang)
        mag = random.uniform(jitter * 0.6, jitter * 1.3)
        out.append((round(x + rx * mag, 1), round(y + ry * mag, 1)))
    return out

if __name__ == "__main__":
    pts = star_points(27)
    wpts = wrong_points(pts)
    print("CORRECT:", pts)
    print("WRONG:  ", wpts)
    mind = min(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    print("min consecutive spacing:", round(mind, 1))
