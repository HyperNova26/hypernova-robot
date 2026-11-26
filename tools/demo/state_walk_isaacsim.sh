#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# G-006 시나리오 1/3 (Isaac Sim): 출발지에서 목적지까지 정상 보행. 판정기만 붙여 상태(INITIALIZING -> STANDING -> WALKING)를 기록하고 고장은 넣지 않습니다.
# 사용: ./tools/demo/state_walk_isaacsim.sh   (저장소 최상위의 데스크톱 터미널에서, 인자 없음. 값을 바꾸려면 아래 하이퍼파라미터 블록만 고치십시오. 컨테이너 hn:sim을 자동으로 씁니다)
# 시뮬레이터 창이 뜨고 실시간 속도로 진행합니다. 판정 상태는 별도의 작은 창 'Locomotion state (G-006)'에 표시됩니다.
# 경로를 끝까지 걷는 데 시뮬레이션 시간으로 약 6~7분이 걸립니다(창 모드는 실시간이라 같은 시간이 걸리고, 창 없는 모드로 바꾸면 MuJoCo 약 1분, Isaac 약 5분). 요약에 FALLEN/STALE 오탐 0프레임 검사가 나옵니다.
# 판정 기록은 JSONL로 컨테이너 /data/state_logger/(호스트 ~/hypernova-data/state_logger/)에 남습니다.
set -euo pipefail

# ======================== 하이퍼파라미터 (여기만 고치십시오) ========================
WINDOW=1                 # 1: 시뮬레이터 창이 뜸(실시간 속도, 데스크톱 터미널에서) / 0: 창 없이 빠르게(원격 접속·자동 검증용)
ROUTE=A                   # 걷는 경로 이름(policies/urdf_v0/routes/pair360_demo.yaml). none이면 경로 없이 고정 명령으로 걷습니다
STAND_S=5                 # 시작 후 이 시간 [s] 동안 속도 명령을 0으로 해서 서 있다가 걷기 시작(STANDING 확인). 0이면 바로 걷고, 0이 아니면 3 이상. 도착 시간이 이만큼 늦어집니다
UNTIL=""                  # 이 시뮬레이션 시간 [s]에 끝냅니다. 비우면 목적지에 도착할 때까지
EXIT_ON_ARRIVAL=1         # 1: 목적지에 도착하면 요약을 내고 끝냄 / 0: 도착한 뒤에도 창을 유지(창을 닫거나 Ctrl+C로 종료하면 요약이 나옴)
ROS_TOPIC=""              # 비우면 ROS로 발행하지 않음. 예: /locomotion/status  (다른 터미널: ./docker/hn sim ros2 topic echo /locomotion/status)
ROS_LOCAL=1               # ROS_TOPIC을 쓸 때: 1이면 이 PC 안에서만 보임(같은 ROS_DOMAIN_ID의 다른 PC에 시험용 FALLEN이 퍼지지 않게), 0이면 네트워크 전체
# =================================================================================

ARGS=()
[ -n "$UNTIL" ] && ARGS+=(--until "$UNTIL")
[ "$STAND_S" != 0 ] && ARGS+=(--stand-s "$STAND_S")
export EXIT_ON_ARRIVAL
if [ -n "$ROS_TOPIC" ]; then
  ARGS+=(--ros-topic "$ROS_TOPIC")
  [ "$WINDOW" = 1 ] || ARGS+=(--realtime)   # 창 없는 모드는 실시간보다 빨라서, ROS로 볼 때만 실시간(50 Hz)으로 늦춥니다
  export ROS_LOCAL
fi
export ROUTE HEADLESS=$((1 - WINDOW))
exec "$(dirname "${BASH_SOURCE[0]}")/_state_run.sh" isaacsim baseline --label walk "${ARGS[@]}"
