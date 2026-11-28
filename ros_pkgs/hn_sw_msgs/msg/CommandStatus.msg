# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 요청 처리 상태 (인터페이스 명세 3.3).
# 기본값 0 = NONE(아직 요청 없음)은 명세에 없던 값을 추가한 것입니다. 채우지 않은 상태가 '접수됨'으로 읽히지 않게 하려는 것입니다.

uint8 NONE = 0
uint8 RECEIVED = 1
uint8 ACCEPTED = 2
uint8 EXECUTING = 3
uint8 HELD = 4       # 보류 (Teleop 전환, 일시정지 등)
uint8 SUCCEEDED = 5
uint8 FAILED = 6
uint8 REJECTED = 7
uint8 CANCELED = 8

uint8 value
