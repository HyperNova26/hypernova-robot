# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
#
# 위치추정 상태. 토픽 /localization/status (S-005). S-005 확정 전 제안

std_msgs/Header header

uint8 STATUS_ACQUIRING = 0
uint8 STATUS_TRACKING = 1
uint8 STATUS_DEGRADED = 2
uint8 STATUS_LOST = 3
uint8 STATUS_STALE_INPUT = 4
uint8 STATUS_INPUT_TIMEOUT = 5

uint8 status  # STATUS_*
