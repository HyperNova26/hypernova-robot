# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 조이스틱 조종 입력 (IF-02). 토픽 /hn/control/teleop, QoS STREAM, 20 Hz.
# 좌표 base_link (x 전방, y 좌측, z 상방). 카메라는 쓰지 않습니다.
# deadman이 false이거나 입력이 끊기면 받는 쪽은 속도 0으로 처리합니다 (R-06).

std_msgs/Header header
string client_id   # 조종권을 가진 앱만 받아들임
float32 vx         # m/s
float32 vy         # m/s
float32 wz         # rad/s
bool deadman       # 조종 버튼을 누르고 있으면 true
