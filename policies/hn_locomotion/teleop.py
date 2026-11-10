# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""학습한 보행 정책을 키보드로 조종합니다 (Isaac Lab 3.0.0, hn:sim).

컨테이너 안, 호스트 데스크톱 세션에서 연 셸에서 실행합니다(창이 필요).

    cd /workspace/isaaclab
    ./isaaclab.sh -p /workspace/hypernova/policies/hn_locomotion/teleop.py \
        --task HN-Velocity-Rough-Go2v0 --terrain stairs --level 3 --visualizer kit

키 (Isaac Sim 창을 클릭해 포커스를 준 상태에서):
    ↑ / ↓   앞 / 뒤          ← / →   왼쪽 / 오른쪽 옆걸음
    Z / X   왼쪽 / 오른쪽 회전  L       명령 0 (정지)
    키를 떼면 그 방향 명령이 빠집니다. 여러 키를 같이 누르면 합쳐집니다.

--terrain (Rough 과제만): all, flat, slope, stairs, boxes, rough
--level: 지형 난이도 0(쉬움)~9(어려움). 넘어지면 같은 자리에서 다시 시작합니다.
--checkpoint: model_*.pt 경로. 없으면 이 과제의 가장 최근 학습, 마지막 체크포인트.
physics는 PhysX(isaacsim_physx)로 고정합니다(ADR-0002).
"""

import argparse
import os
import sys
import time

# 우리 과제 등록을 위해 policies/를 import 경로에 넣습니다(PYTHONPATH export 불필요).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from isaaclab.app import add_launcher_args, launch_simulation  # noqa: E402

TERRAIN_GROUPS = {
    "flat": ["flat"],
    "slope": ["hf_pyramid_slope", "hf_pyramid_slope_inv"],
    "stairs": ["pyramid_stairs", "pyramid_stairs_inv"],
    "boxes": ["boxes"],
    "rough": ["random_rough"],
}

parser = argparse.ArgumentParser(description="HyperNova 보행 정책 키보드 조종")
parser.add_argument("--task", default="HN-Velocity-Rough-Go2v0")
parser.add_argument("--checkpoint", default=None, help="model_*.pt 경로 (기본: 가장 최근)")
parser.add_argument("--terrain", default="all", choices=["all", *TERRAIN_GROUPS])
parser.add_argument("--level", type=int, default=0, help="지형 난이도 0~9")
parser.add_argument("--vx", type=float, default=0.8, help="↑↓ 한 번에 주는 앞뒤 속도 [m/s]")
parser.add_argument("--vy", type=float, default=0.4, help="←→ 옆 속도 [m/s]")
parser.add_argument("--wz", type=float, default=1.0, help="Z/X 회전 속도 [rad/s]")
add_launcher_args(parser)
args_cli, _ = parser.parse_known_args()


def configure(env_cfg) -> None:
    env_cfg.scene.num_envs = 1
    env_cfg.episode_length_s = 3600.0  # 시간 초과 리셋 없이 오래 조종
    env_cfg.curriculum.terrain_levels = None
    env_cfg.events.push_robot = None
    env_cfg.events.base_external_force_torque = None

    # 속도 명령은 키보드가 매 스텝 덮어씁니다. 자동 재샘플링·heading 제어는 끕니다.
    cmd = env_cfg.commands.base_velocity
    cmd.heading_command = False
    cmd.ranges.heading = None
    cmd.rel_standing_envs = 0.0
    cmd.resampling_time_range = (1.0e6, 1.0e6)

    gen = env_cfg.scene.terrain.terrain_generator
    if gen is not None:
        if args_cli.terrain != "all":
            gen.sub_terrains = {k: v for k, v in gen.sub_terrains.items() if k in TERRAIN_GROUPS[args_cli.terrain]}
        gen.num_rows = 10
        gen.num_cols = len(gen.sub_terrains)
        gen.curriculum = True  # 행(row)이 난이도 순서가 되게
    elif args_cli.terrain != "all":
        print(f"[teleop] {args_cli.task}는 평지 과제라 --terrain {args_cli.terrain}를 무시합니다.")

    # 카메라가 로봇을 따라다니게 (뒤쪽 위에서 바라봄)
    from isaaclab_visualizers.kit import KitVisualizerCfg

    env_cfg.sim.visualizer_cfgs = [
        KitVisualizerCfg(origin_type="asset", origin_track_path="robot", eye=(-2.5, -1.5, 1.5), lookat=(0.0, 0.0, 0.3))
    ]


def place_on_level(env) -> None:
    terrain = env.unwrapped.scene.terrain
    if getattr(terrain, "terrain_origins", None) is None:
        return
    level = max(0, min(args_cli.level, terrain.terrain_origins.shape[0] - 1))
    terrain.terrain_levels[:] = level
    terrain.env_origins[:] = terrain.terrain_origins[terrain.terrain_levels, terrain.terrain_types]
    print(f"[teleop] 지형 '{args_cli.terrain}', 난이도 {level}")


def main() -> None:
    import gymnasium as gym
    import torch

    from hn_locomotion.register import register_tasks

    register_tasks()

    from isaaclab_tasks.utils import get_checkpoint_path, resolve_task_config

    from isaaclab_rl.rsl_rl import (
        RslRlVecEnvWrapper,
        check_rsl_rl_version,
        create_rsl_rl_runner,
        handle_deprecated_rsl_rl_cfg,
    )

    env_cfg, agent_cfg = resolve_task_config(
        args_cli.task, "rsl_rl_cfg_entry_point", play_mode=True, overrides=["physics=isaacsim_physx"]
    )
    configure(env_cfg)

    with launch_simulation(env_cfg, args_cli):
        from isaaclab.devices import Se2Keyboard, Se2KeyboardCfg

        agent_cfg = handle_deprecated_rsl_rl_cfg(agent_cfg, check_rsl_rl_version())
        log_root = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
        ckpt = args_cli.checkpoint or get_checkpoint_path(log_root, agent_cfg.load_run, agent_cfg.load_checkpoint)
        print(f"[teleop] 체크포인트: {ckpt}")

        env = gym.make(args_cli.task, cfg=env_cfg)
        place_on_level(env)
        env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
        env.reset()

        runner = create_rsl_rl_runner(env, agent_cfg)
        runner.load(ckpt)
        policy = runner.get_inference_policy(device=env.unwrapped.device)

        keyboard = Se2Keyboard(
            Se2KeyboardCfg(
                v_x_sensitivity=args_cli.vx,
                v_y_sensitivity=args_cli.vy,
                omega_z_sensitivity=args_cli.wz,
                sim_device=env.unwrapped.device,
            )
        )
        cmd_term = env.unwrapped.command_manager.get_term("base_velocity")
        dt = env.unwrapped.step_dt
        obs = env.get_observations()
        print("[teleop] Isaac Sim 창을 클릭한 뒤 ↑↓←→ / Z X / L 로 조종. 종료는 터미널에서 Ctrl+C")

        try:
            while True:
                start = time.time()
                with torch.inference_mode():
                    cmd_term.vel_command_b[:] = keyboard.advance()
                    obs, _, dones, _ = env.step(policy(obs))
                    policy.reset(dones)
                sleep = dt - (time.time() - start)
                if sleep > 0:
                    time.sleep(sleep)
        except KeyboardInterrupt:
            pass
        finally:
            env.close()


if __name__ == "__main__":
    main()
