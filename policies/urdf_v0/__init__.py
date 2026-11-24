# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""hypernova_go2 v0(description/hn_v0_go2) 보행 과제.

robot.py는 ArticulationCfg, env.py는 과제(env, PPO runner) 설정입니다.
"""

# 과제 ID → (env.py의 env cfg 클래스, PPO runner cfg 클래스). register.py가 읽습니다.
TASKS = {
    "HN-Velocity-Flat-Go2v0": ("HnGo2V0FlatEnvCfg", "HnGo2V0FlatPPORunnerCfg"),
    "HN-Velocity-Rough-Go2v0": ("HnGo2V0RoughEnvCfg", "HnGo2V0RoughPPORunnerCfg"),
}
