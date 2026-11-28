# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""pair360_map <- world for Super-LIO on the 11-15 recording, from the FAST-LIO registration (2026-11-26).

FAST-LIO camera_init is the IMU frame at its start; Super-LIO world is gravity-aligned at its start with the
IMU at the origin, so world <- imu0 is the first /lio/odom pose and
    pair360_map <- world = (pair360_map <- camera_init) * (world <- imu0)^-1.
This assumes the hand-held rig was still while both filters initialised. The check compares the
transformed Super-LIO path with the FAST-LIO map path in trajectory_1115_base.csv (--reference; local isaac-runpod output, not in this repo)
(x, y = registered LiDAR position, lio_z = its height) by time since the first odometry message.

usage: python superlio_registration.py RESULT_BAG --reference trajectory_1115_base.csv [--out-env 1115_superlio.env] [--out-json 1115_superlio.json]
RESULT_BAG: OUT_BAG of ../ros/run_bag_superlio.sh with identity START_* (needs /lio/odom).
Run with the ROS Python (rosbag2_py), e.g. inside the hn:ros image: /usr/bin/python3 superlio_registration.py ...
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def quat_matrix(x, y, z, w):
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rpy(R):  # R = Rz(yaw) Ry(pitch) Rx(roll), as static_transform_publisher
    return math.atan2(R[2, 1], R[2, 2]), -math.asin(max(-1, min(1, R[2, 0]))), math.atan2(R[1, 0], R[0, 0])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("bag", type=Path)
    p.add_argument("--out-env", type=Path, default=HERE / "1115_superlio.env")
    p.add_argument("--out-json", type=Path, default=HERE / "1115_superlio.json")
    p.add_argument("--reference", type=Path, required=True, help="FAST-LIO map path CSV (trajectory_1115_base.csv)")
    a = p.parse_args()
    import rosbag2_py
    from nav_msgs.msg import Odometry
    from rclpy.serialization import deserialize_message
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(a.bag), storage_id=""),
                rosbag2_py.ConverterOptions("cdr", "cdr"))
    reader.set_filter(rosbag2_py.StorageFilter(topics=["/lio/odom"]))
    t, poses = [], []
    while reader.has_next():
        _, raw, _ = reader.read_next()
        m = deserialize_message(raw, Odometry)
        s = m.header.stamp
        pos, q = m.pose.pose.position, m.pose.pose.orientation
        T = np.eye(4)
        T[:3, :3] = quat_matrix(q.x, q.y, q.z, q.w)
        T[:3, 3] = (pos.x, pos.y, pos.z)
        t.append(s.sec + s.nanosec * 1e-9)
        poses.append(T)
    if not poses:
        raise SystemExit("no /lio/odom in " + str(a.bag))
    order = np.argsort(t)
    t = np.array(t)[order] - min(t)
    poses = [poses[i] for i in order]
    map_cam = np.array(json.loads((HERE / "1115.json").read_text())["matrix"])
    map_world = map_cam @ np.linalg.inv(poses[0])
    roll, pitch, yaw = rpy(map_world[:3, :3])
    x, y, z = map_world[:3, 3]

    # Check against the FAST-LIO path (both clocks start at their first odometry message).
    ref = np.loadtxt(a.reference, delimiter=",", skiprows=1)
    mine = np.array([(map_world @ P)[:3, 3] for P in poses])
    idx = np.clip(np.searchsorted(t, ref[:, 0]), 0, len(t) - 1)
    close = np.abs(t[idx] - ref[:, 0]) < 0.06
    dxy = np.hypot(mine[idx, 0] - ref[:, 1], mine[idx, 1] - ref[:, 2])[close]
    dz = (mine[idx, 2] - ref[:, 5])[close]
    check = {
        "matched_samples": int(close.sum()),
        "horizontal_m": {"median": float(np.median(dxy)), "p95": float(np.percentile(dxy, 95)), "max": float(dxy.max())},
        "vertical_m": {"median": float(np.median(dz)), "p95_abs": float(np.percentile(np.abs(dz), 95))},
        "end_point_superlio_xy": mine[-1, :2].round(3).tolist(),
        "start_point_superlio_xy": mine[0, :2].round(3).tolist(),
    }
    a.out_env.write_text(
        "# pair360_map <- world for the 11-15 recording with Super-LIO (see 1115_superlio.json). Radians.\n"
        f"START_X={x:.4f}\nSTART_Y={y:.4f}\nSTART_Z={z:.4f}\n"
        f"START_ROLL={roll:.6f}\nSTART_PITCH={pitch:.6f}\nSTART_YAW={yaw:.6f}\n", encoding="utf-8")
    a.out_json.write_text(json.dumps({
        "transform": "pair360_map <- world (Super-LIO run with sensor-capture/ros/super_lio_mlx.yaml, 11-15 recording)",
        "matrix": map_world.round(6).tolist(),
        "rpy_deg": [round(math.degrees(v), 3) for v in (roll, pitch, yaw)],
        "via": "1115.json (pair360_map <- FAST-LIO camera_init) composed with the inverse of the first /lio/odom pose",
        "source_bag": str(a.bag),
        "check_vs_fastlio_path": check,
    }, indent=2), encoding="utf-8")
    print(json.dumps(check, indent=2))
    print("wrote", a.out_env, a.out_json)


if __name__ == "__main__":
    main()
