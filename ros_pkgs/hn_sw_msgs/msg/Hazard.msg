# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 위험 하나 (HazardState, SafetyVerdict에서 씀). 번호 목록은 초안이며 팀 합의 전입니다.

uint8 TYPE_NONE = 0
uint8 TYPE_ESTOP = 1              # E-stop 눌림
uint8 TYPE_DEVICE_FAULT = 2       # 모터·MCU 고장
uint8 TYPE_MCU_LINK_LOSS = 3      # MCU 통신 단절. 정지합니다
uint8 TYPE_FALL_RISK = 4          # 전도 위험. AICV /locomotion/status CODE_TILTING
uint8 TYPE_FALLEN = 5             # 넘어짐. CODE_FALLEN. 그쪽 상태가 풀려도 운영자 재개 전까지 유지
uint8 TYPE_LOCALIZATION_LOST = 6  # 위치 상실·신뢰도 낮음 (R-13)
uint8 TYPE_STATE_STALE = 7        # 필수 상태 값이 오래됨. CODE_STALE_INPUT도 여기
uint8 TYPE_JOINT_LIMIT = 8        # 관절 목표가 허용 범위 밖
uint8 TYPE_STALLED = 9            # 명령은 있는데 실제로 안 움직임 (R-10)
uint8 TYPE_LOW_BATTERY = 10
uint8 TYPE_APP_LINK_LOSS = 11     # 관제 앱 연결 끊김. Teleop은 정지, Auto는 일시정지 (R-16)

uint8 SEVERITY_INFO = 0
uint8 SEVERITY_WARN = 1
uint8 SEVERITY_ERROR = 2
uint8 SEVERITY_CRITICAL = 3

uint8 type
uint8 severity
float32 duration_s   # 이 위험이 이어진 시간
string cause         # 추정 원인 (화면 표시용)
