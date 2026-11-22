# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""teleop 시험용 일자 코스 지형 (Isaac Lab 3.0.0 terrain generator용 sub-terrain, 2026-11-20).

+x 방향으로 차례로: 출발 평지 → 오르막 → 꼭대기 평지 → 내리막 → 평지 → 계단 오르기 → 계단참 → 계단 내리기 → 도착 평지.
학습에는 쓰지 않습니다(policies/teleop.py --course).

난이도 level 0~9는 학습 지형과 같은 공식으로 바꿉니다. 범위는 teleop이 과제의 지형 설정에서 읽어 넘깁니다
(hf_pyramid_slope.slope_range, pyramid_stairs.step_height_range). 학습 curriculum에서 terrain level r은
difficulty (r + U(0, 1)) / 10을 받으므로, 여기서는 그 가운데 (r + 0.5) / 10을 씁니다.
    값 = 범위 최소 + (최대 − 최소) × difficulty
v1 Rough(Go2 설정, 2026-11-23 확인): 경사 0~0.4(높이/수평 거리), 계단 0.025~0.12 m(발판 0.3 m).
"""

import math

import numpy as np
import trimesh

from isaaclab.terrains import SubTerrainBaseCfg
from isaaclab.utils import configclass

WIDTH = 4.0  # 코스 폭 [m] (y)
FLAT = 3.0  # 출발·중간·도착 평지 길이 [m]
RAMP = 3.0  # 오르막·내리막 수평 길이 [m]
TOP = 2.0  # 꼭대기 평지·계단참 길이 [m]
STEP_WIDTH = 0.3  # 계단 발판 깊이 [m] (학습과 같음)
NUM_STEPS = 6  # 오르는 계단 수 (내리는 계단도 같음)
START_X = 1.5  # 코스 시작점에서 로봇 출발 위치까지 [m]


def level_to_difficulty(level: int) -> float:
    return (min(max(level, 0), 9) + 0.5) / 10.0


def _lerp(level: int, value_range: tuple[float, float]) -> float:
    lo, hi = value_range
    return lo + (hi - lo) * level_to_difficulty(level)


def slope_of(level: int, slope_range: tuple[float, float]) -> float:
    return _lerp(level, slope_range)


def step_height_of(level: int, step_height_range: tuple[float, float]) -> float:
    return _lerp(level, step_height_range)


def sections() -> list[tuple[str, float]]:
    """(구간 이름, 구간 끝 x [m]) 목록. x는 코스 시작점 기준입니다."""
    lengths = [
        ("출발 평지", FLAT),
        ("오르막", RAMP),
        ("꼭대기 평지", TOP),
        ("내리막", RAMP),
        ("평지", FLAT),
        ("계단 오르기", NUM_STEPS * STEP_WIDTH),
        ("계단참", TOP),
        ("계단 내리기", NUM_STEPS * STEP_WIDTH),
        ("도착 평지", FLAT),
    ]
    out, x = [], 0.0
    for name, length in lengths:
        x += length
        out.append((name, x))
    return out


COURSE_LENGTH = sections()[-1][1]


def _box(x0: float, x1: float, top: float) -> trimesh.Trimesh:
    """x0~x1, 폭 전체, 바닥 z −1 m부터 top까지 채운 상자."""
    bottom = -1.0
    return trimesh.creation.box(
        extents=(x1 - x0, WIDTH, top - bottom),
        transform=trimesh.transformations.translation_matrix(((x0 + x1) / 2, WIDTH / 2, (top + bottom) / 2)),
    )


def _ramp(x0: float, x1: float, z0: float, z1: float) -> trimesh.Trimesh:
    """x0에서 높이 z0, x1에서 높이 z1인 경사면 아래를 채운 볼록 입체."""
    bottom = -1.0
    pts = [(x, y, z) for x, top in ((x0, z0), (x1, z1)) for y in (0.0, WIDTH) for z in (bottom, top)]
    return trimesh.Trimesh(vertices=np.array(pts)).convex_hull


def course_terrain(difficulty: float, cfg: "CourseTerrainCfg") -> tuple[list[trimesh.Trimesh], np.ndarray]:
    """difficulty는 쓰지 않습니다. 경사·계단 높이는 cfg에서 받습니다."""
    rise = cfg.slope * RAMP
    sh = cfg.step_height
    ends = [x for _, x in sections()]
    meshes = [
        _box(0.0, ends[0], 0.0),
        _ramp(ends[0], ends[1], 0.0, rise),
        _box(ends[1], ends[2], rise),
        _ramp(ends[2], ends[3], rise, 0.0),
        _box(ends[3], ends[4], 0.0),
    ]
    for i in range(NUM_STEPS):  # 오르기: i번째 발판 높이 (i+1)·sh
        x0 = ends[4] + i * STEP_WIDTH
        meshes.append(_box(x0, x0 + STEP_WIDTH, (i + 1) * sh))
    meshes.append(_box(ends[5], ends[6], NUM_STEPS * sh))
    for i in range(NUM_STEPS):  # 내리기
        x0 = ends[6] + i * STEP_WIDTH
        meshes.append(_box(x0, x0 + STEP_WIDTH, (NUM_STEPS - 1 - i) * sh))
    meshes.append(_box(ends[7], ends[8], 0.0))
    return meshes, np.array([START_X, WIDTH / 2, 0.0])


@configclass
class CourseTerrainCfg(SubTerrainBaseCfg):
    function = course_terrain
    size: tuple[float, float] = (COURSE_LENGTH, WIDTH)
    slope: float = 0.2
    """경사(높이/수평 거리)."""
    step_height: float = 0.14
    """계단 한 칸 높이 [m]."""


def describe(slope: float, step_height: float, slope_level: int, stairs_level: int) -> str:
    s, h = slope, step_height
    return (
        f"경사 level {slope_level}: {s:.3f} ({math.degrees(math.atan(s)):.1f}°, 높이 {s * RAMP:.2f} m), "
        f"계단 level {stairs_level}: {h * 100:.1f} cm × {NUM_STEPS}칸 (발판 {STEP_WIDTH * 100:.0f} cm)"
    )
