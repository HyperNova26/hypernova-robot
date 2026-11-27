"""Load a locomotion team's existing Go2 model with the released PAIR360 terrain."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

SCENE_DIR = Path(__file__).resolve().parent / "scene"
SHAPES = {"box": mujoco.mjtGeom.mjGEOM_BOX, "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER,
          "ellipsoid": mujoco.mjtGeom.mjGEOM_ELLIPSOID}


def floats(text):
    return np.fromstring(text, dtype=float, sep=" ")


def load_go2(robot_xml, scene_dir=SCENE_DIR, keyframe="home", height=None):
    """Return (model, data) with team actuators intact and a map-frame spawn pose."""
    scene_dir = Path(scene_dir).resolve()
    spec = mujoco.MjSpec.from_file(str(Path(robot_xml).resolve()))
    if any(g.type == mujoco.mjtGeom.mjGEOM_PLANE for g in spec.worldbody.geoms):
        raise ValueError("Use the robot-only model. Its worldbody already has a plane.")
    terrain = ET.parse(scene_dir/"scene.xml")
    for field in terrain.findall("./asset/hfield"):
        spec.add_hfield(name=field.attrib["name"], file=str(scene_dir/field.attrib["file"]),
                        size=floats(field.attrib["size"]))
    for geom in terrain.findall("./worldbody/geom"):
        attrs = geom.attrib
        kwargs = dict(name=attrs["name"], pos=floats(attrs["pos"]), group=int(attrs["group"]),
                      rgba=floats(attrs["rgba"]), contype=int(attrs.get("contype", 1)),
                      conaffinity=int(attrs.get("conaffinity", 1)))
        if attrs["type"] == "hfield":
            kwargs.update(type=mujoco.mjtGeom.mjGEOM_HFIELD, hfieldname=attrs["hfield"],
                          friction=floats(attrs["friction"]))
        else:
            size = np.zeros(3)
            size[:len(floats(attrs["size"]))] = floats(attrs["size"])
            kwargs.update(type=SHAPES[attrs["type"]], size=size)
        if "euler" in attrs:
            # scene.xml uses MuJoCo defaults: degrees, intrinsic xyz.
            quat = np.zeros(4)
            mujoco.mju_euler2Quat(quat, np.deg2rad(floats(attrs["euler"])), "xyz")
            kwargs["quat"] = quat
        spec.worldbody.add_geom(**kwargs)
    model = spec.compile()
    free = np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
    if len(free) != 1:
        raise ValueError("Expected exactly one free joint, belonging to the Go2 base")
    data = mujoco.MjData(model)
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, keyframe) if keyframe else -1
    if keyframe and key < 0:
        raise ValueError(f"Missing initial pose '{keyframe}'. Supply the team's keyframe or None.")
    if key >= 0:
        mujoco.mj_resetDataKeyframe(model, data, key)
    manifest = json.loads((scene_dir/"manifest.json").read_text(encoding="utf-8"))
    start = manifest["route_xyz_m"][0]
    base = model.jnt_qposadr[free[0]]
    data.qpos[base:base+2] = start[:2]
    local_height = float(data.qpos[base+2]) if height is None else float(height)
    data.qpos[base+2] = start[2]+local_height
    angle = np.deg2rad(manifest["spawn_yaw_deg"])/2
    yaw = np.array([np.cos(angle), 0, 0, np.sin(angle)])
    original = data.qpos[base+3:base+7].copy()
    mujoco.mju_mulQuat(data.qpos[base+3:base+7], yaw, original)
    mujoco.mj_forward(model, data)
    return model, data


def check_menagerie_stand(robot_xml, seconds=3, scene_dir=SCENE_DIR):
    """Run a stand check for the official Menagerie Go2 torque motor configuration."""
    model, data = load_go2(robot_xml, scene_dir)
    foot_ids = {model.geom(foot).id for foot in ("FL", "FR", "RL", "RR")}
    terrain_ids = {g for g in range(model.ngeom) if model.geom(g).name.startswith("pair360_ground_")}
    if model.nu != 12 or np.any(model.actuator_trntype != mujoco.mjtTrn.mjTRN_JOINT):
        raise ValueError("This stand check expects the 12 joint motors of Menagerie Go2")
    joints = model.actuator_trnid[:, 0]
    qa, da = model.jnt_qposadr[joints], model.jnt_dofadr[joints]
    target = data.qpos[qa].copy()
    free = np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)[0]
    base = model.jnt_qposadr[free]
    start = data.qpos[base:base+3].copy()
    tail_feet = set()
    steps = int(round(seconds/model.opt.timestep))
    for i in range(steps):
        data.ctrl[:] = np.clip(70*(target-data.qpos[qa])-3*data.qvel[da],
                               model.actuator_ctrlrange[:, 0], model.actuator_ctrlrange[:, 1])
        mujoco.mj_step(model, data)
        if i > steps*0.8:
            for contact in data.contact:
                pair = set(contact.geom)
                if pair & terrain_ids:
                    tail_feet.update(pair & foot_ids)
    finish = data.qpos[base:base+3]
    up = float(data.xmat[model.jnt_bodyid[free], 8])
    drift = float(np.linalg.norm(finish[:2]-start[:2]))
    result = {"sim_seconds": float(data.time), "timestep": model.opt.timestep,
              "actuators": model.nu, "start_xyz": start.tolist(), "end_xyz": finish.tolist(),
              "base_upright_cosine": up, "horizontal_drift_m": drift,
              "contact_feet_in_last_fifth": sorted(model.geom(i).name for i in tail_feet)}
    if not np.isfinite(data.qpos).all() or up < .9 or drift > .15 or len(tail_feet) != 4:
        raise RuntimeError(f"Go2 stand check failed: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("robot_xml", type=Path)
    parser.add_argument("--scene-dir", type=Path, default=SCENE_DIR)
    parser.add_argument("--keyframe", default="home")
    parser.add_argument("--height", type=float)
    parser.add_argument("--stand-check", action="store_true", help="Official Menagerie Go2 only")
    args = parser.parse_args()
    if args.stand_check:
        print(json.dumps(check_menagerie_stand(args.robot_xml, scene_dir=args.scene_dir), indent=2))
    else:
        model, data = load_go2(args.robot_xml, args.scene_dir, args.keyframe or None, args.height)
        print(f"Loaded {model.ngeom} geoms and {model.nu} actuators. Go2 at {data.qpos[:3]}")
