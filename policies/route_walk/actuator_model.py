# SPDX-License-Identifier: Apache-2.0
"""정책이 학습된 Isaac Lab 액추에이터(DCMotor)와 같은 규칙의 관절 토크 계산. numpy만 씁니다.

관절 목표 위치 q*를 PD로 토크로 바꾸고(tau = kp(q* - q) - kd*qd), 속도에 따라 줄어드는 토크 상한으로 자릅니다.
상한: top = sat*(1 - v/v_max), bottom = sat*(-1 - v/v_max), 그리고 |tau| <= effort_limit (v는 +-v_max로 자른 속도).
값은 모두 policy_io.yaml(pd.kp, pd.kd, pd.groups)에서 옵니다. 토크 제어를 지원하는 시뮬레이터(MuJoCo, PhysX 텐서 API)가 쓰고,
실기에서는 모터 드라이버가 PD를 직접 돌리므로 이 모듈은 쓰지 않습니다.
"""
from __future__ import annotations

import numpy as np

from policy_io import PolicyIO


class DCMotor:
    def __init__(self, io: PolicyIO):
        self.kp, self.kd = io.kp, io.kd
        self.eff = io.effort_limit.astype(np.float64)
        self.vlim = io.velocity_limit.astype(np.float64)

    def __call__(self, q_target, q, qd) -> np.ndarray:
        """정책 조인트 순서의 목표 위치·현재 위치·현재 속도 -> 적용할 토크 [N·m]."""
        tau = self.kp * (np.asarray(q_target, np.float64) - q) - self.kd * qd
        v = np.clip(qd, -self.vlim, self.vlim)
        top = np.minimum(self.eff * (1.0 - v / self.vlim), self.eff)
        bottom = np.maximum(self.eff * (-1.0 - v / self.vlim), -self.eff)
        return np.clip(tau, bottom, top)
