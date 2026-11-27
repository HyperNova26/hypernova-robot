# SPDX-License-Identifier: Apache-2.0
"""Write PAIR360 map v1 as PCD: the raw pc_v1 rows split by the pc_v1 ground v1 (v9) partition.

map_v1_ground.pcd     label 1, the rows listed in the partition's ground.ply (original_index), green
map_v1_non_ground.pcd label 2, every other row (vehicles, trees and buildings are not separated), orange
map_v1.pcd            both, ground rows first
Fields match map_v3: x y z intensity (float32), label, source (1 = pc_v1), rgb (uint32 0xRRGGBB). Each file keeps
raw row order. Frame pair360_map (raw PAIR360 XYZ, m, Z up).

python export_map_v1_pcd.py --source <pc_v1 PLY> --ground <v9 partition>/ground.ply --out <new folder>
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from review_cloud_io import load_xyzi_ply

GROUND_RGB, NON_GROUND_RGB = (46, 204, 64), (255, 133, 27)
PLY_TYPES = {"float": "<f4", "double": "<f8", "uint": "<u4", "int": "<i4", "uchar": "u1", "char": "i1",
             "ushort": "<u2", "short": "<i2"}


def ply_column(path: Path, name: str) -> np.ndarray:
    """One vertex property of a binary little-endian PLY with only scalar vertex properties."""
    with path.open("rb") as stream:
        fields, count = [], 0
        while (line := stream.readline().decode("ascii").strip()) != "end_header":
            parts = line.split()
            if parts[:2] == ["element", "vertex"]:
                count = int(parts[2])
            elif parts[0] == "property":
                fields.append((parts[2], PLY_TYPES[parts[1]]))
        offset = stream.tell()
    return np.memmap(path, np.dtype(fields), "r", offset, (count,))[name]


def write_pcd(path: Path, xyzi: np.ndarray, label: np.ndarray, rgb: np.ndarray) -> None:
    data = np.empty(len(xyzi), [("xyzi", "<f4", (4,)), ("label", "<u4"), ("source", "<u4"), ("rgb", "<u4")])
    data["xyzi"], data["label"], data["source"] = xyzi, label, 1
    rgb = np.asarray(rgb, np.uint32).reshape(-1, 3)
    data["rgb"] = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    header = ("VERSION 0.7\nFIELDS x y z intensity label source rgb\nSIZE 4 4 4 4 4 4 4\nTYPE F F F F U U U\n"
              f"COUNT 1 1 1 1 1 1 1\nWIDTH {len(data)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(data)}\nDATA binary\n")
    with path.open("xb") as stream:
        stream.write(header.encode("ascii"))
        data.tofile(stream)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True, help="raw pc_v1 PLY (x y z scalar_intensity)")
    ap.add_argument("--ground", type=Path, required=True, help="v9 partition ground.ply with original_index")
    ap.add_argument("--out", type=Path, required=True, help="new output folder")
    args = ap.parse_args()
    raw = np.asarray(load_xyzi_ply(args.source))
    is_ground = np.zeros(len(raw), bool)
    is_ground[np.asarray(ply_column(args.ground, "original_index"))] = True
    ground, rest = raw[is_ground], raw[~is_ground]
    args.out.mkdir(parents=True)
    write_pcd(args.out/"map_v1_ground.pcd", ground, np.ones(len(ground), np.uint32), np.tile(GROUND_RGB, (len(ground), 1)))
    write_pcd(args.out/"map_v1_non_ground.pcd", rest, np.full(len(rest), 2, np.uint32),
              np.tile(NON_GROUND_RGB, (len(rest), 1)))
    label = np.r_[np.ones(len(ground), np.uint32), np.full(len(rest), 2, np.uint32)]
    write_pcd(args.out/"map_v1.pcd", np.concatenate([ground, rest]), label,
              np.array([GROUND_RGB, NON_GROUND_RGB])[label-1])
    print(f"map_v1: ground {len(ground):,}, non-ground {len(rest):,} -> {args.out}")


if __name__ == "__main__":
    main()
