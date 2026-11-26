# SPDX-License-Identifier: Apache-2.0
"""경유점을 따라가는 단순 이동 제어기와 경로 yaml 로더. numpy·pyyaml만 씁니다(시뮬레이터에 의존하지 않음).

정책에 줄 속도 명령 [vx, vy, wz](base 프레임)를 만듭니다. 이전 경유점에서 현재 경유점까지의 선분을 추종하고(선분 위 투영점에서
LOOKAHEAD 앞을 겨냥), 많이 틀어져 있으면 제자리에서 먼저 돌고, 마지막 목적지 앞에서 감속합니다. 장애물·구멍은 알지 못합니다.
Isaac Lab, MuJoCo, Isaac Sim 재생 스크립트가 같은 제어기를 씁니다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass(frozen=True)
class Route:
    name: str
    start: tuple[float, float]
    waypoints: tuple[tuple[float, float], ...]
    description: str = ""


def load_route(path: str | Path, name: str) -> Route:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if name not in raw["routes"]:
        raise KeyError(f"경로 '{name}'가 {path}에 없습니다. 있는 경로: {sorted(raw['routes'])}")
    r = raw["routes"][name]
    return Route(name, tuple(map(float, r["start"])), tuple(tuple(map(float, w)) for w in r["waypoints"]), r.get("description", ""))


def parse_xy_list(text: str) -> list[tuple[float, float]]:
    """'x,y;x,y;...' 문자열을 점 목록으로."""
    return [tuple(float(v) for v in item.split(",")[:2]) for item in text.split(";") if item.strip()]


class RouteFollower:
    """환경 하나(로봇 하나)의 경로 추종 상태."""

    def __init__(self, start_xy, waypoints, vmax: float = 0.5, lookahead: float = 1.5, tol_mid: float = 0.5, tol_goal: float = 0.3):
        self.start = np.asarray(start_xy, float)
        self.wps = [np.asarray(w, float) for w in waypoints]
        self.vmax, self.lookahead, self.tol_mid, self.tol_goal = min(vmax, 1.0), lookahead, tol_mid, tol_goal
        self.idx = 0
        self.arrived = False

    def reset(self) -> None:
        self.idx, self.arrived = 0, False

    @property
    def num_waypoints(self) -> int:
        return len(self.wps)

    def command(self, pos_xy, yaw: float):
        """반환: (vx, vy, wz, 이벤트 목록). 이벤트는 ('waypoint', 통과한 번호) 또는 ('arrived', 목적지까지 거리)."""
        events = []
        if self.arrived:
            return 0.0, 0.0, 0.0, events
        pos = np.asarray(pos_xy, float)
        last = self.idx == len(self.wps) - 1
        goal = self.wps[self.idx]
        seg_a = self.wps[self.idx - 1] if self.idx > 0 else self.start
        seg = goal - seg_a
        dist = float(np.hypot(*(goal - pos)))
        passed = float(np.dot(pos - seg_a, seg)) >= float(np.dot(seg, seg)) and dist < 1.5   # 선분 끝을 지나쳤으면 도달로 침
        if dist < (self.tol_goal if last else self.tol_mid) or (passed and not last):
            if last:
                self.arrived = True
                events.append(("arrived", dist))
                return 0.0, 0.0, 0.0, events
            self.idx += 1
            events.append(("waypoint", self.idx))
            last = self.idx == len(self.wps) - 1
            goal = self.wps[self.idx]
            seg_a = self.wps[self.idx - 1]
            seg = goal - seg_a
            dist = float(np.hypot(*(goal - pos)))
        seg_len = float(np.hypot(*seg))
        t_proj = float(np.dot(pos - seg_a, seg)) / max(seg_len, 1e-6)
        aim = seg_a + seg / max(seg_len, 1e-6) * min(max(t_proj, 0.0) + self.lookahead, seg_len)
        da = aim - pos
        err = wrap(math.atan2(da[1], da[0]) - yaw)
        vx = 0.0 if abs(err) > 0.8 else self.vmax * max(0.0, math.cos(err))
        if last:
            vx = min(vx, max(0.15, 0.6 * dist))
        return vx, 0.0, float(np.clip(1.2 * err, -0.8, 0.8)), events
