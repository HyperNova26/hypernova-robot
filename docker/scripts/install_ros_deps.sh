#!/usr/bin/env bash
# 공용 ROS 레이어. ros, sim 두 target이 같은 스크립트를 씁니다(docker/Dockerfile).
#
#   1. ROS apt 저장소를 날짜 고정 snapshot으로 바꿉니다.
#   2. 모든 팀이 쓰는 ROS 패키지를 설치합니다. 팀 전용 패키지는 여기에 섞지 않고 별도 스크립트로 둡니다.
#
# 필요한 환경변수(docker/.env): ROS_DISTRO, ROS_SNAPSHOT_DATE
# root로 실행합니다. 끝나면 apt 목록을 지워서 레이어를 작게 유지합니다.
set -euo pipefail

: "${ROS_DISTRO:?ROS_DISTRO가 비어 있습니다. docker/.env 값을 build arg로 넘겨야 합니다 (./docker/hn build ...)}"
: "${ROS_SNAPSHOT_DATE:?ROS_SNAPSHOT_DATE가 비어 있습니다. docker/.env 값을 build arg로 넘겨야 합니다 (./docker/hn build ...)}"

SNAPSHOT_KEY="${HN_ROS_SNAPSHOT_KEY:-/opt/hn/ros/ros-snapshots.asc}"
export DEBIAN_FRONTEND=noninteractive

# --- 1. apt 저장소: 날짜 고정 snapshot -------------------------------------------------
# ros:* 공식 이미지에 들어 있는 최신(rolling) ROS 저장소는 끕니다. 두면 snapshot보다 새 패키지가 섞입니다.
# snapshot은 별도 키(ROS Snapshot builder, 4B63CF8FDE49746E98FA01DDAD19BAB3CBF125EA, 2027-06-01 만료)로
# 서명돼 있고, 그 공개키를 docker/ros/ros-snapshots.asc로 저장소에 넣어 두었습니다.
rm -f /etc/apt/sources.list.d/ros2.sources /etc/apt/sources.list.d/ros2.list /etc/apt/sources.list.d/ros2-latest.list

install -d -m 0755 /etc/apt/keyrings
install -m 0644 "$SNAPSHOT_KEY" /etc/apt/keyrings/ros-snapshots.asc

# shellcheck source=/dev/null
codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
cat > /etc/apt/sources.list.d/ros-snapshot.sources <<EOF
Types: deb
URIs: http://snapshots.ros.org/${ROS_DISTRO}/${ROS_SNAPSHOT_DATE}/ubuntu
Suites: ${codename}
Components: main
Signed-By: /etc/apt/keyrings/ros-snapshots.asc
EOF

# --- 2. 공용 패키지 ---------------------------------------------------------------------
# ros-base는 ros target에는 이미 들어 있지만(snapshot과 같은 버전이라 아무 일도 안 함),
# sim target(Ubuntu 기반 Isaac Lab 이미지)에는 없으므로 여기서 설치합니다. 시스템 python3도 이때 같이 들어옵니다.
packages=(
  ca-certificates curl git
  "ros-${ROS_DISTRO}-ros-base"
  "ros-${ROS_DISTRO}-rviz2"
  "ros-${ROS_DISTRO}-rqt" "ros-${ROS_DISTRO}-rqt-common-plugins"
  "ros-${ROS_DISTRO}-rosbag2" "ros-${ROS_DISTRO}-rosbag2-storage-mcap"
  "ros-${ROS_DISTRO}-rosbridge-suite"
  "ros-${ROS_DISTRO}-foxglove-bridge"
  "ros-${ROS_DISTRO}-joy" "ros-${ROS_DISTRO}-teleop-twist-joy"
  "ros-${ROS_DISTRO}-pcl-ros"
  "ros-${ROS_DISTRO}-tf2-tools"
  "ros-${ROS_DISTRO}-rmw-fastrtps-cpp"
  ros-dev-tools   # colcon, vcstool, rosdep, bloom, build-essential
  python3-rosdep
)

apt-get update
apt-get install -y --no-install-recommends "${packages[@]}"

# rosdep 설정 파일(/etc/ros/rosdep)만 만들어 둡니다. 데이터베이스(rosdep update)는 쓰는 사람이 직접 받습니다.
[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || rosdep init

# --- 3. 빈 colcon underlay(/opt/hn_ws) -------------------------------------------------------
# ros target은 install_lio.sh가 이 자리에 LIO 패키지를 빌드해 넣습니다(그때 이 빈 workspace는 지워짐).
# sim target에는 넣을 패키지가 없지만 경로와 setup 스크립트는 같게 둡니다. 저장소를 colcon build한 결과(overlay,
# 두 서비스가 같이 쓰는 named volume)가 이 경로를 underlay로 기록하기 때문에, 한쪽에만 있으면 다른 쪽 셸마다
# `not found: "/opt/hn_ws/install/local_setup.bash"` 오류가 납니다.
hn_ws="${HN_WS:-/opt/hn_ws}"
mkdir -p "$hn_ws/src"
set +u
# shellcheck disable=SC1090,SC1091
. "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u
(cd "$hn_ws" && colcon --log-base /tmp/hn_ws_log build --base-paths src --build-base /tmp/hn_ws_build --install-base "$hn_ws/install")
rm -rf /tmp/hn_ws_log /tmp/hn_ws_build

apt-get clean
rm -rf /var/lib/apt/lists/*
