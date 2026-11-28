# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 안전 검사를 통과한 관절 명령 (IF-21). 토픽 /hn/safety/joint_cmd, QoS CONTROL, 50 Hz.
# 장치연동은 이 토픽으로만 MCU 명령을 만듭니다.
# 기본값 0 = MODE_DAMP. ACTIVE를 명시해야만 관절 목표를 따릅니다(채우지 않은 명령으로 움직이지 않게).
# 배열 규칙은 JointTargets와 같습니다.

uint8 MODE_DAMP = 0     # 감쇠 정지
uint8 MODE_HOLD = 1     # 현재 자세 유지
uint8 MODE_CUT = 2      # 토크 차단
uint8 MODE_ACTIVE = 3   # 관절 목표 추종

std_msgs/Header header
uint8 mode
string[] name
float32[] position   # rad
float32[] velocity   # rad/s
float32[] kp         # N·m/rad
float32[] kd         # N·m·s/rad
float32[] effort     # N·m
Reason reason        # 정지·대기 사유
