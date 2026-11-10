# check=skip=InvalidDefaultArgInFrom
#
# HyperNova 개발 이미지 — Dockerfile 하나, build target 둘
#
#   ros : ros:jazzy-ros-base + 공용 ROS 레이어 + robot venv + LIO   (amd64, arm64. CI가 GHCR에 올림)
#   sim : Isaac Lab 공식 이미지 + 공용 ROS 레이어 + robot venv       (각자 로컬 빌드. 배포하지 않음)
#
# 두 target은 docker/scripts의 같은 설치 스크립트를 씁니다. 스크립트나 버전을 고치면 두 target을 모두 빌드해 확인하세요.
# 버전은 모두 docker/.env에 있고 이 파일에는 기본값을 두지 않습니다(값이 두 곳에 있으면 어긋납니다).
# 빌드는 ./docker/hn build ros|sim 으로 합니다. build context는 저장소 최상위입니다.
# 근거: docs/decisions/0002-dev-environment.md

ARG ROS_BASE_IMAGE
ARG ISAACLAB_BASE_IMAGE

# =====================================================================================
# ros
# =====================================================================================
FROM ${ROS_BASE_IMAGE} AS ros

LABEL org.opencontainers.image.source="https://github.com/HyperNova26/hypernova-robot" \
      org.opencontainers.image.description="HyperNova ROS 2 개발 이미지 (hn:ros). docker/README.md 참고"

ARG ROS_DISTRO
ARG ROS_SNAPSHOT_DATE
ARG UV_VERSION
ARG UV_SHA256_AMD64
ARG UV_SHA256_ARM64

# 1) 공용 ROS 레이어: snapshot apt 저장소 + 공용 패키지
COPY docker/ros/ros-snapshots.asc /opt/hn/ros/ros-snapshots.asc
COPY --chmod=0755 docker/scripts/install_ros_deps.sh /opt/hn/scripts/install_ros_deps.sh
RUN /opt/hn/scripts/install_ros_deps.sh

# 2) robot venv: 저장소 최상위 pyproject.toml/uv.lock 그대로 (이 두 파일만 COPY해서 코드 수정이 캐시를 깨지 않게 함)
COPY pyproject.toml uv.lock /opt/hn/lock/
COPY --chmod=0755 docker/scripts/install_robot_venv.sh /opt/hn/scripts/install_robot_venv.sh
RUN --mount=type=cache,id=hn-uv,target=/tmp/uv-cache /opt/hn/scripts/install_robot_venv.sh

# 3) LIO: ros-jazzy-rko-lio(apt) + FAST-LIO·livox 메시지(소스 빌드 → /opt/hn_ws)
COPY docker/ros/hypernova.repos /opt/hn/ros/hypernova.repos
COPY --chmod=0755 docker/scripts/install_lio.sh /opt/hn/scripts/install_lio.sh
RUN /opt/hn/scripts/install_lio.sh

# 4) 실행 환경: 진입점, Fast DDS 프로필, 셸 설정. 자주 바뀌는 것이라 맨 뒤에 둡니다.
#    어떤 UID로 실행해도 HOME과 colcon 출력 경로(named volume이 이 디렉터리의 권한을 물려받음)에 쓸 수 있게 1777로 만듭니다.
COPY --chmod=0755 docker/entrypoint.sh /opt/hn/entrypoint.sh
COPY --chmod=0755 docker/scripts/selftest.sh /opt/hn/scripts/selftest.sh
COPY docker/env.sh docker/fastdds.xml /opt/hn/
RUN set -eux; \
    mkdir -p /home/hn /workspace/hypernova/build /workspace/hypernova/install /workspace/hypernova/log /data; \
    chmod 1777 /home/hn /workspace/hypernova/build /workspace/hypernova/install /workspace/hypernova/log; \
    printf '\n# HyperNova: ROS 환경과 프롬프트 (VS Code 등으로 직접 붙은 셸에서도 같게)\n[ -f /opt/hn/env.sh ] && . /opt/hn/env.sh\n' >> /etc/bash.bashrc

# ROS middleware는 이미지에 둡니다. compose 없이 docker run(CI, Jetson)으로 띄워도 같게 동작하도록.
ENV HN_TARGET=ros \
    HN_ROS_DISTRO=${ROS_DISTRO} \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    FASTRTPS_DEFAULT_PROFILES_FILE=/opt/hn/fastdds.xml \
    HN_UV=/opt/hn/bin/uv \
    HOME=/home/hn

WORKDIR /workspace/hypernova
ENTRYPOINT ["/opt/hn/entrypoint.sh"]
CMD ["bash"]

# =====================================================================================
# sim
# =====================================================================================
FROM ${ISAACLAB_BASE_IMAGE} AS sim

ARG ROS_DISTRO
ARG ROS_SNAPSHOT_DATE
ARG UV_VERSION
ARG UV_SHA256_AMD64
ARG UV_SHA256_ARM64

# 설치 단계는 root로 합니다. 마지막에 베이스의 비root 사용자(isaaclab)로 되돌립니다.
# hadolint ignore=DL3066
USER root

# 1) 공용 ROS 레이어 (ros target과 같은 스크립트)
COPY docker/ros/ros-snapshots.asc /opt/hn/ros/ros-snapshots.asc
COPY --chmod=0755 docker/scripts/install_ros_deps.sh /opt/hn/scripts/install_ros_deps.sh
RUN /opt/hn/scripts/install_ros_deps.sh

# 2) robot venv (ros target과 같은 스크립트). Isaac Lab venv(/opt/isaaclab-venv)는 건드리지 않습니다.
COPY pyproject.toml uv.lock /opt/hn/lock/
COPY --chmod=0755 docker/scripts/install_robot_venv.sh /opt/hn/scripts/install_robot_venv.sh
RUN --mount=type=cache,id=hn-uv,target=/tmp/uv-cache /opt/hn/scripts/install_robot_venv.sh

# 3) 실행 환경
COPY --chmod=0755 docker/entrypoint.sh /opt/hn/entrypoint.sh
COPY --chmod=0755 docker/scripts/selftest.sh /opt/hn/scripts/selftest.sh
COPY docker/env.sh docker/fastdds.xml /opt/hn/
#    - hn-rl: physics=isaacsim_physx를 대신 붙이는 학습·재생 wrapper(docker/scripts/rl.sh)
COPY --chmod=0755 docker/scripts/rl.sh /usr/local/bin/hn-rl
#    - HOME: 베이스의 /root는 UID 1000 전용(750)이라 다른 UID로 실행하면 쓸 수 없으므로 /home/hn을 씁니다.
#    - 아래 디렉터리들은 compose.yaml이 named volume으로 mount하는 캐시 자리입니다(경로는 Isaac Lab v3.0.0 docker-compose.yaml과 같음).
#      volume은 처음 만들어질 때 이미지 안 디렉터리의 권한을 물려받으므로 여기서 1777로 만들어 둡니다.
RUN set -eux; \
    mkdir -p /home/hn/.cache/ov /home/hn/.cache/pip /home/hn/.cache/warp /home/hn/.cache/nvidia/GLCache \
             /home/hn/.nv/ComputeCache /home/hn/.nvidia-omniverse/logs /home/hn/.local/share/ov/data /home/hn/Documents \
             /isaac-sim/kit/logs/Kit/Isaac-Sim \
             /workspace/hypernova/build /workspace/hypernova/install /workspace/hypernova/log /data; \
    find /home/hn -type d -exec chmod 1777 {} +; \
    chmod 1777 /isaac-sim/kit/cache /isaac-sim/kit/data /isaac-sim/kit/logs/Kit/Isaac-Sim /workspace/isaaclab/logs \
               /workspace/hypernova/build /workspace/hypernova/install /workspace/hypernova/log; \
    printf '\n# HyperNova: ROS 환경과 프롬프트 (VS Code 등으로 직접 붙은 셸에서도 같게)\n[ -f /opt/hn/env.sh ] && . /opt/hn/env.sh\n' >> /etc/bash.bashrc

# VIRTUAL_ENV, UV_PROJECT_ENVIRONMENT, UV_PYTHON(베이스가 설정한 Isaac Lab venv)은 그대로 둡니다.
# robot venv는 활성화하지 않고 /opt/hn-venv/bin/python 으로 직접 부릅니다(활성화하면 isaaclab.sh가 거부함).
# ROS middleware는 이미지에 둡니다. compose 없이 docker run(CI, Jetson)으로 띄워도 같게 동작하도록.
ENV HN_TARGET=sim \
    HN_ROS_DISTRO=${ROS_DISTRO} \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    FASTRTPS_DEFAULT_PROFILES_FILE=/opt/hn/fastdds.xml \
    HN_UV=/opt/hn/bin/uv \
    HOME=/home/hn

# 베이스 이미지의 HEALTHCHECK는 Isaac Sim 앱이 주 프로세스로 떠서 Kit 로그에 "App is loaded."를 남겨야 통과합니다.
# 우리 컨테이너는 sleep으로 떠 있고 Isaac Sim은 셸에서 따로 실행하므로, 그대로 두면 docker ps가 계속 unhealthy로 표시합니다.
HEALTHCHECK NONE

# hadolint ignore=DL3066
USER isaaclab
ENTRYPOINT ["/opt/hn/entrypoint.sh"]
CMD ["bash"]
