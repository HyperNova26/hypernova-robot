# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""학습한 보행 정책을 키보드로 조종합니다 (Isaac Lab 3.0.0, hn:sim).

컨테이너 안, 호스트 데스크톱 세션에서 연 셸에서 실행합니다(창이 필요).

    cd /workspace/isaaclab
    ./isaaclab.sh -p /workspace/hypernova/policies/teleop.py \
        --task HN-Velocity-Rough-Go2v0 --terrain stairs --level 3 --visualizer kit

키 (Isaac Sim 창을 클릭해 포커스를 준 상태에서):
    ↑ / ↓   앞 / 뒤          ← / →   왼쪽 / 오른쪽 옆걸음
    Z / X   왼쪽 / 오른쪽 회전  L       명령 0 (정지)
    기본: 누르고 있는 동안만 그 방향으로 갑니다. 여러 키를 같이 누르면 합쳐집니다.
    --incremental: 누를 때마다 그 방향으로 한 단계(--vx, --vy, --wz)씩 더하고, 떼도 유지합니다.
        ↑ 두 번이면 두 단계, ↑ 다음 ↓면 0, ↑ 다음 ←면 앞+왼쪽입니다. 학습한 명령 범위는 넘지 않습니다.
        원격 데스크톱(RustDesk)처럼 누르고 있는 키가 바로 뗀 것으로 들어올 때 씁니다.
    명령이 바뀔 때마다 터미널에 출력합니다. --log_keys면 받은 키 이벤트도 모두 출력합니다.

--terrain (Rough 과제만): all, flat, slope, stairs, boxes, rough
--level: 지형 난이도 0(쉬움)~9(어려움). 넘어지면 같은 자리에서 다시 시작합니다.
--checkpoint: model_*.pt 경로. 없으면 이 과제의 가장 최근 학습, 마지막 체크포인트.
physics는 PhysX(isaacsim_physx)로 고정합니다(ADR-0002).
"""

import argparse
import os
import sys
import time

# 우리 과제 등록을 위해 저장소 루트를 import 경로에 넣습니다(PYTHONPATH export 불필요).
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
parser.add_argument("--vx", type=float, default=0.8, help="↑↓ 앞뒤 속도 [m/s] (--incremental이면 한 단계)")
parser.add_argument("--vy", type=float, default=0.4, help="←→ 옆 속도 [m/s] (--incremental이면 한 단계)")
parser.add_argument("--wz", type=float, default=1.0, help="Z/X 회전 속도 [rad/s] (--incremental이면 한 단계)")
parser.add_argument(
    "--incremental", action="store_true", help="누를 때마다 명령에 한 단계씩 더하고 떼도 유지합니다(원격 데스크톱용)"
)
parser.add_argument("--log_keys", action="store_true", help="받은 키 이벤트를 모두 출력합니다(키 입력 점검용)")
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


class KeyLogger:
    """받은 키 이벤트를 시각과 함께 출력합니다(--log_keys). 명령에는 손대지 않습니다."""

    def __init__(self):
        import carb
        import omni.appwindow

        self._input = carb.input.acquire_input_interface()
        self._keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        self._sub = self._input.subscribe_to_keyboard_events(self._keyboard, self._on_event)

    def _on_event(self, event, *args) -> bool:
        # 문자 키는 CHAR 이벤트도 오고, 이때 event.input은 KeyboardInput이 아니라 문자열입니다.
        print(f"[teleop] 키 이벤트 {event.type} {event.input} t={time.monotonic():.3f}", flush=True)
        return True

    def close(self) -> None:
        self._input.unsubscribe_to_keyboard_events(self._keyboard, self._sub)


class IncrementalKeyboard:
    """누를 때마다 그 축 명령에 한 단계씩 더하고, 떼도 유지하는 키보드 입력(--incremental).

    RustDesk로 원격 접속하면 키를 누르고 있어도 KEY_PRESS 바로 뒤에 KEY_RELEASE가 붙어 옵니다
    (2026-11-11 --log_keys로 확인, RustDesk 키보드 모드 Map). 자동 반복은 마지막에 누른 키만 되풀이하므로
    두 키를 같이 누르고 있는 것도 전달되지 않습니다. 그래서 누르는 동안만 명령을 주는 Se2Keyboard는
    명령이 곧바로 0이 됩니다. 여기서는 KEY_PRESS만 세므로 키를 누르고 있을 필요가 없습니다.
    축마다 단계 수를 정수로 세므로 ↑ 다음 ↓는 정확히 0입니다.
    """

    def __init__(self, steps, ranges, device):
        import carb
        import omni.appwindow

        # 키 → (축 번호, 방향). 축은 (v_x [m/s], v_y [m/s], ω_z [rad/s]), y와 회전은 왼쪽이 +입니다.
        self._keys = {
            "UP": (0, 1), "DOWN": (0, -1),
            "LEFT": (1, 1), "RIGHT": (1, -1),
            "Z": (2, 1), "X": (2, -1),
        }  # fmt: skip
        self._steps = steps
        self._ranges = ranges
        self._levels = [0, 0, 0]
        self._device = device
        self._press = carb.input.KeyboardEventType.KEY_PRESS
        self._input = carb.input.acquire_input_interface()
        self._keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        self._sub = self._input.subscribe_to_keyboard_events(self._keyboard, self._on_event)

    def _on_event(self, event, *args) -> bool:
        # KEY_RELEASE·KEY_REPEAT는 무시합니다. CHAR 이벤트는 event.input이 문자열이라 type을 먼저 봅니다.
        if event.type != self._press:
            return True
        name = event.input.name
        if name == "L":
            self._levels = [0, 0, 0]
        elif name in self._keys:
            axis, sign = self._keys[name]
            level = self._levels[axis] + sign
            low, high = self._ranges[axis]
            # 학습한 명령 범위를 벗어나는 단계로는 가지 않습니다(1e-6은 부동소수 오차 여유).
            if low - 1e-6 <= level * self._steps[axis] <= high + 1e-6:
                self._levels[axis] = level
        return True

    def advance(self):
        """Se2Keyboard.advance()처럼 (v_x, v_y, ω_z) 명령을 tensor로 돌려줍니다."""
        import torch

        command = [level * step for level, step in zip(self._levels, self._steps)]
        return torch.tensor(command, dtype=torch.float32, device=self._device)

    def close(self) -> None:
        self._input.unsubscribe_to_keyboard_events(self._keyboard, self._sub)


def print_command(command) -> None:
    vx, vy, wz = command
    print(f"[teleop] 명령 v_x {vx:+.2f} m/s, v_y {vy:+.2f} m/s, ω_z {wz:+.2f} rad/s", flush=True)


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

    from policies.register import register_tasks

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

        if args_cli.incremental:
            ranges = env_cfg.commands.base_velocity.ranges
            keyboard = IncrementalKeyboard(
                (args_cli.vx, args_cli.vy, args_cli.wz),
                (ranges.lin_vel_x, ranges.lin_vel_y, ranges.ang_vel_z),
                env.unwrapped.device,
            )
        else:
            keyboard = Se2Keyboard(
                Se2KeyboardCfg(
                    v_x_sensitivity=args_cli.vx,
                    v_y_sensitivity=args_cli.vy,
                    omega_z_sensitivity=args_cli.wz,
                    sim_device=env.unwrapped.device,
                )
            )
        key_logger = KeyLogger() if args_cli.log_keys else None
        cmd_term = env.unwrapped.command_manager.get_term("base_velocity")
        dt = env.unwrapped.step_dt
        obs = env.get_observations()
        how = "누르고 있는 동안만 움직입니다."
        if args_cli.incremental:
            how = "누를 때마다 한 단계씩 더하고, 떼도 유지합니다. 학습한 명령 범위를 넘는 단계는 무시합니다."
        print(
            f"[teleop] Isaac Sim 창을 클릭해 포커스를 준 뒤 조종합니다. {how}\n"
            f"    ↑ / ↓   앞 / 뒤 ({args_cli.vx:.2f} m/s)\n"
            f"    ← / →   왼쪽 / 오른쪽 옆걸음 ({args_cli.vy:.2f} m/s)\n"
            f"    Z / X   왼쪽 / 오른쪽 회전 ({args_cli.wz:.2f} rad/s)\n"
            "    L       정지 (모든 명령 0)\n"
            "    Ctrl+C  종료 (터미널에서)",
            flush=True,
        )
        last_command = None

        try:
            while True:
                start = time.time()
                with torch.inference_mode():
                    command = keyboard.advance()
                    cmd_term.vel_command_b[:] = command
                    obs, _, dones, _ = env.step(policy(obs))
                    policy.reset(dones)
                command = command.tolist()
                if command != last_command:
                    print_command(command)
                    last_command = command
                sleep = dt - (time.time() - start)
                if sleep > 0:
                    time.sleep(sleep)
        except KeyboardInterrupt:
            pass
        finally:
            if args_cli.incremental:
                keyboard.close()
            if key_logger is not None:
                key_logger.close()
            env.close()


if __name__ == "__main__":
    main()
