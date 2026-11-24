<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# SW 인터페이스 계약

2026-11-23 기준 초안입니다. 메시지 정의([`hn_sw_msgs`](../../ros_pkgs/hn_sw_msgs/))만으로는 알 수 없는 것, 곧 누가 내고 누가 받는지, QoS, 끊김·오래됨 판단 시간, 모드 전환, 사유 코드를 적습니다. 기준 문서는 SW팀 노션의 인터페이스 계약 명세(IF-01~IF-27)이고, 이 문서와 다르면 둘을 같이 고칩니다.

여기 적은 숫자는 모두 **제안값**입니다. 시뮬레이터와 실기에서 시험하지 않았고 팀 합의도 받지 않았습니다. 정해지면 "제안" 표시를 지우고 근거를 남깁니다.

## 토픽·서비스 목록

토픽 하나는 한 영역만 냅니다(단일 작성자). 이름 앞의 `/hn/`을 AICV·Nav2 토픽에 붙일지는 정하지 않았습니다([정하지 않은 것](#정하지-않은-것)).

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
| `/map` | `nav_msgs/OccupancyGrid` | STATE | 변경 시 | 지도관리 | Nav2, 임무경로관리 | 14 |

- 관제 앱은 rosbridge로 붙습니다. 앱에는 위 표에서 받는 쪽이나 내는 쪽이 관제 앱인 것만 열어 둡니다. 관절·속도 명령 토픽은 열지 않습니다.
- `/cmd_vel`은 AICV `hn_interfaces` README의 Nav2 연결 표(Nav2 → 보행 제어, `Twist`)를 따릅니다. 보행 정책이 받는 이름과 타입은 그대로 두고 그 앞에 제어권명령관리와 안전 위협 관리를 둡니다. Nav2가 `/cmd_vel`에 직접 내지 않도록 Nav2 속도 출력은 `/cmd_vel_nav`로 remap합니다. 정지는 0 속도 `Twist`로 보냅니다.
- 앱은 `/hn/state/robot`을 20 Hz 그대로 받지 않고, rosbridge `subscribe`의 `throttle_rate: 200`(ms)으로 5 Hz만 받습니다. 토픽을 따로 만들지 않습니다.
- `/locomotion/status`의 `FALLEN`, `TILTING`은 안전 위협 관리가 `Hazard.TYPE_FALLEN`, `TYPE_FALL_RISK`로 옮깁니다. 이 연결은 AICV팀과 아직 맞추지 않았습니다.

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

서비스는 바로 끝나는 요청에만 씁니다. 서비스 응답은 1 s 안에 오지 않으면 부르는 쪽이 실패로 처리하고, 같은 `request_id`로 다시 보냅니다(제안). 받는 쪽은 같은 `request_id`를 한 번만 처리합니다.

## QoS 프로필

| 프로필 | reliability | history | durability | deadline | 쓰는 곳 |
| --- | --- | --- | --- | --- | --- |
| STREAM | best effort | keep last 1 | volatile | 없음 | 센서, 관절 상태, Teleop 입력, 앱 heartbeat |
| CONTROL | reliable | keep last 1 | volatile | 100 ms (제안) | 속도 명령, 관절 명령, 안전 판정 |
| STATE | reliable | keep last 1 | transient local | 없음 | 모드, 위험, 임무 상태, 로봇 상태, 지도 |
| EVENT | reliable | keep last 20 | transient local | 없음 | 경유점 도착, 점검 결과, 이벤트 |

- EVENT는 노션 명세의 STATE에서 나눈 것입니다. 이벤트가 연달아 나면 depth 1로는 앞의 것을 잃기 때문입니다. 놓친 이벤트는 `QueryRecord`로 다시 받습니다.
- CONTROL의 deadline은 QoS 이벤트로 알림만 받습니다. 정지는 아래 시간 기준에 따라 받는 쪽 코드가 합니다.

## 시간 기준 (제안)

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
| 위치추정 오래됨 | 300 ms | `pose_validity = STALE`, Auto 보류 | 10 Hz 3번 |
| 배터리 오래됨 | 3 s | `battery_validity = STALE` | 1 Hz 3번 |
| 안정 정지 확인 | 선속도 < 0.02 m/s, 회전 < 0.05 rad/s가 0.5 s 유지 | `stop_confirmed = true` | IF-04 |
| 정체 (R-10) | 명령 선속도 ≥ 0.1 m/s인데 실제 < 0.02 m/s가 3 s | `TYPE_STALLED` | IF-06 |
| 배터리 낮음 (R-15) | 30 % 이하 WARN, 15 % 이하 ERROR | WARN: 귀환 판단. ERROR: Auto 시작 거부 | 배터리 사양 확인 전 |

- 위치추정 신뢰도(R-13)는 숫자 대신 `LocalizationStatus.status`를 씁니다. `STATUS_TRACKING`이 아니면 Auto를 보류합니다. `fitness` 기준값은 AICV 쪽 실험값이라 여기서 정하지 않습니다.
- Sim에서는 모든 시간을 시뮬레이터 시간(`use_sim_time`)으로 잽니다.

## 모드 전환

`ControlMode`는 제어권명령관리만 바꿉니다. 위험이 사라져도 스스로 움직이는 모드로 바꾸지 않습니다(R-12).

| 지금 | 다음 | 계기 | 조건 |
| --- | --- | --- | --- |
| IDLE | AUTO | `REQUEST_AUTO` | 승인된 임무, `ready_to_walk`, 위치 `TRACKING`, `motion_blocked = false` |
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
| `MISSION_LOW_BATTERY_RETURN` | 임무경로관리 | 배터리 때문에 귀환 (R-15) |
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

- `/hn/` 접두사를 AICV·Nav2 토픽에도 붙일지. 지금은 붙이지 않고 launch remap으로 맞추는 쪽입니다.
- Nav2 속도 출력을 `/cmd_vel_nav`로 remap하는 것(Nav2 설정은 AICV 담당). 앱 목표를 임무경로관리를 거쳐 Nav2로 보내는 것(AICV 표는 "앱 → Nav2"). 둘 다 AICV팀과 합의가 필요합니다.
- MCU 프레임(IF-12)의 물리층과 주기, heartbeat가 끊겼을 때 MCU 동작. 모터를 MCU를 거쳐 돌릴지부터 EE팀과 정해야 합니다.
- 점검 이상 유형 목록과 낮은 신뢰도 처리(IF-17), 지도 패키지 형식(IF-24).
- 기록이 빠졌을 때의 처리(IF-25).
