#!/usr/bin/env bash
# LIO 패키지. ros target에만 들어갑니다(docker/Dockerfile).
#
#   - RKO-LIO:   ROS apt snapshot의 ros-<배포판>-rko-lio
#   - FAST-LIO2: hku-mars/FAST_LIO(ROS2 브랜치)를 소스에서 빌드해 /opt/hn_ws(underlay)에 설치
#   - livox_ros_driver2: FAST-LIO가 컴파일에 필요로 하는 메시지(CustomMsg, CustomPoint)만 같은 underlay에 설치
#
# 소스 의존성은 docker/ros/hypernova.repos에 commit SHA로 고정돼 있습니다.
#
# livox_ros_driver2를 메시지만 만드는 이유 (가장 덜 깨지는 방법)
#   FAST-LIO는 find_package(livox_ros_driver2)로 메시지 타입만 씁니다. 드라이버 본체는 Livox-SDK2(별도 C++ SDK)를
#   먼저 빌드·설치해야 하고, 이 저장소에는 package.xml이 없어서(package_ROS1.xml, package_ROS2.xml만 있음) 공식 절차는
#   build.sh가 파일을 바꿔치기한 뒤 배포판별 define을 넘기는 방식입니다. 시뮬레이션은 Livox 하드웨어 없이
#   PointCloud2를 쓰므로 본체가 필요 없습니다. 같은 패키지 이름과 같은 .msg(저장소의 msg/ 그대로)로 인터페이스만 빌드하면
#   FAST-LIO가 그대로 빌드되고, 나중에 실제 드라이버로 바꿔도 메시지 형식이 같아 bag이 호환됩니다.
#   실제 Livox 센서를 붙이는 단계가 되면 이 부분을 Livox-SDK2 + 전체 드라이버 빌드로 바꿉니다.
#
# 필요한 환경변수(docker/.env): ROS_DISTRO       root로 실행합니다.
set -euo pipefail

: "${ROS_DISTRO:?ROS_DISTRO가 비어 있습니다. docker/.env 값을 build arg로 넘겨야 합니다 (./docker/hn build ...)}"

REPOS_FILE="${HN_REPOS_FILE:-/opt/hn/ros/hypernova.repos}"
WS="${HN_WS:-/opt/hn_ws}"
export DEBIAN_FRONTEND=noninteractive

# --- 1. apt: RKO-LIO와 FAST-LIO 빌드 의존성 ---------------------------------------------
# python3-dev, python3-numpy: FAST-LIO가 matplotlibcpp.h(Python.h, numpy 헤더)를 컴파일합니다.
apt-get update
apt-get install -y --no-install-recommends \
  "ros-${ROS_DISTRO}-rko-lio" \
  libpcl-dev libeigen3-dev python3-dev python3-numpy

# --- 2. 소스 의존성 받기 (--recursive: FAST-LIO의 ikd-Tree 서브모듈, 부모 commit이 가리키는 SHA로 고정) ---
rm -rf "$WS"
mkdir -p "$WS/src"
vcs import --recursive "$WS/src" < "$REPOS_FILE"

# --- 3. livox_ros_driver2: 메시지만 남기고 빌드 정의를 최소 버전으로 교체 --------------------
livox="$WS/src/livox_ros_driver2"
find "$livox" -mindepth 1 -maxdepth 1 ! -name msg ! -name 'LICENSE*' -exec rm -rf {} +

cat > "$livox/package.xml" <<'EOF'
<?xml version="1.0"?>
<package format="3">
  <name>livox_ros_driver2</name>
  <version>1.0.0</version>
  <description>livox_ros_driver2 메시지(CustomMsg, CustomPoint)만 빌드한 HyperNova용 최소 패키지. 드라이버 본체는 없음</description>
  <maintainer email="dev@livoxtech.com">feng</maintainer>
  <license>MIT</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <buildtool_depend>rosidl_default_generators</buildtool_depend>
  <depend>std_msgs</depend>
  <exec_depend>rosidl_default_runtime</exec_depend>
  <member_of_group>rosidl_interface_packages</member_of_group>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
EOF

cat > "$livox/CMakeLists.txt" <<'EOF'
cmake_minimum_required(VERSION 3.8)
project(livox_ros_driver2)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/CustomPoint.msg"
  "msg/CustomMsg.msg"
  DEPENDENCIES std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
EOF

# --- 4. FAST-LIO를 C++17로 빌드하도록 패치 -----------------------------------------------
# 이 commit의 CMakeLists.txt는 -std=c++14(와 -std=c++0x)를 직접 넣는데, Jazzy의 rclcpp 헤더는 C++17
# (std::is_same_v 등)이 필요해서 그대로는 컴파일되지 않습니다. 소스는 저장소에 복사하지 않고 빌드 때만 고칩니다.
fastlio_cmake="$WS/src/FAST_LIO/CMakeLists.txt"
sed -i -e 's/-std=c++14/-std=c++17/g' -e 's/-std=c++0x/-std=c++17/g' -e 's/CMAKE_CXX_STANDARD 14/CMAKE_CXX_STANDARD 17/' "$fastlio_cmake"
if grep -nE 'c\+\+14|c\+\+0x|CXX_STANDARD 14' "$fastlio_cmake"; then
  echo "FAST-LIO CMakeLists.txt에 C++14 지정이 남았습니다. hypernova.repos의 commit이 바뀌었다면 위 sed 패치를 다시 확인하세요." >&2
  exit 1
fi

# --- 5. colcon 빌드 → /opt/hn_ws/install ------------------------------------------------
# ROS setup 스크립트는 정의 안 된 변수를 참조하므로 source할 때만 nounset을 끕니다.
set +u
# shellcheck disable=SC1090
. "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u

CMAKE_BUILD_PARALLEL_LEVEL="$(nproc)"
export CMAKE_BUILD_PARALLEL_LEVEL
cd "$WS"
colcon --log-base "$WS/log" build \
  --base-paths src \
  --build-base "$WS/build" --install-base "$WS/install" \
  --cmake-args -DCMAKE_BUILD_TYPE=Release

# 설치가 제대로 됐는지 확인합니다(실패하면 이미지 빌드도 실패).
set +u
# shellcheck disable=SC1091
. "$WS/install/setup.bash"
set -u
for pkg in fast_lio livox_ros_driver2 "rko_lio"; do
  ros2 pkg prefix "$pkg" > /dev/null
  echo "OK: $pkg -> $(ros2 pkg prefix "$pkg")"
done

# 소스와 빌드 중간물은 이미지에 남기지 않습니다. (launch, config는 install/ 아래에 들어가 있습니다)
rm -rf "$WS/src" "$WS/build" "$WS/log"
apt-get clean
rm -rf /var/lib/apt/lists/*
