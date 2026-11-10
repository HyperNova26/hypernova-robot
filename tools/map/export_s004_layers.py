# SPDX-License-Identifier: Apache-2.0
"""Partition source XYZI rows into final observed-ground and remainder PLYs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from review_cloud_io import load_xyzi_ply, write_review_ply


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tolerance-m", type=float, default=.15)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    if not 0 < args.tolerance_m < 1:
        raise ValueError("tolerance must be in (0, 1) metre")
    source = load_xyzi_ply(args.source)
    labels = np.load(args.classification)["point_type"]
    surface = np.load(args.surface)
    if len(labels) != len(source):
        raise ValueError("classification/source row count mismatch")
    x, y, height, permitted = (surface[name] for name in ("x", "y", "height", "permitted"))
    ix = np.rint((source[:, 0] - x[0]) / (x[1] - x[0])).astype(np.int64)
    iy = np.rint((source[:, 1] - y[0]) / (y[1] - y[0])).astype(np.int64)
    valid = (ix >= 0) & (ix < len(x)) & (iy >= 0) & (iy < len(y))
    floor = np.full(len(source), np.nan)
    floor[valid] = height[iy[valid], ix[valid]]
    ground = ((labels == 1) & valid & permitted[iy.clip(0, len(y)-1), ix.clip(0, len(x)-1)]
              & np.isfinite(floor) & (np.abs(source[:, 2] - floor) <= args.tolerance_m))
    args.out.mkdir(parents=True)
    counts = {}
    for name, mask, rgb, code in (("ground", ground, (105, 210, 155), 1),
                                  ("non_ground", ~ground, (145, 97, 66), 2)):
        indices = np.flatnonzero(mask).astype(np.uint32)
        points = np.ascontiguousarray(source[indices], dtype="<f4")
        write_review_ply(args.out / f"{name}.ply", points, indices, rgb,
                         review_class=code, provenance_fields={"scalar_source_partition": code})
        counts[name] = len(indices)
    if counts["ground"] + counts["non_ground"] != len(source):
        raise AssertionError("source partition lost rows")
    report = {"source_rows": len(source), **counts, "tolerance_m": args.tolerance_m,
              "partition_exhaustive_and_disjoint": True}
    (args.out / "partition.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
