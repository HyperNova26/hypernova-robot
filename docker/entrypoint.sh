#!/usr/bin/env bash
# 컨테이너의 진입점. 컨테이너를 처음 시작할 때와 ./docker/hn 으로 셸·명령을 열 때마다 실행됩니다.
#
#   1. ROS 환경 (/opt/ros, /opt/hn_ws, 저장소 colcon overlay)       -> env.sh
#   2. 저장소 안의 Python 패키지를 editable로 설치                    -> HN_EDITABLE_PACKAGES가 비어 있으면 아무것도 안 함
#   3. 넘겨받은 명령 실행
set -eo pipefail

# shellcheck source=docker/env.sh
. /opt/hn/env.sh

# HN_EDITABLE_PACKAGES: 저장소 기준 상대 경로를 공백으로 구분(예: "policies/hypernova_tasks").
# HN_EDITABLE_PYTHON:   설치할 interpreter. compose.yaml이 target마다 정합니다(sim: Isaac Lab venv, ros: robot venv).
# 아직 설치할 패키지가 없으므로 지금은 둘 다 비어 있고, 이 블록은 건너뜁니다.
if [ -n "${HN_EDITABLE_PACKAGES:-}" ]; then
  for rel in ${HN_EDITABLE_PACKAGES}; do
    dir="${HN_WORKSPACE:-/workspace/hypernova}/${rel}"
    if [ -f "${dir}/pyproject.toml" ] || [ -f "${dir}/setup.py" ]; then
      "${HN_UV:-uv}" pip install --quiet --python "${HN_EDITABLE_PYTHON:?HN_EDITABLE_PYTHON이 비어 있습니다}" --editable "${dir}" \
        || echo "[hn] 경고: ${rel} editable 설치에 실패했습니다. 계속 진행합니다." >&2
    else
      echo "[hn] 경고: HN_EDITABLE_PACKAGES의 ${rel} 에 pyproject.toml/setup.py가 없습니다." >&2
    fi
  done
fi

exec "$@"
