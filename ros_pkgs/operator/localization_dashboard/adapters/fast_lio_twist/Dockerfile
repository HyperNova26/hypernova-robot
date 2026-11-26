# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
# Local test image: team hn:ros + FAST-LIO2 rebuilt with twist.linear filled (patch_twist.sh).
# Same pinned commit and C++17 fix as docker/scripts/install_lio.sh; replaces fast_lio in /opt/hn_ws/install.
ARG BASE=hn:ros-2026.10.1-local
FROM ${BASE}
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY patch_twist.sh /opt/hn/scripts/patch_fast_lio_twist.sh
RUN set -eux; \
    WS=/opt/hn_ws; mkdir -p $WS/src; cd $WS/src; \
    git clone https://github.com/hku-mars/FAST_LIO.git; cd FAST_LIO; \
    git checkout a4743b095409588842a5b30ddfa27e29d2f99164; git submodule update --init --recursive; \
    sed -i -e 's/-std=c++14/-std=c++17/g' -e 's/-std=c++0x/-std=c++17/g' -e 's/CMAKE_CXX_STANDARD 14/CMAKE_CXX_STANDARD 17/' CMakeLists.txt; \
    bash /opt/hn/scripts/patch_fast_lio_twist.sh $WS/src/FAST_LIO; \
    set +u; . /opt/ros/jazzy/setup.bash; . $WS/install/setup.bash; set -u; \
    cd $WS; colcon --log-base $WS/log_twist build --base-paths src/FAST_LIO --packages-select fast_lio       --build-base $WS/build_twist --install-base $WS/install --cmake-args -DCMAKE_BUILD_TYPE=Release;     rm -rf $WS/src $WS/build_twist $WS/log_twist
