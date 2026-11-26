"""Source rows of each cloud in the final pair360_map frame (step 3 rigid fit, step 4 local fit)."""
import numpy as np

from config import PC, work
from pcio import load_json, read_xyzi, transform


def map_xyzi(key):
    """(N, 4) float64 x, y, z, intensity in pair360_map, same row order as the source file."""
    p = np.array(read_xyzi(PC[key]), dtype=float)
    if key == "pc_v2":
        p[:, :3] = transform(p[:, :3], load_json(work("03_register.json"))["pc_v2_to_map"])
    else:
        from s04_local_fit import apply
        p[:, :3] = apply(p[:, :3])
    return p
