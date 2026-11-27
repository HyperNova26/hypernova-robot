"""Export the released MuJoCo terrain as PLY meshes for CloudCompare.

mesh_v1_ground.ply: every hfield vertex, triangulated like MuJoCo (diagonal r,c -> r+1,c+1).
mesh_v1_obstacle.ply: structure boxes and tree trunks, root mounds and crown lobes, in scene colours.
Same pair360_map coordinates as output/reference_map.pcd. numpy only.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from audit_ground import SCENE, load_hfields

OUT = Path(__file__).resolve().parent / "preview"


def write_ply(path, vertices, faces, colors=None):
    vtype = [("xyz", "<f4", (3,))] + ([("rgb", "u1", (3,))] if colors is not None else [])
    v = np.empty(len(vertices), vtype)
    v["xyz"] = vertices
    if colors is not None:
        v["rgb"] = colors
    f = np.empty(len(faces), [("n", "u1"), ("idx", "<i4", (3,))])
    f["n"], f["idx"] = 3, faces
    header = ["ply", "format binary_little_endian 1.0", "comment frame pair360_map, metres, Z up",
              f"element vertex {len(v)}", "property float x", "property float y", "property float z"]
    if colors is not None:
        header += ["property uchar red", "property uchar green", "property uchar blue"]
    header += [f"element face {len(f)}", "property list uchar int vertex_indices", "end_header"]
    with path.open("wb") as stream:
        stream.write(("\n".join(header) + "\n").encode("ascii"))
        v.tofile(stream)
        f.tofile(stream)


def terrain_mesh():
    vertices, faces, offset = [], [], 0
    for field in load_hfields():
        h = field["h"]
        nrow, ncol = h.shape
        gx, gy = np.meshgrid(np.linspace(field["x0"], field["x1"], ncol), np.linspace(field["y0"], field["y1"], nrow))
        vertices.append(np.column_stack([gx.ravel(), gy.ravel(), h.ravel()]))
        idx = np.arange(nrow*ncol).reshape(nrow, ncol) + offset
        a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
        faces += [np.column_stack([a, b, c]), np.column_stack([a, c, d])]
        offset += nrow*ncol
    return np.concatenate(vertices), np.concatenate(faces)


def unit_shape(kind):
    """Unit box, cylinder (radius 1, half-height 1) or sphere as (vertices, triangles)."""
    if kind == "box":
        v = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float)
        return v, np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
                            [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]])
    n = 16
    a = np.linspace(0, 2*np.pi, n, endpoint=False)
    if kind == "cylinder":
        ring = np.column_stack([np.cos(a), np.sin(a)])
        v = np.vstack([np.column_stack([ring, -np.ones(n)]), np.column_stack([ring, np.ones(n)]), [[0, 0, -1], [0, 0, 1]]])
        i = np.arange(n)
        j = (i+1) % n
        side = np.vstack([np.column_stack([i, j, j+n]), np.column_stack([i, j+n, i+n])])
        caps = np.vstack([np.column_stack([np.full(n, 2*n), j, i]), np.column_stack([np.full(n, 2*n+1), i+n, j+n])])
        return v, np.vstack([side, caps])
    rings = 8
    lat = np.linspace(-np.pi/2, np.pi/2, rings+1)[1:-1]
    v = np.vstack([[[0, 0, -1]]] + [np.column_stack([np.cos(t)*np.cos(a), np.cos(t)*np.sin(a), np.full(n, np.sin(t))])
                                     for t in lat] + [[[0, 0, 1]]])
    tris, i = [], np.arange(n)
    j = (i+1) % n
    tris.append(np.column_stack([np.zeros(n, int), 1+j, 1+i]))
    for r in range(rings-2):
        a0, a1 = 1+r*n, 1+(r+1)*n
        tris += [np.column_stack([a0+i, a0+j, a1+j]), np.column_stack([a0+i, a1+j, a1+i])]
    top, last = len(v)-1, 1+(rings-2)*n
    tris.append(np.column_stack([np.full(n, top), last+i, last+j]))
    return v, np.vstack(tris)


def box_mesh(scene=SCENE):
    """Every non-hfield geom (structure boxes, tree trunks, mounds, crowns) with its scene colour."""
    vertices, faces, colors, offset = [], [], [], 0
    for geom in ET.parse(scene/"scene.xml").getroot().findall("./worldbody/geom"):
        kind = geom.attrib["type"]
        if kind == "hfield":
            continue
        v, f = unit_shape("sphere" if kind == "ellipsoid" else kind)
        size = np.array(geom.attrib["size"].split(), float)
        scale = np.array([size[0], size[0], size[1]]) if kind == "cylinder" else size
        yaw = np.radians(float(geom.attrib.get("euler", "0 0 0").split()[2]))
        rot = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
        vertices.append((v*scale) @ rot.T + np.array(geom.attrib["pos"].split(), float))
        faces.append(f+offset)
        offset += len(v)
        rgb = (np.array(geom.attrib["rgba"].split(), float)[:3]*255).round()
        colors.append(np.tile(rgb, (len(v), 1)))
    return np.concatenate(vertices), np.concatenate(faces), np.concatenate(colors).astype(np.uint8)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    v, f = terrain_mesh()
    write_ply(OUT/"mesh_v1_ground.ply", v, f)
    bv, bf, bc = box_mesh()
    write_ply(OUT/"mesh_v1_obstacle.ply", bv, bf, bc)
    print(f"terrain: {len(v)} vertices, {len(f)} triangles; obstacles: {len(bv)} vertices, {len(bf)} triangles")
