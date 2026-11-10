# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""Isaac Lab 3.0 --external_callback으로 우리 과제를 등록합니다.

    hn-rl train --task HN-Velocity-Flat-Go2v0 --external_callback hn_locomotion.register.register_tasks ...

주의: Isaac Lab은 이 함수가 돌려준 목록과 겹치는 인자만 Hydra로 넘깁니다.
빈 목록을 돌려주면 hn-rl이 붙인 physics=isaacsim_physx가 사라져 newton_mjwarp로 학습되므로,
받은 인자를 그대로 돌려줍니다.
"""

import sys

import gymnasium as gym

_PKG = __name__.rsplit(".", 1)[0]

TASKS = {
    "HN-Velocity-Flat-Go2v0": ("HnGo2V0FlatEnvCfg", "HnGo2V0FlatPPORunnerCfg"),
    "HN-Velocity-Rough-Go2v0": ("HnGo2V0RoughEnvCfg", "HnGo2V0RoughPPORunnerCfg"),
}


def register_tasks() -> list[str]:
    for task_id, (env_cfg, agent_cfg) in TASKS.items():
        if task_id in gym.registry:
            continue
        gym.register(
            id=task_id,
            entry_point="isaaclab.envs:ManagerBasedRLEnv",
            disable_env_checker=True,
            kwargs={
                "env_cfg_entry_point": f"{_PKG}.envs.hn_v0_go2:{env_cfg}",
                "rsl_rl_cfg_entry_point": f"{_PKG}.envs.hn_v0_go2:{agent_cfg}",
                "default_agent": "rsl_rl",
            },
        )
    return list(sys.argv[1:])
