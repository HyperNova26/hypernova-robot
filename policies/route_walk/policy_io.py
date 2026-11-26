# SPDX-License-Identifier: Apache-2.0
"""정책 입출력 계약(policy_io.yaml) 로더.

Isaac Lab 학습·평가 설정(isaaclab_policy_io.py)과 배포 러너(runner.py)가 같은 이 모듈로 같은 yaml을 읽습니다.
의존성은 numpy와 pyyaml뿐입니다(robot venv에서 그대로 돌아야 하므로 torch·Isaac Lab을 import하지 않습니다).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import yaml

SUPPORTED_SCHEMA = 1
HEIGHT_VALUE = "base_z_minus_hit_z_minus_offset"


class PolicyIOError(ValueError):
    """yaml이 계약을 어기거나, 입력 상태가 계약과 다를 때."""


@dataclass(frozen=True)
class ObsTerm:
    name: str
    dim: int
    source: str
    rel_to: str | None = None  # "default_pos" | "zero" | None


@dataclass(frozen=True)
class PdGroup:
    match: str
    effort_limit_nm: float
    velocity_limit_rad_s: float


class PolicyIO:
    """yaml 한 장에서 파생되는 모든 값. 읽기 전용으로 씁니다."""

    def __init__(self, raw: Mapping, path: Path | None = None):
        self.raw = raw
        self.path = path
        if raw.get("schema_version") != SUPPORTED_SCHEMA:
            raise PolicyIOError(f"schema_version {raw.get('schema_version')!r} 미지원(지원: {SUPPORTED_SCHEMA})")

        # --- 조인트 ---
        self.joints: tuple[str, ...] = tuple(raw["joints"]["order"])
        n = len(self.joints)
        if len(set(self.joints)) != n:
            raise PolicyIOError("joints.order에 중복이 있습니다")
        defaults = raw["joints"]["default_pos_rad"]
        if set(defaults) != set(self.joints):
            raise PolicyIOError(f"default_pos_rad 키가 joints.order와 다릅니다: {sorted(set(defaults) ^ set(self.joints))}")
        self.default_pos_by_name = {j: float(defaults[j]) for j in self.joints}
        self.default_pos = np.array([self.default_pos_by_name[j] for j in self.joints], np.float32)

        # --- 주기 ---
        rate = raw["rate"]
        self.sim_dt = float(rate["sim_dt_s"])
        self.decimation = int(rate["decimation"])
        self.policy_dt = float(rate["policy_dt_s"])
        if abs(self.sim_dt * self.decimation - self.policy_dt) > 1e-9:
            raise PolicyIOError(f"policy_dt_s {self.policy_dt} != sim_dt_s*decimation {self.sim_dt * self.decimation}")

        # --- 표준 강체명 ---
        links = raw["robot"]["links"]
        self.root_link = str(links["root"])
        self.foot_links = tuple(links["feet"])
        legs = ("FL", "FR", "RL", "RR")
        want_joints = {f"{leg}_{p}_joint" for leg in legs for p in ("hip", "thigh", "calf")}
        if set(self.joints) != want_joints:
            raise PolicyIOError(f"조인트 이름이 팀 표준 {{FL,FR,RL,RR}}_{{hip,thigh,calf}}_joint와 다릅니다: 차이 {sorted(set(self.joints) ^ want_joints)}")
        if self.root_link != "trunk" or set(self.foot_links) != {f"{leg}_foot" for leg in legs}:
            raise PolicyIOError(f"robot.links가 팀 표준(root trunk, feet {{FL,FR,RL,RR}}_foot)과 다릅니다: {self.root_link}, {self.foot_links}")

        # --- 시뮬레이션 ---
        self.physics_backend = str(raw["simulation"]["physics_backend"])
        if self.physics_backend not in ("physx", "newton"):
            raise PolicyIOError(f"simulation.physics_backend {self.physics_backend!r}는 physx 또는 newton이어야 합니다")

        # --- 행동 ---
        act = raw["action"]
        if act["type"] != "joint_position_target" or int(act["dim"]) != n:
            raise PolicyIOError("action은 joint_position_target이고 dim이 조인트 수와 같아야 합니다")
        self.action_scale = float(act["scale"])
        self.action_clip = None if act.get("clip") is None else tuple(float(v) for v in act["clip"])

        # --- PD ---
        pd = raw["pd"]
        self.kp = float(pd["kp"])
        self.kd = float(pd["kd"])
        self.friction = float(pd.get("friction", 0.0))
        self.pd_groups = tuple(PdGroup(g["match"], float(g["effort_limit_nm"]), float(g["velocity_limit_rad_s"])) for g in pd["groups"])
        self.effort_limit = np.array([self._group_of(j).effort_limit_nm for j in self.joints], np.float32)
        self.velocity_limit = np.array([self._group_of(j).velocity_limit_rad_s for j in self.joints], np.float32)

        # --- 관측 ---
        obs = raw["observations"]
        self.obs_terms = tuple(ObsTerm(t["name"], int(t["dim"]), t["source"], t.get("rel_to")) for t in obs["terms"])
        if len({t.name for t in self.obs_terms}) != len(self.obs_terms):
            raise PolicyIOError("observations.terms 이름이 겹칩니다")
        self.obs_dim = sum(t.dim for t in self.obs_terms)
        if self.obs_dim != int(obs["dim"]):
            raise PolicyIOError(f"observations.dim {obs['dim']} != 항목 합 {self.obs_dim}")

        # --- height scan ---
        hs = raw["height_scan"]
        if hs["value"] != HEIGHT_VALUE or hs["grid"]["ordering"] != "x_fastest":
            raise PolicyIOError("height_scan.value/ordering이 이 로더가 아는 정의와 다릅니다")
        self.hs_offset = float(hs["offset_m"])
        self.hs_clip = tuple(float(v) for v in hs["clip"])
        sx, sy = (float(v) for v in hs["grid"]["size_m"])
        res = float(hs["grid"]["resolution_m"])
        nx, ny = (int(v) for v in hs["grid"]["shape"])
        if nx != round(sx / res) + 1 or ny != round(sy / res) + 1:
            raise PolicyIOError(f"height_scan.grid.shape {[nx, ny]}가 size/resolution과 맞지 않습니다")
        self.hs_size, self.hs_res, self.hs_shape = (sx, sy), res, (nx, ny)
        self.hs_start_height = float(hs["start_height_above_base_m"])
        hs_terms = [t for t in self.obs_terms if t.name == "height_scan"]
        if hs_terms and hs_terms[0].dim != nx * ny:
            raise PolicyIOError(f"height_scan 항목 dim {hs_terms[0].dim} != 격자 {nx}x{ny}")

        # --- 신경망 ---
        net = raw["policy"]["network"]
        if int(net["input_dim"]) != self.obs_dim or int(net["output_dim"]) != n:
            raise PolicyIOError("network input/output 차원이 관측·행동 정의와 다릅니다")
        self.hidden_dims = tuple(int(v) for v in net["hidden_dims"])

    # ---------------------------------------------------------------- 조회
    def _group_of(self, joint: str) -> PdGroup:
        hits = [g for g in self.pd_groups if re.fullmatch(g.match, joint)]
        if len(hits) != 1:
            raise PolicyIOError(f"조인트 {joint}에 맞는 pd.groups가 {len(hits)}개입니다(정확히 1개여야 함)")
        return hits[0]

    def height_scan_offsets(self) -> np.ndarray:
        """base 프레임(yaw 정렬)에서 ray 시작점의 (x, y) 오프셋. (nx*ny, 2), x가 가장 빠르게 변하는 순서."""
        nx, ny = self.hs_shape
        xs = np.linspace(-self.hs_size[0] / 2, self.hs_size[0] / 2, nx)
        ys = np.linspace(-self.hs_size[1] / 2, self.hs_size[1] / 2, ny)
        gx, gy = np.meshgrid(xs, ys)  # indexing="xy": shape (ny, nx), flatten하면 x가 가장 빠름
        return np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float32)

    def height_scan_world_xy(self, base_xy, yaw: float) -> np.ndarray:
        """지면 높이를 조회할 세계 좌표 (x, y) 187개. 배포 쪽 지도에서 이 점들의 z를 읽어 height_hits_z로 넘깁니다."""
        c, s = np.cos(yaw), np.sin(yaw)
        off = self.height_scan_offsets()
        rot = np.array([[c, -s], [s, c]], np.float32)
        return off @ rot.T + np.asarray(base_xy, np.float32)

    def pd_regex_dict(self, field: str) -> dict[str, float]:
        """Isaac Lab 액추에이터 설정에 넘기는 {정규식: 값} 형태."""
        return {g.match: getattr(g, field) for g in self.pd_groups}

    def to_policy_order(self, by_name: Mapping[str, float], what: str = "값") -> np.ndarray:
        """모터 드라이버 등 다른 순서의 {조인트 이름: 값}을 정책 순서 배열로 바꿉니다. 이름이 모자라거나 남으면 오류입니다."""
        if set(by_name) != set(self.joints):
            raise PolicyIOError(f"{what}의 조인트 이름이 계약과 다릅니다: 차이 {sorted(set(by_name) ^ set(self.joints))}")
        return np.array([by_name[j] for j in self.joints], np.float32)

    # ---------------------------------------------------------------- 변환
    def decode_action(self, action) -> np.ndarray:
        """정규화된 행동 -> 조인트 목표 위치 [rad], 정책 조인트 순서."""
        a = np.asarray(action, np.float32)
        if a.shape != (len(self.joints),):
            raise PolicyIOError(f"action shape {a.shape} != ({len(self.joints)},)")
        if self.action_clip is not None:
            a = np.clip(a, *self.action_clip)
        return self.default_pos + self.action_scale * a

    def build_obs(self, state: Mapping[str, np.ndarray]) -> np.ndarray:
        """원시 상태 dict -> actor 입력 벡터. 항목 순서·상대값·clip은 모두 yaml대로입니다.

        필요한 키는 observations.terms의 source와, height scan이 있으면 base_pos_z입니다.
        잡음은 더하지 않습니다(학습 때 잡음은 training.obs_noise_uniform).
        """
        parts = []
        for t in self.obs_terms:
            if t.source not in state:
                raise PolicyIOError(f"상태에 '{t.source}'가 없습니다(항목 {t.name})")
            v = np.asarray(state[t.source], np.float32).reshape(-1)
            if v.shape[0] != t.dim:
                raise PolicyIOError(f"'{t.source}' 길이 {v.shape[0]} != {t.dim}(항목 {t.name})")
            if t.rel_to == "default_pos":
                v = v - self.default_pos
            if t.name == "height_scan":
                if "base_pos_z" not in state:
                    raise PolicyIOError("height_scan에는 상태의 base_pos_z가 필요합니다")
                v = np.clip(float(np.asarray(state["base_pos_z"]).reshape(-1)[0]) - v - self.hs_offset, *self.hs_clip)
            parts.append(v.astype(np.float32))
        out = np.concatenate(parts)
        assert out.shape == (self.obs_dim,)
        return out


def load_policy_io(path: str | Path) -> PolicyIO:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        return PolicyIO(yaml.safe_load(f), path)
