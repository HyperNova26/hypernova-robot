# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 통합 기체 상태 (IF-10, 11, 22). 토픽 /hn/state/robot, QoS STATE, 20 Hz (앱에는 5 Hz).
# 항목마다 유효 여부가 붙습니다. 모르는 실수 값은 NaN입니다.

std_msgs/Header header
RunTarget run_target                  # 지금 명령이 가는 대상 (R-20)

geometry_msgs/Pose pose               # 지도 프레임(pair360_map) 기준 몸체(trunk) 위치·방향
Validity pose_validity
float32 localization_confidence       # 0~1. AICV /localization/status의 fitness(지도 정합 비율). 없으면 NaN

geometry_msgs/Twist twist             # 몸체 프레임(trunk) 기준 실제 속도
Validity twist_validity

float32 battery_ratio                 # 0~1
Validity battery_validity

bool motors_ok
Validity motors_validity

bool ready_to_walk                    # 보행 준비 완료 (R-01)
Reason not_ready_reason
