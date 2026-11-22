# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 장치 고장 상태 (IF-07). 토픽 /hn/device/fault, QoS STATE, 변경 시 + 10 Hz.
# 통신 단절(mcu_link)과 모터 Fault를 따로 구분합니다 (R-12, R-16).

uint8 LINK_UNKNOWN = 0
uint8 LINK_CONNECTED = 1
uint8 LINK_DISCONNECTED = 2

std_msgs/Header header
bool estop_pressed
uint8 mcu_link             # LINK_*
string[] joint_names
uint32[] motor_fault_codes # joint_names와 같은 순서. 0 = 정상
bool emergency             # 긴급 오류
Reason reason
