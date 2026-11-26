"""Hand-reviewed terrain edits (decisions/terrain_edits.json): scope cuts, parking lot, no-go areas, curb
lines and tree corrections.

A curb line is a polyline on the step between road and sidewalk. Step 7 makes it a vertical step: every
0.1 m cell within curb_step_half_width_m of the line takes the height measured that far out on its own
side, so the smoothed 0.3-0.4 m ramp of the grid becomes a wall. Step 8 additionally turns curbs with
nogo=true into a no-go strip strip_height_m above the road side (0.3 m, not the usual 0.8 m).
Polygons (scope cuts, parking lot, no-go areas) are rasterised on the 0.1 m grid by cell centre.
"""
import numpy as np
from matplotlib.path import Path as Polygon
from scipy import ndimage

from config import TERRAIN_EDITS
from pcio import load_json


def load():
    return load_json(TERRAIN_EDITS)


def polygon_mask(x, y, polygon):
    """Cells of the (len(y), len(x)) grid whose centre lies inside the polygon."""
    poly = np.asarray(polygon, float)
    lo, hi = poly.min(0), poly.max(0)
    cs, rs = np.flatnonzero((x >= lo[0]) & (x <= hi[0])), np.flatnonzero((y >= lo[1]) & (y <= hi[1]))
    mask = np.zeros((len(y), len(x)), bool)
    if len(cs) and len(rs):
        gx, gy = np.meshgrid(x[cs], y[rs])
        inside = Polygon(poly).contains_points(np.column_stack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
        mask[np.ix_(rs, cs)] = inside
    return mask


def sample(h, x, y, xy):
    return ndimage.map_coordinates(h, [(xy[..., 1]-y[0])/(y[1]-y[0]), (xy[..., 0]-x[0])/(x[1]-x[0])], order=1, mode="nearest")


def near_line(x, y, polyline, reach):
    """Cells within `reach` of the polyline (not past its ends): row/col index, signed distance (+ = left of
    the drawing direction), foot point on the line and unit left normal."""
    line = np.asarray(polyline, float)
    lo, hi = line.min(0)-reach, line.max(0)+reach
    cs, rs = np.flatnonzero((x >= lo[0]) & (x <= hi[0])), np.flatnonzero((y >= lo[1]) & (y <= hi[1]))
    rr, cc = np.meshgrid(rs, cs, indexing="ij")
    pts = np.column_stack([x[cc.ravel()], y[rr.ravel()]])
    best = np.full(len(pts), np.inf)
    sd, foot, normal = np.zeros(len(pts)), np.zeros((len(pts), 2)), np.zeros((len(pts), 2))
    for i, (a, b) in enumerate(zip(line[:-1], line[1:])):
        d = b-a
        t = ((pts-a)@d)/(d@d)
        first, last = i == 0, i == len(line)-2
        inside = (t >= (0 if first else -.05)) & (t <= (1 if last else 1.05))
        t = np.clip(t, 0, 1)
        q = a+t[:, None]*d
        dist = np.linalg.norm(pts-q, axis=1)
        n = np.array([-d[1], d[0]])/np.linalg.norm(d)
        better = inside & (dist < best)
        best[better] = dist[better]
        sd[better] = ((pts[better]-q[better])@n)
        foot[better], normal[better] = q[better], n
    ok = best <= reach
    return rr.ravel()[ok], cc.ravel()[ok], sd[ok], foot[ok], normal[ok]


def curb_step(h, x, y, curb, reach):
    """Vertical step along one curb line. Returns the edited height grid and the step heights at the line."""
    r, c, sd, foot, n = near_line(x, y, curb["polyline_xy"], reach)
    left, right = sample(h, x, y, foot+reach*n), sample(h, x, y, foot-reach*n)
    out = h.copy()
    out[r, c] = np.where(sd >= 0, left, right)
    return out, np.abs(left-right)


def curb_strip(h, x, y, curb, reach):
    """No-go strip strip_width_m wide centred on the curb line: cells, top (road + strip_height_m), road (lower side)."""
    r, c, sd, foot, n = near_line(x, y, curb["polyline_xy"], reach)
    a, b = sample(h, x, y, foot+reach*n), sample(h, x, y, foot-reach*n)
    on = np.abs(sd) <= curb["strip_width_m"]/2
    road = np.minimum(a, b)[on]
    return r[on], c[on], road+curb["strip_height_m"], road


def fix_trees(trees, ground_at, ground):
    """Apply the reviewed tree corrections; each entry must match one tree with trunk returns within 1 m."""
    log = []
    for e in load()["trees"]:
        hit = [t for t in trees if t["trunk_evidence"] == "stem_returns" and
               np.hypot(*np.subtract(t["trunk_xy"], e["near_xy"])) <= 1.0]
        if not hit:
            log.append({**e, "matched": None})
            continue
        t = min(hit, key=lambda t: np.hypot(*np.subtract(t["trunk_xy"], e["near_xy"])))
        if e["action"] == "not_trunk":
            t["trunk_evidence"] = "reviewed_not_trunk"
        else:
            t["trunk_xy"] = list(e["to_xy"])
            t["ground_z"] = round(float(ground_at(ground, np.asarray([e["to_xy"]], float))[0]), 3)
            t["trunk_evidence"] = "stem_returns"
        t["review"] = e["why"]
        log.append({**e, "matched": t["id"]})
    return log
