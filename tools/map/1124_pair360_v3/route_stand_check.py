"""Stand the Menagerie Go2 at points along route_xyz_m, facing the route, ramp included.

No gait controller: this checks foot contact and posture on the local slope only.
python route_stand_check.py /path/to/unitree_go2/go2.xml [--step 1.0] [--seconds 2]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

from load_go2 import SCENE_DIR, load_go2

TERRAIN = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)


def floor(model, data, xy):
    dist = mujoco.mj_ray(model, data, np.array([*xy, 40.0]), np.array([0, 0, -1.0]), TERRAIN, True, -1,
                         np.array([-1], dtype=np.int32))
    if dist < 0:
        raise RuntimeError(f"No floor under {xy}")
    return 40.0-dist


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("robot_xml", type=Path)
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--scene-dir", type=Path, default=SCENE_DIR)
    args = ap.parse_args()
    model, data = load_go2(args.robot_xml, args.scene_dir)
    route = np.asarray(json.loads((args.scene_dir/"manifest.json").read_text(encoding="utf-8"))["route_xyz_m"])[:, :2]
    free = np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)[0]
    base, body = model.jnt_qposadr[free], model.jnt_bodyid[free]
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    joints = model.actuator_trnid[:, 0]
    qa, da = model.jnt_qposadr[joints], model.jnt_dofadr[joints]
    feet = {model.geom(f).id: f for f in ("FL", "FR", "RL", "RR")}
    terrain = {g for g in range(model.ngeom) if model.geom(g).name.startswith("pair360_ground_")}
    seg = np.linalg.norm(np.diff(route, axis=0), axis=1)
    stations = np.r_[np.arange(0, seg.sum(), args.step), seg.sum()]
    results = []
    for s in stations:
        i = min(np.searchsorted(np.cumsum(seg), s, side="right"), len(seg)-1)
        t = (s-np.r_[0, np.cumsum(seg)][i])/seg[i]
        heading = (route[i+1]-route[i])/seg[i]
        xy = route[i]+t*(route[i+1]-route[i])
        # Rays need computed geom poses, which a keyframe reset clears.
        mujoco.mj_forward(model, data)
        ahead, behind = floor(model, data, xy+.3*heading), floor(model, data, xy-.3*heading)
        ground = floor(model, data, xy)
        mujoco.mj_resetDataKeyframe(model, data, key)
        stand_height = float(data.qpos[base+2])
        data.qpos[base:base+3] = [*xy, ground+stand_height]
        yaw = np.arctan2(heading[1], heading[0])/2
        original = data.qpos[base+3:base+7].copy()
        mujoco.mju_mulQuat(data.qpos[base+3:base+7], np.array([np.cos(yaw), 0, 0, np.sin(yaw)]), original)
        target = data.qpos[qa].copy()
        start = data.qpos[base:base+3].copy()
        steps = int(round(args.seconds/model.opt.timestep))
        tail = set()
        for k in range(steps):
            data.ctrl[:] = np.clip(70*(target-data.qpos[qa])-3*data.qvel[da],
                                   model.actuator_ctrlrange[:, 0], model.actuator_ctrlrange[:, 1])
            mujoco.mj_step(model, data)
            if k > steps*.8:
                for c in data.contact:
                    pair = set(c.geom)
                    if pair & terrain:
                        tail.update(feet[g] for g in pair & feet.keys())
        up = float(data.xmat[body, 8])
        results.append({"station_m": round(float(s), 2), "xy": np.round(xy, 2).tolist(),
                        "floor_z_m": round(ground, 3), "slope_along_route_pct": round((ahead-behind)/.6*100, 1),
                        "feet_in_contact": sorted(tail), "body_tilt_deg": round(float(np.degrees(np.arccos(min(1, up)))), 2),
                        "drift_m": round(float(np.linalg.norm(data.qpos[base:base+2]-start[:2])), 3),
                        "body_above_floor_m": round(float(data.qpos[base+2]-ground), 3),
                        "pass": bool(np.isfinite(data.qpos).all() and up >= .9 and len(tail) == 4
                                     and np.linalg.norm(data.qpos[base:base+2]-start[:2]) <= .15)})
    summary = {"mujoco_version": mujoco.__version__, "stations": len(results),
               "passed": sum(r["pass"] for r in results), "max_slope_pct": max(abs(r["slope_along_route_pct"]) for r in results),
               "max_tilt_deg": max(r["body_tilt_deg"] for r in results), "max_drift_m": max(r["drift_m"] for r in results),
               "note": "Static stance with joint PD at the home keyframe; not a walking test.", "results": results}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
