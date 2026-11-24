"""Step 8. mesh_v3: ground heightfield, no-go obstacles, trees near the route, demo start/goal.

No-go = 0.2 m cells holding >= 3 obstacle returns 0.15-0.5 m above the ground (grown by 0.1 m), plus
cells where the ground rises more than 0.2 m within 0.5 m (walls, banks, curbs above Go2's step). The band
is the Go2 body: it steps over about 0.15 m and stands 0.40 m tall, so lower returns are walkable relief
and higher-only returns (branches, the ghost layer pc_v1 has 0.5-0.8 m above some floors) pass over it;
walls, hedges, poles and trunks all reach into the band. MuJoCo gets a second heightfield raised 0.8 m
there. Trees within 15 m of the route with trunk returns are trunk + root mound (solid) and three crown
ellipsoids (rays only); crowns without a trunk below them are rays only. A road-only reference path through
start -> via -> goal is planned with 0.6 m clearance for terrain checks; navigation itself only needs start
and goal.
Reviewed edits (decisions/terrain_edits.json): false trunks (planter, shrub, parked object) lose their
solid, one trunk moves to its real stem, the ramp curbs become no-go strips 0.3 m wide and 0.3 m above
the road (measured curbs 0.21-0.40 m) instead of the 0.8 m used for other no-go cells, the planting strip
along the straight road is no-go, and the parking lot has no other no-go than curbs (continuous floor as in
mesh_v1; trees stay).
Raised islands (terrain_edits.json curb_rims): hand-traced planting islands of the parking lot and beside the
start are no-go blocks at the measured curb height (not +0.8 m), also inside the parking lot.
Scope (step 7): the meshes cover only the scope. Just outside it MuJoCo keeps a 0.5 m no-go wall (group 4,
hidden by default) and the visible ground drops 1 m, so the edge reads as a cut.

In : results/mesh_v3/ground_surface.npz, results/map_v3/map_v3_obstacle.pcd, decisions/demo_route.json,
     decisions/terrain_edits.json
Out: results/mesh_v3/mujoco/{scene.xml, hfields/*.bin, trees.json, manifest.json},
     results/mesh_v3/mesh_v3_{ground,obstacle,trees,route}.ply (route: red ribbon + start/goal discs, viewing only)
"""
import xml.etree.ElementTree as ET

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

import edits
from config import GROUND_MESH_RGB, MAP_DIR, MAP_VERSION, MESH_DIR, MESH_VERSION, ROUTE
from pcio import load_json, read_labelled, save_json, write_ply
from shapes import scene_shapes
from trees import ground_at, mound_radius, segment, solid, tree_geoms, xyz_text

SIM = MESH_DIR/"mujoco"
BAND, MIN_RETURNS, NOGO_M = (0.15, 0.5), 3, 0.8   # Go2: climbs ~0.15 m, 0.70 x 0.31 x 0.40 m standing
RELIEF_M, RELIEF_CELLS = 0.2, 5                     # ground rising > 0.2 m inside a 0.5 m window
CLEARANCE_M, MAX_SLOPE, TREE_MARGIN = 0.6, 0.3, 15.0
SCOPE_DROP_M, SCOPE_WALL_M = 1.0, 0.5               # outside the scope: ground 1 m lower, invisible wall 0.5 m wide


def bilinear(grid, x, y, xy):
    return ndimage.map_coordinates(grid, [(xy[:, 1]-y[0])/(y[1]-y[0]), (xy[:, 0]-x[0])/(x[1]-x[0])], order=1, mode="nearest")


def route_mesh(path, h, x, y, width=.4, lift=.05, marker_r=.8):
    """Demo route for viewing: a ribbon on the ground along the reference path, discs at start and goal."""
    pts = [path[0]]
    for a, b in zip(path, path[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b-a)/.2)))
        pts += [a+(b-a)*t for t in np.linspace(0, 1, n+1)[1:]]
    pts = np.array(pts)
    d = np.gradient(pts, axis=0)
    n = np.column_stack([-d[:, 1], d[:, 0]])/np.maximum(np.linalg.norm(d, axis=1), 1e-9)[:, None]*width/2
    side = np.vstack([pts+n, pts-n])
    verts = [np.column_stack([side, bilinear(h, x, y, side)+lift])]
    k = len(pts)
    i = np.arange(k-1)
    faces = [np.column_stack([i, i+1, k+i+1]), np.column_stack([i, k+i+1, k+i])]
    base = 2*k
    for c in (path[0], path[-1]):
        ang = np.linspace(0, 2*np.pi, 25)[:-1]
        ring = c+marker_r*np.column_stack([np.cos(ang), np.sin(ang)])
        ring = np.vstack([c, ring])
        verts.append(np.column_stack([ring, bilinear(h, x, y, ring)+lift+.02]))
        j = np.arange(1, 25)
        faces.append(np.column_stack([np.zeros(24, int), j, np.roll(j, -1)])+base)
        base += 25
    return np.vstack(verts), np.vstack(faces)


def curb_rims(review, h, x, y):
    """Hand-traced raised islands (terrain_edits.json curb_rims): (no-go cells, top height) on the 0.1 m grid.
    Each island is a block height_m above the lowest ground within 0.3 m."""
    cfg = review["curb_rims"]
    cells, top = np.zeros(h.shape, bool), np.full(h.shape, np.nan)
    low = ndimage.minimum_filter(h, int(round(.3/(x[1]-x[0])))*2+1)
    for island in cfg["islands"]:
        inside = edits.polygon_mask(x, y, island["polygon_xy"])
        cells |= inside
        top[inside] = np.fmax(top[inside], low[inside]+island["height_m"])
    return cells, top


def nogo_mask(obstacle, h, known, x, y, trees, lot, areas, curb_zone):
    """No-go cells inside the scope: band returns, steep relief, reviewed areas; none inside the parking lot.
    The relief rule skips the reviewed curb lines: their own strips (0.3 m on the ramp) represent them."""
    xy = obstacle[:, :2]
    hag = obstacle[:, 2]-bilinear(h, x, y, xy)
    band = (hag > BAND[0]) & (hag < BAND[1])
    c = np.round((xy[band, 0]-x[0])/(x[1]-x[0])).astype(int)//2
    r = np.round((xy[band, 1]-y[0])/(y[1]-y[0])).astype(int)//2
    shape = (-(-len(y)//2), -(-len(x)//2))
    ok = (c >= 0) & (c < shape[1]) & (r >= 0) & (r < shape[0])
    count = np.bincount(r[ok]*shape[1]+c[ok], minlength=shape[0]*shape[1]).reshape(shape)
    from_band = ndimage.binary_dilation(np.repeat(np.repeat(count >= MIN_RETURNS, 2, 0), 2, 1)[:len(y), :len(x)])
    relief = ((ndimage.maximum_filter(h, RELIEF_CELLS)-ndimage.minimum_filter(h, RELIEF_CELLS)) > RELIEF_M) & ~curb_zone
    blocked = from_band | relief
    gx, gy = np.meshgrid(x, y)
    for t in solid(trees):   # trunks and mounds block on their own
        blocked &= np.hypot(gx-t["trunk_xy"][0], gy-t["trunk_xy"][1]) > mound_radius(t)+.3
    blocked = (blocked | areas) & known
    stats = {"band_returns": int(band.sum()), "band_cells": int((from_band & known & ~lot).sum()),
             "relief_cells": int((relief & known & ~lot & ~from_band).sum()),
             "reviewed_area_cells": int((areas & known & ~lot).sum()),
             "parking_lot_cells_cleared": int((blocked & lot).sum())}
    blocked &= ~lot
    stats["obstacle_cells"] = int(blocked.sum())
    return blocked, stats


def plan_path(h, nogo, x, y, trees, anchors):
    """Shortest road path through the anchors keeping CLEARANCE_M from no-go and tree solids, centred."""
    step = x[1]-x[0]
    lo, hi = anchors.min(0)-10, anchors.max(0)+10
    xs, ys = np.flatnonzero((x >= lo[0]) & (x <= hi[0])), np.flatnonzero((y >= lo[1]) & (y <= hi[1]))
    sub = np.ix_(ys, xs)
    gx, gy = np.meshgrid(x[xs], y[ys])
    blocked = nogo[sub].copy()
    for t in solid(trees):
        blocked |= np.hypot(gx-t["trunk_xy"][0], gy-t["trunk_xy"][1]) <= mound_radius(t)
    clear = ndimage.distance_transform_edt(~blocked)*step
    sy, sx = np.gradient(h[sub].astype(float), step)
    ok = (clear >= CLEARANCE_M) & (np.hypot(sx, sy) <= MAX_SLOPE)
    ids = -np.ones(ok.shape, int)
    ids[ok] = np.arange(ok.sum())
    H, W = ok.shape
    rows, cols, cost = [], [], []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        c0, c1 = max(0, -dc), W-max(0, dc)
        a, b = (slice(0, H-dr), slice(c0, c1)), (slice(dr, H), slice(c0+dc, c1+dc))
        both = ok[a] & ok[b]
        rows.append(ids[a][both])
        cols.append(ids[b][both])
        cost.append(np.hypot(dr, dc)*step*(1+1.5/np.minimum(clear[a][both], 3)))
    rows, cols, cost = map(np.concatenate, (rows, cols, cost))
    n = int(ok.sum())
    graph = coo_matrix((np.r_[cost, cost], (np.r_[rows, cols], np.r_[cols, rows])), shape=(n, n)).tocsr()
    pts = np.column_stack([gx[ok], gy[ok]])
    snap = [int(np.argmin(np.linalg.norm(pts-a, axis=1))) for a in anchors]
    path = []
    for s, e in zip(snap, snap[1:]):
        _, pred = dijkstra(graph, indices=s, return_predecessors=True)
        if pred[e] < 0 and e != s:
            raise RuntimeError(f"No road path between anchors {pts[s]} and {pts[e]}")
        seg = [e]
        while seg[-1] != s:
            seg.append(pred[seg[-1]])
        path += seg[::-1][(1 if path else 0):]
    P = pts[path]

    def visible(a, b):
        t = np.linspace(0, 1, max(2, int(np.linalg.norm(b-a)/(step/2))))
        q = a+t[:, None]*(b-a)
        return bool(ok[np.round((q[:, 1]-y[ys[0]])/step).astype(int), np.round((q[:, 0]-x[xs[0]])/step).astype(int)].all())
    way, i = [P[0]], 0
    while i < len(P)-1:
        j = len(P)-1
        while j > i+1 and not visible(P[i], P[j]):
            j -= 1
        way.append(P[j])
        i = j
    way = np.round(np.array(way), 2)
    return way, {"clearance_m": CLEARANCE_M, "max_slope": MAX_SLOPE,
                 "anchor_shift_m": np.round(np.linalg.norm(pts[snap]-anchors, axis=1), 2).tolist(),
                 "length_m": round(float(np.linalg.norm(np.diff(way, axis=0), axis=1).sum()), 2)}


def write_hfield(path, values):
    lo, hi = float(values.min()), float(values.max())
    span = max(hi-lo, 1e-6)
    with path.open("wb") as f:
        f.write(np.array(values.shape, "<i4").tobytes())
        f.write(((values-lo)/span).astype("<f4").tobytes())
    return lo, span


def grid_mesh(x, y, h, cell_ok):
    gx, gy = np.meshgrid(x, y)
    idx = np.arange(h.size).reshape(h.shape)
    q = cell_ok[:-1, :-1] & cell_ok[1:, 1:] & cell_ok[:-1, 1:] & cell_ok[1:, :-1]
    a, b, c, d = idx[:-1, :-1][q], idx[:-1, 1:][q], idx[1:, 1:][q], idx[1:, :-1][q]
    faces = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    used, faces = np.unique(faces, return_inverse=True)
    return np.column_stack([gx.ravel(), gy.ravel(), h.ravel()])[used], faces.reshape(-1, 3)


def block_mesh(x, y, h, top, mask):
    """No-go area as a plateau at height `top` with vertical walls on its outline."""
    gx, gy = np.meshgrid(x, y)
    n = h.size
    idx = np.arange(n).reshape(h.shape)
    verts = np.vstack([np.column_stack([gx.ravel(), gy.ravel(), h.ravel()]), np.column_stack([gx.ravel(), gy.ravel(), top.ravel()])])
    q = mask[:-1, :-1] & mask[1:, 1:] & mask[:-1, 1:] & mask[1:, :-1]
    a, b, c, d = idx[:-1, :-1][q], idx[:-1, 1:][q], idx[1:, 1:][q], idx[1:, :-1][q]
    faces = [np.column_stack([a, b, c])+n, np.column_stack([a, c, d])+n]
    pad = np.pad(q, 1)
    for edge, nxt in ((pad[:-1, 1:-1] ^ pad[1:, 1:-1], (0, 1)), (pad[1:-1, :-1] ^ pad[1:-1, 1:], (1, 0))):
        r, c = np.nonzero(edge)
        u, v = idx[r, c], idx[r+nxt[0], c+nxt[1]]
        faces += [np.column_stack([u, v, v+n]), np.column_stack([u, v+n, u+n])]
    used, faces = np.unique(np.vstack(faces), return_inverse=True)
    return verts[used], faces.reshape(-1, 3)


def main():
    (SIM/"hfields").mkdir(parents=True, exist_ok=True)
    g = np.load(MESH_DIR/"ground_surface.npz")
    x, y, h, known = g["x"], g["y"], g["height"].astype(float), g["known"]
    obstacle = np.asarray(read_labelled(MAP_DIR/f"{MAP_VERSION}_obstacle.pcd")["xyzi"][:, :3], float)
    route = load_json(ROUTE)
    anchors = np.array([route["start"]["xy"], *route["via"], route["goal"]["xy"]], float)
    review, curb_cells = edits.load(), {}
    trees = segment(obstacle, (x, y, h), anchors.min(0)-TREE_MARGIN, anchors.max(0)+TREE_MARGIN)
    trees["review"] = edits.fix_trees(trees["trees"], ground_at, (x, y, h))
    ti = [(int(round((t["trunk_xy"][1]-y[0])/(y[1]-y[0]))), int(round((t["trunk_xy"][0]-x[0])/(x[1]-x[0])))) for t in trees["trees"]]
    in_scope = [0 <= i < len(y) and 0 <= j < len(x) and bool(known[i, j]) for i, j in ti]
    trees["outside_scope_dropped"] = [{"id": t["id"], "trunk_xy": t["trunk_xy"], "evidence": t["trunk_evidence"]}
                                      for t, keep in zip(trees["trees"], in_scope) if not keep]
    trees["trees"] = [t for t, keep in zip(trees["trees"], in_scope) if keep]
    lot = edits.polygon_mask(x, y, review["parking_lot"]["polygon_xy"]) & known
    areas, curb_zone, strip_zone = np.zeros(h.shape, bool), np.zeros(h.shape, bool), np.zeros(h.shape, bool)
    for area in review["nogo_areas"]:
        areas |= edits.polygon_mask(x, y, area["polygon_xy"])
    for curb in review["curbs"]:
        zr, zc, *_ = edits.near_line(x, y, curb["polyline_xy"], review["curb_step_half_width_m"])
        curb_zone[zr, zc] = True
        strip_zone[zr, zc] |= bool(curb.get("nogo"))
    blocked, nsum = nogo_mask(obstacle, h, known, x, y, trees["trees"], lot, areas, curb_zone)
    for clear in review.get("nogo_clear", []):   # reviewed false blocks
        blocked &= ~edits.polygon_mask(x, y, clear["polygon_xy"])
    curbs, curb_top = curb_rims(review, h, x, y)
    curbs &= known
    curb_only = curbs & ~blocked
    blocked |= curbs
    nsum.update({"curb_rim_cells": int(curbs.sum()), "curb_rim_cells_in_parking_lot": int((curbs & lot).sum()),
                 "obstacle_cells": int(blocked.sum())})
    nogo = blocked | ~known
    top = h+NOGO_M
    top[curb_only] = np.maximum(curb_top[curb_only], h[curb_only]+.05)   # curb height, not +0.8 m
    for curb in review["curbs"]:
        if curb.get("nogo"):
            r, c, curb_top, road = edits.curb_strip(h, x, y, curb, review["curb_step_half_width_m"])
            free = ~nogo[r, c]
            nogo[r, c] = True
            top[r[free], c[free]] = curb_top[free]
            curb_cells[curb["id"]] = {"cells": int(len(r)), "height_above_road_m_p10_p50_p90":
                                      np.percentile(curb_top-road, [10, 50, 90]).round(3).tolist()}
    path, psum = plan_path(h, nogo, x, y, trees["trees"], anchors)

    scene = ET.Element("mujoco", model=f"PAIR360 {MESH_VERSION} walking environment")
    ET.SubElement(scene, "option", timestep="0.002", gravity="0 0 -9.81")
    ET.SubElement(scene, "statistic", center=xyz_text([*anchors.mean(0), 2]), extent="40")
    asset, world = ET.SubElement(scene, "asset"), ET.SubElement(scene, "worldbody")
    half, centre = [(x[-1]-x[0])/2, (y[-1]-y[0])/2], [(x[-1]+x[0])/2, (y[-1]+y[0])/2]
    wall = ~known & (ndimage.distance_transform_edt(~known)*(x[1]-x[0]) <= SCOPE_WALL_M)
    nogo_values = np.where(known, np.where(nogo, top, h-.05), np.where(wall, top, h-SCOPE_DROP_M-.05))
    for name, values, group, rgba in (("pair360_ground_000", np.where(known, h, h-SCOPE_DROP_M), "0", ".38 .44 .42 1"),
                                      ("pair360_nogo_000", nogo_values, "4", ".55 .45 .38 1")):
        lo, span = write_hfield(SIM/f"hfields/{name}.bin", values)
        ET.SubElement(asset, "hfield", name=name, file=f"hfields/{name}.bin", size=xyz_text([*half, span, .1]))
        ET.SubElement(world, "geom", name=name, type="hfield", hfield=name, pos=xyz_text([*centre, lo]),
                      friction="1 0.005 0.0001", rgba=rgba, group=group)
    tree_geoms(trees["trees"], world)
    ET.indent(scene)
    ET.ElementTree(scene).write(SIM/"scene.xml", encoding="utf-8", xml_declaration=True)
    save_json(SIM/"trees.json", trees)
    z = lambda pts: bilinear(h, x, y, np.asarray(pts, float).reshape(-1, 2))  # noqa: E731
    manifest = {"mesh": MESH_VERSION, "map": MAP_VERSION, "frame": "pair360_map",
                "start": {**route["start"], "z": float(z(route["start"]["xy"])[0])},
                "goal": {**route["goal"], "z": float(z(route["goal"]["xy"])[0])}, "via": route["via"],
                "spawn_yaw_deg": route["start"]["yaw_deg"],
                "route_xyz_m": np.column_stack([path, z(path)]).round(3).tolist(), "reference_path": psum,
                "nogo": {**nsum, "band_above_ground_m": list(BAND), "min_returns_per_0.2m_cell": MIN_RETURNS,
                         "relief_m_in_window": [RELIEF_M, round(RELIEF_CELLS*float(x[1]-x[0]), 2)],
                         "raised_m": NOGO_M, "cells_in_scope": int((nogo & known).sum()), "curb_strips": curb_cells,
                         "reviewed_areas": [a["id"] for a in review["nogo_areas"]]},
                "scope": {"cells": int(known.sum()), "area_m2": round(float(known.sum()*(x[1]-x[0])**2), 1),
                          "outside": f"no-go wall {SCOPE_WALL_M} m wide along the edge (group 4, hidden by default); "
                                     f"visible ground {SCOPE_DROP_M} m lower beyond"},
                "parking_lot": {"cells": int(lot.sum()), "no_go_cells": int((nogo & lot).sum())},
                "trees": {"count": len(trees["trees"]), "area_xy": trees["area_xy"],
                          "outside_scope_dropped": trees["outside_scope_dropped"]}}
    gv, gf = grid_mesh(x, y, h, known)
    write_ply(MESH_DIR/f"{MESH_VERSION}_ground.ply", gv, gf, np.tile(np.array(GROUND_MESH_RGB, np.uint8), (len(gv), 1)))
    bv, bf = block_mesh(x, y, h, top, nogo & known)
    write_ply(MESH_DIR/f"{MESH_VERSION}_obstacle.ply", bv, bf, np.tile([140, 115, 97], (len(bv), 1)).astype(np.uint8))
    rv, rf = route_mesh(np.asarray(path, float), h, x, y)
    write_ply(MESH_DIR/f"{MESH_VERSION}_route.ply", rv, rf, np.tile(np.array([230, 20, 20], np.uint8), (len(rv), 1)))
    tv, tf, tc = scene_shapes(SIM/"scene.xml")
    write_ply(MESH_DIR/f"{MESH_VERSION}_trees.ply", tv, tf, tc)
    manifest["meshes"] = {f"{MESH_VERSION}_ground.ply": len(gf), f"{MESH_VERSION}_obstacle.ply": len(bf),
                          f"{MESH_VERSION}_trees.ply": len(tf)}
    save_json(SIM/"manifest.json", manifest)
    print("trees", len(trees["trees"]), "no-go cells in scope", int((nogo & known).sum()), nsum, "reference path", psum)


if __name__ == "__main__":
    main()
