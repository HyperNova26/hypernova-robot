#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""상태 로거(G-006) 시험 하네스. 재생기(play_*.py)를 수정하지 않고 감싸서 실행하며, 로봇이 걷는 도중 고장을 넣습니다.

보통은 tools/demo/run_route.sh가 기본으로 부릅니다(STATE=0이면 하네스 없이 재생기만). 직접 부를 때:
  state_scenarios.py --player play_mujoco.py [하네스 옵션...] ::: <재생기 옵션...>     (구분자는 ::: 또는 --)

재생기는 세 시뮬레이터 모두 같은 `PolicyRunner.act(state)`를 거칩니다. 이 하네스가 그 한 곳을 감싸서
  1) 정책이 받는 상태 dict를 hn_robot_state 판정기에 넘기고(결과를 터미널·JSONL·ROS로 냄),
  2) 고장을 넣습니다. 고장은 한 줄(queue)로 들어오고 매 정책 스텝 시작에 시뮬레이션 루프 안에서 적용합니다.
     들어오는 곳은 둘입니다: 예약(--scenario 종류 --at 초)과 ROS 서비스(--ros일 때 /sim/inject_fault, hn_interfaces/srv/InjectFault).
재생기 파일은 읽기만 하고, 자체 낙상 종료 조건(기울기 70°에서 바로 종료)만 메모리에서 제거해서 실행합니다
(그대로면 낙상이 0.2초 지속되는지 볼 수 없음). 해당 줄을 정확히 한 번 찾지 못하면 중단합니다.

고장 종류(세 시뮬레이터 공통)
  collapse  정책 출력을 주저앉는 자세(모든 thigh/calf 접기)로 바꿉니다. 기대 상태 FALLEN(low_height).
  flip      몸통 x축(로봇 기준 roll) 각속도를 한 번 더해 옆으로 뒤집습니다(재생기의 전역 변수 data / view / robot으로 접근). 기대 상태 FALLEN(tilt).
            로봇이 스스로 일어나면 FALLEN이 풀릴 수 있습니다.
  stale     판정기에 입력을 주지 않습니다(로봇은 계속 걸음). 감시기가 wall 시간으로 끊김을 알아야 하므로 창 없는 모드에서는
            그 동안 매 스텝 wall 시간 0.02초를 기다립니다. 기대 상태 STALE_INPUT.
  push      몸통 질량 중심에 수평 외력 [N]을 정해진 시간(기본 0.2 s) 동안 겁니다. 방향은 넣는 순간 로봇이 보는 방향 기준(0 = 앞, 90 = 왼쪽).
            세 시뮬레이터 모두 world 좌표계의 같은 힘입니다(MuJoCo xfrc_applied, Isaac Lab permanent wrench, Isaac Sim은 물리 스텝마다 적용).
            결과는 힘에 따라 다릅니다(버티면 WALKING/TILTING, 못 버티면 FALLEN). 요약은 PASS/FAIL이 아니라 결과(INFO)를 적습니다.
  tilt      한쪽 다리(thigh/calf)를 접고 반대쪽 다리를 펴서 몸통을 옆으로 기울이고, 목표 roll [deg]에 머물도록 정도를 조절합니다.
            v1(HYPER)은 최대로 기울여도 약 40°입니다(MuJoCo, 2026-11-19). 기대 상태 TILTING.
            고장이 끝나면 정책이 다시 걷게 하고, TILTING이 풀리는지 봅니다.
  clear     진행 중인 고장을 모두 끝냅니다(서비스 전용). 로봇 자세는 그대로입니다.
  reset     진행 중인 고장을 모두 끝내고 로봇을 지금 x, y에 다시 세웁니다(서비스 전용): 지면 위 0.40 m(시작과 같음), 지금 방향, 관절 기본 자세, 속도 0.
            판정기는 그대로 두므로 FALLEN이었다면 직립 1 s 뒤에 풀립니다. 경로는 이어서 걷습니다.
collapse, stale, tilt는 지속 시간(0이면 clear나 실행 끝까지)이 있고(push는 0이면 기본 0.2 s), collapse와 tilt는 다리 자세를 덮어쓰므로 하나만 진행됩니다.
시간 `t`는 정책 스텝 수 x policy_dt(시뮬레이션 시간)입니다.

화면 표시: MuJoCo는 창 왼쪽 위 글자, Isaac Sim/Lab은 작은 창 'Locomotion state'. 상태 전환과 고장 시작·끝은 터미널에 한 줄씩 출력합니다.
Isaac Lab은 몸통 접촉 시 환경이 자동 리셋되어 낙상을 볼 수 없으므로 종료 조건(base_contact)만 끄고 실행합니다(apply_policy_io를 감쌈).
끝나면(--until, 도착, 창 닫기, Ctrl+C) 요약과 PASS/FAIL 검사를 출력합니다. 고장마다 기대 상태가 나왔는지, 고장 전 오탐이 없었는지 봅니다.

ROS(--ros): 판정 상태를 /locomotion/status(hn_interfaces/LocomotionStatus)로 발행하고, /clock(시뮬레이션 시간)을 정책 스텝마다 내고,
  고장 주입 서비스 /sim/inject_fault를 엽니다. hn_interfaces는 colcon으로 먼저 빌드합니다. 창 없는 모드는 실시간보다 빠르므로
  ROS 쪽에서 타이밍을 보려면 --realtime을 함께 씁니다.
"""
from __future__ import annotations

import argparse
import atexit
import dataclasses
import math
import os
import queue
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

FAULTS = ("collapse", "flip", "stale", "tilt", "push")
SCENARIOS = ("baseline",) + FAULTS
CONTROLS = ("clear", "reset")                  # 고장이 아니라 고장을 끝내는 요청(서비스 전용)
POSE_FAULTS = ("collapse", "tilt")            # 정책 출력(다리 자세)을 덮어쓰는 고장. 한 번에 하나만
RESET_DROP_M = 0.40                           # reset: 지면 위 이 높이에서 놓습니다(재생기의 시작 높이와 같음)
DEFAULT_DURATION_S = {"collapse": 0.0, "flip": 0.0, "stale": 3.0, "tilt": 5.0, "push": 0.2}   # 예약 고장(--scenario)의 기본 지속 시간. 0 = 실행 끝까지
PUSH_REPORT_S = 3.0                           # push: 힘을 건 뒤 이 시간 동안의 결과(최대 기울기, 상태)를 요약에 적음 [s]
STALE_RELEASE_S = 1.0                         # stale: 끊김 시작 -> STALE_INPUT, 복귀 -> 해제 허용 시간 [s]
TILT_CLEAR_CHECK_S = 3.0                      # tilt: 고장이 끝난 뒤 TILTING이 풀려야 하는 시간 [s]
# tilt 자세 조절: 접는 정도(0~1)의 변화율 = clip(GAIN x (목표 roll - 예측 roll), -UNFOLD, +FOLD) [1/s]. 걷던 관성으로 넘어지지 않게 천천히 접고 빨리 폅니다
TILT_GAIN, TILT_FOLD_RATE, TILT_UNFOLD_RATE, TILT_LOOKAHEAD_S = 0.05, 0.5, 2.0, 0.3
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


_STATE_COLOR = {"INITIALIZING": (110, 110, 110), "STANDING": (30, 90, 200), "WALKING": (30, 150, 60), "TILTING": (220, 190, 20),
                "FALLEN": (200, 30, 30), "STALE_INPUT": (230, 140, 20)}


def parse_args(argv):
    # 하네스 옵션과 재생기 옵션의 구분자: "--" 또는 ":::". isaaclab.sh -p는 맨몸의 "--"를 자체 CLI에서 거부하므로 실행기는 ":::"를 씁니다
    idx = next((i for i, x in enumerate(argv) if x in ("--", ":::")), None)
    own, player = (argv[:idx], argv[idx + 1:]) if idx is not None else (argv, [])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--player", required=True, help="재생기 파일(이 폴더 기준), 예: play_mujoco.py")
    ap.add_argument("--scenario", choices=SCENARIOS, default="baseline", help="예약 고장 종류(baseline이면 예약 없음. 서비스로는 언제든 넣을 수 있음)")
    ap.add_argument("--at", type=float, default=8.0, help="예약 고장을 넣는 시뮬레이션 시간 [s]")
    ap.add_argument("--duration", type=float, help="예약 고장의 지속 시간 [s](0이면 실행 끝까지). 기본: stale 3, tilt 5, collapse 0")
    ap.add_argument("--until", type=float, help="이 시뮬레이션 시간에 실행을 끝냅니다(기본: 예약 고장은 고장 끝 + 4 s, 그 밖에는 재생기가 끝낼 때까지)")
    ap.add_argument("--stand-s", type=float, default=0.0, help="처음 이 시간 [s] 동안 정책과 판정기가 받는 속도 명령을 0으로 바꿔 서 있게 합니다(0이면 바로 걷습니다, 0이 아니면 3 s 이상)")
    ap.add_argument("--flip-rate", type=float, default=36.0, help="flip: 몸통 x축(roll)에 한 번 더하는 각속도 [rad/s] (몸체 프레임, 부호는 방향). 서비스의 magnitude 0일 때도 이 값. "
                    "run_route.sh는 시뮬레이터별 값을 넘깁니다(v1이 누운 채 남는 범위가 시뮬레이터마다 다름)")
    ap.add_argument("--tilt-deg", type=float, default=45.0, help="tilt: 목표 roll [deg](양수 = 오른쪽이 내려감). 서비스의 magnitude 0일 때도 이 값. 못 미치면 최대로 기운 자세에 머묾")
    ap.add_argument("--tilt-up-thigh", type=float, default=0.5, help="tilt: 올라가는 쪽 다리를 편 thigh 목표 [rad]")
    ap.add_argument("--tilt-up-calf", type=float, default=-1.0, help="tilt: 올라가는 쪽 다리를 편 calf 목표 [rad]")
    ap.add_argument("--push-n", type=float, default=100.0, help="push: 힘 [N]. 서비스의 magnitude 0일 때도 이 값")
    ap.add_argument("--push-s", type=float, default=0.2, help="push: 미는 시간 [s]. 서비스의 duration_s 0일 때도 이 값")
    ap.add_argument("--push-dir-deg", type=float, default=90.0, help="push: 예약 고장(--scenario push)의 방향 [deg](0 = 앞, 90 = 왼쪽). 서비스는 direction_deg 필드")
    ap.add_argument("--collapse-thigh", type=float, default=1.6, help="collapse·tilt: 접은 thigh 목표 [rad]")
    ap.add_argument("--collapse-calf", type=float, default=-2.7, help="collapse·tilt: 접은 calf 목표 [rad]")
    ap.add_argument("--expect", choices=("stand", "walk"), help="고장 전 구간에서 기대하는 상태를 검사")
    ap.add_argument("--log", help="JSONL 기록 파일(없으면 기록 안 함)")
    ap.add_argument("--sample-hz", type=float, default=5.0, help="JSONL sample 기록 주기 [Hz](분석용으로 50까지 올릴 수 있음)")
    ap.add_argument("--thresholds", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--label", default="")
    ap.add_argument("--latency-max", type=float, default=1.0, help="collapse·flip: 고장 시작 -> FALLEN 허용 시간 [s](물리적으로 쓰러지는 시간 포함)")
    ap.add_argument("--tilt-latency-max", type=float, default=3.0, help="tilt: 고장 시작 -> TILTING 허용 시간 [s](다리를 천천히 접는 약 2 s 포함)")
    ap.add_argument("--ros", action="store_true", help="ROS를 켭니다: 상태 발행(--ros-topic), /clock 발행, 고장 주입 서비스 /sim/inject_fault")
    ap.add_argument("--ros-topic", default="/locomotion/status", help="--ros일 때 상태를 발행할 토픽(hn_interfaces/LocomotionStatus)")
    ap.add_argument("--fault-service", default="/sim/inject_fault", help="--ros일 때 고장 주입 서비스 이름")
    ap.add_argument("--stamp", choices=("system", "sim"), default="system",
                    help="상태 메시지 header.stamp: system = 시스템 시간(ADR-0004 기본), sim = 시뮬레이션 시간(/clock과 같은 시간)")
    ap.add_argument("--robot-id", default="hn_v1_hyper", help="발행 메시지의 robot_id")
    ap.add_argument("--realtime", action="store_true", help="창 없는 모드를 실시간(50 Hz)으로 돌립니다(ROS 쪽에서 타이밍을 관찰할 때)")
    ap.add_argument("--exit-on-fall", type=float, default=0.0,
                    help="고장을 넣지 않았는데 FALLEN이 이 시간 [s] 이어지면 끝냅니다(0이면 끄기). 창 없는 경로 보행이 넘어진 채 끝나지 않는 것을 막습니다")
    a = ap.parse_args(own)
    if Path(a.player).name not in FALL_EXIT_PATCHES:
        ap.error(f"지원하는 재생기: {', '.join(FALL_EXIT_PATCHES)}")
    if a.flip_rate == 0.0:
        ap.error("--flip-rate는 0이 아니어야 합니다")
    if not 0.0 < abs(a.tilt_deg) < 90.0:
        ap.error("--tilt-deg는 0이 아니고 절댓값이 90 미만이어야 합니다")
    if not (a.push_n > 0.0 and a.push_s > 0.0):
        ap.error("--push-n, --push-s는 0보다 커야 합니다")
    if a.stand_s < 0.0 or 0.0 < a.stand_s < 3.0:
        ap.error("--stand-s는 0(바로 걷기)이거나 3 s 이상이어야 합니다(초기화 약 1 s와 정지 판정 0.5 s가 지나야 STANDING이 나옵니다)")
    if a.duration is None:
        a.duration = DEFAULT_DURATION_S.get(a.scenario, 0.0)
    if a.duration < 0.0:
        ap.error("--duration은 0 이상이어야 합니다")
    if a.until is None and a.scenario != "baseline":
        a.until = a.at + a.duration + 4.0
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
        self.records: list[dict] = []
        self.viewer = None            # MuJoCo 창 핸들(창 모드)
        self._finished, self._rc = False, 0
        self._shown_state = None
        self.pub = None               # StatusPublisher(--ros)
        self.ros = None               # SimRos: /clock, 고장 주입 서비스(--ros)
        self._t_next = None           # --realtime 페이싱
        self._ui_labels = None        # Isaac Sim/Lab 창의 상태 표시(omni.ui)
        self._player_args = ()
        self.player_globals: dict = {}   # 재생기를 실행하는 전역 이름공간(flip이 data/view/robot에 접근)
        # 고장: 요청 줄(서비스 스레드 -> 시뮬레이션 루프), 진행 중인 고장, 지나간 고장 기록
        self.requests: queue.SimpleQueue = queue.SimpleQueue()
        self.active: dict[str, dict] = {}
        self.events: list[dict] = []
        self._scheduled = a.scenario == "baseline"     # 예약 고장을 이미 넣었는가
        self._roll_deg = 0.0           # 이번 스텝 입력의 roll [deg](tilt 조절용)
        self._prev_roll = None
        self._tilt_frac = 0.0          # tilt: 내려가는 쪽 다리를 접은 정도(0 = 기본 자세, 1 = collapse 자세)
        self._push_force = None        # push: world 좌표계 힘 [N](Isaac Sim은 물리 스텝마다 이 값을 다시 겁니다)
        self._push_ctx = None          # push: 시뮬레이터별 준비물(Isaac Sim 링크 번호, Isaac Lab 몸통 번호 등)
        self._hold_default_once = False  # reset 직후 한 스텝은 정책 대신 기본 자세를 냅니다(정책 입력이 reset 전 상태이므로)

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
            if run.ros is not None:
                run.ros.publish_clock(run.t)
            if run.a.until is not None and run.t >= run.a.until:
                run.finish()                       # Kit 등이 정리되기 전에 요약을 내고 ROS 발행을 닫습니다
                raise KeyboardInterrupt()          # 재생기들이 자기 정리 경로로 정상 종료하도록 Ctrl+C와 같은 방식으로 끝냅니다
            run._prev_roll, run._roll_deg = run._roll_deg, run._roll_of(state)
            run._process_faults()
            if run.t < run.a.stand_s:                      # 대기: 정책과 판정기가 속도 명령 0을 받음(`* 0`은 ndarray·torch 모두 타입을 유지)
                state = {**state, "command": state["command"] * 0}
            run._observe(state, run.t)
            if run._fell_without_fault():
                run.finish()
                raise KeyboardInterrupt()
            q = orig_act(rs, state)
            if "collapse" in run.active:
                q = run._override(rs, run._collapse_target(rs.io))
            elif "tilt" in run.active:
                q = run._override(rs, run._tilt_target(rs.io))
            if run._hold_default_once:
                run._hold_default_once = False
                q = run._override(rs, rs.io.default_pos.astype(np.float64).copy())
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
        if self.a.ros:
            from hn_robot_state.ros_node import StatusPublisher     # rclpy가 있는 환경에서만 import됨
            from sim_ros import SimRos

            stamp = (lambda rep: int(round(rep.t * 1e9))) if self.a.stamp == "sim" else None
            self.pub = StatusPublisher(topic=self.a.ros_topic, robot_id=self.a.robot_id, stale_provider=self._stale_provider, stamp_ns=stamp)
            self.ros = SimRos(on_request=self.request, sim_time=lambda: self.t, service=self.a.fault_service)
            print(f"[STATE] ROS: 상태 {self.a.ros_topic}(hn_interfaces/LocomotionStatus, stamp={self.a.stamp}), /clock, "
                  f"고장 주입 서비스 {self.a.fault_service}(hn_interfaces/srv/InjectFault). robot_id={self.a.robot_id}", flush=True)
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

    def _fell_without_fault(self) -> bool:
        """--exit-on-fall: 고장 없이 넘어진 채 정해진 시간이 지났는가(재생기의 원래 넘어짐 종료를 대신함)."""
        limit = self.a.exit_on_fall
        if limit <= 0.0 or self.events or not self.records or self.records[-1]["state"] != State.FALLEN.name:
            return False
        if self.records[-1]["since"] < limit:
            return False
        print(f"[STATE] t={self.t:7.2f} s  고장 없이 넘어진 채 {limit:g} s가 지나 끝냅니다(--exit-on-fall)", flush=True)
        return True

    def _pace(self) -> None:
        now = time.perf_counter()
        if self._t_next is None:
            self._t_next = now
        self._t_next += self.io.policy_dt
        time.sleep(max(0.0, self._t_next - now))

    @staticmethod
    def _roll_of(state) -> float:
        g = np.asarray(state["projected_gravity_b"], dtype=float).reshape(-1)
        return math.degrees(math.atan2(-g[1], -g[2]))

    # ------------------------------------------------------------------ 고장
    def request(self, kind: str, magnitude: float = 0.0, duration_s: float = 0.0, source: str = "service",
                direction_deg: float = 0.0) -> tuple[bool, str]:
        """고장 요청을 접수합니다(어느 스레드에서 불러도 됨). 적용은 시뮬레이션 루프가 다음 정책 스텝 시작에 합니다."""
        if kind not in FAULTS + CONTROLS:
            return False, f"모르는 kind '{kind}'. {', '.join(FAULTS + CONTROLS)} 중 하나"
        if not (math.isfinite(magnitude) and math.isfinite(duration_s) and math.isfinite(direction_deg)) or duration_s < 0.0:
            return False, "magnitude, duration_s, direction_deg는 유한해야 하고 duration_s는 0 이상이어야 합니다"
        if kind == "push" and magnitude < 0.0:
            return False, "push의 magnitude(힘)는 0 이상이어야 합니다. 방향은 direction_deg로 정합니다"
        if kind == "tilt" and magnitude != 0.0 and not abs(magnitude) < 90.0:
            return False, "tilt의 magnitude(목표 roll)는 절댓값이 90 미만이어야 합니다"
        self.requests.put((kind, float(magnitude), float(duration_s), source, float(direction_deg)))
        return True, f"{kind} 접수(다음 정책 스텝에 적용)"

    def _process_faults(self) -> None:
        a, t = self.a, self.t
        if not self._scheduled and t >= a.at:
            self._scheduled = True
            mag = {"flip": a.flip_rate, "tilt": a.tilt_deg, "push": a.push_n}.get(a.scenario, 0.0)
            self.request(a.scenario, mag, a.duration, source="schedule", direction_deg=a.push_dir_deg)
        while True:
            try:
                kind, mag, dur, source, direction = self.requests.get_nowait()
            except queue.Empty:
                break
            self._apply(kind, mag, dur, source, direction)
        for kind in [k for k, f in self.active.items() if f["t_end"] is not None and t >= f["t_end"] - 1e-9]:
            self._end(kind)

    def _apply(self, kind: str, mag: float, dur: float, source: str, direction: float = 0.0) -> None:
        t = self.t
        if kind in CONTROLS:
            ended = list(self.active)
            for k in ended:
                self._end(k)
            print(f"[STATE] t={t:7.2f} s  ** {kind}: 끝낸 고장 {', '.join(ended) if ended else '없음'} **", flush=True)
            if kind == "reset":
                where = self._reset_robot()
                self.primary.reset()                     # 정책의 직전 행동 관측을 0으로
                self._hold_default_once = True
                self.events.append({"kind": "reset", "t0": t, "t1": t, "magnitude": 0.0, "duration_s": 0.0, "source": source})
                print(f"[STATE] t={t:7.2f} s  ** reset: 로봇을 다시 세움 {where} **", flush=True)
                if self.logger:
                    self.logger.event("reset", t=t, source=source)
            return
        if kind == "flip":
            mag = mag or self.a.flip_rate
            self._flip(mag)
            ev = {"kind": kind, "t0": t, "t1": t, "magnitude": mag, "duration_s": 0.0, "source": source}
        else:
            if kind == "tilt":
                mag = mag or self.a.tilt_deg
            if kind == "push":
                mag, dur = mag or self.a.push_n, dur or self.a.push_s
            for k in ([kind] + [p for p in POSE_FAULTS if kind in POSE_FAULTS and p != kind]):
                if k in self.active:
                    self._end(k)
            ev = {"kind": kind, "t0": t, "t1": None, "magnitude": mag, "duration_s": dur, "source": source}
            if kind == "push":
                ev["direction_deg"] = direction
                self._push_start(mag, direction)
            self.active[kind] = {"t_end": t + dur if dur > 0.0 else None, "event": ev}
            if kind == "tilt":
                self._tilt_frac = 0.0
        self.events.append(ev)
        what = {"collapse": f"주저앉기(thigh {self.a.collapse_thigh:g}, calf {self.a.collapse_calf:g} rad)",
                "flip": f"몸통 roll 각속도 {mag:+.1f} rad/s 한 번",
                "stale": "판정기 입력 끊기",
                "tilt": f"한쪽 다리 접기, 목표 roll {mag:+.0f}°({'오른쪽' if mag > 0 else '왼쪽'}이 내려감)",
                "push": f"몸통에 {mag:g} N, 방향 {direction:+.0f}°(0 앞, 90 왼쪽)"}[kind]
        until = "" if kind == "flip" else (f", {dur:g} s 동안" if dur > 0.0 else ", clear까지")
        print(f"[STATE] t={t:7.2f} s  ** 고장 시작({source}): {kind} - {what}{until} **", flush=True)
        if self.records and self.records[-1]["state"] == State.INITIALIZING.name:
            ev["during_init"] = True
            print("[STATE]             주의: 판정기가 아직 초기화 중(INITIALIZING)입니다. 초기화는 직립 1 s가 지나야 끝나고, "
                  "그 전에는 TILTING·STANDING·WALKING을 내지 않습니다(FALLEN은 냄)", flush=True)
        if self.logger:
            self.logger.event("fault_start", t=t, kind=kind, magnitude=mag, duration_s=dur, source=source)

    def _end(self, kind: str) -> None:
        f = self.active.pop(kind)
        f["event"]["t1"] = self.t
        if kind == "push":
            self._set_push_force(None)
        print(f"[STATE] t={self.t:7.2f} s  ** 고장 끝: {kind}" + (" (입력 복귀)" if kind == "stale" else "") + " **", flush=True)
        if self.logger:
            self.logger.event("fault_end", t=self.t, kind=kind)

    def _override(self, rs, target: np.ndarray) -> np.ndarray:
        io = rs.io
        action = ((target - io.default_pos) / io.action_scale).astype(np.float32)
        rs.last_action = action                              # Isaac Lab 재생기는 act()의 반환값이 아니라 last_action을 씁니다
        return io.decode_action(action)

    def _collapse_target(self, io) -> np.ndarray:
        target = io.default_pos.astype(np.float64).copy()
        for i, joint in enumerate(io.joints):
            if joint.endswith("_hip_joint"):
                target[i] = 0.0
            elif joint.endswith("_thigh_joint"):
                target[i] = self.a.collapse_thigh
            elif joint.endswith("_calf_joint"):
                target[i] = self.a.collapse_calf
        return target

    def _tilt_target(self, io) -> np.ndarray:
        """목표 roll 쪽(양수면 오른쪽 FR/RR, 음수면 왼쪽 FL/RL) 다리의 thigh/calf를 접고 반대쪽 다리는 폅니다.
        접고 펴는 정도(0~1)는 roll 오차로 조절합니다(TILT_*). 목표에 못 미치면 1(최대로 기운 자세)에 머뭅니다."""
        goal = self.active["tilt"]["event"]["magnitude"]
        sign = math.copysign(1.0, goal)
        rate = 0.0 if self._prev_roll is None else (self._roll_deg - self._prev_roll) / self.io.policy_dt
        err = abs(goal) - sign * (self._roll_deg + TILT_LOOKAHEAD_S * rate)   # 목표 쪽으로 덜 기울었으면 양수. 기우는 속도만큼 앞을 내다봄(넘침 방지)
        self._tilt_frac = float(np.clip(self._tilt_frac + np.clip(TILT_GAIN * err, -TILT_UNFOLD_RATE, TILT_FOLD_RATE) * self.io.policy_dt, 0.0, 1.0))
        down = ("FR_", "RR_") if goal > 0 else ("FL_", "RL_")
        target = io.default_pos.astype(np.float64).copy()
        fold = self._collapse_target(io)
        for i, joint in enumerate(io.joints):
            if joint.endswith("_hip_joint"):
                continue
            if joint.startswith(down):
                goal_q = fold[i]
            else:
                goal_q = self.a.tilt_up_thigh if joint.endswith("_thigh_joint") else self.a.tilt_up_calf
            target[i] += self._tilt_frac * (goal_q - target[i])
        return target

    # ------------------------------------------------------------------ 외력(push)
    def _root_rot(self) -> np.ndarray:
        """몸통(루트 링크)의 몸체 -> world 회전행렬."""
        g, player = self.player_globals, Path(self.a.player).name
        if player == "play_mujoco.py":
            return np.asarray(g["data"].xmat[g["bid"]], dtype=float).reshape(3, 3)
        if player == "play_isaacsim.py":
            return _rot_from_quat_xyzw(g["view"].get_root_transforms()[0][3:7])
        robot, tt = g["robot"], g["tt"]
        return _rot_from_quat_xyzw(tt(robot.data.root_quat_w)[0].cpu().numpy())

    def _push_start(self, force_n: float, direction_deg: float) -> None:
        R = self._root_rot()
        ang = math.atan2(R[1, 0], R[0, 0]) + math.radians(direction_deg)    # 로봇이 보는 방향 + direction (수평)
        self._set_push_force(np.array([force_n * math.cos(ang), force_n * math.sin(ang), 0.0]))

    def _set_push_force(self, f) -> None:
        """world 좌표계 힘 f [N]을 몸통 질량 중심에 겁니다(None이면 뗌)."""
        g, player = self.player_globals, Path(self.a.player).name
        self._push_force = None if f is None else np.asarray(f, dtype=float)
        if player == "play_mujoco.py":                               # xfrc_applied는 다음에 바꿀 때까지 매 mj_step에 질량 중심으로 적용됨
            g["data"].xfrc_applied[g["bid"], :3] = 0.0 if f is None else self._push_force
        elif player == "play_isaaclab.py":                           # permanent wrench는 reset할 때까지 매 물리 스텝에 적용됨
            import torch

            robot = g["robot"]
            if self._push_ctx is None:
                dev = g["tt"](robot.data.root_quat_w).device
                self._push_ctx = {"body": [robot.body_names.index(self.io.root_link)], "env": torch.tensor([0], device=dev), "dev": dev}
            c, comp = self._push_ctx, robot.permanent_wrench_composer
            if f is None:
                comp.reset(env_ids=c["env"])
            else:
                forces = torch.tensor(self._push_force, dtype=torch.float32, device=c["dev"]).view(1, 1, 3)
                comp.set_forces_and_torques_index(forces=forces, torques=torch.zeros_like(forces), body_ids=c["body"], env_ids=c["env"], is_global=True)
        elif f is not None and self._push_ctx is None:              # Isaac Sim: PhysX는 힘을 한 스텝만 적용하므로 sim.step마다 다시 겁니다
            self._install_isaacsim_push()

    def _install_isaacsim_push(self) -> None:
        g, run = self.player_globals, self
        view, sim = g["view"], g["sim"]
        names = list(view.shared_metatype.link_names)
        root = names.index(self.io.root_link) if self.io.root_link in names else 0
        self._push_ctx = {"root": root, "n": len(names)}
        orig_step = sim.step

        def step(*args, **kw):
            if run._push_force is not None:
                run._isaacsim_apply_push()
            return orig_step(*args, **kw)

        sim.step = step

    def _isaacsim_apply_push(self) -> None:
        g, c = self.player_globals, self._push_ctx
        view = g["view"]
        tf = np.asarray(view.get_link_transforms(), dtype=np.float64).reshape(1, -1, 7)[0, c["root"]]
        com = np.asarray(view.get_coms(), dtype=np.float64).reshape(1, -1, 7)[0, c["root"]]
        pos = tf[:3] + _rot_from_quat_xyzw(tf[3:7]) @ com[:3]         # 링크 질량 중심(world). 위치를 안 주면 링크 원점에 걸림
        force = np.zeros((1, c["n"], 3), np.float32)
        where = np.zeros((1, c["n"], 3), np.float32)
        force[0, c["root"]], where[0, c["root"]] = self._push_force, pos
        if g.get("GPU"):
            import torch

            force, where = (torch.as_tensor(x, device="cuda:0") for x in (force, where))
            idx = torch.as_tensor(g["idx0"], dtype=torch.int32, device="cuda:0")
        else:
            idx = g["idx0"]
        view.apply_forces_and_torques_at_position(force, None, where, idx, True)

    def _reset_robot(self) -> str:
        """로봇을 지금 x, y에 똑바로 다시 세웁니다(지면 위 RESET_DROP_M, 지금 yaw, 관절 기본 자세, 속도 0). 놓은 위치를 글로 돌려줍니다."""
        g, player, io = self.player_globals, Path(self.a.player).name, self.io
        R = self._root_rot()
        yaw = math.atan2(R[1, 0], R[0, 0])
        qw, qz = math.cos(yaw / 2), math.sin(yaw / 2)
        for buf in g.get("_tau_q", []):                              # 토크 지연 버퍼(--torque-delay)에 남은 넘어지기 전 토크를 비움
            buf[:] = 0.0
        if player == "play_mujoco.py":
            import mujoco

            model, data, bid = g["model"], g["data"], g["bid"]
            x, y = (float(v) for v in data.xpos[bid][:2])
            gz = g["ground_at"](x, y)
            z = (g["ground_z"] if gz is None else gz) + RESET_DROP_M
            jid = int(model.body_jntadr[bid])                         # 몸통의 free joint
            qa, da = int(model.jnt_qposadr[jid]), int(model.jnt_dofadr[jid])
            data.qpos[qa:qa + 7] = [x, y, z, qw, 0.0, 0.0, qz]       # MuJoCo 쿼터니언은 (w, x, y, z)
            data.qvel[da:da + 6] = 0.0
            data.qpos[g["qadr"]] = io.default_pos
            data.qvel[g["dadr"]] = 0.0
            mujoco.mj_forward(model, data)
        elif player == "play_isaacsim.py":
            view, idx0 = g["view"], g["idx0"]
            p = view.get_root_transforms()[0]
            x, y = float(p[0]), float(p[1])
            gz = float(g["ground_z"](x, y))
            z = (g["start_z"] if math.isnan(gz) else gz) + RESET_DROP_M
            view.set_root_transforms(np.array([[x, y, z, 0.0, 0.0, qz, qw]], np.float32), idx0)   # 텐서 API 쿼터니언은 (x, y, z, w)
            view.set_root_velocities(np.zeros((1, 6), np.float32), idx0)
            q0 = np.zeros((1, len(g["names"])), np.float32)
            q0[0, g["perm"]] = io.default_pos
            view.set_dof_positions(q0, idx0)
            view.set_dof_velocities(np.zeros_like(q0), idx0)
        else:                                                        # play_isaaclab.py (env 하나, env 원점 0)
            import torch

            robot, tt = g["robot"], g["tt"]
            p = tt(robot.data.root_pos_w)[0].cpu().numpy()
            dev = tt(robot.data.root_quat_w).device
            x, y = float(p[0]), float(p[1])
            gz = g["ground_z"](x, y) if g.get("ground") is not None else float("nan")
            z = (g["start_dz"] if math.isnan(gz) else gz) + RESET_DROP_M
            robot.write_root_link_pose_to_sim_index(root_pose=torch.tensor([[x, y, z, 0.0, 0.0, qz, qw]], dtype=torch.float32, device=dev), env_ids=[0])
            robot.write_root_com_velocity_to_sim_index(root_velocity=torch.zeros((1, 6), dtype=torch.float32, device=dev), env_ids=[0])
            q = torch.tensor([[float(io.default_pos[io.joints.index(n)]) for n in robot.joint_names]], dtype=torch.float32, device=dev)
            robot.write_joint_position_to_sim_index(position=q, env_ids=[0])
            robot.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(q), env_ids=[0])
        return f"({x:.2f}, {y:.2f}, z {z:.2f}), 방향 {math.degrees(yaw):.0f}°"

    def _flip(self, w: float) -> None:
        """몸통 x축(로봇 기준 roll) 둘레 각속도를 w [rad/s]만큼 한 번 더합니다. 세 시뮬레이터에서 같은 몸체 프레임 충격입니다."""
        g, player = self.player_globals, Path(self.a.player).name
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

    def active_text(self) -> str:
        return ",".join(sorted(self.active))

    # ------------------------------------------------------------------ 판정·표시
    def _observe(self, state, t: float) -> None:
        if "stale" in self.active:
            if not (self.a.realtime or self._windowed()):
                time.sleep(self.io.policy_dt)                 # wall 시간이 지나야 감시기가 끊김을 알 수 있음(창 모드·--realtime은 이미 실시간)
            if self.wd.is_stale():
                self._record(self.est.stale_report(t, self.wd.silent_s()), publish=False)   # 발행은 heartbeat 스레드가 함
            return
        rep = self.est.update(state, t)
        self.wd.feed()
        self._record(rep)

    def _record(self, rep, publish: bool = True) -> None:
        f = rep.features
        fault = self.active_text()
        self.records.append({"t": rep.t, "state": rep.state.name, "reason": rep.reason, "since": rep.since_s, "tilt": f.get("tilt_deg"),
                             "height": f.get("height_m"), "ground_ok": f.get("ground_ok"), "h0": f.get("h0_m"),
                             "speed": f.get("speed_mps"), "cmd": f.get("cmd_lin_mps"), "fault": fault})
        if self.logger:
            self.logger.log(rep, extra={"fault": fault})
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

    def _windowed(self) -> bool:
        if self.a.player.endswith("play_mujoco.py"):
            return "--headless" not in self._player_args
        return self._windowed_kit()

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

            self._ui_win = ui.Window("Locomotion state (G-006)", width=380, height=250, position_x=20, position_y=60)
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

    def _lines(self, rep) -> tuple[str, ...]:
        f = rep.features
        h, h0 = f.get("height_m"), f.get("h0_m")
        return (f"{rep.state.name} ({rep.code})", rep.reason,
                f"{_fmt(f.get('tilt_deg'), '.0f')}/{_fmt(f.get('pitch_deg'), '.0f')}/{_fmt(f.get('roll_deg'), '.0f')} deg",
                f"{_fmt(f.get('speed_mps'), '.2f')}/{_fmt(f.get('cmd_lin_mps'), '.2f')} m/s",
                _fmt(h / h0 if h and h0 else None, '.2f'), self.active_text() or "-", f"{rep.t:.1f} s")

    def _update_kit_ui(self, rep) -> None:
        r, g, b = _STATE_COLOR.get(rep.state.name, (255, 255, 255))
        title, *rows = self._ui_labels
        head, *vals = self._lines(rep)
        title.text = head
        title.style = {"font_size": 34, "color": 0xFF000000 | (b << 16) | (g << 8) | r}      # ABGR
        names = ("reason", "tilt/pitch/roll", "speed/cmd", "height/h0", "fault", "t")
        for label, name, val in zip(rows, names, vals):
            label.text = f"{name}  {val}"

    def _overlay(self, rep) -> None:
        import mujoco

        left = "STATE\nreason\ntilt/pitch/roll\nspeed/cmd\nheight/h0\nfault\nt"
        self.viewer.set_texts((mujoco.mjtFont.mjFONT_BIG, mujoco.mjtGridPos.mjGRID_TOPLEFT, left, "\n".join(self._lines(rep))))

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
        try:
            self._rc = self._finish()
        finally:
            for side in (self.pub, self.ros):
                if side is not None:
                    side.close()
        return self._rc

    def _finish(self) -> int:
        a = self.a
        if self.est is None:   # 정책이 돌기 전에 끝남(예: --dump-model, --dump-physx 같은 도구 모드나 재생기 오류). 종료 코드는 재생기 것을 씁니다
            print("[STATE] 정책이 한 번도 돌지 않아 판정 요약이 없습니다", flush=True)
            return 0
        recs, dt = self.records, self.io.policy_dt
        share = Counter(r["state"] for r in recs)
        print(f"[STATE] 기록 {len(recs)}개(약 {len(recs) * dt:.1f} s), 고장 {len(self.events)}회 | 상태별 시간: "
              + ", ".join(f"{k} {v * dt:.1f}s({v / max(len(recs), 1) * 100:.1f}%)" for k, v in share.most_common()), flush=True)
        trans = [(r1["t"], r0["state"], r1["state"], r1["reason"]) for r0, r1 in zip(recs, recs[1:]) if r0["state"] != r1["state"]]   # 새 상태의 첫 기록 시각
        print(f"[STATE] 상태 전환 {len(trans)}회" + (": " + ", ".join(f"{t:.2f}s {x}->{y}({why})" for t, x, y, why in trans[:14]) if trans else "")
              + (" ..." if len(trans) > 14 else ""), flush=True)
        checks: list[tuple[str, bool, str]] = []
        metrics: dict = {"records": len(recs), "transitions": len(trans), "faults": len(self.events)}
        first = self.events[0]["t0"] if self.events else None
        pre = recs if first is None else [r for r in recs if r["t"] < first]
        self._margin(pre, metrics)
        tag = "" if first is None else f"고장({first:.1f} s) 전 "
        for st in (State.FALLEN, State.TILTING, State.STALE_INPUT):
            n = sum(r["state"] == st.name for r in pre)
            checks.append((f"{tag}{st.name} 오탐 0프레임", n == 0, f"{n}프레임"))
        after_init = [r for r in pre if r["state"] != State.INITIALIZING.name]
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
            if go is not None and (first is None or go["t"] < first):   # 대기가 끝난 뒤 걷는 명령이 고장 전에 나온 경우만
                walking = next((r for r in recs if r["t"] >= go["t"] and r["state"] == State.WALKING.name), None)
                lag = None if walking is None else walking["t"] - go["t"]
                checks.append(("걷는 명령이 나온 뒤 1.0 s 안에 WALKING", lag is not None and lag <= 1.0, "없음" if lag is None else f"{lag:.2f} s"))
        end_t = recs[-1]["t"] if recs else 0.0
        for i, ev in enumerate(self.events):
            nxt = self.events[i + 1]["t0"] if i + 1 < len(self.events) else math.inf
            win = [r for r in recs if ev["t0"] <= r["t"] < nxt]
            checks += self._event_checks(ev, win, min(nxt, end_t), metrics)
        ok = all(c[1] for c in checks)
        for name, passed, detail in checks:
            print(f"[STATE] [{'PASS' if passed else 'FAIL'}] {name}: {detail}", flush=True)
        for line in self._push_infos():
            print(f"[STATE] [INFO] {line}", flush=True)
        if self.pub is not None:
            print(f"[STATE] ROS 발행 {self.pub.sent_count}건({self.a.ros_topic})" + (f", 오류: {self.pub.error!r}" if self.pub.error else "")
                  + (f", 고장 주입 요청 {self.ros.requests}건" if self.ros is not None else ""), flush=True)
        if self.logger:
            self.logger.event("summary", ok=ok, metrics=metrics, events=self.events, infos=self._push_infos(),
                              checks=[{"name": n, "pass": p, "detail": d} for n, p, d in checks])
            self.logger.close()
            print(f"[STATE] 기록: {a.log}", flush=True)
        return 0 if ok else 1

    def _push_infos(self) -> list[str]:
        """push는 힘에 따라 결과가 달라 PASS/FAIL 대신 결과를 적습니다: 힘을 건 뒤 PUSH_REPORT_S 동안의 최대 기울기와 상태."""
        out = []
        for ev in (e for e in self.events if e["kind"] == "push"):
            win = [r for r in self.records if ev["t0"] <= r["t"] <= ev["t0"] + ev["duration_s"] + PUSH_REPORT_S]
            peak = max((r["tilt"] for r in win if r["tilt"] is not None), default=None)
            seen = list(dict.fromkeys(r["state"] for r in win))
            fall = next((r for r in win if r["state"] == State.FALLEN.name), None)
            result = (f"넘어짐(FALLEN {fall['t'] - ev['t0']:.2f} s 뒤, {fall['reason']})" if fall else "버팀")
            out.append(f"push@{ev['t0']:.1f}s {ev['magnitude']:g} N x {ev['duration_s']:g} s, 방향 {ev['direction_deg']:+.0f}°: {result}, "
                       f"최대 기울기 {_fmt(peak, '.0f')}°, 상태 {' -> '.join(seen)}")
        return out

    def _margin(self, pre: list[dict], metrics: dict) -> None:
        """임계값 여유: 고장 전(고장이 없으면 전체) 구간에서 기준까지 얼마나 남았는지."""
        tilts = [r["tilt"] for r in pre if r["tilt"] is not None]
        if not tilts:
            return
        ratios = [r["height"] / r["h0"] for r in pre if r["height"] is not None and r["h0"]]
        metrics.update(pre_tilt_max_deg=max(tilts), pre_tilt_p99_deg=float(np.percentile(tilts, 99)),
                       pre_ground_false_frames=sum(r["ground_ok"] is False for r in pre))
        msg = (f"[STATE] 여유(고장 전 {len(pre)}개): 기울기 최대 {max(tilts):.1f}°/p99 {np.percentile(tilts, 99):.1f}° "
               f"(경고 기준 {self.cfg.tilt_warn_deg:.0f}°, 낙상 기준 {self.cfg.fall_tilt_deg:.0f}°)")
        if ratios:
            metrics.update(pre_height_ratio_min=min(ratios), pre_height_ratio_p01=float(np.percentile(ratios, 1)))
            msg += f", 높이/h0 최저 {min(ratios):.2f}/p1 {np.percentile(ratios, 1):.2f} (기준 {self.cfg.fall_low_height_ratio:.2f})"
        print(msg + f", 지면 없음 {metrics['pre_ground_false_frames']}프레임", flush=True)

    def _event_checks(self, ev: dict, win: list[dict], win_end: float, metrics: dict) -> list[tuple[str, bool, str]]:
        """고장 하나(시작 t0부터 다음 고장 전까지의 기록 win)에서 기대 상태가 나왔는지 봅니다."""
        kind, t0, t1 = ev["kind"], ev["t0"], ev["t1"]
        tag = f"{kind}@{t0:.1f}s"
        active_end = win_end if t1 is None else t1
        out: list[tuple[str, bool, str]] = []
        if ev.get("during_init"):
            tag += "(초기화 중에 넣음)"
        first = lambda st, rs=win: next((r for r in rs if r["state"] == st.name), None)   # noqa: E731
        if kind in ("collapse", "flip"):
            fall = first(State.FALLEN)
            out.append((f"{tag}: {self.a.latency_max:g} s 안에 FALLEN", fall is not None and fall["t"] - t0 <= self.a.latency_max,
                        "없음" if fall is None else f"{fall['t'] - t0:.2f} s ({fall['reason']})"))
            if fall is None:
                return out
            # 판정기 지연: FALLEN 직전까지 이어진 연속 낙상 조건 구간의 시작부터 잽니다(격하게 넘어질 때 조건이 중간에 끊길 수 있음)
            recs = self.records
            j = next(i for i, r in enumerate(recs) if r is fall)
            while j > 0 and self._raw_fall(recs[j - 1]):
                j -= 1
            run_start = recs[j]["t"]
            out.append((f"{tag}: 연속 낙상 조건 시작 -> FALLEN 0.3 s 이내(debounce)", fall["t"] - run_start <= 0.3,
                        f"{fall['t'] - run_start:.2f} s (연속 조건 시작 t={run_start:.2f})"))
            hold_end = active_end if kind == "collapse" else win_end
            held = [r for r in win if fall["t"] <= r["t"] <= hold_end]
            released = next((r for r in held if r["state"] != State.FALLEN.name), None)
            held_s = (held[-1]["t"] - fall["t"]) if held else 0.0
            if released is None:
                out.append((f"{tag}: FALLEN 유지" + (" (고장 중)" if kind == "collapse" else ""), True, f"{held_s:.1f} s 동안 유지"))
            elif kind == "flip":      # 충격은 로봇이 스스로 일어날 수 있음: 직립 복구 뒤의 해제는 정상
                ok_rel = released["tilt"] is not None and released["tilt"] < self.cfg.recover_tilt_deg
                out.append((f"{tag}: FALLEN 유지, 또는 스스로 복구한 뒤 해제", ok_rel,
                            f"{released['t'] - fall['t']:.1f} s 뒤 해제(해제 시 기울기 {_fmt(released['tilt'], '.0f')} deg)"))
            else:
                out.append((f"{tag}: FALLEN 유지(고장 중)", False, f"{released['t'] - fall['t']:.1f} s 뒤 풀림"))
            metrics.setdefault("latency_s", []).append({"kind": kind, "t0": t0, "fallen_s": fall["t"] - t0})
        elif kind == "stale":
            st = first(State.STALE_INPUT)
            out.append((f"{tag}: {STALE_RELEASE_S:g} s 안에 STALE_INPUT", st is not None and st["t"] - t0 <= STALE_RELEASE_S,
                        "없음" if st is None else f"{st['t'] - t0:.2f} s"))
            if t1 is not None and win_end >= t1 + STALE_RELEASE_S:
                back = next((r for r in win if r["t"] >= t1 and r["state"] != State.STALE_INPUT.name), None)
                out.append((f"{tag}: 입력 복귀 후 {STALE_RELEASE_S:g} s 안에 해제", back is not None and back["t"] - t1 <= STALE_RELEASE_S,
                            "없음" if back is None else f"{back['t'] - t1:.2f} s"))
            n = sum(r["state"] == State.FALLEN.name for r in win)
            out.append((f"{tag}: FALLEN 오탐 0프레임", n == 0, f"{n}프레임"))
        elif kind == "tilt":
            during = [r for r in win if r["t"] <= active_end]
            tilting = first(State.TILTING, during)
            peak = max((r["tilt"] for r in during if r["tilt"] is not None), default=None)
            out.append((f"{tag}: {self.a.tilt_latency_max:g} s 안에 TILTING", tilting is not None and tilting["t"] - t0 <= self.a.tilt_latency_max,
                        ("없음" if tilting is None else f"{tilting['t'] - t0:.2f} s") + f" (최대 기울기 {_fmt(peak, '.0f')}°, 목표 roll {ev['magnitude']:+.0f}°)"))
            n = sum(r["state"] == State.FALLEN.name for r in during)
            out.append((f"{tag}: 기울어진 동안 FALLEN 0프레임", n == 0, f"{n}프레임"))
            if t1 is not None and win_end >= t1 + TILT_CLEAR_CHECK_S:
                after = [r for r in win if t1 <= r["t"] <= t1 + TILT_CLEAR_CHECK_S]
                ok_at = next((r for r in after if r["state"] in (State.STANDING.name, State.WALKING.name)), None)
                out.append((f"{tag}: 고장이 끝난 뒤 {TILT_CLEAR_CHECK_S:g} s 안에 STANDING/WALKING으로 복귀", ok_at is not None,
                            "없음" if ok_at is None else f"{ok_at['t'] - t1:.2f} s 뒤 {ok_at['state']}"))
        return out


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
    player_rc = 0
    try:
        run_player(path, src, player_args, run.player_globals)
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        player_rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if player_rc:
            print(f"[STATE] 재생기가 종료 코드 {e.code}로 끝남", flush=True)
    rc = run.finish()
    if run.est is None:              # 판정이 없었으면 재생기의 종료 코드를 그대로 돌려줍니다
        rc = player_rc
    if run.viewer is not None:       # 창 모드: GLFW 정리 단계의 오류를 피해 재생기처럼 바로 끝냅니다
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
