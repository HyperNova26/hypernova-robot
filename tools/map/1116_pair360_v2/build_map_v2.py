"""map_v2: pc_v1 (S-004) + pc_v3 -> ground + obstacle point cloud, dynamic objects removed.

Classes: 1 ground, 2 obstacle (every other fixed return). Dropped and written to a
separate review cloud: vehicles (5) and transient objects (7) such as people or a
scanner trail. pc_v3 gets the per-area z offset measured against pc_v1 observed ground
(as in separate_ground.py); its rows in registration tiles with metre-level error are dropped.
Writes map_v2/pc/*.pcd, map_v2/pc/ground_correction.npz and map_v2/manifest.json.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
from scipy import ndimage
from matplotlib.path import Path as Polygon

from register_maps import FRAME_KEY, OUTPUT, ROOT, read_points, sources, transform
from separate_ground import SURFACE, fit_offsets, sample, stats, surface_lookup

OUT = ROOT/"map_v2"
V9_CONFIG = ROOT.parent/"ground_seperation/tools/map/continuous_ground_20261109_v9.json"
VOXEL = 0.08
GHOST_TILE_MEDIAN_M = 0.5   # registration holdout tiles worse than this are not trusted
GROUND, OBSTACLE, VEHICLE, TRANSIENT = 1, 2, 5, 7
VERSION_ID = {"pc_v1": 1, "pc_v3": 3}
TREE_AREA = ([-38.0, 150.0], [10.0, 205.0])   # demo route box + 20 m: trunk/foliage hints for tree shapes
# Change check on a 0.2 m grid. A return 0.12-3 m above ground is transient when the other
# capture measured the ground there (>= 3 ground returns per 0.5 m) yet has no raised return
# within OCC_REACH cells. pc_v1 is dense, so it needs 3 returns per cell to confirm a pc_v3
# object; pc_v3 is sparse, so one pc_v3 return keeps a pc_v1 object.
OCC_LO, OCC_CELL, OCC_SHAPE, OCC_REACH = np.array([-110.0, 40.0]), 0.2, (1050, 1000), 2
CONFIRM = {"pc_v1": 3, "pc_v3": 1}


def occupancy_index(xy, cell=OCC_CELL):
    shape = np.ceil(np.array(OCC_SHAPE)*OCC_CELL/cell).astype(int)
    ij = np.clip(np.floor((xy-OCC_LO)/cell).astype(int), 0, shape[::-1]-1)
    return ij[:, 1], ij[:, 0], tuple(shape)


def counts(xy, cell=OCC_CELL):
    r, c, shape = occupancy_index(xy, cell)
    return np.bincount(r*shape[1]+c, minlength=shape[0]*shape[1]).reshape(shape)


def write_pcd(path, xyzi, label, source):
    data = np.empty(len(label), dtype=[("xyzi", "<f4", (4,)), ("label", "<u4"), ("source", "<u4")])
    data["xyzi"], data["label"], data["source"] = xyzi, label, source
    header = ("VERSION 0.7\nFIELDS x y z intensity label source\nSIZE 4 4 4 4 4 4\nTYPE F F F F U U\nCOUNT 1 1 1 1 1 1\n"
              f"WIDTH {len(data)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(data)}\nDATA binary\n")
    with path.open("wb") as stream:
        stream.write(header.encode("ascii"))
        data.tofile(stream)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def in_polygons(xy, polygons):
    inside = np.zeros(len(xy), bool)
    for poly in polygons:
        poly = np.asarray(poly)
        box = np.flatnonzero(np.all((xy >= poly.min(axis=0)) & (xy <= poly.max(axis=0)), axis=1))
        inside[box[Polygon(poly).contains_points(xy[box])]] = True
    return inside


def load(key, frame, surf, info):
    """Map-frame rows of one capture, its merged labels, height above v9 ground and trust mask."""
    path = sources()[key]
    raw = np.array(read_points(path), dtype=float)
    codes = np.load(ROOT/f"classification/{key}_merged_labels.npy")
    raw[:, :3] = transform(raw[:, :3], np.array(frame["source_to_map"][FRAME_KEY[key]]))
    info.update(file=str(path.relative_to(ROOT.parent)), rows=len(raw), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    z_ref, observed = surface_lookup(surf, raw[:, :2])
    trusted = np.ones(len(raw), bool)
    if key == "pc_v3":
        bad = [t["tile_xy"] for t in json.loads((OUTPUT/"registration_pc_v3.json").read_text())["holdout_tiles"]
               if t["median_m"] > GHOST_TILE_MEDIAN_M]
        tiles = np.floor(raw[:, :2]/10).astype(int)
        trusted = ~np.isin(tiles[:, 0]*10000+tiles[:, 1], [a*10000+b for a, b in bad])
        # Per-area z offset from pc_v3 ground over pc_v1 observed ground (holdout: 20% of cells).
        xy, dz = raw[:, :2], raw[:, 2]-z_ref
        use = (codes == 1) & observed & (np.abs(dz) < 1.0) & trusted
        lo = np.floor(xy.min(axis=0)/5.0)*5.0
        shape = tuple((np.floor((xy.max(axis=0)-lo)/5.0).astype(int)+1)[::-1])
        cell = np.floor((xy-lo)/5.0).astype(int) @ np.array([1, shape[1]])
        held = np.random.default_rng(1116).random(shape[0]*shape[1]) < .2
        test = use & held[cell]
        pred = sample(fit_offsets(xy, dz, lo, shape, use & ~held[cell])[0], xy[test], lo)
        ok = np.isfinite(pred)
        field, measured = fit_offsets(xy, dz, lo, shape, use)
        corr = sample(field, xy, lo)
        trusted &= np.isfinite(corr)
        raw[:, 2] -= np.nan_to_num(corr)
        np.savez_compressed(OUT/"pc/ground_correction.npz", offset_m=field.astype("f4"), measured=measured,
                            origin_xy=lo, cell_m=5.0)
        info["registration_tiles_dropped"] = bad
        info["z_correction"] = {"cell_m": 5.0, "offset_range_m": [float(np.nanmin(field)), float(np.nanmax(field))],
                                "holdout_before": stats(dz[test][ok]), "holdout_after": stats(dz[test][ok]-pred[ok])}
    return raw, codes, raw[:, 2]-z_ref, observed, trusted


def main():
    (OUT/"pc").mkdir(parents=True, exist_ok=True)
    frame = json.loads((OUTPUT/"frame.json").read_text())
    surf = dict(np.load(SURFACE))
    parking = [v["polygon_xy"] for v in json.loads(V9_CONFIG.read_text(encoding="utf-8"))["vehicles"]]
    report = {"map": "map_v2", "frame": "pair360_map", "inputs": {}, "classes": {"1": "ground", "2": "obstacle"},
              "dropped": {"5": "vehicle: label 5, or pc_v3 returns 0.1-2.5 m above ground inside reviewed pc_v1 parking polygons",
                          "7": "transient: raised return absent from the other capture where that capture saw the ground",
                          "noise": "isolated returns (label 6)"}}
    data = {}
    for key in ("pc_v1", "pc_v3"):
        info = report["inputs"].setdefault(key, {})
        raw, codes, hag, observed, trusted = load(key, frame, surf, info)
        vehicle = codes == 5
        if key == "pc_v3":
            # Parked cars occupy the same stalls; pc_v3 cars there were often missed by the detector.
            vehicle |= (codes != 1) & in_polygons(raw[:, :2], parking) & ~(hag > 2.5) & ~(hag < .1)
        raised = (codes != 1) & (codes != 6) & ~vehicle & trusted & (hag > .12) & (hag < 3.0)
        data[key] = dict(raw=raw, codes=codes, observed=observed, trusted=trusted, vehicle=vehicle, raised=raised,
                         raised_count=counts(raw[raised, :2]),
                         ground_count=counts(raw[(codes == 1) & trusted, :2], cell=.5))
    for key, other in (("pc_v1", "pc_v3"), ("pc_v3", "pc_v1")):
        d, o = data[key], data[other]
        confirmed = ndimage.binary_dilation(o["raised_count"] >= CONFIRM[other], iterations=OCC_REACH)
        # One cell of slack: a capture's own carrier leaves a ground shadow along its path.
        seen = ndimage.binary_dilation(o["ground_count"] >= 3)
        r, c, _ = occupancy_index(d["raw"][:, :2])
        r5, c5, _ = occupancy_index(d["raw"][:, :2], cell=.5)
        seen_here = seen[r5, c5] | (d["observed"] if key == "pc_v3" else False)   # v9 observed = pc_v1 saw the floor
        d["transient"] = d["raised"] & seen_here & ~confirmed[r, c]
    keep_xyzi, keep_label, keep_source, gone_xyzi, gone_label, gone_source, tree_xyz, tree_label = ([] for _ in range(8))
    for key, d in data.items():
        raw, codes, trusted, vehicle, transient = d["raw"], d["codes"], d["trusted"], d["vehicle"], d["transient"]
        noise = codes == 6
        ground = (codes == 1) & trusted & ~vehicle
        if key == "pc_v3":
            ground &= ~d["observed"]      # pc_v1 already measured these cells
        obstacle = (codes != 1) & ~vehicle & ~transient & ~noise & trusted
        sel = ground | obstacle
        keep_xyzi.append(raw[sel].astype("f4"))
        keep_label.append(np.where(ground, GROUND, OBSTACLE)[sel].astype(np.uint32))
        keep_source.append(np.full(sel.sum(), VERSION_ID[key], np.uint32))
        gone = (vehicle | transient) & trusted
        gone_xyzi.append(raw[gone].astype("f4"))
        gone_label.append(np.where(vehicle[gone], VEHICLE, TRANSIENT).astype(np.uint32))
        gone_source.append(np.full(gone.sum(), VERSION_ID[key], np.uint32))
        hint = np.isin(codes, (2, 3)) & ~transient & trusted & np.all((raw[:, :2] >= TREE_AREA[0]) & (raw[:, :2] <= TREE_AREA[1]), axis=1)
        tree_xyz.append(raw[hint, :3].astype("f4"))
        tree_label.append(codes[hint])
        report["inputs"][key].update(ground_rows=int(ground.sum()), obstacle_rows=int(obstacle.sum()),
                                     vehicle_rows_dropped=int(vehicle.sum()), transient_rows_dropped=int(transient.sum()),
                                     noise_rows_dropped=int(noise.sum()), untrusted_rows_dropped=int((~trusted).sum()))
        print(key, {k: v for k, v in report["inputs"][key].items() if k.endswith("rows") or k.endswith("dropped")}, flush=True)
    xyzi, label, source = np.concatenate(keep_xyzi), np.concatenate(keep_label), np.concatenate(keep_source)
    cells = np.floor(xyzi[:, :3]/VOXEL).astype(np.int64)
    cells -= cells.min(axis=0)
    dims = cells.max(axis=0)+1
    voxel_key = ((cells[:, 0]*dims[1]+cells[:, 1])*dims[2]+cells[:, 2])*4+label
    _, first = np.unique(voxel_key, return_index=True)   # pc_v1 rows come first, so they win
    first.sort()
    xyzi, label, source = xyzi[first], label[first], source[first]
    files = {"map_v2.pcd": write_pcd(OUT/"pc/map_v2.pcd", xyzi, label, source)}
    for name, code in (("map_v2_ground.pcd", GROUND), ("map_v2_obstacle.pcd", OBSTACLE)):
        m = label == code
        files[name] = write_pcd(OUT/f"pc/{name}", xyzi[m], label[m], source[m])
    np.savez_compressed(OUT/"pc/tree_points.npz", xyz=np.concatenate(tree_xyz), label=np.concatenate(tree_label))
    gone = np.concatenate(gone_xyzi)
    files["map_v2_removed_dynamic.pcd"] = write_pcd(OUT/"pc/map_v2_removed_dynamic.pcd", gone,
                                                    np.concatenate(gone_label), np.concatenate(gone_source))
    report.update(voxel_m=VOXEL, rows=len(label), ground_rows=int((label == GROUND).sum()),
                  obstacle_rows=int((label == OBSTACLE).sum()),
                  rows_by_source={f"pc_v{v}": int((source == v).sum()) for v in (1, 3)},
                  removed_dynamic_rows=len(gone), files_sha256=files)
    (OUT/"manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("inputs", "dropped")}, indent=1))


if __name__ == "__main__":
    main()
