#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Isaac Sim 단독(Isaac Lab 없이)에서 policy_io.yaml + numpy 러너(배포 경로)로 로봇이 경로를 걷게 합니다.

장면 USD(지형 충돌 메시 + 로봇)를 열고, PhysX 텐서 API로 관절 상태를 읽어 관측을 만들고, 정책(50 Hz)이 낸 관절 목표를
DC 모터 모델(policies/actuator_model.py)로 토크로 바꿔 매 물리 스텝(200 Hz) 가합니다. USD 드라이브의 강성·감쇠는 0으로 둡니다.
Isaac Lab 환경(play_isaaclab.py)과 달리 관리자(manager) 계층이 없어, 같은 정책이 순수 Isaac Sim 물리에서도 걷는지 확인하는 도구입니다.
height scan은 지면 높이 격자(.npz)에서 읽습니다(Isaac Lab의 RayCaster는 지형 메시 하나만 맞히므로 같은 값에 가깝습니다).

  ./docker/hn sim /workspace/isaaclab/isaaclab.sh -p <이 파일> --scene <scene_demo_v0.usda> --actor <actor.npz> \
      --ground-grid <ground_grid_demo.npz> --route-file <pair360_demo.yaml> --route A             # 창
  ... --headless --exit-on-arrival                                                              # 창 없이 시험

좌표는 데모 프레임(x=동, y=북, m). 창에서는 카메라가 로봇을 따라가되 마우스 돌리기·휠 줌이 됩니다(--follow 0이면 고정).
"""
import argparse
import math
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--yaml", default=str(Path(__file__).resolve().parents[1] / "urdf_v0" / "policy_io.yaml"))
ap.add_argument("--actor", required=True)
ap.add_argument("--scene", required=True, help="Isaac Sim 장면 USD(지형 + /World/Robot), 예: .../isaac/scene_demo_v0.usda")
ap.add_argument("--robot", default="/World/Robot")
ap.add_argument("--ground-grid", required=True, help="지면 높이 격자 .npz(시작 높이와 height scan에 씀)")
ap.add_argument("--route-file")
ap.add_argument("--route", default="A")
ap.add_argument("--start")
ap.add_argument("--waypoints")
ap.add_argument("--vmax", type=float, default=0.5)
ap.add_argument("--lookahead", type=float, default=1.5)
ap.add_argument("--max-steps", type=int, default=0, help="정책 스텝 수 상한(0이면 무제한). 1스텝 = 0.02 s")
ap.add_argument("--headless", action="store_true")
ap.add_argument("--exit-on-arrival", action="store_true")
ap.add_argument("--no-realtime", action="store_true")
ap.add_argument("--follow", type=int, default=1, help="1: 카메라가 로봇을 따라감(돌리기·줌 가능), 0: 고정")
ap.add_argument("--cam", default="5,-5,3.5", help="처음 카메라 위치(로봇 기준 dx,dy,dz)")
ap.add_argument("--no-markers", action="store_true", help="경유점 표시(빨간 구)를 끕니다")
ap.add_argument("--hold-default", action="store_true", help="정책 대신 기본 자세를 목표로 고정합니다(물리만 비교하는 통제 실험)")
ap.add_argument("--torque-delay", type=int, default=0, help="계산한 모터 토크를 이만큼의 물리 스텝(5 ms) 늦게 적용합니다(시뮬레이터 비교 실험용). 0이면 바로 적용")
ap.add_argument("--drop-offset", type=float, default=0.0, help="처음 낙하 높이(기본 0.40 m)에 더하는 값 [m]. 초기 조건을 조금 바꿔 걸음의 변동을 재는 실험용")
ap.add_argument("--apply-physx-dump", help="Isaac Lab 런타임 덤프(--hn-dump-physx 출력 JSON)에 적힌 PhysX 속성(장면, articulation, 링크, 충돌체, 관절)을 이 스테이지에 그대로 적용합니다(시뮬레이터 비교 실험용)")
ap.add_argument("--apply-physx-only", default="", help="--apply-physx-dump에서 이 접두사/이름으로 시작하는 속성만 적용합니다(쉼표 구분. 예: physxRigidBody:,physxScene:enableExternalForcesEveryIteration)")
ap.add_argument("--device", choices=("cpu", "cuda"), default="cpu",
                help="PhysX 파이프라인. cuda = GPU(Isaac Lab 학습 환경과 같은 파이프라인), cpu = CPU. 같은 정책이 두 파이프라인에서 속도가 다릅니다(docs/development/sim-parity.md)")
ap.add_argument("--physx-scene", action="append", default=[], metavar="이름=값",
                help="PhysicsScene의 physxScene:<이름> 속성을 바꿉니다(시뮬레이터 비교 실험용). 예: --physx-scene enableExternalForcesEveryIteration=true")
ap.add_argument("--robot-material", metavar="정지,운동[,결합]", help="로봇 물리 재질(실험용). 결합은 average|min|multiply|max. 기본 0.8,0.6(결합 미지정=PhysX 기본 average)")
ap.add_argument("--rigid-props", type=int, default=0, choices=(0, 1),
                help="1: 로봇 링크에 Isaac Lab 로봇 설정(policies/urdf_v1/robot.py의 rigid_props)과 같은 PhysX 강체 속성을 적습니다. 단독 Isaac Sim은 적지 않은 값에 PhysX 기본(예: angularDamping 0.05)이 적용됩니다")
ap.add_argument("--dump-physx", help="런타임 PhysX 파라미터(링크 질량·관성, 관절 속성, 재질, 스테이지 속성)를 이 JSON에 쓰고 끝냅니다(시뮬레이터 비교용)")
ap.add_argument("--trace", help="정책 입출력을 매 스텝 이 파일에 기록합니다(runner.enable_trace). 시뮬레이터 사이 비교용")
ap.add_argument("--self-collision", type=int, default=0, choices=(0, 1),
                help="1: articulation 자기충돌 켬. v1(HYPER)은 자기충돌을 켜고 학습했으므로 1, v0는 0")
args = ap.parse_args()
sys.argv = sys.argv[:1]                     # Kit이 우리 인자를 해석하지 않게 비움

from isaacsim import SimulationApp  # noqa: E402

app = SimulationApp({"headless": args.headless, "width": 1280, "height": 720})

import numpy as np  # noqa: E402
import omni.usd  # noqa: E402
from isaacsim.core.api import SimulationContext  # noqa: E402
from isaacsim.core.simulation_manager import SimulationManager  # noqa: E402
from isaacsim.core.utils.stage import open_stage  # noqa: E402
from pxr import Gf, PhysxSchema, UsdGeom, UsdPhysics, UsdShade  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actuator_model import DCMotor  # noqa: E402
from policy_io import load_policy_io  # noqa: E402
from route_nav import RouteFollower, load_route, parse_xy_list  # noqa: E402
from runner import PolicyRunner  # noqa: E402

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

# ---------------------------------------------------------------- 지면 높이 격자
_g = np.load(args.ground_grid)
GZ, GX0, GY0, GR = _g["z"], float(_g["x0"]), float(_g["y0"]), float(_g["res"])


def ground_z(x, y):
    """점 (x, y)의 지면 높이. 격자 최근접 셀, 구멍이거나 지형 밖이면 nan."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ix, iy = np.floor((x - GX0) / GR).astype(int), np.floor((y - GY0) / GR).astype(int)
    ok = (ix >= 0) & (ix < GZ.shape[1]) & (iy >= 0) & (iy < GZ.shape[0])
    out = np.full(np.shape(x), np.nan)
    out[ok] = GZ[iy[ok], ix[ok]]
    return out


start_z = float(ground_z(start[0], start[1]))
if math.isnan(start_z):
    raise SystemExit(f"시작점 ({start[0]}, {start[1]}) 아래에 지면이 없습니다(구멍이거나 지형 밖).")

# ---------------------------------------------------------------- 장면 준비(USD)
open_stage(args.scene)
stage = omni.usd.get_context().get_stage()
robot_prim = stage.GetPrimAtPath(args.robot)
if not robot_prim.IsValid():
    raise SystemExit(f"장면에 {args.robot}가 없습니다.")
root_path = next(str(p.GetPath()) for p in __import__("pxr").Usd.PrimRange(robot_prim) if p.HasAPI(UsdPhysics.ArticulationRootAPI))
# 학습 환경과 같은 solver 반복 수·자기충돌(--self-collision, v0 끔 / v1 켬)·로봇 마찰(정지 0.8, 운동 0.6)
art = PhysxSchema.PhysxArticulationAPI.Apply(stage.GetPrimAtPath(root_path))
art.CreateSolverPositionIterationCountAttr(4)
art.CreateSolverVelocityIterationCountAttr(0)
art.CreateEnabledSelfCollisionsAttr(bool(args.self_collision))
mat = UsdShade.Material.Define(stage, "/World/Looks/RobotPhysicsMaterial")
pm = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
_rm = (args.robot_material or "0.8,0.6").split(",")
pm.CreateStaticFrictionAttr(float(_rm[0]))
pm.CreateDynamicFrictionAttr(float(_rm[1]))
pm.CreateRestitutionAttr(0.0)
if len(_rm) > 2:
    PhysxSchema.PhysxMaterialAPI.Apply(mat.GetPrim()).CreateFrictionCombineModeAttr(_rm[2])
if args.rigid_props:
    _n = 0
    for _p in __import__("pxr").Usd.PrimRange(robot_prim):
        if _p.HasAPI(UsdPhysics.RigidBodyAPI):
            _rb = PhysxSchema.PhysxRigidBodyAPI.Apply(_p)
            _rb.CreateLinearDampingAttr(0.0)
            _rb.CreateAngularDampingAttr(0.0)
            _rb.CreateMaxLinearVelocityAttr(1000.0)
            _rb.CreateMaxAngularVelocityAttr(1000.0)
            _rb.CreateMaxDepenetrationVelocityAttr(1.0)
            _rb.CreateEnableGyroscopicForcesAttr(True)
            _rb.CreateRetainAccelerationsAttr(False)
            _n += 1
    print(f"[ISAACSIM] 강체 속성(Isaac Lab 로봇 설정과 같게) 적용: 링크 {_n}개", flush=True)
if args.apply_physx_dump:
    import json as _json

    _dump = _json.load(open(args.apply_physx_dump, encoding="utf-8"))["stage"]
    _APIS = {"physxRigidBody:": PhysxSchema.PhysxRigidBodyAPI, "physxArticulation:": PhysxSchema.PhysxArticulationAPI, "physxCollision:": PhysxSchema.PhysxCollisionAPI,
             "physxJoint:": PhysxSchema.PhysxJointAPI, "physxScene:": PhysxSchema.PhysxSceneAPI}
    _applied = _skipped = 0
    for _path, _attrs in _dump.items():
        if not isinstance(_attrs, dict):
            continue
        _path = _path.replace("/World/envs/env_0/Robot", "/World/Robot")
        if _path in ("/physicsScene", "/World/physicsScene"):
            _path = "/World/PhysicsScene"
        _prim = stage.GetPrimAtPath(_path)
        if not _prim.IsValid():
            continue
        for _name, _val in _attrs.items():
            _api = next((a for pre, a in _APIS.items() if _name.startswith(pre)), None)
            if args.apply_physx_only and not any(_name.startswith(t) for t in args.apply_physx_only.split(",")):
                continue
            if _api is None or isinstance(_val, str) and _val in ("inf", "-inf") or _name.endswith("launcherType"):
                _skipped += 1
                continue
            try:
                _api.Apply(_prim)
                _attr = _prim.GetAttribute(_name)
                if _attr and _attr.IsValid():
                    _attr.Set(_val if not isinstance(_val, str) or _attr.GetTypeName().type.pythonClass is None else _val)
                    _applied += 1
                else:
                    _skipped += 1
            except Exception:  # noqa: BLE001
                _skipped += 1
    print(f"[ISAACSIM] Isaac Lab PhysX 속성 적용: {_applied}개 적용, {_skipped}개 건너뜀", flush=True)
_scene_prim = stage.GetPrimAtPath("/World/PhysicsScene")
if args.physx_scene:
    PhysxSchema.PhysxSceneAPI.Apply(_scene_prim)
    for _item in args.physx_scene:
        _k, _, _v = _item.partition("=")
        _val = {"true": True, "false": False}.get(_v.lower())
        if _val is None:
            try:
                _val = int(_v)
            except ValueError:
                try:
                    _val = float(_v)
                except ValueError:
                    _val = _v
        _attr = _scene_prim.GetAttribute("physxScene:" + _k)
        if not _attr:
            raise SystemExit(f"physxScene:{_k} 속성이 없습니다")
        _attr.Set(_val)
    print(f"[ISAACSIM] 실험 설정: physxScene {args.physx_scene}", flush=True)
UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(args.robot + "/Geometry")).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")

# 경유점 표시(시각 전용). Isaac Lab과 같은 빨간 구(반지름 0.25 m, 지면 +0.3 m, 지면이 없으면 0+0.3).
# 충돌·물리 API를 붙이지 않아 시뮬레이션에 영향이 없습니다(height scan은 지면 격자에서 읽으므로 ray에도 잡히지 않음).
if not args.no_markers:
    for i, (wx, wy) in enumerate(wps):
        gz = float(ground_z(wx, wy))
        sphere = UsdGeom.Sphere.Define(stage, f"/World/RouteMarkers/wp_{i + 1:02d}")
        sphere.CreateRadiusAttr(0.25)
        sphere.AddTranslateOp().Set(Gf.Vec3d(wx, wy, (0.0 if math.isnan(gz) else gz) + 0.3))
        sphere.CreateDisplayColorAttr([Gf.Vec3f(1.0, 0.1, 0.1)])
    print(f"[ISAACSIM] 경유점 표시 {len(wps)}개(빨간 구, 시각 전용, /World/RouteMarkers)", flush=True)

GPU = args.device == "cuda"
sim = SimulationContext(physics_dt=io.sim_dt, rendering_dt=io.policy_dt, stage_units_in_meters=1.0,
                        backend="torch" if GPU else "numpy", device="cuda:0" if GPU else "cpu")
sim.reset()
view = SimulationManager.get_physics_sim_view().create_articulation_view(root_path)


class TorchViewAdapter:
    """GPU 파이프라인의 텐서 API view는 torch 텐서(GPU)를 주고받습니다. 이 플레이어의 나머지 코드는 numpy라서, 입출력만 바꿔 줍니다."""

    def __init__(self, v, device):
        self._v, self._dev = v, device

    @property
    def shared_metatype(self):
        return self._v.shared_metatype

    def __getattr__(self, name):
        fn = getattr(self._v, name)
        if not callable(fn):
            return fn
        if name.startswith("get_"):
            def getter(*a, **k):
                r = fn(*a, **k)
                return r.detach().cpu().numpy() if hasattr(r, "detach") else r
            return getter
        if name.startswith("set_"):
            import torch

            # 관절·링크 속성(강성, 감쇠, 질량 등) setter는 CPU 텐서만 받고, 상태·토크 setter는 GPU 텐서를 받습니다(PhysX 텐서 API).
            on_cpu = name in ("set_dof_stiffnesses", "set_dof_dampings", "set_dof_armatures", "set_dof_friction_coefficients", "set_dof_limits",
                              "set_dof_max_forces", "set_dof_max_velocities", "set_masses", "set_coms", "set_inertias", "set_material_properties")
            dev = "cpu" if on_cpu else self._dev

            def setter(data, indices, *a, **k):
                return fn(torch.as_tensor(np.asarray(data), dtype=torch.float32, device=dev),
                          torch.as_tensor(np.asarray(indices), dtype=torch.int32, device=dev), *a, **k)
            return setter
        return fn


if GPU:
    view = TorchViewAdapter(view, "cuda:0")
names = list(view.shared_metatype.dof_names)
perm = np.array([names.index(j) for j in io.joints])            # 정책 순서 i -> 뷰의 DOF 번호
idx0 = np.array([0], dtype=np.int32)
zeros12 = np.zeros((1, len(names)), np.float32)
view.set_dof_stiffnesses(zeros12, idx0)                         # USD 드라이브(강성 100/감쇠 1)는 끄고 토크로만 구동
view.set_dof_dampings(zeros12, idx0)
for _ in range(5):                                              # PhysX 초기화 스텝. 상태는 그 다음에 설정합니다(먼저 설정하면 이 스텝 동안 토크 없이 떨어져 MuJoCo·Isaac Lab과 출발 상태가 달라짐)
    sim.step(render=False)
q0 = np.zeros((1, len(names)), np.float32)
q0[0, perm] = io.default_pos
view.set_dof_positions(q0, idx0)
view.set_dof_velocities(zeros12, idx0)
qz = np.array([0.0, 0.0, math.sin(yaw0 / 2), math.cos(yaw0 / 2)])
view.set_root_transforms(np.array([[start[0], start[1], start_z + 0.40 + args.drop_offset, *qz]], np.float32), idx0)
view.set_root_velocities(np.zeros((1, 6), np.float32), idx0)

if args.dump_physx:
    from physx_dump import write_dump

    write_dump(args.dump_physx, view, stage, ["/World/PhysicsScene", root_path, "/World/PAIR360Ground", "/World/Nogo", "/World/PhysicsMaterials", "/World/Looks"],
               {"sim": "isaacsim", "scene": args.scene, "root": root_path, "dof_names": names})
    print(f"[ISAACSIM] PhysX 기록: {args.dump_physx}", flush=True)
    app.close()
    sys.exit(0)

motor = DCMotor(io)
_tau_q = [np.zeros(len(io.joints)) for _ in range(args.torque_delay)]   # 토크 지연 버퍼(--torque-delay)
runner = PolicyRunner(io, args.actor)
runner.reset()
runner.hold_default = args.hold_default
if args.trace:
    runner.enable_trace(args.trace, {"sim": "isaacsim", "scene": str(args.scene), "self_collision": args.self_collision})
follower = RouteFollower(start, wps, vmax=args.vmax, lookahead=args.lookahead) if wps else None
print(f"[ISAACSIM] 정책 가중치 {Path(args.actor).name} | articulation {root_path} | 시작 ({start[0]}, {start[1]}) 지면 z={start_z:+.2f} yaw {math.degrees(yaw0):.0f}도"
      + (f" | 경유점 {len(wps)}개" if wps else " | 경로 없음(고정 전진 명령)"), flush=True)

cam_follow = None
if not args.headless:
    try:
        from isaacsim.core.utils.viewports import set_camera_view
        from omni.kit.viewport.utility import get_active_viewport
        from omni.kit.viewport.utility.camera_state import ViewportCameraState
        from pxr import Gf

        dx, dy, dz = (float(v) for v in args.cam.split(","))
        set_camera_view(eye=np.array([start[0] + dx, start[1] + dy, start_z + dz]), target=np.array([start[0], start[1], start_z + 0.3]))
        for _ in range(5):
            sim.render()   # app.update()를 직접 부르면 타임라인이 재생 중이라 물리가 몇 스텝 진행됨(토크 없이 중력만 받은 채 출발해 창 없는 모드와 궤적이 달라졌음). sim.render()는 물리 진행을 끄고 갱신함
        if args.follow:
            vp = get_active_viewport()
            cam_follow = ViewportCameraState(vp.get_active_camera() or "/OmniverseKit_Persp", vp)
    except Exception as e:  # noqa: BLE001
        print(f"[ISAACSIM] 카메라 설정 생략: {e}", flush=True)


def read_state(command):
    pos_q = view.get_root_transforms()[0].astype(np.float64)
    vel = view.get_root_velocities()[0].astype(np.float64)
    x, y, z, qx, qy, qz_, qw = pos_q
    R = np.array([[1 - 2 * (qy * qy + qz_ * qz_), 2 * (qx * qy - qz_ * qw), 2 * (qx * qz_ + qy * qw)],
                  [2 * (qx * qy + qz_ * qw), 1 - 2 * (qx * qx + qz_ * qz_), 2 * (qy * qz_ - qx * qw)],
                  [2 * (qx * qz_ - qy * qw), 2 * (qy * qz_ + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])   # body -> world
    yaw = math.atan2(R[1, 0], R[0, 0])
    hit = ground_z(*io.height_scan_world_xy([x, y], yaw).T)
    hit = np.where(np.isfinite(hit), hit, 1.0e3)                # 지형 밖은 아주 높은 값 -> 관측 -1로 clip
    qv = view.get_dof_positions()[0]
    qdv = view.get_dof_velocities()[0]
    state = {
        "base_lin_vel_b": R.T @ vel[:3], "base_ang_vel_b": R.T @ vel[3:], "projected_gravity_b": R.T @ np.array([0.0, 0.0, -1.0]),
        "command": np.asarray(command), "joint_pos": qv[perm].astype(np.float64), "joint_vel": qdv[perm].astype(np.float64),
        "height_hits_z": hit, "base_pos_z": np.array([z]),
    }
    return state, np.array([x, y, z]), yaw, R[2, 2]


dt = io.policy_dt
step, t0, t_next = 0, time.perf_counter(), time.perf_counter()
fell = False
last_root = read_state((0, 0, 0))[1]
try:
    while (args.max_steps == 0 or step < args.max_steps) and app.is_running():
        _, pos_now, yaw_now, _ = read_state((0, 0, 0))
        if follower is not None:
            vx, vy, wz, events = follower.command(pos_now[:2], yaw_now)
            for kind, val in events:
                if kind == "waypoint":
                    print(f"[ISAACSIM] 경유점 {val}/{follower.num_waypoints} 통과 t={step * dt:.1f}s 위치 ({pos_now[0]:.1f}, {pos_now[1]:.1f})", flush=True)
                else:
                    print(f"[ISAACSIM] 도착: t={step * dt:.1f}s, 목적지까지 {val:.2f} m, 위치 ({pos_now[0]:.2f}, {pos_now[1]:.2f}, z {pos_now[2]:.2f})", flush=True)
            cmd = (vx, vy, wz)
            if follower.arrived and args.exit_on_arrival:
                break
        else:
            cmd = (args.vmax, 0.0, 0.0)
        state, pos, yaw, up = read_state(cmd)
        q_target = runner.act(state).astype(np.float64)
        for _ in range(io.decimation):
            tau = motor(q_target, view.get_dof_positions()[0][perm], view.get_dof_velocities()[0][perm])
            if args.torque_delay:
                _tau_q.append(tau)
                tau = _tau_q.pop(0)
            tau_v = np.zeros((1, len(names)), np.float32)
            tau_v[0, perm] = tau
            view.set_dof_actuation_forces(tau_v, idx0)
            sim.step(render=False)
        runner.trace_aux = np.abs(tau)                # 마지막 하위 스텝에 가한 토크(기록 중일 때만 쓰임)
        step += 1
        zg = ground_z(pos[0], pos[1])
        if up < math.cos(math.radians(70)) or view.get_root_transforms()[0][2] < (start_z if np.isnan(zg) else float(zg)) - 3.0:
            p = view.get_root_transforms()[0]
            print(f"[ISAACSIM] 넘어짐/추락: t={step * dt:.1f}s 위치 ({p[0]:.1f}, {p[1]:.1f}, z {p[2]:.2f}), 기울기 {math.degrees(math.acos(max(-1, min(1, up)))):.0f}도"
                  + (f", 경유점 {follower.idx}/{follower.num_waypoints} 진행 중" if follower else ""), flush=True)
            fell = True
            break
        if step % 250 == 0:
            print(f"[ISAACSIM] step {step} (t={step * dt:.0f}s) base xyz = ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})", flush=True)
        if not args.headless:
            if cam_follow is not None:               # 로봇이 움직인 만큼 카메라를 평행이동(사용자가 돌리거나 줌한 시점은 유지)
                d = pos - last_root
                p_, t_ = cam_follow.position_world, cam_follow.target_world
                cam_follow.set_position_world(p_ + Gf.Vec3d(*[float(v) for v in d]), False)
                cam_follow.set_target_world(t_ + Gf.Vec3d(*[float(v) for v in d]), True)
            sim.render()
            if not args.no_realtime:
                t_next += dt
                time.sleep(max(0.0, t_next - time.perf_counter()))
        last_root = pos
except KeyboardInterrupt:
    pass
print(f"[ISAACSIM] 종료: {step} step ({step * dt:.1f} s 시뮬레이션, 실제 {time.perf_counter() - t0:.1f} s)" + (", 넘어짐" if fell else ""), flush=True)
app.close()
sys.exit(1 if fell else 0)
