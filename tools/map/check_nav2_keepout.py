# SPDX-License-Identifier: Apache-2.0
"""Grab /map, /keepout_filter_mask and the Nav2 global costmap, then report keep-out coverage.

Run by check_nav2_keepout.sh inside the ROS image after the Nav2 nodes are up. Exits 1 if any keep-out or
outside-map cell is not lethal in the costmap. Needs rclpy and numpy only.
"""
import sys
import time

import numpy as np
import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

TOPICS = ('/map', '/keepout_filter_mask', '/global_costmap/costmap')


def main(timeout_s=300.0):
    rclpy.init()
    node = rclpy.create_node('check_nav2_keepout')
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
    got = {}
    for topic in TOPICS:
        node.create_subscription(OccupancyGrid, topic, lambda m, t=topic: got.__setitem__(t, m), qos)
    start = time.time()
    while time.time() - start < timeout_s:
        rclpy.spin_once(node, timeout_sec=0.5)
        shapes = {(m.info.height, m.info.width) for m in got.values()}
        if len(got) == len(TOPICS) and len(shapes) == 1:
            break
    else:
        print('timeout: costmap did not reach the map size', {t: (m.info.height, m.info.width) for t, m in got.items()})
        return 1
    grid = {t: np.array(m.data, np.int8).reshape(m.info.height, m.info.width).astype(int) for t, m in got.items()}
    static, mask, cost = grid['/map'], grid['/keepout_filter_mask'], grid['/global_costmap/costmap']
    keepout = mask == 100
    lethal = cost >= 99
    walkable = (static == 0) & ~keepout
    rows = [('keep-out cells (zones + outside map)', keepout, lethal),
            ('outside map (unknown in map.yaml)', static == -1, lethal),
            ('walkable cells with cost 0', walkable, cost == 0)]
    for name, sel, ok in rows:
        print(f'{name}: {int(sel.sum())} cells, {ok[sel].mean() * 100:.2f}%')
    failed = not lethal[keepout].all() or not lethal[static == -1].all()
    print('RESULT:', 'FAIL' if failed else 'PASS')
    node.destroy_node()
    rclpy.shutdown()
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
