#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
# Python 실행 환경을 선택하고 같은 이름의 구현 파일로 인수를 전달합니다.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ -n "${HN_MAP_PYTHON:-}" ]]; then
    if ! command -v -- "$HN_MAP_PYTHON" >/dev/null 2>&1; then
        printf 'ERROR: HN_MAP_PYTHON is not executable: %s\n' "$HN_MAP_PYTHON" >&2
        exit 2
    fi
    python_command=("$HN_MAP_PYTHON")
elif [[ -x /opt/hn-venv/bin/python ]]; then
    python_command=(/opt/hn-venv/bin/python)
elif command -v uv >/dev/null 2>&1; then
    python_command=(uv run --no-sync --project "$ROOT" python)
else
    printf 'ERROR: Set HN_MAP_PYTHON to the prepared Python interpreter, or provide uv.\n' >&2
    exit 2
fi
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export UV_PYTHON_DOWNLOADS=never

exec "${python_command[@]}" "$ROOT/tools/map/demo_sim_converter.py" "$@"
