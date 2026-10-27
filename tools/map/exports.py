# SPDX-License-Identifier: Apache-2.0
"""MuJoCo, USD, mesh, and Nav2 exports of the same heightfield."""

from __future__ import annotations

import gc
import math
import struct
import time
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy import ndimage

from pointcloud import sample_height, write_yaml
from mesh_tiling import grid_xy, stitch_boundary


def export_mujoco(out, hf, meta, params):
    out = Path(out)
    xmin, xmax, ymin, ymax = params["walk_box"]
    res = meta["resolution"]
    # Aligned decimal bounds can differ from an integer grid index by a
    # floating-point ulp; do not accidentally discard a boundary row.
    j0 = max(0, int(np.ceil((xmin-meta["x0"])/res-1e-8)))
    j1 = min(hf.shape[1]-1, int(np.floor((xmax-meta["x0"])/res+1e-8)))
    i0 = max(0, int(np.ceil((ymin-meta["y0"])/res-1e-8)))
    i1 = min(hf.shape[0]-1, int(np.floor((ymax-meta["y0"])/res+1e-8)))
    if j1 <= j0 or i1 <= i0:
        raise ValueError("walk_box has no two-dimensional overlap with the heightfield")
    crop = hf[i0:i1+1, j0:j1+1]
    xmin, xmax = meta["x0"]+j0*res, meta["x0"]+j1*res
    ymin, ymax = meta["y0"]+i0*res, meta["y0"]+i1*res
    zmin, zmax = float(crop.min()), float(crop.max())
    zrange = max(zmax-zmin, 1e-6)
    # Verified by mj_ray on an asymmetric, non-square test: binary hfields
    # use rows increasing +Y. PNG/XML elevation conventions are different.
    data = crop.astype("<f4")
    with (out/"terrain.hfield").open("wb") as f:
        f.write(struct.pack("<ii", *data.shape))
        f.write(data.tobytes())
    size = f"{(xmax-xmin)/2:.10g} {(ymax-ymin)/2:.10g} {zrange:.10g} {params['base_m']:.10g}"
    pos = f"{(xmin+xmax)/2:.10g} {(ymin+ymax)/2:.10g} {zmin:.10g}"
    (out/"terrain.xml").write_text(
        '<mujoco model="pair360_parking">\n'
        '  <compiler angle="degree"/>\n'
        '  <asset>\n'
        f'    <hfield name="terrain" file="terrain.hfield" size="{size}"/>\n'
        '  </asset>\n'
        '  <worldbody>\n'
        f'    <geom name="terrain" type="hfield" hfield="terrain" pos="{pos}" rgba="0.55 0.6 0.5 1"/>\n'
        '    <light pos="0 0 20" dir="0 0 -1" directional="true"/>\n'
        '  </worldbody>\n'
        '</mujoco>\n')
    result = {"bounds_xy": [xmin, xmax, ymin, ymax], "shape": list(crop.shape),
              "z_min": zmin, "z_max": zmax, "binary_rows": "min_y_first",
              "walk_box_status": params["walk_box_status"]}
    write_yaml(out/"mujoco.yaml", result)
    return result


def mujoco_height(xml, xy):
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(Path(xml).resolve()))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    top = float(data.geom_xpos[0, 2])
    top += float(model.hfield_size[0, 2]) + 10
    geomid = np.array([-1], dtype=np.int32)
    distance = mujoco.mj_ray(model, data, np.array([*xy, top]), np.array([0., 0., -1.]),
                             None, 1, -1, geomid)
    if distance < 0:
        raise ValueError(f"MuJoCo ray missed terrain at {xy}")
    return float(top-distance)


def grid_mesh(hf, meta):
    rows, cols = hf.shape
    vertices = np.empty((rows*cols, 3), dtype=np.float64)
    view = vertices.reshape(rows, cols, 3)
    view[:, :, 0] = grid_xy(np.column_stack((np.arange(cols), np.zeros(cols))), meta)[:, 0]
    view[:, :, 1] = grid_xy(np.column_stack((np.zeros(rows), np.arange(rows))), meta)[:, 1, None]
    view[:, :, 2] = hf
    a = (np.arange(rows-1, dtype=np.int32)[:, None]*cols+np.arange(cols-1, dtype=np.int32)).ravel()
    triangles = np.empty((2*len(a), 3), dtype=np.int32)
    triangles[::2] = np.column_stack((a, a+1, a+cols+1))
    triangles[1::2] = np.column_stack((a, a+cols+1, a+cols))
    return o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),
                                     o3d.utility.Vector3iVector(triangles))


def mesh_error(mesh, hf, meta, params, seed, return_samples=False):
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    rng = np.random.default_rng(seed)
    low = np.array([meta["x0"], meta["y0"]])
    high = low+(np.array(hf.shape[::-1])-1)*meta["resolution"]
    top = max(float(hf.max()), float(np.asarray(mesh.vertices)[:, 2].max())) + 10
    misses = 0

    def errors(xy):
        nonlocal misses
        # Avoid numerical ambiguity exactly on outer boundary edges.
        # Float32 triangle/ray intersection is ambiguous exactly on shared
        # edges. Move probes by a few micrometers, also at outer boundaries.
        eps = max(1e-4*meta["resolution"], float(np.max(np.abs([low, high])))*np.finfo(np.float32).eps*8)
        xy = np.clip(xy+[eps, eps*.731], low+eps, high-eps)
        rays = np.column_stack((xy, np.full(len(xy), top), np.zeros((len(xy), 2)), -np.ones(len(xy))))
        hit = scene.cast_rays(o3d.core.Tensor(rays.astype(np.float32)))["t_hit"].numpy()
        misses += int((~np.isfinite(hit)).sum())
        return np.abs(top-hit-sample_height(hf, meta, xy))

    random_error = errors(rng.uniform(low, high, size=(params["random_samples"], 2)))
    maximum = float(random_error.max())
    count = len(random_error)
    # Check all source nodes and cell centers, as well as the candidate's own
    # vertices, so a small curb cannot disappear between the random probes.
    batch = params["check_batch_size"]
    for center in (False, True):
        rows, cols = np.array(hf.shape) - int(center)
        for start in range(0, rows*cols, batch):
            flat = np.arange(start, min(start+batch, rows*cols))
            xy = np.column_stack((flat % cols, flat // cols)).astype(float)
            xy = low+(xy+(0.5 if center else 0))*meta["resolution"]
            e = errors(xy)
            maximum = max(maximum, float(e.max()))
            count += len(e)
    vertices = np.asarray(mesh.vertices)
    for start in range(0, len(vertices), batch):
        e = errors(vertices[start:start+batch, :2])
        maximum = max(maximum, float(e.max()))
        count += len(e)
    report = {"max_error_m": maximum, "random_max_error_m": float(random_error.max()),
            "random_p95_error_m": float(np.percentile(random_error, 95)) if np.isfinite(random_error).all() else float("inf"),
            "random_samples": len(random_error), "total_probes": count, "ray_misses": misses,
            "validation": "vertical rays at seeded random XY, every grid node/cell center and candidate vertex; sampled bound"}
    return (report, random_error) if return_samples else report


def _decimate_tile(hf, meta, params, seed, log):
    raw = grid_mesh(hf, meta)
    raw_count = len(raw.triangles)
    attempts = []
    ratio = params["target_triangle_ratio"]
    for attempt in range(params["max_attempts"]):
        target = max(2, int(raw_count*min(ratio, 0.999)))
        log(f"QEM {attempt+1}/{params['max_attempts']}, target {target:,} / {raw_count:,} triangles")
        started = time.monotonic()
        mesh = raw.simplify_quadric_decimation(
            target_number_of_triangles=target,
            maximum_error=params["max_error_m"]**2,
            boundary_weight=params["boundary_weight"])
        try:
            mesh = stitch_boundary(mesh, hf, meta)
        except ValueError as exc:
            attempts.append({"target_triangles": target, "boundary_error": str(exc)})
            log(f"boundary rejected ({exc}); increasing target")
            del mesh
            gc.collect()
            ratio = min(0.999, ratio*2)
            continue
        log(f"QEM/boundary {time.monotonic()-started:.1f}s; checking rays")
        error, samples = mesh_error(mesh, hf, meta, params, seed, return_samples=True)
        attempts.append({"target_triangles": target, "triangles": len(mesh.triangles), **error})
        log(f"error max={error['max_error_m']:.6g}m, misses={error['ray_misses']}")
        if error["max_error_m"] <= params["max_error_m"]:
            return mesh, {"raw_triangles": raw_count, "triangles": len(mesh.triangles),
                          "vertices": len(mesh.vertices), "attempts": attempts, "raw_fallback": False, **error}, samples
        del mesh
        gc.collect()
        ratio = min(0.999, ratio*2)
    # Retain full fidelity in a difficult tile; never relax the metric limit.
    log("no acceptable decimation; retaining this tile's original grid")
    error, samples = mesh_error(raw, hf, meta, params, seed, return_samples=True)
    if error["max_error_m"] > params["max_error_m"]:
        raise ValueError(f"Original tile fails ray validation: {error}")
    return raw, {"raw_triangles": raw_count, "triangles": raw_count, "vertices": len(raw.vertices),
                 "attempts": attempts, "raw_fallback": True, **error}, samples


def decimate(hf, meta, params, seed):
    if not 0 < params["max_error_m"] <= 0.02:
        raise ValueError("isaac.max_error_m must be in (0, 0.02]")
    cells = params.get("tile_cells", 256)
    if not isinstance(cells, int) or not 16 <= cells <= 512:
        raise ValueError("isaac.tile_cells must be an integer in [16, 512]")
    rows, cols = hf.shape
    total = math.ceil((rows-1)/cells)*math.ceil((cols-1)/cells)
    raw_count = 2*(rows-1)*(cols-1)
    print(f"[isaac] {raw_count:,} raw triangles; {total} tiles, at most {2*cells*cells:,} raw triangles per QEM call", flush=True)
    parts_v, parts_t, reports, samples = [], [], [], []
    offset = 0
    for i0 in range(0, rows-1, cells):
        for j0 in range(0, cols-1, cells):
            tile = hf[i0:min(i0+cells, rows-1)+1, j0:min(j0+cells, cols-1)+1]
            tile_meta = {"x0": meta["x0"]+j0*meta["resolution"],
                         "y0": meta["y0"]+i0*meta["resolution"], "resolution": meta["resolution"],
                         "grid_origin": [meta["x0"], meta["y0"]], "grid_offset": [j0, i0]}
            tile_params = dict(params, random_samples=max(1, math.ceil(params["random_samples"]*(tile.shape[0]-1)*(tile.shape[1]-1)/((rows-1)*(cols-1)))))
            number = len(reports)+1
            log = lambda message: print(f"[isaac] tile {number}/{total} ({i0},{j0}): {message}", flush=True)
            mesh, report, random_errors = _decimate_tile(tile, tile_meta, tile_params, seed+number-1, log)
            parts_v.append(np.asarray(mesh.vertices).copy())
            parts_t.append(np.asarray(mesh.triangles).copy()+offset)
            offset += len(mesh.vertices)
            reports.append({"row_start": i0, "column_start": j0, "shape": list(tile.shape), **report})
            samples.append(random_errors)
            del mesh
    print(f"[isaac] welding {total} conforming tiles into one mesh", flush=True)
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.concatenate(parts_v)),
                                     o3d.utility.Vector3iVector(np.concatenate(parts_t)))
    del parts_v, parts_t
    mesh.remove_duplicated_vertices().remove_degenerate_triangles().remove_unreferenced_vertices()
    random_errors = np.concatenate(samples)
    report = {"raw_triangles": raw_count, "triangles": len(mesh.triangles), "vertices": len(mesh.vertices),
              "tile_cells": cells, "tile_count": total, "max_tile_raw_triangles": max(r["raw_triangles"] for r in reports),
              "raw_fallback_tiles": sum(r["raw_fallback"] for r in reports), "tiles": reports,
              "max_error_m": max(r["max_error_m"] for r in reports),
              "random_max_error_m": float(random_errors.max()), "random_p95_error_m": float(np.percentile(random_errors, 95)),
              "random_samples": len(random_errors), "total_probes": sum(r["total_probes"] for r in reports),
              "ray_misses": sum(r["ray_misses"] for r in reports),
              "validation": "per-tile vertical rays at stratified random XY, all source nodes/cell centers and candidate vertices after seam repair; exact-coordinate weld; sampled bound"}
    return mesh, report


def export_usd(path, mesh):
    from pxr import Gf, Usd, UsdGeom, UsdPhysics, Vt

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    terrain = UsdGeom.Mesh.Define(stage, "/Terrain")
    vertices = np.asarray(mesh.vertices).astype(np.float32)
    triangles = np.asarray(mesh.triangles).astype(np.int32)
    terrain.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(vertices))
    terrain.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(triangles), 3, dtype=np.int32)))
    terrain.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(triangles.ravel()))
    terrain.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    terrain.CreateExtentAttr([Gf.Vec3f(*vertices.min(axis=0).tolist()), Gf.Vec3f(*vertices.max(axis=0).tolist())])
    prim = terrain.GetPrim()
    UsdPhysics.CollisionAPI.Apply(prim).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr("none")
    stage.SetDefaultPrim(prim)
    stage.GetRootLayer().Save()


def export_isaac(out, hf, meta, params, seed):
    out = Path(out)
    mesh, report = decimate(hf, meta, params, seed)
    write_yaml(out/"mesh_report.yaml", report)
    print(f"[isaac] writing OBJ ({len(mesh.triangles):,} triangles)", flush=True)
    if not o3d.io.write_triangle_mesh(str(out/"terrain.obj"), mesh, write_vertex_normals=False,
                                     write_vertex_colors=False, write_triangle_uvs=False):
        raise RuntimeError("Cannot write terrain.obj")
    print("[isaac] writing USD (one static Mesh prim)", flush=True)
    export_usd(out/"terrain.usd", mesh)
    return report


def occupancy(hf, measured, meta, non_ground, params):
    image = np.full(hf.shape, 205, dtype=np.uint8)
    image[measured] = 254
    obstacles = np.zeros(hf.shape, dtype=bool)
    if len(non_ground):
        above = non_ground[:, 2]-sample_height(hf, meta, non_ground[:, :2])
        keep = (above >= params["min_height_m"]) & (above <= params["max_height_m"])
        ij = np.floor((non_ground[keep, :2]-[meta["x0"], meta["y0"]])/meta["resolution"]+1e-8).astype(int)
        good = (ij >= 0).all(axis=1) & (ij[:, 0] < hf.shape[1]) & (ij[:, 1] < hf.shape[0])
        obstacles[ij[good, 1], ij[good, 0]] = True
    if params["dilation_cells"]:
        obstacles = ndimage.binary_dilation(obstacles, structure=np.ones((3, 3)), iterations=params["dilation_cells"])
    image[obstacles] = 0
    return np.flipud(image)


def export_map2d(out, hf, measured, meta, non_ground, params):
    out = Path(out)
    image = occupancy(hf, measured, meta, non_ground, params)
    with (out/"map2d.pgm").open("wb") as f:
        f.write(f"P5\n{image.shape[1]} {image.shape[0]}\n255\n".encode())
        f.write(image.tobytes())
    write_yaml(out/"map2d.yaml", {"image": "map2d.pgm", "resolution": meta["resolution"],
                                 "origin": [meta["x0"], meta["y0"], 0.0], "negate": 0,
                                 "occupied_thresh": 0.65, "free_thresh": 0.25})
    return {"occupied_cells": int((image == 0).sum()), "free_cells": int((image == 254).sum()),
            "unknown_cells": int((image == 205).sum())}
