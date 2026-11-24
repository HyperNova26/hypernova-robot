<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# hn_sw_msgs

2026-11-22 기준 초안입니다. SW 모듈(임무경로관리, 제어권명령관리, 안전 위협 관리, 로봇상태관리, 장치연동, 지도관리, 이벤트점검관리, 실행환경기록관리)과 관제 앱이 주고받는 ROS 2 message, service, action의 **정의만** 둡니다. 코드는 없습니다.

기준 문서는 SW팀 인터페이스 명세(노션, IF-01~IF-25)의 3.5절 "주요 메시지"와 5절 계약 표입니다. AICV팀이 만드는 위치추정·보행 상태 메시지는 [`hn_interfaces`](../hn_interfaces/)에 따로 있으며(브랜치 `feat/localization-status-fields`), 병합 충돌을 피하려고 패키지를 나눴습니다.

누가 내고 받는지, QoS, 끊김 판단 시간, 모드 전환, 사유 코드는 [SW 인터페이스 계약](../../docs/interfaces/sw-contract.md)에 있습니다.

## 들어 있는 것

| 구분 | 이름 | 토픽·서비스 | IF |
| --- | --- | --- | --- |
| 공통 값 | `Validity`, `ControlMode`, `CommandStatus`, `RunTarget`, `Reason` | 다른 메시지의 필드 | 명세 3.1, 3.3 |
| 임무·경로 | `Waypoint`, `Route`, `MissionStatus` | `/hn/mission/status` | 01 |
| | `WaypointEvent`, `TargetResult` | `/hn/mission/waypoint_event`, `/hn/inspection/target_result` | 16 |
| | `InspectionDetection` | `/hn/inspection/detection` | 17 |
| | srv `SubmitRoute`, `ApproveRoute` | `/hn/mission/submit_route`, `/hn/mission/approve_route` | 01 |
| | action `ExecuteMission` | `/hn/control/execute_mission` | 03 |
| 제어권 | `TeleopCmd`, `ControlState` | `/hn/control/teleop`, `/hn/control/state` | 02 |
| | `AppHeartbeat` | `/hn/app/heartbeat` | 02 (R-16) |
| | srv `RequestMode` | `/hn/control/request_mode` | 02 |
| | `SelectedSafeCmd` (명세의 `SelectedCmd`) | `/hn/control/cmd_vel_selected` | 04 |
| 안전 | `Hazard`, `HazardState` | `/hn/safety/hazard` | 05, 06 |
| | `SafetyVerdict` | `/hn/safety/verdict` | 04 |
| | `JointTargets` | `/hn/policy/joint_targets` | 20 |
| | `JointCommand` | `/hn/safety/joint_cmd` | 21 |
| 상태·장치 | `RobotState` | `/hn/state/robot` | 10, 11, 22 |
| | `DeviceFault` | `/hn/device/fault` | 07 |
| 지도 | `MapInfo`, srv `RegisterMap` | `/hn/map/info`, `/hn/map/register` | 13, 14, 24 |
| 이벤트·기록 | `Event`, srv `AckEvent` | `/hn/event/stream`, `/hn/event/ack` | 18 |
| | srv `QueryRecord` | `/hn/record/query` | 19 |

관절·IMU·배터리는 표준 `sensor_msgs/JointState`, `Imu`, `BatteryState`를 씁니다(명세 3.5). 안전 위협 관리가 보행 정책에 넘기는 속도 명령은 AICV 인터페이스대로 표준 `/cmd_vel`(`geometry_msgs/Twist`)이라 이 패키지에 정의하지 않습니다(IF-20). 장치 진단(`/hn/device/health`, IF-08)은 표준 `diagnostic_msgs/DiagnosticArray`를 씁니다.

## 규칙

- **기본값은 안전한 쪽입니다.** ROS 메시지는 채우지 않은 숫자 필드가 0, bool이 false입니다. 그래서 0을 `Validity.UNAVAILABLE`, `RunTarget.MOCK`, `CommandStatus.NONE`, `JointCommand.MODE_DAMP`, `TargetResult.UNVISITED`, `InspectionDetection.UNKNOWN`으로 두었습니다. 명세의 enum 순서와 다르고, `CommandStatus.NONE`은 명세에 없던 값입니다. `test/test_contract.py`가 이 기본값을 확인합니다.
- **관절은 이름으로 짝을 맞춥니다.** `JointTargets`, `JointCommand`는 `name` 배열을 함께 싣습니다. 정책(`policies/urdf_v1/policy_io.yaml`)은 hip×4 → thigh×4 → calf×4 순서이고 명세는 다리별 순서라서, 숫자 순서를 가정하지 않습니다.
- 모르는 실수 값은 `NaN`, 사유는 `Reason`(코드 + 화면 문장)으로 보냅니다(명세 3.1). 코드 목록은 [사유 코드](../../docs/interfaces/sw-contract.md#사유-코드)에 있습니다.
- 번호(상수)는 정하고 나면 바꾸거나 다른 뜻으로 재사용하지 않습니다. 필드를 바꾸면 보내는 쪽과 받는 쪽이 같은 정의로 다시 빌드해야 합니다.

## 빌드

```bash
colcon build --base-paths ros_pkgs --packages-select hn_sw_msgs
source install/setup.bash
ros2 interface show hn_sw_msgs/msg/RobotState
python3 -m pytest ros_pkgs/hn_sw_msgs/test -q
```

## AICV·Nav2와 맞춘 것 (2026-11-23)

AICV 브랜치 `feat/localization-status-fields`의 `hn_interfaces` README "Nav2 연결(계획)"에 맞췄습니다. Nav2 쪽은 모두 표준 타입이라 이 패키지에 새 정의를 두지 않습니다.

| 항목 | 정한 것 |
| --- | --- |
| 좌표 이름 | 지도 프레임은 `pair360_map`(ADR-0005 Proposed), 몸체 프레임은 `trunk`. 명세의 `map`, `base_link`에 해당합니다 |
| 위치추정 신뢰도 (IF-09) | 숫자 점수 대신 AICV `LocalizationStatus.status`를 `RobotState.localization_status`로 그대로 옮기고, TRACKING이 아니면 `pose_validity`를 VALID가 아니게 둡니다. `fitness` 기준값은 AICV 실험값이라 SW에서 정하지 않습니다([계약 문서](../../docs/interfaces/sw-contract.md)와 같음) |
| 속도 명령 | 보행 정책은 AICV 표대로 표준 `/cmd_vel`(`Twist`)을 받습니다. `/cmd_vel`은 안전 위협 관리 하나만 냅니다. Nav2 속도 출력은 `/cmd_vel_nav`로 remap해 제어권명령관리가 Teleop 입력과 함께 받고, 고른 명령(`SelectedSafeCmd`)을 안전 위협 관리에 넘깁니다. 보행 정책 쪽 이름과 타입은 바꾸지 않습니다 |
| 경로 추종 (IF-15) | 앱은 Nav2에 직접 목표를 주지 않고, `SubmitRoute`·`ApproveRoute`로 임무경로관리에 승인받은 뒤 임무경로관리가 Nav2 표준 action(`NavigateToPose` 또는 `FollowWaypoints`)을 부릅니다. AICV 표의 "앱 → Nav2"와 다르므로 합의가 필요합니다 |
| 2D 지도 | 지도관리가 표준 `nav_msgs/OccupancyGrid`로 `/map`에 냅니다 |
| 재위치추정 (R-13) | 앱 → 위치추정 표준 `/initialpose`(`PoseWithCovarianceStamped`) |

## 정하지 않은 것

- 토픽 이름의 `/hn/` 접두사: AICV 토픽(`/locomotion/status`, `/localization/*`)과 Nav2 토픽에는 없습니다. launch의 remap으로 맞출 수 있습니다.
- `Hazard.TYPE_*` 번호 목록은 초안입니다.
- 위치추정 결과에 지도 버전이 없습니다(IF-09).
- 경로 보정(통행 불가 구간만 고치기, IF-15)의 양식은 AICV팀과 정할 항목이라 넣지 않았습니다.
- `InspectionDetection`은 틀만 정했습니다. 이상 유형 목록과 낮은 신뢰도 결과를 어떻게 처리할지는 AICV팀과 정해야 합니다(IF-17).
- 보행 정책을 ROS로 연결하는 쪽, 모터 제어 경로(MCU 경유 여부)에 따라 `JointCommand` 필드가 바뀔 수 있습니다.
