"""Step 1. Check both inputs: hash, point count, extent, density, intensity range (native frames, no change).

In : data/raw/pc_v1_*.ply, data/raw/pc_v2_*.pcd
Out: results/map_v3/work/01_inputs.json
"""
import numpy as np
from scipy.spatial import cKDTree

from config import PC, work
from pcio import read_xyzi, save_json, sha256


def describe(path):
    p = read_xyzi(path)
    xyz = np.asarray(p[:, :3], float)
    cells = np.unique(np.floor(xyz[:, :2]/0.5).astype(np.int64), axis=0)
    sample = xyz[np.random.default_rng(0).choice(len(xyz), min(len(xyz), 200000), replace=False)]
    spacing = cKDTree(xyz).query(sample, k=2, workers=-1)[0][:, 1]
    return {"file": path.name, "sha256": sha256(path), "points": len(xyz),
            "native_xyz_min": xyz.min(axis=0).round(2).tolist(), "native_xyz_max": xyz.max(axis=0).round(2).tolist(),
            "area_m2_0.5m_cells": len(cells)*0.25, "points_per_m2": round(len(xyz)/(len(cells)*0.25), 1),
            "median_spacing_m": round(float(np.median(spacing)), 4),
            "intensity_p1_p50_p99": np.percentile(p[:, 3], [1, 50, 99]).round(1).tolist()}


def main():
    report = {key: describe(path) for key, path in PC.items()}
    save_json(work("01_inputs.json"), report)
    for key, r in report.items():
        print(key, r["points"], "pts", r["points_per_m2"], "pts/m2", "spacing", r["median_spacing_m"], "m")


if __name__ == "__main__":
    main()
