# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 점검 대상별 결과 (IF-16, R-19). 토픽 /hn/inspection/target_result, 발생 시.
# 기본값 0 = UNVISITED. 확인하지 않은 대상이 '점검 완료'로 읽히지 않게 하려는 것입니다.

uint8 UNVISITED = 0          # 미방문
uint8 ARRIVED_UNCHECKED = 1  # 도착했으나 미확인
uint8 CHECKED = 2            # 점검 완료

std_msgs/Header header
string mission_id
string target_id
uint8 result
Reason reason   # 미완료 사유
