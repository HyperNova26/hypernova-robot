# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""Isaac Lab 3.0 --external_callback으로 우리 과제를 등록합니다.

저장소 루트가 import 경로에 있어야 합니다(컨테이너: PYTHONPATH=/workspace/hypernova).

    hn-rl train --task HN-Velocity-Flat-Go2v0 --external_callback policies.register.register_tasks ...

주의: Isaac Lab은 이 함수가 돌려준 목록과 겹치는 인자만 Hydra로 넘깁니다.
빈 목록을 돌려주면 hn-rl이 붙인 physics=isaacsim_physx가 사라져 newton_mjwarp로 학습되므로,
받은 인자를 그대로 돌려줍니다.
"""

import sys

import gymnasium as gym

from . import urdf_v0, urdf_v1

# 버전 패키지마다 TASKS와 env.py를 둡니다. 새 버전은 여기에 추가합니다.
VERSIONS = (urdf_v0, urdf_v1)


def register_tasks() -> list[str]:
    for pkg in VERSIONS:
        for task_id, (env_cfg, agent_cfg) in pkg.TASKS.items():
            if task_id in gym.registry:
                continue
            gym.register(
                id=task_id,
                entry_point="isaaclab.envs:ManagerBasedRLEnv",
                disable_env_checker=True,
                kwargs={
                    "env_cfg_entry_point": f"{pkg.__name__}.env:{env_cfg}",
                    "rsl_rl_cfg_entry_point": f"{pkg.__name__}.env:{agent_cfg}",
                    "default_agent": "rsl_rl",
                },
            )
    return list(sys.argv[1:])
