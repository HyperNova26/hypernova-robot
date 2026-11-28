# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 실패·중단 사유 (인터페이스 명세 3.1). 프로그램은 code로 분기하고, 화면에는 message를 보여 줍니다.
# 사유가 없으면 둘 다 빈 문자열입니다.

string code     # 예: "MISSION_ROUTE_UNREACHABLE". 목록은 docs/interfaces/sw-contract.md
string message  # 화면 표시용 설명 문장
