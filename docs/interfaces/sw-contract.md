<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# SW 인터페이스 계약

2026-11-28 기준 초안입니다. 메시지 정의([`hn_sw_msgs`](../../ros_pkgs/hn_sw_msgs/))만으로는 알 수 없는 것, 곧 누가 내고 누가 받는지, QoS, 끊김·오래됨 판단 시간, 모드 전환, 사유 코드를 적습니다. 기준 문서는 SW팀 노션의 인터페이스 계약 명세(IF-01~IF-27)이고, 이 문서와 다르면 둘을 같이 고칩니다.

여기 적은 숫자는 모두 **임시값**입니다. 시뮬레이터와 실기에서 시험하지 않았고 팀 합의도 받지 않았습니다. 실측하거나 담당 팀이 정하면 "임시" 표시를 지우고 근거를 남깁니다.

## AICV 인터페이스 기준

AICV팀이 먼저 정한 인터페이스를 기준으로 SW를 연결합니다. EE·AICV 작업에 따라 요구사항이 바뀔 수 있어서, SW가 따로 정의해 두고 나중에 맞추는 것보다 이쪽이 덜 어긋납니다.

- 기준은 `hn_interfaces`(브랜치 `feat/sim-fault-injection`)입니다. 이 브랜치는 아직 `main`에 없어서, 지금 `main`의 `hn_robot_state`는 `/locomotion/status`를 표준 `DiagnosticArray`로 냅니다. SW는 `LocomotionStatus` 기준으로 만들고, 이 브랜치가 `main`에 들어오면 맞춰집니다. `feat/localization-status-fields`는 그 위에 `LocalizationStatus` 필드와 Nav2 연결 계획을 더한 것이고, SW는 두 브랜치에 공통인 `LocalizationStatus.status`만 씁니다.
- AICV가 정한 토픽의 이름, 타입, QoS, 번호는 그대로 받습니다. `/hn/`을 붙이거나 이름을 바꾸지 않습니다. 예외는 Nav2 속도 출력 하나입니다. 보행 정책이 받는 `/cmd_vel`을 안전 위협 관리만 내야 해서 Nav2 쪽 출력을 `/cmd_vel_nav`로 remap합니다(AICV 합의 필요). 그 밖에 바꿔야 하면 AICV팀에 요청하고 ADR로 정합니다.
- 표준 인터페이스가 있는 것(`/cmd_vel`, `/odom`, `/map`, `/tf`, `/initialpose`, Nav2 action)은 표준 타입을 씁니다.
- SW가 새로 정의하는 것은 SW 영역 사이와 관제 앱 쪽 인터페이스(`/hn/...`, `hn_sw_msgs`)뿐입니다.
- AICV가 아직 정하지 않았는데 SW가 받아야 하는 것(보행 정책의 관절 목표 `JointTargets`, 점검 모델의 결과 `InspectionDetection`)은 SW가 먼저 정의하고 AICV팀에 알립니다. AICV가 다른 정의를 내면 그쪽에 맞춥니다.

## 토픽·서비스 목록

토픽 하나는 한 영역만 냅니다(단일 작성자). `/hn/`은 SW 토픽에만 붙이고, AICV·Nav2 토픽은 원래 이름을 씁니다.

### 토픽

| 토픽 | 타입 | QoS | 주기 | 내는 쪽 | 받는 쪽 | IF |
| --- | --- | --- | --- | --- | --- | --- |
| `/hn/mission/status` | `MissionStatus` | STATE | 변경 시 + 2 Hz | 임무경로관리 | 관제 앱 | 01 |
| `/hn/mission/waypoint_event` | `WaypointEvent` | EVENT | 발생 시 | 임무경로관리 | 이벤트점검관리 | 16 |
| `/hn/inspection/target_result` | `TargetResult` | EVENT | 발생 시 | 이벤트점검관리 | 임무경로관리 | 16 |
| `/hn/inspection/detection` | `InspectionDetection` | EVENT | 발생 시 | AICV 점검 | 이벤트점검관리 | 17 |
| `/hn/event/stream` | `Event` | EVENT | 발생 시 | 이벤트점검관리 | 관제 앱 | 18 |
| `/hn/control/teleop` | `TeleopCmd` | STREAM | 20 Hz | 관제 앱 | 제어권명령관리 | 02 |
| `/hn/app/heartbeat` | `AppHeartbeat` | STREAM | 2 Hz | 관제 앱 | 제어권명령관리 | 02 |
| `/hn/control/state` | `ControlState` | STATE | 변경 시 + 1 Hz | 제어권명령관리 | 관제 앱, 임무경로관리 | 02, 03 |
| `/cmd_vel_nav` | `geometry_msgs/Twist` | Nav2 기본값 | Nav2 controller 주기 | Nav2 (AICV) | 제어권명령관리 | 26 |
| `/hn/control/cmd_vel_selected` | `SelectedSafeCmd` | CONTROL | 50 Hz | 제어권명령관리 | 안전 위협 관리 | 04 |
| `/hn/safety/verdict` | `SafetyVerdict` | CONTROL | 50 Hz | 안전 위협 관리 | 제어권명령관리 | 04 |
| `/cmd_vel` | `geometry_msgs/Twist` | CONTROL | 50 Hz | 안전 위협 관리 | 보행 정책 (AICV) | 20 |
| `/hn/policy/joint_targets` | `JointTargets` | CONTROL | 50 Hz | 보행 정책 (AICV) | 안전 위협 관리 | 20 |
| `/hn/safety/joint_cmd` | `JointCommand` | CONTROL | 50 Hz | 안전 위협 관리 | 장치연동 | 21 |
| `/hn/safety/hazard` | `HazardState` | STATE | 변경 시 + 1 Hz | 안전 위협 관리 | 관제 앱, 임무경로관리 | 05, 06 |
| `/hn/device/fault` | `DeviceFault` | STATE | 변경 시 + 10 Hz | 장치연동 | 안전 위협 관리 | 07 |
| `/hn/device/joint_states` | `sensor_msgs/JointState` | STREAM | 200 Hz | 장치연동 | 로봇상태관리, 보행 정책 | 08, 23 |
| `/hn/device/imu` | `sensor_msgs/Imu` | STREAM | 200 Hz | 장치연동 | 로봇상태관리, 보행 정책 | 08, 23 |
| `/hn/device/battery` | `sensor_msgs/BatteryState` | STATE | 1 Hz | 장치연동 | 로봇상태관리 | 08 |
| `/hn/device/health` | `diagnostic_msgs/DiagnosticArray` | STATE | 2 Hz | 장치연동 | 로봇상태관리 | 08 |
| `/localization/status` | `hn_interfaces/LocalizationStatus` | reliable (AICV) | 스캔마다 | 위치추정 (AICV) | 로봇상태관리 | 09 |
| `/localization/odometry` | `nav_msgs/Odometry` | AICV 정의 | 스캔마다 | 위치추정 (AICV) | 로봇상태관리 | 09 |
| `/locomotion/status` | `hn_interfaces/LocomotionStatus` | reliable, transient_local (AICV) | 변경 시 + 10 Hz | 보행 상태 판정 (AICV) | 안전 위협 관리 | 27 |
| `/hn/state/robot` | `RobotState` | STATE | 20 Hz | 로봇상태관리 | 안전 위협 관리, 임무경로관리, 관제 앱 | 10, 11, 22 |
| `/hn/map/info` | `MapInfo` | STATE | 변경 시 | 지도관리 | 관제 앱, 임무경로관리 | 13, 14 |
| `/map` | `nav_msgs/OccupancyGrid` | Nav2 기본값 | 시작 시 | Nav2 map server (AICV 지도 파일) | Nav2, 임무경로관리, 지도관리 | 14 |
| `/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | Nav2 기본값 | 요청 시 | 관제 앱 | 위치추정 (AICV) | 09 |
| `/clock` | `rosgraph_msgs/Clock` | AICV 정의 | 50 Hz | 시뮬레이터 (SIM만) | 모든 노드 (`use_sim_time`) | - |

- 관제 앱은 rosbridge로 붙습니다. 앱에는 위 표에서 받는 쪽이나 내는 쪽이 관제 앱인 것만 열어 둡니다. 관절·속도 명령 토픽은 열지 않습니다.
- `/cmd_vel`은 AICV `hn_interfaces` README의 Nav2 연결 표(Nav2 → 보행 제어, `Twist`)를 따릅니다. 보행 정책이 받는 이름과 타입은 그대로 두고 그 앞에 제어권명령관리와 안전 위협 관리를 둡니다. Nav2가 `/cmd_vel`에 직접 내지 않도록 Nav2 속도 출력은 `/cmd_vel_nav`로 remap합니다. 정지는 0 속도 `Twist`로 보냅니다.
- 앱은 `/hn/state/robot`을 20 Hz 그대로 받지 않고, rosbridge `subscribe`의 `throttle_rate: 200`(ms)으로 5 Hz만 받습니다. 토픽을 따로 만들지 않습니다.
- `/locomotion/status`를 SW 위험으로 옮기는 방법은 [SIM과 실기](#sim과-실기)에 있습니다.

### 서비스·액션

| 이름 | 종류·타입 | 부르는 쪽 | 받는 쪽 | IF |
| --- | --- | --- | --- | --- |
| `/hn/mission/submit_route` | srv `SubmitRoute` | 관제 앱 | 임무경로관리 | 01 |
| `/hn/mission/approve_route` | srv `ApproveRoute` | 관제 앱 | 임무경로관리 | 01 |
| `/hn/control/request_mode` | srv `RequestMode` | 관제 앱 | 제어권명령관리 | 02 |
| `/hn/control/execute_mission` | action `ExecuteMission` | 임무경로관리 | 제어권명령관리 | 03 |
| `/navigate_to_pose` 또는 `/follow_waypoints` | Nav2 표준 action | 임무경로관리 | Nav2 (AICV) | 15 |
| `/hn/event/ack` | srv `AckEvent` | 관제 앱 | 이벤트점검관리 | 18 |
| `/hn/record/query` | srv `QueryRecord` | 관제 앱 | 실행환경기록관리 | 19 |
| `/hn/map/register` | srv `RegisterMap` | AICV | 지도관리 | 24 |

서비스는 바로 끝나는 요청에만 씁니다. 서비스 응답은 1 s 안에 오지 않으면 부르는 쪽이 실패로 처리하고, 같은 `request_id`로 다시 보냅니다(1 s는 임시값). 받는 쪽은 같은 `request_id`를 한 번만 처리합니다.

## QoS 프로필

| 프로필 | reliability | history | durability | deadline | 쓰는 곳 |
| --- | --- | --- | --- | --- | --- |
| STREAM | best effort | keep last 1 | volatile | 없음 | 센서, 관절 상태, Teleop 입력, 앱 heartbeat |
| CONTROL | reliable | keep last 1 | volatile | 100 ms (임시값) | 속도 명령, 관절 명령, 안전 판정 |
| STATE | reliable | keep last 1 | transient local | 없음 | 모드, 위험, 임무 상태, 로봇 상태, 지도 |
| EVENT | reliable | keep last 20 | transient local | 없음 | 경유점 도착, 점검 결과, 이벤트 |

- EVENT는 노션 명세의 STATE에서 나눈 것입니다. 이벤트가 연달아 나면 depth 1로는 앞의 것을 잃기 때문입니다. 놓친 이벤트는 `QueryRecord`로 다시 받습니다.
- CONTROL의 deadline은 QoS 이벤트로 알림만 받습니다. 정지는 아래 시간 기준에 따라 받는 쪽 코드가 합니다.

## 시간 기준 (임시값)

| 항목 | 기준 | 넘었을 때 | 근거 |
| --- | --- | --- | --- |
| Teleop 입력 끊김 | 200 ms | 제어권명령관리가 속도 0 | 20 Hz 입력 4번 |
| `deadman` 해제 | 즉시 | 속도 0 | R-06 |
| Nav2 `/cmd_vel_nav` 끊김 (Auto) | 200 ms | 속도 0, 임무는 유지 | Nav2 controller 20 Hz 기준 4번 |
| `cmd_vel_selected`, `/cmd_vel`, `joint_targets` 끊김 | 100 ms | 받는 쪽이 정지 | 50 Hz 5번. `/cmd_vel`을 받는 보행 정책 쪽 동작은 AICV와 맞춤 |
| `joint_cmd` 끊김 | 100 ms | 장치연동이 `MODE_DAMP`를 MCU에 보냄 | 50 Hz 5번 |
| 앱 heartbeat 끊김 | 1.5 s | Teleop: 정지 후 PAUSED. Auto: 일시정지(PAUSED) | 2 Hz 3번 |
| 관절·IMU 오래됨 | 20 ms | `STALE`, 정책 입력에서 뺌 | 200 Hz 4번 |
| 로봇 상태 오래됨 | 200 ms | `STALE`, 안전 위협 관리는 이동 차단 | 20 Hz 4번 |
| `/locomotion/status` 끊김 | 300 ms | 상태 확인 불가(`TYPE_STATE_STALE`), 이동 차단, ERROR | AICV 10 Hz heartbeat 3번 |
| 위치추정 오래됨 | 300 ms | `pose_validity = STALE`, Auto 보류 | 10 Hz 3번 |
| 배터리 오래됨 | 3 s | `battery_validity = STALE` | 1 Hz 3번 |
| 안정 정지 확인 | 선속도 < 0.02 m/s, 회전 < 0.05 rad/s가 0.5 s 유지 | `stop_confirmed = true` | IF-04 |
| 정체 (R-10) | 명령 선속도 ≥ 0.1 m/s인데 실제 < 0.02 m/s가 3 s | `TYPE_STALLED` | IF-06 |
| 배터리 부족 (R-15) | 남은 배터리 < 예상 소모량 + 10 %p | Auto 시작 거부, 충전 후 출발 | 아래 "배터리 판단" |

### 배터리 판단 (R-15)

배터리가 떨어진 뒤에 대처하지 않고, **출발할 때** 임무를 끝까지 할 수 있는지 미리 봅니다(SW팀장 결정, 2026-11-27).

- 판단하는 곳: 임무경로관리가 `REQUEST_AUTO`를 받을 때.
- 예상 소모량 = 평균 분당 소모량 × 예상 이동 시간. 예상 이동 시간은 승인된 경로 길이를 계획 속도로 나눈 값입니다(왕복이면 왕복 거리).
- 여유분 10 %p를 더해서, 남은 배터리(`RobotState.battery_ratio`)가 그보다 적으면 시작을 거부하고 `MISSION_BATTERY_INSUFFICIENT`를 냅니다. 예) 예상 소모량 60 %면 70 % 이상일 때만 출발합니다.
- **평균 분당 소모량은 임시값**입니다. 배터리 사양과 실측이 나오기 전까지 파라미터로 두고, EE·HW팀 값이 나오면 바꿉니다. 여유분 10 %p도 같은 파라미터로 둡니다.
- `battery_validity`가 `VALID`가 아니면 판단할 수 없으므로 시작을 거부합니다.

- 위치추정 신뢰도(R-13)는 숫자 대신 `LocalizationStatus.status`를 씁니다. `STATUS_TRACKING`이 아니면 Auto를 보류합니다. `fitness` 기준값은 AICV 쪽 실험값이라 여기서 정하지 않습니다.
- SIM에서는 모든 SW 노드가 시뮬레이터 시간(`/clock`, `use_sim_time`)으로 잽니다. 실기에서는 시스템 시간입니다.

## SIM과 실기

실제 로봇에 올릴 SW 코드가 SIM에서도 같은 경로로 돌게 합니다.

- SW 노드는 SIM과 실기에서 같은 코드, 같은 토픽 이름으로 돕니다. SIM이라고 다른 경로를 타는 코드는 두지 않습니다.
- 달라지는 것은 AICV 토픽을 누가 내는지(SIM: 시뮬레이터 하네스·SIM 어댑터, 실기: 센서 드라이버·LIO)와 시간(`/clock`)뿐입니다.
- 고장 주입과 reset(`/sim/inject_fault`, `hn_interfaces/srv/InjectFault`)은 AICV 검증용 SIM 전용 기능으로 둡니다. SW 노드는 이 서비스를 부르거나 기대하지 않고, rosbridge로 앱에 열지도 않습니다. SW 통합 시험 스크립트만 이 서비스로 위험 상황을 만듭니다.

### 통합 시험에서 기대하는 동작

| `InjectFault.kind` | `/locomotion/status` | SW 동작 |
| --- | --- | --- |
| `tilt` | `TILTING` | `TYPE_FALL_RISK`, 이동 차단, PAUSED |
| `collapse`, `flip` | `FALLEN` | `TYPE_FALLEN`, 이동 차단, PAUSED |
| `stale` | `STALE_INPUT` (로봇은 계속 걸음) | `TYPE_STATE_STALE`, 이동 차단, ERROR |
| `push` | 힘에 따라 `WALKING`·`TILTING`(버팀) 또는 `FALLEN` | 나온 상태에 따라 위와 같음 |
| `clear` | 고장만 끝남. 로봇 자세는 그대로(넘어졌으면 `FALLEN` 유지) | 위험이 남아 있으면 그대로. 풀려도 `resumable = true`까지만 |
| `reset` | 그 자리에 다시 세움 → `STANDING` | `resumable = true`까지만. 운영자가 재개하기 전에는 움직이지 않음 (R-12) |

### `/locomotion/status`를 받을 때 주의할 것

AICV 인터페이스 문서(`docs/interfaces/locomotion-status.md`)의 알려진 한계 중 SW 동작에 걸리는 것입니다.

- 로봇이 스스로 일어나면 `FALLEN`이 풀릴 수 있습니다. SW는 `TYPE_FALLEN`을 운영자가 재개할 때까지 유지합니다.
- 걸려서 못 움직여도 `WALKING`으로 남습니다(`SLIPPING` 미구현). 정체 판정(R-10)은 SW가 `RobotState`로 합니다.
- `header.stamp`는 기본이 시스템 시간입니다. SIM에서 SW 노드는 `use_sim_time`이므로 이 토픽의 오래됨은 stamp가 아니라 받은 시각으로 판단합니다.

## 모드 전환

`ControlMode`는 제어권명령관리만 바꿉니다. 위험이 사라져도 스스로 움직이는 모드로 바꾸지 않습니다(R-12).

| 지금 | 다음 | 계기 | 조건 |
| --- | --- | --- | --- |
| IDLE | AUTO | `REQUEST_AUTO` | 승인된 임무, `ready_to_walk`, 위치 `TRACKING`, `motion_blocked = false`, 배터리 충분(R-15) |
| IDLE | TELEOP | `REQUEST_TELEOP` | 조종권을 받은 앱, `ready_to_walk` |
| AUTO | TELEOP | `REQUEST_TELEOP` | 운영자 개입. 임무는 `HELD` (R-07) |
| TELEOP | AUTO | `REQUEST_RESUME` | 보류된 임무가 있고 IDLE → AUTO 조건을 충족 |
| AUTO, TELEOP | PAUSED | `REQUEST_PAUSE`, 앱 끊김, `motion_blocked = true` | 없음 |
| PAUSED | 직전 모드 | `REQUEST_RESUME` | `HazardState.resumable = true` |
| 모든 모드 | IDLE | `REQUEST_STOP`, `REQUEST_CANCEL` | STOP은 즉시 정지, 임무 `CANCELED`. CANCEL은 임무만 취소하고 정지 |
| 모든 모드 | ESTOP | `DeviceFault.estop_pressed` | 없음 |
| ESTOP | IDLE | E-Stop 해제 확인 | 해제돼도 IDLE까지만 갑니다 |
| 모든 모드 | ERROR | MCU 연결 끊김, 필수 상태 `STALE` | 없음 |
| ERROR | IDLE | `REQUEST_STOP` | 원인이 해소됨 |

PAUSE와 STOP의 차이는 임무를 남기는지입니다. PAUSE는 임무를 `HELD`로 두고, STOP은 끝냅니다.

## 사유 코드

`Reason.code`에 넣는 값입니다. `<영역>_<이름>` 꼴의 대문자로 쓰고, 한 번 정한 코드는 다른 뜻으로 쓰지 않습니다. 앱은 `code`로 분기하고 `message`를 그대로 보여 줍니다.

| 코드 | 내는 쪽 | 뜻 |
| --- | --- | --- |
| `MISSION_ROUTE_NOT_APPROVED` | 임무경로관리 | 승인하지 않은 경로 |
| `MISSION_REVISION_MISMATCH` | 임무경로관리 | 승인한 revision이 최신이 아님 (R-05) |
| `MISSION_ROUTE_UNREACHABLE` | 임무경로관리 | 보정해도 갈 수 없음 (R-14) |
| `MISSION_MAP_MISMATCH` | 임무경로관리 | 경로의 지도 ID·버전이 현재 지도와 다름 |
| `MISSION_WAYPOINT_SKIPPED` | 임무경로관리 | 경유점에 도착하지 못하고 넘어감 (R-19) |
| `MISSION_BATTERY_INSUFFICIENT` | 임무경로관리 | 남은 배터리로 임무를 끝낼 수 없어 시작 거부. 충전 후 출발 (R-15) |
| `CONTROL_NOT_OWNER` | 제어권명령관리 | 조종권이 없는 앱의 요청 (R-01, R-06) |
| `CONTROL_INVALID_REQUEST` | 제어권명령관리 | 지금 모드에서 할 수 없는 요청 |
| `CONTROL_NOT_READY` | 제어권명령관리 | 보행 준비 전 (`ready_to_walk = false`) |
| `CONTROL_TELEOP_ACTIVE` | 제어권명령관리 | Teleop 중이라 임무 보류 (R-07) |
| `CONTROL_APP_DISCONNECTED` | 제어권명령관리 | 앱 heartbeat 끊김 (R-16) |
| `CONTROL_TELEOP_TIMEOUT` | 제어권명령관리 | Teleop 입력 끊김 |
| `CONTROL_RESUME_NOT_ALLOWED` | 제어권명령관리 | 복구 조건 미충족 상태의 재개 요청 (R-12) |
| `SAFETY_ESTOP` | 안전 위협 관리 | E-Stop |
| `SAFETY_DEVICE_FAULT` | 안전 위협 관리 | 모터·MCU 고장 |
| `SAFETY_MCU_LINK_LOSS` | 안전 위협 관리 | MCU 통신 끊김 |
| `SAFETY_FALLEN` | 안전 위협 관리 | 넘어짐 |
| `SAFETY_FALL_RISK` | 안전 위협 관리 | 크게 기울어짐 |
| `SAFETY_LOCALIZATION_LOST` | 안전 위협 관리 | 위치 상실 (R-13) |
| `SAFETY_STATE_STALE` | 안전 위협 관리 | 필수 상태 값이 오래됨 (R-08) |
| `SAFETY_JOINT_LIMIT` | 안전 위협 관리 | 관절 목표가 허용 범위 밖 (R-09) |
| `SAFETY_STALLED` | 안전 위협 관리 | 정체 (R-10) |
| `SAFETY_CMD_TIMEOUT` | 안전 위협 관리 | 이동·관절 명령 끊김 |
| `MAP_NOT_LOADED` | 지도관리 | 등록된 지도 없음 |
| `MAP_PACKAGE_INVALID` | 지도관리 | 지도 패키지 파일 누락·해시 불일치 |
| `EVENT_NOT_FOUND` | 이벤트점검관리 | 없는 `event_id` |
| `RECORD_NOT_FOUND` | 실행환경기록관리 | 없는 `mission_id` |

## 정하지 않은 것

- Nav2 속도 출력을 `/cmd_vel_nav`로 remap하는 것(Nav2 설정은 AICV 담당). 앱 목표를 임무경로관리를 거쳐 Nav2로 보내는 것(AICV 표는 "앱 → Nav2"). 둘 다 AICV팀과 합의가 필요합니다.
- 보행 정책 runner가 SIM에서도 `/cmd_vel`을 받게 하는 것. 지금 SIM의 경로 추종은 시뮬레이터 안에서 명령을 만들고 ROS로 받지 않습니다(AICV 표에서도 받는 쪽 미정).
- SIM에서 장치 토픽(`/hn/device/*`)을 낼 쪽. 실기와 같은 경로로 시험하려면 시뮬레이터 하네스나 SW Mock이 같은 토픽을 내야 합니다.
- `/odom`과 `odom` → `trunk` TF를 누가 낼지(AICV 미정). 로봇상태관리는 위치를 `/localization/odometry`에서 받습니다.
- `/locomotion/status`의 stamp를 SIM에서 시뮬레이션 시간으로 할지(AICV의 `--stamp sim`).
- MCU 프레임(IF-12)의 물리층과 주기, heartbeat가 끊겼을 때 MCU 동작. 모터를 MCU를 거쳐 돌릴지부터 EE팀과 정해야 합니다.
- 점검 이상 유형 목록과 낮은 신뢰도 처리(IF-17), 지도 패키지 형식(IF-24).
- 기록이 빠졌을 때의 처리(IF-25).
- 배터리(R-15): 임무 중에 예상보다 빨리 닳을 때의 처리(`Hazard.TYPE_LOW_BATTERY`를 쓸지 포함), 충전을 사람이 하는지 로봇이 충전기로 가는지, 평균 분당 소모량의 실제 값(EE·HW).
