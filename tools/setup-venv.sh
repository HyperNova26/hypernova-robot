#!/usr/bin/env bash
# 공용 Python 환경(.venv)을 만들거나 uv.lock에 맞춰 갱신합니다.
#
# 사용법:  ./tools/setup-venv.sh       (처음 한 번, 그리고 git pull로 uv.lock이 바뀌었을 때)
# 필요:    Ubuntu 24.04 (/usr/bin/python3.12), uv
# 문서:    docs/development/python-env.md
#
# 하는 일
#   1. /usr/bin/python3.12 + --system-site-packages로 venv를 만듭니다(ADR-0002 §4).
#      apt로 설치한 ROS 패키지(rclpy 등)를 venv 안에서도 import할 수 있습니다.
#   2. uv.lock에 적힌 버전 그대로 설치합니다. lock과 pyproject.toml이 안 맞으면 멈춥니다.
#
# venv 위치는 기본 <저장소>/.venv이고, UV_PROJECT_ENVIRONMENT로 바꿀 수 있습니다(컨테이너용).
# 되돌리기: venv 디렉터리를 지우면 끝입니다. 시스템 Python은 건드리지 않습니다.
set -euo pipefail

cd "$(dirname "$0")/.."

PY=/usr/bin/python3.12
VENV="${UV_PROJECT_ENVIRONMENT:-.venv}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv가 설치돼 있지 않습니다. 아래 명령으로 설치하고, 터미널을 새로 연 뒤 다시 실행하세요." >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

if [ ! -x "$PY" ]; then
  echo "$PY 가 없습니다. Ubuntu 24.04에서 실행하고 있는지 확인하세요." >&2
  exit 1
fi

# uv sync만 먼저 실행해서 --system-site-packages 없이 만들어진 venv라면 다시 만듭니다.
if [ -f "$VENV/pyvenv.cfg" ] && ! grep -q '^include-system-site-packages = true' "$VENV/pyvenv.cfg"; then
  echo "$VENV 가 --system-site-packages 없이 만들어져 있어 다시 만듭니다."
  rm -rf "$VENV"
fi

if [ ! -f "$VENV/pyvenv.cfg" ]; then
  uv venv --python "$PY" --system-site-packages "$VENV"
fi

uv sync --locked

echo
echo "완료. 스크립트는 'uv run python <파일>'로 실행하세요(activate 필요 없음)."
