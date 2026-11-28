# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 제어권명령관리가 고른 이동 명령 (IF-04). 토픽 /hn/control/cmd_vel_selected, QoS CONTROL, 50 Hz.
# 좌표는 몸체 프레임(trunk, 명세의 base_link). 정해진 시간 안에 새 명령이 안 오면 안전 위협 관리는 정지합니다.
# 입력: Auto는 Nav2 속도 출력(/cmd_vel_nav, geometry_msgs/Twist), Teleop은 /hn/control/teleop(TeleopCmd).
# 보행 정책의 입력은 AICV 인터페이스대로 표준 /cmd_vel(geometry_msgs/Twist)이고, 안전 위협 관리만 냅니다(IF-20).
# 그래서 Nav2 출력은 /cmd_vel_nav로 remap합니다. 모든 이동 명령은 안전 위협 관리를 거칩니다(명세 2.3).

std_msgs/Header header
float32 vx     # m/s
float32 vy     # m/s
float32 wz     # rad/s
ControlMode mode
bool stop      # true면 속도와 상관없이 정지 요청 (PAUSED, REQUEST_STOP 등)
