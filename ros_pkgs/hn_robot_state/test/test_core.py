# SPDX-License-Identifier: Apache-2.0
"""hn_robot_state.core 단위 시험. 합성 신호만 씁니다(시뮬레이터·ROS 불필요). 정책 주기 50 Hz(DT=0.02 s) 기준입니다."""
import json
import math

import numpy as np
import pytest

from hn_robot_state import (DEFAULT_CONFIG_PATH, Severity, State, StateEstimator, StaleWatchdog, Thresholds,
                            load_thresholds)

DT = 0.02
H0 = 0.30            # 시험용 서 있는 높이 [m]
NX, NY = 17, 11      # policy_io.yaml의 height scan 격자


def gravity(roll_deg=0.0, pitch_deg=0.0, yaw_deg=0.0):
    """회전행렬에서 만든 projected gravity(base 프레임). 판정기의 공식과 독립입니다. R = Rz·Ry·Rx (body -> world)."""
    r, p, y = (math.radians(a) for a in (roll_deg, pitch_deg, yaw_deg))
    rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    return (rz @ ry @ rx).T @ np.array([0.0, 0.0, -1.0])


def make_state(*, roll=0.0, pitch=0.0, speed=0.0, vz=0.0, cmd=(0.0, 0.0, 0.0), height=H0, ground=True, base_z=1.0, scan=True):
    s = {"projected_gravity_b": gravity(roll, pitch), "base_lin_vel_b": np.array([speed, 0.0, vz]),
         "command": np.array(cmd, dtype=float), "joint_pos": np.zeros(12), "joint_vel": np.zeros(12)}   # 마지막 둘은 무시되어야 함
    if scan:
        s["height_hits_z"] = np.full(NX * NY, base_z - height if ground else 1.0e3)
        s["base_pos_z"] = np.array([base_z])
    return s


class Driver:
    """판정기에 50 Hz로 같은 상태를 계속 넣는 시험 도구."""

    def __init__(self, est=None):
        self.est = est or StateEstimator()
        self.t = 0.0
        self.last = None

    def run(self, seconds, **kw):
        out = []
        for _ in range(int(round(seconds / DT))):
            self.t += DT
            self.last = self.est.update(make_state(**kw), self.t)
            out.append(self.last)
        return out


def first_time(reports, state):
    return next((r.t for r in reports if r.state == state), None)


def standing_driver():
    d = Driver()
    d.run(1.2)
    assert d.last.state == State.STANDING
    return d


# ---------------------------------------------------------------------- 기울기·롤·피치
@pytest.mark.parametrize("roll,pitch", [(0, 0), (30, 0), (0, 30), (20, -25), (-45, 10), (0, 85), (170, 0)])
@pytest.mark.parametrize("yaw", [0.0, 123.0])
def test_tilt_roll_pitch_from_gravity(roll, pitch, yaw):
    s = make_state()
    s["projected_gravity_b"] = gravity(roll, pitch, yaw)
    f = StateEstimator().update(s, 0.0).features
    assert f["tilt_deg"] == pytest.approx(math.degrees(math.acos(math.cos(math.radians(roll)) * math.cos(math.radians(pitch)))), abs=1e-6)
    assert f["roll_deg"] == pytest.approx(roll, abs=1e-6)
    assert f["pitch_deg"] == pytest.approx(pitch, abs=1e-6)


def test_upside_down_tilt_is_180():
    s = make_state()
    s["projected_gravity_b"] = np.array([0.0, 0.0, 1.0])
    assert StateEstimator().update(s, 0.0).features["tilt_deg"] == pytest.approx(180.0)


# ---------------------------------------------------------------------- 초기화
def test_init_then_standing_and_h0_calibrated():
    d = Driver()
    r = d.run(0.9)
    assert all(x.state == State.INITIALIZING and x.reason == "calibrating" for x in r)
    d.run(0.3)
    assert d.last.state == State.STANDING and d.last.reason == "idle"
    assert d.last.features["h0_m"] == pytest.approx(H0)
    assert d.last.severity == Severity.OK and d.last.code == 1


def test_init_restarts_when_unstable():
    d = Driver()
    d.run(0.8)
    d.run(0.04, vz=1.0)                       # 아직 떨어지는 중: 안정 구간이 끊김
    assert d.run(0.9)[-1].state == State.INITIALIZING
    assert d.run(0.2)[-1].state == State.STANDING


def test_init_ends_in_walking_when_commanded():
    d = Driver()
    d.run(1.3, cmd=(0.5, 0.0, 0.0), speed=0.5)
    assert d.last.state == State.WALKING and d.last.reason == "moving"


# ---------------------------------------------------------------------- 정지/보행
def test_standing_to_walking_and_back_with_dwell():
    d = standing_driver()
    t0 = d.t
    r = d.run(0.3, cmd=(0.5, 0.0, 0.0), speed=0.5)
    assert 0.10 <= first_time(r, State.WALKING) - t0 <= 0.14        # walk_dwell_s 0.1
    assert d.run(0.4, cmd=(0.0, 0.0, 0.0), speed=0.0)[-1].state == State.WALKING   # stand_dwell_s 0.5 전
    assert d.run(0.2, cmd=(0.0, 0.0, 0.0), speed=0.0)[-1].state == State.STANDING


def test_hysteresis_band_keeps_state():
    d = standing_driver()
    assert all(x.state == State.STANDING for x in d.run(2.0, speed=0.12))       # stand(0.10)와 walk(0.15) 사이
    d.run(0.5, cmd=(0.5, 0.0, 0.0), speed=0.5)
    assert d.last.state == State.WALKING
    assert all(x.state == State.WALKING for x in d.run(2.0, speed=0.12))


def test_turning_in_place_is_walking():
    d = standing_driver()
    d.run(0.5, cmd=(0.0, 0.0, 0.5))
    assert d.last.state == State.WALKING


# ---------------------------------------------------------------------- 기울어짐(TILTING)
def test_tilting_after_debounce_then_clears_back_to_motion_state():
    d = standing_driver()
    t0 = d.t
    r = d.run(1.0, roll=50)                                          # 경고 35° 초과, 낙상 70° 미만
    assert 0.30 <= first_time(r, State.TILTING) - t0 <= 0.36         # tilt_enter_s 0.3
    assert (d.last.reason, d.last.severity, d.last.code) == ("tilt", Severity.WARN, 3)
    assert d.run(1.0, roll=32)[-1].state == State.TILTING            # 해제 기준(30°)보다 크면 유지(히스테리시스)
    t1 = d.t
    r = d.run(1.0, roll=10)
    assert 0.50 <= first_time(r, State.STANDING) - t1 <= 0.56        # tilt_clear_s 0.5 뒤 정지/보행 판정으로 복귀
    d.run(0.4, pitch=-45, speed=0.5, cmd=(0.5, 0.0, 0.0))            # 앞뒤 기울기도 같음
    assert d.last.state == State.TILTING
    assert d.run(1.0, speed=0.5, cmd=(0.5, 0.0, 0.0))[-1].state == State.WALKING


def test_brief_tilt_over_warning_is_ignored():
    d = standing_driver()
    assert all(r.state == State.STANDING for r in d.run(0.2, roll=50) + d.run(1.0))


def test_tilting_then_fall_has_priority_and_recovery_skips_tilting():
    d = standing_driver()
    d.run(1.0, roll=45)
    assert d.last.state == State.TILTING
    r = d.run(0.5, roll=80)
    assert State.FALLEN in {x.state for x in r} and d.last.reason == "tilt"
    r = d.run(1.5, roll=20)                                          # 해제(25° 미만 1 s) 뒤 바로 정지 판정, TILTING을 거치지 않음
    assert d.last.state == State.STANDING and State.TILTING not in {x.state for x in r}


def test_tilt_during_initialization_does_not_report_tilting():
    d = Driver()
    r = d.run(2.0, roll=50)
    assert {x.state for x in r} == {State.INITIALIZING}


# ---------------------------------------------------------------------- 낙상
def test_brief_tilt_spike_is_ignored():
    d = standing_driver()
    reports = d.run(0.1, roll=80) + d.run(1.0)
    assert all(r.state != State.FALLEN for r in reports)


def test_fall_by_tilt_after_debounce_and_latch_recovery():
    d = standing_driver()
    t0 = d.t
    r = d.run(0.5, roll=80)
    assert 0.20 <= first_time(r, State.FALLEN) - t0 <= 0.26          # fall_enter_s 0.2
    assert d.last.state == State.FALLEN and d.last.reason == "tilt"
    assert d.last.severity == Severity.ERROR and d.last.code == 5
    assert d.run(0.9)[-1].state == State.FALLEN                      # 일어서도 recover_s(1.0) 전에는 래치
    assert d.run(0.3)[-1].state == State.STANDING                    # h0를 알고 있으므로 바로 분류


def test_fall_stays_latched_while_still_tilted():
    d = standing_driver()
    d.run(0.5, roll=80)
    assert d.run(3.0, roll=40)[-1].state == State.FALLEN             # 25°(해제 기준)보다 기울어 있으면 해제 안 됨


def test_fall_by_low_height():
    d = standing_driver()
    d.run(0.5, height=0.10)                                           # h0의 50%(0.15)보다 낮음, 자세는 직립
    assert d.last.state == State.FALLEN and d.last.reason == "low_height"


def test_low_height_with_nominal_height_works_from_the_start():
    d = Driver(StateEstimator(Thresholds(nominal_height_m=H0)))
    d.run(0.5, height=0.10)
    assert d.last.state == State.FALLEN and d.last.reason == "low_height"


def test_fall_by_off_ground_then_recalibrates():
    d = Driver()
    d.run(0.5, ground=False)                                          # 초기화 중에도 지면 없음은 낙상
    assert d.last.state == State.FALLEN and d.last.reason == "off_ground"
    assert d.run(1.3)[-1].state == State.INITIALIZING                 # 지면이 돌아오면 h0를 다시 잼
    assert d.run(1.1)[-1].state == State.STANDING


def test_without_height_input_uses_tilt_only():
    d = Driver()
    d.run(1.2, scan=False)
    assert d.last.state == State.STANDING
    assert d.last.features["height_m"] is None and d.last.features["h0_m"] is None
    d.run(0.5, roll=80, scan=False)
    assert d.last.state == State.FALLEN and d.last.reason == "tilt"
    assert d.run(1.2, scan=False)[-1].state == State.STANDING


def test_height_uses_center_block_median_and_valid_fraction():
    est = StateEstimator()
    s = make_state()
    hits = np.asarray(s["height_hits_z"]).reshape(NY, NX)
    hits[:, :6] = 1.0e3                                               # 중심 블록 밖은 무시되어야 함
    hits[4:7, 7:10] = 0.7                                             # 중심 3x3 블록: base_z(1.0) - 0.7 = 0.3
    hits[4, 7:10] = 1.0e3                                             # 9칸 중 3칸 무효 -> 6/9 유효
    s["height_hits_z"] = hits.ravel()
    f = est.update(s, 0.0).features
    assert f["ground_ok"] is True and f["height_m"] == pytest.approx(0.3)
    hits[5, 7:10] = float("inf")                                      # 무효 6칸 -> 3/9 유효(< 0.5)
    s["height_hits_z"] = hits.ravel()
    f = StateEstimator().update(s, 0.0).features
    assert f["ground_ok"] is False and f["height_m"] is None


# ---------------------------------------------------------------------- 시간 처리
def test_time_going_backwards_resets():
    d = standing_driver()
    r = d.est.update(make_state(), 0.5)
    assert r.state == State.INITIALIZING and r.since_s == 0.0


def test_large_gap_restarts_pending_timers_but_keeps_state():
    d = standing_driver()
    d.run(0.15, roll=80)                                              # 낙상 후보 0.15 s (< 0.2)
    d.t += 1.0                                                        # 입력 공백(> max_dt_s)
    assert all(r.state != State.FALLEN for r in d.run(0.15, roll=80))  # 후보가 새로 시작되어 아직 0.15 s

    d = standing_driver()
    d.run(0.5, roll=80)
    assert d.last.state == State.FALLEN
    d.run(0.8)                                                        # 해제 후보 0.8 s
    d.t += 1.0
    assert d.run(0.5)[-1].state == State.FALLEN                       # 공백 뒤 다시 시작: 0.5 s < recover_s
    assert d.run(0.6)[-1].state == State.STANDING


def test_stale_watchdog():
    class Clock:
        now = 0.0

    c = Clock()
    w = StaleWatchdog(0.5, clock=lambda: c.now)
    c.now = 100.0
    assert w.silent_s() is None and not w.is_stale()                  # 첫 입력 전에는 끊김이 아님
    w.feed()
    c.now = 100.4
    assert not w.is_stale()
    c.now = 100.6
    assert w.is_stale() and w.silent_s() == pytest.approx(0.6)
    w.feed()
    assert not w.is_stale()
    w.reset()
    assert w.silent_s() is None
    with pytest.raises(ValueError):
        StaleWatchdog(0.0)


def test_stale_report_does_not_change_estimator():
    d = standing_driver()
    rep = d.est.stale_report(t=99.0, silent_s=0.7)
    assert rep.state == State.STALE_INPUT and rep.severity == Severity.STALE and rep.code == 6
    assert rep.reason == "no_input" and rep.since_s == 0.7 and rep.features["tilt_deg"] == pytest.approx(0.0)
    assert d.run(0.1)[-1].state == State.STANDING                     # 입력이 돌아오면 판정은 그대로 이어짐


# ---------------------------------------------------------------------- 입력 검증
@pytest.mark.parametrize("mutate", [
    lambda s: s.pop("projected_gravity_b"),
    lambda s: s.__setitem__("projected_gravity_b", np.array([0.0, np.nan, -1.0])),
    lambda s: s.__setitem__("projected_gravity_b", np.array([0.0, -1.0])),
    lambda s: s.__setitem__("projected_gravity_b", np.zeros(3)),
    lambda s: s.__setitem__("base_lin_vel_b", np.array([np.inf, 0.0, 0.0])),
    lambda s: s.__setitem__("command", np.zeros(2)),
    lambda s: s.__setitem__("height_hits_z", np.zeros(5)),
])
def test_invalid_input_raises_and_does_not_corrupt_state(mutate):
    est = StateEstimator()
    s = make_state()
    mutate(s)
    with pytest.raises(ValueError):
        est.update(s, 5.0)                                             # 성공 호출과 시간을 다르게 해서 오염되면 드러나게 함
    r = est.update(make_state(), 0.0)                                  # 실패한 호출이 상태를 바꾸지 않았음
    assert r.state == State.INITIALIZING and r.since_s == 0.0
    with pytest.raises(ValueError):
        est.update(make_state(), float("nan"))


def test_input_types_lists_float32_scalars():
    ref = StateEstimator().update(make_state(), 0.0).features
    s = {"projected_gravity_b": [0, 0, -1], "base_lin_vel_b": [0, 0, 0], "command": [0, 0, 0],
         "height_hits_z": [1.0 - H0] * (NX * NY), "base_pos_z": 1.0}
    assert StateEstimator().update(s, 0.0).features["height_m"] == pytest.approx(ref["height_m"])
    s32 = {k: np.asarray(v, dtype=np.float32) for k, v in make_state().items()}
    f = StateEstimator().update(s32, 0.0).features
    assert f["height_m"] == pytest.approx(H0, abs=1e-5) and f["tilt_deg"] == pytest.approx(0.0, abs=1e-3)


def test_report_is_json_serializable():
    d = standing_driver()
    text = json.dumps(d.last.to_dict())
    back = json.loads(text)
    assert back["state"] == "STANDING" and back["code"] == 1 and back["features"]["h0_m"] == pytest.approx(H0)
    json.dumps(d.est.stale_report(1.0, 0.6).to_dict())


# ---------------------------------------------------------------------- 코드·설정
def test_state_codes_and_severity_values():
    assert {s.name: int(s) for s in State} == {"INITIALIZING": 0, "STANDING": 1, "WALKING": 2, "TILTING": 3, "FALLEN": 5,
                                               "STALE_INPUT": 6}
    assert [int(x) for x in Severity] == [0, 1, 2, 3]
    try:
        from diagnostic_msgs.msg import DiagnosticStatus
    except ImportError:
        pytest.skip("diagnostic_msgs 없음(ROS를 source하지 않은 환경)")
    # rclpy는 byte 상수를 bytes(b'\x00')로 돌려주므로 정수로 바꿔 비교합니다
    ros = tuple(c[0] for c in (DiagnosticStatus.OK, DiagnosticStatus.WARN, DiagnosticStatus.ERROR, DiagnosticStatus.STALE))
    assert (int(Severity.OK), int(Severity.WARN), int(Severity.ERROR), int(Severity.STALE)) == ros


def test_default_yaml_matches_dataclass_defaults():
    assert load_thresholds(DEFAULT_CONFIG_PATH) == Thresholds()


def _yaml_variant(tmp_path, old, new):
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    p = tmp_path / "t.yaml"
    p.write_text(text.replace(old, new), encoding="utf-8")
    return p


@pytest.mark.parametrize("old,new,message", [
    ("schema_version: 1", "schema_version: 2", "schema_version"),
    ("  recover_s: 1.0", "  recover_s: 1.0\n  bogus: 1", "키가 다릅니다"),
    ("  recover_s: 1.0", "", "키가 다릅니다"),
    ("  tilt_deg: 70.0", "  tilt_deg: true", "숫자"),
    ("  nx: 17", "  nx: 17.5", "정수"),
    ("  recover_tilt_deg: 25.0", "  recover_tilt_deg: 80.0", "recover_tilt_deg"),
    ("  clear_deg: 30.0", "  clear_deg: 50.0", "tilt_clear_deg"),
    ("  clear_s: 0.5\n", "\n", "키가 다릅니다"),
    ("  max_dt_s: 0.5", "  max_dt_s: 0.5\nextra:\n  a: 1", "모르는 섹션"),
])
def test_yaml_validation(tmp_path, old, new, message):
    p = _yaml_variant(tmp_path, old, new)
    with pytest.raises(ValueError, match=message):
        load_thresholds(p)


@pytest.mark.parametrize("kw", [{"walk_speed_mps": 0.05}, {"fall_enter_s": 0.0}, {"scan_center_half_width": 9},
                                {"fall_low_height_ratio": 0.9}, {"nominal_height_m": -1.0}, {"scan_min_valid_fraction": 0.0},
                                {"init_tilt_max_deg": 80.0}, {"stand_dwell_s": -0.1}, {"tilt_warn_deg": 75.0},
                                {"tilt_clear_deg": 20.0}, {"tilt_enter_s": 0.0}])
def test_thresholds_validation(kw):
    with pytest.raises(ValueError):
        Thresholds(**kw)


def test_estimator_rejects_scan_shape_smaller_than_center_block():
    with pytest.raises(ValueError):
        StateEstimator(scan_shape=(1, 1))
    est = StateEstimator(Thresholds(scan_center_half_width=0), scan_shape=(1, 1))
    s = make_state()
    s["height_hits_z"] = np.array([1.0 - H0])
    assert est.update(s, 0.0).features["height_m"] == pytest.approx(H0)
