"""Step 11. Nav2 inputs: static map (map_server) and keep-out mask (KeepoutFilter), 0.1 m, frame pair360_map.

Rules follow S-009 (Nav2 global path, 김완준): obstacles are map_v3 static returns 0.25-1.0 m above the step-7 ground;
keep-out is everything off the road painted in the S-009 figure (its 0.4 m margin is already painted as no-go).
map.png: free 254 = ground in scope without an obstacle return, occupied 0 = a 0.1 m cell holding >= MIN_RETURNS
returns 0.25-1.0 m above the ground, unknown 205 = outside the mesh scope.
free_thresh 0.1: map_server reads 205 as (255-205)/255 = 0.196, which the usual 0.25 would turn into free space.
keepout_mask.png: occupied 0 = off the S-009 road (config.ROAD_MASK, made by road_from_figure.py) and everything
outside the mesh scope, free 254 elsewhere.
Pixel centres sit on the step-7 grid points, so the lower-left corner (yaml origin) is half a cell below/left of them.
In : results/mesh_v3/ground_surface.npz, results/map_v3/map_v3_obstacle.pcd, config.ROAD_MASK
Out: results/nav2_v3/{map,keepout_mask}.{png,yaml}, manifest.json, preview.png.
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy import ndimage

from config import MAP_DIR, MAP_VERSION, MESH_DIR, RESULTS, ROAD_MASK
from pcio import read_labelled, save_json, sha256

OUT = RESULTS/"nav2_v3"
BAND, MIN_RETURNS = (0.25, 1.0), 1      # S-009: obstacle = 0.25-1.0 m above the ground
FREE, OCCUPIED, UNKNOWN = 254, 0, 205
YAML = """image: {image}
mode: trinary
resolution: {res}
origin: [{ox:.3f}, {oy:.3f}, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.1
"""


def write_map(stem, grid, res, origin):
    """8-bit greyscale PNG (lossless), rows from top (max y) to bottom as map_server expects, and its yaml."""
    Image.fromarray(np.flipud(grid).astype(np.uint8), mode="L").save(OUT/f"{stem}.png", optimize=True)
    (OUT/f"{stem}.yaml").write_text(YAML.format(image=f"{stem}.png", res=res, ox=origin[0], oy=origin[1]))


def obstacle_cells(x, y, h):
    """0.1 m cells holding >= MIN_RETURNS static obstacle returns BAND above the ground surface."""
    xyz = np.asarray(read_labelled(MAP_DIR/f"{MAP_VERSION}_obstacle.pcd")["xyzi"][:, :3], float)
    col = (xyz[:, 0]-x[0])/(x[1]-x[0])
    row = (xyz[:, 1]-y[0])/(y[1]-y[0])
    hag = xyz[:, 2]-ndimage.map_coordinates(h, [row, col], order=1, mode="nearest")
    c, r = np.round(col).astype(int), np.round(row).astype(int)
    ok = (hag > BAND[0]) & (hag < BAND[1]) & (c >= 0) & (c < len(x)) & (r >= 0) & (r < len(y))
    count = np.bincount(r[ok]*len(x)+c[ok], minlength=len(x)*len(y)).reshape(len(y), len(x))
    return count >= MIN_RETURNS


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    surface = np.load(MESH_DIR/"ground_surface.npz")
    x, y, h, scope = surface["x"], surface["y"], surface["height"], surface["known"]
    res = round(float(x[1]-x[0]), 6)
    origin = (float(x[0])-res/2, float(y[0])-res/2)
    nogo = obstacle_cells(x, y, h) & scope

    occupancy = np.full(scope.shape, UNKNOWN, np.uint8)
    occupancy[scope] = FREE
    occupancy[nogo] = OCCUPIED
    write_map("map", occupancy, res, origin)

    road = np.flipud(np.asarray(Image.open(ROAD_MASK))) > 0
    if road.shape != scope.shape:
        raise SystemExit(f"{ROAD_MASK} is {road.shape}, the map grid is {scope.shape}; rerun road_from_figure.py")
    keepout = ~road
    # Outside the mesh scope is also keep-out: Nav2's static layer can leave unknown cells at cost 0
    # (seen 2026-11-24 when the map arrives after costmap activation), and planners allow unknown by default.
    write_map("keepout_mask", np.where(keepout | ~scope, OCCUPIED, FREE), res, origin)

    walkable = scope & ~nogo & ~keepout
    cell_m2 = res*res
    save_json(OUT/"manifest.json", {
        "frame": "pair360_map", "resolution_m": res, "origin_xy": [round(v, 3) for v in origin],
        "size_px": [int(scope.shape[1]), int(scope.shape[0])],
        "obstacle": {"band_above_ground_m": list(BAND), "min_returns_per_0.1m_cell": MIN_RETURNS},
        "source": {"ground": "mesh_v3 step-7 ground grid", "obstacles": f"{MAP_VERSION}_obstacle.pcd",
                   "road": f"{ROAD_MASK.name} (S-009 figure, road_from_figure.py)", "road_sha256": sha256(ROAD_MASK)},
        "area_m2": {"in_scope": round(float(scope.sum())*cell_m2), "obstacle": round(float(nogo.sum())*cell_m2),
                    "road": round(float((road & scope).sum())*cell_m2), "walkable": round(float(walkable.sum())*cell_m2)},
        "sha256": {f: sha256(OUT/f) for f in ("map.png", "map.yaml", "keepout_mask.png", "keepout_mask.yaml")},
    })

    img = np.empty(scope.shape+(3,))
    img[:] = (.82, .87, .95)
    img[walkable] = (1, 1, 1)
    img[scope & keepout & ~nogo] = (.85, .45, .45)
    img[nogo] = (0, 0, 0)
    fig, ax = plt.subplots(figsize=(14, 14))
    ax.imshow(img, origin="lower", extent=[origin[0], origin[0]+scope.shape[1]*res, origin[1], origin[1]+scope.shape[0]*res])
    ax.set_title("Nav2 inputs: white = walkable, black = obstacle 0.25-1.0 m (map.png), red = off road (keepout_mask.png), "
                 "pale blue = unknown")
    ax.set_aspect("equal")
    ax.grid(lw=.3)
    fig.savefig(OUT/"preview.png", dpi=70, bbox_inches="tight")
    print(json.dumps(json.loads((OUT/"manifest.json").read_text())["area_m2"]))


if __name__ == "__main__":
    main()
