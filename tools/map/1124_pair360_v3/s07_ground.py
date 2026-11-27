"""Step 7. Ground surface on a 0.1 m grid from the merged ground points (map_v3_ground.pcd), inside the scope.

Scope (terrain_edits.json "scope"): 0.5 m cells holding >= 5 input returns (both captures, any label but noise),
closed by 1 m, opened by 3 m so scan scraps and thin arms of far returns drop out, closed by 3 m again so the
opening leaves no notches in the edge, minus the reviewed cut polygons, kept when the piece is >= 1000 m2 and
with holes < 100 m2 filled. The mesh exists only inside it (known = scope); the grid is the scope's bounding box.

Each cell takes the median floor height. Every scope cell then gets a height: gaps up to 1.5 m from measured
floor take a normalised Gaussian average of it; larger gaps (under removed cars, under dense vegetation, sparse
far floor) are filled from a pyramid of block averages (push-pull) and smoothed over 0.5 m, so there are no
holes. A light median + Gaussian filter removes single-return bumps, then a band up to 1 m on each side of the
pc_v2 coverage edge is smoothed. The report compares height mismatches across that edge before and after
smoothing. Reviewed curb lines then become vertical steps (edits.py): the grid alone would smooth a 0.15-0.3 m
curb into a 0.3-0.4 m wide ramp.

In : results/map_v3/map_v3_ground.pcd, frames.map_xyzi + work/02_<pc>_labels.npy (scope),
     work/06_coverage.npz, decisions/terrain_edits.json
Out: results/mesh_v3/ground_surface.npz (x, y, height, known = scope, measured, near_measured, source, pc_v2_area),
     results/mesh_v3/ground_surface.json
"""
import numpy as np
from scipy import ndimage

import edits
from config import MAP_DIR, MAP_VERSION, MESH_DIR, NOISE, work
from frames import map_xyzi
from pcio import read_labelled, save_json

STEP, FILL_M, BLEND_M = 0.1, 1.5, 1.0
COARSE_LO, COARSE_SHAPE = np.array([-130.0, 30.0]), (480, 480)   # 0.5 m cells, as step 6


def disk(radius_cells):
    k = int(np.ceil(radius_cells))
    yy, xx = np.mgrid[-k:k+1, -k:k+1]
    return np.hypot(xx, yy) <= radius_cells+1e-9


def coarse_scope(cfg):
    """Scope on the step-6 0.5 m grid (bool, COARSE_SHAPE) and its statistics."""
    cell = cfg["cell_m"]
    count = np.zeros(COARSE_SHAPE, np.int64)
    for key in ("pc_v1", "pc_v2"):
        xy = map_xyzi(key)[:, :2][np.load(work(f"02_{key}_labels.npy")) != NOISE]
        ij = np.floor((xy-COARSE_LO)/cell).astype(int)
        ok = np.all((ij >= 0) & (ij < np.array(COARSE_SHAPE[::-1])), axis=1)
        count += np.bincount(ij[ok, 1]*COARSE_SHAPE[1]+ij[ok, 0], minlength=count.size).reshape(COARSE_SHAPE)
    covered = count >= cfg["min_returns"]
    mask = ndimage.binary_opening(ndimage.binary_closing(covered, disk(cfg["close_m"]/cell)), disk(cfg["open_m"]/cell))
    mask = ndimage.binary_closing(np.pad(mask, 20), disk(cfg["close_after_open_m"]/cell))[20:-20, 20:-20]
    cx = COARSE_LO[0]+(np.arange(COARSE_SHAPE[1])+.5)*cell
    cy = COARSE_LO[1]+(np.arange(COARSE_SHAPE[0])+.5)*cell
    for cut in cfg["cut"]:
        mask &= ~edits.polygon_mask(cx, cy, cut["polygon_xy"])
    lab, n = ndimage.label(mask)
    area = ndimage.sum(mask, lab, range(1, n+1))*cell**2
    mask = np.isin(lab, 1+np.flatnonzero(area >= cfg["min_area_m2"]))
    holes = ndimage.binary_fill_holes(mask) & ~mask
    hlab, hn = ndimage.label(holes)
    harea = ndimage.sum(holes, hlab, range(1, hn+1))*cell**2
    mask |= np.isin(hlab, 1+np.flatnonzero(harea < cfg["fill_holes_below_m2"]))
    stats = {"covered_cells_m2": float(covered.sum()*cell**2), "pieces_dropped": int((area < cfg["min_area_m2"]).sum()),
             "pieces_dropped_m2": float(area[area < cfg["min_area_m2"]].sum()), "holes_filled": int((harea < cfg["fill_holes_below_m2"]).sum())}
    return mask, stats


def fine_scope(mask, cfg, x, y):
    """Coarse scope on the 0.1 m grid with smooth (bilinear) edges, cut polygons applied at full resolution."""
    cell = cfg["cell_m"]
    gx, gy = np.meshgrid(x, y)
    fine = ndimage.map_coordinates(mask.astype(np.float32), [(gy-COARSE_LO[1])/cell-.5, (gx-COARSE_LO[0])/cell-.5],
                                   order=1, mode="constant") >= .5
    for cut in cfg["cut"]:
        fine &= ~edits.polygon_mask(x, y, cut["polygon_xy"])
    return fine


def push_pull(h, valid):
    """Fill cells without data from a pyramid of 2x2 block averages, pulled back level by level (bilinear)."""
    levels = [(np.where(valid, h, 0.0), valid.astype(float))]
    while min(levels[-1][0].shape) > 2:
        v, w = levels[-1]
        v = np.pad(v, ((0, v.shape[0] % 2), (0, v.shape[1] % 2)))
        w = np.pad(w, ((0, w.shape[0] % 2), (0, w.shape[1] % 2)))
        levels.append((v[::2, ::2]+v[1::2, ::2]+v[::2, 1::2]+v[1::2, 1::2],
                       w[::2, ::2]+w[1::2, ::2]+w[::2, 1::2]+w[1::2, 1::2]))
    est = levels[-1][0]/np.maximum(levels[-1][1], 1e-9)
    for v, w in reversed(levels[:-1]):
        # fine cell i sits at coarse coordinate i/2 - 0.25 (cell centres)
        ri, ci = np.meshgrid(np.arange(v.shape[0])/2-.25, np.arange(v.shape[1])/2-.25, indexing="ij")
        up = ndimage.map_coordinates(est, [ri, ci], order=1, mode="nearest")
        a = np.minimum(w, 1.0)
        est = a*v/np.maximum(w, 1e-9)+(1-a)*up
    return est


def blend_coverage_seam(height, in_v2, known):
    """Smooth the coverage boundary and report absolute height mismatches before curb edits."""
    stats = {"band_cells_in_scope": 0, "samples": 0, "before_m_p50_p90": None, "after_m_p50_p90": None}
    if not in_v2.any() or in_v2.all():
        return height, stats

    # At each cell, only the transform for its own side gives a nonzero distance.
    edge = np.maximum(ndimage.distance_transform_edt(in_v2),
                      ndimage.distance_transform_edt(~in_v2))*STEP
    band = edge <= BLEND_M
    blended = np.where(band, ndimage.gaussian_filter(height, 5), height)
    stats["band_cells_in_scope"] = int((known & band).sum())

    # Sample horizontal and vertical crossings with two in-scope cells on each side.
    before, after = [], []
    for coverage, scope, original, smoothed in ((in_v2, known, height, blended),
                                                (in_v2.T, known.T, height.T, blended.T)):
        left, right = coverage[:, 1:-2], coverage[:, 2:-1]
        crossings = ((left != right) & (coverage[:, :-3] == left) & (coverage[:, 3:] == right)
                     & scope[:, :-3] & scope[:, 1:-2] & scope[:, 2:-1] & scope[:, 3:])
        row, col = np.nonzero(crossings)
        for grid, samples in ((original, before), (smoothed, after)):
            # Extrapolate each side's local slope by half a cell to the same edge midpoint.
            left_z = 1.5*grid[row, col+1] - .5*grid[row, col]
            right_z = 1.5*grid[row, col+2] - .5*grid[row, col+3]
            samples.append(np.abs(right_z-left_z))
    stats["samples"] = sum(len(samples) for samples in before)
    if stats["samples"]:
        stats["before_m_p50_p90"] = np.percentile(np.concatenate(before), [50, 90]).round(4).tolist()
        stats["after_m_p50_p90"] = np.percentile(np.concatenate(after), [50, 90]).round(4).tolist()
    return blended, stats


def main():
    MESH_DIR.mkdir(parents=True, exist_ok=True)
    review = edits.load()
    cfg = review["scope"]
    coarse, sstats = coarse_scope(cfg)
    rr, cc = np.nonzero(coarse)
    lo = COARSE_LO+np.array([cc.min(), rr.min()])*cfg["cell_m"]-1
    hi = COARSE_LO+(np.array([cc.max(), rr.max()])+1)*cfg["cell_m"]+1
    x, y = np.arange(lo[0], hi[0]+STEP/2, STEP), np.arange(lo[1], hi[1]+STEP/2, STEP)
    known = fine_scope(coarse, cfg, x, y)

    g = read_labelled(MAP_DIR/f"{MAP_VERSION}_ground.pcd")
    xyz, src = np.asarray(g["xyzi"][:, :3], float), np.asarray(g["source"])
    c = np.round((xyz[:, 0]-x[0])/STEP).astype(int)
    r = np.round((xyz[:, 1]-y[0])/STEP).astype(int)
    ok = (c >= 0) & (c < len(x)) & (r >= 0) & (r < len(y))
    xyz, src, key = xyz[ok], src[ok], r[ok]*len(x)+c[ok]
    order = np.lexsort((xyz[:, 2], key))
    cells, start, count = np.unique(key[order], return_index=True, return_counts=True)
    height = np.full((len(y), len(x)), np.nan)
    height.flat[cells] = xyz[order, 2][start+count//2]
    source = np.zeros(height.shape, np.uint8)
    source.flat[cells] = src[order][start+count//2]
    measured = np.isfinite(height)
    # Short gaps: normalised Gaussian of nearby floor. Larger gaps: push-pull, then smoothed over 0.5 m.
    dist = ndimage.distance_transform_edt(~measured)*STEP
    w = ndimage.gaussian_filter(measured.astype(float), 3)
    s = ndimage.gaussian_filter(np.nan_to_num(height), 3)/np.maximum(w, 1e-6)
    near = measured | ((dist <= FILL_M) & (w > 1e-3))
    h = np.where(measured, height, np.where(near, s, np.nan))
    filled = push_pull(np.nan_to_num(h), np.isfinite(h))
    far = ~near
    smooth = ndimage.gaussian_filter(filled, 5)
    h = np.where(far, smooth, filled)
    h = ndimage.gaussian_filter(ndimage.median_filter(h, size=3), .8)
    # Blend across the pc_v2 / pc_v1 seam.
    cov = np.load(work("06_coverage.npz"))
    gx, gy = np.meshgrid(x, y)
    ij = np.clip(np.floor((np.stack([gx, gy], -1)-cov["origin_xy"])/cov["cell_m"]).astype(int), 0,
                 np.array(cov["pc_v2"].shape[::-1])-1)
    in_v2 = cov["pc_v2"][ij[..., 1], ij[..., 0]]
    h, seam = blend_coverage_seam(h, in_v2, known)
    curbs = {}
    for curb in review["curbs"]:
        h, step = edits.curb_step(h, x, y, curb, review["curb_step_half_width_m"])
        curbs[curb["id"]] = {"cells": int(len(step)), "step_m_p10_p50_p90": np.percentile(step, [10, 50, 90]).round(3).tolist()}
    np.savez_compressed(MESH_DIR/"ground_surface.npz", x=x, y=y, height=h.astype("f4"), known=known,
                        measured=measured, near_measured=near, source=source, pc_v2_area=in_v2)
    inside = known.sum()
    save_json(MESH_DIR/"ground_surface.json", {
        "grid_m": STEP, "origin_xy": [float(x[0]), float(y[0])], "shape": list(h.shape),
        "scope": {**{k: v for k, v in cfg.items() if k not in ("purpose", "reviewed", "cut")},
                  "cut": [c_["id"] for c_ in cfg["cut"]], "area_m2": round(float(inside*STEP**2), 1), **sstats},
        "cells_in_scope": int(inside), "measured_cells_in_scope": int((measured & known).sum()),
        "short_gap_cells_in_scope": int((near & ~measured & known).sum()),
        "filled_cells_in_scope": int((far & known).sum()), "fill_short_max_m": FILL_M,
        "seam_blend_m": BLEND_M, "seam_continuity": seam, "curb_steps": curbs,
        "cells_by_source": {"pc_v1": int(((source == 1) & known).sum()), "pc_v2": int(((source == 2) & known).sum())}})
    print("scope m2", round(float(inside*STEP**2)), "measured", int((measured & known).sum()), "short gaps",
          int((near & ~measured & known).sum()), "filled", int((far & known).sum()), sstats, curbs)
    print("seam continuity", seam)


if __name__ == "__main__":
    main()
