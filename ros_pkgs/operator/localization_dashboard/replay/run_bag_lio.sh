#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
# Replay a hypernova-capture-v1 rosbag2 through FAST-LIO2 and the dashboard adapter (inside hn:ros).
# Usage: run_bag_lio.sh BAG_DIR [RATE]
#   env START_X/Y/Z/ROLL/PITCH/YAW  pair360_map <- camera_init (radians). Default is an old assumption
#                        (-16,170, yaw 90 deg, roll pi). For the 11-15 recording use ../registration/1115.env.
#   env BRIDGE_ADDRESS   foxglove_bridge bind address (127.0.0.1; use 0.0.0.0 inside Docker with -p 127.0.0.1:8765:8765)
#   env OUT_BAG          if set, record the dashboard-facing outputs there
#   env FAST_LIO_CONFIG  alternative FAST-LIO params file (default: fast_lio_mlx.yaml next to this script)
set -euo pipefail
BAG=${1:?usage: run_bag_lio.sh BAG_DIR [RATE]}
RATE=${2:-1.0}
HERE=$(cd "$(dirname "$0")" && pwd)
ADAPTERS=${ADAPTERS:-/hyper/dashboard/app/adapters}
MAP_PCD=${MAP_PCD:-/hyper/dashboard/app/public/map-223c6135c606.pcd}
START_X=${START_X:--16} START_Y=${START_Y:-170} START_Z=${START_Z:-0} START_YAW=${START_YAW:-1.5708}
START_ROLL=${START_ROLL:-3.14159265} START_PITCH=${START_PITCH:-0}
LOG=${LOG:-/tmp/hn-bag}
mkdir -p "$LOG"
set +u
source /opt/ros/jazzy/setup.bash
source /opt/hn_ws/install/setup.bash
set -u
PY=/opt/hn-venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
SIM=(--ros-args -p use_sim_time:=true)
pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true' EXIT

# camera_init is the IMU frame at bag start (z points down). Pass a registration result through START_*.
ros2 run tf2_ros static_transform_publisher --x "$START_X" --y "$START_Y" --z "$START_Z" --yaw "$START_YAW" \
  --pitch "$START_PITCH" --roll "$START_ROLL" --frame-id pair360_map --child-frame-id camera_init "${SIM[@]}" \
  > "$LOG/tf_map.log" 2>&1 & pids+=($!)
# body (FAST-LIO IMU frame) <- mlx_lidar: same rotation as extrinsic_R in fast_lio_mlx.yaml; translation not calibrated.
ros2 run tf2_ros static_transform_publisher --roll 3.14159265 \
  --frame-id body --child-frame-id mlx_lidar "${SIM[@]}" > "$LOG/tf_body.log" 2>&1 & pids+=($!)
# Registered scan stays in camera_init; the dashboard resolves camera_init via /tf_static.
# (lio_adapter --scan-input fails on FAST-LIO's padded PointXYZINormal cloud in tf2_sensor_msgs.)
ros2 run fast_lio fastlio_mapping --ros-args --params-file "${FAST_LIO_CONFIG:-$HERE/fast_lio_mlx.yaml}" -p use_sim_time:=true \
  -r /cloud_registered:=/lidar/points > "$LOG/fast_lio.log" 2>&1 & pids+=($!)
$PY -u "$ADAPTERS/lio_adapter.py" --input /Odometry --output /localization/odometry --frame pair360_map \
  --base mlx_lidar "${SIM[@]}" > "$LOG/adapter.log" 2>&1 & pids+=($!)
$PY -u "$ADAPTERS/reference_map_ros.py" "$MAP_PCD" --frame pair360_map > "$LOG/map.log" 2>&1 & pids+=($!)
ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:="${BRIDGE_ADDRESS:-127.0.0.1}" port:=8765 \
  > "$LOG/bridge.log" 2>&1 & pids+=($!)
if [ -n "${OUT_BAG:-}" ]; then
  ros2 bag record --use-sim-time -o "$OUT_BAG" /Odometry /localization/odometry /lidar/points \
    > "$LOG/record.log" 2>&1 & pids+=($!)
fi
sleep 4
ros2 bag play "$BAG" --clock --rate "$RATE" --read-ahead-queue-size 2000   # 11-15 starved at the default 1000
sleep 2
echo "logs: $LOG"
