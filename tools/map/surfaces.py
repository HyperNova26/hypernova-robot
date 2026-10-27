# SPDX-License-Identifier: Apache-2.0
"""Local surface evidence and graphs with a bounded number of neighbors."""

from __future__ import annotations

import numpy as np
import open3d as o3d
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def normal_features(points, radius, max_neighbors, min_neighbors, min_planarity):
    """Return consistently upward normals and a reliability mask.

    Planarity rejects isolated points and line-like neighborhoods, including
    Open3D's identity covariance fallback for insufficient local support.
    """
    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    pc.estimate_covariances(o3d.geometry.KDTreeSearchParamHybrid(
        radius=radius, max_nn=max_neighbors))
    covariance = np.asarray(pc.covariances)
    normals = np.empty_like(points)
    reliable = np.zeros(len(points), dtype=bool)
    tree = cKDTree(points)
    for start in range(0, len(points), 32768):
        end = min(start+32768, len(points))
        values, vectors = np.linalg.eigh(covariance[start:end])
        normals[start:end] = vectors[:, :, 0]
        planarity = (values[:, 1]-values[:, 0])/np.maximum(values[:, 2], 1e-12)
        count = tree.query_ball_point(points[start:end], radius, return_length=True)
        reliable[start:end] = (count >= min_neighbors) & (planarity >= min_planarity)
    normals[normals[:, 2] < 0] *= -1
    return normals, reliable


def surface_components(points, radius, max_neighbors, min_points,
                       normals=None, reliable=None, angle_deg=25., plane_distance=.08):
    """Connected surfaces, or spatial objects when normals are omitted.

    Unlike a radius-only DBSCAN neighborhood cache, at most max_neighbors
    edges per point enter this graph. Queries are also processed in batches.
    """
    count = len(points)
    if not count:
        return np.empty(0, dtype=np.int32)
    tree = cKDTree(points)
    rows, columns = [], []
    cosine = np.cos(np.radians(angle_deg))
    for start in range(0, count, 32768):
        end = min(start+32768, count)
        distance, neighbor = tree.query(points[start:end], k=max_neighbors+1,
                                         distance_upper_bound=radius)
        source = np.broadcast_to(np.arange(start, end)[:, None], neighbor.shape)
        valid = np.isfinite(distance) & (neighbor < count) & (source != neighbor)
        a, b = source[valid], neighbor[valid]
        if normals is not None:
            delta = points[b]-points[a]
            keep = (reliable[a] & reliable[b]
                    & (np.abs(np.einsum("ij,ij->i", normals[a], normals[b])) >= cosine)
                    & (np.abs(np.einsum("ij,ij->i", delta, normals[a])) <= plane_distance)
                    & (np.abs(np.einsum("ij,ij->i", delta, normals[b])) <= plane_distance))
            a, b = a[keep], b[keep]
        rows.append(a.astype(np.int32))
        columns.append(b.astype(np.int32))
    a, b = np.concatenate(rows), np.concatenate(columns)
    graph = sparse.coo_matrix((np.ones(len(a), dtype=np.uint8), (a, b)),
                              shape=(count, count)).tocsr()
    _, labels = connected_components(graph, directed=False)
    sizes = np.bincount(labels)
    labels[sizes[labels] < min_points] = -1
    return labels
