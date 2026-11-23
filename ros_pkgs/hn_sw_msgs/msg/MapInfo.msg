# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 지도 정보 (IF-13, IF-14). 토픽 /hn/map/info, QoS STATE, 변경 시. header.frame_id = 지도 프레임(현재 `pair360_map`, ADR-0005 Proposed. 명세의 `map`).
# 2D 격자 지도는 Nav2와 같이 표준 nav_msgs/OccupancyGrid로 /map에 냅니다.
# 지도 이미지 같은 큰 데이터는 HTTP로 받고 여기에는 주소만 담습니다.

std_msgs/Header header
string map_id
string map_version
string image_url
geometry_msgs/Polygon[] no_go_zones     # 통행 불가 구역
string[] target_ids                     # 점검 대상
geometry_msgs/Point[] target_positions  # target_ids와 같은 순서
