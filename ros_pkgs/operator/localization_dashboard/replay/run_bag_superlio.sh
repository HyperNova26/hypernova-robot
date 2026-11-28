#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
# Replay a hypernova-capture-v1 rosbag2 through Super-LIO and the dashboard adapter
# (inside hn:ros-2026.10.1-local-superlio, built from Dockerfile.superlio).
# Usage: run_bag_superlio.sh BAG_DIR [RATE]
#   env START_X/Y/Z/ROLL/PITCH/YAW  pair360_map <- world (radians). For the 11-15 recording use
#                        ../registration/1115_superlio.env (from superlio_registration.py). Default: identity.
#   env BRIDGE_ADDRESS   foxglove_bridge bind address (127.0.0.1; use 0.0.0.0 inside Docker with -p 127.0.0.1:8765:8765)
#   env OUT_BAG          if set, record /lio/odom and the dashboard-facing outputs there
#   env SUPER_LIO_CONFIG alternative params file (default: super_lio_mlx.yaml next to this script)
set -euo pipefail
BAG=${1:?usage: run_bag_superlio.sh BAG_DIR [RATE]}
RATE=${2:-1.0}
HERE=$(cd "$(dirname "$0")" && pwd)
ADAPTERS=${ADAPTERS:-/hyper/dashboard/app/adapters}
MAP_PCD=${MAP_PCD:-/hyper/dashboard/app/public/map-223c6135c606.pcd}
START_X=${START_X:-0} START_Y=${START_Y:-0} START_Z=${START_Z:-0} START_YAW=${START_YAW:-0}
START_ROLL=${START_ROLL:-0} START_PITCH=${START_PITCH:-0}
LOG=${LOG:-/tmp/hn-bag}
mkdir -p "$LOG"
set +u
source /opt/ros/jazzy/setup.bash
source /opt/hn_ws/install/setup.bash
source /opt/superlio_ws/install/setup.bash
set -u
PY=/opt/hn-venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
SIM=(--ros-args -p use_sim_time:=true)
pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true' EXIT

# world: Super-LIO frame, gravity-aligned (z up) at the start pose.
ros2 run tf2_ros static_transform_publisher --x "$START_X" --y "$START_Y" --z "$START_Z" --yaw "$START_YAW" \
  --pitch "$START_PITCH" --roll "$START_ROLL" --frame-id pair360_map --child-frame-id world "${SIM[@]}" \
  > "$LOG/tf_map.log" 2>&1 & pids+=($!)
# imu (Super-LIO body) <- mlx_lidar: same rotation as lio.extrinsic.lidar_imu; translation not calibrated.
ros2 run tf2_ros static_transform_publisher --roll 3.14159265 \
  --frame-id imu --child-frame-id mlx_lidar "${SIM[@]}" > "$LOG/tf_body.log" 2>&1 & pids+=($!)
# Registered full scan stays in world; the dashboard resolves world via /tf_static.
ros2 run super_lio super_lio_node --ros-args --params-file "${SUPER_LIO_CONFIG:-$HERE/super_lio_mlx.yaml}" \
  -p use_sim_time:=true -r /lio/cloud_world:=/lidar/points > "$LOG/super_lio.log" 2>&1 & pids+=($!)
# Super-LIO leaves child_frame_id empty; its pose is the imu frame (TF world -> imu).
$PY -u "$ADAPTERS/lio_adapter.py" --input /lio/odom --output /localization/odometry --frame pair360_map \
  --base mlx_lidar --child-default imu "${SIM[@]}" > "$LOG/adapter.log" 2>&1 & pids+=($!)
# Provisional /localization/status (pipeline health, not map-matching accuracy).
$PY -u "$ADAPTERS/localization_status.py" --odom /localization/odometry --scan /lidar/points \
  > "$LOG/status.log" 2>&1 & pids+=($!)
$PY -u "$ADAPTERS/reference_map_ros.py" "$MAP_PCD" --frame pair360_map > "$LOG/map.log" 2>&1 & pids+=($!)
ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:="${BRIDGE_ADDRESS:-127.0.0.1}" port:=8765 \
  > "$LOG/bridge.log" 2>&1 & pids+=($!)
if [ -n "${OUT_BAG:-}" ]; then
  ros2 bag record --use-sim-time -o "$OUT_BAG" /lio/odom /localization/odometry \
    > "$LOG/record.log" 2>&1 & pids+=($!)
fi
sleep 4
ros2 bag play "$BAG" --clock --rate "$RATE" --read-ahead-queue-size 2000   # 11-15 starved at the default 1000
sleep 2
echo "logs: $LOG"
