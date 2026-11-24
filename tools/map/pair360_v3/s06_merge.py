"""Step 6. Merge: pc_v2 wherever it has data, pc_v1 only where pc_v2 has none. No resampling.

pc_v2 coverage = 0.5 m cells holding >= 4 static pc_v2 returns, closed over small gaps and grown by one
cell. Every pc_v1 row inside that area is left out. Vehicles, noise and transient rows of both captures,
plus the hand-reviewed movable objects in decisions/route_review.json, are taken out of the static map.

pc_v1 floor: step 2 takes pc_v1 ground from the reviewed S-004 partition file, which leaves much floor as
obstacle (the aisle along the north edge of the parking lot, the road south of the start). Here the pc_v1
rows that go into the map also become ground when they lie within 0.12 m of the reviewed S-004 surface
(pc_v1 ground v1, the floor of mesh_v1), or, outside that surface, when the floor model calls them floor
by the pc_v2 ground rule in a 0.5 m cell holding >= 8 such rows (pc_v1_floor).

Second pass on the merged map (movable objects the per-capture steps left behind):
- the step-2 car detector runs again on the merged static map; removed neighbours no longer hide a car;
- every removed vehicle grows into touching obstacle returns below 2.3 m above the floor, up to 1 m, so the
  bumpers, sides and undersides the first boxes cut off go with it. Cells with returns 2.1-3.5 m high
  (shrub tops, low branches) stop the growth, so a hedge next to a car stays.

map_v3.pcd is the union of the three split files, one colour per class (config.CLASS_RGB):
ground from pc_v1 (green), ground from pc_v2 (blue), obstacle (orange), removed vehicles/transients (red).
The static map is label 1 + 2 (map_v3_ground + map_v3_obstacle); steps 7-8 read only those.

In : frames.map_xyzi, work/02_<pc>_labels.npy, work/02_<pc>_hag.npy, work/05_<pc>_transient.npy,
     decisions/route_review.json
Diagnostic: pc_v1_not_in_pc_v2.pcd = pc_v1 rows left out by the pc_v2-priority rule that lie more than
0.5 m from every pc_v2 return (what only the 2023 capture saw there). Not part of map_v3.

Out: results/map_v3/map_v3.pcd (+ _ground, _obstacle, _removed_dynamic), work/06_coverage.npz,
     results/map_v3/pc_v1_not_in_pc_v2.pcd,
     results/map_v3/manifest.json
"""
import numpy as np
from scipy import ndimage

from matplotlib.path import Path as Polygon
from scipy.spatial import cKDTree

from features import floor_model, vehicle_instances
from config import (CLASS_RGB, GROUND, GROUND_V1_SURFACE, MAP_DIR, MAP_VERSION, NOISE, OBSTACLE, PC, ROUTE_REVIEW,
                    SOURCE_ID, TRANSIENT, VEHICLE, work)
from frames import map_xyzi
from pcio import load_json, read_xyzi, save_json, write_pcd

CELL, MIN_RETURNS = 0.5, 4
LO = np.array([-130.0, 30.0])
SHAPE = (480, 480)


def coverage(xy):
    ij = np.floor((xy-LO)/CELL).astype(int)
    count = np.bincount(ij[:, 1]*SHAPE[1]+ij[:, 0], minlength=SHAPE[0]*SHAPE[1]).reshape(SHAPE)
    # Close 1 m gaps between scan lines; real holes (unscanned areas) stay open for pc_v1.
    return ndimage.binary_dilation(ndimage.binary_closing(count >= MIN_RETURNS, iterations=2))


def inside(mask, xy):
    ij = np.clip(np.floor((xy-LO)/CELL).astype(int), 0, np.array(SHAPE[::-1])-1)
    return mask[ij[:, 1], ij[:, 0]]


def reviewed(key, xy, hag):
    """Per-row class code (VEHICLE / TRANSIENT, 0 = untouched) from the demo-corridor review."""
    code = np.zeros(len(xy), np.uint32)
    for item in load_json(ROUTE_REVIEW)["items"]:
        if item["source"] not in (key, "any"):
            continue
        poly = np.asarray(item["polygon_xy"])
        box = np.flatnonzero(np.all((xy >= poly.min(axis=0)) & (xy <= poly.max(axis=0)), axis=1))
        lo, hi = item["hag_m"]
        box = box[(hag[box] > lo) & (hag[box] < hi)]
        box = box[Polygon(poly).contains_points(xy[box])]
        code[box] = VEHICLE if item["class"] == "vehicle" else TRANSIENT
    return code


def second_pass(xyz, label, hag, cell=.25, grow_m=1.0):
    """Relabel movable leftovers on the merged map in place; returns row counts."""
    static = np.flatnonzero(np.isin(label, (GROUND, OBSTACLE)))
    car_id, cars = vehicle_instances(xyz[static], hag[static], label[static] == GROUND, body_returns=1)
    found = static[(car_id > 0) & (label[static] == OBSTACLE)]
    label[found] = VEHICLE
    ij = np.floor((xyz[:, :2]-xyz[:, :2].min(axis=0))/cell).astype(np.int64)
    nx, ny = ij.max(axis=0)+1
    ids = ij[:, 1]*nx+ij[:, 0]

    def cells(mask):
        return np.bincount(ids[mask], minlength=nx*ny).reshape(ny, nx) > 0
    low = (label == OBSTACLE) & (hag < 2.3)
    open_ = cells(low) & ~cells((label == OBSTACLE) & (hag > 2.1) & (hag < 3.5))
    grown = ndimage.binary_closing(cells(label == VEHICLE), iterations=2)
    for _ in range(int(round(grow_m/cell))):
        grown |= ndimage.binary_dilation(grown, np.ones((3, 3), bool)) & open_
    residue = low & grown.ravel()[ids]
    label[residue] = VEHICLE
    return {"detector_cars": len(cars), "detector_rows": int(len(found)), "residue_rows": int(residue.sum())}


def pc_v1_floor(labels):
    """pc_v1 obstacle rows lying on the floor, by source row.

    Inside the reviewed S-004 surface (pc_v1 ground v1, raw frame): within 0.12 m of it. Elsewhere: the rule
    that defines pc_v2 ground in step 2 (|hag| < 0.16 m on a gentle floor), kept only in 0.5 m cells with
    >= 8 such rows. Where returns are sparse a few stray returns below the floor (pc_v1 has ghost returns
    there) pull the floor model down and would otherwise be taken for floor."""
    raw = np.asarray(read_xyzi(PC["pc_v1"])[:, :3], float)
    surface = np.load(GROUND_V1_SURFACE)
    sx, sy, height = surface["x"], surface["y"], surface["height"]
    c = np.round((raw[:, 0]-sx[0])/(sx[1]-sx[0])).astype(int)
    r = np.round((raw[:, 1]-sy[0])/(sy[1]-sy[0])).astype(int)
    on_grid = (c >= 0) & (c < len(sx)) & (r >= 0) & (r < len(sy))
    reference = np.full(len(raw), np.nan)
    reference[on_grid] = height[r[on_grid], c[on_grid]]
    reviewed_area = np.isfinite(reference)
    near_surface = reviewed_area & (np.abs(raw[:, 2]-np.nan_to_num(reference)) < .12)
    hag, smooth = floor_model(raw)
    model = (labels == OBSTACLE) & ~reviewed_area & (np.abs(hag) < .16) & smooth
    ij = np.floor((raw[:, :2]-raw[:, :2].min(axis=0))/.5).astype(np.int64)
    cell = ij[:, 1]*(ij[:, 0].max()+1)+ij[:, 0]
    dense = np.bincount(cell[model], minlength=cell.max()+1)[cell] >= 8
    return (labels == OBSTACLE) & (near_surface | (model & dense))


def colours(label, source):
    rgb = np.empty((len(label), 3), np.uint8)
    rgb[:] = CLASS_RGB["removed"]
    rgb[label == OBSTACLE] = CLASS_RGB["obstacle"]
    rgb[(label == GROUND) & (source == SOURCE_ID["pc_v1"])] = CLASS_RGB["ground_pc_v1"]
    rgb[(label == GROUND) & (source == SOURCE_ID["pc_v2"])] = CLASS_RGB["ground_pc_v2"]
    return rgb


def write(name, xyzi, label, source):
    return write_pcd(MAP_DIR/name, xyzi, label, source, colours(label, source))


def main():
    MAP_DIR.mkdir(parents=True, exist_ok=True)
    parts, report = [], {}
    clouds = {key: (map_xyzi(key), np.load(work(f"02_{key}_labels.npy")), np.load(work(f"05_{key}_transient.npy")),
                    np.load(work(f"02_{key}_hag.npy")).astype(float)) for key in ("pc_v2", "pc_v1")}
    p2, l2 = clouds["pc_v2"][:2]
    cover = coverage(p2[np.isin(l2, (GROUND, OBSTACLE)), :2])
    np.savez_compressed(work("06_coverage.npz"), origin_xy=LO, cell_m=CELL, pc_v2=cover)
    p1, l1 = clouds["pc_v1"][:2]
    left_out = np.flatnonzero(inside(cover, p1[:, :2]) & (l1 != NOISE))
    far, _ = cKDTree(p2[l2 != NOISE, :3]).query(p1[left_out, :3], distance_upper_bound=.5, workers=-1)
    only = left_out[np.isinf(far)]
    rgb = np.tile(np.array(CLASS_RGB["pc_v1_not_in_pc_v2"], np.uint8), (len(only), 1))
    only_sha = write_pcd(MAP_DIR/"pc_v1_not_in_pc_v2.pcd", p1[only], l1[only].astype(np.uint32),
                         np.full(len(only), SOURCE_ID["pc_v1"], np.uint32), rgb)
    for key, (p, labels, transient, hag) in clouds.items():
        use = np.ones(len(p), bool) if key == "pc_v2" else ~inside(cover, p[:, :2])
        floor = np.zeros(len(p), bool)
        if key == "pc_v1":
            floor = pc_v1_floor(labels) & use
            labels = np.where(floor, GROUND, labels).astype(labels.dtype)
        review = reviewed(key, p[:, :2], hag) * np.isin(labels, (GROUND, OBSTACLE))
        vehicle = (labels == VEHICLE) | (review == VEHICLE)
        gone_transient = (transient | (review == TRANSIENT)) & ~vehicle
        static = np.isin(labels, (GROUND, OBSTACLE)) & ~vehicle & ~gone_transient
        out = np.zeros(len(p), np.uint32)
        out[static] = np.where(labels[static] == GROUND, GROUND, OBSTACLE)
        out[vehicle] = VEHICLE
        out[gone_transient] = TRANSIENT
        keep = use & (out > 0)
        parts.append((p[keep], out[keep], np.full(keep.sum(), SOURCE_ID[key], np.uint32), hag[keep]))
        report[key] = {"rows": len(p), "used_area_rows": int(use.sum()), "map_rows": int((use & static).sum()),
                       "floor_rows_relabelled_ground": int((floor & static).sum()),
                       "vehicle_rows_removed": int((use & vehicle).sum()),
                       "transient_rows_removed": int((use & gone_transient).sum()),
                       "route_review_rows_removed": int((use & (review > 0)).sum()),
                       "noise_rows_removed": int((use & (labels == NOISE)).sum())}
    xyzi, label, source, hag = (np.concatenate(v) for v in zip(*parts))
    second = second_pass(np.asarray(xyzi[:, :3], float), label, hag)
    for key in report:
        mine = source == SOURCE_ID[key]
        report[key]["map_rows_after_second_pass"] = int((mine & np.isin(label, (GROUND, OBSTACLE))).sum())
    files = {f"{MAP_VERSION}.pcd": write(f"{MAP_VERSION}.pcd", xyzi, label, source)}
    for name, codes in (("ground", (GROUND,)), ("obstacle", (OBSTACLE,)), ("removed_dynamic", (VEHICLE, TRANSIENT))):
        m = np.isin(label, codes)
        files[f"{MAP_VERSION}_{name}.pcd"] = write(f"{MAP_VERSION}_{name}.pcd", xyzi[m], label[m], source[m])
    reg = load_json(work("03_register.json"))
    save_json(MAP_DIR/"manifest.json", {
        "map": MAP_VERSION, "frame": "pair360_map", "basis": reg["basis"],
        "rule": "pc_v2 wherever it has data (0.5 m cells, >=4 static returns); pc_v1 elsewhere, locally bent onto pc_v2 (step 4)",
        "pc_v1_floor_rule": "besides the S-004 partition, pc_v1 obstacle rows used in the map are ground within 0.12 m of the "
                            "reviewed S-004 surface, or outside it where the floor model calls them floor (|hag| < 0.16 m, "
                            "gentle) in 0.5 m cells holding >= 8 such rows",
        "contents": "map_v3.pcd = map_v3_ground + map_v3_obstacle + map_v3_removed_dynamic; static map = label 1 and 2",
        "fields": {"label": {"1": "ground", "2": "obstacle", "5": "removed vehicle", "7": "removed transient"},
                   "source": {"1": "pc_v1", "2": "pc_v2"},
                   "rgb": {k: list(v) for k, v in CLASS_RGB.items()}},
        "pc_v2_to_map": reg["pc_v2_to_map"], "inputs_sha256": reg["sha256"], "sources": report, "second_pass": second,
        "pc_v1_not_in_pc_v2": {"rows": int(len(only)), "of_left_out_rows": int(len(left_out)), "distance_m": .5,
                               "by_step2_label": {str(k): int(v) for k, v in zip(*np.unique(l1[only], return_counts=True))},
                               "sha256": only_sha},
        "route_review": ROUTE_REVIEW.relative_to(MAP_DIR.parents[1]).as_posix(),
        "pc_v2_coverage_m2": float(cover.sum()*CELL**2), "files_sha256": files})
    print(report, second, "pc_v2 coverage m2", cover.sum()*CELL**2)


if __name__ == "__main__":
    main()
