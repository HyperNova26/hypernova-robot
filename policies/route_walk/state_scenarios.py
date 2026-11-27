#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""상태 로거(G-006) 시나리오 하네스. 재생기(play_*.py)를 수정하지 않고 감싸서 실행하며, 로봇이 걷는 도중 고장을 넣습니다.

재생기는 세 시뮬레이터 모두 같은 `PolicyRunner.act(state)`를 거칩니다. 이 하네스가 그 한 곳을 감싸서
  1) 정책이 받는 상태 dict를 hn_robot_state 판정기에 넘기고(결과를 JSONL로 기록),
  2) 시나리오에 따라 고장을 넣습니다.
재생기 파일은 읽기만 하고, 자체 낙상 종료 조건(기울기 70°에서 바로 종료)만 메모리에서 제거해서 실행합니다
(그대로면 낙상이 0.2초 지속되는지 볼 수 없음). 해당 줄을 정확히 한 번 찾지 못하면 중단합니다.

  state_scenarios.py --player play_mujoco.py --scenario collapse --at 60 --log out.jsonl -- <재생기 옵션...>   (구분자는 -- 또는 :::)

시나리오
  baseline    고장 없음. 판정기만 붙여 기록합니다(경로 보행 오탐 확인, --expect stand|walk로 기대 상태 검사).
              --stand-s 초 동안은 속도 명령을 0으로 바꿔 서 있게 한 뒤 걷게 합니다(STANDING -> WALKING 확인, 다른 시나리오에서도 쓸 수 있음).
  stale       --at 초부터 --gap 초 동안 판정기에 입력을 주지 않습니다(로봇은 계속 걸음). 감시기가 wall 시간으로 끊김을 알아야 하므로
              그 동안 매 스텝 wall 시간 0.02초를 기다립니다(시뮬레이션이 실시간으로 느려짐).
  collapse    --at 초부터 정책 출력을 주저앉는 자세(thigh/calf 접기)로 바꿉니다. 세 시뮬레이터 공통(act 출력을 바꾸므로).
  flip        --at 초에 몸통 x축(로봇 기준 roll) 각속도를 --flip-rate [rad/s]만큼 한 번 더해 옆으로 뒤집습니다. 세 시뮬레이터 공통
              (재생기의 전역 변수 data / view / robot으로 시뮬레이터에 접근. 로봇이 스스로 일어나면 FALLEN이 풀릴 수 있음).
시간 `t`는 정책 스텝 수 x policy_dt(시뮬레이션 시간)입니다. 위 시나리오는 세 재생기(play_mujoco.py, play_isaacsim.py, play_isaaclab.py) 모두 지원합니다.
창 모드의 화면 표시는 MuJoCo(창 왼쪽 위 글자)와 Isaac Sim/Lab(작은 창 'Locomotion state')을 지원합니다. Isaac Lab은 몸통 접촉 시 환경이 자동 리셋되어 낙상을 볼 수 없으므로
종료 조건(base_contact)만 끄고 실행합니다(apply_policy_io를 감쌈, 재생기 파일은 수정하지 않음).

눈으로 확인하기
  재생기를 창 모드(--headless 없이. 실행기는 HEADLESS=0)로 돌리면 MuJoCo 창 왼쪽 위에 판정 상태가 실시간으로 표시됩니다.
  상태 전환과 고장 시작은 어느 모드에서나 터미널에 한 줄씩 출력합니다.

ROS 발행: --ros-topic /locomotion/status 로 판정 상태를 diagnostic_msgs/DiagnosticArray로 발행합니다(어댑터 hn_robot_state.ros_node).
  창 없는 모드는 시뮬레이션이 실시간보다 빠르므로 ROS 쪽에서 발행 타이밍을 보려면 --realtime을 함께 씁니다.
"""
from __future__ import annotations

import argparse
import atexit
import dataclasses
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "ros_pkgs" / "hn_robot_state"))

import runner as runner_mod  # noqa: E402
from hn_robot_state import DEFAULT_CONFIG_PATH, State, StateEstimator, StaleWatchdog, load_thresholds  # noqa: E402
from hn_robot_state.jsonl_log import JsonlLogger  # noqa: E402

SCENARIOS = ("baseline", "stale", "collapse", "flip")
# 재생기의 자체 낙상 종료 조건(기울기 70°에서 즉시 종료)을 메모리에서만 제거합니다. 파일은 수정하지 않습니다.
# None은 재생기에 그런 종료 조건이 없다는 뜻입니다(Isaac Lab은 환경 종료 조건을 apply_policy_io 감싸기로 끕니다).
FALL_EXIT_PATCHES = {
    "play_mujoco.py": ("if up < math.cos(math.radians(70)) or data.xpos[bid][2] < ground_z - 3.0:",
                       "if data.xpos[bid][2] < ground_z - 3.0:"),
    "play_isaacsim.py": ("if up < math.cos(math.radians(70)) or view.get_root_transforms()[0][2] < (start_z if np.isnan(zg) else float(zg)) - 3.0:",
                         "if view.get_root_transforms()[0][2] < (start_z if np.isnan(zg) else float(zg)) - 3.0:"),
    "play_isaaclab.py": None,
}


def _rot_from_quat_xyzw(q) -> np.ndarray:
    """쿼터니언 (x, y, z, w) -> 몸체에서 world로 가는 회전행렬(Isaac Sim 뷰와 Isaac Lab 3.0은 xyzw 순서)."""
    x, y, z, w = (float(v) for v in q)
    n = (x * x + y * y + z * z + w * w) ** 0.5
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _fmt(value, spec: str) -> str:
    return "-" if value is None else format(value, spec)


_STATE_COLOR = {"INITIALIZING": (110, 110, 110), "STANDING": (30, 90, 200), "WALKING": (30, 150, 60),
                "FALLEN": (200, 30, 30), "STALE_INPUT": (230, 140, 20)}


def parse_args(argv):
    # 하네스 옵션과 재생기 옵션의 구분자: "--" 또는 ":::". isaaclab.sh -p는 맨몸의 "--"를 자체 CLI에서 거부하므로 실행기는 ":::"를 씁니다
    idx = next((i for i, x in enumerate(argv) if x in ("--", ":::")), None)
    own, player = (argv[:idx], argv[idx + 1:]) if idx is not None else (argv, [])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--player", required=True, help="재생기 파일(이 폴더 기준), 예: play_mujoco.py")
    ap.add_argument("--scenario", choices=SCENARIOS, default="baseline")
    ap.add_argument("--at", type=float, default=60.0, help="고장을 넣기 시작하는 시뮬레이션 시간 [s]")
    ap.add_argument("--gap", type=float, default=3.0, help="stale: 입력을 끊는 시간 [s]")
    ap.add_argument("--until", type=float, help="이 시뮬레이션 시간에 실행을 끝냅니다(기본: 고장 시나리오는 고장 끝 + 4 s, baseline은 재생기가 끝낼 때까지)")
    ap.add_argument("--stand-s", type=float, default=0.0, help="처음 이 시간 [s] 동안 정책과 판정기가 받는 속도 명령을 0으로 바꿔 서 있게 합니다(0이면 바로 걷습니다, 0이 아니면 3 s 이상)")
    ap.add_argument("--flip-rate", type=float, default=8.0, help="flip: 몸통 x축(roll)에 한 번 더하는 각속도 [rad/s] (몸체 프레임, 부호는 방향)")
    ap.add_argument("--collapse-thigh", type=float, default=1.6, help="collapse: 모든 thigh 목표 [rad]")
    ap.add_argument("--collapse-calf", type=float, default=-2.7, help="collapse: 모든 calf 목표 [rad]")
    ap.add_argument("--expect", choices=("stand", "walk"), help="baseline: 기대하는 상태를 검사")
    ap.add_argument("--log", help="JSONL 기록 파일(없으면 기록 안 함)")
    ap.add_argument("--sample-hz", type=float, default=5.0, help="JSONL sample 기록 주기 [Hz](분석용으로 50까지 올릴 수 있음)")
    ap.add_argument("--thresholds", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--label", default="")
    ap.add_argument("--latency-max", type=float, default=1.0, help="고장 시작 -> FALLEN 허용 시간 [s](물리적으로 쓰러지는 시간 포함)")
    ap.add_argument("--ros-topic", help="판정 상태를 이 ROS 토픽(diagnostic_msgs/DiagnosticArray)으로 발행합니다. 예: /locomotion/status")
    ap.add_argument("--robot-id", default="hn_v0_go2", help="발행 메시지의 hardware_id")
    ap.add_argument("--realtime", action="store_true", help="창 없는 모드를 실시간(50 Hz)으로 돌립니다(ROS 쪽에서 발행 타이밍을 관찰할 때)")
    a = ap.parse_args(own)
    if Path(a.player).name not in FALL_EXIT_PATCHES:
        ap.error(f"지원하는 재생기: {', '.join(FALL_EXIT_PATCHES)}")
    if a.scenario == "flip" and a.flip_rate == 0.0:
        ap.error("flip 시나리오는 0이 아닌 --flip-rate가 필요합니다")
    if a.stand_s < 0.0 or 0.0 < a.stand_s < 3.0:
        ap.error("--stand-s는 0(바로 걷기)이거나 3 s 이상이어야 합니다(초기화 약 1 s와 정지 판정 0.5 s가 지나야 STANDING이 나옵니다)")
    if a.until is None and a.scenario != "baseline":
        end = a.at + a.gap if a.scenario == "stale" else a.at
        a.until = end + 4.0
    return a, player


class Run:
    """판정기·기록기·고장 주입을 묶은 하나의 실행(env0 하나)."""

    def __init__(self, a):
        self.a = a
        self.cfg = load_thresholds(a.thresholds)
        self.primary = None
        self.io = self.est = self.wd = self.logger = None
        self.step = 0
        self.t = 0.0
        self.in_gap = False
        self.fault_logged = False
        self.records: list[dict] = []
        self.viewer = None            # MuJoCo 창 핸들(창 모드)
        self._finished, self._rc = False, 0
        self._shown_state = None
        self.pub = None               # StatusPublisher(--ros-topic)
        self._t_next = None           # --realtime 페이싱
        self._ui_labels = None        # Isaac Sim/Lab 창의 상태 표시(omni.ui)
        self._player_args = ()
        self.player_globals: dict = {}   # 재생기를 실행하는 전역 이름공간(flip이 data/view/robot에 접근)
        self._flipped = False

    # ------------------------------------------------------------------ 설치
    def install(self, player_args=()) -> None:
        self._player_args = tuple(player_args)
        orig_act = runner_mod.PolicyRunner.act
        run = self

        def act(rs, state):
            if run.primary is None:
                run._start(rs)
            if rs is not run.primary:                      # 첫 러너(env0)만 다룸
                return orig_act(rs, state)
            run.step += 1
            run.t = (run.step - 1) * run.io.policy_dt
            if run.a.realtime:
                run._pace()
            if run.a.until is not None and run.t >= run.a.until:
                run.finish()                       # Kit 등이 정리되기 전에 요약을 내고 ROS 발행을 닫습니다
                raise KeyboardInterrupt()          # 재생기들이 자기 정리 경로로 정상 종료하도록 Ctrl+C와 같은 방식으로 끝냅니다
            if run.t < run.a.stand_s:                      # 대기: 정책과 판정기가 속도 명령 0을 받음(`* 0`은 ndarray·torch 모두 타입을 유지)
                state = {**state, "command": state["command"] * 0}
            run._observe(state, run.t)
            q = orig_act(rs, state)
            if run.a.scenario == "collapse" and run.t >= run.a.at:
                q = run._collapse(rs)
            if run.a.scenario == "flip" and not run._flipped and run.t >= run.a.at:
                run._flip()
            return q

        runner_mod.PolicyRunner.act = act
        if self.a.player.endswith("play_mujoco.py") and "--headless" not in player_args:
            self._install_viewer_hook()
        if self.a.player.endswith("play_isaaclab.py"):
            self._install_isaaclab_no_reset()
            self._install_launch_hook()
        if self.a.player.endswith("play_isaacsim.py"):
            self._install_simapp_close_hook()
        atexit.register(self.finish)                   # sys.exit로 끝나는 경로의 안전망(finish는 여러 번 불러도 한 번만 실행)

    def _install_simapp_close_hook(self) -> None:
        """Isaac Sim 재생기는 루프가 끝나면 app.close()를 부르는데, 이 호출이 프로세스를 끝내 하네스로 돌아오지 못합니다. 닫기 전에 요약을 냅니다."""
        from isaacsim import SimulationApp

        orig, run = SimulationApp.close, self

        def close(app, *args, **kw):
            run.finish()
            return orig(app, *args, **kw)

        SimulationApp.close = close

    def _install_launch_hook(self) -> None:
        """Isaac Lab 재생기: launch_simulation이 끝날 때 Kit 종료로 프로세스가 끝나 하네스로 돌아오지 못하므로, 끝나기 전에 요약을 냅니다."""
        import isaaclab.app as isaaclab_app

        orig, run = isaaclab_app.launch_simulation, self

        class _Wrapped:
            def __init__(self, cm):
                self._cm = cm

            def __enter__(self):
                return self._cm.__enter__()

            def __exit__(self, *exc):
                run.finish()
                return self._cm.__exit__(*exc)

        isaaclab_app.launch_simulation = lambda *a, **kw: _Wrapped(orig(*a, **kw))

    def _install_isaaclab_no_reset(self) -> None:
        """Isaac Lab 재생기: 몸통이 바닥에 닿으면 환경이 자동 리셋되어 낙상이 0.2 s 지속되는지 볼 수 없으므로 종료 조건(base_contact)을 끕니다."""
        import isaaclab_policy_io                      # Isaac Lab 없이도 import됨(numpy와 policy_io만 씀)

        orig = isaaclab_policy_io.apply_policy_io

        def apply(env_cfg, io, *args, **kw):
            orig(env_cfg, io, *args, **kw)
            if getattr(env_cfg.terminations, "base_contact", None) is not None:
                env_cfg.terminations.base_contact = None

        isaaclab_policy_io.apply_policy_io = apply

    def _install_viewer_hook(self) -> None:
        """창 모드: viewer 핸들을 잡아 화면에 상태를 띄우고, 재생기가 창을 닫고 os._exit로 끝나도 요약을 내도록 합니다."""
        try:
            import mujoco.viewer as mj_viewer
        except ImportError:
            return
        orig_launch, run, real_exit = mj_viewer.launch_passive, self, os._exit

        def launch(*args, **kw):
            handle = orig_launch(*args, **kw)
            run.viewer = handle
            return handle

        def hooked_exit(code=0):
            try:
                run.finish()
            finally:
                real_exit(code)

        mj_viewer.launch_passive = launch
        os._exit = hooked_exit

    # ------------------------------------------------------------------ 실행 중
    def _start(self, rs) -> None:
        self.primary, self.io = rs, rs.io
        self.est = StateEstimator(self.cfg, scan_shape=tuple(self.io.hs_shape))
        self.wd = StaleWatchdog(self.cfg.stale_timeout_s)
        if self._windowed_kit():
            self._make_kit_ui()
        if self.a.ros_topic:
            from hn_robot_state.ros_node import StatusPublisher     # rclpy가 있는 환경에서만 import됨

            self.pub = StatusPublisher(topic=self.a.ros_topic, robot_id=self.a.robot_id, stale_provider=self._stale_provider)
            print(f"[STATE] ROS 발행 시작: {self.a.ros_topic} (DiagnosticArray, reliable+transient_local, heartbeat 10 Hz)", flush=True)
        if self.a.log:
            header = {"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"), "scenario": self.a.scenario,
                      "label": self.a.label, "player": self.a.player, "policy_dt_s": self.io.policy_dt,
                      "scan_shape": list(self.io.hs_shape), "args": {k: v for k, v in vars(self.a).items()},
                      "thresholds": dataclasses.asdict(self.cfg)}
            self.logger = JsonlLogger(self.a.log, sample_hz=self.a.sample_hz, header=header)

    def _stale_provider(self):
        """heartbeat 스레드가 부릅니다: 입력이 끊겼으면 STALE_INPUT 보고, 아니면 None."""
        if self.est is not None and self.wd is not None and self.wd.is_stale():
            return self.est.stale_report(self.t, self.wd.silent_s())
        return None

    def _pace(self) -> None:
        now = time.perf_counter()
        if self._t_next is None:
            self._t_next = now
        self._t_next += self.io.policy_dt
        time.sleep(max(0.0, self._t_next - now))

    def fault_active(self, t: float) -> bool:
        a = self.a
        if a.scenario == "stale":
            return a.at <= t < a.at + a.gap
        return a.scenario in ("collapse", "flip") and t >= a.at

    def _record(self, rep, publish: bool = True) -> None:
        f = rep.features
        self.records.append({"t": rep.t, "state": rep.state.name, "reason": rep.reason, "tilt": f.get("tilt_deg"),
                             "height": f.get("height_m"), "ground_ok": f.get("ground_ok"), "h0": f.get("h0_m"),
                             "speed": f.get("speed_mps"), "cmd": f.get("cmd_lin_mps"), "fault": self.fault_active(rep.t)})
        if self.logger:
            self.logger.log(rep, extra={"fault": self.fault_active(rep.t)})
        if self.pub is not None and publish:
            self.pub.publish(rep)
        self._show(rep)

    def _show(self, rep) -> None:
        """상태가 바뀔 때 터미널에 한 줄을 찍고, 창 모드면 화면 글자를 갱신합니다."""
        changed = rep.state != self._shown_state
        f = rep.features
        if changed:
            h, h0 = f.get("height_m"), f.get("h0_m")
            before = "-" if self._shown_state is None else self._shown_state.name
            print(f"[STATE] t={rep.t:7.2f} s  {before} -> {rep.state.name} ({rep.reason})  tilt={_fmt(f.get('tilt_deg'), '.0f')} deg  "
                  f"h/h0={_fmt(h / h0 if h and h0 else None, '.2f')}", flush=True)
            self._shown_state = rep.state
        if self.viewer is not None and (changed or self.step % 5 == 0):
            self._overlay(rep)
        if self._ui_labels is not None and (changed or self.step % 5 == 0):
            self._update_kit_ui(rep)

    def _windowed_kit(self) -> bool:
        """Isaac Sim(--headless 없음) 또는 Isaac Lab(--visualizer kit)을 창 모드로 돌리는 중인가."""
        pa = self._player_args
        if self.a.player.endswith("play_isaacsim.py"):
            return "--headless" not in pa
        if self.a.player.endswith("play_isaaclab.py"):
            for i, x in enumerate(pa):
                if x == "--visualizer" and i + 1 < len(pa):
                    return pa[i + 1] == "kit"
                if x.startswith("--visualizer="):
                    return x.split("=", 1)[1] == "kit"
        return False

    def _make_kit_ui(self) -> None:
        """Kit 창 모드: 판정 상태를 보여 주는 작은 창을 띄웁니다(씬·물리는 건드리지 않음). 실패해도 실행은 계속합니다."""
        try:
            import omni.ui as ui

            self._ui_win = ui.Window("Locomotion state (G-006)", width=360, height=250, position_x=20, position_y=60)
            labels = []
            with self._ui_win.frame:
                with ui.VStack(spacing=3):
                    labels.append(ui.Label("INITIALIZING", height=44, style={"font_size": 34}))
                    for _ in range(6):
                        labels.append(ui.Label("", height=24, style={"font_size": 18}))
            self._ui_labels = labels
            print("[STATE] Kit 창에 상태 표시창('Locomotion state (G-006)')을 만들었습니다", flush=True)
        except Exception as e:   # noqa: BLE001
            print(f"[STATE] 상태 표시창을 만들지 못했습니다(실행은 계속): {e!r}", flush=True)

    def _update_kit_ui(self, rep) -> None:
        f = rep.features
        h, h0 = f.get("height_m"), f.get("h0_m")
        r, g, b = _STATE_COLOR.get(rep.state.name, (255, 255, 255))
        title, *rows = self._ui_labels
        title.text = f"{rep.state.name} ({rep.code})"
        title.style = {"font_size": 34, "color": 0xFF000000 | (b << 16) | (g << 8) | r}      # ABGR
        lines = (f"reason  {rep.reason}", f"tilt/pitch/roll  {_fmt(f.get('tilt_deg'), '.0f')}/{_fmt(f.get('pitch_deg'), '.0f')}/{_fmt(f.get('roll_deg'), '.0f')} deg",
                 f"speed/cmd  {_fmt(f.get('speed_mps'), '.2f')}/{_fmt(f.get('cmd_lin_mps'), '.2f')} m/s", f"height/h0  {_fmt(h / h0 if h and h0 else None, '.2f')}",
                 f"fault  {'ACTIVE ' + self.a.scenario if self.fault_active(rep.t) else '-'}", f"t  {rep.t:.1f} s")
        for label, text in zip(rows, lines):
            label.text = text

    def _overlay(self, rep) -> None:
        import mujoco

        f = rep.features
        h, h0 = f.get("height_m"), f.get("h0_m")
        left = "STATE\nreason\ntilt/pitch/roll\nspeed/cmd\nheight/h0\nfault\nt"
        right = (f"{rep.state.name} ({rep.code})\n{rep.reason}\n"
                 f"{_fmt(f.get('tilt_deg'), '.0f')}/{_fmt(f.get('pitch_deg'), '.0f')}/{_fmt(f.get('roll_deg'), '.0f')} deg\n"
                 f"{_fmt(f.get('speed_mps'), '.2f')}/{_fmt(f.get('cmd_lin_mps'), '.2f')} m/s\n"
                 f"{_fmt(h / h0 if h and h0 else None, '.2f')}\n"
                 f"{'ACTIVE ' + self.a.scenario if self.fault_active(rep.t) else '-'}\n{rep.t:.1f} s")
        self.viewer.set_texts((mujoco.mjtFont.mjFONT_BIG, mujoco.mjtGridPos.mjGRID_TOPLEFT, left, right))

    def _observe(self, state, t: float) -> None:
        a = self.a
        if not self.fault_logged and a.scenario != "baseline" and t >= a.at:
            self.fault_logged = True
            print(f"[STATE] t={t:7.2f} s  ** 고장 시작: {a.scenario} **", flush=True)
            if self.logger:
                self.logger.event("fault_start", t=t, kind=a.scenario)
        if a.scenario == "stale" and a.at <= t < a.at + a.gap:
            self.in_gap = True
            if not self.a.realtime:
                time.sleep(self.io.policy_dt)                 # wall 시간이 지나야 감시기가 끊김을 알 수 있음(--realtime이면 이미 실시간)
            if self.wd.is_stale():
                self._record(self.est.stale_report(t, self.wd.silent_s()), publish=False)   # 발행은 heartbeat 스레드가 함
            return
        if self.in_gap:
            self.in_gap = False
            print(f"[STATE] t={t:7.2f} s  ** 입력 복귀 **", flush=True)
            if self.logger:
                self.logger.event("fault_end", t=t, kind="stale")
        rep = self.est.update(state, t)
        self.wd.feed()
        self._record(rep)

    def _collapse(self, rs) -> np.ndarray:
        io = rs.io
        target = io.default_pos.astype(np.float64).copy()
        for i, joint in enumerate(io.joints):
            if joint.endswith("_hip_joint"):
                target[i] = 0.0
            elif joint.endswith("_thigh_joint"):
                target[i] = self.a.collapse_thigh
            elif joint.endswith("_calf_joint"):
                target[i] = self.a.collapse_calf
        action = ((target - io.default_pos) / io.action_scale).astype(np.float32)
        rs.last_action = action                              # Isaac Lab 재생기는 act()의 반환값이 아니라 last_action을 씁니다
        return io.decode_action(action)

    def _flip(self) -> None:
        """몸통 x축(로봇 기준 roll) 둘레 각속도를 --flip-rate [rad/s]만큼 한 번 더합니다. 세 시뮬레이터에서 같은 몸체 프레임 충격입니다."""
        self._flipped = True
        w, g, player = self.a.flip_rate, self.player_globals, Path(self.a.player).name
        if player == "play_mujoco.py":
            g["data"].qvel[3] += w                                   # free joint의 각속도(qvel[3:6])는 몸체 프레임
        elif player == "play_isaacsim.py":
            view, idx0 = g["view"], g["idx0"]
            vel = np.asarray(view.get_root_velocities(), dtype=np.float32).reshape(1, 6).copy()
            vel[0, 3:] += (_rot_from_quat_xyzw(view.get_root_transforms()[0][3:7]) @ np.array([w, 0.0, 0.0])).astype(np.float32)   # 몸체 -> world
            view.set_root_velocities(vel, idx0)
        else:                                                        # play_isaaclab.py
            import torch

            robot, tt = g["robot"], g["tt"]
            vel = torch.cat([tt(robot.data.root_com_lin_vel_w), tt(robot.data.root_com_ang_vel_w)], dim=1)[:1].clone()
            dw = _rot_from_quat_xyzw(tt(robot.data.root_quat_w)[0].cpu().numpy()) @ np.array([w, 0.0, 0.0])
            vel[0, 3:] += torch.as_tensor(dw, dtype=vel.dtype, device=vel.device)
            robot.write_root_com_velocity_to_sim_index(root_velocity=vel, env_ids=[0])
        print(f"[STATE] t={self.t:7.2f} s  ** flip: 몸통 roll 각속도 {w:+.1f} rad/s 추가 **", flush=True)
        if self.logger:
            self.logger.event("flip", t=self.t, rate_rad_s=w)

    # ------------------------------------------------------------------ 요약
    def _raw_fall(self, r: dict) -> bool:
        c = self.cfg
        if r["tilt"] is not None and r["tilt"] > c.fall_tilt_deg:
            return True
        if r["ground_ok"] is False:
            return True
        return r["h0"] is not None and r["height"] is not None and r["height"] < c.fall_low_height_ratio * r["h0"]

    def finish(self) -> int:
        if self._finished:                                  # 창 모드에서 os._exit 감싸기와 main이 둘 다 부를 수 있음
            return self._rc
        self._finished = True
        self._rc = self._finish()
        return self._rc

    def _finish(self) -> int:
        a = self.a
        if self.est is None:
            print("[STATE] 정책 러너가 한 번도 호출되지 않았습니다(재생기가 일찍 끝났거나 실패)", flush=True)
            return 2
        recs, dt = self.records, self.io.policy_dt
        total = len(recs) * dt
        share = Counter(r["state"] for r in recs)
        print(f"[STATE] 시나리오={a.scenario} 기록 {len(recs)}개(약 {total:.1f} s) | 상태별 시간: "
              + ", ".join(f"{k} {v * dt:.1f}s({v / max(len(recs), 1) * 100:.1f}%)" for k, v in share.most_common()), flush=True)
        trans = [(r1["t"], r0["state"], r1["state"], r1["reason"]) for r0, r1 in zip(recs, recs[1:]) if r0["state"] != r1["state"]]   # 새 상태의 첫 기록 시각
        print(f"[STATE] 상태 전환 {len(trans)}회" + (": " + ", ".join(f"{t:.2f}s {x}->{y}({why})" for t, x, y, why in trans[:12]) if trans else "")
              + (" ..." if len(trans) > 12 else ""), flush=True)
        checks: list[tuple[str, bool, str]] = []
        fallen = [r for r in recs if r["state"] == State.FALLEN.name]
        first_fallen = fallen[0]["t"] if fallen else None
        metrics = {"records": len(recs), "transitions": len(trans), "first_fallen_t": first_fallen}
        # 임계값 여유: 고장 전(baseline은 전체) 구간에서 기준까지 얼마나 남았는지
        pre = recs if a.scenario == "baseline" else [r for r in recs if r["t"] < a.at]
        tilts = [r["tilt"] for r in pre if r["tilt"] is not None]
        ratios = [r["height"] / r["h0"] for r in pre if r["height"] is not None and r["h0"]]
        if tilts:
            metrics.update(pre_tilt_max_deg=max(tilts), pre_tilt_p99_deg=float(np.percentile(tilts, 99)),
                           pre_ground_false_frames=sum(r["ground_ok"] is False for r in pre))
            msg = (f"[STATE] 여유(고장 전 {len(pre)}개): 기울기 최대 {max(tilts):.1f}°/p99 {np.percentile(tilts, 99):.1f}° (낙상 기준 {self.cfg.fall_tilt_deg:.0f}°)")
            if ratios:
                metrics.update(pre_height_ratio_min=min(ratios), pre_height_ratio_p01=float(np.percentile(ratios, 1)))
                msg += f", 높이/h0 최저 {min(ratios):.2f}/p1 {np.percentile(ratios, 1):.2f} (기준 {self.cfg.fall_low_height_ratio:.2f})"
            print(msg + f", 지면 없음 {metrics['pre_ground_false_frames']}프레임", flush=True)
        if a.scenario == "baseline":
            checks.append(("FALLEN 오탐 0프레임", not fallen, f"FALLEN {len(fallen)}프레임"))
            stale = [r for r in recs if r["state"] == State.STALE_INPUT.name]
            checks.append(("STALE_INPUT 0프레임", not stale, f"STALE {len(stale)}프레임"))
            after_init = [r for r in recs if r["state"] != State.INITIALIZING.name]
            if a.expect and after_init:
                want = State.STANDING.name if a.expect == "stand" else State.WALKING.name
                frac = sum(r["state"] == want for r in after_init) / len(after_init)
                need = 0.95 if a.expect == "stand" else 0.5
                checks.append((f"초기화 후 {want} {need * 100:.0f}% 이상", frac >= need, f"{frac * 100:.1f}%"))
            if a.stand_s:
                waited = [r for r in recs if r["t"] < a.stand_s and r["state"] != State.INITIALIZING.name]
                frac = sum(r["state"] == State.STANDING.name for r in waited) / len(waited) if waited else 0.0
                checks.append((f"대기 {a.stand_s:g} s 중 초기화 뒤 STANDING 95% 이상", frac >= 0.95, f"{frac * 100:.1f}%"))
                go = next((r for r in recs if r["t"] >= a.stand_s and (r["cmd"] or 0.0) >= self.cfg.walk_cmd_lin_mps), None)
                if go is not None:                         # 대기가 끝난 뒤 걷는 명령이 나온 경우만(--vmax 0이나 짧은 --until이면 건너뜀)
                    walking = next((r for r in recs if r["t"] >= go["t"] and r["state"] == State.WALKING.name), None)
                    lag = None if walking is None else walking["t"] - go["t"]
                    checks.append(("걷는 명령이 나온 뒤 1.0 s 안에 WALKING", lag is not None and lag <= 1.0, "없음" if lag is None else f"{lag:.2f} s"))
        elif a.scenario == "stale":
            stales = [r for r in recs if r["state"] == State.STALE_INPUT.name]
            first_stale = stales[0]["t"] if stales else None
            checks.append(("STALE_INPUT 보고(끊김 시작 후 1.0 s 안)", first_stale is not None and first_stale - a.at <= 1.0,
                           "없음" if first_stale is None else f"{first_stale - a.at:.2f} s"))
            end = a.at + a.gap
            after = next((r for r in recs if r["t"] >= end and r["state"] != State.STALE_INPUT.name), None)
            checks.append(("입력 복귀 후 1.0 s 안에 STALE 해제", after is not None and after["t"] - end <= 1.0,
                           "없음" if after is None else f"{after['t'] - end:.2f} s"))
            checks.append(("FALLEN 오탐 0프레임", not fallen, f"FALLEN {len(fallen)}프레임"))
            metrics.update(first_stale_t=first_stale)
        else:
            pre = [r for r in fallen if r["t"] < a.at]
            checks.append((f"고장({a.at:.0f} s) 전 FALLEN 오탐 0프레임", not pre, f"{len(pre)}프레임"))
            checks.append(("FALLEN 판정", first_fallen is not None, "없음" if first_fallen is None else f"t={first_fallen:.2f}"))
            if first_fallen is not None:
                checks.append((f"고장 시작 -> FALLEN {a.latency_max:g} s 이내", first_fallen - a.at <= a.latency_max, f"{first_fallen - a.at:.2f} s"))
                # 판정기 지연: FALLEN 직전까지 이어진 연속 낙상 조건 구간의 시작부터 잽니다(격하게 넘어질 때 조건이 중간에 끊길 수 있음)
                j = next(i for i, r in enumerate(recs) if r["t"] == first_fallen)
                while j > 0 and self._raw_fall(recs[j - 1]):
                    j -= 1
                run_start = recs[j]["t"]
                first_raw = next((r["t"] for r in recs if r["t"] >= a.at and self._raw_fall(r)), None)
                broken = first_raw is not None and first_raw < run_start - 1e-9
                checks.append(("연속 낙상 조건 시작 -> FALLEN 0.3 s 이내(debounce 확인)", first_fallen - run_start <= 0.3,
                               f"{first_fallen - run_start:.2f} s (연속 조건 시작 t={run_start:.2f}"
                               + (f", 첫 초과 t={first_raw:.2f}에서 한 번 끊겼다가 재성립" if broken else "") + ")"))
                metrics.update(onset_t=first_raw, run_start_t=run_start)
                held = [r for r in recs if r["t"] >= first_fallen]
                held_s = (held[-1]["t"] - first_fallen) if held else 0.0
                released = next((r for r in held if r["state"] != State.FALLEN.name), None)
                if released is None:
                    checks.append(("FALLEN 3 s 이상 유지", held_s >= 3.0, f"{held_s:.1f} s 동안 유지"))
                elif a.scenario == "flip":      # 충격은 로봇이 스스로 일어날 수 있음: 직립 복구 뒤의 해제는 정상
                    ok_rel = released["tilt"] is not None and released["tilt"] < self.cfg.recover_tilt_deg
                    checks.append(("FALLEN 3 s 이상 유지, 또는 스스로 복구한 뒤 해제", ok_rel,
                                   f"{released['t'] - first_fallen:.1f} s 뒤 해제(복구, 해제 시 기울기 {_fmt(released['tilt'], '.0f')} deg)"))
                else:
                    checks.append(("FALLEN 3 s 이상 유지", False, f"{released['t'] - first_fallen:.1f} s 뒤 풀림"))
                metrics.update(latency_s=first_fallen - a.at)
        if self.pub is not None:
            print(f"[STATE] ROS 발행 {self.pub.sent_count}건({self.a.ros_topic})" + (f", 오류: {self.pub.error!r}" if self.pub.error else ""), flush=True)
            self.pub.close()
        ok = all(c[1] for c in checks)
        for name, passed, detail in checks:
            print(f"[STATE] [{'PASS' if passed else 'FAIL'}] {name}: {detail}", flush=True)
        if self.logger:
            self.logger.event("summary", ok=ok, metrics=metrics, checks=[{"name": n, "pass": p, "detail": d} for n, p, d in checks])
            self.logger.close()
            print(f"[STATE] 기록: {a.log}", flush=True)
        return 0 if ok else 1


def prepare_player(path: Path) -> str:
    """재생기 소스를 읽고(파일은 수정하지 않음) 자체 낙상 종료 조건을 메모리에서 제거합니다. 실행 전에 부르므로 실패해도 실행이 시작되지 않습니다."""
    src = path.read_text(encoding="utf-8")
    if path.name not in FALL_EXIT_PATCHES:
        raise SystemExit(f"[하네스] 지원하지 않는 재생기입니다: {path.name} (지원: {', '.join(FALL_EXIT_PATCHES)})")
    patch = FALL_EXIT_PATCHES[path.name]
    if patch is None:
        return src
    old, new = patch
    if src.count(old) != 1:
        raise SystemExit(f"[하네스] {path.name}에서 낙상 종료 조건을 정확히 한 번 찾지 못했습니다(일치 {src.count(old)}회). "
                         "재생기가 바뀌었다면 FALL_EXIT_PATCHES를 갱신하십시오")
    return src.replace(old, new)


def run_player(path: Path, src: str, player_args: list[str], namespace: dict) -> None:
    sys.argv = [str(path)] + player_args
    namespace.update({"__name__": "__main__", "__file__": str(path), "__builtins__": __builtins__})
    exec(compile(src, str(path), "exec"), namespace)


def main(argv) -> int:
    a, player_args = parse_args(argv)
    path = Path(a.player) if Path(a.player).is_absolute() else HERE / a.player
    if not path.is_file():
        raise SystemExit(f"재생기를 찾지 못했습니다: {path}")
    src = prepare_player(path)
    run = Run(a)
    run.install(player_args)
    try:
        run_player(path, src, player_args, run.player_globals)
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"[STATE] 재생기가 종료 코드 {e.code}로 끝남", flush=True)
    rc = run.finish()
    if run.viewer is not None:       # 창 모드: GLFW 정리 단계의 오류를 피해 재생기처럼 바로 끝냅니다
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
