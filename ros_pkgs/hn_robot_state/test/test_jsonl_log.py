# SPDX-License-Identifier: Apache-2.0
"""hn_robot_state.jsonl_log 단위 시험."""
import json

import pytest

from hn_robot_state import State, StatusReport
from hn_robot_state.jsonl_log import JsonlLogger


def report(t, state=State.WALKING, **features):
    return StatusReport(t=t, state=state, reason="x", since_s=0.0, features={"tilt_deg": 1.0, **features})


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_header_transition_and_sample_rate(tmp_path):
    p = tmp_path / "sub" / "dir" / "log.jsonl"                       # 없는 폴더도 만들어야 함
    with JsonlLogger(p, sample_hz=5.0, header={"scenario": "baseline"}) as log:
        for i in range(0, 101):                                       # 0 ~ 2.0 s, 50 Hz
            log.log(report(i * 0.02))
        log.log(report(2.02, State.FALLEN))
        log.event("fault_start", t=2.0, kind="push")
    rows = read(p)
    assert rows[0] == {"event": "header", "scenario": "baseline"}
    assert rows[1]["event"] == "transition" and rows[1]["from"] is None and rows[1]["state"] == "WALKING"
    samples = [r for r in rows if r["event"] == "sample"]
    assert 8 <= len(samples) <= 11                                    # 2 s 동안 5 Hz
    assert all(b["t"] - a["t"] == pytest.approx(0.2, abs=0.021) for a, b in zip(samples, samples[1:]))
    fallen = next(r for r in rows if r["event"] == "transition" and r["state"] == "FALLEN")
    assert fallen["from"] == "WALKING" and fallen["code"] == 5 and fallen["severity"] == 2
    assert rows[-1] == {"event": "fault_start", "t": 2.0, "kind": "push"}


def test_extra_is_recorded_and_lines_are_flushed(tmp_path):
    p = tmp_path / "log.jsonl"
    log = JsonlLogger(p)
    log.log(report(0.0), extra={"fault": True})
    assert read(p)[1]["extra"] == {"fault": True}                     # close() 전에도 읽힘(줄 단위 flush)
    log.close()
    log.close()                                                       # 두 번 닫아도 안전


def test_nan_is_rejected(tmp_path):
    with JsonlLogger(tmp_path / "log.jsonl") as log:
        with pytest.raises(ValueError):
            log.log(report(0.0, tilt_nan=float("nan")))


def test_invalid_sample_rate(tmp_path):
    with pytest.raises(ValueError):
        JsonlLogger(tmp_path / "x.jsonl", sample_hz=0)
