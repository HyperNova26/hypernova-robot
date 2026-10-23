# shellcheck shell=bash disable=SC1090,SC1091
# HyperNova 컨테이너의 ROS 환경.
# entrypoint.sh(컨테이너 시작, hn으로 여는 셸·명령)와 /etc/bash.bashrc(VS Code 등으로 직접 붙은 대화형 셸)가 source합니다.
# 여러 번 source해도 안전합니다. 실행하는 파일이 아니므로 chmod +x 하지 않습니다.

# ROS setup 스크립트는 정의 안 된 변수를 참조하므로 nounset을 잠시 끕니다.
case $- in *u*) _hn_nounset=1; set +u ;; *) _hn_nounset=0 ;; esac

# 1) 시스템 ROS  2) 이미지에 구워 둔 underlay(LIO, ros target만)  3) 저장소를 colcon build한 결과(named volume)
. "/opt/ros/${HN_ROS_DISTRO}/setup.bash"
[ -f /opt/hn_ws/install/setup.bash ] && . /opt/hn_ws/install/setup.bash
[ -f "${HN_WORKSPACE:-/workspace/hypernova}/install/setup.bash" ] && . "${HN_WORKSPACE:-/workspace/hypernova}/install/setup.bash"

[ "$_hn_nounset" = 1 ] && set -u
unset _hn_nounset

# 대화형 셸이면 프롬프트로 컨테이너 안임을 알립니다. (사용자 이름은 UID에 따라 "I have no name!"이 될 수 있어 넣지 않습니다)
case $- in *i*) PS1='\[\e[1;36m\](hn:'"${HN_TARGET:-?}"')\[\e[0m\] \w \$ ' ;; esac

true   # source한 쪽이 set -e여도 이 파일 때문에 종료되지 않게 항상 성공으로 끝냅니다
