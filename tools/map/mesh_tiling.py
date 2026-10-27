# SPDX-License-Identifier: Apache-2.0
"""Conforming tile boundaries for memory-bounded heightfield decimation."""

import numpy as np
import open3d as o3d


def boundary_edges(triangles):
    edges = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges.sort(axis=1)
    unique, count = np.unique(edges, axis=0, return_counts=True)
    if np.any(count > 2):
        raise ValueError("Non-manifold tile edges")
    return unique[count == 1]


def grid_xy(uv, meta):
    origin = np.asarray(meta.get("grid_origin", [meta["x0"], meta["y0"]]))
    offset = np.asarray(meta.get("grid_offset", [0, 0]))
    return origin+(offset+uv)*meta["resolution"]


def stitch_boundary(mesh, hf, meta):
    """Restore every original perimeter node before neighboring tiles weld.

    QEM's boundary_weight is a soft penalty. Snap its boundary vertices to
    source grid nodes, split long boundary edges, and recheck metric error
    afterwards. Adjacent tiles then have identical edges, without T-junctions.
    """
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    edges = boundary_edges(triangles)
    if not len(edges):
        raise ValueError("Tile has no outer boundary")
    boundary = np.unique(edges)
    uv = (vertices[boundary, :2]-[meta["x0"], meta["y0"]])/meta["resolution"]
    last = np.asarray(hf.shape[::-1])-1
    distances = np.column_stack((np.abs(uv[:, 0]), np.abs(uv[:, 0]-last[0]),
                                 np.abs(uv[:, 1]), np.abs(uv[:, 1]-last[1])))
    side = np.argmin(distances, axis=1)
    uv = np.rint(np.clip(uv, 0, last)).astype(int)
    uv[side == 0, 0], uv[side == 1, 0] = 0, last[0]
    uv[side == 2, 1], uv[side == 3, 1] = 0, last[1]
    vertices[boundary, :2] = grid_xy(uv, meta)
    vertices[boundary, 2] = hf[uv[:, 1], uv[:, 0]]
    mesh.remove_duplicated_vertices().remove_degenerate_triangles().remove_unreferenced_vertices()
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    edges = boundary_edges(triangles)
    uv_all = np.rint((vertices[:, :2]-[meta["x0"], meta["y0"]])/meta["resolution"]).astype(int)
    nodes = {tuple(uv_all[v]): int(v) for v in np.unique(edges)}
    extra_vertices = []
    split = {}
    for a, b in edges:
        first, end = uv_all[a], uv_all[b]
        same_x = first[0] == end[0] and first[0] in (0, last[0])
        same_y = first[1] == end[1] and first[1] in (0, last[1])
        if not (same_x or same_y):
            raise ValueError("Decimated tile boundary cut a corner or contains an interior hole")
        axis = 1 if same_x else 0
        distance = int(end[axis]-first[axis])
        if abs(distance) <= 1:
            continue
        step = 1 if distance > 0 else -1
        inserted = []
        for value in range(int(first[axis])+step, int(end[axis]), step):
            node = first.copy()
            node[axis] = value
            key = tuple(node)
            if key not in nodes:
                idx = len(vertices)+len(extra_vertices)
                nodes[key] = idx
                extra_vertices.append([*grid_xy(node, meta), float(hf[node[1], node[0]])])
            inserted.append(nodes[key])
        split[(int(a), int(b))] = inserted
    if split:
        faces = []
        for triangle in triangles:
            polygon = []
            changed = False
            for k in range(3):
                a, b = int(triangle[k]), int(triangle[(k+1) % 3])
                polygon.append(a)
                middle = split.get((min(a, b), max(a, b)), [])
                polygon.extend(middle if a < b else middle[::-1])
                changed |= bool(middle)
            if not changed:
                faces.append(triangle.tolist())
                continue
            center = len(vertices)+len(extra_vertices)
            extra_vertices.append(vertices[triangle].mean(axis=0).tolist())
            faces.extend([center, polygon[k], polygon[(k+1) % len(polygon)]] for k in range(len(polygon)))
        vertices = np.concatenate((vertices, np.asarray(extra_vertices)))
        mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),
                                         o3d.utility.Vector3iVector(np.asarray(faces, dtype=np.int32)))
    # Prove that the whole original perimeter survives as unit grid edges.
    edges = boundary_edges(np.asarray(mesh.triangles))
    uv = np.rint((np.asarray(mesh.vertices)[:, :2]-[meta["x0"], meta["y0"]])/meta["resolution"]).astype(int)
    if len(edges) != 2*(hf.shape[0]+hf.shape[1])-4 or not np.all(np.abs(uv[edges[:, 0]]-uv[edges[:, 1]]).sum(axis=1) == 1):
        raise ValueError("Tile perimeter is incomplete after boundary repair")
    return mesh
