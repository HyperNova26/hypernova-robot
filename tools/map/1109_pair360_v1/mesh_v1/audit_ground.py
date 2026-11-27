"""Compare released hfield heights with reference_map ground and list review zones.

Needs numpy only (no MuJoCo). Heights use MuJoCo's hfield triangulation, the same
formula verify_terrain.py checks against mj_ray. Reads sources; writes two JSON files.
python audit_ground.py [--downloads <Downloads 폴더>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent
sys.path.insert(0, str(RELEASE))
from register_maps import DOWNLOADS, FRAME_KEY, read_points, sources, transform

SCENE = HERE / "scene"
NAMES = ["unknown", "ground", "trunk", "foliage", "structure", "vehicle", "noise"]
TILE = 10.0
# Go2 leg and torso band above the simulated floor (m).
OBSTACLE_BAND = (0.10, 0.60)


def load_hfields(scene=SCENE):
    root = ET.parse(scene/"scene.xml").getroot()
    sizes = {h.attrib["name"]: (h.attrib["file"], np.array(h.attrib["size"].split(), float))
             for h in root.findall("./asset/hfield")}
    fields = []
    for geom in root.findall("./worldbody/geom[@type='hfield']"):
        file, (rx, ry, span, _) = sizes[geom.attrib["hfield"]]
        cx, cy, zmin = np.array(geom.attrib["pos"].split(), float)
        raw = (scene/file).read_bytes()
        nrow, ncol = np.frombuffer(raw[:8], "<i4")
        heights = zmin + span*np.frombuffer(raw[8:], "<f4").reshape(nrow, ncol).astype(float)
        fields.append(dict(x0=cx-rx, x1=cx+rx, y0=cy-ry, y1=cy+ry, h=heights))
    return fields


def sim_height(fields, xy):
    """Top hfield surface under each XY (what a downward ray hits); NaN if none."""
    top = np.full(len(xy), -np.inf)
    covers = np.zeros(len(xy), np.uint8)
    order = np.argsort(xy[:, 0])
    xs = xy[order, 0]
    for f in fields:
        lo, hi = np.searchsorted(xs, f["x0"], side="left"), np.searchsorted(xs, f["x1"], side="right")
        idx = order[lo:hi]
        idx = idx[(xy[idx, 1] >= f["y0"]) & (xy[idx, 1] <= f["y1"])]
        if not len(idx):
            continue
        h = f["h"]
        nrow, ncol = h.shape
        gx = (xy[idx, 0]-f["x0"])/(f["x1"]-f["x0"])*(ncol-1)
        gy = (xy[idx, 1]-f["y0"])/(f["y1"]-f["y0"])*(nrow-1)
        c, r = np.minimum(gx.astype(int), ncol-2), np.minimum(gy.astype(int), nrow-2)
        u, v = gx-c, gy-r
        upper = v >= u
        z = np.where(upper,
                     (1-v)*h[r, c] + u*h[r+1, c+1] + (v-u)*h[r+1, c],
                     (1-u)*h[r, c] + v*h[r+1, c+1] + (u-v)*h[r, c+1])
        top[idx] = np.maximum(top[idx], z)
        covers[idx] += 1
    top[covers == 0] = np.nan
    return top, covers


def read_reference(path):
    with path.open("rb") as stream:
        for line in stream:
            if line.startswith(b"DATA"):
                break
        offset = stream.tell()
    return np.memmap(path, dtype=[("xyzi", "<f4", (4,)), ("label", "<u4")], offset=offset, mode="r")


def summary(d):
    if not len(d):
        return {"points": 0}
    a = np.abs(d)
    q = np.percentile(d, [1, 5, 25, 50, 75, 95, 99])
    return {"points": int(len(d)), "mean_m": round(float(d.mean()), 4), "std_m": round(float(d.std()), 4),
            "p01_p05_p25_median_p75_p95_p99_m": [round(float(v), 4) for v in q],
            "abs_within_m": {k: round(float((a <= float(k)).mean()), 4) for k in ("0.02", "0.05", "0.10", "0.25")},
            "above_hfield_gt_0.10m": int((d > .10).sum()), "below_hfield_lt_-0.10m": int((d < -.10).sum())}


def route_distance(route, xy):
    best = np.full(len(xy), np.inf)
    for a, b in zip(route, route[1:]):
        ab = b-a
        t = np.clip(((xy-a)@ab)/(ab@ab), 0, 1)
        best = np.minimum(best, np.linalg.norm(xy-(a+t[:, None]*ab), axis=1))
    return best


def tiles(xy, weights=None):
    keys = np.floor(xy/TILE).astype(int)
    cells, inverse = np.unique(keys, axis=0, return_inverse=True)
    return cells, inverse.ravel()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads", type=Path, default=DOWNLOADS)
    args = ap.parse_args()
    fields = load_hfields()
    manifest = json.loads((SCENE/"manifest.json").read_text(encoding="utf-8"))
    route = np.asarray(manifest["route_xyz_m"])
    route_xy = route[:, :2]
    ctx_lo, ctx_hi = np.array(manifest["context"]["bounds_xy"]).T
    bounds = [min(f["x0"] for f in fields), max(f["x1"] for f in fields),
              min(f["y0"] for f in fields), max(f["y1"] for f in fields)]

    # 0. Decoding check: route waypoints carry the floor height used at build time.
    route_h, _ = sim_height(fields, route_xy)
    decode_err = float(np.nanmax(np.abs(route_h-route[:, 2])))

    # 1. Reference ground (class 1) against the simulated floor.
    ref_path = RELEASE/"output/reference_map.pcd"
    ref = read_reference(ref_path)
    prov = np.load(RELEASE/"output/provenance.npz")["source_id"]
    ground = np.flatnonzero(ref["label"] == 1)
    xyz = ref["xyzi"][ground, :3].astype(float)
    h, covers = sim_height(fields, xyz[:, :2])
    ok = np.isfinite(h)
    d = xyz[ok, 2]-h[ok]
    near = route_distance(route_xy, xyz[ok, :2]) <= 3.0
    by_source = {name: summary(d[prov[ground][ok] == sid]) for sid, name in enumerate(("pc_v1", "pc_v3", "pc_v2"))}
    multi = covers[ok] > 1
    cells, inv = tiles(xyz[ok, :2])
    tile_rows = []
    for k, cell in enumerate(cells):
        dk = d[inv == k]
        if len(dk) < 200:
            continue
        tile_rows.append({"tile_xy_min_m": (cell*TILE).tolist(), "points": int(len(dk)),
                          "median_m": round(float(np.median(dk)), 3),
                          "p95_abs_m": round(float(np.percentile(np.abs(dk), 95)), 3),
                          "within_5cm": round(float((np.abs(dk) <= .05).mean()), 3)})
    tile_rows.sort(key=lambda t: -t["p95_abs_m"])
    alignment = {
        "frame": "pair360_map", "reference_map_sha256": manifest["reference_map_sha256"],
        "reference_file_sha256": hashlib.sha256(ref_path.read_bytes()).hexdigest(),
        "method": "z(reference ground point) - top hfield height at the same XY, MuJoCo triangle interpolation",
        "hfield_decode_check_route_max_abs_m": decode_err,
        "hfield_bounds_xy_m": bounds,
        "ground_points_total": int(len(ground)), "ground_points_on_hfield": int(ok.sum()),
        "ground_points_without_hfield": int((~ok).sum()),
        "all_on_hfield": summary(d), "within_3m_of_route": summary(d[near]), "by_source": by_source,
        "multi_hfield_cover_points": int(multi.sum()),
        "worst_10m_tiles_by_p95_abs": tile_rows[:15], "tiles_evaluated": len(tile_rows),
    }
    # Ground-only map (separate_ground.py): S-004 plus z-corrected new/old.
    gpath = RELEASE/"output/map_v1_ground.pcd"
    with gpath.open("rb") as stream:
        for line in stream:
            if line.startswith(b"DATA"):
                break
        offset = stream.tell()
    gm = np.memmap(gpath, dtype=[("xyzi", "<f4", (4,)), ("source", "<u4")], offset=offset, mode="r")
    gxyz = gm["xyzi"][:, :3].astype(float)
    gh, _ = sim_height(fields, gxyz[:, :2])
    gok = np.isfinite(gh)
    gd = gxyz[gok, 2]-gh[gok]
    alignment["ground_map"] = {"sha256": hashlib.sha256(gpath.read_bytes()).hexdigest(), "points": int(len(gm)),
                               "on_hfield": int(gok.sum()),
                               "by_source": {name: summary(gd[gm["source"][gok] == sid])
                                             for sid, name in enumerate(("pc_v1", "pc_v3", "pc_v2"))}}
    (HERE/"ground_alignment.json").write_text(json.dumps(alignment, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")

    # 2. Rows excluded from or uncertain in the reference map, in the map frame.
    frame = json.loads((RELEASE/"output/frame.json").read_text())
    zones = {}
    totals = {}
    for key, path in sources(args.downloads).items():
        codes = np.load(RELEASE/f"classification/{key}_merged_labels.npy")
        raw = read_points(path)
        pick = np.flatnonzero(np.isin(codes, (0, 2, 3, 4, 5)))
        p = transform(np.asarray(raw[pick, :3], float), np.array(frame["source_to_map"][FRAME_KEY[key]]))
        inside = (p[:, 0] >= bounds[0]) & (p[:, 0] <= bounds[1]) & (p[:, 1] >= bounds[2]) & (p[:, 1] <= bounds[3])
        p, c = p[inside], codes[pick][inside]
        hs, _ = sim_height(fields, p[:, :2])
        hag = p[:, 2]-hs
        on = np.isfinite(hag)
        band = on & (hag > OBSTACLE_BAND[0]) & (hag < OBSTACLE_BAND[1])
        in_ctx = np.all((p[:, :2] >= ctx_lo) & (p[:, :2] <= ctx_hi), axis=1)
        dist = route_distance(route_xy, p[:, :2])
        totals[key] = {NAMES[i]: {"in_hfield_bounds": int((c == i).sum()), "on_hfield": int(((c == i) & on).sum()),
                                  "in_go2_band": int(((c == i) & band).sum()),
                                  "in_go2_band_within_3m_route": int(((c == i) & band & (dist <= 3)).sum())}
                       for i in (0, 2, 3, 4, 5)}
        cells, inv = tiles(p[:, :2])
        for k, cell in enumerate(cells):
            m = inv == k
            z = zones.setdefault(tuple(cell.tolist()), {n: 0 for n in ("unknown_band", "vehicle_band", "vehicle_any",
                                                                     "trunk_band", "structure_band", "foliage_low",
                                                                     "unknown_off_hfield")} | {"min_route_dist_m": np.inf})
            z["unknown_band"] += int((m & band & (c == 0)).sum())
            z["vehicle_band"] += int((m & band & (c == 5)).sum())
            z["vehicle_any"] += int((m & (c == 5)).sum())
            # Trunks and structures are modelled only inside the context bounds.
            z["trunk_band"] += int((m & band & (c == 2) & ~in_ctx).sum())
            z["structure_band"] += int((m & band & (c == 4) & ~in_ctx).sum())
            z["foliage_low"] += int((m & band & (c == 3)).sum())
            z["unknown_off_hfield"] += int((m & ~on & (c == 0)).sum())
            z["min_route_dist_m"] = round(float(min(z["min_route_dist_m"], dist[m].min())), 1)
    rows = []
    for cell, z in zones.items():
        reasons = []
        if z["vehicle_band"] >= 50:
            reasons.append("vehicle_not_modelled")
        if z["unknown_band"] >= 300:
            reasons.append("unknown_obstacle_band")
        if z["trunk_band"] + z["structure_band"] >= 50:
            reasons.append("trunk_structure_outside_context")
        if z["foliage_low"] >= 300:
            reasons.append("low_foliage_or_shrub")
        if reasons:
            rows.append({"tile_xy_min_m": [cell[0]*TILE, cell[1]*TILE], "reasons": reasons, **z})
    rows.sort(key=lambda r: (r["min_route_dist_m"], -r["unknown_band"]-r["vehicle_band"]))
    review = {"frame": "pair360_map", "tile_m": TILE, "go2_band_above_hfield_m": list(OBSTACLE_BAND),
              "hfield_bounds_xy_m": bounds, "context_bounds_xy_m": manifest["context"]["bounds_xy"],
              "thresholds_points_per_tile": {"vehicle_band": 50, "unknown_band": 300,
                                             "trunk_structure_outside_context": 50, "foliage_low": 300},
              "totals_by_source": totals, "zones": rows}
    (HERE/"review_zones.json").write_text(json.dumps(review, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({k: alignment[k] for k in ("hfield_decode_check_route_max_abs_m", "ground_points_total",
                      "ground_points_on_hfield", "all_on_hfield", "within_3m_of_route")}, indent=1))
    print("review zones", len(rows))


if __name__ == "__main__":
    main()
