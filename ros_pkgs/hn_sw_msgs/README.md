<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# hn_sw_msgs

2026-11-22 기준 초안입니다. SW 모듈(임무경로관리, 제어권명령관리, 안전 위협 관리, 로봇상태관리, 장치연동, 지도관리, 이벤트점검관리, 실행환경기록관리)과 관제 앱이 주고받는 ROS 2 message, service, action의 **정의만** 둡니다. 코드는 없습니다.

기준 문서는 SW팀 인터페이스 명세(노션, IF-01~IF-25)의 3.5절 "주요 메시지"와 5절 계약 표입니다. AICV팀이 만드는 위치추정·보행 상태 메시지는 [`hn_interfaces`](../hn_interfaces/)에 따로 있으며(브랜치 `feat/sim-fault-injection`), 병합 충돌을 피하려고 패키지를 나눴습니다.

## 들어 있는 것

| 구분 | 이름 | 토픽·서비스 | IF |
| --- | --- | --- | --- |
| 공통 값 | `Validity`, `ControlMode`, `CommandStatus`, `RunTarget`, `Reason` | 다른 메시지의 필드 | 명세 3.1, 3.3 |
| 임무·경로 | `Waypoint`, `Route`, `MissionStatus` | `/hn/mission/status` | 01 |
| | `WaypointEvent`, `TargetResult` | `/hn/mission/waypoint_event`, `/hn/inspection/target_result` | 16 |
| | srv `SubmitRoute`, `ApproveRoute` | `/hn/mission/submit_route`, `/hn/mission/approve_route` | 01 |
| | action `ExecuteMission` | `/hn/control/execute_mission` | 03 |
| 제어권 | `TeleopCmd`, `ControlState` | `/hn/control/teleop`, `/hn/control/state` | 02 |
| | srv `RequestMode` | `/hn/control/request_mode` | 02 |
| | `SelectedSafeCmd` (명세의 `SelectedCmd`·`SafeCmd`를 합침) | `/hn/control/cmd_vel_selected`, `/hn/safety/cmd_vel_safe` | 04, 20 |
| 안전 | `Hazard`, `HazardState` | `/hn/safety/hazard` | 05, 06 |
| | `SafetyVerdict` | `/hn/safety/verdict` | 04 |
| | `JointTargets` | `/hn/policy/joint_targets` | 20 |
| | `JointCommand` | `/hn/safety/joint_cmd` | 21 |
| 상태·장치 | `RobotState` | `/hn/state/robot` | 10, 11, 22 |
| | `DeviceFault` | `/hn/device/fault` | 07 |
| 지도 | `MapInfo`, srv `RegisterMap` | `/hn/map/info`, `/hn/map/register` | 13, 14, 24 |
| 이벤트·기록 | `Event`, srv `AckEvent` | `/hn/event/stream`, `/hn/event/ack` | 18 |
| | srv `QueryRecord` | `/hn/record/query` | 19 |

관절·IMU·배터리는 표준 `sensor_msgs/JointState`, `Imu`, `BatteryState`를 씁니다(명세 3.5). 장치 진단(`/hn/device/health`, IF-08)은 표준 `diagnostic_msgs/DiagnosticArray`를 씁니다.

## 규칙

- **기본값은 안전한 쪽입니다.** ROS 메시지는 채우지 않은 숫자 필드가 0, bool이 false입니다. 그래서 0을 `Validity.UNAVAILABLE`, `RunTarget.MOCK`, `CommandStatus.NONE`, `JointCommand.MODE_DAMP`, `TargetResult.UNVISITED`로 두었습니다. 명세의 enum 순서와 다르고, `CommandStatus.NONE`은 명세에 없던 값입니다. `test/test_contract.py`가 이 기본값을 확인합니다.
- **관절은 이름으로 짝을 맞춥니다.** `JointTargets`, `JointCommand`는 `name` 배열을 함께 싣습니다. 정책(`policies/urdf_v1/policy_io.yaml`)은 hip×4 → thigh×4 → calf×4 순서이고 명세는 다리별 순서라서, 숫자 순서를 가정하지 않습니다.
- 모르는 실수 값은 `NaN`, 사유는 `Reason`(코드 + 화면 문장)으로 보냅니다(명세 3.1).
- 번호(상수)는 정하고 나면 바꾸거나 다른 뜻으로 재사용하지 않습니다. 필드를 바꾸면 보내는 쪽과 받는 쪽이 같은 정의로 다시 빌드해야 합니다.

## 빌드

```bash
colcon build --base-paths ros_pkgs --packages-select hn_sw_msgs
source install/setup.bash
ros2 interface show hn_sw_msgs/msg/RobotState
python3 -m pytest ros_pkgs/hn_sw_msgs/test -q
```

## 정하지 않은 것

- 토픽 이름의 `/hn/` 접두사: AICV 토픽(`/locomotion/status`, `/localization/*`)에는 없습니다. launch의 remap으로 맞출 수 있습니다.
- `Hazard.TYPE_*` 번호 목록은 초안입니다.
- 경로 보정·추종(IF-15), 위치추정(IF-09), 점검 탐지(IF-17)는 AICV팀과 정할 항목이라 넣지 않았습니다.
- 보행 정책을 ROS로 연결하는 쪽, 모터 제어 경로(MCU 경유 여부)에 따라 `JointCommand` 필드가 바뀔 수 있습니다.
