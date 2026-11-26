"""Step 5. After alignment, drop returns that only one capture saw (people, scanner trail, moved objects).

On a 0.2 m grid, a return 0.12-3 m above its floor is transient when the other capture measured the
floor there (>= 3 floor returns per 0.5 m cell, one cell of slack for the scanner's own shadow) and has
no raised return within 0.4 m. pc_v1 is dense, so 3 returns per cell confirm a pc_v2 object;
one pc_v2 return is enough to keep a pc_v1 object.

In : work/02_<pc>_labels.npy, work/02_<pc>_hag.npy, frames.map_xyzi (steps 3-4)
Out: work/05_<pc>_transient.npy (bool per source row), work/05_change.json
"""
import numpy as np
from scipy import ndimage

from config import GROUND, OBSTACLE, work
from frames import map_xyzi
from pcio import save_json

LO, REACH = np.array([-130.0, 30.0]), 2
CONFIRM = {"pc_v1": 3, "pc_v2": 1}


def grid_index(xy, cell, shape):
    ij = np.clip(np.floor((xy-LO)/cell).astype(int), 0, np.array(shape[::-1])-1)
    return ij[:, 1], ij[:, 0]


def counts(xy, cell, shape):
    r, c = grid_index(xy, cell, shape)
    return np.bincount(r*shape[1]+c, minlength=shape[0]*shape[1]).reshape(shape)


def main():
    fine, coarse = (1200, 1200), (480, 480)          # 0.2 m and 0.5 m cells over 240 m
    data = {}
    for key in ("pc_v1", "pc_v2"):
        xy = map_xyzi(key)[:, :2]
        labels, hag = np.load(work(f"02_{key}_labels.npy")), np.load(work(f"02_{key}_hag.npy")).astype(float)
        raised = (labels == OBSTACLE) & (hag > .12) & (hag < 3.0)
        data[key] = dict(xy=xy, raised=raised, raised_count=counts(xy[raised], .2, fine),
                         floor_count=counts(xy[labels == GROUND], .5, coarse))
    report = {}
    for key, other in (("pc_v1", "pc_v2"), ("pc_v2", "pc_v1")):
        d, o = data[key], data[other]
        confirmed = ndimage.binary_dilation(o["raised_count"] >= CONFIRM[other], iterations=REACH)
        seen = ndimage.binary_dilation(o["floor_count"] >= 3)
        r, c = grid_index(d["xy"], .2, fine)
        r5, c5 = grid_index(d["xy"], .5, coarse)
        transient = d["raised"] & seen[r5, c5] & ~confirmed[r, c]
        np.save(work(f"05_{key}_transient.npy"), transient)
        report[key] = {"raised_rows": int(d["raised"].sum()), "transient_rows": int(transient.sum())}
        print(key, report[key])
    save_json(work("05_change.json"), report)


if __name__ == "__main__":
    main()
