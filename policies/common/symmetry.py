# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""좌우 대칭 데이터 증강 함수 (Isaac Lab 3.0.0 RslRlSymmetryCfg용, 2026-11-15).

PPO 업데이트마다 mini-batch를 좌우로 뒤집은 복사본을 붙여 학습합니다(batch 2배). 정책이 이유 없이 한쪽으로
도는 습관(전진 명령만 줘도 −0.03 rad/s로 오른쪽으로 돎, 2026-11-15 측정)을 막기 위함입니다.
앞뒤 뒤집기는 넣지 않습니다(앞뒤 다리 자세가 다르고 LiDAR가 앞에만 있음).

뒤집기는 몸통 frame의 xz 평면 거울상입니다(y → −y).
- 벡터(선속도, 중력 방향): y 부호 반대. 축벡터(각속도): x, z 부호 반대. 명령 (vx, vy, wz): vy, wz 부호 반대.
- 관절(위치, 속도, 이전 action, action): FL↔FR, RL↔RR 교환, hip(옆으로 벌리는 관절)만 부호 반대.
  네 다리 관절 축이 같은 방향(hip x, thigh·calf y)이고 기본 자세가 좌우 거울상(hip ±0.1)이어야 맞습니다.
- height scan: 같은 x, 반대 y 칸끼리 교환. 칸 위치에서 짝을 찾으므로 grid 배치 순서에 의존하지 않습니다.

관측 항목 이름으로 처리 방법을 정하고, 모르는 항목이 있으면 바로 에러를 냅니다(조용히 틀린 학습 방지).
"""

from __future__ import annotations

import torch

# 항목 이름 → 성분별 부호 (항목 자체 순서 그대로)
_VECTOR_SIGNS = {
    "base_lin_vel": (1.0, -1.0, 1.0),
    "base_ang_vel": (-1.0, 1.0, -1.0),
    "projected_gravity": (1.0, -1.0, 1.0),
    "velocity_commands": (1.0, -1.0, -1.0),
}
_JOINT_TERMS = ("joint_pos", "joint_vel", "actions")
_HEIGHT_TERMS = ("height_scan",)
_ACTION_TERM = "joint_pos"
_CACHE_ATTR = "_hn_left_right_symmetry"


def _mirror_joint_name(name: str) -> str:
    """FL_hip_joint → FR_hip_joint. 다리 이름은 앞 두 글자(F/R + L/R)입니다."""
    leg, rest = name[:2], name[2:]
    if len(leg) != 2 or leg[0] not in "FR" or leg[1] not in "LR":
        raise ValueError(f"[symmetry] 다리 이름을 알 수 없는 관절: {name}")
    return leg[0] + {"L": "R", "R": "L"}[leg[1]] + rest


def _joint_perm_sign(joint_names: list[str]) -> tuple[list[int], list[float]]:
    perm = [joint_names.index(_mirror_joint_name(n)) for n in joint_names]
    sign = [-1.0 if "_hip_" in n else 1.0 for n in joint_names]
    return perm, sign


def _match_mirror_xy(xy: torch.Tensor, tol: float = 1e-4) -> list[int]:
    """칸 i의 짝 j: x_j = x_i, y_j = −y_i. 짝이 없으면(grid가 y = 0에 대칭이 아니면) 에러."""
    target = xy.clone()
    target[:, 1] = -target[:, 1]
    dist = torch.cdist(target.double(), xy.double())
    d, j = dist.min(dim=1)
    if bool((d > tol).any()):
        raise ValueError(f"[symmetry] height scan grid가 y = 0에 대칭이 아닙니다(최대 어긋남 {float(d.max()):.4f} m)")
    return j.tolist()


def _height_cells_xy(u, cfg) -> torch.Tensor:
    """height scan 항목의 칸 위치 (C, 2), 몸통 yaw frame."""
    func = cfg.func
    if hasattr(func, "cell_xy"):  # lidar_memory_height_scan
        return func.cell_xy.detach().cpu()
    sensor = u.scene[cfg.params["sensor_cfg"].name]  # mdp.height_scan: RayCaster grid
    starts, _ = sensor.cfg.pattern_cfg.func(sensor.cfg.pattern_cfg, "cpu")
    offset = torch.tensor(sensor.cfg.offset.pos[:2])
    return starts[:, :2] + offset


def _action_joint_names(u) -> list[str]:
    term = u.action_manager.get_term(_ACTION_TERM)
    return list(term._joint_names)


def _group_perm_sign(u, group: str) -> tuple[torch.Tensor, torch.Tensor]:
    om = u.observation_manager
    names = om.active_terms[group]
    dims = om.group_obs_term_dim[group]
    cfgs = om._group_obs_term_cfgs[group]
    perm: list[int] = []
    sign: list[float] = []
    start = 0
    for name, dim, cfg in zip(names, dims, cfgs):
        if len(dim) != 1:
            raise ValueError(f"[symmetry] {group}/{name}: 1차원 항목만 지원합니다({dim})")
        n = dim[0]
        if name in _VECTOR_SIGNS:
            p, s = list(range(n)), list(_VECTOR_SIGNS[name])
        elif name in _JOINT_TERMS:
            joints = _action_joint_names(u) if name == "actions" else list(cfg.params["asset_cfg"].joint_names)
            p, s = _joint_perm_sign(joints)
        elif name in _HEIGHT_TERMS:
            p = _match_mirror_xy(_height_cells_xy(u, cfg))
            s = [1.0] * len(p)
        else:
            raise ValueError(f"[symmetry] {group}/{name}: 뒤집는 방법이 정해지지 않은 관측 항목입니다")
        if len(p) != n:
            raise ValueError(f"[symmetry] {group}/{name}: 차원 {n}인데 뒤집기 정의는 {len(p)}개입니다")
        perm += [start + i for i in p]
        sign += s
        start += n
    return torch.tensor(perm, dtype=torch.long), torch.tensor(sign)


def _tables(u, device) -> dict:
    """관측 그룹별, action의 (perm, sign). 처음 한 번 만들고 env에 저장합니다."""
    tables = getattr(u, _CACHE_ATTR, None)
    if tables is None:
        tables = {g: _group_perm_sign(u, g) for g in u.observation_manager.active_terms}
        p, s = _joint_perm_sign(_action_joint_names(u))
        tables["__actions__"] = (torch.tensor(p, dtype=torch.long), torch.tensor(s))
        setattr(u, _CACHE_ATTR, tables)
    return {k: (p.to(device), s.to(device)) for k, (p, s) in tables.items()}


def mirror_obs(u, group: str, x: torch.Tensor) -> torch.Tensor:
    perm, sign = _tables(u, x.device)[group]
    return x[:, perm] * sign


def mirror_actions(u, a: torch.Tensor) -> torch.Tensor:
    perm, sign = _tables(u, a.device)["__actions__"]
    return a[:, perm] * sign


@torch.no_grad()
def compute_left_right_symmetric_states(env, obs=None, actions=None):
    """RslRlSymmetryCfg.data_augmentation_func. [원본; 좌우 뒤집기] 순서로 batch를 2배로 만듭니다."""
    u = env.unwrapped
    obs_aug = None
    if obs is not None:
        n = obs.batch_size[0]
        obs_aug = obs.repeat(2)
        for group in obs.keys():
            obs_aug[group][n:] = mirror_obs(u, group, obs[group])
    actions_aug = None
    if actions is not None:
        actions_aug = torch.cat([actions, mirror_actions(u, actions)], dim=0)
    return obs_aug, actions_aug
