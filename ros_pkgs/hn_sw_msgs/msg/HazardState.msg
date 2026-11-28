# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 현재 위험 목록 (IF-05, IF-06). 토픽 /hn/safety/hazard, QoS STATE, 변경 시 + 1 Hz.
# 위험이 사라져도 자동으로 재출발하지 않습니다 (R-12).

std_msgs/Header header
Hazard[] hazards
bool motion_blocked            # true면 일반 이동 차단 중
bool resumable                 # 복구 조건을 모두 충족함. 앱은 이때만 재개 버튼을 켭니다. 재개는 운영자 요청으로만 (R-12)
string[] recovery_conditions   # 다시 움직이려면 충족해야 할 조건 (화면 표시용)
