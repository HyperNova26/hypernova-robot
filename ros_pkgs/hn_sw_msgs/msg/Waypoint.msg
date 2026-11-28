# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 경유점 하나. 좌표는 Route.header.frame_id(지도 프레임) 기준, 단위 m.

string waypoint_id         # 관제 앱이 만듦
geometry_msgs/Pose pose
float32 arrival_radius_m   # 이 반경 안에 들어오면 도착
bool required              # 필수 점검 지점이면 true. 보정 중에 빠지면 안 됨 (R-03)
string[] target_ids        # 이 지점에서 점검할 대상 (지도관리의 target_id)
