# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 위치추정 상태. 토픽 /localization/status, QoS reliable + depth 10 (S-005 v0)
# 처리한 스캔마다 1개, 입력이 끊기면 INPUT_TIMEOUT 1개를 냅니다
# 단위: ms, m. 모르는 값은 NaN

std_msgs/Header header  # stamp: 그 스캔의 /localization/odometry와 같은 시각(INPUT_TIMEOUT은 발행 시각), frame_id: 지도 프레임

uint8 STATUS_ACQUIRING = 0      # 확정한 위치가 아직 없음(초기화 중이거나 거부 뒤 다시 확인 중)
uint8 STATUS_TRACKING = 1       # 위치를 /localization/odometry와 /tf로 냄
uint8 STATUS_DEGRADED = 2       # 이 스캔은 거부함. 회복할 수 있음
uint8 STATUS_LOST = 3           # 새 초기 위치가 필요함
uint8 STATUS_STALE_INPUT = 4    # 결과가 너무 늦어 위치를 내지 않음
uint8 STATUS_INPUT_TIMEOUT = 5  # 새 입력이 없어 위치를 내지 않음

uint8 status  # STATUS_*

string status_text  # 추정기 자체 상태 이름(예: AMBIGUOUS_INITIALIZATION). status는 위 번호로 맞춘 값
bool pose_accepted  # 같은 stamp의 위치를 냈을 때만 true
string source       # 추정기 어댑터 이름: lidar_only, fastlio2, superlio
float32 latency_ms  # 입력 도착부터 결과까지
float32 fitness     # 지도 정합 inlier 비율 0~1
float32 rmse_m      # 지도 정합 RMSE
string detail_json  # 추정기 전용 값(JSON). 대시보드와 앱은 이 값에 의존하지 않습니다
