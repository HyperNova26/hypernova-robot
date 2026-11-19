# SPDX-License-Identifier: Apache-2.0
"""판정 결과를 JSONL(한 줄에 JSON 하나)로 기록합니다. 코어와 같은 순수 파이썬이라 ROS·시뮬레이터가 필요 없습니다.

기록 종류(`event` 키)
  header      파일 맨 앞 한 줄: 실행 정보(시나리오, 임계값 등 호출자가 넘긴 dict)
  transition  상태가 바뀔 때마다: 이전 상태(from)와 새 보고
  sample      상태가 같을 때 sample_hz(기본 5 Hz) 간격으로 보고
  그 밖       event()로 호출자가 넣는 사건(예: fault_start, fault_end, summary)
시간 `t`는 호출자의 시간(시뮬레이션 시간)입니다. 로그는 저장소가 아니라 데이터 폴더(/data/state_logger/)에 둡니다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .core import State, StatusReport


class JsonlLogger:
    def __init__(self, path: str | Path, *, sample_hz: float = 5.0, header: dict | None = None):
        if not sample_hz > 0:
            raise ValueError("sample_hz는 0보다 커야 합니다")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8", buffering=1)   # 줄 단위 flush: 비정상 종료에도 기록이 남음
        self._sample_dt = 1.0 / sample_hz
        self._last_state: State | None = None
        self._last_sample_t: float | None = None
        self._write({"event": "header", **(header or {})})

    def _write(self, record: dict) -> None:
        self._f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    def log(self, report: StatusReport, extra: dict | None = None) -> None:
        """보고 하나를 넘깁니다. 상태가 바뀌었으면 transition, 아니면 sample 간격이 지났을 때만 sample을 씁니다."""
        record = report.to_dict()
        if extra:
            record["extra"] = dict(extra)
        if report.state != self._last_state:
            self._write({"event": "transition", "from": None if self._last_state is None else self._last_state.name, **record})
            self._last_state, self._last_sample_t = report.state, report.t
        elif self._last_sample_t is None or report.t - self._last_sample_t >= self._sample_dt - 1e-9:
            self._write({"event": "sample", **record})
            self._last_sample_t = report.t

    def event(self, name: str, **fields) -> None:
        self._write({"event": name, **fields})

    def close(self) -> None:
        if not self._f.closed:
            self._f.close()

    def __enter__(self) -> "JsonlLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
