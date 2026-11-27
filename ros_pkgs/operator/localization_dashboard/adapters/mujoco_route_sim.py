# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Kinematic MuJoCo stand-in for the dashboard's synthetic preview. Not a locomotion simulation.

A mocap body carrying the LiDAR is moved along the terrain package's walking-test route
(scene/manifest.json route_xyz_m) on the released PAIR360 heightfields. Each step publishes,
through adapters/mujoco_ros.MujocoTelemetry:
  /localization/odometry  nav_msgs/Odometry, pair360_map -> mlx_lidar (simulator pose, NOT a LIO estimate)
  /lidar/points           forward 120 deg, 16 x 121 rays at 10 Hz (configurable) against the terrain and context boxes, frame mlx_lidar
  /ground_truth/odom      the same simulator pose as GT (--gt-topic, '' disables)
  /clock                  simulation time
No controller, joints, contacts or IMU are simulated. LocalizationStatus is not published
(hn_interfaces is not in this environment). Requires mujoco, numpy, rclpy, sensor_msgs_py.

--locomotion-topic /locomotion/status (2026-11-27) adds the G-006 robot state: the team's own
StateEstimator (ros_pkgs/hn_robot_state, default thresholds) judges the carrier's motion and the
team's StatusPublisher sends it as diagnostic_msgs/DiagnosticArray. The inputs are this kinematic
carrier (level body, speed along the route, command = that speed), not a walking policy, so the
states are INITIALIZING -> STANDING (--stand-s) -> WALKING, and FALLEN only if --fall-at tips it over.
Set HN_ROBOT_STATE to the folder that contains the hn_robot_state package.

Example: /opt/hn-venv/bin/python adapters/mujoco_route_sim.py <map release>/terrain/scene
"""
import argparse
import json
import math
import time
from pathlib import Path

import mujoco
import numpy as np
import rclpy

from mujoco_ros import MujocoTelemetry


def route_pose(route, distance):
    """Position and yaw at a travelled distance along a forward-and-back polyline."""
    lengths = [math.dist(a[:2], b[:2]) for a, b in zip(route, route[1:])]
    total = sum(lengths)
    d = distance % (2 * total)
    back = d > total
    d = 2 * total - d if back else d
    for (a, b), length in zip(zip(route, route[1:]), lengths):
        if d <= length or b is route[-1]:
            f = min(1.0, d / length)
            p = [a[i] + (b[i] - a[i]) * f for i in range(3)]
            return p, math.atan2(b[1] - a[1], b[0] - a[0]) + (math.pi if back else 0)
        d -= length


def build(scene_dir):
    spec = mujoco.MjSpec.from_file(str(Path(scene_dir) / "scene.xml"))
    carrier = spec.worldbody.add_body(name="mlx_lidar", mocap=True)
    # Visual-only housing; contype/conaffinity 0 so it never collides, and rays exclude this body.
    carrier.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.05, 0.03, 0.03],
                     contype=0, conaffinity=0, rgba=[0.9, 0.7, 0.2, 1])
    carrier.add_site(name="mlx_lidar_site")
    model = spec.compile()
    return model, mujoco.MjData(model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene_dir", type=Path)
    parser.add_argument("--speed", type=float, default=0.6, help="m/s along the route")
    parser.add_argument("--sensor-height", type=float, default=0.35,
                        help="LiDAR height above route ground, m (display assumption, not a calibrated extrinsic)")
    parser.add_argument("--odom-topic", default="/localization/odometry")
    parser.add_argument("--rate", type=float, default=1.0, help="simulation speed relative to wall clock")
    # Ray casts against ~300 heightfields cost ~27 us each, so the default follows the team URDF's
    # front LiDAR (description/hn_v0_go2/config/front_lidar.json: 120 deg horizontal, 121 columns, 10 Hz)
    # instead of mujoco_ros's 16 x 360. 10 Hz keeps scans inside the dashboard's +-120 ms pairing window.
    parser.add_argument("--lidar-hz", type=float, default=10)
    parser.add_argument("--lidar-columns", type=int, default=121)
    parser.add_argument("--lidar-hfov-deg", type=float, default=120)
    # SIM ground truth: same mlx_lidar pose on a second topic. The name follows the team demo bag
    # (tools/check_demo_lio.py reads /ground_truth/odom); it is not an S-005 agreed topic.
    parser.add_argument("--gt-topic", default="/ground_truth/odom", help="empty string disables GT")
    parser.add_argument("--locomotion-topic", default="", help="G-006 status topic; empty disables it")
    parser.add_argument("--stand-s", type=float, default=5.0, help="stand still this long before walking")
    parser.add_argument("--fall-at", type=float, default=None, help="tip the body over at this time (FALLEN)")
    parser.add_argument("--robot-id", default="hn_v1_hyper")
    parser.add_argument("--path-topic", default="",
                        help="publish the route as nav_msgs/Path at 1 Hz (stand-in for the Nav2 /plan); empty disables")
    args, ros_args = parser.parse_known_args()

    manifest = json.loads((args.scene_dir / "manifest.json").read_text(encoding="utf-8"))
    route = manifest["route_xyz_m"]
    model, data = build(args.scene_dir)
    rclpy.init(args=ros_args)
    telemetry = MujocoTelemetry(
        model, body="mlx_lidar", gt_topic=args.odom_topic,
        world_frame=manifest.get("frame", "pair360_map"), base_frame="mlx_lidar",
        clock_owner=True, lidar_site="mlx_lidar_site", lidar_topic="/lidar/points",
        lidar_frame="mlx_lidar", lidar_hz=args.lidar_hz, lidar_columns=args.lidar_columns,
        lidar_hfov_deg=args.lidar_hfov_deg)
    if args.gt_topic:
        # Mirror every simulator pose message onto the GT topic (same stamp, frames and values).
        from nav_msgs.msg import Odometry
        mirror = telemetry.create_publisher(Odometry, args.gt_topic, 10)
        primary = telemetry.gt.publish
        telemetry.gt.publish = lambda msg: (primary(msg), mirror.publish(msg))
    telemetry.get_logger().info(
        f"route {len(route)} points, map {manifest.get('reference_map_sha256', '?')[:12]}, "
        f"frame {manifest.get('frame')}, odometry on {args.odom_topic} (simulator pose)")
    judge = status = None
    if args.locomotion_topic:
        import os
        import sys
        # Default: ros_pkgs/hn_robot_state next to ros_pkgs/operator/localization_dashboard in the repo.
        state = os.environ.get("HN_ROBOT_STATE") or str(Path(__file__).resolve().parents[3] / "hn_robot_state")
        sys.path.insert(0, state)
        from hn_robot_state.core import StateEstimator
        from hn_robot_state.ros_node import StatusPublisher
        judge = StateEstimator()
        status = StatusPublisher(topic=args.locomotion_topic, robot_id=args.robot_id,
                                 stale_provider=None)
        telemetry.get_logger().info(f"G-006 status on {args.locomotion_topic} (team StateEstimator, kinematic inputs)")
    plan_pub = plan_msg = None
    if args.path_topic:
        # The route polyline, 0.5 m apart, as a Nav2-style global path (not a planner output).
        from geometry_msgs.msg import PoseStamped
        from nav_msgs.msg import Path as PathMsg
        plan_pub = telemetry.create_publisher(PathMsg, args.path_topic, 1)
        plan_msg = PathMsg()
        plan_msg.header.frame_id = manifest.get("frame", "pair360_map")
        for a, b in zip(route, route[1:]):
            n = max(1, int(math.dist(a[:2], b[:2]) / 0.5))
            for k in range(n):
                ps = PoseStamped()
                ps.header.frame_id = plan_msg.header.frame_id
                ps.pose.position.x, ps.pose.position.y, ps.pose.position.z = (a[i] + (b[i] - a[i]) * k / n for i in range(3))
                ps.pose.orientation.w = 1.0
                plan_msg.poses.append(ps)
        telemetry.get_logger().info(f"route as nav_msgs/Path on {args.path_topic}: {len(plan_msg.poses)} poses")
    dt, start = 0.02, time.monotonic()
    fallen_at = None
    next_plan = 0.0
    try:
        while rclpy.ok():
            if args.fall_at is not None and data.time >= args.fall_at and fallen_at is None:
                fallen_at = data.time
            moving = data.time >= args.stand_s and fallen_at is None
            travelled = max(0.0, (fallen_at or data.time) - args.stand_s) * args.speed
            p, yaw = route_pose(route, travelled)
            if judge is not None:
                v = args.speed if moving else 0.0
                # Lying on its side once tipped over: gravity along body -y (roll 90 deg).
                gravity = [0.0, -1.0, 0.0] if fallen_at is not None else [0.0, 0.0, -1.0]
                status.publish(judge.update({"projected_gravity_b": gravity, "base_lin_vel_b": [v, 0.0, 0.0],
                                             "command": [v, 0.0, 0.0]}, data.time))
            data.mocap_pos[0] = [p[0], p[1], p[2] + args.sensor_height]
            data.mocap_quat[0] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
            mujoco.mj_forward(model, data)
            telemetry.publish(data)
            if plan_pub is not None and data.time >= next_plan:
                next_plan = data.time + 1.0
                sec = int(data.time)
                plan_msg.header.stamp.sec, plan_msg.header.stamp.nanosec = sec, int((data.time - sec) * 1e9)
                plan_pub.publish(plan_msg)
            rclpy.spin_once(telemetry, timeout_sec=0)
            data.time += dt
            lag = start + data.time / args.rate - time.monotonic()
            if lag > 0:
                time.sleep(lag)
    except KeyboardInterrupt:
        pass
    finally:
        if status is not None:
            status.close()
        telemetry.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
