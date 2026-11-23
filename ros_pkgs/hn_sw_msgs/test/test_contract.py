# SPDX-License-Identifier: Apache-2.0
"""hn_sw_msgs 계약 시험. 빌드된 hn_sw_msgs가 있는 환경에서만 돕니다(rclpy 통신은 쓰지 않음).

채우지 않은 메시지(기본값 0·false)가 '정상·허용·실물·움직여라'로 읽히지 않는지 확인합니다.
번호를 바꾸거나 더할 때는 이 표와 README를 같이 고칩니다.
"""
import pytest

msgs = pytest.importorskip("hn_sw_msgs.msg")
srvs = pytest.importorskip("hn_sw_msgs.srv")


def constants(cls):
    return {k: getattr(cls, k) for k in dir(cls) if k.isupper() and isinstance(getattr(cls, k), int)}


def test_unfilled_messages_default_to_safe_side():
    assert msgs.Validity().value == msgs.Validity.UNAVAILABLE
    assert msgs.RunTarget().value == msgs.RunTarget.MOCK
    assert msgs.ControlMode().value == msgs.ControlMode.IDLE
    assert msgs.CommandStatus().value == msgs.CommandStatus.NONE
    assert msgs.JointCommand().mode == msgs.JointCommand.MODE_DAMP
    assert msgs.TargetResult().result == msgs.TargetResult.UNVISITED
    assert msgs.SafetyVerdict().allowed is False
    assert msgs.TeleopCmd().deadman is False
    assert msgs.DeviceFault().mcu_link == msgs.DeviceFault.LINK_UNKNOWN
    assert msgs.InspectionDetection().result == msgs.InspectionDetection.UNKNOWN


def test_request_mode_zero_is_not_a_request():
    assert 0 not in constants(srvs.RequestMode.Request).values()


def test_enum_numbers_are_fixed():
    assert constants(msgs.Validity) == {"UNAVAILABLE": 0, "VALID": 1, "STALE": 2, "INVALID": 3}
    assert constants(msgs.ControlMode) == {"IDLE": 0, "AUTO": 1, "TELEOP": 2, "PAUSED": 3, "ESTOP": 4, "ERROR": 5}
    assert constants(msgs.RunTarget) == {"MOCK": 0, "SIM": 1, "REAL": 2}
    assert constants(msgs.JointCommand) == {"MODE_DAMP": 0, "MODE_HOLD": 1, "MODE_CUT": 2, "MODE_ACTIVE": 3}
    assert constants(msgs.InspectionDetection) == {"UNKNOWN": 0, "NORMAL": 1, "ANOMALY": 2}
