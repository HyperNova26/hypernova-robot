# SPDX-License-Identifier: Apache-2.0
"""배포용 정책 러너. policy_io.yaml과 내보낸 actor 가중치(.npz)만으로 관측 -> 조인트 목표 위치를 계산합니다.

torch·Isaac Lab·ROS 없이 numpy만 씁니다(robot venv에서 그대로 실행). ROS 노드나 실기 어댑터는 이 클래스를
감싸서 `ros_pkgs/`에 두고, 센서 값을 `act()`의 state dict로 넘기면 됩니다.

사용:
    io = load_policy_io("policies/urdf_v0/policy_io.yaml")
    runner = PolicyRunner(io, "actor.npz")          # 가중치는 export_actor.py로 만듭니다
    runner.reset()
    q_target = runner.act(state)                    # 50 Hz(io.policy_dt)로 호출, 정책 조인트 순서의 목표 위치 [rad]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import numpy as np

from policy_io import PolicyIO, PolicyIOError


def elu(x: np.ndarray) -> np.ndarray:
    return np.where(x > 0, x, np.expm1(np.minimum(x, 0)))


class ActorMLP:
    """rsl_rl actor의 평균 행동 경로(Linear-ELU 반복, 마지막은 Linear). obs 정규화 없음."""

    def __init__(self, weights: list[np.ndarray], biases: list[np.ndarray]):
        self.weights, self.biases = weights, biases

    @classmethod
    def from_npz(cls, path: str | Path) -> "ActorMLP":
        with np.load(path, allow_pickle=False) as z:
            n = int(z["num_layers"])
            return cls([z[f"w{i}"].astype(np.float32) for i in range(n)], [z[f"b{i}"].astype(np.float32) for i in range(n)])

    @property
    def input_dim(self) -> int:
        return self.weights[0].shape[1]

    @property
    def output_dim(self) -> int:
        return self.weights[-1].shape[0]

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        x = obs.astype(np.float32)
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            x = w @ x + b
            if i < len(self.weights) - 1:
                x = elu(x)
        return x


class PolicyRunner:
    def __init__(self, io: PolicyIO, actor_npz: str | Path):
        self.io = io
        self.actor = ActorMLP.from_npz(actor_npz)
        dims = [self.actor.input_dim] + [w.shape[0] for w in self.actor.weights]
        want = [io.obs_dim, *io.hidden_dims, len(io.joints)]
        if dims != want:
            raise PolicyIOError(f"가중치 구조 {dims}가 yaml과 다릅니다({want})")
        self.last_action = np.zeros(len(io.joints), np.float32)
        self._trace_f = None
        self._trace_n = 0
        self.hold_default = False  # True면 정책을 쓰지 않고 항상 기본 자세를 목표로 냅니다(물리만 비교하는 통제 실험)
        self.trace_aux = None     # 기록 중이면, 플레이어가 직전 스텝의 관절 토크 |tau| [N·m](정책 조인트 순서)를 넣어 두면 다음 act()가 같이 기록합니다

    def enable_trace(self, path: str | Path, meta: dict | None = None) -> None:
        """매 act()마다 정책 입출력 한 줄(float32)을 path에 이어 씁니다. 열 이름은 path + '.json'에 적습니다.
        시뮬레이터 사이 차이를 비교하려고 만든 기능입니다. 프로세스가 갑자기 끝나도 남도록 매 줄 flush합니다."""
        n = len(self.io.joints)
        cols = (["step", "cmd_vx", "cmd_vy", "cmd_wz", "vx_b", "vy_b", "vz_b", "wx_b", "wy_b", "wz_b", "gx_b", "gy_b", "gz_b"]
                + [f"q{i}" for i in range(n)] + [f"qd{i}" for i in range(n)] + [f"a{i}" for i in range(n)] + [f"qt{i}" for i in range(n)]
                + ["base_z"] + [f"tau_prev{i}" for i in range(n)])
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(str(path) + ".json").write_text(json.dumps({"columns": cols, "dtype": "float32", "policy_dt_s": self.io.policy_dt,
                                                          "joints": list(self.io.joints), "meta": meta or {}}, ensure_ascii=False, indent=1), encoding="utf-8")
        self._trace_f = open(path, "wb")
        self._trace_n = 0

    def reset(self) -> None:
        """에피소드 시작(또는 정책 재시작) 때 호출합니다. 직전 행동 관측을 0으로 되돌립니다."""
        self.last_action[:] = 0.0

    def act(self, state: Mapping[str, np.ndarray]) -> np.ndarray:
        """state: observations.terms의 source 키(last_action 제외, 러너가 보관) + base_pos_z.
        반환: 정책 조인트 순서의 목표 위치 [rad]."""
        full = dict(state)
        full["last_action"] = self.last_action
        obs = self.io.build_obs(full)
        action = np.zeros(len(self.io.joints), np.float32) if self.hold_default else self.actor(obs)
        self.last_action = action.astype(np.float32)
        q_target = self.io.decode_action(action)
        if self._trace_f is not None:
            n = len(self.io.joints)
            aux = np.full(n, np.nan) if self.trace_aux is None else np.asarray(self.trace_aux, np.float64).reshape(-1)
            row = np.concatenate([[self._trace_n]] + [np.asarray(state[k], np.float64).reshape(-1)[:m] for k, m in (
                ("command", 3), ("base_lin_vel_b", 3), ("base_ang_vel_b", 3), ("projected_gravity_b", 3), ("joint_pos", n), ("joint_vel", n))]
                + [np.asarray(action, np.float64).reshape(-1), q_target.astype(np.float64), np.asarray(state["base_pos_z"], np.float64).reshape(-1)[:1], aux])
            self._trace_f.write(row.astype(np.float32).tobytes())
            self._trace_f.flush()
            self._trace_n += 1
        return q_target
