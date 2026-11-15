#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# 상태 로거(G-006) 시나리오 실행 엔진(내부용): 경로 걷기 재생기를 감싸 도중에 고장을 넣고 판정 결과를 JSONL로 기록합니다(컨테이너 hn:sim).
# 일반 사용은 이 파일이 아니라 state_<walk|collapse|flip>_<mujoco|isaacsim|isaaclab>.sh 9개입니다(값은 각 파일 위쪽 하이퍼파라미터 블록).
# 이 엔진을 직접 부르면 stale 시나리오와 모든 하네스 옵션을 쓸 수 있습니다.
#
# 사용법 (저장소 최상위에서)
#   ./tools/demo/_state_run.sh <mujoco|isaaclab|isaacsim> <시나리오> [하네스 옵션...] [-- 재생기 옵션...]
#   시나리오: baseline | stale | collapse | flip   (설명은 policies/route_walk/state_scenarios.py, 세 시뮬레이터 모두 지원)
# 예
#   ROUTE=none ./tools/demo/_state_run.sh mujoco baseline --until 20 --expect stand -- --vmax 0   # 정지 20초
#   ./tools/demo/_state_run.sh mujoco baseline                                                  # 경로 A 전 구간(오탐 확인)
#   ./tools/demo/_state_run.sh isaaclab collapse --at 20                                        # Isaac Lab, 20초에 주저앉힘
#   ./tools/demo/_state_run.sh isaacsim stale --at 20 --gap 3                                   # Isaac Sim, 20초부터 3초 입력 끊김
# 환경 변수: ROUTE(기본 A, none이면 경로 없이 고정 명령), HEADLESS(기본 1), EXIT_ON_ARRIVAL(기본 1: baseline 경로 보행은 도착하면 끝냄), LOG(기록 파일, 기본 /data/state_logger/<시각>_<sim>_<시나리오>.jsonl),
#   ROS_LOCAL(1이면 ROS 탐색을 이 PC로 제한: 같은 ROS_DOMAIN_ID를 쓰는 다른 PC에 시험 토픽이 보이지 않게)
# 눈으로 확인하기(창 모드는 데스크톱 터미널에서, 실시간 속도)
#   HEADLESS=0 ./tools/demo/_state_run.sh isaacsim collapse --at 10 --until 20   # Isaac Sim 창 + 판정 상태 작은 창
#   HEADLESS=0 ./tools/demo/_state_run.sh isaaclab collapse --at 10 --until 20   # Isaac Lab 창 + 판정 상태 작은 창
#   HEADLESS=0 ./tools/demo/_state_run.sh mujoco collapse --at 8 --until 16   # MuJoCo 창 왼쪽 위에 판정 상태가 실시간 표시됨(실시간 속도, 데스크톱 터미널에서)
#   ./tools/demo/_state_run.sh mujoco collapse --at 6 --until 14 --ros-topic /locomotion/status --realtime   # 상태를 ROS 토픽으로 발행(다른 터미널: ./docker/hn sim ros2 topic echo /locomotion/status)
# 필요한 파일은 tools/demo/run_route.sh와 같습니다(./tools/demo/run_route.sh check). Isaac 모드의 창(HEADLESS=0)에는 재생기의 기존 창과 함께 판정 상태를 보여 주는 작은 창('Locomotion state')이 뜹니다.
set -euo pipefail

SIM="${1:-}"
SCEN="${2:-}"
if [ -z "$SIM" ] || [ -z "$SCEN" ]; then
  sed -n '3,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi
shift 2
H_ARGS=(); P_ARGS=()
while [ $# -gt 0 ]; do   # `--` 앞은 하네스 옵션, 뒤는 재생기 옵션
  if [ "$1" = "--" ]; then shift; P_ARGS=("$@"); break; fi
  H_ARGS+=("$1"); shift
done
ROUTE="${ROUTE:-A}"
HEADLESS="${HEADLESS:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${HN_REPO:-}"
if [ -z "$REPO" ]; then
  top="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$top" ] && [ -x "$top/docker/hn" ]; then REPO="$top"; else REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"; fi
fi
DATA_HOST="${HN_DATA_DIR:-}"
if [ -z "$DATA_HOST" ] && [ -f "$REPO/docker/.env.local" ]; then
  DATA_HOST="$(sed -n 's/^HN_DATA_DIR=//p' "$REPO/docker/.env.local" | tail -1)"
fi
DATA_HOST="${DATA_HOST:-$HOME/hypernova-data}"
D_HOST="$DATA_HOST/pair360_demo_frame"; D_CTR=/data/pair360_demo_frame
CODE_CTR=/workspace/hypernova/policies/route_walk
YAML_CTR=/workspace/hypernova/policies/urdf_v0/policy_io.yaml
ROUTES_CTR=/workspace/hypernova/policies/urdf_v0/routes/pair360_demo.yaml
URDF_CTR=/workspace/hypernova/description/hn_v0_go2/hypernova_go2.urdf
ACTOR_CTR="$D_CTR/policy/actor_model_3849.npz"
SCENE_HOST="${HN_ISAACSIM_SCENE:-$D_HOST/isaac/scene_demo_v0.usda}"
SCENE_CTR="${HN_ISAACSIM_SCENE_CTR:-$D_CTR/isaac/scene_demo_v0.usda}"
TASK=HN-Velocity-Demo-Rough-Go2v0

case "$SCEN" in baseline|stale|collapse|flip) ;; *) echo "알 수 없는 시나리오: $SCEN" >&2; exit 2 ;; esac
case "$SIM" in mujoco|isaaclab|isaacsim) ;; *) echo "알 수 없는 시뮬레이터: $SIM (mujoco|isaaclab|isaacsim)" >&2; exit 2 ;; esac

NEED=("$D_HOST/policy/actor_model_3849.npz" "$REPO/description/hn_v0_go2/meshes/base.stl")
case "$SIM" in
  mujoco)   NEED+=("$D_HOST/mujoco/scene.xml" "$D_HOST/mujoco/hfields") ;;
  isaaclab) NEED+=("$D_HOST/ground_grid_demo.npz" "$D_HOST/isaac/ground_collision_demo.usdc") ;;
  isaacsim) NEED+=("$D_HOST/ground_grid_demo.npz" "$D_HOST/isaac/ground_collision_demo.usdc" "$SCENE_HOST") ;;
esac
MISSING=0
for f in "${NEED[@]}"; do
  [ -e "$f" ] || { echo "[_state_run] 없음: $f" >&2; MISSING=1; }
done
[ "$MISSING" = 0 ] || { echo "[_state_run] 필요한 파일이 없습니다. ./tools/demo/run_route.sh check 로 준비 상태를 확인하십시오." >&2; exit 2; }

mkdir -p "$DATA_HOST/state_logger"
LOG_CTR="${LOG:-/data/state_logger/$(date +%Y%m%d_%H%M%S)_${SIM}_${SCEN}.jsonl}"
ENVP=()
[ "${ROS_LOCAL:-0}" = 1 ] && ENVP=(env ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST)
# 경로 전 구간을 걷는 baseline은 도착하면 끝냅니다(고장 시나리오는 --until 또는 재생기가 끝냄)
ARRIVE=0
[ "$SCEN" = baseline ] && [ "$ROUTE" != none ] && [ "${EXIT_ON_ARRIVAL:-1}" = 1 ] && ARRIVE=1

cd "$REPO"
case "$SIM" in
  mujoco)
    HL=(); RT=()
    [ "$HEADLESS" = 1 ] && HL=(--headless)
    [ "$ARRIVE" = 1 ] && HL+=(--exit-on-arrival)
    [ "$ROUTE" != none ] && RT=(--route-file "$ROUTES_CTR" --route "$ROUTE")
    exec ./docker/hn sim "${ENVP[@]}" /opt/hn-venv/bin/python "$CODE_CTR/state_scenarios.py" \
      --player play_mujoco.py --scenario "$SCEN" --log "$LOG_CTR" "${H_ARGS[@]}" ::: \
      --yaml "$YAML_CTR" --actor "$ACTOR_CTR" --scene "$D_CTR/mujoco/scene.xml" --urdf "$URDF_CTR" \
      "${RT[@]}" "${HL[@]}" "${P_ARGS[@]}" ;;
  isaacsim)
    HL=(); RT=()
    [ "$HEADLESS" = 1 ] && HL=(--headless)
    [ "$ARRIVE" = 1 ] && HL+=(--exit-on-arrival)
    [ "$ROUTE" != none ] && RT=("--route-file=$ROUTES_CTR" "--route=$ROUTE")
    exec ./docker/hn sim "${ENVP[@]}" /workspace/isaaclab/isaaclab.sh -p "$CODE_CTR/state_scenarios.py" \
      --player play_isaacsim.py --scenario "$SCEN" --log "$LOG_CTR" "${H_ARGS[@]}" ::: \
      "--yaml=$YAML_CTR" "--actor=$ACTOR_CTR" "--scene=$SCENE_CTR" "--ground-grid=$D_CTR/ground_grid_demo.npz" \
      "${RT[@]}" "${HL[@]}" "${P_ARGS[@]}" ;;
  isaaclab)
    VIZ=kit; REAL=1; RT=(); EX=()
    [ "$HEADLESS" = 1 ] && { VIZ=none; REAL=0; }
    [ "$ARRIVE" = 1 ] && EX=(--hn-exit-on-arrival=1)
    [ "$ROUTE" != none ] && RT=("--hn-route-file=$ROUTES_CTR" "--hn-route=$ROUTE")
    exec ./docker/hn sim "${ENVP[@]}" /workspace/isaaclab/isaaclab.sh -p "$CODE_CTR/state_scenarios.py" \
      --player play_isaaclab.py --scenario "$SCEN" --log "$LOG_CTR" "${H_ARGS[@]}" ::: \
      --task "$TASK" --num_envs 1 "--hn-yaml=$YAML_CTR" "--hn-actor=$ACTOR_CTR" "--hn-ground=$D_CTR/ground_grid_demo.npz" \
      "${RT[@]}" --hn-follow=2 --hn-cam=5,-5,3.5 "--hn-realtime=$REAL" "${EX[@]}" \
      "${P_ARGS[@]}" --visualizer "$VIZ" physics=isaacsim_physx ;;
esac
