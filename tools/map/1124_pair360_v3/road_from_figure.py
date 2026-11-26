"""S-009 road mask: the light-blue "통행 도로" of the S-009 Nav2 figure (김완준, 2026-11-23, "통행 도로와 통행불가 구역
(실기용)") moved onto the 0.1 m map grid. In that figure the road was painted by hand and the 0.4 m margin already
drawn as no-go, so road = light blue, plus the obstacle dots and the 11-15 path line drawn on it.

Usage: python road_from_figure.py <figure.png> <out road_mask.png>   (grid = config MAP grid from step 7)
Figure axes (1200 x 1320 px export): x -80..60 m at px 100..1141, y 220..80 m at px 72..1114; the legend box is
not road. Output: 8-bit PNG on the map grid, rows top (max y) first, 255 = road, 0 = not road.
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

from config import MESH_DIR

X_PX, Y_PX = ((-80, 100), (60, 1141)), ((220, 72), (80, 1114))
LEGEND_PX = (975, 1100, 1170, 1225)   # x0, y0, x1, y1


def main(figure, out):
    im = np.asarray(Image.open(figure).convert("RGB")).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    blue = (b > 230) & (b - r > 12) & (g > 215)              # road fill
    dots = (im.sum(2) < 260) & (np.abs(r - b) < 30)           # grey-black obstacle dots drawn on the road
    path = ndimage.binary_dilation((g - r > 40) & (g - b > 20), iterations=3)   # 11-15 path line drawn over the road
    near = ndimage.binary_dilation(blue, iterations=4)
    road_px = ndimage.binary_closing(blue | ((dots | path) & near), iterations=2)
    road_px = ndimage.binary_fill_holes(road_px)
    x0, y0, x1, y1 = LEGEND_PX
    road_px[y0:y1, x0:x1] = False
    labels, n = ndimage.label(road_px)
    sizes = ndimage.sum(road_px, labels, range(1, n + 1))
    road_px = labels == (np.argmax(sizes) + 1)               # one connected road network

    grid = np.load(MESH_DIR/"ground_surface.npz")
    gx, gy = np.meshgrid(grid["x"], grid["y"])
    (xa, pa), (xb, pb) = X_PX
    (ya, qa), (yb, qb) = Y_PX
    px = np.round(pa + (gx - xa) * (pb - pa) / (xb - xa)).astype(int)
    py = np.round(qa + (gy - ya) * (qb - qa) / (yb - ya)).astype(int)
    inside = (px >= 0) & (px < im.shape[1]) & (py >= 0) & (py < im.shape[0])
    road = np.zeros(gx.shape, bool)
    road[inside] = road_px[py[inside], px[inside]]
    Image.fromarray(np.flipud(np.where(road, 255, 0)).astype(np.uint8), mode="L").save(out, optimize=True)
    print(f"road cells {int(road.sum())} ({road.sum() * 0.01:.0f} m2)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
