"""Point cloud and mesh I/O shared by all steps: binary PLY/PCD in, labelled PCD (turbo RGB) and PLY meshes out."""
import hashlib
import json

import numpy as np

from config import RGB_Z_RANGE


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_xyzi(path):
    """(N, 4) float32 x, y, z, intensity from a binary PLY (x y z scalar_intensity) or PCD (x y z intensity)."""
    with open(path, "rb") as f:
        lines = []
        while True:
            line = f.readline(1024).decode("ascii").strip()
            lines.append(line)
            if line in ("end_header", "DATA binary") or len(lines) > 80:
                break
        offset = f.tell()
    if lines[-1] == "end_header":
        props = [l.split()[-1] for l in lines if l.startswith("property ")]
        count = int(next(l for l in lines if l.startswith("element vertex")).split()[-1])
        if props[:4] != ["x", "y", "z", "scalar_intensity"] or len(props) != 4:
            raise ValueError(f"Unexpected PLY layout {props} in {path}")
    elif lines[-1] == "DATA binary":
        fields = next(l for l in lines if l.startswith("FIELDS")).split()[1:]
        count = int(next(l for l in lines if l.startswith("POINTS")).split()[-1])
        if fields != ["x", "y", "z", "intensity"]:
            raise ValueError(f"Unexpected PCD fields {fields} in {path}")
    else:
        raise ValueError(f"Unrecognised header in {path}")
    return np.memmap(path, dtype="<f4", mode="r", offset=offset, shape=(count, 4))


def read_labelled(path):
    """Structured array of a PCD written by write_pcd (xyzi, label, source, rgb)."""
    with open(path, "rb") as f:
        for line in f:
            if line.startswith(b"DATA"):
                break
        offset = f.tell()
    return np.memmap(path, dtype=[("xyzi", "<f4", (4,)), ("label", "<u4"), ("source", "<u4"), ("rgb", "<u4")],
                     mode="r", offset=offset)


def turbo_rgb(z):
    from matplotlib import colormaps
    lo, hi = RGB_Z_RANGE
    rgb = (colormaps["turbo"](np.clip((z-lo)/(hi-lo), 0, 1))[:, :3]*255).astype(np.uint32)
    return (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]


def pack_rgb(rgb):
    rgb = np.asarray(rgb, np.uint32).reshape(-1, 3)
    return (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]


def write_pcd(path, xyzi, label, source, rgb=None):
    """Binary PCD: x y z intensity label source rgb. rgb: (n, 3) uint8 per point, or None for turbo by z
    (the FAST-LIO view). Returns sha256."""
    data = np.empty(len(label), dtype=[("xyzi", "<f4", (4,)), ("label", "<u4"), ("source", "<u4"), ("rgb", "<u4")])
    data["xyzi"], data["label"], data["source"] = xyzi, label, source
    data["rgb"] = turbo_rgb(np.asarray(xyzi)[:, 2]) if rgb is None else pack_rgb(rgb)
    header = ("VERSION 0.7\nFIELDS x y z intensity label source rgb\nSIZE 4 4 4 4 4 4 4\nTYPE F F F F U U U\n"
              f"COUNT 1 1 1 1 1 1 1\nWIDTH {len(data)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(data)}\nDATA binary\n")
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as stream:
        stream.write(header.encode("ascii"))
        data.tofile(stream)
    tmp.replace(path)
    return sha256(path)


def write_ply(path, vertices, faces, colors=None, comment="pair360_map, metres, Z up"):
    vtype = [("xyz", "<f4", (3,))] + ([("rgb", "u1", (3,))] if colors is not None else [])
    v = np.empty(len(vertices), vtype)
    v["xyz"] = vertices
    if colors is not None:
        v["rgb"] = colors
    f = np.empty(len(faces), [("n", "u1"), ("idx", "<i4", (3,))])
    f["n"], f["idx"] = 3, faces
    header = ["ply", "format binary_little_endian 1.0", f"comment {comment}", f"element vertex {len(v)}",
              "property float x", "property float y", "property float z"]
    if colors is not None:
        header += ["property uchar red", "property uchar green", "property uchar blue"]
    header += [f"element face {len(f)}", "property list uchar int vertex_indices", "end_header"]
    with path.open("wb") as stream:
        stream.write(("\n".join(header)+"\n").encode("ascii"))
        v.tofile(stream)
        f.tofile(stream)


def transform(points, matrix):
    """p_map = R @ p + t for a 4x4 matrix."""
    matrix = np.asarray(matrix)
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def voxel_first(points, size):
    """Index of the first point in every occupied voxel (earlier rows win)."""
    cell = np.floor(points/size).astype(np.int64)
    cell -= cell.min(axis=0)
    dims = cell.max(axis=0)+1
    key = (cell[:, 0]*dims[1]+cell[:, 1])*dims[2]+cell[:, 2]
    first = np.unique(key, return_index=True)[1]
    first.sort()
    return first


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))
