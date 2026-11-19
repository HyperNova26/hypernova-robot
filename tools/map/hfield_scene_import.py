#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""MuJoCo hfield 장면(PAIR360 mesh_v3 형식)을 MuJoCo, Isaac Sim, Isaac Lab이 같이 쓰는 입력으로 바꿉니다.

세 시뮬레이터가 같은 hfield에서 나온 같은 지형 위를 걷게 하는 것이 목적입니다(시뮬레이터 사이 도착 시간 차이의 원인에서 지형을 빼기 위해).
MuJoCo는 받은 scene.xml을 그대로 씁니다. 이 도구는 나머지를 만듭니다.

  ground_grid.npz            지면 높이 격자. z[행(y), 열(x)], x0·y0·res(최근접 꼭짓점 조회용 셀 경계), nogo_z(이동 금지 hfield 윗면)
  isaac/terrain_ground.usdc  지면 삼각형 메시(충돌 + height scan ray가 맞는 면). 경로 둘레(--margin)만 자릅니다
  isaac/terrain_obstacles.usdc  이동 금지 장애물 메시(충돌만, height scan에는 보이지 않음)와 나무 줄기·밑동(충돌만)
  isaac/scene_<이름>.usda    Isaac Sim 장면(--robot-usd 이름=경로를 주면). 지형 둘 + 로봇 참조
  report.json                입력·출력 해시, 크기, 검증 결과, 실행 인자

이 도구가 하는 확인(실패하면 오류로 끝냄)
  1. MuJoCo가 hfield 셀을 삼각형으로 나누는 대각선 방향을, 무작위 점의 광선 높이와 두 방향의 해석 높이를 비교해 정함(추정하지 않음).
  2. 쓴 USD를 다시 읽어, 같은 무작위 점의 메시 높이가 MuJoCo 광선 높이와 같은지 비교.
충돌 모양은 MuJoCo와 같게 둡니다: 지면 hfield + 이동 금지 hfield(group 4) + 나무 줄기·밑동(group 2). 수관(group 3, contype 0)은 충돌이 없어서 뺍니다.
height scan은 MuJoCo처럼 지면(group 0)만 봅니다. 그래서 이동 금지 장애물은 지면 메시와 다른 파일에 둡니다.

실행(컨테이너 robot venv: numpy, scipy, mujoco 3.12, usd-core가 있는 곳)
  ./docker/hn sim /opt/hn-venv/bin/python tools/map/hfield_scene_import.py \\
      --scene /data/pair360_map_v3/src/PAIR360-Go2-mesh_v3/scene/scene.xml --out /data/pair360_map_v3/derived \\
      --robot-usd v1=/data/usd/hn_v1_hyper/hypernova_hyper/hypernova_hyper.usda \\
      --route-yaml sim_scenes/pair360_map_v3/routes.yaml
출력 폴더가 이미 있으면 거부합니다. 좌표는 입력 장면의 좌표를 그대로 씁니다(변환 없음, 단위 m).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

TOOL_VERSION = "1"
RAISED_EPS_M = 0.01      # 이동 금지 hfield가 지면보다 이만큼 높은 꼭짓점을 장애물로 봅니다
MIN_CLEARANCE_M = 0.3    # 경로 파일에는 이동 금지와 나무 줄기까지 이 거리 이상 떨어진 경로만 씁니다(로봇 폭의 절반 남짓)
FRICTION = 1.0           # 기존 데모 지형 USD(GroundMaterial)와 같은 정지·운동 마찰


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------ hfield 읽기
class HField:
    """MuJoCo hfield 하나를 세계 좌표 높이 격자로 바꾼 것. z[행(y), 열(x)], 꼭짓점 값."""

    def __init__(self, model, data, name: str):
        import mujoco

        self.name = name
        hid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_HFIELD, name)
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        if hid < 0 or gid < 0:
            raise SystemExit(f"hfield·geom '{name}'이 장면에 없습니다")
        nrow, ncol = int(model.hfield_nrow[hid]), int(model.hfield_ncol[hid])
        adr = int(model.hfield_adr[hid])
        norm = np.asarray(model.hfield_data[adr:adr + nrow * ncol], np.float64).reshape(nrow, ncol)
        size = np.asarray(model.hfield_size[hid], np.float64)          # 반경 x, 반경 y, 최대 높이, 바닥 두께
        pos = np.asarray(model.geom_pos[gid], np.float64)
        if np.abs(model.geom_quat[gid] - [1, 0, 0, 0]).max() > 1e-9:
            raise SystemExit(f"hfield geom '{name}'에 회전이 있습니다(지원하지 않음)")
        self.res_x = 2 * size[0] / (ncol - 1)
        self.res_y = 2 * size[1] / (nrow - 1)
        if abs(self.res_x - self.res_y) > 1e-9:
            raise SystemExit(f"hfield 격자 간격이 x({self.res_x})와 y({self.res_y})에서 다릅니다")
        self.res = float(self.res_x)
        self.vx0, self.vy0 = float(pos[0] - size[0]), float(pos[1] - size[1])        # 열 0, 행 0 꼭짓점의 세계 좌표
        self.nrow, self.ncol = nrow, ncol
        self.z = pos[2] + norm * size[2]                                              # 세계 높이 [m]
        self.group = int(model.geom_group[gid])


def tri_height(z00, z10, z01, z11, u, v, diag: str):
    """셀 안 (u, v) in [0,1]^2의 삼각형 보간 높이. 꼭짓점: 00=(col,row) 10=(col+1,row) 01=(col,row+1) 11=(col+1,row+1).
    diag 'A': 00-11 대각선, 'B': 10-01 대각선."""
    if diag == "A":
        zl = z00 + u * (z10 - z00) + v * (z11 - z10)
        zu = z00 + u * (z11 - z01) + v * (z01 - z00)
        return np.where(u >= v, zl, zu)
    zl = z00 + u * (z10 - z00) + v * (z01 - z00)
    zu = z11 + (1 - u) * (z01 - z11) + (1 - v) * (z10 - z11)
    return np.where(u + v <= 1, zl, zu)


def cell_corners(hf: HField, ii, jj):
    z = hf.z
    return z[jj, ii], z[jj, ii + 1], z[jj + 1, ii], z[jj + 1, ii + 1]


def sample_points(hf: HField, n: int, rng, bbox):
    """bbox 안 임의의 셀에서 무작위 (x, y). 셀 경계를 피해 (u, v)를 0.02~0.98에서 고릅니다."""
    i0, i1 = int(math.ceil((bbox[0] - hf.vx0) / hf.res)), int(math.floor((bbox[2] - hf.vx0) / hf.res)) - 1
    j0, j1 = int(math.ceil((bbox[1] - hf.vy0) / hf.res)), int(math.floor((bbox[3] - hf.vy0) / hf.res)) - 1
    ii, jj = rng.integers(i0, i1 + 1, n), rng.integers(j0, j1 + 1, n)
    u, v = rng.uniform(0.02, 0.98, n), rng.uniform(0.02, 0.98, n)
    return ii, jj, u, v, hf.vx0 + (ii + u) * hf.res, hf.vy0 + (jj + v) * hf.res


def mj_surface_z(model, data, xs, ys, group: int):
    import mujoco

    mask = np.zeros(6, np.uint8)
    mask[group] = 1
    out = np.empty(len(xs))
    gid = np.zeros(1, np.int32)
    for k, (x, y) in enumerate(zip(xs, ys)):
        d = mujoco.mj_ray(model, data, np.array([x, y, 100.0]), np.array([0, 0, -1.0]), mask, 1, -1, gid)
        out[k] = np.nan if d < 0 else 100.0 - d
    return out


def detect_diagonal(model, data, hf: HField, bbox, rng, n=3000):
    ii, jj, u, v, xs, ys = sample_points(hf, n, rng, bbox)
    ray = mj_surface_z(model, data, xs, ys, hf.group)
    z00, z10, z01, z11 = cell_corners(hf, ii, jj)
    err = {d: float(np.nanmax(np.abs(tri_height(z00, z10, z01, z11, u, v, d) - ray))) for d in ("A", "B")}
    best = min(err, key=err.get)
    if err[best] > 1e-3:
        raise SystemExit(f"MuJoCo hfield 삼각분할을 식별하지 못했습니다(대각선 A/B 최대 오차 {err}). 이 도구가 아는 규약과 다른 입력입니다")
    return best, err


# ------------------------------------------------------------------------------------------ 메시 만들기
def grid_mesh(zfull, vx0, vy0, res, i0, i1, j0, j1, diag: str, cell_mask=None):
    """꼭짓점 구간 [i0..i1] x [j0..j1]의 삼각형 메시. cell_mask(셀 단위 bool, 크기 (ny-1, nx-1))가 있으면 그 셀만."""
    nx, ny = i1 - i0 + 1, j1 - j0 + 1
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
    pts = np.stack([vx0 + ii * res, vy0 + jj * res, zfull[j0:j1 + 1, i0:i1 + 1]], -1).reshape(-1, 3)
    cj, ci = np.meshgrid(np.arange(ny - 1), np.arange(nx - 1), indexing="ij")
    a = (cj * nx + ci).ravel()
    if cell_mask is not None:
        a = a[cell_mask.ravel()]
    b, c, d = a + 1, a + nx, a + nx + 1
    if diag == "A":
        tri = np.stack([np.stack([a, b, d], -1), np.stack([a, d, c], -1)], 1)
    else:
        tri = np.stack([np.stack([a, b, c], -1), np.stack([b, d, c], -1)], 1)
    faces = tri.reshape(-1, 3)
    if cell_mask is not None:                      # 쓰는 꼭짓점만 남기고 번호를 다시 매깁니다
        used = np.unique(faces)
        faces = np.searchsorted(used, faces)
        pts = pts[used]
    return pts.astype(np.float32), faces.astype(np.int32)


def cylinder_mesh(radius, half_h, n=32):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.stack([radius * np.cos(ang), radius * np.sin(ang)], -1)
    bot = np.c_[ring, np.full(n, -half_h)]
    top = np.c_[ring, np.full(n, half_h)]
    pts = np.vstack([bot, top, [[0, 0, -half_h]], [[0, 0, half_h]]])
    cb, ct = 2 * n, 2 * n + 1
    f = []
    for k in range(n):
        k2 = (k + 1) % n
        f += [(k, k2, n + k2), (k, n + k2, n + k), (cb, k2, k), (ct, n + k, n + k2)]
    return pts.astype(np.float32), np.array(f, np.int32)


def ellipsoid_mesh(sx, sy, sz, nlat=12, nlon=24):
    pts = [[0, 0, sz]]
    for i in range(1, nlat):
        th = np.pi * i / nlat
        for k in range(nlon):
            ph = 2 * np.pi * k / nlon
            pts.append([sx * np.sin(th) * np.cos(ph), sy * np.sin(th) * np.sin(ph), sz * np.cos(th)])
    pts.append([0, 0, -sz])
    f = []
    for k in range(nlon):
        f.append((0, 1 + k, 1 + (k + 1) % nlon))
    for i in range(nlat - 2):
        r0, r1 = 1 + i * nlon, 1 + (i + 1) * nlon
        for k in range(nlon):
            k2 = (k + 1) % nlon
            f += [(r0 + k, r1 + k, r1 + k2), (r0 + k, r1 + k2, r0 + k2)]
    last = len(pts) - 1
    r = 1 + (nlat - 2) * nlon
    for k in range(nlon):
        f.append((last, r + (k + 1) % nlon, r + k))
    return np.array(pts, np.float32), np.array(f, np.int32)


# ------------------------------------------------------------------------------------------ USD 쓰기
def _usd():
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt  # noqa: F401

    return Gf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt


def new_stage(path: Path):
    Gf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt = _usd()
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    mat = UsdShade.Material.Define(stage, "/World/PhysicsMaterials/GroundMaterial")
    pm = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    pm.CreateStaticFrictionAttr(FRICTION)
    pm.CreateDynamicFrictionAttr(FRICTION)
    pm.CreateRestitutionAttr(0.0)
    pm.CreateDensityAttr(0.0)
    return stage, mat


def add_mesh(stage, mat, path: str, pts, faces, approximation: str, translate=None):
    Gf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt = _usd()
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(pts, np.float32)))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(faces), 3, np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(np.ascontiguousarray(faces.reshape(-1), np.int32)))
    mesh.CreateSubdivisionSchemeAttr("none")
    mesh.CreateDoubleSidedAttr(True)
    lo, hi = pts.min(0), pts.max(0)
    mesh.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))]))
    if translate is not None:
        UsdGeom.Xformable(mesh).AddTranslateOp().Set(Gf.Vec3d(*map(float, translate)))
    prim = mesh.GetPrim()
    UsdPhysics.CollisionAPI.Apply(prim)
    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr(approximation)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")
    return mesh


SCENE_TEMPLATE = '''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    subLayers = [
        @./terrain_ground.usdc@,
        @./terrain_obstacles.usdc@
    ]
    upAxis = "Z"
)

over "World"
{{
    def PhysicsScene "PhysicsScene"
    {{
        vector3f physics:gravityDirection = (0, 0, -1)
        float physics:gravityMagnitude = 9.81
    }}

    def DistantLight "Sun"
    {{
        float inputs:intensity = 3000
    }}

    def DomeLight "Sky"
    {{
        float inputs:intensity = 500
    }}

    def Xform "Robot" (
        prepend references = @{robot_ref}@
    )
    {{
        double3 xformOp:translate = ({sx}, {sy}, {sz})
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }}
}}
'''


def write_scene(path: Path, robot_usd: str, start_xyz):
    ref = os.path.relpath(robot_usd, path.parent).replace(os.sep, "/")
    path.write_text(SCENE_TEMPLATE.format(robot_ref=ref, sx=start_xyz[0], sy=start_xyz[1], sz=start_xyz[2] + 0.4), encoding="utf-8")


# ------------------------------------------------------------------------------------------ 경로 점검
def densify(poly, step=0.05):
    pts = [np.asarray(poly[0], float)]
    for a, b in zip(poly[:-1], poly[1:]):
        a, b = np.asarray(a, float), np.asarray(b, float)
        n = max(int(np.ceil(np.hypot(*(b - a)) / step)), 1)
        pts += [a + (b - a) * (k / n) for k in range(1, n + 1)]
    return np.array(pts)


def check_route(name, poly, ground: HField, nogo: HField, diag, trees, raised_mask):
    from scipy.spatial import cKDTree

    p = densify(poly)
    ii = np.clip(((p[:, 0] - ground.vx0) / ground.res).astype(int), 0, ground.ncol - 2)
    jj = np.clip(((p[:, 1] - ground.vy0) / ground.res).astype(int), 0, ground.nrow - 2)
    u, v = (p[:, 0] - ground.vx0) / ground.res - ii, (p[:, 1] - ground.vy0) / ground.res - jj
    z = tri_height(*cell_corners(ground, ii, jj), u, v, diag)
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    # 0.5 m 간격 기울기
    k = max(int(0.5 / 0.05), 1)
    slope = np.abs(z[k:] - z[:-k]) / np.maximum(s[k:] - s[:-k], 1e-9)
    rj, ri = np.nonzero(raised_mask)
    obst = np.c_[ground.vx0 + ri * ground.res, ground.vy0 + rj * ground.res]
    clear = np.inf
    if len(obst):
        near = obst[(obst[:, 0] > p[:, 0].min() - 5) & (obst[:, 0] < p[:, 0].max() + 5) & (obst[:, 1] > p[:, 1].min() - 5) & (obst[:, 1] < p[:, 1].max() + 5)]
        if len(near):
            clear = float(cKDTree(near).query(p)[0].min())
    tclear = np.inf
    for (tx, ty, tr) in trees:
        tclear = min(tclear, float(np.hypot(p[:, 0] - tx, p[:, 1] - ty).min() - tr))
    return {"route": name, "length_m": round(float(s[-1]), 2), "z_start": round(float(z[0]), 3), "z_end": round(float(z[-1]), 3),
            "max_slope_pct_0p5m": round(float(slope.max()) * 100, 1), "min_clearance_to_nogo_m": round(clear, 2),
            "min_clearance_to_tree_m": round(tclear, 2)}


# ------------------------------------------------------------------------------------------ 본체
def parse_bbox(s):
    v = [float(t) for t in s.split(",")]
    if len(v) != 4 or v[0] >= v[2] or v[1] >= v[3]:
        raise argparse.ArgumentTypeError("x0,y0,x1,y1 (x0<x1, y0<y1)")
    return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", required=True, type=Path, help="입력 MuJoCo scene.xml(hfield 둘 포함)")
    ap.add_argument("--out", required=True, type=Path, help="출력 폴더(이미 있으면 거부)")
    ap.add_argument("--manifest", type=Path, help="manifest.json(기본: scene.xml 옆). 시작·목표·경유점과 참조 경로")
    ap.add_argument("--ground", default="pair360_ground_000", help="지면 hfield geom 이름")
    ap.add_argument("--nogo", default="pair360_nogo_000", help="이동 금지 hfield geom 이름")
    ap.add_argument("--margin", type=float, default=30.0, help="Isaac 메시를 경로 둘레 이 거리 [m]만큼 자릅니다(기본 30). 전체는 --margin 1000")
    ap.add_argument("--bbox", type=parse_bbox, help="x0,y0,x1,y1로 직접 자름(--margin보다 우선)")
    ap.add_argument("--no-trees", action="store_true", help="나무 줄기·밑동을 Isaac 장애물에 넣지 않음")
    ap.add_argument("--robot-usd", action="append", default=[], metavar="이름=경로", help="Isaac Sim 장면에 참조할 로봇 USD. 여러 번 가능")
    ap.add_argument("--route-yaml", type=Path, help="manifest에서 경로 파일(routes.yaml)을 만들고 점검 결과를 주석에 적음")
    ap.add_argument("--verify-samples", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    import mujoco
    from pxr import Usd, UsdGeom  # noqa: F401  (없으면 여기서 실패하도록 먼저 불러 봄)

    if args.out.exists():
        raise SystemExit(f"출력 경로가 이미 있습니다: {args.out}")
    scene = args.scene.resolve()
    manifest_path = args.manifest or scene.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None

    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    ground, nogo = HField(model, data, args.ground), HField(model, data, args.nogo)
    if (ground.nrow, ground.ncol, ground.vx0, ground.vy0, ground.res) != (nogo.nrow, nogo.ncol, nogo.vx0, nogo.vy0, nogo.res):
        raise SystemExit("지면과 이동 금지 hfield의 격자가 다릅니다(이 도구는 같은 격자만 지원)")
    rng = np.random.default_rng(args.seed)
    xmax, ymax = ground.vx0 + (ground.ncol - 1) * ground.res, ground.vy0 + (ground.nrow - 1) * ground.res
    full = [ground.vx0 + 1.0, ground.vy0 + 1.0, xmax - 1.0, ymax - 1.0]
    print(f"[IMPORT] hfield {ground.nrow}행 x {ground.ncol}열, 간격 {ground.res:.4f} m, x {ground.vx0:.2f}..{xmax:.2f}, y {ground.vy0:.2f}..{ymax:.2f}, "
          f"지면 z {ground.z.min():.2f}..{ground.z.max():.2f}", flush=True)

    diag, derr = detect_diagonal(model, data, ground, full, rng)
    print(f"[IMPORT] MuJoCo 삼각분할 대각선: {diag} (해석 높이와 광선 높이의 최대 오차 A {derr['A']:.2e} / B {derr['B']:.2e})", flush=True)

    raised_v = nogo.z > ground.z + RAISED_EPS_M
    raised_cells = raised_v[:-1, :-1] | raised_v[:-1, 1:] | raised_v[1:, :-1] | raised_v[1:, 1:]
    print(f"[IMPORT] 장애물 꼭짓점 {int(raised_v.sum()):,}개, 걸친 셀 {int(raised_cells.sum()):,}개", flush=True)

    # 나무(충돌하는 원기둥·타원체). hfield 밖의 충돌 geom이 다른 종류면 알려 줍니다.
    trees = []          # (geom id, kind, 세계 위치, 크기)
    skipped = {}
    for g in range(model.ngeom):
        t = int(model.geom_type[g])
        if t == int(mujoco.mjtGeom.mjGEOM_HFIELD):
            continue
        if int(model.geom_contype[g]) == 0 and int(model.geom_conaffinity[g]) == 0:
            skipped["충돌 없음(수관 등)"] = skipped.get("충돌 없음(수관 등)", 0) + 1
            continue
        kind = {int(mujoco.mjtGeom.mjGEOM_CYLINDER): "cylinder", int(mujoco.mjtGeom.mjGEOM_ELLIPSOID): "ellipsoid"}.get(t)
        if kind is None:
            raise SystemExit(f"충돌 geom '{mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)}'의 종류({t})를 지원하지 않습니다")
        R = np.asarray(data.geom_xmat[g]).reshape(3, 3)
        if np.abs(R - np.eye(3)).max() > 1e-6:
            raise SystemExit(f"충돌 geom '{mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)}'에 회전이 있습니다(지원하지 않음)")
        trees.append((mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g), kind, np.asarray(data.geom_xpos[g]), np.asarray(model.geom_size[g])))
    print(f"[IMPORT] 충돌 나무 geom {len(trees)}개, 건너뜀 {skipped}", flush=True)

    # 자를 범위
    pts_for_bbox = []
    if manifest:
        pts_for_bbox += [manifest["start"]["xy"], manifest["goal"]["xy"]] + list(manifest.get("via", [])) + [p[:2] for p in manifest.get("route_xyz_m", [])]
    if args.bbox:
        bbox = args.bbox
    elif pts_for_bbox:
        a = np.array(pts_for_bbox)
        bbox = [a[:, 0].min() - args.margin, a[:, 1].min() - args.margin, a[:, 0].max() + args.margin, a[:, 1].max() + args.margin]
    else:
        bbox = full
    bbox = [max(bbox[0], ground.vx0), max(bbox[1], ground.vy0), min(bbox[2], xmax), min(bbox[3], ymax)]
    i0, i1 = int(math.ceil((bbox[0] - ground.vx0) / ground.res)), int(math.floor((bbox[2] - ground.vx0) / ground.res))
    j0, j1 = int(math.ceil((bbox[1] - ground.vy0) / ground.res)), int(math.floor((bbox[3] - ground.vy0) / ground.res))
    cbox = [ground.vx0 + i0 * ground.res, ground.vy0 + j0 * ground.res, ground.vx0 + i1 * ground.res, ground.vy0 + j1 * ground.res]
    print(f"[IMPORT] Isaac 메시 범위 x {cbox[0]:.1f}..{cbox[2]:.1f}, y {cbox[1]:.1f}..{cbox[3]:.1f} ({(cbox[2]-cbox[0])*(cbox[3]-cbox[1]):,.0f} m2)", flush=True)

    args.out.mkdir(parents=True)
    (args.out / "isaac").mkdir()

    # 1) 지면 격자(전체)
    np.savez(args.out / "ground_grid.npz", z=ground.z.astype(np.float32), nogo_z=nogo.z.astype(np.float32),
             x0=np.float64(ground.vx0 - ground.res / 2), y0=np.float64(ground.vy0 - ground.res / 2), res=np.float64(ground.res),
             vertex_x0=np.float64(ground.vx0), vertex_y0=np.float64(ground.vy0), diagonal=np.array(diag),
             source_scene_sha256=np.array(sha256(scene)))

    # 2) Isaac 지면 메시
    gp, gf = grid_mesh(ground.z, ground.vx0, ground.vy0, ground.res, i0, i1, j0, j1, diag)
    stage, mat = new_stage(args.out / "isaac" / "terrain_ground.usdc")
    add_mesh(stage, mat, "/World/PAIR360Ground", gp, gf, "none")
    stage.GetRootLayer().Save()
    print(f"[IMPORT] terrain_ground.usdc: 꼭짓점 {len(gp):,}, 삼각형 {len(gf):,}", flush=True)

    # 3) Isaac 장애물(이동 금지 hfield 중 지면보다 높은 셀 + 나무)
    cell_mask = raised_cells[j0:j1, i0:i1]
    stage, mat = new_stage(args.out / "isaac" / "terrain_obstacles.usdc")
    n_nogo = 0
    if cell_mask.any():
        op, of = grid_mesh(nogo.z, ground.vx0, ground.vy0, ground.res, i0, i1, j0, j1, diag, cell_mask)
        add_mesh(stage, mat, "/World/Nogo", op, of, "none")
        n_nogo = len(of)
    n_trees = 0
    tree_xy_r = []
    for name, kind, pos, size in trees:
        tree_xy_r.append((float(pos[0]), float(pos[1]), float(size[0]) if kind == "cylinder" else float(max(size[0], size[1]))))
        if args.no_trees or not (cbox[0] - 3 <= pos[0] <= cbox[2] + 3 and cbox[1] - 3 <= pos[1] <= cbox[3] + 3):
            continue
        tp, tf = cylinder_mesh(size[0], size[1]) if kind == "cylinder" else ellipsoid_mesh(*size[:3])
        add_mesh(stage, mat, f"/World/Trees/{name}", tp, tf, "convexHull", translate=pos)
        n_trees += 1
    stage.GetRootLayer().Save()
    print(f"[IMPORT] terrain_obstacles.usdc: 이동 금지 삼각형 {n_nogo:,}, 나무 geom {n_trees}", flush=True)

    # 4) 다시 읽어 검증: 쓴 메시의 높이 == MuJoCo 광선 높이
    from pxr import Usd as _Usd, UsdGeom as _UsdGeom

    st = _Usd.Stage.Open(str(args.out / "isaac" / "terrain_ground.usdc"))
    m = _UsdGeom.Mesh(st.GetPrimAtPath("/World/PAIR360Ground"))
    rp = np.array(m.GetPointsAttr().Get(), np.float64)
    rf = np.array(m.GetFaceVertexIndicesAttr().Get(), np.int64).reshape(-1, 3)
    ii, jj, u, v, xs, ys = sample_points(ground, args.verify_samples, np.random.default_rng(args.seed + 1), cbox)
    nx = i1 - i0 + 1
    cell = (jj - j0) * (nx - 1) + (ii - i0)
    z_mesh = np.empty(len(xs))
    for k in range(len(xs)):
        tris = rp[rf[2 * cell[k]:2 * cell[k] + 2]]                       # 이 셀의 삼각형 둘
        for tri in tris:
            (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = tri
            den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
            l1 = ((y2 - y3) * (xs[k] - x3) + (x3 - x2) * (ys[k] - y3)) / den
            l2 = ((y3 - y1) * (xs[k] - x3) + (x1 - x3) * (ys[k] - y3)) / den
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) >= -1e-9:
                z_mesh[k] = l1 * z1 + l2 * z2 + l3 * z3
                break
        else:
            z_mesh[k] = np.nan
    ray = mj_surface_z(model, data, xs, ys, ground.group)
    d = np.abs(z_mesh - ray)
    verify = {"samples": int(len(xs)), "max_abs_err_m": float(np.nanmax(d)), "mean_abs_err_m": float(np.nanmean(d)),
              "nan_mesh": int(np.isnan(z_mesh).sum()), "nan_ray": int(np.isnan(ray).sum())}
    print(f"[IMPORT] 검증: 쓴 USD 메시 vs MuJoCo 광선 {verify['samples']}점, 최대 오차 {verify['max_abs_err_m']:.2e} m, 평균 {verify['mean_abs_err_m']:.2e} m, NaN {verify['nan_mesh']}/{verify['nan_ray']}", flush=True)
    if not (verify["max_abs_err_m"] < 1e-3 and verify["nan_mesh"] == 0 and verify["nan_ray"] == 0):
        raise SystemExit("검증 실패: 쓴 메시가 MuJoCo hfield와 다릅니다")

    # 5) 경로 점검 + 경로 파일
    route_checks = []
    start_xyz = None
    if manifest:
        sx, sy = manifest["start"]["xy"]
        ii0, jj0 = int((sx - ground.vx0) / ground.res), int((sy - ground.vy0) / ground.res)
        sz = float(tri_height(*cell_corners(ground, np.array([ii0]), np.array([jj0])), np.array([(sx - ground.vx0) / ground.res - ii0]),
                              np.array([(sy - ground.vy0) / ground.res - jj0]), diag)[0])
        start_xyz = (sx, sy, sz)
        routes = {}
        if manifest.get("route_xyz_m"):
            ref = [p[:2] for p in manifest["route_xyz_m"]]
            routes["A"] = ("지형 팀이 막힘 없음을 확인한 참조 경로(manifest route_xyz_m)", ref)
        via = [manifest["start"]["xy"]] + list(manifest.get("via", [])) + [manifest["goal"]["xy"]]
        routes["via"] = ("manifest의 시작 -> 경유점 -> 목표를 직선으로 이음", via)
        for nm, (_, poly) in routes.items():
            route_checks.append(check_route(nm, poly, ground, nogo, diag, tree_xy_r, raised_cells))
            print(f"[IMPORT] 경로 {nm}: {route_checks[-1]}", flush=True)
        ok_routes = {c["route"] for c in route_checks if min(c["min_clearance_to_nogo_m"], c["min_clearance_to_tree_m"]) >= MIN_CLEARANCE_M}
        for c in route_checks:
            if c["route"] not in ok_routes:
                print(f"[IMPORT] 경로 {c['route']}는 이동 금지 또는 나무 줄기에 {MIN_CLEARANCE_M} m보다 가까워 경로 파일에 쓰지 않습니다", flush=True)
        if args.route_yaml:
            lines = ["# SPDX-License-Identifier: Apache-2.0", "#",
                     "# PAIR360 mesh_v3 지형 위의 경로. Isaac Lab, MuJoCo, Isaac Sim 재생 스크립트가 같은 파일을 읽습니다.",
                     f"# 생성: tools/map/hfield_scene_import.py (v{TOOL_VERSION}, mujoco {mujoco.__version__}). 손으로 고치지 않고 다시 생성합니다.",
                     f"# 입력: manifest.json sha256 {sha256(manifest_path)} / scene.xml sha256 {sha256(scene)}",
                     "# 좌표는 입력 장면의 pair360_map 좌표 그대로입니다(변환 없음, x/y/z 단위 m, M-002 공통 원점 적용 전).",
                     "# 목표는 지형 팀이 촬영 화면과 측정 흔적으로 추정한 값이라 +-3~5 m 오차가 있습니다(mesh_v3 README).",
                     "# 점검(아래 값은 지면 hfield와 이동 금지 hfield, 나무 줄기 기준): "]
            for c in route_checks:
                if c["route"] not in ok_routes:
                    continue
                lines.append(f"#   {c['route']}: 길이 {c['length_m']} m, 최대 경사 {c['max_slope_pct_0p5m']}% (0.5 m 간격), 이동 금지까지 최소 {c['min_clearance_to_nogo_m']} m, 나무 줄기까지 최소 {c['min_clearance_to_tree_m']} m")
            lines += ["frame: pair360_map (x, y, z=up, m)", "routes:"]
            for nm, (desc, poly) in routes.items():
                if nm not in ok_routes:
                    continue
                lines += [f"  {nm}:", f"    description: {desc}", f"    start: [{poly[0][0]}, {poly[0][1]}]", "    waypoints:"]
                lines += [f"      - [{p[0]}, {p[1]}]" for p in poly[1:]]
            args.route_yaml.parent.mkdir(parents=True, exist_ok=True)
            args.route_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"[IMPORT] 경로 파일: {args.route_yaml}", flush=True)

    # 6) Isaac Sim 장면
    scenes = []
    for item in args.robot_usd:
        nm, _, rp_ = item.partition("=")
        if not rp_:
            raise SystemExit("--robot-usd는 이름=경로 형식입니다")
        write_scene(args.out / "isaac" / f"scene_{nm}.usda", rp_, start_xyz or (0.0, 0.0, 0.0))
        scenes.append(f"scene_{nm}.usda")

    report = {
        "tool": "hfield_scene_import.py", "tool_version": TOOL_VERSION, "mujoco": mujoco.__version__, "argv": sys.argv[1:],
        "input": {"scene_xml": str(scene), "scene_xml_sha256": sha256(scene),
                  "manifest_sha256": sha256(manifest_path) if manifest else None,
                  "hfield": {"rows": ground.nrow, "cols": ground.ncol, "res_m": ground.res, "x0": ground.vx0, "y0": ground.vy0,
                             "z_min": float(ground.z.min()), "z_max": float(ground.z.max())}},
        "diagonal": diag, "diagonal_fit_max_err_m": derr, "isaac_bbox": cbox, "raised_vertices": int(raised_v.sum()),
        "meshes": {"ground_triangles": int(len(gf)), "nogo_triangles": int(n_nogo), "tree_geoms": n_trees},
        "verify": verify, "route_checks": route_checks, "scenes": scenes,
        "outputs": {str(p.relative_to(args.out)): {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(args.out.rglob("*")) if p.is_file()},
    }
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[IMPORT] 완료: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
