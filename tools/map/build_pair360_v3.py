#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
"""Build PAIR360 map_v3 (merged point cloud), mesh_v3 (MuJoCo terrain) and the Nav2 map from two captures.

Steps live in tools/map/pair360_v3/ (s01..s11); see sim_scenes/pair360_v3_decisions/README.md.
Inputs: --data (point clouds, reviewed S-004 ground, Go2 model; not in Git), --decisions (hand-made
decisions in Git), --road (S-009 road mask for the Nav2 keep-out). Every result goes under --out.
"""
import argparse
import importlib
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().with_name("pair360_v3")
STEPS = ["s01_inputs", "s02_dynamic", "s03_register", "check_vehicles", "s04_local_fit", "s05_change",
         "s06_merge", "s07_ground", "s08_mesh", "s09_verify", "s10_bundle", "s11_nav2"]
REQUIRED = ["raw/pc_v1_pair360_t1_parking_demo.ply", "raw/pc_v2_20261115.pcd",
            "reviewed/pc_v1_ground_v1/ground_surface.npz", "reviewed/pc_v1_ground_v1_partition/ground.ply",
            "models/unitree_go2/go2.xml"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=REPO/"data/pair360_v3", help="input data folder (default: %(default)s)")
    ap.add_argument("--decisions", type=Path, default=REPO/"sim_scenes/pair360_v3_decisions")
    ap.add_argument("--road", type=Path, default=REPO/"sim_scenes/pair360_nav2/road_s009.png")
    ap.add_argument("--out", type=Path, default=REPO/"data/pair360_v3_results", help="result folder (default: %(default)s)")
    ap.add_argument("--steps", nargs="+", choices=STEPS, help="run only these steps, in pipeline order")
    ap.add_argument("--cloudcompare", action="store_true",
                    help="also run s10_bundle (needs CloudCompare; set CLOUDCOMPARE to its executable)")
    args = ap.parse_args()

    missing = [p for p in REQUIRED if not (args.data/p).exists()]
    if missing and (not args.steps or {"s01_inputs", "s02_dynamic"} & set(args.steps)):
        sys.exit("Missing input files under {}:\n  {}".format(args.data, "\n  ".join(missing)))
    os.environ.update(HN_PAIR360_DATA=str(args.data.resolve()), HN_PAIR360_DECISIONS=str(args.decisions.resolve()),
                      HN_PAIR360_ROAD=str(args.road.resolve()), HN_PAIR360_OUT=str(args.out.resolve()))
    sys.path.insert(0, str(PACKAGE))
    for name in [s for s in STEPS if (s in args.steps if args.steps else s != "s10_bundle" or args.cloudcompare)]:
        start = time.time()
        print(f"== {name}", flush=True)
        importlib.import_module(name).main()
        print(f"== {name} done in {time.time()-start:.0f} s", flush=True)


if __name__ == "__main__":
    main()
