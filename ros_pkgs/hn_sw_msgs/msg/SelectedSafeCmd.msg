# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 이동 명령. 명세의 SelectedCmd와 SafeCmd를 한 타입으로 씁니다(칸이 stop 하나만 달라서). QoS CONTROL, 50 Hz.
#   /hn/control/cmd_vel_selected : 제어권명령관리가 고른 명령 (IF-04). stop은 쓰지 않고 false
#   /hn/safety/cmd_vel_safe      : 안전 위협 관리가 허용한 명령. 보행 정책의 입력 (IF-20)
# 좌표는 몸체 프레임(trunk, 명세의 base_link). 정해진 시간 안에 새 명령이 안 오면 받는 쪽은 정지합니다.
# 제어권명령관리의 입력: Auto는 Nav2의 표준 /cmd_vel(geometry_msgs/Twist), Teleop은 /hn/control/teleop(TeleopCmd).
# Nav2 /cmd_vel을 보행 정책이 직접 받지 않습니다. 모든 이동 명령은 이 메시지로 안전 위협 관리를 거칩니다(명세 2.3).

std_msgs/Header header
float32 vx     # m/s
float32 vy     # m/s
float32 wz     # rad/s
ControlMode mode
bool stop      # true면 속도와 상관없이 정지 (cmd_vel_safe에서 위험 시)
