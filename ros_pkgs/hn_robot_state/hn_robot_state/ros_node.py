# SPDX-License-Identifier: Apache-2.0
"""ROS 2 어댑터(G-006): 판정 보고(StatusReport)를 hn_interfaces/LocomotionStatus로 발행합니다. 판정은 하지 않습니다(core.py의 일).

토픽 /locomotion/status, 타입 hn_interfaces/msg/LocomotionStatus(ros_pkgs/hn_interfaces). QoS는 reliable + transient_local + KEEP_LAST 1이라 늦게 붙은 구독자도 마지막 상태를 받습니다.
hn_interfaces는 colcon으로 한 번 빌드해야 import됩니다(docs/interfaces/locomotion-status.md).
발행 시점: 상태가 바뀌면 즉시, 그 밖에는 heartbeat(기본 10 Hz)로 마지막 보고를 다시 냅니다. 입력이 끊기면(stale_provider가 보고를 돌려주면) heartbeat가 그것을 냅니다.

시간 규칙(ROS 시계와 시뮬레이터 시계가 어긋나는 문제를 피하려고)
  - header.stamp는 node 시계가 아니라 기본적으로 time.time_ns()(시스템 시간)입니다(ADR-0004). 시뮬레이션 시간은 sim_time_s 필드로 따로 싣습니다.
    stamp_ns를 주면 그 함수가 보고마다 stamp를 정합니다(시뮬레이터가 /clock을 낼 때 시뮬레이션 시간을 stamp로 쓰는 선택지. 기본값은 바꾸지 않음).
  - node는 use_sim_time=False를 강제합니다. true인데 /clock이 없거나 시뮬레이터가 멈추면 ROS 시계가 멈추고 timer(heartbeat)가 돌지 않아,
    입력이 끊겼을 때 STALE_INPUT을 낼 수 없습니다. heartbeat는 항상 wall 시간으로 돕니다.
  - 전용 rclpy Context와 전용 스레드를 씁니다. 같은 프로세스의 다른 rclpy 사용(예: Isaac Sim의 ROS 확장)과 전역 상태를 공유하지 않습니다.
rclpy가 있는 환경에서만 import할 수 있습니다(패키지 __init__은 이 모듈을 import하지 않음).

값을 알 수 없는 실수 필드(측정값)는 NaN으로 싣습니다. uint8 필드(code, severity)는 rclpy에서 int입니다.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Callable, Optional

import rclpy
from builtin_interfaces.msg import Time
from hn_interfaces.msg import LocomotionStatus
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from .core import State, StatusReport

DEFAULT_TOPIC = "/locomotion/status"
QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                 history=HistoryPolicy.KEEP_LAST, depth=1)
_FEATURES = ("tilt_deg", "roll_deg", "pitch_deg", "speed_mps", "height_m")   # LocomotionStatus의 측정값 필드(이름이 같음)


def report_to_msg(report: StatusReport, robot_id: str, stamp_ns: int) -> LocomotionStatus:
    """보고 하나를 메시지로 바꿉니다(ROS 통신 없이 시험할 수 있는 순수 변환)."""
    msg = LocomotionStatus()
    msg.header.stamp = Time(sec=int(stamp_ns // 1_000_000_000), nanosec=int(stamp_ns % 1_000_000_000))
    msg.header.frame_id = ""
    msg.code = int(report.code)
    msg.state = report.name
    msg.severity = int(report.severity)
    msg.reason = report.reason
    msg.since_s = float(report.since_s)
    msg.robot_id = robot_id
    msg.sim_time_s = float(report.t)
    for k in _FEATURES:
        v = report.features.get(k)
        setattr(msg, k, math.nan if v is None else float(v))
    return msg


class StatusPublisher:
    """보고를 발행하는 어댑터. publish()는 판정 스레드에서, heartbeat는 내부 스레드에서 돕니다.

    stale_provider: 호출하면 "입력이 끊겼을 때의 보고"(StatusReport)나 None을 돌려주는 함수(heartbeat 스레드에서 불림).
    stamp_ns: 보고를 받아 header.stamp [ns]를 돌려주는 함수. None이면 시스템 시간(time.time_ns()).
    """

    def __init__(self, *, topic: str = DEFAULT_TOPIC, robot_id: str = "hn_v1_hyper", heartbeat_hz: float = 10.0,
                 stale_provider: Optional[Callable[[], Optional[StatusReport]]] = None, node_name: str = "hn_robot_state",
                 context_args: Optional[list[str]] = None, stamp_ns: Optional[Callable[[StatusReport], int]] = None):
        if not heartbeat_hz > 0:
            raise ValueError("heartbeat_hz는 0보다 커야 합니다")
        self.robot_id = robot_id
        self.error: Optional[BaseException] = None        # stale_provider 등에서 난 마지막 예외(발행은 계속함)
        self._stale_provider = stale_provider
        self._stamp_ns = stamp_ns or (lambda _report: time.time_ns())
        self._lock = threading.Lock()
        self._latest: Optional[StatusReport] = None
        self._last_state: Optional[State] = None
        self._sent = 0
        self._closed = False
        self._ctx = Context()
        rclpy.init(args=list(context_args or []), context=self._ctx)       # args=None이면 sys.argv를 해석하므로 항상 명시
        self._node = Node(node_name, context=self._ctx, enable_rosout=False, start_parameter_services=False,
                          parameter_overrides=[Parameter("use_sim_time", Parameter.Type.BOOL, False)])
        self._pub = self._node.create_publisher(LocomotionStatus, topic, QOS)
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
        self._pub.publish(report_to_msg(report, self.robot_id, self._stamp_ns(report)))
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
