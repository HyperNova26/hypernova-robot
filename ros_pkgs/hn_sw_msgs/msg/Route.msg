# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 순찰 경로 (IF-01, IF-15). header.frame_id = 지도 프레임(현재 `pair360_map`, ADR-0005 Proposed. 명세의 `map`).
# 승인된 경로는 임무경로관리가 Nav2 표준 action(NavigateToPose 또는 FollowWaypoints)으로 넘깁니다.
# 보정될 때마다 revision이 올라가고, 승인한 revision만 실행합니다 (R-04, R-05).

std_msgs/Header header
string route_id
uint32 revision
string map_id
string map_version
Waypoint[] waypoints   # 방문 순서대로
