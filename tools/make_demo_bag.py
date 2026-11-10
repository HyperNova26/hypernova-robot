#!/usr/bin/env python3
"""LIO 시험용 데모 rosbag(MCAP)을 만듭니다. 합성 데이터라서 외부 다운로드가 필요 없습니다.

방 하나(12 x 8 x 3 m, 기둥·상자 4개) 안에서 8자 경로로 움직이는 로봇에 달린 회전식 LiDAR(16채널)와 IMU를
시뮬레이션합니다. 처음 2초는 정지, 다음 2초 동안 가속한 뒤 일정 속도(최대 약 0.7 m/s)로 움직입니다.
LiDAR는 점마다 측정 시각(`t`)이 달라서 움직이는 동안의 왜곡(deskew 대상)이 실제처럼 들어갑니다.

  입력   없음 (--seed가 같으면 항상 같은 bag)
  출력   <out>/ 폴더: metadata.yaml, *.mcap  (30초 기준 약 18 MB)
           /lidar/points      sensor_msgs/PointCloud2  10 Hz   x y z intensity t(점별 시각, 초)
           /imu/data          sensor_msgs/Imu          200 Hz  가속도 m/s^2, 각속도 rad/s
           /tf_static         tf2_msgs/TFMessage       1회     base_link -> lidar, base_link -> imu_link
           /ground_truth/odom nav_msgs/Odometry        20 Hz   world 기준 정답 경로 (평가용, LIO는 쓰지 않음)
  환경   hn:ros 컨테이너의 robot venv(numpy)와 ROS Python(rclpy, rosbag2_py)

  사용   ./docker/hn ros /opt/hn-venv/bin/python tools/make_demo_bag.py
         ./docker/hn ros /opt/hn-venv/bin/python tools/make_demo_bag.py --out /data/bags/demo-room --duration 30
  되돌리기  출력 폴더를 지우면 끝입니다(--force로 덮어쓸 수도 있습니다).

실제 센서 bag이 아니므로 LIO 성능을 평가하는 용도가 아니라, 환경이 제대로 깔렸는지와 LIO 실행 절차를
확인하는 용도입니다. 정답과의 차이를 보려면 마지막에 출력되는 "시작 자세 기준 최종 자세"를 LIO의 odom과 비교하세요.
"""

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
from builtin_interfaces.msg import Time
from geometry_msgs.msg import Quaternion, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.serialization import serialize_message
from rosbag2_py import ConverterOptions, SequentialWriter, StorageOptions, TopicMetadata
from rosbag2_py._storage import QoS
from sensor_msgs.msg import Imu, PointCloud2, PointField
from std_msgs.msg import Header
from tf2_msgs.msg import TFMessage

# --- 세계: 방 하나와 기둥·상자(축에 평행한 상자) -------------------------------------------
ROOM_LO = np.array([-6.0, -4.0, 0.0])
ROOM_HI = np.array([6.0, 4.0, 3.0])
OBSTACLES = [  # (최소 모서리, 최대 모서리). 경로(|x|<=3, |y|<=1.5)와 겹치지 않게 둡니다.
    (np.array([-5.2, -3.4, 0.0]), np.array([-4.2, -2.2, 2.0])),
    (np.array([3.8, 2.2, 0.0]), np.array([5.0, 3.2, 1.2])),
    (np.array([-1.0, 2.6, 0.0]), np.array([0.2, 3.4, 2.6])),
    (np.array([4.0, -3.0, 0.0]), np.array([4.6, -2.4, 3.0])),
]

# --- 로봇과 센서 ----------------------------------------------------------------------------
BASE_Z = 0.30  # base_link 높이 (바닥 기준)
LIDAR_OFFSET = np.array([0.15, 0.0, 0.35])  # base_link 기준 lidar 위치(회전 없음)
IMU_OFFSET = np.array([0.0, 0.0, 0.10])  # base_link 기준 imu_link 위치(회전 없음)
LIDAR_HZ, IMU_HZ, GT_HZ = 10, 200, 20
N_BEAMS, N_AZIMUTH = 16, 256  # 한 바퀴(0.1 s)에 16 x 256점
ELEVATION = np.deg2rad(np.linspace(-15.0, 15.0, N_BEAMS))
RANGE_NOISE = 0.01  # m
ACC_NOISE, GYRO_NOISE = 0.03, 0.003  # m/s^2, rad/s
ACC_BIAS = np.array([0.02, -0.01, 0.015])
GYRO_BIAS = np.array([0.001, -0.0005, 0.0008])
GRAVITY = 9.81

# --- 경로: 8자 (한 바퀴 40 s). 처음 T_REST초 정지, 다음 T_RAMP초 동안 가속 ----------------------
AX, AY, OMEGA = 3.0, 1.5, 2 * np.pi / 40.0
T_REST, T_RAMP = 2.0, 2.0
T0_NS = 1_760_000_000 * 10**9  # bag 시작 시각 (임의의 epoch)


def phase(t):
    """경로 매개변수 ph(t)와 그 1, 2계 도함수."""
    u = np.clip(np.asarray(t, dtype=float) - T_REST, 0.0, None)
    ramping = u < T_RAMP
    ph = OMEGA * np.where(ramping, u**2 / (2 * T_RAMP), u - T_RAMP / 2)
    dph = OMEGA * np.where(ramping, u / T_RAMP, 1.0)
    ddph = np.where(ramping & (np.asarray(t) > T_REST), OMEGA / T_RAMP, 0.0)
    return ph, dph, ddph


def base_state(t):
    """시각 t의 base_link 위치 p(3), yaw, 가속도 a(3, 세계 좌표계), yaw 각속도."""
    ph, dph, ddph = phase(t)
    x, y = AX * np.sin(ph), AY * np.sin(2 * ph)
    vx, vy = AX * np.cos(ph), 2 * AY * np.cos(2 * ph)  # d/dph
    ax_, ay_ = -AX * np.sin(ph), -4 * AY * np.sin(2 * ph)  # d2/dph2
    yaw = np.arctan2(vy, vx)
    dyaw_dph = (vx * ay_ - vy * ax_) / (vx**2 + vy**2)
    acc = np.stack([ax_ * dph**2 + vx * ddph, ay_ * dph**2 + vy * ddph, np.zeros_like(ph)], axis=-1)
    p = np.stack([x, y, np.full_like(x, BASE_Z)], axis=-1)
    return p, yaw, acc, dyaw_dph * dph


def rot_z(yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    z, o = np.zeros_like(c), np.ones_like(c)
    return np.stack([np.stack([c, -s, z], -1), np.stack([s, c, z], -1), np.stack([z, z, o], -1)], -2)


def raycast(origin, direction):
    """방 안쪽 벽과 상자에 대한 광선의 첫 교차 거리. origin, direction: (N, 3)."""
    d = np.where(np.abs(direction) < 1e-12, 1e-12, direction)
    t1, t2 = (ROOM_LO - origin) / d, (ROOM_HI - origin) / d
    hit = np.maximum(t1, t2).min(axis=1)  # 방을 벗어나는 거리
    for lo, hi in OBSTACLES:
        t1, t2 = (lo - origin) / d, (hi - origin) / d
        near, far = np.minimum(t1, t2).max(axis=1), np.maximum(t1, t2).min(axis=1)
        hit = np.where((near <= far) & (near > 0) & (near < hit), near, hit)
    return hit


def make_scan(k, rng):
    """k번째 LiDAR 한 바퀴. 점마다 측정 시각이 다르고, 점은 측정 순간의 센서 좌표계로 기록됩니다(왜곡 포함)."""
    t_scan = k / LIDAR_HZ
    az = 2 * np.pi * np.arange(N_AZIMUTH) / N_AZIMUTH
    t_pt = np.repeat(np.arange(N_AZIMUTH) / N_AZIMUTH / LIDAR_HZ, N_BEAMS)  # 점별 상대 시각
    azg, elg = np.repeat(az, N_BEAMS), np.tile(ELEVATION, N_AZIMUTH)
    d_sensor = np.stack([np.cos(elg) * np.cos(azg), np.cos(elg) * np.sin(azg), np.sin(elg)], axis=-1)

    p, yaw, _, _ = base_state(t_scan + t_pt)  # 측정 순간의 로봇 자세
    rot = rot_z(yaw)
    origin = p + np.einsum("nij,j->ni", rot, LIDAR_OFFSET)
    direction = np.einsum("nij,nj->ni", rot, d_sensor)
    r = raycast(origin, direction) + rng.normal(0.0, RANGE_NOISE, len(t_pt))
    xyz = (r[:, None] * d_sensor).astype(np.float32)

    cloud = np.zeros(len(t_pt), dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"), ("intensity", "f4"), ("t", "f4")])
    cloud["x"], cloud["y"], cloud["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    cloud["intensity"] = np.clip(100.0 / np.maximum(r, 1.0), 0, 255)
    cloud["t"] = t_pt
    return cloud


def stamp(t_s):
    ns = T0_NS + int(round(t_s * 1e9))
    return Time(sec=ns // 10**9, nanosec=ns % 10**9), ns


def cloud_msg(cloud, t_s):
    st, ns = stamp(t_s)
    fields = [PointField(name=n, offset=4 * i, datatype=PointField.FLOAT32, count=1) for i, n in enumerate(cloud.dtype.names)]
    msg = PointCloud2(
        header=Header(stamp=st, frame_id="lidar"), height=1, width=len(cloud), fields=fields,
        is_bigendian=False, point_step=cloud.dtype.itemsize, row_step=cloud.dtype.itemsize * len(cloud),
        data=cloud.tobytes(), is_dense=True,
    )
    return msg, ns


def imu_msg(t_s, rng):
    p, yaw, acc, yaw_rate = base_state(t_s)
    # 가속도계는 비력(중력 반대 방향 +g)을 body 좌표계로 잽니다. 정지하면 z축에 +9.81.
    f_body = rot_z(yaw).T @ (acc + np.array([0.0, 0.0, GRAVITY]))
    f_body = f_body + ACC_BIAS + rng.normal(0.0, ACC_NOISE, 3)
    w_body = np.array([0.0, 0.0, yaw_rate]) + GYRO_BIAS + rng.normal(0.0, GYRO_NOISE, 3)
    st, ns = stamp(t_s)
    msg = Imu(header=Header(stamp=st, frame_id="imu_link"))
    msg.orientation_covariance[0] = -1.0  # 방향 추정치 없음
    msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z = map(float, w_body)
    msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z = map(float, f_body)
    return msg, ns


def odom_msg(t_s):
    p, yaw, _, _ = base_state(t_s)
    st, ns = stamp(t_s)
    msg = Odometry(header=Header(stamp=st, frame_id="world"), child_frame_id="base_link")
    msg.pose.pose.position.x, msg.pose.pose.position.y, msg.pose.pose.position.z = map(float, p)
    msg.pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=float(np.sin(yaw / 2)), w=float(np.cos(yaw / 2)))
    return msg, ns


def tf_static_msg():
    st, ns = stamp(0.0)
    msg = TFMessage()
    for child, offset in (("lidar", LIDAR_OFFSET), ("imu_link", IMU_OFFSET)):
        tf = TransformStamped(header=Header(stamp=st, frame_id="base_link"), child_frame_id=child)
        tf.transform.translation.x, tf.transform.translation.y, tf.transform.translation.z = map(float, offset)
        tf.transform.rotation.w = 1.0
        msg.transforms.append(tf)
    return msg, ns


def tf_static_qos():
    """rosbag2가 /tf_static을 기록할 때 쓰는 QoS(reliable, transient_local). 이게 있어야 ros2 bag play가 늦게 붙은 구독자에게도 전달합니다."""
    return [QoS(1).keep_all().reliable().transient_local()]


def relative_pose(t_end):
    """시작 자세 기준(시작 자세를 원점으로 한 좌표계)으로 본 t_end의 자세. LIO의 odom과 같은 기준입니다."""
    p0, yaw0, _, _ = base_state(0.0)
    p1, yaw1, _, _ = base_state(t_end)
    dp = rot_z(yaw0).T @ (p1 - p0)
    dyaw = (yaw1 - yaw0 + np.pi) % (2 * np.pi) - np.pi
    return dp, dyaw


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="/data/bags/demo-room", help="출력 폴더 (기본 /data/bags/demo-room)")
    ap.add_argument("--duration", type=float, default=30.0, help="길이(초). 기본 30")
    ap.add_argument("--seed", type=int, default=0, help="잡음 seed. 같으면 같은 bag")
    ap.add_argument("--force", action="store_true", help="출력 폴더가 있으면 지우고 다시 만듭니다")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        if not args.force:
            sys.exit(f"{out} 가 이미 있습니다. 지우거나 --force 를 쓰세요.")
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    writer = SequentialWriter()
    # zstd_small: MCAP chunk 압축. 점구름이 몇 배로 줄어듭니다.
    writer.open(StorageOptions(uri=str(out), storage_id="mcap", storage_preset_profile="zstd_small"), ConverterOptions("", ""))
    topics = [
        ("/lidar/points", "sensor_msgs/msg/PointCloud2", []),
        ("/imu/data", "sensor_msgs/msg/Imu", []),
        ("/tf_static", "tf2_msgs/msg/TFMessage", tf_static_qos()),
        ("/ground_truth/odom", "nav_msgs/msg/Odometry", []),
    ]
    for i, (name, type_, qos) in enumerate(topics):
        writer.create_topic(TopicMetadata(id=i, name=name, type=type_, serialization_format="cdr", offered_qos_profiles=qos))

    def write(topic, made):
        msg, ns = made
        writer.write(topic, serialize_message(msg), ns)

    write("/tf_static", tf_static_msg())
    n_scans, n_imu, n_gt = int(args.duration * LIDAR_HZ) - 1, int(args.duration * IMU_HZ), int(args.duration * GT_HZ)
    # 시간 순서대로 쓰기 위해 (시각, 종류, 번호)로 모아 정렬합니다. LiDAR는 한 바퀴가 끝나는 시각에 도착한다고 봅니다.
    events = [(k / LIDAR_HZ + 1 / LIDAR_HZ, "lidar", k) for k in range(n_scans)]
    events += [(i / IMU_HZ, "imu", i) for i in range(n_imu)]
    events += [(i / GT_HZ, "gt", i) for i in range(n_gt)]
    for _, kind, i in sorted(events):
        if kind == "lidar":
            write("/lidar/points", cloud_msg(make_scan(i, rng), i / LIDAR_HZ))
        elif kind == "imu":
            write("/imu/data", imu_msg(i / IMU_HZ, rng))
        else:
            write("/ground_truth/odom", odom_msg(i / GT_HZ))
    del writer  # 닫아서 metadata.yaml을 씁니다

    t_end = (n_scans - 1) / LIDAR_HZ  # 마지막 LiDAR 스캔의 시작 시각
    dp, dyaw = relative_pose(t_end)
    size = sum(f.stat().st_size for f in out.iterdir()) / 1e6
    print(f"만들었습니다: {out}  ({size:.1f} MB, {args.duration:.0f}초, LiDAR {n_scans}회, IMU {n_imu}개)")
    print(f"마지막 스캔 시작 시각 {t_end:.1f}초 기준 정답 — 시작 자세를 원점으로 본 로봇(base_link) 자세")
    print(f"  위치 x={dp[0]:+.3f} y={dp[1]:+.3f} z={dp[2]:+.3f} m,  yaw={np.rad2deg(dyaw):+.1f} deg")


if __name__ == "__main__":
    main()
