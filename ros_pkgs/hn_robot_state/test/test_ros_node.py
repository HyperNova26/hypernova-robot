# SPDX-License-Identifier: Apache-2.0
"""hn_robot_state.ros_node 시험. rclpy가 있는 환경(컨테이너)에서만 돕니다. 같은 프로세스 안의 발행·구독으로 시험합니다."""
import os
import threading
import time
import uuid

os.environ.setdefault("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST")   # 다른 PC와 섞이지 않게(rclpy를 부르기 전에 정해야 함)

import pytest

rclpy = pytest.importorskip("rclpy")
pytest.importorskip("diagnostic_msgs.msg")

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus  # noqa: E402
from rclpy.context import Context  # noqa: E402
from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy  # noqa: E402

from hn_robot_state import State, StatusReport  # noqa: E402
from hn_robot_state.ros_node import STATUS_NAME, StatusPublisher, report_to_msg  # noqa: E402


def make_report(state=State.WALKING, t=12.34, since_s=1.5, reason="moving", **features):
    base = {"tilt_deg": 3.14159, "roll_deg": -1.0, "pitch_deg": 2.0, "speed_mps": 0.5, "height_m": 0.3, "h0_m": 0.3}
    base.update(features)
    return StatusReport(t=t, state=state, reason=reason, since_s=since_s, features=base)


def new_topic():
    return "/hn_test_" + uuid.uuid4().hex[:10] + "/status"


class Listener:
    """시험용 구독자(전용 context·스레드)."""

    def __init__(self, topic, durability=DurabilityPolicy.TRANSIENT_LOCAL):
        self.ctx = Context()
        rclpy.init(args=[], context=self.ctx)
        self.node = Node("probe_" + uuid.uuid4().hex[:8], context=self.ctx, enable_rosout=False, start_parameter_services=False)
        self.msgs = []
        qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=durability, history=HistoryPolicy.KEEP_LAST, depth=100)
        self.node.create_subscription(DiagnosticArray, topic, lambda m: self.msgs.append((time.monotonic(), m)), qos)
        self.executor = SingleThreadedExecutor(context=self.ctx)
        self.executor.add_node(self.node)
        threading.Thread(target=self.executor.spin, daemon=True).start()

    def wait_for(self, predicate, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for t, m in list(self.msgs):
                if predicate(m):
                    return t, m
            time.sleep(0.02)
        return None

    def close(self):
        self.executor.shutdown()
        self.node.destroy_node()
        self.ctx.try_shutdown()


def values(msg):
    return {kv.key: kv.value for kv in msg.status[0].values}


@pytest.fixture
def cleanup():
    items = []
    yield items.append
    for obj in reversed(items):
        obj.close()


# ---------------------------------------------------------------------- 변환(통신 없음)
def test_report_to_msg_fields_and_levels():
    stamp = 1_700_000_000_123_456_789
    msg = report_to_msg(make_report(State.FALLEN, reason="tilt"), "hn_v0_go2", stamp)
    st = msg.status[0]
    assert len(msg.status) == 1 and msg.header.frame_id == ""
    assert (msg.header.stamp.sec, msg.header.stamp.nanosec) == (1_700_000_000, 123_456_789)
    assert st.level == DiagnosticStatus.ERROR and st.level == b"\x02"         # rclpy의 byte는 bytes
    assert (st.name, st.message, st.hardware_id) == (STATUS_NAME, "FALLEN", "hn_v0_go2")
    v = values(msg)
    assert v["code"] == "5" and v["state"] == "FALLEN" and v["reason"] == "tilt"
    assert v["since_s"] == "1.50" and v["sim_t"] == "12.34"
    assert v["tilt_deg"] == "3.142" and v["height_m"] == "0.300"
    assert "h0_m" not in v                                                       # 계획한 키만 싣는다
    assert report_to_msg(make_report(State.STANDING), "r", 0).status[0].level == DiagnosticStatus.OK
    assert report_to_msg(make_report(State.STALE_INPUT, reason="no_input"), "r", 0).status[0].level == DiagnosticStatus.STALE


def test_report_to_msg_omits_missing_values():
    msg = report_to_msg(make_report(height_m=None), "r", 0)
    assert "height_m" not in values(msg) and "tilt_deg" in values(msg)


# ---------------------------------------------------------------------- 발행·구독
def test_first_report_is_published_and_heartbeat_repeats(cleanup):
    topic = new_topic()
    pub = StatusPublisher(topic=topic, heartbeat_hz=10.0)
    cleanup(pub)
    sub = Listener(topic)
    cleanup(sub)
    pub.publish(make_report(State.WALKING))
    assert sub.wait_for(lambda m: values(m)["code"] == "2", 5.0) is not None
    n0 = len(sub.msgs)
    time.sleep(1.0)
    assert 7 <= len(sub.msgs) - n0 <= 14                                          # 10 Hz heartbeat


def test_state_change_is_published_immediately_not_by_heartbeat(cleanup):
    topic = new_topic()
    pub = StatusPublisher(topic=topic, heartbeat_hz=0.5)                          # heartbeat 주기 2 s
    cleanup(pub)
    sub = Listener(topic)
    cleanup(sub)
    pub.publish(make_report(State.WALKING))
    assert sub.wait_for(lambda m: values(m)["code"] == "2", 5.0) is not None
    t0 = time.monotonic()
    pub.publish(make_report(State.FALLEN, reason="tilt"))
    got = sub.wait_for(lambda m: values(m)["code"] == "5", 1.0)
    assert got is not None and got[0] - t0 < 0.5                                  # 다음 heartbeat(최대 2 s)를 기다리지 않음
    assert got[1].status[0].level == b"\x02"


def test_same_state_is_not_republished_until_heartbeat(cleanup):
    topic = new_topic()
    pub = StatusPublisher(topic=topic, heartbeat_hz=0.2)                          # 5 s
    cleanup(pub)
    for i in range(20):
        pub.publish(make_report(State.WALKING, t=i * 0.02))
    assert pub.sent_count == 1                                                    # 상태가 같으면 50 Hz로 들어와도 한 번만 발행


def test_late_joiner_gets_latest_state_only_with_transient_local(cleanup):
    topic = new_topic()
    pub = StatusPublisher(topic=topic, heartbeat_hz=0.2)                          # heartbeat가 5 s 뒤라 래치만 관찰됨
    cleanup(pub)
    early = Listener(topic)
    cleanup(early)
    pub.publish(make_report(State.FALLEN, reason="tilt"))
    assert early.wait_for(lambda m: values(m)["code"] == "5", 5.0) is not None
    time.sleep(1.0)
    late = Listener(topic, DurabilityPolicy.TRANSIENT_LOCAL)
    volatile = Listener(topic, DurabilityPolicy.VOLATILE)
    cleanup(late)
    cleanup(volatile)
    assert late.wait_for(lambda m: values(m)["code"] == "5", 2.0) is not None
    assert volatile.wait_for(lambda m: True, 1.5) is None


def test_stale_provider_is_published_by_heartbeat_and_recovers(cleanup):
    topic = new_topic()
    flag = {"stale": False}
    stale_report = make_report(State.STALE_INPUT, reason="no_input", since_s=0.7)
    pub = StatusPublisher(topic=topic, heartbeat_hz=10.0, stale_provider=lambda: stale_report if flag["stale"] else None)
    cleanup(pub)
    sub = Listener(topic)
    cleanup(sub)
    pub.publish(make_report(State.WALKING))
    assert sub.wait_for(lambda m: values(m)["code"] == "2", 5.0) is not None
    flag["stale"] = True
    got = sub.wait_for(lambda m: values(m)["code"] == "6", 1.0)
    assert got is not None and got[1].status[0].level == b"\x03" and values(got[1])["reason"] == "no_input"
    flag["stale"] = False
    n = len(sub.msgs)                                                              # 이 뒤에 온 메시지만 본다(이전 WALKING 메시지와 구분)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not any(values(m)["code"] == "2" for _, m in sub.msgs[n:]):
        time.sleep(0.02)
    assert any(values(m)["code"] == "2" for _, m in sub.msgs[n:])                  # 입력이 돌아오면 마지막 정상 보고로 복귀


def test_stamp_is_wall_time_and_heartbeat_runs_even_if_use_sim_time_true(cleanup):
    topic = new_topic()
    pub = StatusPublisher(topic=topic, heartbeat_hz=10.0, context_args=["--ros-args", "-p", "use_sim_time:=true"])
    cleanup(pub)
    sub = Listener(topic)
    cleanup(sub)
    pub.publish(make_report(State.WALKING))
    got = sub.wait_for(lambda m: True, 5.0)
    assert got is not None
    stamp_ns = got[1].header.stamp.sec * 1_000_000_000 + got[1].header.stamp.nanosec
    assert abs(stamp_ns - time.time_ns()) < 5_000_000_000                         # 0에 멈춘 ROS 시계가 아니라 시스템 시간
    n0 = len(sub.msgs)
    time.sleep(0.6)
    assert len(sub.msgs) - n0 >= 3                                                # /clock 없이도 heartbeat(timer)가 돎


def test_provider_exception_keeps_publisher_alive(cleanup):
    topic = new_topic()

    def boom():
        raise RuntimeError("provider failed")

    pub = StatusPublisher(topic=topic, heartbeat_hz=10.0, stale_provider=boom)
    cleanup(pub)
    sub = Listener(topic)
    cleanup(sub)
    pub.publish(make_report(State.WALKING))
    assert sub.wait_for(lambda m: values(m)["code"] == "2", 5.0) is not None
    n0 = len(sub.msgs)
    time.sleep(0.5)
    assert len(sub.msgs) - n0 >= 3 and isinstance(pub.error, RuntimeError)


def test_close_is_idempotent_and_stops_publishing():
    topic = new_topic()
    pub = StatusPublisher(topic=topic, heartbeat_hz=10.0)
    sub = Listener(topic)
    try:
        pub.publish(make_report(State.WALKING))
        assert sub.wait_for(lambda m: True, 5.0) is not None
        pub.close()
        pub.close()
        n = len(sub.msgs)
        pub.publish(make_report(State.FALLEN))                                    # 닫힌 뒤에는 무시
        time.sleep(0.5)
        assert len(sub.msgs) == n
    finally:
        sub.close()


def test_invalid_heartbeat_rate():
    with pytest.raises(ValueError):
        StatusPublisher(topic=new_topic(), heartbeat_hz=0)
