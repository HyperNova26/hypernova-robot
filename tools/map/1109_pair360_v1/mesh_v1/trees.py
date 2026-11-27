"""Split trunk/foliage points near the demo route into individual trees.

Canopy height model (0.5 m cells, height above ground) -> smoothed local maxima as tree
tops -> watershed crowns. The trunk is the median of trunk-class points in the crown, or
the crown top when no trunk was measured. new/old points get the same per-area z offset
that separate_ground.py removed from their ground.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent
CELL = 0.5
MARGIN = 15.0       # demo area = route bounding box + margin (m)
MIN_TOP_M = 3.0     # tree top height above ground
PEAK_WINDOW = 5     # cells; tops closer than ~1.25 m merge
MAX_CROWN_R = 4.5   # m from the top; farther canopy belongs to a neighbour
MIN_CROWN_POINTS = 300


def xyz_text(values):
    return " ".join(f"{v:.9g}" for v in values)


def tree_geoms(trees, world):
    """Rounded trees: solid trunk and root mound stop the robot; crown lobes are sensor-only."""
    greens = [".22 .42 .22 1", ".27 .48 .25 1", ".19 .37 .20 1"]
    for t in trees:
        x, y = t["trunk_xy"]
        gz, base, top = t["ground_z"], t["crown_base_m"], t["crown_top_m"]
        height = top-base
        rx, ry = t["crown_radii_m"]
        trunk_h = base+.35*height
        stem = f"pair360_tree{t['id']:02d}"
        ET.SubElement(world, "geom", name=f"{stem}_trunk", type="cylinder", group="2", rgba=".40 .27 .16 1",
                      pos=xyz_text([x, y, gz+trunk_h/2]), size=xyz_text([t["trunk_radius_m"], trunk_h/2]))
        mound = float(np.clip(.3+.35*min(rx, ry), .6, 1.2))
        ET.SubElement(world, "geom", name=f"{stem}_mound", type="ellipsoid", group="2", rgba=".25 .33 .17 1",
                      pos=xyz_text([x, y, gz+.05]), size=xyz_text([mound, mound, .4]))
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


def filled_ground(surface):
    """v9 height with excluded cells (tree pits, structures) filled from the nearest floor."""
    h = surface["height"].astype(float)
    hole = np.isnan(h)
    idx = ndimage.distance_transform_edt(hole, return_distances=False, return_indices=True)
    return surface["x"], surface["y"], h[tuple(idx)]


def ground_at(ground, xy):
    x, y, h = ground
    g = [(xy[:, 1]-y[0])/(y[1]-y[0]), (xy[:, 0]-x[0])/(x[1]-x[0])]
    return ndimage.map_coordinates(h, g, order=1, mode="nearest")


def source_offsets(xy, source):
    """z offset (m) separate_ground.py measured for new(1)/old(2) points; 0 for S-004."""
    out = np.zeros(len(xy))
    with np.load(RELEASE/"output/map_v1_ground_correction.npz") as c:
        for sid, key in ((1, "pc_v3"), (2, "pc_v2")):
            m = source == sid
            if not m.any():
                continue
            field, lo, cell = c[f"{key}_offset_m"].astype(float), c[f"{key}_origin_xy"], float(c[f"{key}_cell_m"])
            g = [(xy[m, 1]-lo[1])/cell-.5, (xy[m, 0]-lo[0])/cell-.5]
            filled = field[tuple(ndimage.distance_transform_edt(np.isnan(field), return_distances=False, return_indices=True))]
            out[m] = ndimage.map_coordinates(filled, g, order=1, mode="nearest")
    return out


def segment(xyz, label, source, ground, route):
    lo, hi = route.min(axis=0)-MARGIN, route.max(axis=0)+MARGIN
    m = np.isin(label, (2, 3)) & np.all((xyz[:, :2] >= lo) & (xyz[:, :2] <= hi), axis=1)
    p, lab, src = xyz[m].astype(float), label[m], source[m]
    p[:, 2] -= source_offsets(p[:, :2], src)
    hag = p[:, 2]-ground_at(ground, p[:, :2])
    ij = np.floor((p[:, :2]-lo)/CELL).astype(int)
    shape = tuple(np.floor((hi-lo)/CELL).astype(int)[::-1]+1)
    chm = np.zeros(shape)
    np.maximum.at(chm, (ij[:, 1], ij[:, 0]), np.where(lab == 3, hag, 0))
    smooth = ndimage.gaussian_filter(chm, 1.0)
    tops = (smooth == ndimage.maximum_filter(smooth, PEAK_WINDOW)) & (smooth > MIN_TOP_M)
    markers, n = ndimage.label(tops)
    canopy = ndimage.binary_closing(chm > 2.0, iterations=2)
    level = np.clip(255-smooth*20, 0, 255).astype(np.uint8)
    markers = markers.astype(np.int32)
    markers[~canopy & (markers == 0)] = -1
    crowns = ndimage.watershed_ift(level, markers)
    crowns[~canopy] = 0
    owner = crowns[ij[:, 1], ij[:, 0]]
    trees, used = [], np.zeros(len(p), bool)

    def add(crown, trunk, fallback_xy):
        cp, ch = p[crown], hag[crown]
        if trunk.sum() >= 15:
            txy = np.median(p[trunk, :2], axis=0)
            radius = float(np.clip(np.percentile(np.linalg.norm(p[trunk, :2]-txy, axis=1), 60), .12, .35))
            evidence = "trunk_points"
        else:
            txy, radius, evidence = fallback_xy, .18, "crown_top"
        base, top = np.percentile(ch, [5, 98])
        upper = ch >= base+.6*(top-base)
        centre = cp[:, :2].mean(axis=0)
        val, vec = np.linalg.eigh(np.cov((cp[:, :2]-centre).T))
        rx, ry = np.clip(2*np.sqrt(np.maximum(val[::-1], 0)), 1.0, MAX_CROWN_R)
        used[crown | trunk] = True
        trees.append({"id": len(trees), "trunk_xy": np.round(txy, 3).tolist(),
                      "ground_z": round(float(ground_at(ground, txy[None])[0]), 3),
                      "trunk_radius_m": round(radius, 3), "trunk_evidence": evidence,
                      "crown_base_m": round(float(base), 2), "crown_top_m": round(float(top), 2),
                      "crown_xy": np.round(centre, 3).tolist(), "crown_radii_m": [round(float(rx), 2), round(float(ry), 2)],
                      "crown_yaw_deg": round(float(np.degrees(np.arctan2(vec[1, 1], vec[0, 1]))), 1),
                      "upper_xy": np.round(cp[upper, :2].mean(axis=0), 3).tolist(),
                      "points": {"foliage": int(crown.sum()), "trunk": int(trunk.sum())}})

    for k in range(1, n+1):
        top_xy = lo+(np.argwhere(markers == k)[0][::-1]+.5)*CELL
        mine = (owner == k) & (np.linalg.norm(p[:, :2]-top_xy, axis=1) <= MAX_CROWN_R)
        if (mine & (lab == 3)).sum() >= MIN_CROWN_POINTS:
            add(mine & (lab == 3), mine & (lab == 2), top_xy)
    # Measured trunks that no crown claimed (canopy merged into a neighbour) get their own tree.
    loose = (lab == 2) & ~used
    grid = np.zeros(shape, bool)
    grid[ij[loose, 1], ij[loose, 0]] = True
    stems, count = ndimage.label(ndimage.binary_dilation(grid, iterations=1))
    stem = np.where(loose, stems[ij[:, 1], ij[:, 0]], 0)
    for k in range(1, count+1):
        trunk = stem == k
        if trunk.sum() < 15:
            continue
        txy = np.median(p[trunk, :2], axis=0)
        if any(np.linalg.norm(np.subtract(t["trunk_xy"], txy)) < 1.5 for t in trees):
            continue
        crown = (lab == 3) & (hag > 2.5) & (np.linalg.norm(p[:, :2]-txy, axis=1) <= 3.0)
        if crown.sum() >= MIN_CROWN_POINTS:
            add(crown, trunk, txy)
    return {"area_xy": [lo.tolist(), hi.tolist()], "cell_m": CELL, "tops_found": int(n), "trees": trees}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(HERE))
    from audit_ground import read_reference
    from build_terrain import SURFACE, WAYPOINTS
    ref = read_reference(RELEASE/"output/reference_map.pcd")
    src = np.load(RELEASE/"output/provenance.npz")["source_id"]
    with np.load(SURFACE) as s:
        g = filled_ground(s)
    out = segment(np.asarray(ref["xyzi"][:, :3]), np.asarray(ref["label"]), src, g, np.array(WAYPOINTS, float))
    print(json.dumps({k: v for k, v in out.items() if k != "trees"}), len(out["trees"]))
    for t in out["trees"]:
        print(t["id"], t["trunk_xy"], t["trunk_evidence"], t["crown_base_m"], t["crown_top_m"], t["crown_radii_m"], t["points"])
