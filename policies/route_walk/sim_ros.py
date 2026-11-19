# SPDX-License-Identifier: Apache-2.0
"""시뮬레이터 쪽 ROS 2 연결(시험 하네스용). /clock을 발행하고 고장 주입 서비스 /sim/inject_fault를 제공합니다.

세 재생기(MuJoCo, Isaac Sim, Isaac Lab)를 감싸는 policies/route_walk/state_scenarios.py가 만들어 씁니다. 실기에는 없습니다.
  - /clock(rosgraph_msgs/Clock): 정책 스텝(50 Hz)마다 시뮬레이션 시간을 냅니다. 세 시뮬레이터가 같은 방식으로 냅니다.
    use_sim_time=true인 노드(예: Nav2, RViz)가 이 시간을 따릅니다. 이 노드 자신은 use_sim_time=False입니다(timer를 쓰지 않음).
  - /sim/inject_fault(hn_interfaces/srv/InjectFault): 요청을 검사해 접수만 하고(on_request), 적용은 시뮬레이션 루프가 다음 스텝에 합니다.
전용 rclpy Context와 전용 스레드를 씁니다(hn_robot_state.ros_node.StatusPublisher와 같은 방식). rclpy와 빌드된 hn_interfaces가 필요합니다.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile
from rosgraph_msgs.msg import Clock

try:
    from hn_interfaces.srv import InjectFault
except ImportError as e:   # 메시지 패키지를 아직 빌드하지 않음
    raise ImportError("hn_interfaces를 import하지 못했습니다. 컨테이너에서 한 번 빌드하십시오: "
                      "./docker/hn sim bash -c 'unset VIRTUAL_ENV && colcon build --base-paths ros_pkgs'") from e

FAULT_SERVICE = "/sim/inject_fault"
CLOCK_TOPIC = "/clock"


class SimRos:
    """on_request(kind, magnitude, duration_s, direction_deg) -> (accepted, message)는 서비스 스레드에서 불립니다(스레드 안전하게 접수만 할 것).
    sim_time()은 응답에 실을 현재 시뮬레이션 시간을 돌려줍니다."""

    def __init__(self, *, on_request: Callable[..., tuple[bool, str]], sim_time: Callable[[], float],
                 clock: bool = True, service: Optional[str] = FAULT_SERVICE, node_name: str = "hn_sim"):
        self._on_request, self._sim_time = on_request, sim_time
        self._closed = False
        self._lock = threading.Lock()
        self.requests = 0
        self._ctx = Context()
        rclpy.init(args=[], context=self._ctx)       # args=None이면 sys.argv를 해석하므로 항상 명시
        self._node = Node(node_name, context=self._ctx, enable_rosout=False, start_parameter_services=False,
                          parameter_overrides=[Parameter("use_sim_time", Parameter.Type.BOOL, False)])
        self._clock_pub = self._node.create_publisher(Clock, CLOCK_TOPIC, QoSProfile(depth=10)) if clock else None
        self._srv = self._node.create_service(InjectFault, service, self._handle) if service else None
        self._executor = SingleThreadedExecutor(context=self._ctx)
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, name="hn_sim_ros", daemon=True)
        self._thread.start()

    def _handle(self, req, res):
        self.requests += 1
        try:
            res.accepted, res.message = self._on_request(req.kind.strip().lower(), float(req.magnitude), float(req.duration_s),
                                                         direction_deg=float(req.direction_deg))
        except Exception as e:   # noqa: BLE001  잘못된 요청 하나로 서비스가 멈추지 않게
            res.accepted, res.message = False, f"오류: {e!r}"
        res.sim_time_s = float(self._sim_time())
        return res

    def publish_clock(self, t_sim: float) -> None:
        if self._clock_pub is None:
            return
        with self._lock:
            if self._closed:
                return
            ns = int(round(max(t_sim, 0.0) * 1e9))
            msg = Clock()
            msg.clock.sec, msg.clock.nanosec = ns // 1_000_000_000, ns % 1_000_000_000
            self._clock_pub.publish(msg)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown()
        self._thread.join(timeout=2.0)
        self._node.destroy_node()
        self._ctx.try_shutdown()
