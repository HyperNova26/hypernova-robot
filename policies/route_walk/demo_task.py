# SPDX-License-Identifier: Apache-2.0
"""PAIR360 데모 지형 위 Rough task의 gym 등록(로봇 버전별). Isaac Lab을 import하지 않으므로 Kit 실행 전에 불러도 안전합니다.

환경 설정 클래스는 demo_task_cfg.py에 있고, gym이 문자열 entry point로 Kit 실행 뒤에 불러옵니다(저장소 루트가 import 경로에 있어야 합니다).
데이터(지형 USD)는 컨테이너의 /data(= 호스트 HN_DATA_DIR) 아래에 있어야 합니다. 다른 위치면 환경 변수 HN_DEMO_DATA로 바꿉니다.

task ID는 로봇 버전과 1:1입니다. 어느 것을 쓸지는 재생기의 --task가 정하고(tools/demo/run_route.sh의 POLICY=v0|v1),
정책 yaml·체크포인트·URDF는 같은 버전의 것을 써야 합니다.
"""
import gymnasium as gym

# task ID -> (env cfg entry point, PPO runner cfg entry point). runner cfg는 gym 등록에만 필요하고 재생에는 쓰지 않습니다.
TASKS = {
    "HN-Velocity-Demo-Rough-Go2v0": (
        "policies.route_walk.demo_task_cfg:HnGo2V0DemoRoughEnvCfg",
        "policies.urdf_v0.env:HnGo2V0RoughPPORunnerCfg",
    ),
    "HN-Velocity-Demo-Rough-HYPERv1": (
        "policies.route_walk.demo_task_cfg:HnHyperV1DemoRoughEnvCfg",
        "policies.urdf_v1.env:HnHyperV1RoughPPORunnerCfg",
    ),
}
TASK_ID = "HN-Velocity-Demo-Rough-Go2v0"   # 이전 호환(v0)


def register() -> None:
    for task_id, (env_cfg, runner_cfg) in TASKS.items():
        if task_id in gym.registry:
            continue
        gym.register(
            id=task_id,
            entry_point="isaaclab.envs:ManagerBasedRLEnv",
            disable_env_checker=True,
            kwargs={
                "env_cfg_entry_point": env_cfg,
                "rsl_rl_cfg_entry_point": runner_cfg,
                "default_agent": "rsl_rl",
            },
        )
