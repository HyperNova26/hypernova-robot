"""Ground-only map: S-004 measured ground plus z-corrected new/old ground where S-004 saw nothing.

new/old ground sits up to ±0.45 m off S-004 in a non-planar pattern, so one rigid
transform cannot fix it. A 5 m grid of median offsets, measured only on cells where
S-004 observed the ground, is smoothed and subtracted. A random 20% of cells is held
out to check the correction. Writes output/map_v1_ground.pcd (+ .json, map_v1_ground_correction.npz).
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
from scipy import ndimage

from register_maps import DOWNLOADS, FRAME_KEY, OUTPUT, ROOT, read_points, sources, transform

SURFACE = ROOT.parent / "ground_seperation/data/PAIR360_demo/20261109_canopy_floor_v9_smoothed/ground_surface.npz"
CELL = 5.0          # correction grid (m)
MIN_POINTS = 30     # per correction cell
MAX_FILL = 4        # cells (20 m) of extrapolation from measured offsets
VOXEL = 0.08


def surface_lookup(surf, xy):
    """Bilinear v9 height and observed flag; NaN outside the grid."""
    x, y, h = surf["x"], surf["y"], surf["height"].astype(float)
    gx, gy = (xy[:, 0]-x[0])/(x[1]-x[0]), (xy[:, 1]-y[0])/(y[1]-y[0])
    inside = (gx >= 0) & (gx <= len(x)-1) & (gy >= 0) & (gy <= len(y)-1)
    z = np.full(len(xy), np.nan)
    z[inside] = ndimage.map_coordinates(h, [gy[inside], gx[inside]], order=1)
    obs = np.zeros(len(xy), bool)
    r, c = np.round(gy[inside]).astype(int), np.round(gx[inside]).astype(int)
    obs[inside] = surf["observed_coarse"][np.minimum(r//5, surf["observed_coarse"].shape[0]-1),
                                          np.minimum(c//5, surf["observed_coarse"].shape[1]-1)]
    return z, obs


def fit_offsets(xy, dz, lo, shape, use):
    ij = np.floor((xy-lo)/CELL).astype(int)
    keys = ij[:, 1]*shape[1]+ij[:, 0]
    grid = np.full(shape, np.nan)
    order = np.argsort(keys[use], kind="stable")
    k, d = keys[use][order], dz[use][order]
    cells, starts, counts = np.unique(k, return_index=True, return_counts=True)
    for cell, s, n in zip(cells, starts, counts):
        if n >= MIN_POINTS:
            grid.flat[cell] = np.median(d[s:s+n])
    known = np.isfinite(grid)
    weight = ndimage.gaussian_filter(known.astype(float), 1.0)
    smooth = ndimage.gaussian_filter(np.where(known, grid, 0), 1.0)/np.maximum(weight, 1e-6)
    near, idx = ndimage.distance_transform_edt(~known, return_indices=True)
    filled = np.where(weight > .05, smooth, smooth[tuple(idx)])
    filled[near > MAX_FILL] = np.nan
    return filled, known


def sample(field, xy, lo):
    """Bilinear offset at XY (cell centres at (i+.5)*CELL); NaN next to unconstrained cells."""
    g = [(xy[:, 1]-lo[1])/CELL-.5, (xy[:, 0]-lo[0])/CELL-.5]
    value = ndimage.map_coordinates(np.nan_to_num(field), g, order=1, mode="nearest")
    value[ndimage.map_coordinates(np.isnan(field).astype(float), g, order=1, mode="nearest") > 0] = np.nan
    return value


def stats(d):
    a = np.abs(d)
    return {"points": int(len(d)), "median_m": round(float(np.median(d)), 4),
            "p50_abs_m": round(float(np.median(a)), 4), "p95_abs_m": round(float(np.percentile(a, 95)), 4),
            "within_10cm": round(float((a <= .10).mean()), 4)}


def write_pcd(path, xyzi, source):
    data = np.empty(len(source), dtype=[("xyzi", "<f4", (4,)), ("source", "<u4")])
    data["xyzi"], data["source"] = xyzi, source
    header = ("VERSION 0.7\nFIELDS x y z intensity source\nSIZE 4 4 4 4 4\nTYPE F F F F U\nCOUNT 1 1 1 1 1\n"
              f"WIDTH {len(data)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(data)}\nDATA binary\n")
    with path.open("wb") as stream:
        stream.write(header.encode("ascii"))
        data.tofile(stream)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--downloads", type=Path, default=DOWNLOADS)
    args = ap.parse_args()
    frame = json.loads((OUTPUT/"frame.json").read_text())
    surf = dict(np.load(SURFACE))
    rng = np.random.default_rng(1116)
    parts, report, fields = [], {"frame": "pair360_map", "surface": SURFACE.parent.name,
                                 "correction": {"cell_m": CELL, "min_points": MIN_POINTS, "max_fill_m": MAX_FILL*CELL}}, {}
    for sid, (key, path) in enumerate(((k, sources(args.downloads)[k]) for k in ("pc_v1", "pc_v3", "pc_v2"))):
        codes = np.load(ROOT/f"classification/{key}_merged_labels.npy")
        rows = np.flatnonzero(codes == 1)
        raw = np.asarray(read_points(path)[rows], float)
        raw[:, :3] = transform(raw[:, :3], np.array(frame["source_to_map"][FRAME_KEY[key]]))
        if key == "pc_v1":
            parts.append((raw, np.zeros(len(raw), np.uint32)))
            report["pc_v1"] = {"ground_rows": len(raw)}
            continue
        xy = raw[:, :2]
        z_ref, observed = surface_lookup(surf, xy)
        dz = raw[:, 2]-z_ref
        use = observed & (np.abs(dz) < 1.0)
        lo = np.floor(xy.min(axis=0)/CELL)*CELL
        shape = tuple((np.floor((xy.max(axis=0)-lo)/CELL).astype(int)+1)[::-1])
        # Holdout: drop 20% of correction cells, predict them from neighbours.
        cell_id = (np.floor((xy-lo)/CELL).astype(int) @ np.array([1, shape[1]]))
        held = rng.random(shape[0]*shape[1]) < .2
        test = use & held[cell_id]
        field_cv, _ = fit_offsets(xy, dz, lo, shape, use & ~held[cell_id])
        pred = sample(field_cv, xy[test], lo)
        ok = np.isfinite(pred)
        field, known = fit_offsets(xy, dz, lo, shape, use)
        corr = sample(field, xy, lo)
        fields[key] = dict(offset_m=field.astype("f4"), measured=known, origin_xy=lo, cell_m=CELL)
        fit = use & np.isfinite(corr)
        # Keep only where S-004 has no ground of its own and the offset is constrained.
        keep = ~observed & np.isfinite(corr)
        raw[:, 2] -= np.nan_to_num(corr)
        parts.append((raw[keep], np.full(keep.sum(), sid, np.uint32)))
        report[key] = {"ground_rows": len(raw), "on_s004_observed_cells": int(use.sum()),
                       "before": stats(dz[use]), "after_in_sample": stats(dz[fit]-corr[fit]),
                       "holdout_20pct_cells": {"before": stats(dz[test][ok]), "after": stats(dz[test][ok]-pred[ok]),
                                               "unpredicted_points": int((~ok).sum())},
                       "offset_range_m": [round(float(np.nanmin(field)), 3), round(float(np.nanmax(field)), 3)],
                       "kept_rows_outside_s004_observed": int(keep.sum()),
                       "dropped_unconstrained_rows": int((~observed & ~np.isfinite(corr)).sum())}
    xyzi = np.concatenate([p for p, _ in parts]).astype("f4")
    source = np.concatenate([s for _, s in parts])
    cells = np.floor(xyzi[:, :3]/VOXEL).astype(np.int64)
    cells -= cells.min(axis=0)
    key = (cells[:, 0]*(cells[:, 1].max()+1)+cells[:, 1])*(cells[:, 2].max()+1)+cells[:, 2]
    _, first = np.unique(key, return_index=True)
    first.sort()
    path = OUTPUT/"map_v1_ground.pcd"
    write_pcd(path, xyzi[first], source[first])
    np.savez_compressed(OUTPUT/"map_v1_ground_correction.npz", **{f"{k}_{n}": v for k, f in fields.items() for n, v in f.items()})
    report.update(voxel_m=VOXEL, output_rows=len(first),
                  output_rows_by_source=np.bincount(source[first], minlength=3).tolist(),
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (OUTPUT/"map_v1_ground.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
