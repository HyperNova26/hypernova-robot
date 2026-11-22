# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 임무 진행 상태 (IF-01). 토픽 /hn/mission/status, QoS STATE, 변경 시 + 2 Hz.

std_msgs/Header header
string mission_id
string route_id
uint32 revision
CommandStatus status
string current_waypoint_id
string[] visited_waypoint_ids
string[] remaining_waypoint_ids
float32 progress       # 0~1. 모르면 NaN
Reason reason          # 보류·실패·종료 사유
