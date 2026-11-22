# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 보행 정책이 낸 관절 목표 (IF-20). 토픽 /hn/policy/joint_targets, QoS CONTROL, 50 Hz.
# 배열은 모두 name과 같은 길이·같은 순서입니다. 순서를 숫자로 가정하지 말고 name으로 확인합니다
# (정책은 hip×4 → thigh×4 → calf×4, 명세는 다리별 순서라 서로 다름).

std_msgs/Header header
string[] name        # 예: "FL_hip_joint"
float32[] position   # rad
float32[] velocity   # rad/s
float32[] kp         # N·m/rad
float32[] kd         # N·m·s/rad
float32[] effort     # N·m (feedforward 토크)
