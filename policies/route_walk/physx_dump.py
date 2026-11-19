# SPDX-License-Identifier: Apache-2.0
"""PhysX 로봇의 런타임 물리 파라미터 덤프(시뮬레이터 비교용). Isaac Sim 단독과 Isaac Lab이 같은 형식으로 씁니다.

두 군데에서 읽습니다.
  1. PhysX 텐서 API의 articulation view: 링크 질량·관성·무게중심, 관절 armature·마찰·최대 속도·강성·감쇠·한계, 형상별 재질(정지·운동 마찰, 반발)
  2. 실행 중인 USD 스테이지의 PhysX 속성: 장면(PhysicsScene), 로봇 링크·관절·충돌체(contact/rest offset 등), 지형 충돌체, 재질
시뮬레이터에서 실제로 적용된 값이라서, 파일(USD)이나 설정(cfg)에 적힌 값과 다를 수 있는 것을 잡으려는 도구입니다.
Isaac Sim 또는 Isaac Lab Python에서만 import합니다(pxr가 필요).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

VIEW_GETTERS = ("get_masses", "get_inertias", "get_coms", "get_dof_armatures", "get_dof_friction_coefficients", "get_dof_max_velocities",
                "get_dof_max_forces", "get_dof_stiffnesses", "get_dof_dampings", "get_dof_limits", "get_material_properties",
                "get_link_incoming_joint_force")
ATTR_PREFIXES = ("physxArticulation:", "physxRigidBody:", "physxCollision:", "physxJoint:", "physxScene:", "physxMaterial:", "physics:", "drive:", "limit:",
                 "physxLimit:", "physxContactReport:", "physxTriangleMeshCollision:", "physxConvexHullCollision:")
SKIP = {"physics:points", "physics:faceVertexIndices", "physics:faceVertexCounts"}


def _to_list(v):
    if hasattr(v, "torch"):
        v = v.torch
    if hasattr(v, "detach"):
        v = v.detach().cpu().numpy()
    elif hasattr(v, "numpy"):
        v = v.numpy()
    return np.asarray(v).tolist()


def dump_view(view) -> dict:
    out = {}
    for name in VIEW_GETTERS:
        fn = getattr(view, name, None)
        if fn is None:
            out[name] = "없음"
            continue
        try:
            out[name] = _to_list(fn())
        except Exception as e:  # noqa: BLE001
            out[name] = f"오류: {e}"
    return out


def dump_stage(stage, roots) -> dict:
    """roots 아래(와 각 root 자체) prim의 PhysX·물리 속성을 모읍니다. 큰 배열은 건너뜁니다."""
    from pxr import Usd

    out = {}
    for root in roots:
        prim = stage.GetPrimAtPath(root)
        if not prim.IsValid():
            out[root] = "prim 없음"
            continue
        for p in Usd.PrimRange(prim):
            attrs = {}
            for a in p.GetAttributes():
                n = a.GetName()
                if n in SKIP or not n.startswith(ATTR_PREFIXES):
                    continue
                v = a.Get()
                if v is None:
                    continue
                attrs[n] = v if isinstance(v, (bool, int, float, str)) else str(v)
            if attrs:
                out[str(p.GetPath())] = attrs
    return out


def write_dump(path, view, stage, roots, meta=None) -> None:
    data = {"meta": meta or {}, "view": dump_view(view) if view is not None else None, "stage": dump_stage(stage, roots)}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
