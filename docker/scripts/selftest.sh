#!/usr/bin/env bash
# 컨테이너 환경 점검. ros, sim 두 target에서 같이 쓰고, CI도 이 스크립트로 이미지 내용을 확인합니다.
#
#   ./docker/hn ros /opt/hn/scripts/selftest.sh           기본 점검 (몇 초)
#   ./docker/hn sim /opt/hn/scripts/selftest.sh --isaac   Isaac Lab import까지 (sim, 30초 안팎)
#
# 확인하는 것: ROS 패키지, robot venv 버전이 이미지에 들어간 uv.lock과 같은지, rclpy가 venv에서도 import되는지.
# 하나라도 실패하면 종료 코드 1.
set -uo pipefail

VENV="${HN_VENV:-/opt/hn-venv}"
LOCK="${HN_LOCK_DIR:-/opt/hn/lock}/uv.lock"
fail=0

ok()  { printf '  OK    %s\n' "$*"; }
bad() { printf '  FAIL  %s\n' "$*"; fail=1; }
section() { printf '\n[%s]\n' "$*"; }

check() {   # check <이름> <명령...>   (성공하면 출력의 첫 줄을 함께 보여 줍니다)
  local name="$1" out
  shift
  if out="$("$@" 2>&1)"; then
    ok "$name${out:+ — $(printf '%s' "$out" | head -n1)}"
  else
    bad "$name — $(printf '%s' "$out" | tail -n1)"
  fi
}

section "환경 ($HN_TARGET, $(uname -m))"
check "ROS_DISTRO=$ROS_DISTRO" test "${ROS_DISTRO:-}" = "${HN_ROS_DISTRO:-}"
check "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-}" test "${RMW_IMPLEMENTATION:-}" = rmw_fastrtps_cpp
check "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-(기본 0)}" true

section "ROS 패키지"
pkgs=(rclpy rviz2 rqt rosbag2 rosbag2_storage_mcap rosbridge_server foxglove_bridge joy teleop_twist_joy pcl_ros tf2_tools)
if [ "${HN_TARGET:-}" = ros ]; then
  pkgs+=(rko_lio fast_lio livox_ros_driver2)
fi
for p in "${pkgs[@]}"; do
  check "$p" ros2 pkg prefix "$p"
done
check "underlay /opt/hn_ws" test -f /opt/hn_ws/install/setup.bash   # ros: LIO 패키지, sim: 비어 있음(경로만 같게)
check "colcon" command -v colcon
check "vcs" command -v vcs
check "rosdep" command -v rosdep

section "robot venv ($VENV)"
check "interpreter" "$VENV/bin/python" -c 'import sys; print(sys.version.split()[0], sys.prefix)'
# 설치된 버전이 이미지에 들어간 uv.lock과 같은지. open3d는 aarch64에 wheel이 없어 그 구조에서는 건너뜁니다.
if [ -f "$LOCK" ]; then
  while IFS= read -r line; do
    case "$line" in
      OK*)   ok "${line#OK }" ;;
      SKIP*) ok "${line#SKIP }" ;;
      *)     bad "$line" ;;
    esac
  done < <("$VENV/bin/python" -I - "$LOCK" <<'PY'
import platform, sys, tomllib
from importlib import metadata

locked = {p["name"]: p["version"] for p in tomllib.load(open(sys.argv[1], "rb"))["package"]}
for name in ("mujoco", "onnx", "onnxruntime", "open3d", "numpy"):
    try:
        have = metadata.version(name)
    except metadata.PackageNotFoundError:
        have = None
    if have is None and name == "open3d" and platform.machine() == "aarch64":
        print(f"SKIP {name} 없음 (arm64 이미지에는 일부러 넣지 않음 — ADR-0002 §4)")
    elif have == locked[name]:
        print(f"OK {name} {have} (uv.lock과 같음)")
    else:
        print(f"{name}: 설치 {have}, uv.lock {locked[name]}")
PY
)
else
  bad "$LOCK 없음"
fi
# 시스템 numpy(ROS 메시지 바인딩이 쓰는 1.x C API)와 venv가 충돌하지 않는지: venv에서 rclpy와 메시지 import
check "rclpy + 메시지 import (venv)" "$VENV/bin/python" -c '
import numpy, rclpy
from sensor_msgs.msg import PointCloud2
from geometry_msgs.msg import TransformStamped
print("numpy", numpy.__version__, "rclpy", rclpy.__file__.split("/lib/")[0])'

if [ "${HN_TARGET:-}" = sim ]; then
  section "Isaac Lab venv (건드리지 않아야 함)"
  check "VIRTUAL_ENV" test "${VIRTUAL_ENV:-}" = /opt/isaaclab-venv
  check "hn-rl이 PhysX를 붙임" bash -c 'HN_RL_DRY_RUN=1 hn-rl train --task X | grep -q "physics=isaacsim_physx"'
  check "torch / warp / numpy / mujoco / onnx / rsl-rl" /opt/isaaclab-venv/bin/python -c '
from importlib import metadata as m
print(*(f"{n}={m.version(n)}" for n in ("torch","warp-lang","numpy","mujoco","onnx","rsl-rl-lib")))'
  if [ "${1:-}" = --isaac ]; then
    # 출력이 [INFO] 줄과 섞이고, grep -m1이 파이프를 먼저 닫으면 pipefail이 실패로 보므로 출력을 모은 뒤 찾습니다.
    # shellcheck disable=SC2016  # bash -c 안에서 펼쳐져야 하므로 작은따옴표가 맞습니다
    check "import isaaclab (isaaclab.sh)" bash -c 'cd /workspace/isaaclab && out="$(./isaaclab.sh -p -c "import isaaclab; print(\"isaaclab\", isaaclab.__version__)" 2>&1)" || { printf "%s\n" "$out" | tail -n 3; exit 1; }; grep -m1 "^isaaclab " <<< "$out"'
  fi
fi

printf '\n'
if [ "$fail" -eq 0 ]; then
  echo "모두 통과"
else
  echo "실패한 항목이 있습니다. 위 FAIL 줄을 확인하세요."
fi
exit "$fail"
