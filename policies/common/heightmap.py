# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""LiDAR로 본 점을 기억해서 만드는 height map 관측 (2026-11-15).

Isaac Lab 기본 height scan은 몸통 위 20 m에서 grid 칸마다 수직으로 광선을 쏘는 "완벽한 지도"(GT)입니다.
여기서는 실제 로봇처럼 몸통에 단 LiDAR 광선이 맞은 점만으로 같은 모양의 grid를 채웁니다.

    LiDAR scan(20 Hz) → 칸마다 가장 높은 점을 world 좌표로 기억(최근 memory_s 초)
    → 매 step 현재 몸통 기준 grid로 옮김(칸마다 가장 최근 scan 값)
    → 기억에 없는 칸은 발끝 평면으로 채움

- grid 칸 순서와 값의 규칙은 Isaac Lab GridPatternCfg(ordering="xy") + mdp.height_scan과 같습니다.
  값 = 기준 높이 − 바닥 높이 − offset. 기준 높이는 GT height scanner의 pos_w z를 그대로 써서 GT와 같은 규칙을 지킵니다.
- 발끝 평면: 발마다 최근 foot_window_s 초 동안 가장 낮았던 발 중심 높이에서 발 반지름을 빼고, 네 점에 맞는
  평면 z = a + b·x + c·y를 구합니다. 걷는 중 공중에 뜬 발 때문에 평면이 들리는 것을 줄이기 위해서입니다.
  실기에서는 관절 각도(정기구학)와 IMU로 같은 값을 계산할 수 있습니다.
"""

from __future__ import annotations

import torch

from isaaclab.managers import ManagerTermBase


def _yaw(quat_xyzw: torch.Tensor) -> torch.Tensor:
    x, y, z, w = quat_xyzw.unbind(-1)
    return torch.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class lidar_memory_height_scan(ManagerTermBase):
    """ObsTerm func로 쓰는 클래스. params:

    - lidar_cfg: LiDAR RayCaster (SceneEntityCfg)
    - ref_sensor_cfg: GT height scanner. 값의 기준 높이(pos_w z)에만 씁니다.
    - grid_size, grid_offset_x, resolution: 정책 grid [m]. GT scanner가 같은 grid를 쓰면 칸이 1:1로 맞습니다.
    - memory_s: 기억 시간 [s], scan_period_s: LiDAR 주기 [s]
    - foot_body_regex, foot_radius, foot_window_s: 발끝 평면
    - offset: mdp.height_scan과 같은 값 빼기 [m]
    """

    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        p = cfg.params
        self.lidar_name = p["lidar_cfg"].name
        self.ref_name = p["ref_sensor_cfg"].name
        self.offset = p.get("offset", 0.5)
        self.res = p.get("resolution", 0.1)
        sx, sy = p.get("grid_size", (1.6, 1.0))
        self.gx0 = p.get("grid_offset_x", 0.0)
        dev = env.device
        # Isaac Lab grid_pattern(ordering="xy")와 같은 순서: x가 가장 빨리 바뀜
        xs = torch.arange(-sx / 2, sx / 2 + 1e-9, self.res, device=dev)
        ys = torch.arange(-sy / 2, sy / 2 + 1e-9, self.res, device=dev)
        gx, gy = torch.meshgrid(xs, ys, indexing="xy")
        self.nx, self.ny = xs.numel(), ys.numel()
        self.x_min, self.y_min = float(xs[0]) + self.gx0, float(ys[0])
        self.cell_xy = torch.stack([gx.flatten() + self.gx0, gy.flatten()], dim=-1)  # (C, 2), 몸통 yaw frame
        self.C = self.cell_xy.shape[0]

        self.scan_period = p.get("scan_period_s", 0.05)
        self.S = max(1, round(p.get("memory_s", 3.0) / self.scan_period))
        n = env.num_envs
        # 기억: scan마다 칸별 (world x, y, z)와 유효 여부. 슬롯은 ring buffer.
        self.mem_xyz = torch.zeros(n, self.S, self.C, 3, device=dev)
        self.mem_valid = torch.zeros(n, self.S, self.C, dtype=torch.bool, device=dev)
        self.mem_stamp = torch.full((n, self.S), -1, dtype=torch.long, device=dev)  # scan 번호, -1 = 빈 슬롯
        self.scan_count = 0
        self.last_scan_tick = -1

        robot = env.scene["robot"]
        self.foot_ids, _ = robot.find_bodies(p.get("foot_body_regex", ".*_foot"))
        self.foot_radius = p.get("foot_radius", 0.025)
        self.W = max(1, round(p.get("foot_window_s", 0.5) / env.step_dt))
        self.foot_z = torch.full((n, self.W, len(self.foot_ids)), float("inf"), device=dev)
        self.foot_k = 0

        # 확인용: 마지막으로 만든 grid의 출처 (0 = 발끝 평면, 1 = 기억, 2 = 이번 scan)
        self.last_source = torch.zeros(n, self.C, dtype=torch.long, device=dev)

    def reset(self, env_ids=None):
        if env_ids is None:
            env_ids = slice(None)
        self.mem_valid[env_ids] = False
        self.mem_stamp[env_ids] = -1
        self.foot_z[env_ids] = float("inf")

    # ---- scan을 grid 칸 단위로 줄여서 기억에 넣기 ----
    def _scan_points(self, env, base_xy, yaw):
        """이번 scan의 칸별 (world x, y, z), 유효 여부. 칸마다 가장 높은 점."""
        n = env.num_envs
        hits = env.scene.sensors[self.lidar_name].data.ray_hits_w.torch  # (n, R, 3), 안 맞으면 inf
        ok = torch.isfinite(hits).all(-1)
        local = self._to_local(hits[..., :2], base_xy, yaw)
        ix = torch.floor((local[..., 0] - self.x_min) / self.res + 0.5).long()
        iy = torch.floor((local[..., 1] - self.y_min) / self.res + 0.5).long()
        ok &= (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        cell = (iy * self.nx + ix).clamp(0, self.C - 1)
        flat = torch.arange(n, device=env.device).unsqueeze(1) * self.C + cell
        z = torch.where(ok, hits[..., 2], torch.full_like(hits[..., 2], -float("inf")))
        zmax = torch.full((n * self.C,), -float("inf"), device=env.device)
        zmax.scatter_reduce_(0, flat.flatten(), z.flatten(), reduce="amax")
        zmax = zmax.view(n, self.C)
        valid = torch.isfinite(zmax)
        # 칸 중심의 world xy (scan 시점 몸통 기준)
        world_xy = self._to_world(self.cell_xy.expand(n, -1, -1), base_xy, yaw)
        return torch.cat([world_xy, torch.where(valid, zmax, 0.0).unsqueeze(-1)], dim=-1), valid

    @staticmethod
    def _to_local(xy_w, base_xy, yaw):
        c, s = torch.cos(yaw).unsqueeze(1), torch.sin(yaw).unsqueeze(1)
        d = xy_w - base_xy.unsqueeze(1)
        return torch.stack([c * d[..., 0] + s * d[..., 1], -s * d[..., 0] + c * d[..., 1]], dim=-1)

    @staticmethod
    def _to_world(xy_l, base_xy, yaw):
        c, s = torch.cos(yaw).unsqueeze(1), torch.sin(yaw).unsqueeze(1)
        x, y = xy_l[..., 0], xy_l[..., 1]
        return torch.stack([c * x - s * y, s * x + c * y], dim=-1) + base_xy.unsqueeze(1)

    # ---- 발끝 평면 ----
    def _foot_plane(self, env, base_xy, yaw):
        """grid 칸별 발끝 평면 높이 (n, C)."""
        foot = env.scene["robot"].data.body_pos_w.torch[:, self.foot_ids]  # (n, 4, 3)
        self.foot_z[:, self.foot_k % self.W] = foot[..., 2]
        self.foot_k += 1
        zlow = self.foot_z.amin(dim=1) - self.foot_radius  # (n, 4)
        fl = self._to_local(foot[..., :2], base_xy, yaw)  # (n, 4, 2)
        A = torch.cat([torch.ones_like(fl[..., :1]), fl], dim=-1)  # (n, 4, 3)
        AtA = A.transpose(1, 2) @ A + 1e-6 * torch.eye(3, device=env.device)
        coef = torch.linalg.solve(AtA, A.transpose(1, 2) @ zlow.unsqueeze(-1)).squeeze(-1)  # (n, 3)
        return coef[:, :1] + coef[:, 1:2] * self.cell_xy[:, 0] + coef[:, 2:3] * self.cell_xy[:, 1]

    def __call__(
        self,
        env,
        lidar_cfg,
        ref_sensor_cfg,
        grid_size=(1.6, 1.0),
        grid_offset_x=0.0,
        resolution=0.1,
        memory_s=3.0,
        scan_period_s=0.05,
        foot_body_regex=".*_foot",
        foot_radius=0.025,
        foot_window_s=0.5,
        offset=0.5,
    ):
        # 파라미터는 __init__에서 읽었습니다. Isaac Lab이 이름을 검사하므로 여기 그대로 둡니다.
        n = env.num_envs
        robot = env.scene["robot"]
        base_xy = robot.data.root_pos_w.torch[:, :2]
        yaw = _yaw(robot.data.root_quat_w.torch)
        plane_z = self._foot_plane(env, base_xy, yaw)

        # LiDAR 주기마다 scan을 기억에 넣습니다(모든 env 같은 시각).
        tick = int(env.common_step_counter * env.step_dt / self.scan_period + 1e-6)
        if tick != self.last_scan_tick:
            self.last_scan_tick = tick
            xyz, valid = self._scan_points(env, base_xy, yaw)
            slot = self.scan_count % self.S
            self.mem_xyz[:, slot] = xyz
            self.mem_valid[:, slot] = valid
            self.mem_stamp[:, slot] = self.scan_count
            self.scan_count += 1

        # 기억 전체를 현재 grid로 옮기고, 칸마다 가장 최근 scan을 고릅니다(같은 scan이면 가장 높은 점).
        S, C = self.S, self.C
        pts = self.mem_xyz.view(n, S * C, 3)
        local = self._to_local(pts[..., :2], base_xy, yaw)
        ix = torch.floor((local[..., 0] - self.x_min) / self.res + 0.5).long()
        iy = torch.floor((local[..., 1] - self.y_min) / self.res + 0.5).long()
        stamp = self.mem_stamp.unsqueeze(-1).expand(n, S, C).reshape(n, S * C)
        ok = self.mem_valid.view(n, S * C) & (stamp >= 0)
        ok &= (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        cell = (iy * self.nx + ix).clamp(0, C - 1)
        flat = (torch.arange(n, device=env.device).unsqueeze(1) * C + cell).flatten()
        st = torch.where(ok, stamp, torch.full_like(stamp, -1)).flatten()
        best = torch.full((n * C,), -1, dtype=torch.long, device=env.device)
        best.scatter_reduce_(0, flat, st, reduce="amax")
        pick = ok.flatten() & (st == best[flat])
        z = torch.where(pick, pts[..., 2].flatten(), torch.full_like(st, 0, dtype=pts.dtype) - float("inf"))
        mem_z = torch.full((n * C,), -float("inf"), device=env.device)
        mem_z.scatter_reduce_(0, flat, z, reduce="amax")
        mem_z = mem_z.view(n, C)
        best = best.view(n, C)
        have = torch.isfinite(mem_z)
        ground = torch.where(have, mem_z, plane_z)

        newest = self.scan_count - 1
        self.last_source = torch.where(have, torch.where(best == newest, 2, 1), 0)

        ref_z = env.scene.sensors[self.ref_name].data.pos_w.torch[:, 2].unsqueeze(1)
        return ref_z - ground - self.offset

