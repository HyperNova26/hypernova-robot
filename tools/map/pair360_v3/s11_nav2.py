"""Step 11. Nav2 inputs: static map (map_server) and keep-out mask (KeepoutFilter), 0.1 m, frame pair360_map.

map.png: free 254 = ground in scope and not no-go, occupied 0 = s08 no-go cells, unknown 205 = outside the mesh scope.
free_thresh 0.1: map_server reads 205 as (255-205)/255 = 0.196, which the usual 0.25 would turn into free space.
keepout_mask.png: occupied 0 = zones decided 'keepout' in the keep-out zones JSON (config.KEEPOUT_ZONES) and everything outside the mesh scope, free 254 elsewhere.
Pixel centres sit on the step-7 grid points, so the lower-left corner (yaml origin) is half a cell below/left of them.
Out: results/nav2_v3/{map,keepout_mask}.{png,yaml}, manifest.json, preview.png.
"""
import json
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path as Polygon
from PIL import Image

from config import KEEPOUT_ZONES, MESH_DIR, RESULTS
from pcio import save_json, sha256

SIM = MESH_DIR/"mujoco"
OUT = RESULTS/"nav2_v3"
FREE, OCCUPIED, UNKNOWN = 254, 0, 205
YAML = """image: {image}
mode: trinary
resolution: {res}
origin: [{ox:.3f}, {oy:.3f}, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.1
"""


def hfield(name):
    """MuJoCo hfield heights in metres (normalised values x elevation + geom z)."""
    scene = (SIM/"scene.xml").read_text()
    elevation = float(re.search(rf'hfield name="{name}"[^>]*size="[^ ]+ [^ ]+ ([^ ]+)', scene).group(1))
    z = float(re.search(rf'geom name="{name}"[^>]*pos="[^ ]+ [^ ]+ ([^"]+)"', scene).group(1))
    raw = (SIM/f"hfields/{name}.bin").read_bytes()
    rows, cols = np.frombuffer(raw[:8], "<i4")
    return np.frombuffer(raw[8:], "<f4").reshape(rows, cols)*elevation+z


def write_map(stem, grid, res, origin):
    """8-bit greyscale PNG (lossless), rows from top (max y) to bottom as map_server expects, and its yaml."""
    Image.fromarray(np.flipud(grid).astype(np.uint8), mode="L").save(OUT/f"{stem}.png", optimize=True)
    (OUT/f"{stem}.yaml").write_text(YAML.format(image=f"{stem}.png", res=res, ox=origin[0], oy=origin[1]))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    surface = np.load(MESH_DIR/"ground_surface.npz")
    x, y, scope = surface["x"], surface["y"], surface["known"]
    res = round(float(x[1]-x[0]), 6)
    origin = (float(x[0])-res/2, float(y[0])-res/2)
    nogo = (hfield("pair360_nogo_000")-hfield("pair360_ground_000")) > .1

    occupancy = np.full(scope.shape, UNKNOWN, np.uint8)
    occupancy[scope] = FREE
    occupancy[scope & nogo] = OCCUPIED
    write_map("map", occupancy, res, origin)

    zones = json.loads(KEEPOUT_ZONES.read_text(encoding="utf-8"))["zones"]
    gx, gy = np.meshgrid(x, y)
    cells = np.column_stack([gx.ravel(), gy.ravel()])
    keepout = np.zeros(scope.shape, bool)
    for z in zones:
        if z["decision"] == "keepout":
            keepout |= Polygon(np.asarray(z["polygon_xy"])).contains_points(cells).reshape(scope.shape)
    # Outside the mesh scope is also keep-out: Nav2's static layer can leave unknown cells at cost 0
    # (seen 2026-11-24 when the map arrives after costmap activation), and planners allow unknown by default.
    write_map("keepout_mask", np.where(keepout | ~scope, OCCUPIED, FREE), res, origin)

    walkable = scope & ~nogo & ~keepout
    cell_m2 = res*res
    save_json(OUT/"manifest.json", {
        "frame": "pair360_map", "resolution_m": res, "origin_xy": [round(v, 3) for v in origin],
        "size_px": [int(scope.shape[1]), int(scope.shape[0])],
        "source": {"terrain": "mesh_v3 (s07 ground grid, s08 no-go hfield)", "zones": "the keep-out zones JSON (config.KEEPOUT_ZONES)"},
        "area_m2": {"free": round(float((scope & ~nogo).sum())*cell_m2), "no_go": round(float((scope & nogo).sum())*cell_m2),
                    "keepout_on_free": round(float((scope & ~nogo & keepout).sum())*cell_m2),
                    "walkable_after_keepout": round(float(walkable.sum())*cell_m2)},
        "keepout_zones": [z["id"] for z in zones if z["decision"] == "keepout"],
        "sha256": {f: sha256(OUT/f) for f in ("map.png", "map.yaml", "keepout_mask.png", "keepout_mask.yaml")},
    })

    img = np.empty(scope.shape+(3,))
    img[:] = (.82, .87, .95)
    img[walkable] = (1, 1, 1)
    img[scope & nogo] = (0, 0, 0)
    img[scope & ~nogo & keepout] = (.85, .45, .45)
    fig, ax = plt.subplots(figsize=(14, 14))
    ax.imshow(img, origin="lower", extent=[origin[0], origin[0]+scope.shape[1]*res, origin[1], origin[1]+scope.shape[0]*res])
    ax.set_title("Nav2 inputs: white = walkable, black = no-go (map.png), red = keep-out (keepout_mask.png), pale blue = unknown")
    ax.set_aspect("equal")
    ax.grid(lw=.3)
    fig.savefig(OUT/"preview.png", dpi=70, bbox_inches="tight")
    print(json.dumps(json.loads((OUT/"manifest.json").read_text())["area_m2"]))


if __name__ == "__main__":
    main()
