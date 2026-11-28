# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 관제 앱 연결 확인 (IF-02, R-16). 토픽 /hn/app/heartbeat, QoS STREAM, 2 Hz.
# 제어권명령관리가 client_id별로 마지막 수신 시각을 보고 연결 끊김을 판단합니다.
# 끊김 판정 시간과 끊겼을 때의 동작은 docs/interfaces/sw-contract.md에 둡니다.

std_msgs/Header header   # stamp: 앱이 보낸 시각
string client_id
uint32 seq               # 1씩 증가. 건너뛰면 손실로 셉니다
