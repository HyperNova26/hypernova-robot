"""Triangle meshes of a MuJoCo scene's primitive geoms (boxes, cylinders, ellipsoids) for CloudCompare."""
import xml.etree.ElementTree as ET

import numpy as np


def unit_shape(kind, n=16, rings=8):
    """Unit box, cylinder (radius 1, half-height 1) or sphere as (vertices, triangles)."""
    if kind == "box":
        v = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float)
        return v, np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
                            [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]])
    a = np.linspace(0, 2*np.pi, n, endpoint=False)
    i, j = np.arange(n), (np.arange(n)+1) % n
    if kind == "cylinder":
        ring = np.column_stack([np.cos(a), np.sin(a)])
        v = np.vstack([np.column_stack([ring, -np.ones(n)]), np.column_stack([ring, np.ones(n)]), [[0, 0, -1], [0, 0, 1]]])
        side = np.vstack([np.column_stack([i, j, j+n]), np.column_stack([i, j+n, i+n])])
        caps = np.vstack([np.column_stack([np.full(n, 2*n), j, i]), np.column_stack([np.full(n, 2*n+1), i+n, j+n])])
        return v, np.vstack([side, caps])
    lat = np.linspace(-np.pi/2, np.pi/2, rings+1)[1:-1]
    v = np.vstack([[[0, 0, -1]]]+[np.column_stack([np.cos(t)*np.cos(a), np.cos(t)*np.sin(a), np.full(n, np.sin(t))])
                                   for t in lat]+[[[0, 0, 1]]])
    tris = [np.column_stack([np.zeros(n, int), 1+j, 1+i])]
    for r in range(rings-2):
        a0, a1 = 1+r*n, 1+(r+1)*n
        tris += [np.column_stack([a0+i, a0+j, a1+j]), np.column_stack([a0+i, a1+j, a1+i])]
    top, last = len(v)-1, 1+(rings-2)*n
    tris.append(np.column_stack([np.full(n, top), last+i, last+j]))
    return v, np.vstack(tris)


def scene_shapes(scene_xml):
    """Every non-heightfield world geom with its scene colour; yaw-only rotations (euler z)."""
    vertices, faces, colors, offset = [], [], [], 0
    for geom in ET.parse(scene_xml).getroot().findall("./worldbody/geom"):
        kind = geom.attrib["type"]
        if kind == "hfield":
            continue
        v, f = unit_shape("sphere" if kind == "ellipsoid" else kind)
        size = np.array(geom.attrib["size"].split(), float)
        scale = np.array([size[0], size[0], size[1]]) if kind == "cylinder" else size
        yaw = np.radians(float(geom.attrib.get("euler", "0 0 0").split()[2]))
        rot = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
        vertices.append((v*scale) @ rot.T+np.array(geom.attrib["pos"].split(), float))
        faces.append(f+offset)
        offset += len(v)
        colors.append(np.tile((np.array(geom.attrib["rgba"].split(), float)[:3]*255).round(), (len(v), 1)))
    if not vertices:
        return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 3), np.uint8)
    return np.concatenate(vertices), np.concatenate(faces), np.concatenate(colors).astype(np.uint8)
