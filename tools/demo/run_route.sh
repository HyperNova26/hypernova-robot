#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# PAIR360 데모 지형에서 팀원 정책(model_3849)으로 로봇이 경로를 걷는 것을 Isaac Lab, MuJoCo, Isaac Sim에서 재생합니다.
#
# 사용법 (저장소 최상위에서)
#   ./tools/demo/run_route.sh check               # 필요한 파일이 있는지 점검
#   ./tools/demo/run_route.sh export              # 저장소 체크포인트에서 actor 가중치(.npz)를 만듭니다(컨테이너 hn:sim, 처음 한 번)
#   ./tools/demo/run_route.sh mujoco              # MuJoCo 창(컨테이너 hn:sim의 robot venv)
#   ./tools/demo/run_route.sh isaaclab            # Isaac Lab 창(컨테이너 hn:sim). 카메라가 로봇을 따라가며 줌 가능
#   ./tools/demo/run_route.sh isaacsim            # Isaac Sim 단독 창(컨테이너 hn:sim). 장면 USD는 아래 설명 참고
#   ROUTE=B ./tools/demo/run_route.sh mujoco      # 다른 경로(A: 스크린샷 그대로, B: 좁은 목을 피해 우회)
#   ./tools/demo/run_route.sh isaaclab --hn-vmax=0.4        # 뒤에 붙인 옵션은 그대로 해당 스크립트로 전달
#   HEADLESS=1 ./tools/demo/run_route.sh mujoco             # 창 없이 끝까지 걷고 결과만 출력(시험용)
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
# 좌표는 데모 프레임(x=동, y=북, m). 프레임 제안은 docs/decisions/0003-pair360-demo-frame.md(Proposed).
set -euo pipefail

MODE="${1:-}"
[ $# -gt 0 ] && shift
ROUTE="${ROUTE:-A}"
HEADLESS="${HEADLESS:-0}"

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
D_HOST="$DATA_HOST/pair360_demo_frame"       # 호스트에서 본 경로
D_CTR=/data/pair360_demo_frame               # 컨테이너에서 본 경로(데이터 폴더는 /data로 마운트됨)

CODE_HOST="$REPO/policies/route_walk";  CODE_CTR=/workspace/hypernova/policies/route_walk
VER_HOST="$REPO/policies/urdf_v0";      VER_CTR=/workspace/hypernova/policies/urdf_v0
YAML_HOST="$VER_HOST/policy_io.yaml";   YAML_CTR="$VER_CTR/policy_io.yaml"
ROUTES_HOST="$VER_HOST/routes/pair360_demo.yaml"; ROUTES_CTR="$VER_CTR/routes/pair360_demo.yaml"
CKPT_CTR="$VER_CTR/pretrained/hn_go2v0_rough_model_3849.pt"
URDF_HOST="$REPO/description/hn_v0_go2/hypernova_go2.urdf"; URDF_CTR=/workspace/hypernova/description/hn_v0_go2/hypernova_go2.urdf
ACTOR_HOST="$D_HOST/policy/actor_model_3849.npz"; ACTOR_CTR="$D_CTR/policy/actor_model_3849.npz"
SCENE_HOST="${HN_ISAACSIM_SCENE:-$D_HOST/isaac/scene_demo_v0.usda}"
SCENE_CTR="${HN_ISAACSIM_SCENE_CTR:-$D_CTR/isaac/scene_demo_v0.usda}"
TASK=HN-Velocity-Demo-Rough-Go2v0

# ---- 필요한 파일 점검 -------------------------------------------------------------------------------------------------
need() {  # need <표시 이름> <호스트 경로>
  if [ -e "$2" ]; then printf '  [ok]    %s\n' "$1"; else printf '  [없음]  %s  <- %s\n' "$1" "$2"; MISSING=1; fi
}
check_data() {
  MISSING=0
  echo "[run_route] 저장소: $REPO"
  echo "[run_route] 데이터 폴더: $DATA_HOST"
  need "코드 policies/route_walk/play_mujoco.py"     "$CODE_HOST/play_mujoco.py"
  need "정책 yaml / 경로 yaml"                        "$YAML_HOST"
  need "경로 yaml"                                    "$ROUTES_HOST"
  need "로봇 URDF"                                    "$URDF_HOST"
  need "로봇 mesh base.stl (fetch_go2_meshes.py --convert)" "$REPO/description/hn_v0_go2/meshes/base.stl"
  case "$1" in
    export|all)
      need "체크포인트 hn_go2v0_rough_model_3849.pt"   "$VER_HOST/pretrained/hn_go2v0_rough_model_3849.pt" ;;
  esac
  case "$1" in
    mujoco|isaaclab|isaacsim|all)
      need "정책 가중치 actor_model_3849.npz (export 모드로 생성)" "$ACTOR_HOST"
      need "지면 높이 격자 ground_grid_demo.npz"       "$D_HOST/ground_grid_demo.npz" ;;
  esac
  case "$1" in
    isaaclab|isaacsim|all)
      need "지형 충돌 메시 ground_collision_demo.usdc" "$D_HOST/isaac/ground_collision_demo.usdc" ;;
  esac
  case "$1" in
    isaacsim|all)
      need "Isaac Sim 장면 scene_demo_v0.usda"         "$SCENE_HOST" ;;
  esac
  case "$1" in
    mujoco|all)
      need "MuJoCo 지형 scene.xml"                     "$D_HOST/mujoco/scene.xml"
      need "MuJoCo 높이맵 타일 hfields/"               "$D_HOST/mujoco/hfields" ;;
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
    cd "$REPO"
    exec ./docker/hn sim /workspace/isaaclab/isaaclab.sh -p "$CODE_CTR/play_isaaclab.py" \
      --task "$TASK" --num_envs 1 \
      "--hn-yaml=$YAML_CTR" "--hn-actor=$ACTOR_CTR" "--hn-ground=$D_CTR/ground_grid_demo.npz" \
      "--hn-route-file=$ROUTES_CTR" "--hn-route=$ROUTE" --hn-follow=2 --hn-cam=5,-5,3.5 "${EXIT[@]}" \
      "$@" --visualizer "$VIZ" physics=isaacsim_physx ;;
  isaacsim)
    check_data isaacsim
    HL=(); [ "$HEADLESS" = 1 ] && HL=(--headless --exit-on-arrival)
    cd "$REPO"
    exec ./docker/hn sim /workspace/isaaclab/isaaclab.sh -p "$CODE_CTR/play_isaacsim.py" \
      "--yaml=$YAML_CTR" "--actor=$ACTOR_CTR" "--scene=$SCENE_CTR" \
      "--ground-grid=$D_CTR/ground_grid_demo.npz" "--route-file=$ROUTES_CTR" "--route=$ROUTE" "${HL[@]}" "$@" ;;
  mujoco)
    check_data mujoco
    HL=(); [ "$HEADLESS" = 1 ] && HL=(--headless --exit-on-arrival)
    cd "$REPO"
    exec ./docker/hn sim /opt/hn-venv/bin/python "$CODE_CTR/play_mujoco.py" \
      --yaml "$YAML_CTR" --actor "$ACTOR_CTR" \
      --scene "$D_CTR/mujoco/scene.xml" --urdf "$URDF_CTR" \
      --route-file "$ROUTES_CTR" --route "$ROUTE" "${HL[@]}" "$@" ;;
  *)
    sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    [ -n "$MODE" ] && { echo "알 수 없는 모드: $MODE" >&2; exit 2; } || exit 0 ;;
esac
