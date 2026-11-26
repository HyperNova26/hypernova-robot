"""Individual trees near the demo route from obstacle returns, and their MuJoCo shapes.

Canopy height model (0.5 m cells, height above the ground surface) -> smoothed local maxima as tree
tops -> watershed crowns. Canopy = obstacle returns > 2.8 m above ground; stem candidates = returns
0.3-1.5 m above ground within 2.5 m of the top. The trunk is the densest 0.2 m spot of stem returns when
>= 15 of them lie within 0.4 m of it; otherwise the crown overhangs from a trunk elsewhere and is kept for
sensor rays only (no solid trunk in the road).
"""
import xml.etree.ElementTree as ET

import numpy as np
from scipy import ndimage

CELL = 0.5
MIN_TOP_M = 3.0     # tree top height above ground
PEAK_WINDOW = 5     # cells; tops closer than ~1.25 m merge
MAX_CROWN_R = 4.5   # m from the top; farther canopy belongs to a neighbour
MIN_CROWN_POINTS = 300
CANOPY_M, STEM_M = 2.8, (0.3, 1.5)
STEM_SEARCH_M, STEM_CLUSTER_M, MIN_STEM = 2.5, 0.4, 15


def xyz_text(values):
    return " ".join(f"{v:.9g}" for v in values)


def ground_at(ground, xy):
    x, y, h = ground
    return ndimage.map_coordinates(h, [(xy[:, 1]-y[0])/(y[1]-y[0]), (xy[:, 0]-x[0])/(x[1]-x[0])], order=1, mode="nearest")


def solid(trees):
    """Trees with trunk returns: these get a collision trunk and root mound."""
    return [t for t in trees if t["trunk_evidence"] == "stem_returns"]


def trunk_from_stems(stems):
    """Densest 0.2 m spot of stem returns and the returns within STEM_CLUSTER_M of it, or None."""
    if len(stems) < MIN_STEM:
        return None
    cell = np.floor(stems[:, :2]/.2).astype(int)
    keys, inv, count = np.unique(cell, axis=0, return_inverse=True, return_counts=True)
    centre = (keys[np.argmax(count)]+.5)*.2
    near = stems[np.linalg.norm(stems[:, :2]-centre, axis=1) <= STEM_CLUSTER_M]
    return near if len(near) >= MIN_STEM else None


def mound_radius(tree):
    return float(np.clip(.3+.35*min(tree["crown_radii_m"]), .6, 1.2))


def segment(obstacle_xyz, ground, lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    p = obstacle_xyz[np.all((obstacle_xyz[:, :2] >= lo) & (obstacle_xyz[:, :2] <= hi), axis=1)].astype(float)
    hag = p[:, 2]-ground_at(ground, p[:, :2])
    canopy_pt, stem_pt = hag > CANOPY_M, (hag > STEM_M[0]) & (hag < STEM_M[1])
    ij = np.floor((p[:, :2]-lo)/CELL).astype(int)
    shape = tuple(np.floor((hi-lo)/CELL).astype(int)[::-1]+1)
    chm = np.zeros(shape)
    np.maximum.at(chm, (ij[:, 1], ij[:, 0]), np.where(canopy_pt, hag, 0))
    smooth = ndimage.gaussian_filter(chm, 1.0)
    markers, n = ndimage.label((smooth == ndimage.maximum_filter(smooth, PEAK_WINDOW)) & (smooth > MIN_TOP_M))
    canopy = ndimage.binary_closing(chm > 2.0, iterations=2)
    markers = markers.astype(np.int32)
    markers[~canopy & (markers == 0)] = -1
    crowns = ndimage.watershed_ift(np.clip(255-smooth*20, 0, 255).astype(np.uint8), markers)
    crowns[~canopy] = 0
    owner = crowns[ij[:, 1], ij[:, 0]]
    trees = []
    for k in range(1, n+1):
        top_xy = lo+(np.argwhere(markers == k)[0][::-1]+.5)*CELL
        mine = (owner == k) & (np.linalg.norm(p[:, :2]-top_xy, axis=1) <= MAX_CROWN_R)
        crown, stem = mine & canopy_pt, (np.linalg.norm(p[:, :2]-top_xy, axis=1) <= STEM_SEARCH_M) & stem_pt
        if crown.sum() < MIN_CROWN_POINTS:
            continue
        cp, ch = p[crown], hag[crown]
        trunk = trunk_from_stems(p[stem])
        if trunk is not None:
            txy = np.median(trunk[:, :2], axis=0)
            radius = float(np.clip(np.percentile(np.linalg.norm(trunk[:, :2]-txy, axis=1), 60), .12, .35))
            evidence = "stem_returns"
        else:
            txy, radius, evidence = top_xy, .18, "crown_only"
        base, top = np.percentile(ch, [5, 98])
        centre = cp[:, :2].mean(axis=0)
        val, vec = np.linalg.eigh(np.cov((cp[:, :2]-centre).T))
        rx, ry = np.clip(2*np.sqrt(np.maximum(val[::-1], 0)), 1.0, MAX_CROWN_R)
        trees.append({"id": len(trees), "trunk_xy": np.round(txy, 3).tolist(),
                      "ground_z": round(float(ground_at(ground, txy[None])[0]), 3),
                      "trunk_radius_m": round(radius, 3), "trunk_evidence": evidence,
                      "crown_base_m": round(float(base), 2), "crown_top_m": round(float(top), 2),
                      "crown_xy": np.round(centre, 3).tolist(), "crown_radii_m": [round(float(rx), 2), round(float(ry), 2)],
                      "crown_yaw_deg": round(float(np.degrees(np.arctan2(vec[1, 1], vec[0, 1]))), 1),
                      "upper_xy": np.round(cp[ch >= base+.6*(top-base), :2].mean(axis=0), 3).tolist(),
                      "points": {"crown": int(crown.sum()), "stem": int(stem.sum())}})
    return {"area_xy": [lo.tolist(), hi.tolist()], "cell_m": CELL, "tops_found": int(n), "trees": trees}


def tree_geoms(trees, world):
    """Rounded trees: solid trunk and root mound stop the robot; crown lobes are sensor-only."""
    greens = [".22 .42 .22 1", ".27 .48 .25 1", ".19 .37 .20 1"]
    for t in trees:
        x, y = t["trunk_xy"]
        has_trunk = t["trunk_evidence"] == "stem_returns"
        gz, base, top = t["ground_z"], t["crown_base_m"], t["crown_top_m"]
        height = top-base
        rx, ry = t["crown_radii_m"]
        trunk_h = base+.35*height
        stem = f"pair360_tree{t['id']:02d}"
        if has_trunk:
            ET.SubElement(world, "geom", name=f"{stem}_trunk", type="cylinder", group="2", rgba=".40 .27 .16 1",
                          pos=xyz_text([x, y, gz+trunk_h/2]), size=xyz_text([t["trunk_radius_m"], trunk_h/2]))
            ET.SubElement(world, "geom", name=f"{stem}_mound", type="ellipsoid", group="2", rgba=".25 .33 .17 1",
                          pos=xyz_text([x, y, gz+.05]), size=xyz_text([mound_radius(t)]*2+[.4]))
        yaw = t["crown_yaw_deg"]
        side = np.array([-np.sin(np.radians(yaw)), np.cos(np.radians(yaw))])*.35*ry
        # Narrow crowns would become tall spindles; keep each lobe no taller than it is wide.
        tall = min(.5*height, 1.1*max(rx, ry))
        lobes = [(t["crown_xy"], base+.45*height, [rx, ry, tall]),
                 (t["upper_xy"], base+.72*height, [.62*rx, .62*ry, .64*tall]),
                 (np.add(t["crown_xy"], side), base+.55*height, [.55*rx, .55*ry, .72*tall])]
        for i, (xy, z, size) in enumerate(lobes):
            ET.SubElement(world, "geom", name=f"{stem}_crown{i}", type="ellipsoid", group="3", rgba=greens[i],
                          contype="0", conaffinity="0", euler=xyz_text([0, 0, yaw]),
                          pos=xyz_text([xy[0], xy[1], gz+z]), size=xyz_text(size))
    return len(trees)
