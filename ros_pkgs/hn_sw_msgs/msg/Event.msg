# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 이상 이벤트 (IF-18). 토픽 /hn/event/stream, QoS STATE, 발생 시.
# header.stamp = 발생 시각, header.frame_id = 지도 프레임(현재 `pair360_map`, ADR-0005 Proposed. 명세의 `map`). 재전송해도 event_id가 같으면 한 건입니다 (R-18).

std_msgs/Header header
string event_id
string mission_id
string type             # 이상 유형
string source           # 출처 (예: "inspection", "safety", "poc_preset")
geometry_msgs/Point position
float32 confidence      # 0~1. 모르면 NaN
string image_url
bool acknowledged       # 운영자 확인 여부
