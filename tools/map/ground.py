# SPDX-License-Identifier: Apache-2.0
"""Ground from two local plane hypotheses and trusted neighbor continuity."""

from __future__ import annotations

from collections import deque
import time

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

from surfaces import normal_features


def plane_candidates(points, normals, center, params):
    """Fit up to two supported planes; the denser plane has rank zero.

    Deterministic point-normal hypotheses permit a minority ground layer to
    survive a denser roof. No cell minimum or unconditional average is used.
    Coefficients describe z=a*(x-center.x)+b*(y-center.y)+c.
    """
    local = points.copy()
    local[:, :2] -= center
    median_normal = np.median(normals, axis=0)
    median_normal /= max(np.linalg.norm(median_normal), 1e-12)
    order = np.argsort(local @ median_normal, kind="stable")
    if len(order) > params["max_patch_points"]:
        order = order[np.linspace(0, len(order)-1, params["max_patch_points"], dtype=int)]
    local, normals = local[order], normals[order]
    minimum = params["min_plane_points"]
    cosine = np.cos(np.radians(params["normal_angle_deg"]))
    threshold = params["fit_distance_m"]
    result = []
    for _ in range(2):
        if len(local) < minimum:
            break
        anchors = np.linspace(0, len(local)-1, min(24, len(local)), dtype=int)
        average = np.median(normals, axis=0)
        average /= max(np.linalg.norm(average), 1e-12)
        trial_normals = np.vstack((normals[anchors], np.tile(average, (len(anchors), 1))))
        trial_points = np.tile(local[anchors], (2, 1))
        offsets = -np.einsum("ij,ij->i", trial_normals, trial_points)
        distance = np.abs(local @ trial_normals.T + offsets)
        agreement = normals @ trial_normals.T >= cosine
        votes = (distance <= threshold) & agreement
        inliers = votes[:, np.argmax(votes.sum(axis=0))]
        if inliers.sum() < minimum:
            break
        # Refit and reselect against all remaining points, keeping planes apart.
        for _ in range(3):
            xyz = local[inliers]
            xy = xyz[:, :2]-xyz[:, :2].mean(axis=0)
            spread = np.linalg.eigvalsh(xy.T @ xy/len(xy))
            if spread[0] < params["min_xy_spread_m"]**2:
                break
            coefficients = np.linalg.lstsq(np.column_stack((xyz[:, :2], np.ones(len(xyz)))),
                                           xyz[:, 2], rcond=None)[0]
            normal = np.array([-coefficients[0], -coefficients[1], 1.])
            normal /= np.linalg.norm(normal)
            residual = local[:, 2] - (local[:, :2] @ coefficients[:2]+coefficients[2])
            updated = (np.abs(residual)*normal[2] <= threshold) & (normals @ normal >= cosine)
            if updated.sum() < minimum:
                break
            if np.array_equal(updated, inliers):
                inliers = updated
                break
            inliers = updated
        else:
            xyz = local[inliers]
            coefficients = np.linalg.lstsq(np.column_stack((xyz[:, :2], np.ones(len(xyz)))),
                                           xyz[:, 2], rcond=None)[0]
        # A narrow line or vertical fragment is not a supported ground plane.
        xyz = local[inliers]
        xy = xyz[:, :2]-xyz[:, :2].mean(axis=0)
        spread = np.linalg.eigvalsh(xy.T @ xy/len(xy))
        if spread[0] < params["min_xy_spread_m"]**2:
            local, normals = local[~inliers], normals[~inliers]
            continue
        coefficients = np.linalg.lstsq(np.column_stack((xyz[:, :2], np.ones(len(xyz)))),
                                       xyz[:, 2], rcond=None)[0]
        error = np.abs(xyz[:, 2]-(xyz[:, :2] @ coefficients[:2]+coefficients[2]))
        slope = np.linalg.norm(coefficients[:2])
        distinct = all(abs(coefficients[2]-old[0][2]) >= params["layer_separation_m"]
                       for old in result)
        if (slope <= params["max_slope_m_per_m"] and distinct
                and np.quantile(error, .9) <= threshold*1.5):
            result.append((coefficients, len(xyz), float(np.median(error))))
        # Remove this surface even if it duplicates an already fitted layer.
        remaining = np.abs(local[:, 2]-(local[:, :2] @ coefficients[:2]+coefficients[2]))
        keep = remaining >= params["layer_separation_m"]
        local, normals = local[keep], normals[keep]
    return sorted(result, key=lambda record: -record[1])


def select_ground(planes, support, xy, shape, params):
    """Choose hypotheses by continuity with already trusted ground patches."""
    rows, cols = shape
    total = len(xy)
    selected = np.full(total, -1, dtype=np.int8)
    has_plane = support[:, 0] >= params["min_plane_points"]
    radius = params["seed_radius_m"]
    seed_nodes = np.flatnonzero(has_plane & (np.linalg.norm(xy, axis=1) <= radius))
    for node in seed_nodes:
        height = np.abs(planes[node, :, 2]-np.einsum("ij,j->i", planes[node, :, :2], xy[node]))
        valid = (support[node] >= params["min_plane_points"]) & (height <= params["seed_height_m"])
        options = np.flatnonzero(valid)
        if len(options) == 1 or (len(options) == 2 and abs(height[0]-height[1]) >= params["ambiguity_margin_m"]):
            selected[node] = options[np.argmin(height[options])]
    seeds = np.flatnonzero(selected >= 0)
    if not len(seeds):
        raise ValueError("No reliable ground seed near leveled origin; inspect ground parameters/frame")
    max_step = int(np.ceil(params["neighbor_radius_m"]/params["grid_m"]))
    offsets = [(di, dj) for di in range(-max_step, max_step+1)
               for dj in range(-max_step, max_step+1)
               if 0 < np.hypot(di, dj)*params["grid_m"] <= params["neighbor_radius_m"]+1e-9]
    offsets = np.array(sorted(offsets, key=lambda pair: pair[0]**2+pair[1]**2))

    def neighbors(node):
        ij = offsets + [node//cols, node % cols]
        keep = (ij[:, 0] >= 0) & (ij[:, 0] < rows) & (ij[:, 1] >= 0) & (ij[:, 1] < cols)
        return ij[keep, 0]*cols+ij[keep, 1]

    queue = deque()
    queued = np.zeros(total, dtype=bool)
    for seed in seeds:
        for node in neighbors(seed):
            if has_plane[node] and selected[node] < 0 and not queued[node]:
                queue.append(node)
                queued[node] = True
    cosine = np.cos(np.radians(params["normal_angle_deg"]))
    normals = np.concatenate((-planes[:, :, :2], np.ones((*planes.shape[:2], 1))), axis=2)
    normals /= np.linalg.norm(normals, axis=2, keepdims=True)
    ambiguous = np.zeros(total, dtype=bool)
    while queue:
        node = queue.popleft()
        queued[node] = False
        if selected[node] >= 0:
            continue
        adjacent = neighbors(node)
        trusted = adjacent[selected[adjacent] >= 0]
        if not len(trusted):
            continue
        choices = selected[trusted]
        delta = (xy[node]-xy[trusted])*.5
        other = planes[trusted, choices]
        expected = other[:, 2] + np.einsum("ij,ij->i", other[:, :2], delta)
        score = np.full(2, np.inf)
        for candidate in range(2):
            if support[node, candidate] < params["min_plane_points"]:
                continue
            plane = planes[node, candidate]
            predicted = plane[2] - delta @ plane[:2]
            gap = np.abs(predicted-expected)
            angle_ok = normals[trusted, choices] @ normals[node, candidate] >= cosine
            agreeing = (gap <= params["continuity_m"]) & angle_ok
            if np.mean(agreeing) >= params["neighbor_agreement_fraction"]:
                score[candidate] = float(np.median(gap))
        order = np.argsort(score)
        if not np.isfinite(score[order[0]]):
            continue
        if np.isfinite(score[order[1]]) and score[order[1]]-score[order[0]] < params["ambiguity_margin_m"]:
            ambiguous[node] = True
            continue
        selected[node] = order[0]
        ambiguous[node] = False
        for other_node in adjacent:
            if has_plane[other_node] and selected[other_node] < 0 and not queued[other_node]:
                queue.append(other_node)
                queued[other_node] = True
    return selected, len(seeds), ambiguous


def plane_reference(query, xy, coefficients, radius, bounded=True):
    """Blend overlapping trusted planes; never select a plane by query Z."""
    tree = cKDTree(xy)
    result = np.full(len(query), np.nan)
    for start in range(0, len(query), 65536):
        end = min(start+65536, len(query))
        distance, neighbor = tree.query(query[start:end], k=4,
                                         distance_upper_bound=radius if bounded else np.inf)
        valid = neighbor < len(xy)
        safe = np.minimum(neighbor, len(xy)-1)
        delta = query[start:end, None]-xy[safe]
        predicted = coefficients[safe, 2]+np.einsum("ijk,ijk->ij", coefficients[safe, :2], delta)
        weight = np.where(valid, 1/np.maximum(distance, .05)**2, 0.)
        weight_sum = weight.sum(axis=1)
        np.divide((predicted*weight).sum(axis=1), weight_sum,
                  out=result[start:end], where=weight_sum > 0)
    return result


def split_ground_planes(points, params):
    from pointcloud import cloud, grid_spec

    meta = grid_spec(points, params["grid_m"])
    ii, jj = np.indices(meta["shape"])
    xy = np.column_stack((meta["x0"]+jj.ravel()*meta["resolution"],
                          meta["y0"]+ii.ravel()*meta["resolution"]))
    pc = cloud(points).voxel_down_sample(params["voxel_m"])
    work = np.asarray(pc.points)
    print(f"[ground] normals on {len(work):,} downsampled points", flush=True)
    normals, reliable = normal_features(work, params["normal_radius_m"], params["normal_max_neighbors"],
                                        params["normal_min_neighbors"], params["min_planarity"])
    reliable &= normals[:, 2] >= 1/np.sqrt(1+params["max_slope_m_per_m"]**2)
    work, normals = work[reliable], normals[reliable]
    if len(work) < params["min_plane_points"]:
        raise ValueError("Too few supported upward surface points for ground extraction")
    tree = cKDTree(work[:, :2])
    planes = np.full((len(xy), 2, 3), np.nan)
    support = np.zeros((len(xy), 2), dtype=np.int32)
    errors = np.full((len(xy), 2), np.nan)
    progress = time.monotonic()
    for start in range(0, len(xy), 512):
        neighborhoods = tree.query_ball_point(xy[start:start+512], params["patch_radius_m"])
        for offset, neighbors in enumerate(neighborhoods):
            if len(neighbors) < params["min_plane_points"]:
                continue
            node = start+offset
            candidates = plane_candidates(work[neighbors], normals[neighbors], xy[node], params)
            for rank, (plane, count, error) in enumerate(candidates):
                planes[node, rank], support[node, rank], errors[node, rank] = plane, count, error
        if time.monotonic()-progress > 10:
            print(f"[ground] local planes {min(start+512, len(xy)):,}/{len(xy):,}", flush=True)
            progress = time.monotonic()
    print("[ground] selecting connected ground hypotheses", flush=True)
    selected, seed_count, ambiguous = select_ground(planes, support, xy, meta["shape"], params)
    accepted = np.flatnonzero(selected >= 0)
    coefficients = planes[accepted, selected[accepted]]
    reference = plane_reference(points[:, :2], xy[accepted], coefficients, params["patch_radius_m"])
    residual = points[:, 2]-reference
    mask = np.isfinite(reference) & (residual >= -params["below_m"]) & (residual <= params["above_m"])
    # Classifier reference may be estimated under occlusions; this does not
    # create points or set the final heightfield's measured-ground mask.
    surface = plane_reference(xy, xy[accepted], coefficients, np.inf, bounded=False).reshape(meta["shape"])
    meta.update({"method": "normal_planes_with_neighbor_selection",
                 "index_convention": "surface[i,j]: x=x0+j*resolution, y=y0+i*resolution",
                 "estimated_under_occlusions": True})
    report = {"method": meta["method"], "input_points": len(points),
              "analysis_points": len(pc.points), "reliable_upward_points": len(work),
              "patches": len(xy), "patches_with_candidates": int((support[:, 0] > 0).sum()),
              "patches_with_two_candidates": int((support[:, 1] > 0).sum()),
              "seed_patches": seed_count, "accepted_patches": len(accepted),
              "secondary_candidate_selected": int((selected == 1).sum()),
              "ambiguous_patches": int(ambiguous.sum()),
              "unresolved_patches": int((selected < 0).sum()),
              "ground_points": int(mask.sum()), "non_ground_points": int((~mask).sum()),
              "candidate_coefficients": "z=a*(x-patch_x)+b*(y-patch_y)+c; ranks sorted by support",
              "unresolved_policy": "no ground label without a nearby selected plane; no invented returns"}
    diagnostics = {"report": report, "patches": {"xy": xy, "planes": planes, "support": support,
                    "median_error_m": errors, "selected": selected, "ambiguous": ambiguous}}
    return mask, surface, meta, diagnostics
