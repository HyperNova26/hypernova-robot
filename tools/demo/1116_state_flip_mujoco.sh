#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# G-006 시나리오 3/3 (MuJoCo): 걷다가 옆으로 돌아서 넘어지기. AT초에 몸통 roll(로봇 기준 좌우 회전) 각속도를 한 번 더해 옆으로 뒤집고, 판정기가 FALLEN을 내는지 봅니다.
# 사용: ./tools/demo/1116_state_flip_mujoco.sh   (저장소 최상위의 데스크톱 터미널에서, 인자 없음. 값을 바꾸려면 아래 하이퍼파라미터 블록만 고치십시오. 컨테이너 hn:sim을 자동으로 씁니다)
# 시뮬레이터 창이 뜨고 실시간 속도로 진행합니다. 판정 상태는 MuJoCo 창 왼쪽 위 글자(색은 상태별: 회색 INIT, 파랑 STANDING, 초록 WALKING, 빨강 FALLEN)로 표시됩니다.
# 충격 크기 FLIP_RATE: 너무 작으면 로봇이 버티고 일어나고, 너무 크면 한 바퀴 돌아 다시 발로 섭니다(그러면 FALLEN이 풀림).
#   경로 A, AT=8에서 직접 돌려 본 값: 26~28은 세 시뮬레이터 모두 누운 채 FALLEN 유지 / 24는 Isaac Lab에서 버텨 일어남 / 30은 MuJoCo에서 한 바퀴 돌아 일어남.
# 요약에 FALLEN 판정, 고장 후 판정까지 시간, FALLEN 유지(또는 스스로 복구한 뒤 해제) 검사가 나옵니다.
# 판정 기록은 JSONL로 컨테이너 /data/state_logger/(호스트 ~/hypernova-data/state_logger/)에 남습니다.
set -euo pipefail

# ======================== 하이퍼파라미터 (여기만 고치십시오) ========================
WINDOW=1                 # 1: 시뮬레이터 창이 뜸(실시간 속도, 데스크톱 터미널에서) / 0: 창 없이 빠르게(원격 접속·자동 검증용)
ROUTE=A                   # 걷는 경로 이름. none이면 경로 없이 고정 명령으로 걷습니다
AT=8                      # 충격을 주는 시뮬레이션 시간 [s]
UNTIL=18                  # 이 시뮬레이션 시간 [s]에 끝냅니다
FLIP_RATE=27              # 몸통 x축(roll) 각속도 충격 [rad/s]. 부호를 바꾸면 반대쪽(왼쪽/오른쪽)으로 넘어집니다
ROS_TOPIC=""              # 비우면 ROS로 발행하지 않음. 예: /locomotion/status  (다른 터미널: ./docker/hn sim ros2 topic echo /locomotion/status)
ROS_LOCAL=1               # ROS_TOPIC을 쓸 때: 1이면 이 PC 안에서만 보임(같은 ROS_DOMAIN_ID의 다른 PC에 시험용 FALLEN이 퍼지지 않게), 0이면 네트워크 전체
# =================================================================================

ARGS=(--at "$AT" --until "$UNTIL" "--flip-rate=$FLIP_RATE")
if [ -n "$ROS_TOPIC" ]; then
  ARGS+=(--ros-topic "$ROS_TOPIC")
  [ "$WINDOW" = 1 ] || ARGS+=(--realtime)   # 창 없는 모드는 실시간보다 빨라서, ROS로 볼 때만 실시간(50 Hz)으로 늦춥니다
  export ROS_LOCAL
fi
export ROUTE HEADLESS=$((1 - WINDOW))
exec "$(dirname "${BASH_SOURCE[0]}")/1116_state_run.sh" mujoco flip --label flip "${ARGS[@]}"
