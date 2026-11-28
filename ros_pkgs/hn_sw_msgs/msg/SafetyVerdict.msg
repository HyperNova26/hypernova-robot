# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 이동 명령에 대한 안전 판정 (IF-04). 토픽 /hn/safety/verdict, QoS CONTROL, 50 Hz.

std_msgs/Header header
bool allowed     # 기본값 false = 불허
uint8 hazard_type  # Hazard.TYPE_*
bool resumable   # 운영자가 재개 요청을 할 수 있는 상태인지
bool stop_confirmed  # 실제 속도로 정지를 확인함. 기준은 docs/interfaces/sw-contract.md
Reason reason
