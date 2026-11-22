# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 순찰 경로 (IF-01, IF-15). header.frame_id = "map".
# 보정될 때마다 revision이 올라가고, 승인한 revision만 실행합니다 (R-04, R-05).

std_msgs/Header header
string route_id
uint32 revision
string map_id
string map_version
Waypoint[] waypoints   # 방문 순서대로
