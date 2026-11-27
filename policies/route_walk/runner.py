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

    def reset(self) -> None:
        """에피소드 시작(또는 정책 재시작) 때 호출합니다. 직전 행동 관측을 0으로 되돌립니다."""
        self.last_action[:] = 0.0

    def act(self, state: Mapping[str, np.ndarray]) -> np.ndarray:
        """state: observations.terms의 source 키(last_action 제외, 러너가 보관) + base_pos_z.
        반환: 정책 조인트 순서의 목표 위치 [rad]."""
        full = dict(state)
        full["last_action"] = self.last_action
        obs = self.io.build_obs(full)
        action = self.actor(obs)
        self.last_action = action.astype(np.float32)
        return self.io.decode_action(action)
