#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Load a Nav2 map + keep-out mask into a real Nav2 global costmap (Jazzy) inside the team ROS image and
# report how much of the keep-out and outside-map area ends up lethal. Implementation: check_nav2_keepout.py.
# Usage (repository root, Docker): tools/map/check_nav2_keepout.sh [maps_dir=sim_scenes/pair360_nav2] [image=hn:ros-2026.10.1]
# The container installs nav2_map_server, nav2_costmap_2d and nav2_lifecycle_manager with apt (network needed);
# the image itself is not changed. Takes about 5 minutes; the 1611x1616 costmap needs a few minutes to publish.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
maps=$(cd "${1:-$repo/sim_scenes/pair360_nav2}" && pwd)
image=${2:-hn:ros-2026.10.1}
MSYS_NO_PATHCONV=1 docker run --rm -v "$maps:/maps:ro" -v "$repo:/repo:ro" "$image" bash -c '
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq ros-jazzy-nav2-map-server ros-jazzy-nav2-costmap-2d ros-jazzy-nav2-lifecycle-manager >/dev/null
source /opt/ros/jazzy/setup.bash
P=/maps/nav2_params.example.yaml
log=/tmp/nav2; mkdir -p $log
ros2 run tf2_ros static_transform_publisher --frame-id pair360_map --child-frame-id base_link --x -16.7 --y 123.4 >/dev/null 2>&1 &
# 1) keep-out mask and filter info first
ros2 run nav2_map_server map_server --ros-args -r __node:=filter_mask_server --params-file $P >$log/mask.log 2>&1 &
ros2 run nav2_map_server costmap_filter_info_server --ros-args --params-file $P >$log/info.log 2>&1 &
ros2 run nav2_lifecycle_manager lifecycle_manager --ros-args -r __node:=lifecycle_manager_filters --params-file $P >$log/lm1.log 2>&1 &
sleep 6
# 2) costmap
ros2 run nav2_costmap_2d nav2_costmap_2d --ros-args -r __ns:=/global_costmap -r __node:=global_costmap \
  -p always_send_full_costmap:=true --params-file $P >$log/costmap.log 2>&1 &
for i in $(seq 1 20); do ros2 lifecycle set /global_costmap/global_costmap configure >/dev/null 2>&1 && break; sleep 2; done
ros2 lifecycle set /global_costmap/global_costmap activate >/dev/null
sleep 8
# 3) static map last
ros2 run nav2_map_server map_server --ros-args --params-file $P >$log/map.log 2>&1 &
ros2 run nav2_lifecycle_manager lifecycle_manager --ros-args -r __node:=lifecycle_manager_map --params-file $P >$log/lm2.log 2>&1 &
python3 /repo/tools/map/check_nav2_keepout.py
'
