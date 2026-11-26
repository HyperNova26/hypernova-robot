# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Display mesh for the dashboard from the pair360-map mesh_v3 PLYs (pair360_map frame, whole scope).

The Isaac USD of the team scene is cut to 30 m around route A, so the 11-15 recording start
(x -48.5) falls off it; mesh_v3 covers x -81.3 .. 77.5.
Usage: python adapters/prepare-terrain-ply.py path/to/pair360-map/results/mesh_v3 [--cell 0.4]
Reads mesh_v3_ground.ply, mesh_v3_obstacle.ply, mesh_v3_trees.ply (binary PLY: float xyz + uchar rgb,
triangle faces). Output: public/terrain-<sha12>.bin (float32 xyz, then uint32 triangle indices),
public/terrain-mesh.json. Needs numpy only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

PARTS = ("mesh_v3_ground.ply", "mesh_v3_obstacle.ply", "mesh_v3_trees.ply")


def read_ply(path: Path):
    data = path.read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    header = data[:end].decode("ascii").splitlines()
    if "format binary_little_endian 1.0" not in header:
        raise SystemExit(f"{path.name}: binary little-endian PLY expected")
    nv = int(next(h for h in header if h.startswith("element vertex")).split()[-1])
    nf = int(next(h for h in header if h.startswith("element face")).split()[-1])
    vprops = [h.split()[-1] for h in header if h.startswith("property") and "list" not in h]
    if vprops != ["x", "y", "z", "red", "green", "blue"]:
        raise SystemExit(f"{path.name}: unexpected vertex properties {vprops}")
    vtype = np.dtype([("xyz", "<f4", 3), ("rgb", "u1", 3)])
    ftype = np.dtype([("n", "u1"), ("i", "<i4", 3)])
    verts = np.frombuffer(data, vtype, nv, end)
    faces = np.frombuffer(data, ftype, nf, end + nv * vtype.itemsize)
    if end + nv * vtype.itemsize + nf * ftype.itemsize != len(data) or np.any(faces["n"] != 3):
        raise SystemExit(f"{path.name}: only triangle faces are supported")
    return verts["xyz"].astype(float), faces["i"].astype(np.int64)


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
    parser.add_argument("mesh_dir", type=Path)
    parser.add_argument("--cell", type=float, default=0.4)
    args = parser.parse_args()
    positions, indices, parts, digest = [], [], [], hashlib.sha256()
    for name in PARTS:
        source = args.mesh_dir / name
        raw = source.read_bytes()
        digest.update(raw)
        points, tris = read_ply(source)
        merged, faces = cluster(points, tris, args.cell)
        base = sum(len(p) for p in positions)
        positions.append(merged)
        indices.append(faces + base)
        parts.append({"file": name, "sha256": hashlib.sha256(raw).hexdigest(), "source_triangles": len(tris), "triangles": len(faces)})
    xyz = np.concatenate(positions).astype("<f4")
    tri = np.concatenate(indices).astype("<u4")
    body = xyz.tobytes() + tri.tobytes()
    source_hash = digest.hexdigest()
    public = Path(__file__).resolve().parent.parent / "public"
    target = public / f"terrain-{source_hash[:12]}.bin"
    if target.exists() and target.read_bytes() != body:
        raise SystemExit(f"Output exists with different contents: {target}")
    target.write_bytes(body)
    meta = {
        "file": target.name,
        "source": "pair360-map mesh_v3 PLY (ground + obstacle + trees)",
        "scene_sha256": source_hash,  # MapView labels the mesh by this hash
        "mesh_sha256": hashlib.sha256(body).hexdigest(),
        "declared_frame": "pair360_map",
        "status": "display mesh from mesh_v3, whole scope (2026-11-26)",
        "cell_m": args.cell,
        "vertices": len(xyz),
        "triangles": len(tri),
        "bounds_xy": [float(xyz[:, 0].min()), float(xyz[:, 0].max()), float(xyz[:, 1].min()), float(xyz[:, 1].max())],
        "method": f"vertex clustering on a {args.cell} m grid; display only, not the collision surface",
        "parts": parts,
    }
    active = public / "terrain-mesh.json"
    temp = active.with_suffix(f".json.{os.getpid()}")
    temp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    temp.replace(active)
    print(json.dumps({k: meta[k] for k in ("file", "vertices", "triangles", "bounds_xy")}, indent=2))


if __name__ == "__main__":
    main()
