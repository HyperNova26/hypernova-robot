# SPDX-License-Identifier: Apache-2.0
"""ROS 2 어댑터(G-006): 판정 보고(StatusReport)를 diagnostic_msgs/DiagnosticArray로 발행합니다. 판정은 하지 않습니다(core.py의 일).

토픽 /locomotion/status, 타입 DiagnosticArray(상태 1개). QoS는 reliable + transient_local + KEEP_LAST 1이라 늦게 붙은 구독자도 마지막 상태를 받습니다.
발행 시점: 상태가 바뀌면 즉시, 그 밖에는 heartbeat(기본 10 Hz)로 마지막 보고를 다시 냅니다. 입력이 끊기면(stale_provider가 보고를 돌려주면) heartbeat가 그것을 냅니다.

시간 규칙(ROS 시계와 시뮬레이터 시계가 어긋나는 문제를 피하려고)
  - header.stamp는 node 시계가 아니라 time.time_ns()(시스템 시간)입니다. 시뮬레이션 시간은 values의 sim_t로 따로 싣습니다.
  - node는 use_sim_time=False를 강제합니다. true인데 /clock이 없으면 ROS 시계가 0에 멈추고 timer(heartbeat)가 돌지 않습니다.
  - 전용 rclpy Context와 전용 스레드를 씁니다. 같은 프로세스의 다른 rclpy 사용(예: Isaac Sim의 ROS 확장)과 전역 상태를 공유하지 않습니다.
rclpy가 있는 환경에서만 import할 수 있습니다(패키지 __init__은 이 모듈을 import하지 않음).

diagnostic_msgs의 byte 필드(level)는 rclpy에서 bytes입니다(정수 아님). values의 키는 값이 없으면 생략합니다(빈 문자열이나 nan을 넣지 않음).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import rclpy
from builtin_interfaces.msg import Time
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from .core import State, StatusReport

DEFAULT_TOPIC = "/locomotion/status"
STATUS_NAME = "locomotion/state"
QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                 history=HistoryPolicy.KEEP_LAST, depth=1)
_FEATURE_VALUES = ("tilt_deg", "roll_deg", "pitch_deg", "speed_mps", "height_m")   # 값이 있을 때만 싣는 특징(소수 3자리)


def report_to_msg(report: StatusReport, robot_id: str, stamp_ns: int) -> DiagnosticArray:
    """보고 하나를 메시지로 바꿉니다(ROS 통신 없이 시험할 수 있는 순수 변환)."""
    status = DiagnosticStatus()
    status.level = bytes([int(report.severity)])
    status.name = STATUS_NAME
    status.message = report.name
    status.hardware_id = robot_id
    pairs = [("code", str(report.code)), ("state", report.name), ("reason", report.reason),
             ("since_s", f"{report.since_s:.2f}"), ("sim_t", f"{report.t:.2f}")]
    pairs += [(k, f"{report.features[k]:.3f}") for k in _FEATURE_VALUES if report.features.get(k) is not None]
    status.values = [KeyValue(key=k, value=v) for k, v in pairs]
    msg = DiagnosticArray()
    msg.header.stamp = Time(sec=int(stamp_ns // 1_000_000_000), nanosec=int(stamp_ns % 1_000_000_000))
    msg.header.frame_id = ""
    msg.status = [status]
    return msg


class StatusPublisher:
    """보고를 발행하는 어댑터. publish()는 판정 스레드에서, heartbeat는 내부 스레드에서 돕니다.

    stale_provider: 호출하면 "입력이 끊겼을 때의 보고"(StatusReport)나 None을 돌려주는 함수(heartbeat 스레드에서 불림).
    """

    def __init__(self, *, topic: str = DEFAULT_TOPIC, robot_id: str = "hn_v0_go2", heartbeat_hz: float = 10.0,
                 stale_provider: Optional[Callable[[], Optional[StatusReport]]] = None, node_name: str = "hn_robot_state",
                 context_args: Optional[list[str]] = None):
        if not heartbeat_hz > 0:
            raise ValueError("heartbeat_hz는 0보다 커야 합니다")
        self.robot_id = robot_id
        self.error: Optional[BaseException] = None        # stale_provider 등에서 난 마지막 예외(발행은 계속함)
        self._stale_provider = stale_provider
        self._lock = threading.Lock()
        self._latest: Optional[StatusReport] = None
        self._last_state: Optional[State] = None
        self._sent = 0
        self._closed = False
        self._ctx = Context()
        rclpy.init(args=list(context_args or []), context=self._ctx)       # args=None이면 sys.argv를 해석하므로 항상 명시
        self._node = Node(node_name, context=self._ctx, enable_rosout=False, start_parameter_services=False,
                          parameter_overrides=[Parameter("use_sim_time", Parameter.Type.BOOL, False)])
        self._pub = self._node.create_publisher(DiagnosticArray, topic, QOS)
        self._timer = self._node.create_timer(1.0 / heartbeat_hz, self._tick)
        self._executor = SingleThreadedExecutor(context=self._ctx)
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, name="hn_robot_state_ros", daemon=True)
        self._thread.start()

    @property
    def sent_count(self) -> int:
        return self._sent

    def publish(self, report: StatusReport) -> None:
        """새 보고를 넘깁니다. 상태가 바뀌었으면 즉시 발행하고, 아니면 heartbeat가 낼 때까지 보관만 합니다."""
        with self._lock:
            if self._closed:
                return
            self._latest = report
            if report.state != self._last_state:
                self._send(report)

    def _send(self, report: StatusReport) -> None:
        self._pub.publish(report_to_msg(report, self.robot_id, time.time_ns()))
        self._last_state = report.state
        self._sent += 1

    def _tick(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                stale = self._stale_provider() if self._stale_provider else None
            except Exception as e:   # noqa: BLE001  provider 오류가 heartbeat를 멈추게 하지 않음
                self.error, stale = e, None
            report = stale if stale is not None else self._latest
            if report is not None:
                self._send(report)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._timer.cancel()
        self._executor.shutdown()
        self._thread.join(timeout=2.0)
        self._node.destroy_node()
        self._ctx.try_shutdown()
