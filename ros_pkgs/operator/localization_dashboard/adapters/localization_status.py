# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Provisional /localization/status: health of the localization output, as a DiagnosticArray.

Works on any nav_msgs/Odometry source (Super-LIO on a bag, a simulator, the robot), so it does not
depend on the estimator. It judges whether poses keep arriving at a sane rate and without jumps;
it does NOT measure accuracy against the map (there is no map matching yet). Layout follows G-006
(docs/interfaces/locomotion-status.md); this node's contract is in
docs/interfaces/localization-status.md (draft, 2026-11-28).

Example: /opt/hn-venv/bin/python localization_status.py --odom /localization/odometry --scan /lidar/points
"""
import argparse
import math
import time
from collections import deque

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2

STATES = ['ACQUIRING', 'TRACKING', 'DEGRADED', 'LOST', 'STALE_INPUT', 'INPUT_TIMEOUT']
LEVEL = {0: DiagnosticStatus.WARN, 1: DiagnosticStatus.OK, 2: DiagnosticStatus.WARN,
         3: DiagnosticStatus.ERROR, 4: DiagnosticStatus.STALE, 5: DiagnosticStatus.ERROR}
QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                 history=HistoryPolicy.KEEP_LAST, depth=1)


def stamp_s(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


class Judge:
    """Pure state logic (no ROS) so it can be tested. Times: t = message stamp, wall = monotonic."""

    def __init__(self, a):
        self.a = a
        self.stamps = deque()            # odometry stamps inside the rate window
        self.last_odom_wall = self.last_scan_wall = None
        self.last_pose = None            # (t, x, y, z)
        self.ref = None                  # pose the speed is measured from (>= min_dt old)
        self.first_t = None
        self.lost_until = None           # wall time a LOST verdict is held until
        self.lost_reason = ''
        self.speed = None

    def odom(self, t, xyz, wall):
        if not all(math.isfinite(v) for v in (t, *xyz)):
            self.lost_until, self.lost_reason = wall + self.a.hold, 'non_finite'
            return
        if self.last_pose and t < self.last_pose[0]:
            self.__init__(self.a)        # time went backwards: bag restarted
        # Speed over >= min_dt: Super-LIO can emit two poses 1 ms apart, where 2 cm would read as 20 m/s.
        ref = self.ref
        if ref and t - ref[0] >= self.a.min_dt:
            self.speed = math.dist(xyz, ref[1:]) / (t - ref[0])
            if self.speed > self.a.max_speed:
                self.lost_until, self.lost_reason = wall + self.a.hold, 'jump'
                self.jump = (t - ref[0], math.dist(xyz, ref[1:]))
        if not ref or t - ref[0] >= self.a.min_dt:
            self.ref = (t, *xyz)
        self.first_t = t if self.first_t is None else self.first_t
        self.last_pose, self.last_odom_wall = (t, *xyz), wall
        self.stamps.append(t)
        while self.stamps and self.stamps[0] < t - self.a.window:
            self.stamps.popleft()

    def scan(self, wall):
        self.last_scan_wall = wall

    def rate(self):
        if len(self.stamps) < 2 or self.stamps[-1] - self.first_t < self.a.window:
            return None
        return (len(self.stamps) - 1) / (self.stamps[-1] - self.stamps[0])

    def state(self, wall):
        """(code, reason)."""
        if self.last_odom_wall is None:
            return 0, 'waiting_odom'
        if wall - self.last_odom_wall > self.a.timeout:
            return 5, 'no_odom'
        if self.a.scan and self.last_scan_wall is not None and wall - self.last_scan_wall > self.a.timeout:
            return 4, 'no_scan'
        if self.lost_until is not None and wall < self.lost_until:
            return 3, self.lost_reason
        rate = self.rate()
        if rate is None:
            return 0, 'warming_up'
        if rate < self.a.min_rate:
            return 2, 'low_rate'
        return 1, 'ok'


class StatusNode(Node):
    def __init__(self, a):
        # Wall-clock node: timers must run even when /clock stops (same rule as G-006).
        super().__init__('localization_status', parameter_overrides=[Parameter('use_sim_time', value=False)])
        self.a, self.judge = a, Judge(a)
        self.pub = self.create_publisher(DiagnosticArray, a.topic, QOS)
        self.create_subscription(Odometry, a.odom, self.on_odom, qos_profile_sensor_data)
        if a.scan:
            self.create_subscription(PointCloud2, a.scan, lambda _: self.judge.scan(time.monotonic()),
                                     qos_profile_sensor_data)
        self.current, self.since = None, time.monotonic()
        self.create_timer(1.0 / a.heartbeat, self.tick)

    def on_odom(self, m):
        p = m.pose.pose.position
        self.judge.odom(stamp_s(m), (p.x, p.y, p.z), time.monotonic())
        self.tick()

    def tick(self):
        wall = time.monotonic()
        code, reason = self.judge.state(wall)
        changed = (code, reason) != self.current
        if changed:
            self.current, self.since = (code, reason), wall
            extra = ' dt=%.3f s, dist=%.2f m' % self.judge.jump if reason == 'jump' else ''
            self.get_logger().info(f'{STATES[code]} ({reason}){extra}')
        elif self.judge.last_odom_wall is not None and wall - getattr(self, 'sent', 0) < 1.0 / self.a.heartbeat:
            return                       # odometry arrives at 10 Hz+; publish at most at the heartbeat rate
        self.sent = wall
        st = DiagnosticStatus(level=LEVEL[code], name='localization/state', message=STATES[code],
                              hardware_id=self.a.robot_id)
        values = {'code': str(code), 'state': STATES[code], 'reason': reason,
                  'since_s': f'{wall - self.since:.2f}', 'source': self.a.odom}
        j = self.judge
        if j.last_pose:
            values['sim_t'] = f'{j.last_pose[0]:.3f}'
            values['age_s'] = f'{wall - j.last_odom_wall:.2f}'
        if j.rate() is not None:
            values['rate_hz'] = f'{j.rate():.1f}'
        if j.speed is not None:
            values['speed_mps'] = f'{j.speed:.2f}'
        st.values = [KeyValue(key=k, value=v) for k, v in values.items()]
        msg = DiagnosticArray(status=[st])
        msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(time.time_ns(), 10**9)
        self.pub.publish(msg)


def parser():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--odom', default='/localization/odometry')
    p.add_argument('--scan', default='', help='LiDAR topic; if it stops while odometry continues -> STALE_INPUT')
    p.add_argument('--topic', default='/localization/status')
    p.add_argument('--robot-id', default='hn_v1_hyper')
    p.add_argument('--min-rate', type=float, default=5.0, help='Hz, in message time; below -> DEGRADED')
    p.add_argument('--window', type=float, default=2.0, help='s, rate window in message time')
    p.add_argument('--max-speed', type=float, default=5.0, help='m/s between poses; above -> LOST (jump)')
    p.add_argument('--min-dt', type=float, default=0.05, help='s, shortest interval the speed is measured over')
    p.add_argument('--hold', type=float, default=2.0, help='s (wall), how long LOST is held')
    p.add_argument('--timeout', type=float, default=1.0, help='s (wall) without odometry/scan')
    p.add_argument('--heartbeat', type=float, default=5.0, help='Hz')
    return p


def main():
    args, ros_args = parser().parse_known_args()
    rclpy.init(args=ros_args)
    node = StatusNode(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
