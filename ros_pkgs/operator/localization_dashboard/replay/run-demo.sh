#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
# 대시보드 데이터 소스(Docker)와 웹 화면을 한 번에 띄웁니다. Ubuntu 24.04와 WSL2(Ubuntu)에서 같은 명령입니다.
#
#   replay/run-demo.sh setup                  # 처음 한 번: Drive 사본 확인, public/ 생성 파일 복사, 이미지 준비
#   replay/run-demo.sh bag [--rate 0.5]       # 11-15 핸드헬드 bag → Super-LIO(+위치추정 상태) → 대시보드
#   replay/run-demo.sh sim [--fall-at 40]     # 연결 시험용 가짜 로봇(MuJoCo 운동학, 보행 시뮬 아님)
#   replay/run-demo.sh stop                   # 컨테이너와 웹 서버 정리
#
# 옵션: --data DIR   팀 Drive '14. AI Team' 폴더를 받아 둔 곳(기본 ${HN_DATA_DIR:-~/hypernova-data}/ai-team)
#       --bag DIR    다른 rosbag2 폴더(정합값 registration/1115*.env는 11-15 기록에만 맞습니다)
#       --lio superlio|fastlio, --rate R, --fall-at S(sim), --no-web(웹 서버를 띄우지 않음)
#       --expose     bridge를 이 PC의 모든 네트워크에 엽니다(다른 PC의 대시보드에서 접속할 때). 기본은 이 PC에서만
# 웹 화면: http://127.0.0.1:5173 → 데이터 소스를 고르고 '수신 시작'. bridge 주소는 ws://localhost:8765입니다.
# Node.js가 없으면 Docker 안에서 빌드하고 python3로 정적 파일을 띄웁니다.
set -euo pipefail

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$PKG/../../.." && pwd)"
REC=20261115T120809_074988Z_measurement_e03893
DATA="${HN_DATA_DIR:-$HOME/hypernova-data}/ai-team"
BAG="" LIO=superlio RATE=1.0 FALL_AT="" WEB=1 PUBLISH=127.0.0.1
CMD="${1:-}"
[ $# -gt 0 ] && shift
while [ $# -gt 0 ]; do
  case "$1" in
    --data) DATA="$2"; shift 2 ;;
    --bag) BAG="$2"; shift 2 ;;
    --lio) LIO="$2"; shift 2 ;;
    --rate) RATE="$2"; shift 2 ;;
    --fall-at) FALL_AT="$2"; shift 2 ;;
    --no-web) WEB=0; shift ;;
    --expose) PUBLISH=0.0.0.0; shift ;;
    *) echo "모르는 옵션: $1" >&2; exit 2 ;;
  esac
done
BAG="${BAG:-$DATA/data/recordings/$REC/rosbag2}"
say() { printf '[run-demo] %s\n' "$*"; }
die() { printf '[run-demo] %s\n' "$*" >&2; exit 1; }
command -v docker > /dev/null && docker info > /dev/null 2>&1 \
  || die "docker를 쓸 수 없습니다. WSL이면 Docker Desktop → Settings → Resources → WSL integration에서 이 배포판을 켜세요."

# Image tag follows the repository pin (docker/.env). The team ros image comes from GHCR
# (./docker/hn pull ros); a locally built hn:ros-<tag>-local is used instead when present.
TAG="$(sed -n 's/^HN_IMAGE_TAG=//p' "$REPO/docker/.env" 2> /dev/null | tail -1)"
TAG="${TAG:-2026.10.1}"
if docker image inspect "hn:ros-$TAG-local" > /dev/null 2>&1; then BASE="hn:ros-$TAG-local"
else BASE="ghcr.io/hypernova26/hn:ros-$TAG"; fi
TWIST="hn:ros-$TAG-local-twist" SUPERLIO="hn:ros-$TAG-local-superlio"
NAMES=(hyper-bag-fastlio-1115 hyper-bag-superlio-1115 hyper-sim-mujoco-v3)
RUN="$PKG/.run-demo"   # web server pid and logs (ignored by git)

image() {   # image NAME BUILD_ARGS...  — build once if missing
  local name="$1"; shift
  docker image inspect "$name" > /dev/null 2>&1 && return
  say "$name 이미지가 없어 빌드합니다(처음 한 번, 수 분)."
  docker build -t "$name" "$@"
}
images() {
  docker image inspect "$BASE" > /dev/null 2>&1 || docker pull "$BASE" \
    || die "$BASE 를 받지 못했습니다. 저장소 최상위에서 ./docker/hn pull ros (또는 build ros)를 먼저 하세요."
  image "$TWIST" --build-arg "BASE=$BASE" "$PKG/adapters/fast_lio_twist"
  image "$SUPERLIO" --build-arg "BASE=$TWIST" -f "$PKG/replay/Dockerfile.superlio" "$PKG/replay"
}
scene() {   # MuJoCo scene folder from the Drive zip (unpacked next to it once)
  local zip="$DATA/meshes/mesh_v3/PAIR360-Go2-MuJoCo_mesh_v3.zip" dir="$DATA/meshes/mesh_v3/unzipped"
  if [ ! -f "$dir/PAIR360-Go2-mesh_v3/scene/scene.xml" ]; then
    [ -f "$zip" ] || die "없음: $zip (Drive meshes/mesh_v3/)"
    mkdir -p "$dir" && unzip -q -o "$zip" -d "$dir"
  fi
  printf '%s' "$dir/PAIR360-Go2-mesh_v3/scene"
}
stop_all() {
  for n in "${NAMES[@]}"; do docker rm -f "$n" > /dev/null 2>&1 || true; done
  if [ -f "$RUN/web.pid" ]; then kill "$(cat "$RUN/web.pid")" 2> /dev/null || true; rm -f "$RUN/web.pid"; fi
}
web() {
  [ "$WEB" = 1 ] || return 0
  [ -f "$PKG/public/terrain-mesh.json" ] || die "public/ 생성 파일이 없습니다. 먼저: replay/run-demo.sh setup"
  mkdir -p "$RUN"
  local npm; npm="$(command -v npm || true)"
  # Background servers get their own session and no terminal, so this script (and `wsl -- ...`) returns.
  if [ -n "$npm" ] && [[ "$npm" != /mnt/* ]]; then   # Linux Node.js (not Windows npm seen from WSL)
    [ -d "$PKG/node_modules" ] || (cd "$PKG" && npm ci)
    (cd "$PKG" && setsid nohup npm run dev -- --port 5173 --strictPort > "$RUN/web.log" 2>&1 < /dev/null &
      echo $! > "$RUN/web.pid")
  else
    # The source is mounted read-only and built from a copy inside the container, so a node_modules
    # installed on the host (e.g. Windows) is never replaced; only dist/ comes back. npm cache is a volume.
    say "Node.js가 없어 Docker(node:24)에서 빌드합니다(처음 몇 분, 이후 캐시)."
    mkdir -p "$RUN/dist"
    # Runs as root (the cache volume is root-owned); the copied dist/ is handed back to this user.
    docker run --rm -e npm_config_cache=/cache -e OWNER="$(id -u):$(id -g)" \
      -v hn-dashboard-npm:/cache -v "$PKG:/src:ro" -v "$RUN/dist:/out" node:24-bookworm-slim sh -c \
      'mkdir -p /tmp/b && cd /src && tar --exclude=./node_modules --exclude=./dist --exclude=./.run-demo -cf - . \
        | tar -xf - -C /tmp/b && cd /tmp/b && npm ci --no-audit --no-fund && npm run build \
        && cp -r dist/. /out/ && chown -R "$OWNER" /out' \
      > "$RUN/build.log" 2>&1 || die "빌드 실패: $RUN/build.log"
    setsid nohup python3 -m http.server 5173 --bind 127.0.0.1 -d "$RUN/dist" > "$RUN/web.log" 2>&1 < /dev/null &
    echo $! > "$RUN/web.pid"
  fi
  sleep 3
  local url=http://127.0.0.1:5173
  if command -v wslview > /dev/null; then wslview "$url"
  elif grep -qi microsoft /proc/version 2> /dev/null; then cmd.exe /c start "$url" > /dev/null 2>&1 || true
  elif command -v xdg-open > /dev/null; then xdg-open "$url" > /dev/null 2>&1 || true
  fi
  say "웹 화면: $url"
}
publish() { printf '%s' "$PUBLISH:8765:8765"; }

case "$CMD" in
  setup)
    for f in "data/recordings/$REC/rosbag2/metadata.yaml" data/dashboard_public/terrain-mesh.json \
             meshes/mesh_v3/PAIR360-Go2-MuJoCo_mesh_v3.zip; do
      [ -e "$DATA/$f" ] || die "Drive 사본에 없음: $DATA/$f  (팀 Drive '14. AI Team'의 같은 경로를 받거나 --data로 위치 지정)"
    done
    (cd "$DATA/data/dashboard_public" && sha256sum -c --quiet SHA256SUMS.txt) || die "dashboard_public 해시 불일치"
    mkdir -p "$PKG/public"
    cp -r "$DATA/data/dashboard_public/." "$PKG/public/"
    rm -f "$PKG/public/SHA256SUMS.txt" "$PKG/public/README.md"
    say "public/ 생성 파일 복사 완료(지형 메시·지도 프리뷰·로봇)."
    scene > /dev/null && say "MuJoCo 장면 준비 완료."
    images
    say "준비 끝. 다음: replay/run-demo.sh bag  또는  replay/run-demo.sh sim"
    ;;
  bag)
    [ -f "$BAG/metadata.yaml" ] || die "rosbag2 폴더가 아닙니다: $BAG"
    case "$LIO" in
      superlio) name=hyper-bag-superlio-1115 env=1115_superlio.env img="$SUPERLIO" script=run_bag_superlio.sh ;;
      fastlio) name=hyper-bag-fastlio-1115 env=1115.env img="$TWIST" script=run_bag_lio.sh ;;
      *) die "--lio는 superlio 또는 fastlio" ;;
    esac
    images; stop_all
    map="$(sed -n 's/.*"file": *"\([^"]*\)".*/\1/p' "$PKG/public/reference-map.json")"
    docker run -d --rm --name "$name" -p "$(publish)" -e ROS_DOMAIN_ID=42 \
      --env-file "$PKG/replay/registration/$env" -v "$PKG:/pkg:ro" -v "$BAG:/bag:ro" \
      -e BRIDGE_ADDRESS=0.0.0.0 -e ADAPTERS=/pkg/adapters -e "MAP_PCD=/pkg/public/$map" \
      "$img" bash "/pkg/replay/$script" /bag "$RATE" > /dev/null
    web
    say "bag 재생 시작($LIO, 배속 $RATE). 화면의 데이터 소스 '핸드헬드 기록 재생' → '수신 시작'."
    say "Super-LIO 초기화에 bag 시간 약 20초. 1배속 약 5분 30초 뒤 끝나고 컨테이너가 지워집니다."
    ;;
  sim)
    # G-006 judge (main #22). HN_ROBOT_STATE_DIR points at another checkout's copy if this one lacks it.
    STATE="${HN_ROBOT_STATE_DIR:-$REPO/ros_pkgs/hn_robot_state}"
    [ -f "$STATE/hn_robot_state/core.py" ] \
      || die "$STATE 가 없습니다(main #22 이후 브랜치에서 실행하거나 HN_ROBOT_STATE_DIR 지정)."
    sc="$(scene)"
    images; stop_all
    map="$(sed -n 's/.*"file": *"\([^"]*\)".*/\1/p' "$PKG/public/reference-map.json")"
    fall=""; [ -n "$FALL_AT" ] && fall="--fall-at $FALL_AT"
    docker run -d --rm --name hyper-sim-mujoco-v3 -p "$(publish)" -e ROS_DOMAIN_ID=42 \
      -v "$PKG:/pkg:ro" -v "$sc:/scene:ro" -v "$STATE:/state:ro" -e HN_ROBOT_STATE=/state \
      "$BASE" bash -lc "source /opt/ros/jazzy/setup.bash; cd /pkg/adapters; export PYTHONDONTWRITEBYTECODE=1
        /opt/hn-venv/bin/python -u mujoco_route_sim.py /scene --rate $RATE --locomotion-topic /locomotion/status --path-topic /plan $fall > /tmp/sim.log 2>&1 &
        /opt/hn-venv/bin/python -u reference_map_ros.py ../public/$map --frame pair360_map > /tmp/map.log 2>&1 &
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:=0.0.0.0 port:=8765 > /tmp/bridge.log 2>&1 &
        wait" > /dev/null
    web
    say "연결 시험용 가짜 로봇 시작(보행 시뮬 아님). 화면의 데이터 소스 '시뮬레이터' → '수신 시작'(GT 토픽 자동 설정)."
    ;;
  stop) stop_all; say "정리했습니다." ;;
  *) sed -n '4,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
[ "$PUBLISH" = 0.0.0.0 ] && say "주의: bridge가 이 PC의 모든 네트워크(포트 8765)에 열렸습니다. 다른 PC 대시보드의 연결 설정에 ws://<이 PC IP>:8765" || true
