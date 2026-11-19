# SPDX-License-Identifier: Apache-2.0
"""yaml + numpy 러너(배포 경로)로 Isaac Lab 로봇을 구동해 눈으로 확인합니다. 학습 코드나 rsl_rl은 쓰지 않습니다.

  ./docker/hn sim /workspace/isaaclab/isaaclab.sh -p <이 파일> --task <task> --num_envs 1 \
      --hn-yaml=<policy_io.yaml> --hn-actor=<actor.npz> \
      [이동 옵션] --visualizer kit physics=isaacsim_physx

이동 옵션(좌표는 task의 world 프레임. 데모 지형이면 데모 프레임: x=동, y=북, 원점=시작점, 단위 m)
  --hn-start=x,y[,yaw_deg]     시작 위치(와 방향). 방향을 안 주면 첫 목적지를 바라봅니다. 기본 0,0
  --hn-goal=x,y                목적지 하나. 로봇이 시작점에서 그곳까지 걸어갑니다
  --hn-waypoints="x,y;x,y;..." 경유점 목록(마지막이 목적지). --hn-goal과 같이 쓰지 않습니다
  --hn-route-file=<경로.yaml> --hn-route=A   경로 파일(policies/urdf_v0/routes/)에서 시작점·경유점을 읽습니다(위 두 옵션보다 우선)
  --hn-vmax=0.5                최대 전진 속도 m/s(정책이 학습한 범위는 ±1.0. 0.5에서 확인함)
  --hn-nominal=1               외란·랜덤화를 끕니다(기본). 표준 환경의 push_robot(10~15초마다 ±0.5 m/s로 밀침), 질량·무게중심 랜덤화가 사라집니다. 0이면 학습 때와 같은 조건
  --hn-spacing=0               env가 2개 이상일 때 env 원점 간격 m(기본 0 = 모두 같은 지점). 지형이 하나라 0이 아니면 env마다 다른 위치에서 출발합니다
  --hn-lookahead=1.5           선분 추종 시 겨냥 거리 m(작을수록 선분에 바짝 붙고 흔들림이 큼)
  --hn-ground=<ground_grid.npz> 지면 높이 격자. 주면 시작 높이를 맞추고 시작·경로가 지면 위인지 검사합니다
  --hn-terrain-usd=<지면.usdc>  지형 충돌 메시(height scan ray가 맞는 면). 없으면 예전 데모 지형
  --hn-obstacles-usd=<장애물.usdc> 이동 금지 장애물·나무 충돌 메시(충돌만, height scan에는 안 보임). 없으면 없음
  --hn-force=1                 경로에 지면이 없어도 그냥 실행
  --hn-exit-on-arrival=1       도착하면 종료(기본은 서서 대기)
  이동 옵션이 없으면 고정 명령으로 걷습니다: --hn-vx=0.5 --hn-vy=0 --hn-wz=0 --hn-yaw=<rad>
카메라
  기본은 자유 카메라입니다(마우스 휠 줌·회전이 됩니다). 시작점 근처에서 바라보며 시작합니다.
  --hn-follow=2                카메라가 로봇을 따라가되 사용자가 돌리거나 줌한 시점은 유지합니다(로봇 변위만큼 평행이동). 휠 줌 가능
  --hn-follow=1                Kit의 추적 모드. 매 스텝 카메라를 절대 위치로 되돌리므로 휠 줌이 먹지 않습니다.
  --hn-debug-camera=1          step 100에 줌을 흉내 내고 카메라-로봇 거리를 출력(follow=2 점검용)
  --hn-cam=dx,dy,dz            카메라 위치. 자유 카메라면 시작점 기준, 따라가기면 로봇 기준 오프셋(기본 3,-3,2)
  --hn-realtime=0              실시간 대기 없이 최대 속도(시험용)
  --hn-dump-physx=<파일>       런타임 PhysX 파라미터를 이 JSON에 쓰고 끝냅니다(시뮬레이터 비교용)
  --hn-drop-offset=<m>         처음 낙하 높이(기본 0.40 m)에 더하는 값. 초기 조건을 조금 바꿔 걸음의 변동을 재는 실험용
  --hn-hold-default=1          정책 대신 기본 자세를 목표로 고정합니다(물리만 비교하는 통제 실험)
  --hn-substep-probe=<파일>    물리 하위 스텝마다 PhysX의 실제 관절 위치·속도(액추에이터 계산 직전)와 적용된 토크를 float32로 기록합니다(액추에이터가 어떤 상태를 쓰는지 확인하는 실험용)
  --hn-no-newton=1             Newton 액추에이터를 끄고 예전(torch) 액추에이터 경로를 씁니다(학습 설정은 켬. 시뮬레이터 비교 실험용)
  --hn-trace=<파일>            정책 입출력을 매 스텝 이 파일에 기록합니다(env 0만. runner.enable_trace). 시뮬레이터 사이 비교용

이동 제어기는 단순한 "경유점 선분을 따라 돌고 걷기"입니다(이전 경유점→현재 경유점 선분을 추종). 장애물(차량·나무)과 구멍을 피하지 않으니, 직선 경로가 지면 위인지
시작 때 출력되는 경로 검사를 확인하고 필요하면 경유점을 추가하십시오. 창을 닫거나 Ctrl+C로 끝냅니다.
"""
import contextlib
import math
import os
import sys
import time
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch

from isaaclab.app import launch_simulation
from isaaclab_rl.entrypoints.common import apply_env_overrides, close_env
from isaaclab_rl.entrypoints.simple_agents import _parse_args

import isaaclab_tasks  # noqa: F401,E402
from isaaclab_tasks.utils import resolve_task_config  # noqa: E402


def pop_opt(name, default=None):
    for a in list(sys.argv):
        if a.startswith(f"--{name}="):
            sys.argv.remove(a)
            return a.split("=", 1)[1]
    return default


def floats(s):
    return [float(v) for v in s.split(",")]


YAML, ACTOR = pop_opt("hn-yaml"), pop_opt("hn-actor")
VX, VY, WZ = (float(pop_opt(k, d)) for k, d in (("hn-vx", "0.5"), ("hn-vy", "0.0"), ("hn-wz", "0.0")))
YAW, START, GOAL, WAYPOINTS = pop_opt("hn-yaw"), pop_opt("hn-start"), pop_opt("hn-goal"), pop_opt("hn-waypoints")
VMAX, GROUND = min(float(pop_opt("hn-vmax", "0.5")), 1.0), pop_opt("hn-ground")
FORCE, EXIT_ON_ARRIVAL = pop_opt("hn-force", "0") == "1", pop_opt("hn-exit-on-arrival", "0") == "1"
LOOKAHEAD = float(pop_opt("hn-lookahead", "1.5"))
NOMINAL = pop_opt("hn-nominal", "1") != "0"
SPACING = float(pop_opt("hn-spacing", "0"))
FOLLOW_MODE = int(pop_opt("hn-follow", "0"))     # 0 자유 카메라, 1 Kit 추적(줌 불가), 2 평행이동 추적(줌·회전 가능)
FOLLOW = FOLLOW_MODE == 1
CAM, REALTIME = floats(pop_opt("hn-cam", "3,-3,2")), pop_opt("hn-realtime", "1") != "0"
DEBUG_CAM = pop_opt("hn-debug-camera", "0") == "1"
ROUTE_FILE, ROUTE_NAME = pop_opt("hn-route-file"), pop_opt("hn-route", "A")
TRACE = pop_opt("hn-trace")
DUMP_PHYSX = pop_opt("hn-dump-physx")
DROP = float(pop_opt("hn-drop-offset", "0"))
HOLD_DEFAULT = pop_opt("hn-hold-default", "0") == "1"
SUBSTEP_PROBE = pop_opt("hn-substep-probe")
NO_NEWTON = pop_opt("hn-no-newton", "0") == "1"
for _opt, _env in (("hn-terrain-usd", "HN_TERRAIN_USD"), ("hn-obstacles-usd", "HN_OBSTACLES_USD")):   # demo_task_cfg.py가 env cfg를 만들 때 읽음
    _val = pop_opt(_opt)
    if _val:
        os.environ[_env] = _val
if not (YAML and ACTOR):
    raise SystemExit("--hn-yaml=... --hn-actor=... 필요")
if GOAL and WAYPOINTS:
    raise SystemExit("--hn-goal과 --hn-waypoints는 같이 쓸 수 없습니다")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # 저장소 루트: gym entry point가 policies.urdf_v0.env를 import

import demo_task  # noqa: E402  (gym 등록만 함. Isaac Lab을 import하지 않음)

demo_task.register()
if ROUTE_FILE:   # 경로 yaml에서 시작점·경유점을 읽음(MuJoCo·Isaac Sim 스크립트와 같은 파일)
    from route_nav import load_route  # noqa: E402

    _route = load_route(ROUTE_FILE, ROUTE_NAME)
    START = f"{_route.start[0]},{_route.start[1]}"
    WAYPOINTS = ";".join(f"{x},{y}" for x, y in _route.waypoints)
    GOAL = None

from isaaclab_policy_io import apply_policy_io, check_env  # noqa: E402
from policy_io import load_policy_io  # noqa: E402
from runner import PolicyRunner  # noqa: E402

tt = lambda x: x.torch if hasattr(x, "torch") else x  # noqa: E731
wrap = lambda a: (a + math.pi) % (2 * math.pi) - math.pi  # noqa: E731

# ------------------------------------------------------------------ 경로·지면 검사
sx, sy, *_syaw = floats(START) if START else [0.0, 0.0]
waypoints = [floats(g) for g in (WAYPOINTS.split(";") if WAYPOINTS else ([GOAL] if GOAL else []))]
navigate = bool(waypoints)
start_yaw = math.radians(_syaw[0]) if _syaw else (math.atan2(waypoints[0][1] - sy, waypoints[0][0] - sx) if navigate else float(YAW or 0.0))

ground = None
if GROUND:
    g = np.load(GROUND)
    ground = (g["z"], float(g["x0"]), float(g["y0"]), float(g["res"]))


def ground_z(x, y):
    """지면 높이(없으면 nan). 격자 최근접 셀."""
    z, x0, y0, res = ground
    ix, iy = int((x - x0) / res), int((y - y0) / res)
    return float(z[iy, ix]) if 0 <= ix < z.shape[1] and 0 <= iy < z.shape[0] else float("nan")


start_dz = 0.0
if ground is not None:
    start_dz = ground_z(sx, sy)
    if math.isnan(start_dz):
        raise SystemExit(f"시작점 ({sx}, {sy})에 지면이 없습니다(구멍 또는 지형 밖). 지도에서 다른 지점을 고르십시오.")
    pts = [(sx, sy)] + [tuple(w) for w in waypoints]
    worst_slope = worst_step = 0.0
    problems = []
    for a, b in zip(pts[:-1], pts[1:]):
        n_s = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.25) + 1)
        prev = None
        for t in np.linspace(0.0, 1.0, n_s):
            x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            z = ground_z(x, y)
            if math.isnan(z):
                problems.append((x, y))
                prev = None
                continue
            if prev is not None:
                worst_step = max(worst_step, abs(z - prev))
            prev = z
    if navigate:
        zs = [ground_z(*p) for p in pts]
        for q in pts[1:]:
            if math.isnan(ground_z(*q)):
                problems.append(q)
        print(f"[PLAY] 경로 검사: 시작 ({sx}, {sy}) z={start_dz:+.3f} m -> " + " -> ".join(f"({q[0]}, {q[1]})" for q in pts[1:]), flush=True)
        print(f"[PLAY] 경로 검사: 직선 구간에서 지면이 끊긴 지점 {len(problems)}개" + (f", 처음 ({problems[0][0]:.1f}, {problems[0][1]:.1f})" if problems else "")
              + f" | 0.25 m 간격 높이 차 최대 {worst_step * 100:.1f} cm(경사 {math.degrees(math.atan2(worst_step, 0.25)):.1f}도)", flush=True)
        if problems and not FORCE:
            raise SystemExit("직선 경로에 지면이 없는 구간이 있습니다. 경유점(--hn-waypoints)으로 우회하거나 --hn-force=1로 그대로 실행하십시오.")

# ------------------------------------------------------------------ env 구성
io = load_policy_io(YAML)
with np.load(ACTOR, allow_pickle=False) as _z:
    _sha, _it = str(_z["source_sha256"]), int(_z["source_iteration"])
_want = io.raw["policy"]["checkpoint"]
print(f"[PLAY] 정책 가중치: {Path(ACTOR).name} <- {_want['file']} (iteration {_it}, sha256 {_sha[:12]}…) "
      + ("= yaml이 정한 체크포인트와 일치" if _sha == _want["sha256"] and _it == _want["iteration"] else "!! yaml이 정한 체크포인트와 다름 !!"), flush=True)
args = _parse_args(sys.argv[1:], "zero")
env_cfg, _ = resolve_task_config(args.task, "")
apply_env_overrides(args, env_cfg)
args.device = env_cfg.sim.device
apply_policy_io(env_cfg, io)
if NO_NEWTON:
    env_cfg.sim.use_newton_actuators = False

cmd = env_cfg.commands.base_velocity
cmd.ranges.lin_vel_x, cmd.ranges.lin_vel_y, cmd.ranges.ang_vel_z = (VX, VX), (VY, VY), (WZ, WZ)
cmd.heading_command, cmd.rel_standing_envs, cmd.rel_heading_envs, cmd.debug_vis = False, 0.0, 0.0, True
if navigate:
    cmd.resampling_time_range = (1.0e9, 1.0e9)   # 명령을 이 스크립트가 매 스텝 씁니다(무작위 재추출 방지)
env_cfg.episode_length_s = 3600.0               # 20 s 타임아웃으로 시작점에 되돌아가지 않게(경로 없는 고정 명령 모드도 마찬가지)
env_cfg.observations.policy.enable_corruption = False
if NOMINAL:  # 데모 재생: 학습 때의 외란·랜덤화를 끕니다(정책이 학습한 조건의 평균에 해당)
    for _ev in ("push_robot", "add_base_mass", "base_com"):
        if getattr(env_cfg.events, _ev, None) is not None:
            setattr(env_cfg.events, _ev, None)
    try:  # reset 때 관절 위치를 기본값의 0.5~1.5배로 흩뜨리는 것도 끕니다
        env_cfg.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
    except Exception as e:  # noqa: BLE001
        print(f"[PLAY] reset 관절 랜덤화 해제 생략: {e}", flush=True)
if args.num_envs is None or args.num_envs > 1:
    env_cfg.scene.env_spacing = SPACING   # 지형이 월드에 하나뿐이라, env 원점을 흩뜨리면 env마다 다른 곳에서 출발함. 0이면 모두 같은 지점
rb = env_cfg.events.reset_base.params
rb["pose_range"] = {"x": (sx, sx), "y": (sy, sy), "z": (start_dz + DROP, start_dz + DROP), "yaw": (start_yaw, start_yaw)}
rb["velocity_range"] = {k: (0.0, 0.0) for k in ("x", "y", "z", "roll", "pitch", "yaw")}
try:  # 카메라
    if FOLLOW:
        env_cfg.viewer.origin_type, env_cfg.viewer.asset_name = "asset_root", "robot"
        env_cfg.viewer.eye, env_cfg.viewer.lookat = tuple(CAM), (0.0, 0.0, 0.3)
    else:
        env_cfg.viewer.eye = (sx + CAM[0], sy + CAM[1], start_dz + CAM[2])
        env_cfg.viewer.lookat = (sx, sy, start_dz + 0.3)
except Exception as e:  # noqa: BLE001
    print(f"[PLAY] 카메라 설정 생략: {e}", flush=True)

with launch_simulation(env_cfg, args), contextlib.ExitStack() as cleanup:
    env = gym.make(args.task, cfg=env_cfg)
    cleanup.callback(lambda: close_env(env))
    u = env.unwrapped
    n = u.num_envs
    if os.environ.get("HN_OBSTACLES_USD"):   # 장애물이 실제로 장면에 들어갔는지(충돌 메시 prim 수) 확인해 둡니다
        import omni.usd
        from pxr import Usd, UsdGeom, UsdPhysics

        _root = omni.usd.get_context().get_stage().GetPrimAtPath("/World/obstacles")
        _meshes = [p for p in Usd.PrimRange(_root) if p.IsA(UsdGeom.Mesh)] if _root.IsValid() else []
        _coll = sum(1 for p in _meshes if p.HasAPI(UsdPhysics.CollisionAPI))
        print(f"[PLAY] 장애물 /World/obstacles: 메시 {len(_meshes)}개 중 충돌 {_coll}개", flush=True)
    obs, _ = env.reset()
    robot, scanner = u.scene["robot"], u.scene.sensors["height_scanner"]
    if SUBSTEP_PROBE:   # 매 하위 스텝: [PhysX 실제 q 12, qd 12, 액추에이터가 적용한 토크 12]
        from physx_dump import _to_list

        _probe_f = open(SUBSTEP_PROBE, "wb")
        _orig_write = robot.write_data_to_sim

        def _probe_write(*a, **k):
            q = np.asarray(_to_list(robot.root_view.get_dof_positions()), np.float32).reshape(-1)[:12]       # 읽기만 함(robot.data 갱신을 건드리지 않음)
            qd = np.asarray(_to_list(robot.root_view.get_dof_velocities()), np.float32).reshape(-1)[:12]
            r = _orig_write(*a, **k)
            tau = tt(robot.data.applied_torque)[0].detach().cpu().numpy().astype(np.float32).reshape(-1)
            _probe_f.write(np.concatenate([q, qd, tau]).tobytes())
            _probe_f.flush()
            return r

        robot.write_data_to_sim = _probe_write
    if DUMP_PHYSX:
        import omni.usd
        from physx_dump import write_dump

        write_dump(DUMP_PHYSX, robot.root_view, omni.usd.get_context().get_stage(),
                   ["/physicsScene", "/World/physicsScene", "/World/envs/env_0/Robot", "/World/ground", "/World/obstacles", "/World/PhysicsMaterials", "/World/Looks"],
                   {"sim": "isaaclab", "task": args.task, "joint_names": list(robot.joint_names)})
        print(f"[PLAY] PhysX 기록: {DUMP_PHYSX}", flush=True)
        sys.exit(0)
    problems_env = check_env(env, io)
    _orig = torch.unique(u.scene.env_origins.round(decimals=2), dim=0)
    print(f"[PLAY] env 원점: 서로 다른 값 {len(_orig)}개 (1이면 모든 env가 같은 지점에서 출발) 예: {_orig[:3].cpu().numpy().tolist()}", flush=True)
    print(f"[PLAY] task={args.task} physics={type(env_cfg.sim.physics).__name__} envs={n} 시작=({sx}, {sy}, yaw {math.degrees(start_yaw):.0f}도)"
          + (f" 목적지={waypoints}" if navigate else f" 고정 명령=[{VX}, {VY}, {WZ}]"), flush=True)
    print(f"[PLAY] check_env: {'OK' if not problems_env else problems_env}", flush=True)
    print(f"[PLAY] 외란·랜덤화: {'꺼짐(nominal)' if NOMINAL else '켜짐(학습 조건)'}")
    print(f"[PLAY] 카메라: {['자유(휠 줌·회전 가능, 로봇이 멀어지면 화면 밖)', '로봇 따라가기(고정 시점, 휠 줌 안 됨)', '로봇 따라가기(시점 이동 + 휠 줌·회전 가능)'][FOLLOW_MODE]}", flush=True)

    if navigate:  # 목적지 표시(빨간 공). 실패해도 이동에는 영향 없음
        try:
            import isaaclab.sim as sim_utils
            from isaaclab.markers import VisualizationMarkers, VisualizationMarkersCfg

            mk = VisualizationMarkers(VisualizationMarkersCfg(prim_path="/Visuals/goals", markers={
                "goal": sim_utils.SphereCfg(radius=0.25, visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0.1, 0.1)))}))
            gz = [(0.0 if ground is None else (ground_z(w[0], w[1]) if not math.isnan(ground_z(w[0], w[1])) else 0.0)) + 0.3 for w in waypoints]
            mk.visualize(translations=torch.tensor([[w[0], w[1], z] for w, z in zip(waypoints, gz)], dtype=torch.float32, device=u.device))
        except Exception as e:  # noqa: BLE001
            print(f"[PLAY] 목적지 표시 생략: {e}", flush=True)

    term = u.command_manager.get_term("base_velocity")
    runners = [PolicyRunner(io, ACTOR) for _ in range(n)]
    for _r in runners:
        _r.hold_default = HOLD_DEFAULT
    if TRACE:
        runners[0].enable_trace(TRACE, {"sim": "isaaclab", "task": args.task})
    wp_idx = [0] * n
    fell = [False] * n
    arrived = [False] * n
    step, t0, t_next, dt = 0, time.perf_counter(), time.perf_counter(), u.step_dt
    cam_state, last_root = None, tt(robot.data.root_pos_w)[0].detach().cpu().numpy().copy()
    if FOLLOW_MODE == 2:   # 매 스텝 로봇이 움직인 만큼 카메라를 평행이동(사용자가 돌리거나 줌한 시점은 그대로 유지)
        try:
            from omni.kit.viewport.utility import get_active_viewport
            from omni.kit.viewport.utility.camera_state import ViewportCameraState
            from pxr import Gf as _Gf
            _vp = get_active_viewport()
            cam_state = ViewportCameraState(_vp.get_active_camera() or "/OmniverseKit_Persp", _vp)
            print(f"[PLAY] 평행이동 추적 준비: 카메라 {_vp.get_active_camera()}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[PLAY] 평행이동 추적을 쓸 수 없습니다(창이 없거나 API 차이): {e}", flush=True)

    def heading():
        try:
            return tt(robot.data.heading_w)
        except Exception:  # noqa: BLE001
            q = tt(robot.data.root_quat_w)  # Isaac Lab 3.0: (x, y, z, w)
            return torch.atan2(2 * (q[:, 3] * q[:, 2] + q[:, 0] * q[:, 1]), 1 - 2 * (q[:, 1] ** 2 + q[:, 2] ** 2))

    try:
        while args.max_steps is None or step < args.max_steps:
            if navigate:
                pos = (tt(robot.data.root_pos_w) - u.scene.env_origins)[:, :2].cpu().numpy()
                yaw = heading().cpu().numpy()
                c = np.zeros((n, 3), np.float32)
                for i in range(n):
                    if arrived[i]:
                        continue
                    last = wp_idx[i] == len(waypoints) - 1
                    goal_i = np.array(waypoints[wp_idx[i]])
                    d = goal_i - pos[i]
                    dist = float(np.hypot(*d))
                    seg_a = np.array(waypoints[wp_idx[i] - 1]) if wp_idx[i] > 0 else np.array([sx, sy])
                    seg = goal_i - seg_a
                    passed = float(np.dot(pos[i] - seg_a, seg)) >= float(np.dot(seg, seg)) and dist < 1.5   # 선분 끝을 지나쳤으면 도달로 침
                    if dist < (0.3 if last else 0.5) or (passed and not last):
                        if last:
                            arrived[i] = True
                            print(f"[PLAY] env{i} 도착: t={step * dt:.1f}s, 목적지까지 {dist:.2f} m, 위치 ({pos[i][0]:.2f}, {pos[i][1]:.2f})", flush=True)
                            continue
                        wp_idx[i] += 1
                        print(f"[PLAY] env{i} 경유점 {wp_idx[i]}/{len(waypoints)} 통과 t={step * dt:.1f}s", flush=True)
                        goal_i = np.array(waypoints[wp_idx[i]])
                        seg_a = np.array(waypoints[wp_idx[i] - 1])
                        seg = goal_i - seg_a
                        d = goal_i - pos[i]
                        dist = float(np.hypot(*d))
                        last = wp_idx[i] == len(waypoints) - 1
                    # 선분 추종: 로봇을 선분에 투영한 점에서 LOOKAHEAD 앞을 겨냥해, 밀려나도 선분으로 돌아오게 함
                    seg_len = float(np.hypot(*seg))
                    t_proj = float(np.dot(pos[i] - seg_a, seg)) / max(seg_len, 1e-6)
                    aim = seg_a + seg / max(seg_len, 1e-6) * min(max(t_proj, 0.0) + LOOKAHEAD, seg_len)
                    da = aim - pos[i]
                    err = wrap(math.atan2(da[1], da[0]) - float(yaw[i]))
                    vx = 0.0 if abs(err) > 0.8 else VMAX * max(0.0, math.cos(err))   # 많이 틀어졌으면 제자리에서 먼저 돎
                    if last:
                        vx = min(vx, max(0.15, 0.6 * dist))                          # 목적지 앞에서 감속
                    c[i] = (vx, 0.0, float(np.clip(1.2 * err, -0.8, 0.8)))
                term.vel_command_b[:] = torch.as_tensor(c, device=u.device)
                if EXIT_ON_ARRIVAL and all(arrived):
                    break
            st = {
                "base_lin_vel_b": tt(robot.data.root_lin_vel_b), "base_ang_vel_b": tt(robot.data.root_ang_vel_b),
                "projected_gravity_b": tt(robot.data.projected_gravity_b),
                "command": u.command_manager.get_command("base_velocity"),
                "joint_pos": tt(robot.data.joint_pos), "joint_vel": tt(robot.data.joint_vel),
                "height_hits_z": tt(scanner.data.ray_hits_w)[..., 2], "base_pos_z": tt(scanner.data.pos_w)[:, 2],
            }
            st = {k: v.detach().cpu().numpy() for k, v in st.items()}
            for i in range(n):
                runners[i].act({k: v[i] for k, v in st.items()})
            actions = np.stack([r.last_action for r in runners])
            with torch.inference_mode():
                obs, rew, terminated, truncated, _ = env.step(torch.as_tensor(actions, device=u.device))
            if TRACE:
                runners[0].trace_aux = np.abs(tt(robot.data.applied_torque)[0].detach().cpu().numpy())   # 마지막 하위 스텝에 가한 토크
            for i in torch.nonzero(terminated | truncated).flatten().tolist():
                runners[i].reset()
                wp_idx[i], arrived[i] = 0, False
                print(f"[PLAY] env{i} 리셋(넘어짐/종료) t={step * dt:.1f}s -> 시작점에서 다시 출발", flush=True)
            step += 1
            if cam_state is not None:
                _cur = tt(robot.data.root_pos_w)[0].detach().cpu().numpy()
                _d = _cur - last_root
                last_root = _cur.copy()
                try:
                    if DEBUG_CAM and step == 100:   # 시험용: 사용자가 줌한 것처럼 카메라를 목표 쪽으로 40% 당김
                        _p, _t = cam_state.position_world, cam_state.target_world
                        cam_state.set_position_world(_p + (_t - _p) * 0.4, False)
                    _p, _t = cam_state.position_world, cam_state.target_world
                    cam_state.set_position_world(_p + _Gf.Vec3d(*[float(v) for v in _d]), False)
                    cam_state.set_target_world(_t + _Gf.Vec3d(*[float(v) for v in _d]), True)
                    if DEBUG_CAM and (step in (90, 110) or step % 100 == 0):
                        _p = cam_state.position_world
                        print(f"[PLAY] 카메라-로봇 거리 step {step}: {float(np.linalg.norm(np.array([_p[0], _p[1], _p[2]]) - _cur)):.2f} m", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"[PLAY] 카메라 평행이동 실패, 끕니다: {e}", flush=True)
                    cam_state = None
            zpos = tt(robot.data.root_pos_w)[:, 2].cpu().numpy()
            xy_now = (tt(robot.data.root_pos_w) - u.scene.env_origins)[:, :2].cpu().numpy()
            for i in range(n):
                if zpos[i] < -1.0 and not fell[i]:
                    fell[i] = True
                    print(f"[PLAY] env{i} 지형 밖으로 추락: t={step * dt:.1f}s, 위치 ({xy_now[i][0]:.1f}, {xy_now[i][1]:.1f}), 경유점 {wp_idx[i]}/{len(waypoints)} 진행 중", flush=True)
                elif zpos[i] >= -1.0:
                    fell[i] = False
            if step % 250 == 0:
                p = tt(robot.data.root_pos_w)[0].cpu().numpy().round(2).tolist()
                print(f"[PLAY] step {step} (t={step * dt:.0f}s) base xyz = {p}", flush=True)
            if REALTIME:
                t_next += dt                      # 실시간(50 Hz)에 맞춰 천천히 돌립니다
                time.sleep(max(0.0, t_next - time.perf_counter()))
    except KeyboardInterrupt:
        pass
    print(f"[PLAY] 종료: {step} step ({step * dt:.1f} s 시뮬레이션, 실제 {time.perf_counter() - t0:.1f} s)", flush=True)
