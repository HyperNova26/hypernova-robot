#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# G-006 시나리오 2/3 (MuJoCo): 걷다가 주저앉기. AT초에 정책 출력을 주저앉는 자세(thigh/calf 접기)로 바꿔 로봇이 그 자리에 주저앉고, 판정기가 FALLEN을 내는지 봅니다.
# 사용: ./tools/demo/state_collapse_mujoco.sh   (저장소 최상위의 데스크톱 터미널에서, 인자 없음. 값을 바꾸려면 아래 하이퍼파라미터 블록만 고치십시오. 컨테이너 hn:sim을 자동으로 씁니다)
# 시뮬레이터 창이 뜨고 실시간 속도로 진행합니다. 판정 상태는 MuJoCo 창 왼쪽 위 글자(색은 상태별: 회색 INIT, 파랑 STANDING, 초록 WALKING, 빨강 FALLEN)로 표시됩니다.
# 요약에 FALLEN 판정, 고장 후 판정까지 시간, FALLEN 유지 시간 검사가 나옵니다.
# 판정 기록은 JSONL로 컨테이너 /data/state_logger/(호스트 ~/hypernova-data/state_logger/)에 남습니다.
set -euo pipefail

# ======================== 하이퍼파라미터 (여기만 고치십시오) ========================
WINDOW=1                 # 1: 시뮬레이터 창이 뜸(실시간 속도, 데스크톱 터미널에서) / 0: 창 없이 빠르게(원격 접속·자동 검증용)
ROUTE=A                   # 걷는 경로 이름. none이면 경로 없이 고정 명령으로 걷습니다
AT=8                      # 주저앉기 시작하는 시뮬레이션 시간 [s]
UNTIL=16                  # 이 시뮬레이션 시간 [s]에 끝냅니다(AT보다 4초 이상 뒤를 권장: FALLEN 판정과 유지를 보려면)
THIGH=1.6                 # 주저앉는 자세의 모든 thigh 목표 [rad]
CALF=-2.7                 # 주저앉는 자세의 모든 calf 목표 [rad]
ROS_TOPIC=""              # 비우면 ROS로 발행하지 않음. 예: /locomotion/status  (다른 터미널: ./docker/hn sim ros2 topic echo /locomotion/status)
ROS_LOCAL=1               # ROS_TOPIC을 쓸 때: 1이면 이 PC 안에서만 보임(같은 ROS_DOMAIN_ID의 다른 PC에 시험용 FALLEN이 퍼지지 않게), 0이면 네트워크 전체
# =================================================================================

ARGS=(--at "$AT" --until "$UNTIL" --collapse-thigh "$THIGH" --collapse-calf "$CALF")
if [ -n "$ROS_TOPIC" ]; then
  ARGS+=(--ros-topic "$ROS_TOPIC")
  [ "$WINDOW" = 1 ] || ARGS+=(--realtime)   # 창 없는 모드는 실시간보다 빨라서, ROS로 볼 때만 실시간(50 Hz)으로 늦춥니다
  export ROS_LOCAL
fi
export ROUTE HEADLESS=$((1 - WINDOW))
exec "$(dirname "${BASH_SOURCE[0]}")/_state_run.sh" mujoco collapse --label collapse "${ARGS[@]}"
