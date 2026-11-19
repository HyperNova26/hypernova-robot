#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""시뮬레이터 비교 기록(runner.enable_trace의 --trace / --hn-trace 출력)을 한 표로 비교합니다. numpy만 씁니다.

  python3 tools/demo/compare_traces.py <시작 s> <끝 s> 라벨=기록파일 [라벨=기록파일 ...]
예: python3 tools/demo/compare_traces.py 10 40 "MuJoCo=a.bin" "Isaac Sim=b.bin" "Isaac Lab=c.bin"

열(창 안의 평균): vx_b 몸통 전진 속도 [m/s], 비율 = vx_b / 명령 vx, ± 표준편차, wz 몸통 yaw 각속도 [rad/s], pitch 몸통 앞기울기 [deg],
보폭Hz = 앞왼쪽 thigh 관절의 지배 주파수, |토크|calf = calf 4개의 평균 |토크| [N m](시뮬레이터가 기록할 때만), |a| = 행동 크기.
정상 상태를 보려고 보통 처음 10 s는 뺍니다. 기록 형식은 파일 옆 <기록파일>.json의 columns를 봅니다.
"""
import json
import sys
from pathlib import Path

import numpy as np

NJ = 12


def load(path):
    meta = json.loads(Path(str(path) + ".json").read_text(encoding="utf-8"))
    cols = meta["columns"]
    a = np.fromfile(path, np.float32)
    a = a[: len(a) // len(cols) * len(cols)].reshape(-1, len(cols))
    return {c: a[:, i] for i, c in enumerate(cols)}, meta["policy_dt_s"]


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    t0, t1 = float(argv[1]), float(argv[2])
    print(f"창 t = {t0:.0f}~{t1:.0f} s")
    print(f"{'구성':24s} {'steps':>5s} {'vx_b':>6s} {'비율':>6s} {'±':>5s} {'wz':>6s} {'pitch':>6s} {'보폭Hz':>6s} {'|토크|calf':>10s} {'|a|':>5s}")
    for item in argv[3:]:
        label, _, path = item.rpartition("=")
        d, dt = load(path)
        m = ((d["step"] * dt) >= t0) & ((d["step"] * dt) < t1)
        if m.sum() < 50:
            print(f"{label:24s} 창에 표본 부족({int(m.sum())})")
            continue
        q4 = d["q4"][m] - d["q4"][m].mean()
        f = np.fft.rfftfreq(len(q4), dt)
        sp = np.abs(np.fft.rfft(q4 * np.hanning(len(q4))))
        sp[f < 0.5] = 0
        calf = np.nanmean([np.nanmean(d[f"tau_prev{i}"][m]) for i in range(8, 12)])
        vx, cmd = float(np.mean(d["vx_b"][m])), float(np.mean(d["cmd_vx"][m]))
        pitch = float(np.degrees(np.mean(np.arcsin(np.clip(-d["gx_b"][m], -1, 1)))))
        a_abs = float(np.mean([np.abs(d[f"a{i}"][m]).mean() for i in range(NJ)]))
        print(f"{label:24s} {int(m.sum()):5d} {vx:6.3f} {vx / cmd:6.3f} {np.std(d['vx_b'][m]):5.3f} {np.mean(d['wz_b'][m]):6.3f} {pitch:6.2f} {f[np.argmax(sp)]:6.2f} {calf:10.2f} {a_abs:5.2f}")


if __name__ == "__main__":
    main(sys.argv)
