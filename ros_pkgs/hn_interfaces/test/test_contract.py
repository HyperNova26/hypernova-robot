# SPDX-License-Identifier: Apache-2.0
"""메시지 번호 계약 시험. 번호는 앱이 분기하는 값이라 바뀌거나 재사용되면 안 됩니다(ADR-0004, ros_pkgs/hn_interfaces/README.md).

빌드된 hn_interfaces가 있는 환경(컨테이너)에서만 돕니다. rclpy 통신은 쓰지 않습니다.
번호를 일부러 바꾸는 경우(예: 새 번호 추가)에는 이 표를 같이 고치고, ADR을 거칩니다.
"""
import pytest

msgs = pytest.importorskip("hn_interfaces.msg")
srvs = pytest.importorskip("hn_interfaces.srv")

LOCALIZATION_STATUS = {          # S-005 코드 표(PR #24 대시보드 README)
    "STATUS_ACQUIRING": 0, "STATUS_TRACKING": 1, "STATUS_DEGRADED": 2,
    "STATUS_LOST": 3, "STATUS_STALE_INPUT": 4, "STATUS_INPUT_TIMEOUT": 5,
}
INJECT_FAULT_KINDS = {           # 시뮬레이터 하네스(policies/route_walk/state_scenarios.py)가 받는 값
    "KIND_COLLAPSE": "collapse", "KIND_FLIP": "flip", "KIND_STALE": "stale", "KIND_TILT": "tilt", "KIND_PUSH": "push",
    "KIND_CLEAR": "clear", "KIND_RESET": "reset",
}
LOCOMOTION_STATUS = {            # ADR-0004
    "CODE_INITIALIZING": 0, "CODE_STANDING": 1, "CODE_WALKING": 2, "CODE_TILTING": 3,
    "CODE_SLIPPING": 4, "CODE_FALLEN": 5, "CODE_STALE_INPUT": 6,
    "SEVERITY_OK": 0, "SEVERITY_WARN": 1, "SEVERITY_ERROR": 2, "SEVERITY_STALE": 3,
}


def constants(cls):
    return {k: getattr(cls, k) for k in dir(cls) if k.isupper() and isinstance(getattr(cls, k), int)}


def test_localization_status_numbers_are_fixed():
    assert constants(msgs.LocalizationStatus) == LOCALIZATION_STATUS


def test_locomotion_status_numbers_are_fixed():
    assert constants(msgs.LocomotionStatus) == LOCOMOTION_STATUS


def test_localization_status_layout_matches_dashboard_assumption():
    """S-006 대시보드(PR #24)는 header와 정수 필드 `status`를 읽습니다. 이 둘이 바뀌면 대시보드가 상태를 못 읽습니다.
    나머지는 LIO 어댑터가 채우는 S-005 v0 필드입니다."""
    fields = msgs.LocalizationStatus.get_fields_and_field_types()
    assert list(fields)[:2] == ["header", "status"]
    assert fields == {"header": "std_msgs/Header", "status": "uint8", "status_text": "string",
                      "pose_accepted": "boolean", "source": "string", "latency_ms": "float",
                      "fitness": "float", "rmse_m": "float", "detail_json": "string"}


def test_inject_fault_kinds_and_fields():
    req, res = srvs.InjectFault.Request, srvs.InjectFault.Response
    kinds = {k: getattr(req, k) for k in dir(req) if k.startswith("KIND_")}
    assert kinds == INJECT_FAULT_KINDS
    assert req.get_fields_and_field_types() == {"kind": "string", "magnitude": "double", "duration_s": "double",
                                                "direction_deg": "double"}
    assert res.get_fields_and_field_types() == {"accepted": "boolean", "message": "string", "sim_time_s": "double"}
