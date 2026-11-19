#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# PAIR360 데모 지형에서 팀원 정책으로 로봇이 경로를 걷는 것을 Isaac Lab, MuJoCo, Isaac Sim에서 재생합니다.
# 로봇·정책은 POLICY로 고릅니다: v1(기본) = HYPER v1 + Rough GT 정책 model_2998, v0 = Go2 v0 + model_3849.
#
# 사용법 (저장소 최상위에서)
#   POLICY=v0 ./tools/demo/run_route.sh mujoco    # v0(Go2) 로봇으로 같은 경로를 재생(비교·회귀용)
#   MJ_CALIB=0 ACT_DELAY=0 ./tools/demo/run_route.sh mujoco   # 시뮬레이터 보정을 모두 끔(기본은 켬. docs/development/sim-parity.md). 2026-11-15 이전 기록값 재현용
#   MAP=demo  ./tools/demo/run_route.sh mujoco    # 예전 데모 지형(데모 프레임)에서 재생(비교·회귀용). 기본 MAP=v3(PAIR360 mesh_v3)
#   ./tools/demo/run_route.sh check               # 필요한 파일이 있는지 점검
#   ./tools/demo/run_route.sh export              # 저장소 체크포인트에서 actor 가중치(.npz)를 만듭니다(컨테이너 hn:sim, 처음 한 번)
#   ./tools/demo/run_route.sh mujoco              # MuJoCo 창(컨테이너 hn:sim의 robot venv). 판정 상태 표시와 고장 주입 서비스가 함께 켜집니다(아래)
#   ./tools/demo/run_route.sh isaaclab            # Isaac Lab 창(컨테이너 hn:sim). 카메라가 로봇을 따라가며 줌 가능
#   ./tools/demo/run_route.sh isaacsim            # Isaac Sim 단독 창(컨테이너 hn:sim). 장면 USD는 아래 설명 참고
#   ROUTE=B ./tools/demo/run_route.sh mujoco      # 다른 경로(A: 스크린샷 그대로, B: 좁은 목을 피해 우회)
#   ./tools/demo/run_route.sh isaaclab --hn-vmax=0.4        # 뒤에 붙인 옵션은 그대로 해당 스크립트로 전달
#   HEADLESS=1 ./tools/demo/run_route.sh mujoco             # 창 없이 끝까지 걷고 결과만 출력(시험용)
#
# 상태 판정과 고장 주입(G-006). 기본으로 재생기를 시험 하네스 policies/route_walk/state_scenarios.py로 감싸서 실행합니다(STATE=0이면 하네스 없이 예전처럼)
#   ./tools/demo/run_route.sh mujoco              # 판정 상태를 화면·터미널에 표시, /locomotion/status·/clock 발행, 고장 주입 서비스 /sim/inject_fault
#   고장은 다른 터미널에서 컨테이너 셸(./docker/hn sim)을 열고 서비스를 직접 부릅니다. kind: collapse | flip | stale | tilt | push | clear | reset
#     ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: tilt}"
#     ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: tilt, magnitude: -40, duration_s: 5}"   # 왼쪽 40°, 5 s 뒤 자동으로 끝
#     ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: push, magnitude: 150, direction_deg: 90}" # 왼쪽으로 150 N, 0.2 s
#     ros2 topic echo /locomotion/status                                                                              # 판정 상태 보기
#   FAULT=collapse ./tools/demo/run_route.sh isaacsim        # 고장 예약: AT초(기본 8)에 넣고, 끝나면 요약과 PASS/FAIL 검사
#   FAULT=tilt AT=10 FAULT_S=5 HEADLESS=1 ./tools/demo/run_route.sh isaaclab   # 창 없이 자동 검사
#   HEADLESS=1 STAND_S=5 ./tools/demo/run_route.sh mujoco   # 고장 없이 경로 끝까지(오탐 검사). 처음 5 s는 서 있다가 출발
#   환경 변수: STATE(기본 1 = 하네스, 0이면 하네스 없이), FAULT(collapse|flip|stale|tilt|push), AT, FAULT_S(지속 s, 기본 stale 3·tilt 5·collapse 끝까지),
#     UNTIL(이 시뮬레이션 시간에 끝냄), STAND_S(처음 서 있는 시간, 0 또는 3 이상),
#     ROS(창 모드 기본 1, HEADLESS=1 기본 0. 창 없는 모드에서 1이면 실시간으로 늦춤), ROS_LOCAL(기본 1: ROS를 이 PC 안으로 제한),
#     ROS_DOMAIN(같은 PC에서 시뮬레이터를 둘 이상 띄울 때 서로 다른 ROS 도메인으로. 서비스를 부르는 셸도 export ROS_DOMAIN_ID=<같은 값>),
#     LOG(JSONL 기록, 기본 컨테이너 /data/state_logger/<시각>_<sim>_<고장>.jsonl), STATE_ARGS(하네스 옵션을 그대로 추가, 예: "--tilt-deg -50 --stamp sim")
#
# 필요한 것
#   - 로봇 mesh(Git 밖): python3 tools/description/fetch_go2_meshes.py --convert  (description/hn_v0_go2/meshes/)
#   - 데이터 폴더(HN_DATA_DIR, docker/.env.local) 안의 PAIR360 데모 자료(Git 밖): pair360_demo_frame/ 아래
#       ground_grid_demo.npz, mujoco/(scene.xml, hfields/), isaac/ground_collision_demo.usdc, policy/actor_model_3849.npz(export로 생성)
#   - ./docker/hn (hn:sim 이미지). 세 시뮬레이터 모두 컨테이너 안에서 실행합니다(MuJoCo는 /opt/hn-venv의 mujoco 3.12.0).
#     창을 띄우려면 호스트 데스크톱 세션의 터미널에서 실행합니다(DISPLAY가 컨테이너로 전달됨).
#   - Isaac Sim 단독(isaacsim) 모드의 장면 USD: pair360_demo_frame/isaac/scene_demo_v0.usda (환경 변수 HN_ISAACSIM_SCENE로 바꿉니다).
#     지형 + /World/Robot이 든 장면이고, 로봇은 Isaac Lab이 저장소 URDF를 변환해 /data/usd/hn_v0_go2/에 만든 USD를 참조합니다.
#     그래서 isaaclab 모드를 한 번 실행해 그 USD가 만들어진 뒤에 씁니다.
# 좌표는 지도를 따릅니다: MAP=v3은 pair360_map(docs/decisions/0005-pair360-map-frame.md), MAP=demo는 데모 프레임(0003). 단위 m.
set -euo pipefail

MODE="${1:-}"
[ $# -gt 0 ] && shift
ROUTE="${ROUTE:-A}"
HEADLESS="${HEADLESS:-0}"
FAULT="${FAULT:-}"
STATE="${STATE:-1}"
[ -n "$FAULT" ] && STATE=1
# 창 없는 모드는 ROS를 기본으로 끕니다(켜면 사람이 서비스를 부를 수 있게 실시간으로 늦춰 돌아서, 측정·자동 검사가 몇 배 느려짐)
if [ "$HEADLESS" = 1 ]; then ROS="${ROS:-0}"; else ROS="${ROS:-1}"; fi
ROS_LOCAL="${ROS_LOCAL:-1}"
ENVP=()   # 시뮬레이터의 ROS 탐색 범위. 같은 ROS_DOMAIN_ID를 쓰는 다른 PC에 시험용 FALLEN이 퍼지지 않게 기본은 이 PC 안(같은 PC의 다른 셸에서는 보임)
[ "$ROS_LOCAL" = 1 ] && ENVP=(env ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST)
# 같은 PC에서 시뮬레이터를 둘 이상 띄우면 /sim/inject_fault, /clock, /locomotion/status가 겹칩니다. ROS_DOMAIN=<0~101>로 서로 다른 도메인에 둡니다
# (서비스를 부르는 셸에서도 export ROS_DOMAIN_ID=<같은 값>). 비우면 docker/.env.local의 ROS_DOMAIN_ID를 씁니다
if [ -n "${ROS_DOMAIN:-}" ]; then
  [ ${#ENVP[@]} -eq 0 ] && ENVP=(env)
  ENVP+=("ROS_DOMAIN_ID=$ROS_DOMAIN")
fi

# ---- 저장소와 데이터 위치 -------------------------------------------------------------------------------------------
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
D_HOST="$DATA_HOST/pair360_demo_frame"       # 호스트에서 본 경로. 정책 가중치(.npz)와 예전 데모 지형이 여기에 있습니다
D_CTR=/data/pair360_demo_frame               # 컨테이너에서 본 경로(데이터 폴더는 /data로 마운트됨)

# ---- 지도 선택 ---------------------------------------------------------------------------------------------------------
# MAP=v3(기본): PAIR360 mesh_v3, pair360_map 좌표 그대로. tools/map/hfield_scene_import.py가 만든 파일을 씁니다.
# MAP=demo: 예전 데모 지형(데모 프레임). 비교·회귀용. 경로 yaml은 지도에 속하므로 지도와 함께 바뀝니다.
MAP="${MAP:-v3}"
case "$MAP" in
  v3)
    M_HOST="$DATA_HOST/pair360_map_v3/derived"; M_CTR=/data/pair360_map_v3/derived
    GRID_NAME=ground_grid.npz
    MJ_SCENE_REL=../src/PAIR360-Go2-mesh_v3/scene/scene.xml            # 지형 팀이 준 scene.xml을 그대로 씁니다
    TERRAIN_REL=isaac/terrain_ground.usdc; OBST_REL=isaac/terrain_obstacles.usdc; SCENE_FMT="$M_HOST/isaac/scene_%s.usda"; SCENE_FMT_CTR="$M_CTR/isaac/scene_%s.usda"
    ROUTES_HOST="$REPO/sim_scenes/pair360_map_v3/routes.yaml"; ROUTES_CTR=/workspace/hypernova/sim_scenes/pair360_map_v3/routes.yaml
    MAP_HINT="컨테이너에서: /opt/hn-venv/bin/python tools/map/hfield_scene_import.py (사용법은 그 파일 머리말)" ;;
  demo)
    M_HOST="$D_HOST"; M_CTR="$D_CTR"
    GRID_NAME=ground_grid_demo.npz
    MJ_SCENE_REL=mujoco/scene.xml
    TERRAIN_REL=isaac/ground_collision_demo.usdc; OBST_REL=""; SCENE_FMT="$D_HOST/isaac/scene_demo_%s.usda"; SCENE_FMT_CTR="$D_CTR/isaac/scene_demo_%s.usda"
    ROUTES_HOST="$REPO/policies/urdf_v0/routes/pair360_demo.yaml"; ROUTES_CTR=/workspace/hypernova/policies/urdf_v0/routes/pair360_demo.yaml
    MAP_HINT="예전 데모 자료(Git 밖)" ;;
  *)
    # 합성 지형(시뮬레이터 사이 비교 실험용): $DATA/sim_parity/<MAP>/{scene/scene.xml, derived/}. 만드는 법은 tools/map/hfield_scene_import.py의 입력과 같은 형식입니다.
    P_HOST="$DATA_HOST/sim_parity/$MAP"
    [ -d "$P_HOST" ] || { echo "MAP은 v3, demo, 또는 $DATA_HOST/sim_parity/ 아래 폴더 이름이어야 합니다(받은 값: $MAP)" >&2; exit 2; }
    M_HOST="$P_HOST/derived"; M_CTR="/data/sim_parity/$MAP/derived"
    GRID_NAME=ground_grid.npz
    MJ_SCENE_REL=../scene/scene.xml
    TERRAIN_REL=isaac/terrain_ground.usdc; OBST_REL=isaac/terrain_obstacles.usdc; SCENE_FMT="$M_HOST/isaac/scene_%s.usda"; SCENE_FMT_CTR="$M_CTR/isaac/scene_%s.usda"
    ROUTES_HOST=""; ROUTES_CTR=""
    MAP_HINT="합성 지형: sim_parity/$MAP" ;;
esac
GRID_HOST="$M_HOST/$GRID_NAME";           GRID_CTR="$M_CTR/$GRID_NAME"
MJ_SCENE_HOST="$M_HOST/$MJ_SCENE_REL";    MJ_SCENE_CTR="$M_CTR/$MJ_SCENE_REL"
TERRAIN_HOST="$M_HOST/$TERRAIN_REL";      TERRAIN_CTR="$M_CTR/$TERRAIN_REL"
OBST_HOST="";  OBST_ARGS=()
if [ -n "$OBST_REL" ]; then OBST_HOST="$M_HOST/$OBST_REL"; OBST_ARGS=("--hn-obstacles-usd=$M_CTR/$OBST_REL"); fi

# ---- 로봇·정책 버전 선택 ---------------------------------------------------------------------------------------------
# POLICY=v1(기본): HYPER v1 + Rough GT 정책 model_2998 / POLICY=v0: Go2 v0 + model_3849. 정책 yaml·체크포인트·URDF·task는 같은 버전끼리만 맞습니다.
POLICY="${POLICY:-v1}"
case "$POLICY" in
  v0)
    VER=urdf_v0;  CKPT=hn_go2v0_rough_model_3849.pt;  ACTOR_NAME=actor_model_3849.npz
    URDF_REL=description/hn_v0_go2/hypernova_go2.urdf; MESH_CHECK=description/hn_v0_go2/meshes/base.stl
    MESH_HINT="python3 tools/description/fetch_go2_meshes.py --convert"
    TASK=HN-Velocity-Demo-Rough-Go2v0; SELFCOL=0; VISUALS=1; ROBOT_ID=hn_v0_go2
    MJ_DELAY=0; IS_DELAY=0 ;;                                                       # v0: 토크 지연 보정 없음(넣으면 Isaac Lab에서 멀어짐, docs/development/sim-parity.md)
  v1)
    VER=urdf_v1;  CKPT=hn_hyperv1_rough_model_2998.pt; ACTOR_NAME=actor_hyperv1_rough_model_2998.npz
    URDF_REL=description/hn_v1_hyper/hypernova_hyper.urdf; MESH_CHECK=description/hn_v1_hyper/meshes/trunk.stl
    MESH_HINT="python3 tools/description/fetch_hyper_v1_meshes.py"
    TASK=HN-Velocity-Demo-Rough-HYPERv1; SELFCOL=1; ROBOT_ID=hn_v1_hyper   # v1은 자기충돌을 켜고 학습했습니다
    VISUALS=0                                                                       # MuJoCo는 trunk.stl(25.6만 면)을 못 읽어(한도 20만) 충돌 메시로 그립니다
    MJ_DELAY=5; IS_DELAY=1 ;;                                                       # v1: 토크 지연 보정(MuJoCo 1.25 ms x 5, Isaac Sim 5 ms x 1)
  *) echo "POLICY는 v0 또는 v1이어야 합니다(받은 값: $POLICY)" >&2; exit 2 ;;
esac

CODE_HOST="$REPO/policies/route_walk";  CODE_CTR=/workspace/hypernova/policies/route_walk
VER_HOST="$REPO/policies/$VER";         VER_CTR=/workspace/hypernova/policies/$VER
YAML_HOST="$VER_HOST/policy_io.yaml";   YAML_CTR="$VER_CTR/policy_io.yaml"
CKPT_HOST="$VER_HOST/pretrained/$CKPT"; CKPT_CTR="$VER_CTR/pretrained/$CKPT"
URDF_HOST="$REPO/$URDF_REL";            URDF_CTR="/workspace/hypernova/$URDF_REL"
ACTOR_HOST="$D_HOST/policy/$ACTOR_NAME"; ACTOR_CTR="$D_CTR/policy/$ACTOR_NAME"
SCENE_NAME="$(printf "$(basename "$SCENE_FMT")" "$POLICY")"
SCENE_HOST="${HN_ISAACSIM_SCENE:-$(printf "$SCENE_FMT" "$POLICY")}"
SCENE_CTR="${HN_ISAACSIM_SCENE_CTR:-$(printf "$SCENE_FMT_CTR" "$POLICY")}"

# 시뮬레이터 보정(기본 켬). Isaac Lab(학습 환경)에 가깝게 맞추는 경험적 보정이고, 근거와 한계는 docs/development/sim-parity.md입니다.
#   MuJoCo 접촉(MJ_CALIB=0이면 끔): 접촉을 PhysX처럼 딱딱하게(물리 스텝 4분할 + solref 0.002 + solimp 0.99,0.999,0.001). 실행 시간이 약 2배 늘어납니다.
#   토크 지연(ACT_DELAY=0이면 끔, v1만): Isaac Lab의 Newton 액추에이터 경로는 토크를 늦게 적용하는 것처럼 행동합니다. MuJoCo는 MJ_CALIB가 켜졌을 때만 씁니다.
MJ_CAL=(); IS_CAL=()
if [ "${MJ_CALIB:-1}" = 1 ]; then
  MJ_CAL=(--substeps 4 --solref 0.002,1 --solimp 0.99,0.999,0.001)
  [ "${ACT_DELAY:-1}" != 0 ] && [ "$MJ_DELAY" -gt 0 ] && MJ_CAL+=(--torque-delay "$MJ_DELAY")
fi
[ "${ACT_DELAY:-1}" != 0 ] && [ "$IS_DELAY" -gt 0 ] && IS_CAL=(--torque-delay "$IS_DELAY")

# ROUTE=none이면 경로 파일 없이 고정 명령(vx = --vmax, 시작 (0,0), +x 방향)으로 걷습니다. 합성 지형 비교 실험용입니다. 길이는 --max-steps(Isaac Lab은 --max_steps)로 정합니다.
RT_MJ=(); RT_IS=(); RT_IL=()
if [ "$ROUTE" != none ]; then
  RT_MJ=(--route-file "$ROUTES_CTR" --route "$ROUTE"); RT_IS=("--route-file=$ROUTES_CTR" "--route=$ROUTE"); RT_IL=("--hn-route-file=$ROUTES_CTR" "--hn-route=$ROUTE")
fi

# ---- 상태 판정·고장 주입 하네스(STATE=1, 기본) ------------------------------------------------------------------------------
# 재생기 대신 하네스를 실행하고, 재생기 옵션은 ::: 뒤로 넘깁니다(isaaclab.sh -p는 맨몸의 --를 거부함). 재생기 파일은 수정하지 않습니다.
H=()
case "$FAULT" in ""|collapse|flip|stale|tilt|push) ;; *) echo "FAULT는 collapse, flip, stale, tilt, push 중 하나여야 합니다(받은 값: $FAULT)" >&2; exit 2 ;; esac
if [ "$STATE" = 1 ]; then
  # flip 충격 기본값 [rad/s]: 같은 몸체 프레임 충격이라도 시뮬레이터마다 로봇이 버티는 정도가 달라, 각 시뮬레이터에서 v1이 누운 채로 남는 구간의 가운데를 씁니다
  # (2026-11-19, 맵 v3 경로 A의 8 s: MuJoCo 32~40, Isaac Sim 36~44, Isaac Lab 40 이상. 더 약하면 버티고, 더 세면 한 바퀴 돌아 다시 섭니다)
  case "$MODE" in mujoco) FLIP_RATE=36 ;; isaacsim) FLIP_RATE=40 ;; *) FLIP_RATE=42 ;; esac
  H=(--scenario "${FAULT:-baseline}" --robot-id "$ROBOT_ID" --label "${MAP}_${POLICY}_${ROUTE}" --flip-rate "$FLIP_RATE")
  [ -n "$FAULT" ] && H+=(--at "${AT:-8}")
  [ -n "${FAULT_S:-}" ] && H+=(--duration "$FAULT_S")
  [ -n "${UNTIL:-}" ] && H+=(--until "$UNTIL")
  [ "${STAND_S:-0}" != 0 ] && H+=(--stand-s "$STAND_S")
  [ "$ROS" = 1 ] && H+=(--ros)
  [ "$ROS" = 1 ] && [ "$HEADLESS" = 1 ] && H+=(--realtime)    # 창 없는 모드는 실시간보다 빨라서, ROS로 볼 때는 실시간(50 Hz)으로 늦춥니다
  # 하네스는 넘어짐을 관찰하려고 재생기의 넘어짐 종료를 뺍니다. 창 없는 모드에서 고장 없이 넘어지면 예전처럼 끝나도록 3 s 뒤에 끝냅니다
  [ "$HEADLESS" = 1 ] && [ -z "$FAULT" ] && H+=(--exit-on-fall 3)
  mkdir -p "$DATA_HOST/state_logger"
  H+=(--log "${LOG:-/data/state_logger/$(date +%Y%m%d_%H%M%S)_${MODE}_${FAULT:-walk}.jsonl}")
  # shellcheck disable=SC2206  # STATE_ARGS는 공백으로 나눈 옵션 목록입니다
  H+=(${STATE_ARGS:-})
fi
harness() {   # harness <재생기 파일 이름>: 하네스를 쓰면 실행할 스크립트와 하네스 옵션, 아니면 재생기 경로를 냅니다
  if [ "$STATE" = 1 ]; then printf '%s\n' "$CODE_CTR/state_scenarios.py" --player "$1" "${H[@]}" ":::"; else printf '%s\n' "$CODE_CTR/$1"; fi
}

# ---- 필요한 파일 점검 -------------------------------------------------------------------------------------------------
need() {  # need <표시 이름> <호스트 경로>
  if [ -e "$2" ]; then printf '  [ok]    %s\n' "$1"; else printf '  [없음]  %s  <- %s\n' "$1" "$2"; MISSING=1; fi
}
check_data() {
  MISSING=0
  echo "[run_route] 저장소: $REPO"
  echo "[run_route] 데이터 폴더: $DATA_HOST | 지도 MAP=$MAP | 로봇·정책 POLICY=$POLICY"
  need "코드 policies/route_walk/play_mujoco.py"     "$CODE_HOST/play_mujoco.py"
  need "정책 yaml / 경로 yaml"                        "$YAML_HOST"
  [ "$ROUTE" != none ] && need "경로 yaml"            "$ROUTES_HOST"
  need "로봇 URDF"                                    "$URDF_HOST"
  need "로봇 mesh $(basename "$MESH_CHECK") ($MESH_HINT)" "$REPO/$MESH_CHECK"
  case "$1" in
    export|all)
      need "체크포인트 $CKPT"                          "$CKPT_HOST" ;;
  esac
  case "$1" in
    mujoco|isaaclab|isaacsim|all)
      need "정책 가중치 $ACTOR_NAME (export 모드로 생성)" "$ACTOR_HOST"
      need "지면 높이 격자 $GRID_NAME ($MAP_HINT)"     "$GRID_HOST" ;;
  esac
  case "$1" in
    isaaclab|isaacsim|all)
      need "지형 충돌 메시 $(basename "$TERRAIN_REL")"  "$TERRAIN_HOST"
      [ -n "$OBST_HOST" ] && need "장애물 충돌 메시 $(basename "$OBST_REL")" "$OBST_HOST" ;;
  esac
  case "$1" in
    isaacsim|all)
      need "Isaac Sim 장면 $SCENE_NAME"                "$SCENE_HOST" ;;
  esac
  case "$1" in
    mujoco|all)
      need "MuJoCo 지형 scene.xml"                     "$MJ_SCENE_HOST" ;;
  esac
  if [ "$MISSING" = 1 ]; then
    echo "[run_route] 없는 파일이 있습니다. 위 '필요한 것'을 준비하십시오." >&2
    return 1
  fi
}

# ---- 실행 -------------------------------------------------------------------------------------------------------------
case "$MODE" in
  check)
    check_data all && echo "[run_route] 모든 파일이 있습니다." ;;
  export)
    check_data export
    if [ -e "$ACTOR_HOST" ]; then echo "[run_route] 이미 있습니다: $ACTOR_HOST (다시 만들려면 지우고 실행하십시오)"; exit 0; fi
    mkdir -p "$(dirname "$ACTOR_HOST")"
    cd "$REPO"
    exec ./docker/hn sim /workspace/isaaclab/isaaclab.sh -p "$CODE_CTR/export_actor.py" "$YAML_CTR" "$CKPT_CTR" "$ACTOR_CTR" ;;
  isaaclab)
    check_data isaaclab
    VIZ=kit; [ "$HEADLESS" = 1 ] && VIZ=none
    EXIT=(); [ "$HEADLESS" = 1 ] && EXIT=(--hn-exit-on-arrival=1 --hn-realtime=0)
    [ -n "$FAULT" ] && [ "$HEADLESS" = 1 ] && EXIT=(--hn-realtime=0)   # 고장 예약은 UNTIL에서 끝냄(도착해도 끝내지 않음)
    mapfile -t RUN < <(harness play_isaaclab.py)
    cd "$REPO"
    exec ./docker/hn sim "${ENVP[@]}" /workspace/isaaclab/isaaclab.sh -p "${RUN[@]}" \
      --task "$TASK" --num_envs 1 \
      "--hn-yaml=$YAML_CTR" "--hn-actor=$ACTOR_CTR" "--hn-ground=$GRID_CTR" \
      "--hn-terrain-usd=$TERRAIN_CTR" "${OBST_ARGS[@]}" \
      "${RT_IL[@]}" --hn-follow=2 --hn-cam=5,-5,3.5 "${EXIT[@]}" \
      "$@" --visualizer "$VIZ" physics=isaacsim_physx ;;
  isaacsim)
    check_data isaacsim
    HL=(); [ "$HEADLESS" = 1 ] && HL=(--headless --exit-on-arrival)
    [ -n "$FAULT" ] && [ "$HEADLESS" = 1 ] && HL=(--headless)
    mapfile -t RUN < <(harness play_isaacsim.py)
    cd "$REPO"
    exec ./docker/hn sim "${ENVP[@]}" /workspace/isaaclab/isaaclab.sh -p "${RUN[@]}" \
      "--yaml=$YAML_CTR" "--actor=$ACTOR_CTR" "--scene=$SCENE_CTR" "--self-collision=$SELFCOL" \
      "--ground-grid=$GRID_CTR" "${RT_IS[@]}" "${HL[@]}" "${IS_CAL[@]}" "$@" ;;
  mujoco)
    check_data mujoco
    HL=(); [ "$HEADLESS" = 1 ] && HL=(--headless --exit-on-arrival)
    [ -n "$FAULT" ] && [ "$HEADLESS" = 1 ] && HL=(--headless)
    mapfile -t RUN < <(harness play_mujoco.py)
    cd "$REPO"
    exec ./docker/hn sim "${ENVP[@]}" /opt/hn-venv/bin/python "${RUN[@]}" \
      --yaml "$YAML_CTR" --actor "$ACTOR_CTR" \
      --scene "$MJ_SCENE_CTR" --urdf "$URDF_CTR" --self-collision "$SELFCOL" --visuals "$VISUALS" \
      "${RT_MJ[@]}" "${HL[@]}" "${MJ_CAL[@]}" "$@" ;;
  *)
    sed -n '3,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    [ -n "$MODE" ] && { echo "알 수 없는 모드: $MODE" >&2; exit 2; } || exit 0 ;;
esac
