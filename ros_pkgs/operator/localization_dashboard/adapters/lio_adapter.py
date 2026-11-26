# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Normalize any nav_msgs/Odometry to a shared parent and comparison origin, at measurement time.

Example: python lio_adapter.py --input ACTUAL_GT_TOPIC --output /dashboard/gt_lidar
         --frame pair360_map --base mlx_lidar
Topic /dashboard/gt_lidar is a LOCAL PROPOSAL, not an agreed team GT topic.
Only publish calibrated sensor extrinsics / localization transforms to this node.
Never use SIM GT as map->LIO initialization or correction without a declared experiment.
"""
import argparse
import copy
import math
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.duration import Duration
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Pose, Quaternion
from tf2_ros import Buffer, TransformListener, TransformException
from sensor_msgs.msg import PointCloud2


def multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx,
            aw*bz+ax*by-ay*bx+az*bw, aw*bw-ax*bx-ay*by-az*bz)


def quat(q):
    values = (q.x, q.y, q.z, q.w)
    length = math.sqrt(sum(x*x for x in values))
    if not math.isfinite(length) or length < 1e-9:
        raise ValueError('Invalid quaternion')
    return tuple(x/length for x in values)


def compose(a, b):
    ap, aq = a
    bp, bq = b
    rotated = multiply(multiply(aq, (*bp, 0)), (-aq[0], -aq[1], -aq[2], aq[3]))[:3]
    return tuple(x+y for x, y in zip(ap, rotated)), multiply(aq, bq)


def transform_tuple(tf):
    t = tf.transform
    return (t.translation.x, t.translation.y, t.translation.z), quat(t.rotation)


IDENTITY = ((0., 0., 0.), (0., 0., 0., 1.))


class LioAdapter(Node):
    def __init__(self, args):
        super().__init__('hyper_lio_adapter')
        self.args = args
        self.buffer = Buffer(cache_time=Duration(seconds=15))
        self.listener = TransformListener(self.buffer, self)
        self.publisher = self.create_publisher(Odometry, args.output, 10)
        self.subscription = self.create_subscription(
            Odometry, args.input, self.on_odom, qos_profile_sensor_data)
        self.dropped = 0
        if args.scan_input:
            from tf2_sensor_msgs.tf2_sensor_msgs import do_transform_cloud
            self.transform_cloud = do_transform_cloud
            self.scan_publisher = self.create_publisher(PointCloud2, args.scan_output, qos_profile_sensor_data)
            self.scan_subscription = self.create_subscription(PointCloud2, args.scan_input, self.on_cloud, qos_profile_sensor_data)

    def on_cloud(self, message):
        try:
            if message.header.frame_id == self.args.frame:
                self.scan_publisher.publish(message)
                return
            if message.header.stamp.sec == 0 and message.header.stamp.nanosec == 0:
                raise ValueError('Cloud transform at t=0 is ambiguous')
            tf = self.buffer.lookup_transform(self.args.frame, message.header.frame_id, Time.from_msg(message.header.stamp))
            out = self.transform_cloud(message, tf)
            # Preserve the measurement timestamp rather than replacing it with TF stamp.
            out.header.stamp = message.header.stamp
            self.scan_publisher.publish(out)
        except (TransformException, ValueError) as error:
            self.get_logger().warning(f'PointCloud2 skipped: {error}', throttle_duration_sec=2)

    def lookup(self, parent, child, stamp):
        if parent == child:
            return IDENTITY
        if stamp.sec == 0 and stamp.nanosec == 0:
            # tf2 uses zero as latest. It cannot guarantee measurement-time lookup at t=0.
            raise ValueError('At t=0 only matching frames are accepted')
        return transform_tuple(self.buffer.lookup_transform(
            parent, child, Time.from_msg(stamp)))

    def on_odom(self, message):
        try:
            # Super-LIO leaves child_frame_id empty (its pose is the IMU, TF world->imu).
            child = message.child_frame_id or self.args.child_default
            if not message.header.frame_id or not child:
                raise ValueError('Odometry parent/child frame missing')
            pose = message.pose.pose
            local = ((pose.position.x, pose.position.y, pose.position.z), quat(pose.orientation))
            # map<-parent * parent<-LIO body * LIO body<-comparison body.
            parent = self.lookup(self.args.frame, message.header.frame_id, message.header.stamp)
            body = self.lookup(child, self.args.base, message.header.stamp)
            p, q = compose(compose(parent, local), body)
            out = Odometry()
            out.header = copy.deepcopy(message.header)
            out.header.frame_id = self.args.frame
            out.child_frame_id = self.args.base
            out.pose.pose.position.x, out.pose.pose.position.y, out.pose.pose.position.z = p
            out.pose.pose.orientation = Quaternion(x=q[0], y=q[1], z=q[2], w=q[3])
            # Raw pose/twist covariances need SE(3) propagation; do not copy them as valid.
            # Twist unfilled, explicitly use frontend pose-difference velocity.
            self.publisher.publish(out)
        except (TransformException, ValueError) as error:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                self.get_logger().warning(f'Dropped {self.dropped} odometry samples: {error}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--frame', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--child-default', default='',
                        help='child frame when the input leaves child_frame_id empty (Super-LIO: imu)')
    parser.add_argument('--scan-input')
    parser.add_argument('--scan-output')
    args, ros_args = parser.parse_known_args()
    if args.input == args.output:
        parser.error('Input and output topics must differ')
    if bool(args.scan_input) != bool(args.scan_output) or (args.scan_input and args.scan_input == args.scan_output):
        parser.error('Scan input/output must be supplied together and differ')
    rclpy.init(args=ros_args)
    node = LioAdapter(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
