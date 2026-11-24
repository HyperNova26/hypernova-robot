# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 점검 결과 하나 (IF-17). 토픽 /hn/inspection/detection, QoS STATE(depth 20), 발생 시.
# AICV 점검 모델 → 이벤트점검관리. header.stamp = 촬영 시각, header.frame_id = 지도 프레임(pair360_map).
# 기본값 0 = UNKNOWN. 채우지 않은 결과가 '이상 없음'으로 읽히지 않게 하려는 것입니다.
# 이상 유형 목록과 낮은 신뢰도 처리 기준은 AICV팀과 정할 항목이라 문자열로 둡니다.

uint8 UNKNOWN = 0   # 판정하지 못함
uint8 NORMAL = 1    # 이상 없음
uint8 ANOMALY = 2   # 이상 있음. anomaly_type에 유형

std_msgs/Header header
string mission_id
string target_id            # 지도관리의 점검 대상 ID. 대상 밖에서 찾은 것이면 빈 문자열
uint8 result
string anomaly_type         # 예: "door_open", "fallen_object". NORMAL이면 빈 문자열
float32 confidence          # 0~1. 모르면 NaN
geometry_msgs/Point position
string image_url
string detector             # 모델 이름과 버전 (기록용, R-19)
