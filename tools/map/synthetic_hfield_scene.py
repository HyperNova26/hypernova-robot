#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""합성 지형(평지, 일정 경사 오르막)의 MuJoCo hfield 장면을 만듭니다. hfield_scene_import.py의 입력 형식(mesh_v3와 같음)입니다.

시뮬레이터 사이 보행 차이를 가릴 때, 경로 추종기와 지형 복잡도를 빼고 "같은 명령으로 같은 지형에서 얼마나 빨리 가는가"만 보려고 씁니다.
출력 폴더/scene/scene.xml + hfields/{ground,nogo}.bin. 지형은 x -10..50 m, y -20..20 m, 간격 0.1 m이고 시작점 (0, 0)에서 +x 방향으로 걷습니다.
  flat    z = 0
  ramp    z = max(0, x - 3) * tan(slope)   (x < 3 m는 평지, 그 뒤로 일정 경사. --slope-deg)
실행(호스트의 python3 + numpy면 충분합니다):
  python3 tools/map/synthetic_hfield_scene.py --kind ramp --slope-deg 10 --out ~/hypernova-data/sim_parity/ramp10
그 뒤 같은 폴더의 scene/scene.xml을 hfield_scene_import.py에 넣어 derived/를 만듭니다(그 파일 머리말). 출력 폴더가 있으면 거부합니다.
"""
from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

import numpy as np

X0, X1, Y0, Y1, RES = -10.0, 50.0, -20.0, 20.0, 0.1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", choices=("flat", "ramp"), required=True)
    ap.add_argument("--slope-deg", type=float, default=10.0, help="ramp의 경사 [deg]")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"출력 경로가 이미 있습니다: {args.out}")

    ncol, nrow = round((X1 - X0) / RES) + 1, round((Y1 - Y0) / RES) + 1
    xs = X0 + RES * np.arange(ncol)
    z_row = np.zeros(ncol) if args.kind == "flat" else np.maximum(0.0, xs - 3.0) * math.tan(math.radians(args.slope_deg))
    z = np.tile(z_row, (nrow, 1))                                   # 행(y)마다 같음
    height = float(z.max()) if z.max() > 0 else 1.0                 # size[2]. 평지는 정규화 값이 모두 0이라 값이 무엇이든 높이는 0
    norm = (z / height).astype(np.float32)

    (args.out / "scene" / "hfields").mkdir(parents=True)
    for name in ("ground", "nogo"):
        with open(args.out / "scene" / "hfields" / f"{name}.bin", "wb") as f:
            f.write(struct.pack("<ii", nrow, ncol))
            f.write(norm.tobytes())
    cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
    xml = f'''<mujoco model="synthetic {args.kind}">
  <option timestep="0.002" gravity="0 0 -9.81" />
  <asset>
    <hfield name="pair360_ground_000" file="hfields/ground.bin" size="{(X1 - X0) / 2} {(Y1 - Y0) / 2} {height} 0.1" />
    <hfield name="pair360_nogo_000" file="hfields/nogo.bin" size="{(X1 - X0) / 2} {(Y1 - Y0) / 2} {height} 0.1" />
  </asset>
  <worldbody>
    <geom name="pair360_ground_000" type="hfield" hfield="pair360_ground_000" pos="{cx} {cy} 0" friction="1 0.005 0.0001" rgba=".38 .44 .42 1" group="0" />
    <geom name="pair360_nogo_000" type="hfield" hfield="pair360_nogo_000" pos="{cx} {cy} -0.05" friction="1 0.005 0.0001" rgba=".55 .45 .38 1" group="4" />
  </worldbody>
</mujoco>
'''
    (args.out / "scene" / "scene.xml").write_text(xml, encoding="utf-8")
    print(f"[SYNTH] {args.kind} 경사 {args.slope_deg if args.kind == 'ramp' else 0} deg, {nrow}행 x {ncol}열, 높이 {z.max():.2f} m -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
