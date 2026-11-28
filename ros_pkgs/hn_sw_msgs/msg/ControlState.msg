# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 현재 모드와 조종권 (IF-02, IF-03). 토픽 /hn/control/state, QoS STATE, 변경 시 + 1 Hz.

uint8 SOURCE_NONE = 0
uint8 SOURCE_AUTO = 1
uint8 SOURCE_TELEOP = 2

std_msgs/Header header
ControlMode mode
string owner_client_id        # 조종권을 가진 앱. 없으면 빈 문자열
uint8 command_source          # SOURCE_*. 지금 이동 명령을 내는 쪽
string last_request_id
CommandStatus last_request_status
Reason reason
