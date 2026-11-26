#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
# Fill nav_msgs/Odometry twist.linear in FAST-LIO2 publish_odometry with the filter's own
# velocity estimate (state_point.vel, world frame) rotated into the child frame "body"
# (REP-105: twist is expressed in child_frame_id). Angular velocity is left unfilled.
# Usage: patch_twist.sh <FAST_LIO source dir>   (commit a4743b095409588842a5b30ddfa27e29d2f99164)
set -euo pipefail
src="$1/src/laserMapping.cpp"
anchor='    set_posestamp(odomAftMapped.pose);'
[ "$(grep -cF "$anchor" "$src")" = 1 ] || { echo "anchor not found once in $src" >&2; exit 1; }
grep -q 'HYPERNOVA twist' "$src" && { echo "already patched"; exit 0; }
python3 - "$src" "$anchor" <<'PY'
import sys
path, anchor = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
insert = anchor + """
    // HYPERNOVA twist: filter velocity (world) -> child frame "body", per REP-105.
    {
        const V3D v_body = state_point.rot.conjugate() * state_point.vel;
        odomAftMapped.twist.twist.linear.x = v_body(0);
        odomAftMapped.twist.twist.linear.y = v_body(1);
        odomAftMapped.twist.twist.linear.z = v_body(2);
    }"""
open(path, "w", encoding="utf-8").write(text.replace(anchor, insert, 1))
PY
grep -n -A7 'HYPERNOVA twist' "$src"
