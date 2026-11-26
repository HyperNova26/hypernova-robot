# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""HYPER v1(description/hn_v1_hyper) 보행 과제.

robot.py는 ArticulationCfg, env.py는 과제(env, PPO runner) 설정입니다.
Rough-Lidar가 배포용 학습 과제입니다. LiDAR 앞 약 0.63 m부터 보이는 LiDAR 기억 + 발끝 평면 height scan을
actor 입력으로 씁니다(policies/common/heightmap.py). Rough는 actor에 Isaac Lab 기본 height scan(GT)을 넣는
비교용 과제이며 배포하지 않습니다(2026-11-19 결정, 실기에서 같은 입력을 만들 수 없음).
"""

# 과제 ID → (env.py의 env cfg 클래스, PPO runner cfg 클래스). register.py가 읽습니다.
TASKS = {
    "HN-Velocity-Flat-HYPERv1": ("HnHyperV1FlatEnvCfg", "HnHyperV1FlatPPORunnerCfg"),
    # 비교용(actor height scan = GT), 배포 안 함
    "HN-Velocity-Rough-HYPERv1": ("HnHyperV1RoughEnvCfg", "HnHyperV1RoughPPORunnerCfg"),
    # actor height scan = LiDAR로 본 점의 기억 + 발끝 평면
    "HN-Velocity-Rough-HYPERv1-Lidar": ("HnHyperV1RoughLidarEnvCfg", "HnHyperV1RoughLidarPPORunnerCfg"),
}
