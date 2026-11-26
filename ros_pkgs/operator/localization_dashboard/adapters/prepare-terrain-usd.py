# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Display mesh for the dashboard from the Isaac Sim terrain USD (same pair360_map frame as mesh_v3).

Usage: python adapters/prepare-terrain-usd.py path/to/pair360_map_v3_usd [--cell 0.4]
Reads terrain_ground.usdc and terrain_obstacles.usdc (meshes only, world transforms applied).
Vertex clustering on a --cell grid keeps the browser mesh small; display only, not a collision surface.
Output: public/terrain-<sha12>.bin (float32 xyz, then uint32 triangle indices), public/terrain-mesh.json.
Needs: pip install usd-core numpy
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom


def meshes(path):
    stage = Usd.Stage.Open(str(path))
    if UsdGeom.GetStageUpAxis(stage) != 'Z' or UsdGeom.GetStageMetersPerUnit(stage) != 1:
        raise SystemExit(f'{path}: expected Z-up metres')
    cache = UsdGeom.XformCache()
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        points = np.array(mesh.GetPointsAttr().Get(), float)
        counts = np.array(mesh.GetFaceVertexCountsAttr().Get(), int)
        index = np.array(mesh.GetFaceVertexIndicesAttr().Get(), int)
        world = np.array(cache.GetLocalToWorldTransform(prim), float)  # row-vector convention
        points = np.c_[points, np.ones(len(points))] @ world
        # Fan-triangulate polygons.
        tris, start = [], 0
        for n in counts:
            face = index[start:start + n]
            tris += [(face[0], face[k], face[k + 1]) for k in range(1, n - 1)]
            start += n
        yield prim.GetPath(), points[:, :3], np.array(tris, int).reshape(-1, 3)


def cluster(points, tris, cell):
    keys = np.floor(points / cell).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    sums = np.zeros((inverse.max() + 1, 3))
    np.add.at(sums, inverse, points)
    merged = sums / np.bincount(inverse)[:, None]
    t = inverse[tris]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    keep = np.unique(np.sort(t, axis=1), axis=0, return_index=True)[1]
    return merged, t[np.sort(keep)]  # original winding kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('usd_dir', type=Path)
    parser.add_argument('--cell', type=float, default=0.4)
    args = parser.parse_args()
    positions, indices, parts, digest = [], [], [], hashlib.sha256()
    for name in ('terrain_ground.usdc', 'terrain_obstacles.usdc'):
        source = args.usd_dir / name
        digest.update(source.read_bytes())
        for prim, points, tris in meshes(source):
            merged, faces = cluster(points, tris, args.cell)
            base = sum(len(p) for p in positions)
            positions.append(merged)
            indices.append(faces + base)
            parts.append({'prim': str(prim), 'source_triangles': len(tris), 'triangles': len(faces)})
    xyz = np.concatenate(positions).astype('<f4')
    tri = np.concatenate(indices).astype('<u4')
    body = xyz.tobytes() + tri.tobytes()
    source_hash = digest.hexdigest()
    public = Path('public')
    target = public / f'terrain-{source_hash[:12]}.bin'
    if target.exists() and target.read_bytes() != body:
        raise SystemExit(f'Output exists with different contents: {target}')
    target.write_bytes(body)
    meta = {
        'file': target.name, 'source': 'Isaac Sim USD terrain_ground.usdc + terrain_obstacles.usdc',
        'scene_sha256': source_hash,  # MapView labels the mesh by this hash
        'usd_sha256': source_hash, 'mesh_sha256': hashlib.sha256(body).hexdigest(),
        'declared_frame': 'pair360_map', 'status': 'display mesh from the team USD (2026-11-23)',
        'cell_m': args.cell, 'vertices': len(xyz), 'triangles': len(tri),
        'method': f'vertex clustering on a {args.cell} m grid; display only, not the collision surface',
        'parts': f'{len(parts)} meshes, ground {parts[0]["triangles"]} triangles',
    }
    active = public / 'terrain-mesh.json'
    temp = active.with_suffix(f'.json.{os.getpid()}')
    temp.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    temp.replace(active)
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
