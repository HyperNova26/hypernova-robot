# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 상태 값의 유효 여부 (인터페이스 명세 3.1).
# 기본값 0을 UNAVAILABLE로 둡니다. 채우지 않은 값이 '정상'으로 읽히지 않게 하려는 것입니다.

uint8 UNAVAILABLE = 0  # 값 없음
uint8 VALID = 1
uint8 STALE = 2        # 허용 시간보다 오래됨. 판단에 쓰지 않음
uint8 INVALID = 3      # 범위 밖이거나 형식 오류

uint8 value
