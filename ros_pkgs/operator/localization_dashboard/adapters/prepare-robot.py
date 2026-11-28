# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Copy a team URDF and lighter display copies of its visual STL meshes into public/robot/<name>/.

Display only: vertex clustering on a fixed grid (mesh units), not a collision or mass model.
Usage: python prepare-robot.py DESCRIPTION_DIR [--cell-mm 3] [--name hn_v1_hyper]
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
from pathlib import Path

import numpy as np


def read_stl(path: Path) -> np.ndarray:
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    if 84 + count * 50 != len(data):
        raise ValueError(f"{path.name}: only binary STL is supported")
    rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=count, offset=84)
    return rec["v"].astype(np.float64)


def cluster(tris: np.ndarray, cell: float) -> np.ndarray:
    verts = tris.reshape(-1, 3)
    keys = np.floor(verts / cell).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    sums = np.zeros((inverse.max() + 1, 3))
    np.add.at(sums, inverse, verts)
    centers = sums / np.bincount(inverse)[:, None]
    faces = inverse.reshape(-1, 3)
    keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    faces = faces[keep]
    _, first = np.unique(np.sort(faces, axis=1), axis=0, return_index=True)
    return centers[faces[np.sort(first)]]


def write_stl(path: Path, tris: np.ndarray) -> None:
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    n = np.cross(b - a, c - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(tris), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    rec["n"], rec["v"] = n, tris
    path.write_bytes(b"display copy".ljust(80, b" ") + struct.pack("<I", len(tris)) + rec.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("description", type=Path, help="folder with <name>.urdf and meshes/")
    parser.add_argument("--name", default="hn_v1_hyper")
    parser.add_argument("--cell-mm", type=float, default=3.0, help="clustering cell in mesh units (URDF scale 0.001 -> mm)")
    args = parser.parse_args()
    urdf = next(args.description.glob("*.urdf"))
    out = Path(__file__).resolve().parent.parent / "public" / "robot" / args.name
    if out.exists():
        shutil.rmtree(out)
    (out / "meshes").mkdir(parents=True)
    text = urdf.read_text(encoding="utf-8")
    # Visual meshes only; collision meshes are not drawn.
    visuals = sorted(set(re.findall(r'<visual>.*?filename="([^"]+)"', text, flags=re.S)))
    report = {"source_urdf": str(urdf), "urdf_sha256": hashlib.sha256(text.encode()).hexdigest(), "cell_mm": args.cell_mm, "meshes": {}}
    for rel in visuals:
        src = args.description / rel
        tris = read_stl(src)
        small = cluster(tris, args.cell_mm)
        write_stl(out / "meshes" / src.name, small)
        report["meshes"][rel] = {"triangles_in": len(tris), "triangles_out": len(small)}
        print(f"{rel}: {len(tris):,} -> {len(small):,} triangles")
    (out / "robot.urdf").write_text(text, encoding="utf-8")
    (out / "prepare.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
