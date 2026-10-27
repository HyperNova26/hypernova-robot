# SPDX-License-Identifier: Apache-2.0
"""Vehicle proposals from smooth roof patches, side normals, and geometry."""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from surfaces import normal_features, surface_components


def footprint(points):
    center = points[:, :2].mean(axis=0)
    xy = points[:, :2]-center
    _, axes = np.linalg.eigh(xy.T @ xy)
    axes = axes[:, ::-1]
    local = xy @ axes
    lo, hi = local.min(axis=0), local.max(axis=0)
    return center, axes, lo, hi


def classify_surfaces(points, surface, meta, params):
    from pointcloud import cloud, sample_height

    names = ("cars", "other")
    if not len(points):
        return {name: points.copy() for name in names}, []
    pc = cloud(points).voxel_down_sample(params["voxel_m"])
    work = np.asarray(pc.points)
    print(f"[classify] normals and surface patches on {len(work):,} points", flush=True)
    normals, reliable = normal_features(work, params["normal_radius_m"], params["normal_max_neighbors"],
                                        params["normal_min_neighbors"], params["min_planarity"])
    heights = work[:, 2]-sample_height(surface, meta, work[:, :2])
    # Grow roof surfaces separately: a chain of smoothed edge normals must not
    # wrap around a box and merge its roof with all of its side faces.
    roof_members = np.flatnonzero(reliable & (normals[:, 2] >= params["roof_normal_min_z"])
                                 & (heights >= params["car_height_m"][0])
                                 & (heights <= params["car_height_m"][1]))
    labels = np.full(len(work), -1, dtype=np.int32)
    labels[roof_members] = surface_components(
        work[roof_members], params["surface_radius_m"], params["graph_max_neighbors"],
        params["surface_min_points"], normals[roof_members], reliable[roof_members],
        params["surface_angle_deg"], params["surface_plane_distance_m"])
    types = np.full(len(work), 1, dtype=np.uint8)
    records = []
    tree = cKDTree(work[:, :2])
    # Sort once, rather than scanning the whole cloud for every surface.
    order = np.argsort(labels, kind="stable")
    ids, starts, sizes = np.unique(labels[order], return_index=True, return_counts=True)
    proposals = []
    for label, start, size in zip(ids, starts, sizes):
        if label < 0:
            continue
        members = order[start:start+size]
        if np.mean(normals[members, 2] >= params["roof_normal_min_z"]) < params["roof_patch_fraction"]:
            continue
        median_height = np.median(heights[members])
        if not params["car_height_m"][0] <= median_height <= params["car_height_m"][1]:
            continue
        center, axes, lo, hi = footprint(work[members])
        length, width = np.sort(hi-lo)[::-1]
        if (params["roof_min_length_m"] <= length <= params["car_length_m"][1]
                and params["roof_min_width_m"] <= width <= params["car_width_m"][1]):
            proposals.append((size, label, members, center, axes, lo, hi))
    print(f"[classify] checking {len(proposals):,} roof proposals", flush=True)
    for _, label, members, center, axes, lo, hi in sorted(proposals, key=lambda row: -row[0]):
        if np.mean(types[members] == 0) > .5:
            continue
        padding = params["car_footprint_padding_m"]
        bound = np.maximum(np.abs(lo-padding), np.abs(hi+padding))
        neighbors = np.asarray(tree.query_ball_point(center, np.linalg.norm(bound)), dtype=int)
        local = (work[neighbors, :2]-center) @ axes
        keep = (np.all((local >= lo-padding) & (local <= hi+padding), axis=1)
                & (heights[neighbors] >= params["object_min_height_m"])
                & (heights[neighbors] <= params["car_height_m"][1]+params["surface_plane_distance_m"]))
        candidate = neighbors[keep]
        if len(candidate) < params["surface_min_points"]:
            continue
        _, object_axes, object_lo, object_hi = footprint(work[candidate])
        length, width = np.sort(object_hi-object_lo)[::-1]
        height = float(np.quantile(heights[candidate], .98))
        roof = reliable[candidate] & (normals[candidate, 2] >= params["roof_normal_min_z"])
        side = reliable[candidate] & (np.abs(normals[candidate, 2]) <= params["vertical_normal_max_abs_z"])
        # Side normals should support one of the footprint's two axes; a full
        # closed box is deliberately unnecessary for a partially observed car.
        alignment = np.max(np.abs(normals[candidate, :2] @ object_axes), axis=1)
        side &= alignment >= np.cos(np.radians(params["car_side_angle_deg"]))
        roof_fraction, side_fraction = float(roof.mean()), float(side.mean())
        if not (params["car_length_m"][0] <= length <= params["car_length_m"][1]
                and params["car_width_m"][0] <= width <= params["car_width_m"][1]
                and params["car_height_m"][0] <= height <= params["car_height_m"][1]
                and roof_fraction >= params["car_min_roof_fraction"]
                and side_fraction >= params["car_min_side_fraction"]):
            continue
        types[candidate] = 0
        records.append({"cluster": int(label), "class": "cars", "method": "roof_side_normals_and_size",
                        "length_m": float(length), "width_m": float(width), "height_m": height,
                        "roof_normal_fraction": roof_fraction, "vertical_normal_fraction": side_fraction,
                        "downsampled_points": len(candidate)})
    # Keep spatial diagnostics for the remaining context, all labeled other.
    remaining = np.flatnonzero(types != 0)
    print("[classify] grouping remaining static context", flush=True)
    spatial = surface_components(work[remaining], params["object_radius_m"], params["graph_max_neighbors"],
                                 params["object_min_points"])
    order = np.argsort(spatial, kind="stable")
    ids, starts, sizes = np.unique(spatial[order], return_index=True, return_counts=True)
    for label, start, size in zip(ids, starts, sizes):
        if label < 0:
            continue
        members = remaining[order[start:start+size]]
        _, _, lo, hi = footprint(work[members])
        length, width = np.sort(hi-lo)[::-1]
        height = float(np.quantile(heights[members], .98))
        vertical = float(np.mean(reliable[members] & (np.abs(normals[members, 2]) <= params["vertical_normal_max_abs_z"])))
        records.append({"cluster": int(label), "class": "other",
                        "method": "bounded_spatial_graph_and_vertical_normals",
                        "length_m": float(length), "width_m": float(width), "height_m": height,
                        "vertical_normal_fraction": vertical, "downsampled_points": int(size)})
    # Bound label transfer in 3D so distant or unsupported returns remain other.
    distance, closest = cKDTree(work).query(points)
    full = np.full(len(points), 1, dtype=np.uint8)
    valid = distance <= params["label_transfer_voxels"]*params["voxel_m"]
    full[valid] = types[closest[valid]]
    return {name: points[full == k] for k, name in enumerate(names)}, records
