# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Read-only telemetry hook for an existing MuJoCo simulation. Never steps or controls it.

Call publish(data) AFTER mj_step on the simulation thread; ROS publishing is synchronous.
Requires ROS 2 Jazzy (rclpy, sensor_msgs_py), numpy and mujoco in the same interpreter.
All topic/site/body names are supplied by the caller, not team defaults.
"""
import math
import numpy as np
import mujoco
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, PointField
from sensor_msgs_py import point_cloud2
from rosgraph_msgs.msg import Clock
from builtin_interfaces.msg import Time
from std_msgs.msg import Header


def sim_stamp(seconds):
    ns = round(float(seconds) * 1_000_000_000)
    return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


class MujocoTelemetry(Node):
    def __init__(self, model, *, body, gt_topic, world_frame, base_frame,
                 clock_owner=False, lidar_site=None, lidar_topic=None,
                 lidar_frame=None, accel_sensor=None, gyro_sensor=None,
                 imu_topic=None, imu_frame=None, lidar_hz=10, max_range=35,
                 lidar_rings=16, lidar_columns=360, lidar_hfov_deg=360):
        super().__init__('hyper_mujoco_telemetry')
        self.model = model
        self.body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body)
        if self.body <= 0:
            raise ValueError('Explicit robot body name is missing or resolves to world')
        self.world_frame, self.base_frame = world_frame, base_frame
        self.gt = self.create_publisher(Odometry, gt_topic, 10)
        self.clock = self.create_publisher(Clock, '/clock', 10) if clock_owner else None
        self.last_gt = self.last_lidar = -math.inf
        self.previous_time = -math.inf
        self.period, self.max_range = 1 / lidar_hz, max_range
        self.lidar = None
        if lidar_site is not None:
            if not lidar_topic or not lidar_frame:
                raise ValueError('LiDAR topic and frame are required')
            self.site = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, lidar_site)
            if self.site < 0:
                raise ValueError('LiDAR mount site not found')
            # A body-mounted site is needed to exclude robot self-collisions in mj_ray.
            self.lidar_body = int(model.site_bodyid[self.site])
            self.lidar_frame = lidar_frame
            elevation, azimuth = np.meshgrid(np.linspace(-.26, .26, lidar_rings),
                                             np.linspace(-math.radians(lidar_hfov_deg) / 2, math.radians(lidar_hfov_deg) / 2,
                                                         lidar_columns, endpoint=lidar_hfov_deg < 360),
                                             indexing='ij')
            self._directions = np.stack([np.cos(elevation) * np.cos(azimuth),
                                         np.cos(elevation) * np.sin(azimuth),
                                         np.sin(elevation)], axis=-1).reshape(-1, 3)
            self.lidar = self.create_publisher(
                __import__('sensor_msgs.msg', fromlist=['PointCloud2']).PointCloud2,
                lidar_topic, qos_profile_sensor_data)
        self.imu_pub = None
        if accel_sensor is not None or gyro_sensor is not None:
            if not all([accel_sensor, gyro_sensor, imu_topic, imu_frame]):
                raise ValueError('Both physical IMU sensors, topic and frame are required')
            self.accel = self._sensor(accel_sensor, mujoco.mjtSensor.mjSENS_ACCELEROMETER)
            self.gyro = self._sensor(gyro_sensor, mujoco.mjtSensor.mjSENS_GYRO)
            if model.sensor_objid[self.accel] != model.sensor_objid[self.gyro]:
                raise ValueError('Accelerometer and gyro must share the same site')
            self.imu_frame = imu_frame
            self.imu_pub = self.create_publisher(Imu, imu_topic, qos_profile_sensor_data)

    def _sensor(self, name, expected):
        sid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SENSOR, name)
        if sid < 0 or self.model.sensor_type[sid] != expected or self.model.sensor_dim[sid] != 3:
            raise ValueError(f'Invalid or missing sensor: {name}')
        return sid

    def publish(self, data):
        t = float(data.time)
        if t < self.previous_time:
            self.last_gt = self.last_lidar = -math.inf
        self.previous_time = t
        stamp = sim_stamp(t)
        if self.clock:
            self.clock.publish(Clock(clock=stamp))
        if t - self.last_gt >= .02 - 1e-9:
            msg = Odometry(header=Header(stamp=stamp, frame_id=self.world_frame),
                           child_frame_id=self.base_frame)
            p = data.xpos[self.body]
            q = data.xquat[self.body]  # MuJoCo wxyz -> ROS xyzw.
            msg.pose.pose.position.x, msg.pose.pose.position.y, msg.pose.pose.position.z = map(float, p)
            msg.pose.pose.orientation.w, msg.pose.pose.orientation.x, msg.pose.pose.orientation.y, msg.pose.pose.orientation.z = map(float, q)
            # Twist intentionally unfilled. Frontend derives speed from pose/time.
            self.gt.publish(msg)
            self.last_gt = t
        if self.imu_pub:
            msg = Imu(header=Header(stamp=stamp, frame_id=self.imu_frame))
            msg.orientation_covariance[0] = -1.0  # No orientation sensor. Never inject GT into LIO.
            for sensor, dest in [(self.accel, msg.linear_acceleration), (self.gyro, msg.angular_velocity)]:
                address = int(self.model.sensor_adr[sensor])
                dest.x, dest.y, dest.z = map(float, data.sensordata[address:address + 3])
            self.imu_pub.publish(msg)
        if self.lidar and t - self.last_lidar >= self.period - 1e-9:
            self._scan(data, stamp)
            self.last_lidar = t
    def _scan(self, data, stamp):
        # Instantaneous scan, lidar_rings x lidar_columns rays (default 16 x 360). Per-point t=0 ns: NOT a spinning LiDAR model.
        origin = np.asarray(data.site_xpos[self.site], dtype=np.float64)
        rotation = np.asarray(data.site_xmat[self.site]).reshape(3, 3)
        directions = self._directions  # sensor frame, unit vectors
        world = np.ascontiguousarray((directions @ rotation.T).ravel())
        n = len(directions)
        geomid, distance = np.zeros(n, dtype=np.int32), np.zeros(n)
        # One batched call instead of n Python-level mj_ray calls; same rays and exclusions.
        mujoco.mj_multiRay(self.model, data, origin, world, None, 1, self.lidar_body,
                           geomid, distance, None, n, self.max_range)
        hit = (distance > .15) & (distance < self.max_range)
        points = [(*map(float, d * r), 1.0, 0) for d, r in zip(directions[hit], distance[hit])]
        fields = [PointField(name=n, offset=i * 4, datatype=PointField.FLOAT32, count=1)
                  for i, n in enumerate(['x', 'y', 'z', 'intensity'])]
        fields.append(PointField(name='t', offset=16, datatype=PointField.UINT32, count=1))
        self.lidar.publish(point_cloud2.create_cloud(
            Header(stamp=stamp, frame_id=self.lidar_frame), fields, points))

