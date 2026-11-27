#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""MuJoCo에서 policy_io.yaml + numpy 러너(배포 경로)로 로봇이 경로를 걷게 합니다. Isaac Lab 없이 MuJoCo만 필요합니다.

PAIR360 데모 지형(높이맵 타일)과 URDF를 불러오고, 정책(50 Hz) -> 관절 목표 -> DC 모터 모델의 PD(200 Hz) 순으로 구동합니다.
정책이 Isaac Lab에서 본 것과 같게 관측을 만들고(height scan은 mj_ray), 모터는 Isaac Lab DCMotor와 같은 토크·속도 한계로 자릅니다.
다만 접촉 모델이 달라(PhysX와 MuJoCo) 정책이 같은 만큼 안정적으로 걷는다는 보장은 없습니다. 이 스크립트가 그 확인 도구입니다.

  <robot venv python> policies/play_mujoco.py --scene <mujoco/scene.xml> --urdf <hypernova_go2.urdf> --actor <actor.npz> \
      --route-file policies/urdf_v0/routes/pair360_demo.yaml --route A            # 창
  ... --headless --exit-on-arrival --max-steps 40000                                          # 창 없이 시험

경로 지정: --route-file + --route <이름>, 또는 --start x,y --waypoints "x,y;x,y". 좌표는 데모 프레임(x=동, y=북, m).
창에서는 마우스로 돌리고 휠로 줌할 수 있고, --follow가 켜져 있으면(기본) 카메라 중심이 로봇을 따라가며 거리·각도는 유지됩니다.
"""
import argparse
import math
import os
import re
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from policy_io import load_policy_io  # noqa: E402
from route_nav import RouteFollower, load_route, parse_xy_list  # noqa: E402
from runner import PolicyRunner  # noqa: E402
from actuator_model import DCMotor  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--yaml", default=str(Path(__file__).resolve().parents[1] / "urdf_v0" / "policy_io.yaml"))
ap.add_argument("--actor", required=True, help="export_actor.py가 만든 .npz")
ap.add_argument("--scene", required=True, help="지형 MJCF(높이맵 타일), 예: <데이터>/pair360_demo_frame/mujoco/scene.xml")
ap.add_argument("--urdf", default=str(Path(__file__).resolve().parents[2] / "description" / "hn_v0_go2" / "hypernova_go2.urdf"),
                help="로봇 URDF(기본: 저장소 description/hn_v0_go2, 루트 base). 같은 폴더의 meshes/를 씁니다(mesh는 Git 밖: tools/description/1030_fetch_go2_meshes.py)")
ap.add_argument("--route-file")
ap.add_argument("--route", default="A")
ap.add_argument("--start", help="x,y (경로 파일 대신)")
ap.add_argument("--waypoints", help="'x,y;x,y;...' (경로 파일 대신)")
ap.add_argument("--vmax", type=float, default=0.5)
ap.add_argument("--lookahead", type=float, default=1.5)
ap.add_argument("--friction", type=float, default=0.85, help="지면·발 마찰계수(Isaac 쪽 유효 마찰 0.8~0.9에 맞춤)")
ap.add_argument("--max-steps", type=int, default=0, help="정책 스텝 수 상한(0이면 무제한). 1스텝 = 0.02 s")
ap.add_argument("--headless", action="store_true")
ap.add_argument("--exit-on-arrival", action="store_true")
ap.add_argument("--no-realtime", action="store_true", help="창에서도 실시간 대기를 하지 않음")
ap.add_argument("--follow", type=int, default=1, help="1: 카메라 중심이 로봇을 따라감(줌·회전 가능), 0: 고정")
ap.add_argument("--cam-dist", type=float, default=6.0)
ap.add_argument("--no-markers", action="store_true", help="경유점 표시(빨간 구)를 끕니다")
args = ap.parse_args()

io = load_policy_io(args.yaml)
if args.route_file:
    route = load_route(args.route_file, args.route)
    start, wps = route.start, [list(w) for w in route.waypoints]
elif args.waypoints:
    start = tuple(float(v) for v in (args.start or "0,0").split(","))
    wps = parse_xy_list(args.waypoints)
else:
    start, wps = (0.0, 0.0), []
yaw0 = math.atan2(wps[0][1] - start[1], wps[0][0] - start[0]) if wps else 0.0

# ---------------------------------------------------------------- 모델
terrain = mujoco.MjSpec.from_file(str(args.scene))
terrain.compiler.inertiafromgeom = mujoco.mjtInertiaFromGeom.mjINERTIAFROMGEOM_FALSE
for g in terrain.geoms:
    g.friction = [args.friction, 0.005, 0.0001]
m0 = terrain.compile()
d0 = mujoco.MjData(m0)
mujoco.mj_forward(m0, d0)
gid = np.zeros(1, np.int32)
dist = mujoco.mj_ray(m0, d0, np.array([start[0], start[1], 60.0]), np.array([0, 0, -1.0]), None, 1, -1, gid)
if dist < 0:
    raise SystemExit(f"시작점 ({start[0]}, {start[1]}) 아래에 지형이 없습니다(구멍이거나 지형 밖).")
ground_z = 60.0 - dist


def ground_at(x, y):
    """(x, y) 아래 지형의 높이. 지면이 없으면(구멍·지형 밖) None."""
    hit = mujoco.mj_ray(m0, d0, np.array([x, y, 60.0]), np.array([0, 0, -1.0]), None, 1, -1, np.zeros(1, np.int32))
    return None if hit < 0 else 60.0 - hit

urdf = Path(args.urdf)
xml = urdf.read_text(encoding="utf-8")
block = f'<mujoco><compiler meshdir="{urdf.parent / "meshes"}" strippath="true" discardvisual="false"/></mujoco>'  # URDF 파서는 시각 mesh를 파싱 때 버림
xml, n_sub = re.subn(r"(<robot\b[^>]*>)", lambda m: m.group(1) + block, xml, count=1)
if n_sub != 1:
    raise SystemExit("URDF에서 <robot> 태그를 찾지 못했습니다")
robot = mujoco.MjSpec.from_string(xml)
robot.compiler.fusestatic = False
robot.compiler.inertiafromgeom = mujoco.mjtInertiaFromGeom.mjINERTIAFROMGEOM_FALSE
for g in robot.geoms:
    if g.contype == 0 and g.conaffinity == 0:
        g.group = 1                                       # URDF <visual>: 그리기만
    else:
        g.contype, g.conaffinity, g.group = 1, 0, 3       # URDF <collision>: 지형과만 충돌, 숨김
        g.friction = [args.friction, 0.005, 0.0001]
for j in robot.joints:                                     # Isaac Lab 쪽 설정과 같게(관절 감쇠·마찰은 모터 모델이 전담)
    j.damping = np.zeros(np.size(j.damping)) if np.ndim(j.damping) else 0.0   # MuJoCo 3.12: damping은 3원소 배열
    j.frictionloss = np.zeros(np.size(j.frictionloss)) if np.ndim(j.frictionloss) else 0.0
    j.armature = np.zeros(np.size(j.armature)) if np.ndim(j.armature) else 0.0
root = robot.body(io.root_link)
root.add_freejoint()
frame = terrain.worldbody.add_frame(pos=[start[0], start[1], ground_z + 0.40], quat=[math.cos(yaw0 / 2), 0, 0, math.sin(yaw0 / 2)])
frame.attach_body(root, "go2_", "")
for jn, eff in zip(io.joints, io.effort_limit):
    a = terrain.add_actuator(name="a_" + jn, target="go2_" + jn, trntype=mujoco.mjtTrn.mjTRN_JOINT)
    a.gaintype, a.biastype = mujoco.mjtGain.mjGAIN_FIXED, mujoco.mjtBias.mjBIAS_NONE
    a.gainprm[0] = 1.0                                     # ctrl = 토크 [N·m]
    a.ctrllimited, a.ctrlrange = 1, [-float(eff), float(eff)]
# 경유점 표시(시각 전용). Isaac Lab과 같은 빨간 구(반지름 0.25 m, 지면 +0.3 m, 지면이 없으면 0+0.3).
# contype·conaffinity 0이라 충돌하지 않고, group 2라 height scan ray(group 0만 봄)에도 잡히지 않아 물리·관측에 영향이 없습니다.
if not args.no_markers:
    for i, (wx, wy) in enumerate(wps):
        gz = ground_at(wx, wy)
        terrain.worldbody.add_geom(name=f"route_wp{i + 1:02d}", type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.25, 0.0, 0.0],
                                   pos=[wx, wy, (0.0 if gz is None else gz) + 0.3], rgba=[1.0, 0.1, 0.1, 1.0],
                                   contype=0, conaffinity=0, group=2)
    print(f"[MJ] 경유점 표시 {len(wps)}개(빨간 구, 시각 전용)", flush=True)
model = terrain.compile()
model.opt.timestep = io.sim_dt
data = mujoco.MjData(model)

qadr = np.array([model.joint("go2_" + n).qposadr[0] for n in io.joints])
dadr = np.array([model.joint("go2_" + n).dofadr[0] for n in io.joints])
bid = model.body("go2_" + io.root_link).id
data.qpos[qadr] = io.default_pos
mujoco.mj_forward(model, data)
terrain_mask = np.zeros(6, np.uint8)
terrain_mask[0] = 1                                        # 지형 geom은 group 0, 로봇 충돌체는 group 3

motor = DCMotor(io)                                         # Isaac Lab DCMotor와 같은 PD + 토크·속도 한계(policies/actuator_model.py)


def read_state(command):
    R = data.xmat[bid].reshape(3, 3)                       # body -> world
    pos = data.xpos[bid].copy()
    yaw = math.atan2(R[1, 0], R[0, 0])
    hits = np.empty(io.hs_shape[0] * io.hs_shape[1])
    xy = io.height_scan_world_xy(pos[:2], yaw)
    geom = np.zeros(1, np.int32)
    for i, (x, y) in enumerate(xy):
        d = mujoco.mj_ray(model, data, np.array([x, y, pos[2] + io.hs_start_height]), np.array([0, 0, -1.0]), terrain_mask, 1, -1, geom)
        hits[i] = pos[2] + io.hs_start_height - d if d >= 0 else 1.0e3   # 맞은 곳의 높이(안 맞으면 매우 높은 값 -> 관측은 -1로 clip)
    state = {
        "base_lin_vel_b": R.T @ data.qvel[0:3], "base_ang_vel_b": data.qvel[3:6].copy(),
        "projected_gravity_b": R.T @ np.array([0.0, 0.0, -1.0]), "command": np.asarray(command),
        "joint_pos": data.qpos[qadr].copy(), "joint_vel": data.qvel[dadr].copy(),
        "height_hits_z": hits, "base_pos_z": np.array([pos[2]]),
    }
    return state, pos, yaw, R[2, 2]


runner = PolicyRunner(io, args.actor)
runner.reset()
follower = RouteFollower(start, wps, vmax=args.vmax, lookahead=args.lookahead) if wps else None
fixed_cmd = (args.vmax, 0.0, 0.0)
print(f"[MJ] 정책 가중치 {Path(args.actor).name} | 모델 body {model.nbody}, geom {model.ngeom}, hfield {model.nhfield} | 시작 ({start[0]}, {start[1]}) 지면 z={ground_z:+.2f} yaw {math.degrees(yaw0):.0f}도"
      + (f" | 경유점 {len(wps)}개" if wps else " | 경로 없음(고정 전진 명령)"), flush=True)

import contextlib  # noqa: E402

stack = contextlib.ExitStack()                 # viewer 수명을 with 규칙으로 관리(직접 close()하면 종료 때 GLFW가 죽는 경우가 있음)
viewer = None
if not args.headless:
    from mujoco import viewer as mj_viewer

    viewer = stack.enter_context(mj_viewer.launch_passive(model, data))
    viewer.cam.lookat[:] = data.xpos[bid]
    viewer.cam.distance, viewer.cam.elevation, viewer.cam.azimuth = args.cam_dist, -25.0, 135.0

dt = io.policy_dt
step, t_next, t0 = 0, time.perf_counter(), time.perf_counter()
fell = False
try:
    while (args.max_steps == 0 or step < args.max_steps) and (viewer is None or viewer.is_running()):
        # 1) 현재 위치로 명령 계산
        R = data.xmat[bid].reshape(3, 3)
        pos_now, yaw_now = data.xpos[bid], math.atan2(R[1, 0], R[0, 0])
        if follower is not None:
            vx, vy, wz, events = follower.command(pos_now[:2], yaw_now)
            for kind, val in events:
                if kind == "waypoint":
                    print(f"[MJ] 경유점 {val}/{follower.num_waypoints} 통과 t={step * dt:.1f}s 위치 ({pos_now[0]:.1f}, {pos_now[1]:.1f})", flush=True)
                else:
                    print(f"[MJ] 도착: t={step * dt:.1f}s, 목적지까지 {val:.2f} m, 위치 ({pos_now[0]:.2f}, {pos_now[1]:.2f}, z {pos_now[2]:.2f})", flush=True)
            cmd = (vx, vy, wz)
            if follower.arrived and args.exit_on_arrival:
                break
        else:
            cmd = fixed_cmd
        # 2) 정책 -> 관절 목표 -> 모터 모델 PD로 decimation번 적분
        state, pos, yaw, up = read_state(cmd)
        q_target = runner.act(state).astype(np.float64)
        for _ in range(io.decimation):
            data.ctrl[:] = motor(q_target, data.qpos[qadr], data.qvel[dadr])
            mujoco.mj_step(model, data)
        step += 1
        # 3) 넘어짐/추락 검사
        if up < math.cos(math.radians(70)) or data.xpos[bid][2] < ground_z - 3.0:
            print(f"[MJ] 넘어짐/추락: t={step * dt:.1f}s 위치 ({data.xpos[bid][0]:.1f}, {data.xpos[bid][1]:.1f}, z {data.xpos[bid][2]:.2f}), 기울기 {math.degrees(math.acos(max(-1, min(1, up)))):.0f}도"
                  + (f", 경유점 {follower.idx}/{follower.num_waypoints} 진행 중" if follower else ""), flush=True)
            fell = True
            break
        if step % 250 == 0:
            print(f"[MJ] step {step} (t={step * dt:.0f}s) base xyz = ({pos_now[0]:.2f}, {pos_now[1]:.2f}, {pos_now[2]:.2f})", flush=True)
        if viewer is not None:
            if args.follow:
                viewer.cam.lookat[:] = data.xpos[bid]
            viewer.sync()
            if not args.no_realtime:
                t_next += dt
                time.sleep(max(0.0, t_next - time.perf_counter()))
except KeyboardInterrupt:
    pass
print(f"[MJ] 종료: {step} step ({step * dt:.1f} s 시뮬레이션, 실제 {time.perf_counter() - t0:.1f} s)" + (", 넘어짐" if fell else ""), flush=True)
sys.stdout.flush()
sys.stderr.flush()
if viewer is not None:
    # 창 모드: viewer.close()와 프로세스 정리 단계에서 GL 라이브러리가 세그멘테이션 오류를 내는 환경이 있어(MuJoCo 3.12 + GLFW),
    # close()도 부르지 않고 바로 끝냅니다. 결과는 위에서 이미 출력했고 창은 프로세스가 끝나며 닫힙니다.
    print("[MJ] 프로세스 종료(창 모드)", flush=True)
    os._exit(1 if fell else 0)
sys.exit(1 if fell else 0)
