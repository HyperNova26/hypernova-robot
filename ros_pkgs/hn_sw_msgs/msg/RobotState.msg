# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 통합 기체 상태 (IF-10, 11, 22). 토픽 /hn/state/robot, QoS STATE, 20 Hz (앱에는 5 Hz).
# 항목마다 유효 여부가 붙습니다. 모르는 실수 값은 NaN입니다.

std_msgs/Header header
RunTarget run_target                  # 지금 명령이 가는 대상 (R-20)

geometry_msgs/Pose pose               # 지도 프레임(pair360_map) 기준 몸체(trunk) 위치·방향
Validity pose_validity                # localization_status가 TRACKING(1)이 아니거나 300 ms 넘게 안 오면 VALID가 아님. Auto 보류 판단은 이 칸으로 (R-13)
uint8 localization_status             # AICV hn_interfaces/LocalizationStatus.status 값 그대로. 0 찾는 중, 1 정상 추적, 2 불안정, 3 잃음(재위치추정 필요), 4·5 입력 지연·끊김

geometry_msgs/Twist twist             # 몸체 프레임(trunk) 기준 실제 속도
Validity twist_validity

float32 battery_ratio                 # 0~1
Validity battery_validity

bool motors_ok
Validity motors_validity

bool ready_to_walk                    # 보행 준비 완료 (R-01)
Reason not_ready_reason
