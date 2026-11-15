# SPDX-License-Identifier: Apache-2.0
"""policy_io.yaml을 Isaac Lab 환경 설정에 적용하고, 만들어진 환경이 yaml과 같은지 검사합니다.

Isaac Lab 3.0.0(hn:sim) 기준이며 Isaac Lab·torch가 있는 Python에서만 import합니다.
학습·평가 task는 env cfg를 만든 뒤 `apply_policy_io(cfg, io)`를 부르고, env를 만든 뒤 `check_env(env, io)`가
빈 목록을 돌려주는지 확인합니다. 배포 쪽은 같은 yaml을 runner.py로 읽습니다.
"""
from __future__ import annotations

import numpy as np

from policy_io import PolicyIO

ACTUATOR_GROUP = "base_legs"  # 표준 Go2 설정의 다리 액추에이터 이름


def apply_policy_io(env_cfg, io: PolicyIO, *, apply_noise: bool = True, apply_command_ranges: bool = True) -> None:
    """yaml 값을 env cfg에 씁니다. 학습·평가가 yaml과 다른 값을 쓰지 못하게 하는 단방향 적용입니다."""
    # 주기. 센서 갱신 주기도 기본 설정(velocity_env_cfg)과 같은 규칙으로 다시 맞춥니다.
    env_cfg.sim.dt = io.sim_dt
    env_cfg.decimation = io.decimation
    if getattr(env_cfg.scene, "height_scanner", None) is not None:
        env_cfg.scene.height_scanner.update_period = io.decimation * io.sim_dt
    if getattr(env_cfg.scene, "contact_forces", None) is not None:
        env_cfg.scene.contact_forces.update_period = io.sim_dt

    # 행동
    a = env_cfg.actions.joint_pos
    a.scale = io.action_scale
    a.use_default_offset = True
    a.clip = None if io.action_clip is None else {".*": io.action_clip}

    # 기본 자세와 PD
    robot = env_cfg.scene.robot
    robot.init_state.joint_pos = dict(io.default_pos_by_name)
    act = robot.actuators[ACTUATOR_GROUP]
    act.stiffness = io.kp
    act.damping = io.kd
    act.friction = io.friction
    act.actuator_effort_limit = io.pd_regex_dict("effort_limit_nm")
    act.saturation_effort = io.pd_regex_dict("effort_limit_nm")
    act.actuator_velocity_limit = io.pd_regex_dict("velocity_limit_rad_s")

    # height scan
    hs = getattr(env_cfg.scene, "height_scanner", None)
    if hs is not None:
        hs.pattern_cfg.size = list(io.hs_size)
        hs.pattern_cfg.resolution = io.hs_res
        hs.pattern_cfg.ordering = "xy"  # yaml의 ordering: x_fastest에 해당
        hs.ray_alignment = io.raw["height_scan"]["alignment"]
        hs.offset.pos = (0.0, 0.0, io.hs_start_height)
        term = env_cfg.observations.policy.height_scan
        term.clip = io.hs_clip
        term.params["offset"] = io.hs_offset

    # 접촉·종료·height scanner가 붙는 몸체 이름은 로봇·env 설정(policies/urdf_v0/env.py)이 정하므로 여기서 덮어쓰지 않습니다.
    # check_env가 yaml의 root·발 body가 로봇에 있는지만 확인합니다.

    # 학습 전용 값
    tr = io.raw.get("training", {})
    if apply_command_ranges and "command_ranges" in tr:
        r = env_cfg.commands.base_velocity.ranges
        for k, v in tr["command_ranges"].items():
            setattr(r, k, tuple(v))
    if apply_noise and "obs_noise_uniform" in tr:
        from isaaclab.utils.noise import UniformNoiseCfg

        names = {t.name for t in io.obs_terms}
        for k, (lo, hi) in tr["obs_noise_uniform"].items():
            if k in names and getattr(env_cfg.observations.policy, k, None) is not None:
                getattr(env_cfg.observations.policy, k).noise = UniformNoiseCfg(n_min=lo, n_max=hi)


def check_env(env, io: PolicyIO) -> list[str]:
    """만들어진 환경이 yaml과 다른 점을 문자열 목록으로 돌려줍니다. 빈 목록이면 같습니다."""
    from isaaclab.sensors.ray_caster.patterns import grid_pattern

    u = env.unwrapped
    bad: list[str] = []
    robot = u.scene["robot"]

    backend = {"PhysxCfg": "physx", "NewtonCfg": "newton"}.get(type(u.cfg.sim.physics).__name__, type(u.cfg.sim.physics).__name__)
    if backend != io.physics_backend:
        bad.append(f"물리 엔진: env {backend} != yaml {io.physics_backend}(CLI에 physics=isaacsim_physx 등으로 맞추세요)")
    missing = [n for n in (io.root_link, *io.foot_links) if n not in robot.body_names]
    if missing:
        bad.append(f"yaml의 root·발 body가 로봇에 없습니다: {missing}(로봇 몸체 {len(robot.body_names)}개 중)")
    if list(robot.joint_names) != list(io.joints):
        bad.append(f"조인트 순서: env {list(robot.joint_names)} != yaml {list(io.joints)}")
    t = getattr(robot.data.default_joint_pos, "torch", robot.data.default_joint_pos)
    if not np.allclose(t[0].cpu().numpy(), io.default_pos, atol=1e-6):
        bad.append(f"기본 자세: env {t[0].cpu().numpy().round(4).tolist()} != yaml {io.default_pos.tolist()}")

    term = u.action_manager.get_term("joint_pos")
    if list(getattr(term, "_joint_names", [])) != list(io.joints):
        bad.append("행동 term의 조인트 순서가 yaml과 다릅니다")
    act_cfg = u.cfg.actions.joint_pos
    if act_cfg.scale != io.action_scale or not act_cfg.use_default_offset:
        bad.append(f"행동: env scale {act_cfg.scale}, use_default_offset {act_cfg.use_default_offset} != yaml {io.action_scale}, True")

    if u.cfg.decimation != io.decimation or abs(u.cfg.sim.dt - io.sim_dt) > 1e-12 or abs(u.step_dt - io.policy_dt) > 1e-9:
        bad.append(f"주기: env decimation {u.cfg.decimation}, dt {u.cfg.sim.dt}, step {u.step_dt} != yaml {io.decimation}, {io.sim_dt}, {io.policy_dt}")

    om = u.observation_manager
    names, dims = list(om.active_terms["policy"]), [int(np.prod(d)) for d in om.group_obs_term_dim["policy"]]
    if names != [x.name for x in io.obs_terms] or dims != [x.dim for x in io.obs_terms]:
        bad.append(f"관측 항목: env {list(zip(names, dims))} != yaml {[(x.name, x.dim) for x in io.obs_terms]}")

    a = u.cfg.scene.robot.actuators[ACTUATOR_GROUP]
    if (a.stiffness, a.damping) != (io.kp, io.kd):
        bad.append(f"PD: env kp {a.stiffness}, kd {a.damping} != yaml {io.kp}, {io.kd}")
    if a.saturation_effort != io.pd_regex_dict("effort_limit_nm") or a.actuator_velocity_limit != io.pd_regex_dict("velocity_limit_rad_s"):
        bad.append("토크·속도 제한이 yaml과 다릅니다")

    hs = u.cfg.scene.height_scanner
    if hs is not None:
        starts = grid_pattern(hs.pattern_cfg, "cpu")[0][:, :2].numpy()
        if starts.shape != io.height_scan_offsets().shape or not np.allclose(starts, io.height_scan_offsets(), atol=1e-5):
            bad.append("height scan ray 격자(개수·순서·간격)가 yaml과 다릅니다")
    return bad
