#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
"""Load a Nav2 static map and keep-out mask into a real Nav2 global costmap, then report keep-out coverage.

Run inside the team ROS container (./docker/hn ros) through check_nav2_keepout.sh. Nodes come up in the order
that makes the keep-out filter apply fully: filter_mask_server and costmap_filter_info_server, then the
costmap, then map_server; each step waits until the previous nodes report lifecycle state "active".
Exits 1 if any keep-out or outside-map cell is not lethal, 2 if Nav2 packages are missing.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = ('nav2_map_server', 'nav2_costmap_2d', 'nav2_lifecycle_manager')
TOPICS = ('/map', '/keepout_filter_mask', '/global_costmap/costmap')


def missing_packages():
    return [p for p in PACKAGES
            if subprocess.run(['ros2', 'pkg', 'prefix', p], capture_output=True).returncode != 0]


class Nodes:
    """Start ROS nodes as child processes (logs in one folder) and drive their lifecycle over rclpy."""

    def __init__(self, node, params, log_dir):
        self.node, self.params, self.log_dir, self.procs = node, params, log_dir, []

    def run(self, name, package, executable, *ros_args, args=()):
        log = open(self.log_dir / f'{name}.log', 'w')
        cmd = ['ros2', 'run', package, executable, *args, '--ros-args', '--params-file', str(self.params), *ros_args]
        self.procs.append(subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT))

    def _call(self, srv_type, service, request, timeout_s):
        import rclpy
        client = self.node.create_client(srv_type, service)
        try:
            if not client.wait_for_service(timeout_sec=timeout_s):
                return None
            future = client.call_async(request)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout_s)
            return future.result()
        finally:
            self.node.destroy_client(client)

    def state(self, node_name, timeout_s=2.0):
        from lifecycle_msgs.srv import GetState
        result = self._call(GetState, f'{node_name}/get_state', GetState.Request(), timeout_s)
        return result.current_state.label if result else None

    def wait_active(self, *node_names, timeout_s=60.0):
        start = time.time()
        while time.time() - start < timeout_s:
            if all(self.state(n) == 'active' for n in node_names):
                return
            time.sleep(0.5)
        raise SystemExit(f'not active after {timeout_s:.0f} s: {node_names}; logs in {self.log_dir}')

    def transition(self, node_name, label, timeout_s=60.0):
        from lifecycle_msgs.msg import Transition
        from lifecycle_msgs.srv import ChangeState
        ids = {'configure': Transition.TRANSITION_CONFIGURE, 'activate': Transition.TRANSITION_ACTIVATE}
        request = ChangeState.Request()
        request.transition.id = ids[label]
        start = time.time()
        while time.time() - start < timeout_s:   # the node may still be starting: retry until it accepts
            result = self._call(ChangeState, f'{node_name}/change_state', request, 5.0)
            if result and result.success:
                return
            time.sleep(1.0)
        raise SystemExit(f'{node_name}: {label} failed after {timeout_s:.0f} s; logs in {self.log_dir}')

    def stop(self):
        for proc in reversed(self.procs):
            proc.terminate()
        for proc in self.procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def grab_grids(node, timeout_s):
    """Wait until /map, the keep-out mask and the full-size costmap have all arrived."""
    import numpy as np
    import rclpy
    from nav_msgs.msg import OccupancyGrid
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
    got = {}
    for topic in TOPICS:
        node.create_subscription(OccupancyGrid, topic, lambda m, t=topic: got.__setitem__(t, m), qos)
    start = time.time()
    while time.time() - start < timeout_s:
        rclpy.spin_once(node, timeout_sec=0.5)
        if len(got) == len(TOPICS) and len({(m.info.height, m.info.width) for m in got.values()}) == 1:
            grid = {t: np.array(m.data, np.int8).reshape(m.info.height, m.info.width).astype(int)
                    for t, m in got.items()}
            info = got['/map'].info
            return grid, (info.resolution, info.origin.position.x, info.origin.position.y)
    print('timeout: costmap did not reach the map size', {t: (m.info.height, m.info.width) for t, m in got.items()})
    return None, None


def report(grid):
    static, mask, cost = grid['/map'], grid['/keepout_filter_mask'], grid['/global_costmap/costmap']
    keepout = mask == 100
    lethal = cost >= 99
    walkable = (static == 0) & ~keepout
    rows = [('keep-out cells (off road + outside map)', keepout, lethal),
            ('outside map (unknown in map.yaml)', static == -1, lethal),
            ('walkable cells with cost 0', walkable, cost == 0)]
    for name, sel, ok in rows:
        print(f'{name}: {int(sel.sum())} cells, {ok[sel].mean() * 100:.2f}%')
    failed = not lethal[keepout].all() or not lethal[static == -1].all()
    print('RESULT:', 'FAIL' if failed else 'PASS')
    return int(failed)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('maps', nargs='?', type=Path, default=REPO / 'sim_scenes/pair360_nav2',
                    help='folder with map.yaml, keepout_mask.yaml and nav2_params.example.yaml (default: %(default)s)')
    ap.add_argument('--start-xy', type=float, nargs=2, default=(-48.46, 119.61),
                    help='robot position published as pair360_map -> base_link, m (default: 2026-11-15 recording start)')
    ap.add_argument('--save', type=Path, help='also write the three grids to <SAVE>/nav2_grids.npz (int8 values, res, origin)')
    ap.add_argument('--timeout', type=float, default=300.0,
                    help='seconds to wait for the full-size costmap (default: %(default)s; 1611x1616 takes minutes)')
    args = ap.parse_args()
    maps = args.maps.resolve()

    missing = missing_packages()
    if missing:
        print('Nav2 packages missing in this environment:', ' '.join(missing), file=sys.stderr)
        print('Install them in the container first: sudo apt-get install -y '
              + ' '.join('ros-jazzy-' + p.replace('_', '-') for p in PACKAGES), file=sys.stderr)
        return 2

    import rclpy
    rclpy.init()
    node = rclpy.create_node('check_nav2_keepout')
    log_dir = Path(tempfile.mkdtemp(prefix='nav2_keepout_'))
    nodes = Nodes(node, maps / 'nav2_params.example.yaml', log_dir)
    try:
        nodes.run('tf', 'tf2_ros', 'static_transform_publisher', args=(
            '--frame-id', 'pair360_map', '--child-frame-id', 'base_link',
            '--x', str(args.start_xy[0]), '--y', str(args.start_xy[1])))
        # 1) keep-out mask and filter info
        nodes.run('mask', 'nav2_map_server', 'map_server', '-r', '__node:=filter_mask_server',
                  '-p', f'yaml_filename:={maps / "keepout_mask.yaml"}')
        nodes.run('info', 'nav2_map_server', 'costmap_filter_info_server')
        nodes.run('lm_filters', 'nav2_lifecycle_manager', 'lifecycle_manager', '-r', '__node:=lifecycle_manager_filters')
        nodes.wait_active('/filter_mask_server', '/costmap_filter_info_server')
        # 2) costmap
        nodes.run('costmap', 'nav2_costmap_2d', 'nav2_costmap_2d', '-r', '__ns:=/global_costmap',
                  '-r', '__node:=global_costmap', '-p', 'always_send_full_costmap:=true')
        nodes.transition('/global_costmap/global_costmap', 'configure')
        nodes.transition('/global_costmap/global_costmap', 'activate')
        # 3) static map last
        nodes.run('map', 'nav2_map_server', 'map_server', '-p', f'yaml_filename:={maps / "map.yaml"}')
        nodes.run('lm_map', 'nav2_lifecycle_manager', 'lifecycle_manager', '-r', '__node:=lifecycle_manager_map')
        nodes.wait_active('/map_server')
        grid, geometry = grab_grids(node, args.timeout)
        if grid is None:
            return 1
        if args.save:
            import numpy as np
            args.save.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(args.save / 'nav2_grids.npz', res=geometry[0], origin=geometry[1:],
                                **{t.strip('/').replace('/', '_'): g.astype(np.int8) for t, g in grid.items()})
        return report(grid)
    finally:
        nodes.stop()
        node.destroy_node()
        rclpy.shutdown()
        print('node logs:', log_dir)


if __name__ == '__main__':
    os.environ.setdefault('RCUTILS_COLORIZED_OUTPUT', '0')
    sys.exit(main())
