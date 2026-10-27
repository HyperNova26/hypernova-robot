#!/usr/bin/env bash
# robot venv(/opt/hn-venv)를 저장소 최상위 pyproject.toml/uv.lock 그대로 만듭니다. ros, sim 두 target이 같이 씁니다.
#
#   - 시스템 Python 3.12 + --system-site-packages: 같은 interpreter에서 apt로 설치한 rclpy가 import됩니다.
#   - Dockerfile에는 패키지 버전을 따로 적지 않습니다. 버전은 uv.lock이 정하고 `uv sync --locked`가 지킵니다.
#   - uv는 이 스크립트가 버전·sha256을 고정해서 /opt/hn/bin/uv에 따로 설치합니다.
#     sim 베이스(Isaac Lab)의 /usr/local/bin/uv와 그 venv(/opt/isaaclab-venv)는 건드리지 않습니다.
#
# 필요한 환경변수(docker/.env): UV_VERSION, UV_SHA256_AMD64, UV_SHA256_ARM64
# 입력: $HN_LOCK_DIR(기본 /opt/hn/lock)의 pyproject.toml, uv.lock     출력: $HN_VENV(기본 /opt/hn-venv)
set -euo pipefail

: "${UV_VERSION:?UV_VERSION이 비어 있습니다. docker/.env 값을 build arg로 넘겨야 합니다 (./docker/hn build ...)}"
: "${UV_SHA256_AMD64:?UV_SHA256_AMD64가 비어 있습니다}"
: "${UV_SHA256_ARM64:?UV_SHA256_ARM64가 비어 있습니다}"

LOCK_DIR="${HN_LOCK_DIR:-/opt/hn/lock}"
VENV="${HN_VENV:-/opt/hn-venv}"
PYTHON=/usr/bin/python3.12
UV_BIN=/opt/hn/bin/uv

[ -x "$PYTHON" ] || { echo "$PYTHON 이 없습니다. install_ros_deps.sh를 먼저 실행해야 합니다(시스템 python3는 ROS 패키지와 함께 들어옵니다)." >&2; exit 1; }
[ -f "$LOCK_DIR/pyproject.toml" ] && [ -f "$LOCK_DIR/uv.lock" ] || { echo "$LOCK_DIR 에 pyproject.toml, uv.lock 이 없습니다." >&2; exit 1; }

# --- 1. uv 설치 (버전과 sha256 고정) ---------------------------------------------------
case "$(uname -m)" in
  x86_64)  uv_arch=x86_64;  uv_sha="$UV_SHA256_AMD64" ;;
  aarch64) uv_arch=aarch64; uv_sha="$UV_SHA256_ARM64" ;;
  *) echo "지원하지 않는 아키텍처: $(uname -m)" >&2; exit 1 ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tarball="uv-${uv_arch}-unknown-linux-gnu.tar.gz"
curl -fsSL --retry 5 -o "$tmp/$tarball" "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${tarball}"
echo "${uv_sha}  $tmp/$tarball" | sha256sum -c -
tar -xzf "$tmp/$tarball" -C "$tmp"
install -D -m 0755 "$tmp/uv-${uv_arch}-unknown-linux-gnu/uv" "$UV_BIN"

# --- 2. venv ----------------------------------------------------------------------------
# sim 베이스 이미지는 VIRTUAL_ENV, UV_PROJECT_ENVIRONMENT, UV_PYTHON을 Isaac Lab venv로 설정해 둡니다.
# 그대로 두면 uv sync가 Isaac Lab venv를 robot venv의 lock(numpy 1.26.4 등)으로 덮어쓰므로 여기서 모두 지웁니다.
unset VIRTUAL_ENV UV_PYTHON UV_PROJECT_ENVIRONMENT
export UV_PYTHON_PREFERENCE=only-system   # 시스템 /usr/bin/python3.12만 씁니다(pyproject.toml과 같은 규칙)
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
export UV_LINK_MODE=copy                  # 캐시(다른 파일시스템)에서 hardlink가 안 돼서 나는 경고를 없앱니다
export UV_COMPILE_BYTECODE=1              # 실행 사용자가 site-packages에 .pyc를 쓸 수 없으므로 미리 만들어 둡니다

"$UV_BIN" venv --python "$PYTHON" --system-site-packages "$VENV"

sync_args=(--locked --project "$LOCK_DIR" --python "$PYTHON")

# arm64(Jetson)에는 Open3D를 일부러 넣지 않습니다. Jetson에서는 Open3D가 필요 없고(지형 처리는 PC에서 함),
# open3d==0.19.0은 PyPI에 Linux aarch64 wheel도 없어서 uv.lock 그대로는 설치되지 않습니다.
# lock과 버전 고정(ADR-0002 §4)은 그대로 두고 aarch64에서만 이 패키지를 건너뜁니다.
if [ "$(uname -m)" = aarch64 ]; then
  echo "경고: aarch64에서는 open3d를 설치하지 않습니다(open3d==0.19.0에 Linux aarch64 wheel이 없음)." >&2
  sync_args+=(--no-install-package open3d)
fi

UV_PROJECT_ENVIRONMENT="$VENV" "$UV_BIN" sync "${sync_args[@]}"

"$VENV/bin/python" - <<'PY'
import sys
import numpy
print(f"robot venv: python {sys.version.split()[0]}, numpy {numpy.__version__}, prefix {sys.prefix}")
PY
