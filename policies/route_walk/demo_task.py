# SPDX-License-Identifier: Apache-2.0
"""PAIR360 데모 지형 위 Go2 v0 Rough task의 gym 등록. Isaac Lab을 import하지 않으므로 Kit 실행 전에 불러도 안전합니다.

환경 설정 클래스는 demo_task_cfg.py에 있고, gym이 문자열 entry point로 Kit 실행 뒤에 불러옵니다(저장소 루트가 import 경로에 있어야 합니다).
데이터(지형 USD)는 컨테이너의 /data(= 호스트 HN_DATA_DIR) 아래에 있어야 합니다. 다른 위치면 환경 변수 HN_DEMO_DATA로 바꿉니다.
"""
import gymnasium as gym

TASK_ID = "HN-Velocity-Demo-Rough-Go2v0"


def register() -> None:
    if TASK_ID in gym.registry:
        return
    gym.register(
        id=TASK_ID,
        entry_point="isaaclab.envs:ManagerBasedRLEnv",
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": "policies.route_walk.demo_task_cfg:HnGo2V0DemoRoughEnvCfg",
            "rsl_rl_cfg_entry_point": "policies.urdf_v0.env:HnGo2V0RoughPPORunnerCfg",
            "default_agent": "rsl_rl",
        },
    )
