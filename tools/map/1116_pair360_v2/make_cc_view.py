"""One CloudCompare folder for map_v2 (pair360_map): inputs by version, the ground/obstacle split and mesh_v2.

Each file loads as its own entity, so every layer can be toggled in the DB tree.
python make_cc_view.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from audit_ground import RELEASE
from register_maps import FRAME_KEY, read_points, sources, transform

V2 = RELEASE/"map_v2"
OUT = RELEASE/"cc_view_map_v2"


def write_pcd(path, xyz, intensity, field, values):
    data = np.empty(len(xyz), dtype=[("xyzi", "<f4", (4,)), (field, "<u4")])
    data["xyzi"][:, :3], data["xyzi"][:, 3], data[field] = xyz, intensity, values
    header = (f"VERSION 0.7\nFIELDS x y z intensity {field}\nSIZE 4 4 4 4 4\nTYPE F F F F U\nCOUNT 1 1 1 1 1\n"
              f"WIDTH {len(data)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(data)}\nDATA binary\n")
    with path.open("wb") as stream:
        stream.write(header.encode("ascii"))
        data.tofile(stream)
    return len(data)


def main():
    OUT.mkdir(exist_ok=True)
    frame = json.loads((RELEASE/"output/frame.json").read_text())
    counts = {}
    # Inputs in pair360_map; label = merged automatic class (0 unknown, 1 ground, 2 trunk, 3 foliage,
    # 4 structure, 5 vehicle, 6 noise). pc_v3 is shown before its z correction.
    for name, key in (("01_pc_v1_input", "pc_v1"), ("02_pc_v3_input", "pc_v3")):
        raw = np.asarray(read_points(sources()[key]), float)
        xyz = transform(raw[:, :3], np.array(frame["source_to_map"][FRAME_KEY[key]]))
        labels = np.load(RELEASE/f"classification/{key}_merged_labels.npy")
        counts[name] = write_pcd(OUT/f"{name}.pcd", xyz, raw[:, 3], "label", labels)
    for i, name in enumerate(("map_v2_ground", "map_v2_obstacle", "map_v2_removed_dynamic"), 3):
        shutil.copyfile(V2/f"pc/{name}.pcd", OUT/f"{i:02d}_{name}.pcd")
    for i, name in enumerate(("mesh_v2_ground", "mesh_v2_obstacle", "mesh_v2_trees"), 6):
        shutil.copyfile(V2/f"mesh/{name}.ply", OUT/f"{i:02d}_{name}.ply")
    (OUT/"contents.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
