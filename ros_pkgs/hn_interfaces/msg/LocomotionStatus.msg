# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 보행 상태. 토픽 /locomotion/status, QoS reliable + transient_local + depth 1 (ADR-0004)
# 단위: m, deg, m/s, s. 모르는 값은 NaN

std_msgs/Header header  # stamp: 시스템 시간

uint8 CODE_INITIALIZING = 0
uint8 CODE_STANDING = 1
uint8 CODE_WALKING = 2
uint8 CODE_TILTING = 3
uint8 CODE_SLIPPING = 4     # 예약
uint8 CODE_FALLEN = 5
uint8 CODE_STALE_INPUT = 6  # 판정기 입력 끊김

uint8 SEVERITY_OK = 0
uint8 SEVERITY_WARN = 1
uint8 SEVERITY_ERROR = 2
uint8 SEVERITY_STALE = 3

uint8 code          # CODE_*
string state        # 상태 이름
uint8 severity      # SEVERITY_*
string reason
float32 since_s     # 이 상태가 된 뒤 경과 시간
string robot_id
float64 sim_time_s  # 시뮬레이션 시간(실기는 NaN)

float32 tilt_deg
float32 roll_deg
float32 pitch_deg
float32 speed_mps   # 수평 속도
float32 height_m    # 지면 위 몸통 높이
