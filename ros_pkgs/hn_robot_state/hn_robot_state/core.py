# SPDX-License-Identifier: Apache-2.0
"""로봇 상태 판정 코어(G-006). 정책 입력 상태 dict에서 정지·보행·낙상을 판정합니다.

numpy와 pyyaml만 씁니다. ROS·시뮬레이터를 import하지 않으므로 MuJoCo, Isaac Sim, Isaac Lab, 실기에서 같은 코드가 돕니다.
ROS 발행과 파일 기록은 어댑터(ros_node.py, jsonl_log.py)가 맡습니다.

입력 `state`는 정책 러너(policies/route_walk/runner.py)가 받는 dict와 같은 키입니다(단위 m, rad/s, m/s, 정책 base 프레임).
  필수  projected_gravity_b(3, 단위벡터, 정지 시 [0,0,-1]), base_lin_vel_b(3, m/s), command(3, [vx m/s, vy m/s, wz rad/s])
  선택  height_hits_z(nx*ny, 격자 world z, 지면이 없으면 매우 큰 값 또는 inf/nan), base_pos_z(1, m)
  나머지 키(joint_pos 등)는 읽지 않습니다. 선택 입력이 없으면 기울기만으로 판정합니다.
좌표 규약은 base 프레임 +X 전방, +Y 좌, +Z 상입니다. ZYX 오일러(roll=x축, pitch=y축)이며 양의 pitch는 앞이 내려갑니다.

시간: `update(state, t)`의 t는 호출자의 시간(시뮬레이션 시간 또는 로봇 시간, 초)이고 판정 로직(debounce, 지속 시간)에만 씁니다.
입력 끊김(STALE_INPUT)은 wall 시간으로 따로 감시합니다(StaleWatchdog). t가 거꾸로 가면 초기화하고,
max_dt_s보다 크게 건너뛰면 진행 중인 지속 시간 계산을 다시 시작합니다(상태는 유지).

상태 번호는 S-005(/localization/status)처럼 숫자 enum입니다. 3(TILTING)과 4(SLIPPING)는 번호만 예약했고 아직 내보내지 않습니다.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, fields
from enum import IntEnum
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "thresholds.yaml"
_EPS = 1.0e-9   # 부동소수점 시간 비교 여유(초)


class State(IntEnum):
    INITIALIZING = 0
    STANDING = 1
    WALKING = 2
    # 3 TILTING, 4 SLIPPING: 번호 예약(미구현)
    FALLEN = 5
    STALE_INPUT = 6


class Severity(IntEnum):
    """diagnostic_msgs/DiagnosticStatus의 level과 같은 값입니다."""

    OK = 0
    WARN = 1
    ERROR = 2
    STALE = 3


SEVERITY_OF = {
    State.INITIALIZING: Severity.OK,
    State.STANDING: Severity.OK,
    State.WALKING: Severity.OK,
    State.FALLEN: Severity.ERROR,
    State.STALE_INPUT: Severity.STALE,
}


@dataclass(frozen=True)
class Thresholds:
    """판정 임계값. 기본값은 config/thresholds.yaml과 같아야 합니다(시험이 검사). 단위는 필드 이름 끝에 적었습니다."""

    # 초기화: 직립이고 수직 속도가 작은 상태가 init_stable_s 지속되면 끝나고, 그 동안의 높이 중앙값을 h0(서 있는 높이)로 씁니다.
    init_stable_s: float = 1.0
    init_tilt_max_deg: float = 15.0
    init_vertical_speed_max_mps: float = 0.2
    # 낙상: 기울기 초과, 높이 붕괴(h0 대비), 지면 없음 중 하나가 fall_enter_s 지속되면 FALLEN(래치).
    # 기울기 < recover_tilt_deg이고 높이 > recover_height_ratio*h0, 지면 있음이 recover_s 지속되면 해제.
    fall_tilt_deg: float = 70.0
    fall_low_height_ratio: float = 0.5
    fall_enter_s: float = 0.2
    recover_tilt_deg: float = 25.0
    recover_height_ratio: float = 0.8
    recover_s: float = 1.0
    # 정지/보행: stand_* 아래가 stand_dwell_s 지속되면 STANDING, walk_* 이상이 walk_dwell_s 지속되면 WALKING. 사이 구간은 상태 유지(히스테리시스).
    stand_cmd_lin_mps: float = 0.05
    stand_cmd_ang_rps: float = 0.05
    stand_speed_mps: float = 0.10
    walk_cmd_lin_mps: float = 0.10
    walk_cmd_ang_rps: float = 0.10
    walk_speed_mps: float = 0.15
    stand_dwell_s: float = 0.5
    walk_dwell_s: float = 0.1
    # height scan 격자(policies/urdf_v0/policy_io.yaml의 height_scan.grid.shape와 같아야 함. index = iy*nx + ix, 중심 = (nx//2, ny//2))
    scan_nx: int = 17
    scan_ny: int = 11
    scan_center_half_width: int = 1
    scan_off_ground_hit_z_m: float = 100.0
    scan_min_valid_fraction: float = 0.5
    nominal_height_m: float | None = None   # 값을 주면 자체 측정 대신 이 높이를 h0로 씁니다(실기용)
    # 입력 끊김 / 시간
    stale_timeout_s: float = 0.5
    max_dt_s: float = 0.5

    def __post_init__(self):
        pos = ("init_stable_s", "init_tilt_max_deg", "init_vertical_speed_max_mps", "fall_tilt_deg", "fall_low_height_ratio",
               "fall_enter_s", "recover_tilt_deg", "recover_height_ratio", "recover_s", "stand_cmd_lin_mps", "stand_cmd_ang_rps",
               "stand_speed_mps", "walk_cmd_lin_mps", "walk_cmd_ang_rps", "walk_speed_mps", "scan_off_ground_hit_z_m",
               "stale_timeout_s", "max_dt_s")
        for name in pos:
            if not getattr(self, name) > 0:
                raise ValueError(f"{name}는 0보다 커야 합니다: {getattr(self, name)}")
        for name in ("stand_dwell_s", "walk_dwell_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name}는 0 이상이어야 합니다: {getattr(self, name)}")
        if not self.recover_tilt_deg < self.fall_tilt_deg <= 180.0:
            raise ValueError("recover_tilt_deg < fall_tilt_deg <= 180 이어야 합니다")
        if not self.init_tilt_max_deg < self.fall_tilt_deg:
            raise ValueError("init_tilt_max_deg는 fall_tilt_deg보다 작아야 합니다")
        if not self.fall_low_height_ratio < self.recover_height_ratio <= 1.0:
            raise ValueError("fall_low_height_ratio < recover_height_ratio <= 1 이어야 합니다")
        if self.walk_cmd_lin_mps < self.stand_cmd_lin_mps or self.walk_cmd_ang_rps < self.stand_cmd_ang_rps \
                or self.walk_speed_mps < self.stand_speed_mps:
            raise ValueError("walk_* 값은 같은 종류의 stand_* 값 이상이어야 합니다(히스테리시스 구간)")
        if self.scan_nx < 1 or self.scan_ny < 1 or self.scan_center_half_width < 0:
            raise ValueError("scan_nx, scan_ny는 1 이상, scan_center_half_width는 0 이상이어야 합니다")
        if self.scan_center_half_width > min(self.scan_nx // 2, self.scan_ny // 2):
            raise ValueError("scan_center_half_width가 격자 중심 블록보다 큽니다")
        if not 0.0 < self.scan_min_valid_fraction <= 1.0:
            raise ValueError("scan_min_valid_fraction은 (0, 1] 이어야 합니다")
        if self.nominal_height_m is not None and not self.nominal_height_m > 0:
            raise ValueError("nominal_height_m은 null이거나 0보다 커야 합니다")


# yaml 섹션 -> {yaml 키: Thresholds 필드}. yaml은 모든 키를 명시해야 합니다(빠진 값이 조용히 기본값이 되는 것을 막음).
_YAML_FIELDS = {
    "init": {"stable_s": "init_stable_s", "tilt_max_deg": "init_tilt_max_deg", "vertical_speed_max_mps": "init_vertical_speed_max_mps"},
    "fall": {"tilt_deg": "fall_tilt_deg", "low_height_ratio": "fall_low_height_ratio", "enter_s": "fall_enter_s",
             "recover_tilt_deg": "recover_tilt_deg", "recover_height_ratio": "recover_height_ratio", "recover_s": "recover_s"},
    "motion": {"stand_cmd_lin_mps": "stand_cmd_lin_mps", "stand_cmd_ang_rps": "stand_cmd_ang_rps", "stand_speed_mps": "stand_speed_mps",
               "walk_cmd_lin_mps": "walk_cmd_lin_mps", "walk_cmd_ang_rps": "walk_cmd_ang_rps", "walk_speed_mps": "walk_speed_mps",
               "stand_dwell_s": "stand_dwell_s", "walk_dwell_s": "walk_dwell_s"},
    "height_scan": {"nx": "scan_nx", "ny": "scan_ny", "center_half_width": "scan_center_half_width",
                    "off_ground_hit_z_m": "scan_off_ground_hit_z_m", "min_valid_fraction": "scan_min_valid_fraction",
                    "nominal_height_m": "nominal_height_m"},
    "stale": {"timeout_s": "stale_timeout_s"},
    "time": {"max_dt_s": "max_dt_s"},
}
_INT_FIELDS = {"scan_nx", "scan_ny", "scan_center_half_width"}


def load_thresholds(path: str | Path = DEFAULT_CONFIG_PATH) -> Thresholds:
    """thresholds.yaml을 읽습니다. 모르는 키, 빠진 키, 잘못된 형식은 ValueError입니다."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError(f"{path}: schema_version 1이 필요합니다")
    sections = {k: v for k, v in raw.items() if k != "schema_version"}
    unknown = set(sections) - set(_YAML_FIELDS)
    if unknown:
        raise ValueError(f"{path}: 모르는 섹션 {sorted(unknown)}")
    values = {}
    for section, mapping in _YAML_FIELDS.items():
        body = sections.get(section)
        if not isinstance(body, dict):
            raise ValueError(f"{path}: 섹션 '{section}'이 없거나 매핑이 아닙니다")
        if set(body) != set(mapping):
            raise ValueError(f"{path}: 섹션 '{section}'의 키가 다릅니다. 빠짐 {sorted(set(mapping) - set(body))}, 모름 {sorted(set(body) - set(mapping))}")
        for key, field_name in mapping.items():
            v = body[key]
            if field_name == "nominal_height_m" and v is None:
                values[field_name] = None
            elif isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{path}: {section}.{key}는 숫자여야 합니다: {v!r}")
            elif field_name in _INT_FIELDS:
                if int(v) != v:
                    raise ValueError(f"{path}: {section}.{key}는 정수여야 합니다: {v!r}")
                values[field_name] = int(v)
            else:
                values[field_name] = float(v)
    assert set(values) == {f.name for f in fields(Thresholds)}
    return Thresholds(**values)


@dataclass(frozen=True)
class StatusReport:
    t: float                  # 입력의 t(호출자 시간)
    state: State
    reason: str               # initializing: calibrating / standing: idle / walking: moving / fallen: tilt|low_height|off_ground / stale: no_input
    since_s: float            # 이 상태가 시작된 뒤 지난 시간(t 기준). STALE_INPUT은 입력이 끊긴 시간(wall)
    features: dict            # 판정에 쓴 값(단위는 키 끝: _deg, _mps, _rps, _m). 값이 없으면 None

    @property
    def code(self) -> int:
        return int(self.state)

    @property
    def name(self) -> str:
        return self.state.name

    @property
    def severity(self) -> Severity:
        return SEVERITY_OF[self.state]

    def to_dict(self) -> dict:
        """JSON으로 바로 쓸 수 있는 dict(numpy 타입 없음)."""
        return {"t": self.t, "code": self.code, "state": self.name, "severity": int(self.severity), "reason": self.reason,
                "since_s": self.since_s, "features": dict(self.features)}


def _vec(state: Mapping, key: str, n: int) -> np.ndarray:
    if key not in state:
        raise ValueError(f"상태 dict에 '{key}'가 없습니다")
    v = np.asarray(state[key], dtype=float).reshape(-1)
    if v.size != n:
        raise ValueError(f"'{key}'는 값 {n}개여야 합니다(받은 {v.size}개)")
    if not np.all(np.isfinite(v)):
        raise ValueError(f"'{key}'에 유한하지 않은 값이 있습니다")
    return v


class StateEstimator:
    """상태 하나(로봇 하나)의 판정기. update()를 정책 주기로 부릅니다."""

    def __init__(self, thresholds: Thresholds | None = None, scan_shape: tuple[int, int] | None = None):
        self.cfg = thresholds or Thresholds()
        self._nx, self._ny = scan_shape if scan_shape is not None else (self.cfg.scan_nx, self.cfg.scan_ny)
        if self.cfg.scan_center_half_width > min(self._nx // 2, self._ny // 2):
            raise ValueError("scan_center_half_width가 격자 중심 블록보다 큽니다")
        self.reset()

    # ------------------------------------------------------------------ 상태
    def reset(self) -> None:
        self._state = State.INITIALIZING
        self._reason = "calibrating"
        self._since: float | None = None
        self._h0: float | None = self.cfg.nominal_height_m
        self._last_t: float | None = None
        self._last_features: dict = {}
        self._clear_candidates()

    def _clear_candidates(self) -> None:
        """진행 중인 지속 시간 계산을 모두 버립니다(상태는 유지)."""
        self._fall_since = None
        self._recover_since = None
        self._stand_since = None
        self._walk_since = None
        self._init_since = None
        self._init_heights: list[float] = []

    def _set_state(self, state: State, reason: str, t: float) -> None:
        self._state, self._reason, self._since = state, reason, t

    # ------------------------------------------------------------------ 입력 -> 특징
    def _features(self, state: Mapping) -> dict:
        g = _vec(state, "projected_gravity_b", 3)
        norm = float(np.linalg.norm(g))
        if norm < 0.5:
            raise ValueError("'projected_gravity_b'의 크기가 너무 작습니다(단위벡터여야 함)")
        g = g / norm
        v = _vec(state, "base_lin_vel_b", 3)
        cmd = _vec(state, "command", 3)
        feats = {
            "tilt_deg": math.degrees(math.acos(max(-1.0, min(1.0, -g[2])))),
            "roll_deg": math.degrees(math.atan2(-g[1], -g[2])),
            "pitch_deg": math.degrees(math.asin(max(-1.0, min(1.0, g[0])))),
            "speed_mps": float(math.hypot(v[0], v[1])),
            "vz_b_mps": float(v[2]),
            "cmd_lin_mps": float(math.hypot(cmd[0], cmd[1])),
            "cmd_ang_rps": float(abs(cmd[2])),
            "cmd_vx_mps": float(cmd[0]),
            "cmd_wz_rps": float(cmd[2]),
            "height_m": None,
            "ground_ok": None,   # None: 높이 입력 없음, False: 중심 격자에 지면이 없음
        }
        hits, base_z = state.get("height_hits_z"), state.get("base_pos_z")
        if hits is not None and base_z is not None:
            hits = np.asarray(hits, dtype=float).reshape(-1)
            if hits.size != self._nx * self._ny:
                raise ValueError(f"'height_hits_z'는 값 {self._nx * self._ny}개여야 합니다(받은 {hits.size}개)")
            bz = np.asarray(base_z, dtype=float).reshape(-1)
            if bz.size < 1 or not np.isfinite(bz[0]):
                raise ValueError("'base_pos_z'가 올바르지 않습니다")
            w = self.cfg.scan_center_half_width
            cx, cy = self._nx // 2, self._ny // 2
            block = hits.reshape(self._ny, self._nx)[cy - w:cy + w + 1, cx - w:cx + w + 1].ravel()
            valid = np.isfinite(block) & (block < self.cfg.scan_off_ground_hit_z_m)
            if valid.mean() >= self.cfg.scan_min_valid_fraction:
                feats["height_m"] = float(bz[0] - np.median(block[valid]))
                feats["ground_ok"] = True
            else:
                feats["ground_ok"] = False
        return feats

    # ------------------------------------------------------------------ 갱신
    def update(self, state: Mapping, t: float) -> StatusReport:
        t = float(t)
        if not math.isfinite(t):
            raise ValueError("t가 유한하지 않습니다")
        if self._last_t is not None:
            if t < self._last_t - _EPS:
                self.reset()                       # 시간이 거꾸로 감: 새 에피소드로 봄
            elif t - self._last_t > self.cfg.max_dt_s:
                self._clear_candidates()           # 큰 공백: 지속 시간 계산만 다시 시작
        feats = self._features(state)              # 잘못된 입력이면 여기서 예외(상태는 바뀌지 않음)
        if self._since is None:
            self._since = t
        self._last_t, self._last_features = t, feats
        self._step(feats, t)
        return self._report(t)

    def _report(self, t: float) -> StatusReport:
        return StatusReport(t=t, state=self._state, reason=self._reason, since_s=t - self._since,
                            features={**self._last_features, "h0_m": self._h0})

    def stale_report(self, t: float, silent_s: float) -> StatusReport:
        """입력이 끊겼을 때의 보고. 판정 상태는 바꾸지 않고 마지막 특징을 그대로 싣습니다. silent_s는 끊긴 시간(wall, 초)."""
        return StatusReport(t=float(t), state=State.STALE_INPUT, reason="no_input", since_s=float(silent_s),
                            features={**self._last_features, "h0_m": self._h0})

    # ------------------------------------------------------------------ 판정
    def _fall_condition(self, f: dict) -> str | None:
        if f["tilt_deg"] > self.cfg.fall_tilt_deg:
            return "tilt"
        if f["ground_ok"] is False:
            return "off_ground"
        h = f["height_m"]
        if h is not None and self._h0 is not None and h < self.cfg.fall_low_height_ratio * self._h0:
            return "low_height"
        return None

    def _motion_flags(self, f: dict) -> tuple[bool, bool]:
        c = self.cfg
        stand_on = f["cmd_lin_mps"] < c.stand_cmd_lin_mps and f["cmd_ang_rps"] < c.stand_cmd_ang_rps and f["speed_mps"] < c.stand_speed_mps
        walk_on = f["cmd_lin_mps"] >= c.walk_cmd_lin_mps or f["cmd_ang_rps"] >= c.walk_cmd_ang_rps or f["speed_mps"] >= c.walk_speed_mps
        return stand_on, walk_on

    def _enter_motion(self, f: dict, t: float) -> None:
        _, walk_on = self._motion_flags(f)
        if walk_on:
            self._set_state(State.WALKING, "moving", t)
        else:
            self._set_state(State.STANDING, "idle", t)
        self._stand_since = self._walk_since = None
        self._init_since, self._init_heights = None, []

    def _step(self, f: dict, t: float) -> None:
        cfg = self.cfg
        if self._state != State.FALLEN:
            reason = self._fall_condition(f)
            if reason is None:
                self._fall_since = None
            else:
                if self._fall_since is None:
                    self._fall_since = t
                if t - self._fall_since >= cfg.fall_enter_s - _EPS:
                    self._set_state(State.FALLEN, reason, t)
                    self._fall_since = self._recover_since = self._stand_since = self._walk_since = self._init_since = None
                    self._init_heights = []
                    return
        if self._state == State.FALLEN:
            self._step_fallen(f, t)
        elif self._state == State.INITIALIZING:
            self._step_init(f, t)
        else:
            self._step_motion(f, t)

    def _step_fallen(self, f: dict, t: float) -> None:
        cfg = self.cfg
        h = f["height_m"]
        recovered = (f["tilt_deg"] < cfg.recover_tilt_deg and f["ground_ok"] is not False
                     and (h is None or self._h0 is None or h > cfg.recover_height_ratio * self._h0))
        if not recovered:
            self._recover_since = None
            return
        if self._recover_since is None:
            self._recover_since = t
        if t - self._recover_since >= cfg.recover_s - _EPS:
            self._recover_since = None
            if self._h0 is None and h is not None:
                self._set_state(State.INITIALIZING, "calibrating", t)   # 낙상 중에 시작해 h0를 못 쟀음: 다시 측정
            else:
                self._enter_motion(f, t)

    def _step_init(self, f: dict, t: float) -> None:
        cfg = self.cfg
        stable = (f["tilt_deg"] < cfg.init_tilt_max_deg and abs(f["vz_b_mps"]) < cfg.init_vertical_speed_max_mps
                  and f["ground_ok"] is not False)
        if not stable:
            self._init_since, self._init_heights = None, []
            return
        if self._init_since is None:
            self._init_since, self._init_heights = t, []
        if f["height_m"] is not None:
            self._init_heights.append(f["height_m"])
        if t - self._init_since >= cfg.init_stable_s - _EPS:
            if self._h0 is None and self._init_heights:
                self._h0 = float(np.median(self._init_heights))
            self._enter_motion(f, t)

    def _step_motion(self, f: dict, t: float) -> None:
        cfg = self.cfg
        stand_on, walk_on = self._motion_flags(f)
        if self._state == State.STANDING:
            self._stand_since = None
            if not walk_on:
                self._walk_since = None
                return
            if self._walk_since is None:
                self._walk_since = t
            if t - self._walk_since >= cfg.walk_dwell_s - _EPS:
                self._set_state(State.WALKING, "moving", t)
                self._walk_since = None
        else:   # WALKING
            self._walk_since = None
            if not stand_on:
                self._stand_since = None
                return
            if self._stand_since is None:
                self._stand_since = t
            if t - self._stand_since >= cfg.stand_dwell_s - _EPS:
                self._set_state(State.STANDING, "idle", t)
                self._stand_since = None


class StaleWatchdog:
    """입력 끊김 감시(wall 시간). feed()는 입력이 올 때마다, is_stale()은 발행 주기마다 부릅니다. 첫 입력 전에는 끊김으로 보지 않습니다."""

    def __init__(self, timeout_s: float, clock: Callable[[], float] = time.monotonic):
        if not timeout_s > 0:
            raise ValueError("timeout_s는 0보다 커야 합니다")
        self.timeout_s = float(timeout_s)
        self._clock = clock
        self._last: float | None = None

    def feed(self) -> None:
        self._last = self._clock()

    def reset(self) -> None:
        self._last = None

    def silent_s(self) -> float | None:
        return None if self._last is None else self._clock() - self._last

    def is_stale(self) -> bool:
        s = self.silent_s()
        return s is not None and s > self.timeout_s
