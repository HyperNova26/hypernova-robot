#!/usr/bin/env python3
"""LIO가 데모 bag에서 정답 경로를 따라가는지 확인합니다 (tools/make_demo_bag.py로 만든 bag 전용).

/rko_lio/odom을 받아 bag의 /ground_truth/odom과 비교합니다. 둘 다 "시작 자세를 원점으로 본" 값이라서
LIO의 odom 원점과 정답의 절대 좌표가 달라도 됩니다. 오차 평균이 --max-mean-error보다 크면 종료 코드 1입니다.

  입력   데모 bag 폴더, 실행 중이거나 곧 실행할 LIO가 내는 /rko_lio/odom
  출력   위치·yaw 오차(터미널). 파일은 만들지 않습니다
  환경   hn:ros 컨테이너의 robot venv(numpy)와 ROS Python(rclpy, rosbag2_py)

  사용   먼저 이 스크립트를 켜 두고(odom을 기다림), 다른 터미널에서 LIO를 돌립니다. odom이 8초 동안 멈추면 결과를 냅니다.
         터미널 1:  ./docker/hn ros /opt/hn-venv/bin/python tools/check_demo_lio.py /data/bags/demo-room
         터미널 2:  ./docker/hn ros ros2 launch rko_lio odometry.launch.py mode:=offline \\
                      bag_path:=/data/bags/demo-room initialization_phase:=true rviz:=false
  기대   (2026-10-22, hn:ros, 기본 seed 0) 평균 오차 약 6 cm, 최대 약 19 cm, yaw 오차 1도 안쪽
"""

import argparse
import math
import sys
import time

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.serialization import deserialize_message
from rosbag2_py import ConverterOptions, SequentialReader, StorageOptions


def stamp_s(header):
    return header.stamp.sec + header.stamp.nanosec * 1e-9


def pose_of(msg):
    p, q = msg.pose.pose.position, msg.pose.pose.orientation
    x, y, z, w = q.x, q.y, q.z, q.w
    rot = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    return stamp_s(msg.header), np.array([p.x, p.y, p.z]), rot


def yaw(rot):
    return math.atan2(rot[1, 0], rot[0, 0])


def relative_to_first(poses, first):
    """첫 자세를 원점으로 본 (시각, 위치, 회전) 목록."""
    _, p0, r0 = poses[first]
    return [(t, r0.T @ (p - p0), r0.T @ r) for t, p, r in poses]


def read_ground_truth(bag_dir):
    reader = SequentialReader()
    reader.open(StorageOptions(uri=bag_dir, storage_id="mcap"), ConverterOptions("", ""))
    poses = []
    while reader.has_next():
        topic, data, _ = reader.read_next()
        if topic == "/ground_truth/odom":
            poses.append(pose_of(deserialize_message(data, Odometry)))
    if not poses:
        sys.exit(f"{bag_dir} 에 /ground_truth/odom이 없습니다. tools/make_demo_bag.py로 만든 bag인지 확인하세요.")
    return poses


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bag", help="tools/make_demo_bag.py가 만든 bag 폴더")
    ap.add_argument("--idle", type=float, default=8.0, help="odom이 이 시간(초) 동안 안 오면 끝난 것으로 봅니다. 기본 8")
    ap.add_argument("--max-mean-error", type=float, default=0.25, help="합격 기준: 위치 오차 평균(m). 기본 0.25")
    args = ap.parse_args()

    gt = read_ground_truth(args.bag)
    gt_t = np.array([g[0] for g in gt])

    rclpy.init()
    node = Node("check_demo_lio")
    lio = []
    node.create_subscription(Odometry, "/rko_lio/odom", lambda m: lio.append(pose_of(m)), 100)
    print("대기 중: /rko_lio/odom (다른 터미널에서 LIO를 실행하세요)", flush=True)
    last_n, last_change = 0, time.time()
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        if len(lio) != last_n:
            last_n, last_change = len(lio), time.time()
        if lio and time.time() - last_change > args.idle:
            break
    node.destroy_node()
    rclpy.shutdown()

    lio_rel = relative_to_first(lio, 0)
    gt_rel = relative_to_first(gt, int(np.argmin(np.abs(gt_t - lio[0][0]))))
    gt_rel_t = np.array([g[0] for g in gt_rel])

    pos_err, yaw_err = [], []
    for t, p, r in lio_rel:
        _, gp, gr = gt_rel[int(np.argmin(np.abs(gt_rel_t - t)))]
        pos_err.append(np.linalg.norm(p - gp))
        yaw_err.append(math.degrees(yaw(gr.T @ r)))
    pos_err = np.array(pos_err)
    _, p_end, r_end = lio_rel[-1]
    _, gp_end, gr_end = gt_rel[int(np.argmin(np.abs(gt_rel_t - lio_rel[-1][0])))]

    print(f"odom {len(lio)}개를 받았습니다.")
    print(f"마지막 자세  LIO  x={p_end[0]:+.3f} y={p_end[1]:+.3f} z={p_end[2]:+.3f} m  yaw={math.degrees(yaw(r_end)):+.1f} deg")
    print(f"             정답 x={gp_end[0]:+.3f} y={gp_end[1]:+.3f} z={gp_end[2]:+.3f} m  yaw={math.degrees(yaw(gr_end)):+.1f} deg")
    print(f"위치 오차: 마지막 {pos_err[-1] * 100:.1f} cm, 평균 {pos_err.mean() * 100:.1f} cm, 최대 {pos_err.max() * 100:.1f} cm")
    print(f"yaw 오차: 마지막 {yaw_err[-1]:+.2f} deg")
    ok = pos_err.mean() <= args.max_mean_error
    print("결과:", "정상" if ok else f"평균 위치 오차가 기준({args.max_mean_error * 100:.0f} cm)보다 큽니다")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
