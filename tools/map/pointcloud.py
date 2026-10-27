# SPDX-License-Identifier: Apache-2.0
"""Point processing and the common, metric heightfield convention."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import open3d as o3d
import yaml
from scipy import ndimage
from scipy.interpolate import griddata
from scipy.spatial import QhullError
from scipy.spatial.transform import Rotation


def read_yaml(path):
    return yaml.safe_load(Path(path).read_text())


def write_yaml(path, value):
    Path(path).write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False))


def effective_config(config, quick=False):
    cfg = copy.deepcopy(config)
    cfg.pop("generated_from_data", None)
    if quick:
        q, p = cfg["quick"], cfg["processing"]
        p["clean"]["voxel_m"] = q["clean_voxel_m"]
        p["ground"]["voxel_m"] = q["ground_voxel_m"]
        p["classes"]["voxel_m"] = q["class_voxel_m"]
        p["heightfield"]["resolution_m"] = q["resolution_m"]
        p["isaac"]["random_samples"] = q["random_samples"]
    return cfg


def cloud(points):
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points)))


def save_cloud(path, points):
    # Open3D refuses to write an empty cloud; a valid empty ASCII PLY is useful.
    if not len(points):
        Path(path).write_text("ply\nformat ascii 1.0\nelement vertex 0\n"
                              "property double x\nproperty double y\nproperty double z\nend_header\n")
    elif not o3d.io.write_point_cloud(str(path), cloud(points), write_ascii=False):
        raise RuntimeError(f"Cannot write {path}")


def load_cloud(path):
    p = np.asarray(o3d.io.read_point_cloud(str(path)).points).copy()
    return p[np.isfinite(p).all(axis=1)]


def apply_transform(points, matrix):
    return np.asarray(points) @ matrix[:3, :3].T + matrix[:3, 3]


def level_cloud(points_map, cfg):
    p = cfg["processing"]["leveling"]
    t0 = np.asarray(cfg["T_demo_from_map_unleveled"], dtype=float)
    if t0.shape != (4, 4) or not np.allclose(t0[3], [0, 0, 0, 1]):
        raise ValueError("Invalid homogeneous transform")
    if not np.allclose(t0[:3, :3].T @ t0[:3, :3], np.eye(3), atol=2e-6):
        raise ValueError("Transform rotation is not orthonormal")
    points = apply_transform(points_map, t0)
    bounds = np.array([points.min(axis=0), points.max(axis=0)])
    origin_inside = bool(np.all(bounds[0, :2] <= 0) and np.all(bounds[1, :2] >= 0))
    if not origin_inside:
        raise ValueError("Origin is outside crop XY bounds: possible CloudCompare global shift")
    mask = (np.linalg.norm(points[:, :2], axis=1) <= p["radius_m"]) & (np.abs(points[:, 2]) < p["abs_z_m"])
    local = points[mask]
    if len(local) < p["min_points"]:
        raise ValueError("Too few ground candidates near origin: check frame/global shift")
    rng = np.random.default_rng(cfg["processing"]["seed"])
    if len(local) > p["max_fit_points"]:
        local = local[rng.choice(len(local), p["max_fit_points"], replace=False)]
    o3d.utility.random.seed(cfg["processing"]["seed"])
    plane, inliers = cloud(local).segment_plane(p["distance_threshold_m"], 3, p["iterations"])
    plane = np.asarray(plane)
    plane /= np.linalg.norm(plane[:3])
    if plane[2] < 0:
        plane = -plane
    if len(inliers) < p["min_points"]:
        raise ValueError("Too few leveling plane inliers")
    normal = plane[:3]
    axis = np.cross(normal, [0, 0, 1])
    tilt = float(np.arccos(np.clip(normal[2], -1, 1)))
    rot = Rotation.from_rotvec(axis / np.linalg.norm(axis) * tilt).as_matrix() if np.linalg.norm(axis) > 1e-12 else np.eye(3)
    leveling = np.eye(4)
    leveling[:3, :3] = rot
    # After rotating the normal to +Z, the plane equation is z + d = 0.
    leveling[2, 3] = plane[3]
    final = leveling @ t0
    result = apply_transform(points_map, final)
    check = local[inliers] @ rot.T + leveling[:3, 3]
    near = check[np.linalg.norm(check[:, :2], axis=1) <= p["origin_check_radius_m"], 2]
    if not len(near):
        raise ValueError("No measured plane inliers within origin check radius")
    z = float(np.median(near))
    if abs(z) > p["origin_z_tolerance_m"]:
        raise ValueError(f"Ground near origin is {z:.4f} m, outside tolerance")
    resolved = {
        "T_demo_from_map": final.tolist(), "T_level_from_unleveled": leveling.tolist(),
        "tilt_deg": float(np.degrees(tilt)), "plane_unleveled": plane.tolist(),
        "plane_inliers": len(inliers), "origin_inside_crop": origin_inside,
        "origin_ground_z_m": z, "bounds_map": [points_map.min(axis=0).tolist(), points_map.max(axis=0).tolist()],
        "bounds_demo": [result.min(axis=0).tolist(), result.max(axis=0).tolist()],
        "map_origin_in_demo": apply_transform(np.array([cfg["demo_frame"]["origin_in_map"]]), final)[0].tolist(),
        "warnings": ["Leveling tilt exceeds warning threshold"] if np.degrees(tilt) > p["warn_tilt_deg"] else [],
    }
    return result, resolved


def clean_cloud(points, params):
    pc = cloud(points).voxel_down_sample(params["voxel_m"])
    if len(pc.points) <= params["neighbors"]:
        raise ValueError("Cloud too small for statistical outlier removal")
    pc, _ = pc.remove_statistical_outlier(params["neighbors"], params["std_ratio"])
    return np.asarray(pc.points).copy()


def grid_spec(points, res, max_cells=16000000):
    lo = np.floor(points[:, :2].min(axis=0) / res) * res
    hi = np.ceil(points[:, :2].max(axis=0) / res) * res
    shape = (np.rint((hi - lo) / res).astype(int) + 1)[::-1]
    if min(shape) < 2 or np.prod(shape) > max_cells:
        raise ValueError(f"Invalid/oversize grid {tuple(shape)}; inspect crop or increase max_cells")
    return {"x0": float(lo[0]), "y0": float(lo[1]), "resolution": float(res), "shape": shape.tolist()}


def indices(points, meta):
    ij = np.floor((points[:, :2] - [meta["x0"], meta["y0"]]) / meta["resolution"] + 1e-8).astype(int)
    return ij[:, 1], ij[:, 0]


def nearest_fill(grid):
    valid = np.isfinite(grid)
    if not valid.any():
        raise ValueError("No measured cells")
    nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return grid[tuple(nearest)]


def sample_height(hf, meta, xy):
    """Piecewise linear interpolation on triangles (a,b,d), (a,d,c)."""
    uv = (np.asarray(xy) - [meta["x0"], meta["y0"]]) / meta["resolution"]
    uv = np.clip(uv, [0, 0], np.array(hf.shape[::-1]) - 1)
    j = np.minimum(uv[:, 0].astype(int), hf.shape[1] - 2)
    i = np.minimum(uv[:, 1].astype(int), hf.shape[0] - 2)
    fx, fy = uv[:, 0] - j, uv[:, 1] - i
    a, b, c, d = hf[i, j], hf[i, j+1], hf[i+1, j], hf[i+1, j+1]
    return np.where(fy <= fx, a + fx*(b-a) + fy*(d-b), a + fy*(c-a) + fx*(d-c))


def split_ground(points, params, diagnostics=None):
    from ground import split_ground_planes

    mask, surface, meta, details = split_ground_planes(points, params)
    if diagnostics is not None:
        diagnostics.update(details)
    return mask, surface, meta


def classify(points, surface, meta, params):
    from objects import classify_surfaces

    return classify_surfaces(points, surface, meta, params)


def build_heightfield(ground, bounds_points, params):
    meta = grid_spec(bounds_points, params["resolution_m"], params["max_cells"])
    i, j = indices(ground, meta)
    hf = np.full(meta["shape"], np.nan)
    flat = i * hf.shape[1] + j
    # Sorting z within each cell makes the grouped median fully vectorized.
    order = np.lexsort((ground[:, 2], flat))
    ids, starts, counts = np.unique(flat[order], return_index=True, return_counts=True)
    z = ground[order, 2]
    hf.ravel()[ids] = (z[starts+(counts-1)//2]+z[starts+counts//2])/2
    measured = np.isfinite(hf)
    filled = nearest_fill(hf)
    if params["fill"] == "linear" and measured.sum() >= 3:
        ii, jj = np.indices(hf.shape)
        # Linear only fills the convex hull; retain nearest outside it.
        try:
            linear = griddata(np.column_stack((ii[measured], jj[measured])), hf[measured],
                              np.column_stack((ii[~measured], jj[~measured])), method="linear")
            filled[~measured] = np.where(np.isfinite(linear), linear, filled[~measured])
        except QhullError as exc:
            raise ValueError("Ground samples are collinear; cannot linearly fill terrain") from exc
    elif params["fill"] not in ("linear", "nearest"):
        raise ValueError("heightfield.fill must be linear or nearest")
    hf = ndimage.median_filter(filled, size=params["median_window"])
    hf = hf.astype(np.float32)
    meta.update({"index_convention": "hf[i,j]: x=x0+j*resolution, y=y0+i*resolution; rows increase +y",
                 "aggregation": "median of ground points in [x,x+resolution) x [y,y+resolution)",
                 "shape": list(hf.shape), "dtype": "float32", "units": "m",
                 "z_min": float(hf.min()), "z_max": float(hf.max()),
                 "x_max": meta["x0"]+(hf.shape[1]-1)*meta["resolution"],
                 "y_max": meta["y0"]+(hf.shape[0]-1)*meta["resolution"],
                 "measured_cells": int(measured.sum()), "total_cells": int(hf.size),
                 "measured_mask": "heightfield_measured.npy"})
    return hf, measured, meta
