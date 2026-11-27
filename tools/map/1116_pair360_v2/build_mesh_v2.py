"""mesh_v2 from map_v2: ground surface + no-go obstacles, as PLY meshes and a MuJoCo scene.

Ground: the reviewed pc_v1 v9 surface (0.1 m grid) where it was measured or reviewed;
pc_v3 ground re-anchors interpolated cells and adds cells pc_v1 never saw.
No-go: 0.2 m cells holding obstacle returns 0.12-1.2 m above the ground, plus cells with
no ground measurement. Obstacles only have to stop a Go2, so MuJoCo gets a second
heightfield raised NOGO_M above the ground there. Trees near the demo route are drawn as
trees (trunk, root mound, crown) instead of raised cells.
Run with a Python that has mujoco: .venv_mujoco/Scripts/python build_mesh_v2.py <go2.xml>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy import ndimage

from register_maps import ROOT
from separate_ground import SURFACE

sys.path.insert(0, str(ROOT/"terrain"))
from trees import segment, tree_geoms, xyz_text  # noqa: E402

V2 = ROOT/"map_v2"
SIM = V2/"mujoco"
WAYPOINTS = [[-16, 170], [-16, 175], [-17, 179], [-18, 182], [-16, 185], [-12, 185], [-10, 185]]
BAND = (0.12, 1.2)      # obstacle returns in this height range above ground block the robot (m)
MIN_RETURNS = 3         # per 0.2 m cell
NOGO_M = 0.8            # raised wall height (m)
CLEARANCE_M = 0.45      # route centre to the nearest no-go cell (Go2 half diagonal ~0.4 m)
MAX_SLOPE = 0.3         # rise per metre on the planned route


def read_pcd(path):
    with path.open("rb") as stream:
        for line in stream:
            if line.startswith(b"DATA"):
                break
        offset = stream.tell()
    return np.memmap(path, dtype=[("xyzi", "<f4", (4,)), ("label", "<u4"), ("source", "<u4")], offset=offset, mode="r")


def bilinear(grid, x, y, xy):
    g = [(xy[:, 1]-y[0])/(y[1]-y[0]), (xy[:, 0]-x[0])/(x[1]-x[0])]
    return ndimage.map_coordinates(grid, g, order=1, mode="nearest")


def coarse_median(xy, z, x, y, factor=5):
    """Median and 10-90% spread of z per (factor x 0.1 m) cell on the v9 grid."""
    c = np.round((xy[:, 0]-x[0])/(x[1]-x[0])).astype(int)//factor
    r = np.round((xy[:, 1]-y[0])/(y[1]-y[0])).astype(int)//factor
    shape = (-(-len(y)//factor), -(-len(x)//factor))
    ok = (c >= 0) & (c < shape[1]) & (r >= 0) & (r < shape[0])
    keys, zz = r[ok]*shape[1]+c[ok], z[ok]
    order = np.lexsort((zz, keys))
    keys, zz = keys[order], zz[order]
    cells, start, count = np.unique(keys, return_index=True, return_counts=True)
    med = np.full(shape, np.nan)
    spread = np.full(shape, np.inf)
    n = np.zeros(shape, int)
    med.flat[cells] = zz[start+count//2]
    spread.flat[cells] = zz[start+np.minimum(count-1, (count*9)//10)] - zz[start+count//10]
    n.flat[cells] = count
    return med, spread, n


def ground_surface(ground_pts, surf):
    x, y = surf["x"], surf["y"]
    h0 = surf["height"].astype(float)
    permitted = surf["permitted"]
    observed = np.repeat(np.repeat(surf["observed_coarse"], 5, 0), 5, 1)[:len(y), :len(x)]
    v3 = ground_pts["source"] == 3
    xy, z = ground_pts["xyzi"][v3, :2].astype(float), ground_pts["xyzi"][v3, 2].astype(float)
    med, spread, n = coarse_median(xy, z, x, y)
    fine = lambda a: np.repeat(np.repeat(a, 5, 0), 5, 1)[:len(y), :len(x)]  # noqa: E731
    support = fine((n >= 4) & (spread <= .12))
    m = fine(med)
    # 1. Interpolated (reviewed, unobserved) pc_v1 cells: re-anchor to pc_v3 where it agrees within 25 cm.
    reanchor = permitted & ~observed & support & (np.abs(m-h0) <= .25)
    delta = np.where(reanchor, m-np.nan_to_num(h0), 0)
    w = ndimage.gaussian_filter(reanchor.astype(float), 3.0)
    smooth = ndimage.gaussian_filter(delta, 3.0)/np.maximum(w, 1e-3)
    fade = np.clip((ndimage.distance_transform_edt(reanchor)-.5)/5, 0, 1)
    h = np.where(reanchor, h0+smooth*fade, h0)
    # 2. Cells pc_v1 never had: pc_v3 measured ground only.
    added = ~permitted & support
    known = permitted | added
    base = np.where(added, m, h)
    wk = ndimage.gaussian_filter(added.astype(float), 1.5)
    soft = ndimage.gaussian_filter(np.where(added, m, 0), 1.5)/np.maximum(wk, 1e-3)
    h = np.where(added, soft, base)
    # 3. Unknown cells copy the nearest known height so the surface has no voids; they are no-go.
    idx = ndimage.distance_transform_edt(~known, return_distances=False, return_indices=True)
    h = h[tuple(idx)]
    return h, known, {"reanchored_cells": int(reanchor.sum()), "added_cells": int(added.sum()),
                      "known_cells": int(known.sum()), "unknown_cells": int((~known).sum())}


def nogo_mask(obstacle_pts, h, known, x, y, trees):
    xy = obstacle_pts["xyzi"][:, :2].astype(float)
    hag = obstacle_pts["xyzi"][:, 2]-bilinear(h, x, y, xy)
    band = (hag > BAND[0]) & (hag < BAND[1])
    c = np.round((xy[band, 0]-x[0])/(x[1]-x[0])).astype(int)//2
    r = np.round((xy[band, 1]-y[0])/(y[1]-y[0])).astype(int)//2
    shape = (-(-len(y)//2), -(-len(x)//2))
    ok = (c >= 0) & (c < shape[1]) & (r >= 0) & (r < shape[0])
    count = np.bincount(r[ok]*shape[1]+c[ok], minlength=shape[0]*shape[1]).reshape(shape)
    blocked = np.repeat(np.repeat(count >= MIN_RETURNS, 2, 0), 2, 1)[:len(y), :len(x)]
    blocked = ndimage.binary_dilation(blocked)
    gx, gy = np.meshgrid(x, y)
    for t in trees:   # tree trunks and mounds block on their own
        reach = float(np.clip(.3+.35*min(t["crown_radii_m"]), .6, 1.2))+.3
        blocked &= np.hypot(gx-t["trunk_xy"][0], gy-t["trunk_xy"][1]) > reach
    return blocked | ~known, {"obstacle_cells": int(blocked.sum()), "band_returns": int(band.sum())}


def plan_route(h, nogo, x, y, trees, start, goal):
    """Shortest route that keeps CLEARANCE_M from no-go cells and tree solids, on gentle slopes.

    The demo keeps its intent (parking start, top of the ramp); waypoints move only as far as
    the obstacles require. Returns waypoints simplified by line of sight.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    lo = np.minimum(start, goal)-12
    hi = np.maximum(start, goal)+12
    xs = np.flatnonzero((x >= lo[0]) & (x <= hi[0]))
    ys = np.flatnonzero((y >= lo[1]) & (y <= hi[1]))
    sub = np.ix_(ys, xs)
    gx, gy = np.meshgrid(x[xs], y[ys])
    blocked = nogo[sub].copy()
    for t in trees:
        reach = float(np.clip(.3+.35*min(t["crown_radii_m"]), .6, 1.2))
        blocked |= np.hypot(gx-t["trunk_xy"][0], gy-t["trunk_xy"][1]) <= reach
    step = x[1]-x[0]
    clear = ndimage.distance_transform_edt(~blocked)*step
    sy, sx = np.gradient(h[sub].astype(float), step)
    ok = (clear >= CLEARANCE_M) & (np.hypot(sx, sy) <= MAX_SLOPE)
    ids = -np.ones(ok.shape, int)
    ids[ok] = np.arange(ok.sum())
    rows, cols, cost = [], [], []
    height, width = ok.shape
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        c0, c1 = max(0, -dc), width-max(0, dc)
        here = (slice(0, height-dr), slice(c0, c1))
        there = (slice(dr, height), slice(c0+dc, c1+dc))
        both = ok[here] & ok[there]
        ca = clear[here]
        rows.append(ids[here][both])
        cols.append(ids[there][both])
        # Prefer the middle of a corridor: short steps cost more next to obstacles.
        cost.append(np.hypot(dr, dc)*step*(1+.3/ca[both]))
    rows, cols, cost = map(np.concatenate, (rows, cols, cost))
    n = int(ok.sum())
    graph = coo_matrix((np.r_[cost, cost], (np.r_[rows, cols], np.r_[cols, rows])), shape=(n, n)).tocsr()
    pts = np.column_stack([gx[ok], gy[ok]])
    s = int(np.argmin(np.linalg.norm(pts-start, axis=1)))
    # The goal is "this far up the ramp": among free cells, prefer the requested height.
    zf = h[sub][ok]
    goal_z = float(bilinear(h, x, y, np.asarray([goal], float))[0])
    level = np.abs(zf-goal_z) <= .1
    g = int(np.argmin(np.linalg.norm(pts-goal, axis=1)+np.where(level, 0, 1e3)))
    dist, pred = dijkstra(graph, indices=s, return_predecessors=True)
    if not np.isfinite(dist[g]):
        raise RuntimeError("No traversable route between start and goal")
    chain = [g]
    while chain[-1] != s:
        chain.append(pred[chain[-1]])
    path = pts[chain[::-1]]

    def visible(a, b):
        t = np.linspace(0, 1, max(2, int(np.linalg.norm(b-a)/(step/2))))
        p = a+t[:, None]*(b-a)
        c = np.round((p[:, 0]-x[xs[0]])/step).astype(int)
        r = np.round((p[:, 1]-y[ys[0]])/step).astype(int)
        return bool(ok[r, c].all())
    way, i = [path[0]], 0
    while i < len(path)-1:
        j = len(path)-1
        while j > i+1 and not visible(path[i], path[j]):
            j -= 1
        way.append(path[j])
        i = j
    way = np.round(np.array(way), 2)
    return way, {"clearance_m": CLEARANCE_M, "max_slope": MAX_SLOPE, "requested_start_goal": [list(start), list(goal)],
                 "start_shift_m": round(float(np.linalg.norm(way[0]-start)), 2),
                 "goal_shift_m": round(float(np.linalg.norm(way[-1]-goal)), 2), "goal_z_target_m": round(goal_z, 3),
                 "length_m": round(float(np.linalg.norm(np.diff(way, axis=0), axis=1).sum()), 2)}


def write_hfield(path, values):
    lo, hi = float(values.min()), float(values.max())
    span = max(hi-lo, 1e-6)
    with path.open("wb") as f:
        f.write(np.array(values.shape, "<i4").tobytes())
        f.write(((values-lo)/span).astype("<f4").tobytes())
    return lo, span


def write_ply(path, vertices, faces, colors=None):
    vtype = [("xyz", "<f4", (3,))] + ([("rgb", "u1", (3,))] if colors is not None else [])
    v = np.empty(len(vertices), vtype)
    v["xyz"] = vertices
    if colors is not None:
        v["rgb"] = colors
    f = np.empty(len(faces), [("n", "u1"), ("idx", "<i4", (3,))])
    f["n"], f["idx"] = 3, faces
    header = ["ply", "format binary_little_endian 1.0", "comment map_v2 pair360_map, metres, Z up",
              f"element vertex {len(v)}", "property float x", "property float y", "property float z"]
    if colors is not None:
        header += ["property uchar red", "property uchar green", "property uchar blue"]
    header += [f"element face {len(f)}", "property list uchar int vertex_indices", "end_header"]
    with path.open("wb") as stream:
        stream.write(("\n".join(header)+"\n").encode("ascii"))
        v.tofile(stream)
        f.tofile(stream)


def grid_mesh(x, y, h, cell_ok):
    """Triangles (MuJoCo diagonal) for every grid quad whose flag is set; unused vertices dropped."""
    gx, gy = np.meshgrid(x, y)
    idx = np.arange(h.size).reshape(h.shape)
    q = cell_ok[:-1, :-1] & cell_ok[1:, 1:] & cell_ok[:-1, 1:] & cell_ok[1:, :-1]
    a, b, c, d = idx[:-1, :-1][q], idx[:-1, 1:][q], idx[1:, 1:][q], idx[1:, :-1][q]
    faces = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    used, faces = np.unique(faces, return_inverse=True)
    verts = np.column_stack([gx.ravel(), gy.ravel(), h.ravel()])[used]
    return verts, faces.reshape(-1, 3)


def block_mesh(x, y, h, mask):
    """No-go area as a plateau NOGO_M above the ground with vertical walls on its outline."""
    gx, gy = np.meshgrid(x, y)
    n = h.size
    idx = np.arange(n).reshape(h.shape)
    verts = np.vstack([np.column_stack([gx.ravel(), gy.ravel(), h.ravel()]),
                       np.column_stack([gx.ravel(), gy.ravel(), h.ravel()+NOGO_M])])
    q = mask[:-1, :-1] & mask[1:, 1:] & mask[:-1, 1:] & mask[1:, :-1]
    a, b, c, d = (idx[:-1, :-1][q], idx[:-1, 1:][q], idx[1:, 1:][q], idx[1:, :-1][q])
    faces = [np.column_stack([a, b, c])+n, np.column_stack([a, c, d])+n]
    pad = np.pad(q, 1)
    # Edge between vertices (r,c)-(r,c+1): quads below (r-1,c) and above (r,c).
    edge_h = pad[:-1, 1:-1] ^ pad[1:, 1:-1]
    r, c = np.nonzero(edge_h)
    u, v = idx[r, c], idx[r, c+1]
    faces += [np.column_stack([u, v, v+n]), np.column_stack([u, v+n, u+n])]
    # Edge between vertices (r,c)-(r+1,c): quads left (r,c-1) and right (r,c).
    edge_v = pad[1:-1, :-1] ^ pad[1:-1, 1:]
    r, c = np.nonzero(edge_v)
    u, v = idx[r, c], idx[r+1, c]
    faces += [np.column_stack([u, v, v+n]), np.column_stack([u, v+n, u+n])]
    faces = np.vstack(faces)
    used, faces = np.unique(faces, return_inverse=True)
    return verts[used], faces.reshape(-1, 3)


def verify(go2, route_xyz):
    import mujoco
    sys.path.insert(0, str(ROOT/"terrain"))
    from load_go2 import check_menagerie_stand
    model = mujoco.MjModel.from_xml_path(str(SIM/"scene.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    ground_only = np.array([1, 0, 0, 0, 0, 0], np.uint8)
    solid = np.array([0, 0, 1, 0, 1, 0], np.uint8)

    def ray(p, d, groups):
        return mujoco.mj_ray(model, data, np.asarray(p, float), np.asarray(d, float), groups, True, -1,
                             np.array([-1], np.int32))
    route = np.asarray(route_xyz)[:, :2]
    path = []
    for a, b in zip(route, route[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b-a)/.1)))
        path.extend(a+(b-a)*t for t in np.linspace(0, 1, n, endpoint=False))
    path.append(route[-1])
    blocked, floors = [], []
    for c in path:
        for off in ([0, 0], [.24, .14], [.24, -.14], [-.24, .14], [-.24, -.14]):
            xy = c+off
            fl = 40-ray([*xy, 40], [0, 0, -1], ground_only)
            hit = ray([*xy, 40], [0, 0, -1], solid)
            top = 40-hit if hit >= 0 else -np.inf
            low = ray([*xy, fl+.01], [0, 0, 1], solid)
            if top > fl+.02 or 0 <= low <= .54:
                blocked.append(np.round(xy, 2).tolist())
            if off == [0, 0]:
                floors.append(fl)
    result = {"mujoco_version": mujoco.__version__, "geoms": model.ngeom, "hfields": model.nhfield,
              "route_probes": 5*len(path), "route_blocked_probes": len(blocked), "blocked_examples": blocked[:8],
              "max_center_step_per_10cm_m": float(np.abs(np.diff(floors)).max())}
    if go2:
        result["go2_stand"] = check_menagerie_stand(go2, scene_dir=SIM)
        result["go2_xml_sha256"] = hashlib.sha256(Path(go2).read_bytes()).hexdigest()
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("go2", nargs="?", type=Path, help="Menagerie go2.xml for the stand check")
    args = ap.parse_args()
    (SIM/"hfields").mkdir(parents=True, exist_ok=True)
    (V2/"mesh").mkdir(parents=True, exist_ok=True)
    surf = dict(np.load(SURFACE))
    x, y = surf["x"], surf["y"]
    ground = read_pcd(V2/"pc/map_v2_ground.pcd")
    obstacle = read_pcd(V2/"pc/map_v2_obstacle.pcd")
    h, known, gsum = ground_surface(ground, surf)
    route = np.array(WAYPOINTS, float)

    # Trees near the demo route: trunk/foliage returns of the classified sources (already z-corrected in map_v2).
    tree_input = np.load(V2/"pc/tree_points.npz")
    trees = segment(tree_input["xyz"], tree_input["label"], np.zeros(len(tree_input["label"]), int), (x, y, h), route)
    (SIM/"trees.json").write_text(json.dumps(trees, indent=1), encoding="utf-8")
    nogo, nsum = nogo_mask(obstacle, h, known, x, y, trees["trees"])
    route, rsum = plan_route(h, nogo, x, y, trees["trees"], route[0], route[-1])

    # MuJoCo: ground heightfield + no-go heightfield (raised where blocked, just below ground elsewhere).
    scene = ET.Element("mujoco", model="PAIR360 map_v2 walking environment")
    ET.SubElement(scene, "option", timestep="0.002", gravity="0 0 -9.81")
    ET.SubElement(scene, "statistic", center="-16 178 1.5", extent="17")
    asset, world = ET.SubElement(scene, "asset"), ET.SubElement(scene, "worldbody")
    half = [(x[-1]-x[0])/2, (y[-1]-y[0])/2]
    centre = [(x[-1]+x[0])/2, (y[-1]+y[0])/2]
    for name, values, group, rgba in (("pair360_ground_000", h, "0", ".38 .44 .42 1"),
                                      ("pair360_nogo_000", np.where(nogo, h+NOGO_M, h-.05), "4", ".55 .45 .38 1")):
        lo, span = write_hfield(SIM/f"hfields/{name}.bin", values)
        ET.SubElement(asset, "hfield", name=name, file=f"hfields/{name}.bin", size=xyz_text([*half, span, .1]))
        ET.SubElement(world, "geom", name=name, type="hfield", hfield=name, pos=xyz_text([*centre, lo]),
                      friction="1 0.005 0.0001", rgba=rgba, group=group)
    tree_geoms(trees["trees"], world)
    route_z = bilinear(h, x, y, route)
    ET.indent(scene)
    ET.ElementTree(scene).write(SIM/"scene.xml", encoding="utf-8", xml_declaration=True)
    v2 = json.loads((V2/"manifest.json").read_text(encoding="utf-8"))
    manifest = {"frame": "pair360_map", "map": "map_v2", "mesh": "mesh_v2",
                "map_v2_ground_sha256": v2["files_sha256"]["map_v2_ground.pcd"],
                "map_v2_obstacle_sha256": v2["files_sha256"]["map_v2_obstacle.pcd"],
                "surface_base": SURFACE.parent.name, "grid_m": float(x[1]-x[0]), "ground": gsum,
                "nogo": {**nsum, "band_above_ground_m": list(BAND), "min_returns_per_0.2m_cell": MIN_RETURNS,
                         "raised_m": NOGO_M, "cells": int(nogo.sum())},
                "trees": {"count": len(trees["trees"]), "area_xy": trees["area_xy"]}, "route_planning": rsum,
                "route_xyz_m": np.column_stack((route, route_z)).tolist(), "spawn_yaw_deg": 90.0}
    (SIM/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    np.savez_compressed(SIM/"ground_grid.npz", x=x, y=y, height=h.astype("f4"), known=known, nogo=nogo)

    # Meshes for CloudCompare: walkable ground, and no-go blocks next to it.
    gv, gf = grid_mesh(x, y, h, known)
    write_ply(V2/"mesh/mesh_v2_ground.ply", gv, gf)
    near_site = nogo & (ndimage.distance_transform_edt(~known) <= 10)
    bv, bf = block_mesh(x, y, h, near_site)
    write_ply(V2/"mesh/mesh_v2_obstacle.ply", bv, bf, np.tile([140, 115, 97], (len(bv), 1)).astype(np.uint8))
    from export_preview import box_mesh
    tv, tf, tc = box_mesh(SIM)
    write_ply(V2/"mesh/mesh_v2_trees.ply", tv, tf, tc)
    manifest["meshes"] = {"mesh_v2_ground.ply": {"vertices": len(gv), "triangles": len(gf)},
                          "mesh_v2_obstacle.ply": {"cells": int(near_site.sum()), "triangles": len(bf),
                                                   "note": "no-go plateau and walls within 1 m of known ground"},
                          "mesh_v2_trees.ply": {"trees": len(trees["trees"]), "triangles": len(tf)}}
    manifest["verification"] = verify(args.go2, manifest["route_xyz_m"])
    (SIM/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
