"""Merge the mesh_v3 PLY parts into one PLY (ground + obstacle + trees; the demo route ribbon is left out).

All parts must share one layout (x y z float, red green blue uchar, triangles as uchar count + int indices),
which pipeline step 8 writes; anything else stops the script.
python tools/map/1124_pair360_v3/merge_meshes.py [--dir <out>/mesh_v3] [--parts ground obstacle trees] [--out mesh_v3_all.ply]
The default --dir is config.MESH_DIR (HN_PAIR360_OUT/mesh_v3).
"""
import argparse
from pathlib import Path

import numpy as np

from config import MESH_DIR

VERTEX = np.dtype([("xyz", "<f4", (3,)), ("rgb", "u1", (3,))])
FACE = np.dtype([("n", "u1"), ("idx", "<i4", (3,))])
LAYOUT = ["format binary_little_endian 1.0", "property float x", "property float y", "property float z",
          "property uchar red", "property uchar green", "property uchar blue",
          "property list uchar int vertex_indices"]


def read_ply(path):
    with open(path, "rb") as f:
        lines = []
        while True:
            line = f.readline().decode("ascii").strip()
            lines.append(line)
            if line == "end_header":
                break
        body = f.tell()
    if lines[0] != "ply" or any(item not in lines for item in LAYOUT):
        raise SystemExit(f"{path}: unexpected PLY layout")
    nv = int(next(l for l in lines if l.startswith("element vertex")).split()[-1])
    nf = int(next(l for l in lines if l.startswith("element face")).split()[-1])
    vertices = np.fromfile(path, VERTEX, nv, offset=body)
    faces = np.fromfile(path, FACE, nf, offset=body+nv*VERTEX.itemsize)
    if not (faces["n"] == 3).all():
        raise SystemExit(f"{path}: only triangles are supported")
    return vertices, faces["idx"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=MESH_DIR)
    ap.add_argument("--parts", nargs="+", default=["ground", "obstacle", "trees"])
    ap.add_argument("--prefix", default="mesh_v3")
    ap.add_argument("--out", default="mesh_v3_all.ply")
    args = ap.parse_args()
    vertices, faces, offset = [], [], 0
    for part in args.parts:
        v, f = read_ply(args.dir/f"{args.prefix}_{part}.ply")
        vertices.append(v)
        faces.append(f+offset)
        offset += len(v)
        print(f"{part}: {len(v)} vertices, {len(f)} triangles")
    vertices, faces = np.concatenate(vertices), np.concatenate(faces)
    out_faces = np.empty(len(faces), FACE)
    out_faces["n"], out_faces["idx"] = 3, faces
    header = ["ply", "format binary_little_endian 1.0", f"comment {args.prefix} parts: {' '.join(args.parts)}; pair360_map, metres, Z up",
              f"element vertex {len(vertices)}", "property float x", "property float y", "property float z",
              "property uchar red", "property uchar green", "property uchar blue",
              f"element face {len(out_faces)}", "property list uchar int vertex_indices", "end_header"]
    path = args.dir/args.out
    with path.open("wb") as stream:
        stream.write(("\n".join(header)+"\n").encode("ascii"))
        vertices.tofile(stream)
        out_faces.tofile(stream)
    print(f"{path}: {len(vertices)} vertices, {len(out_faces)} triangles, {path.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
