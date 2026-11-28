# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 경유점 도착 알림 (IF-16). 토픽 /hn/mission/waypoint_event, 발생 시.

std_msgs/Header header
string mission_id
string waypoint_id
string[] target_ids
bool arrived
