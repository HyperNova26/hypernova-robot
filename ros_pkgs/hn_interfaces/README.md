<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# hn_interfaces

2026-11-23 기준입니다. 로봇과 SW팀 앱이 주고받는 ROS 2 message, service, action과 시뮬레이터 시험용 service의 **정의만** 둡니다. 코드는 없습니다. 통신은 Fast DDS를 쓰기로 SW팀과 정했습니다(2026-11-18, `docker/fastdds.xml`).

## 들어 있는 것

이 패키지가 정의하는 메시지입니다.

| 종류 | 이름 | 토픽 | 상태 | 기준 문서 |
| --- | --- | --- | --- | --- |
| message | [`LocalizationStatus`](msg/LocalizationStatus.msg) | `/localization/status` | S-005 v0(2026-11-23). 번호는 S-005 표 그대로이고, 맨 앞 `header` + `uint8 status`는 대시보드 가정과 같습니다. 뒤에 품질·출처 필드 7개를 더했습니다. LIO 어댑터가 발행하는 코드는 아직 이 브랜치에 없습니다 | S-005 |
| message | [`LocomotionStatus`](msg/LocomotionStatus.msg) | `/locomotion/status` | 제안(ADR-0004 Proposed). 시뮬레이터에서 발행을 확인했습니다 | [인터페이스 문서](../../docs/interfaces/locomotion-status.md), [ADR-0004](../../docs/decisions/0004-locomotion-status-topic.md) |
| service | [`InjectFault`](srv/InjectFault.srv) | `/sim/inject_fault` | 시험용(2026-11-19). 시뮬레이터 하네스만 제공하고 실기에는 없습니다. SW팀 앱이 쓰는 인터페이스가 아닙니다 | [인터페이스 문서의 직접 실행해 보기](../../docs/interfaces/locomotion-status.md#직접-실행해-보기) |

## 고정 토픽 목록

로봇과 SW팀 앱·대시보드가 주고받는 토픽을 한곳에 모은 표입니다. 표준 인터페이스가 있는 것(`cmd_vel`, `odom`, `map`, Nav2의 action 등)은 새로 정의하지 않고 표준 타입을 씁니다. S-005 행은 S-005 인터페이스 그림(`localization-dashboard-interface`)과 PR #24 대시보드 README의 표를 옮긴 것입니다.

| 토픽 | 타입 | 좌표·비고 | 출처 | 정의 |
| --- | --- | --- | --- | --- |
| `/lidar/points` | `sensor_msgs/msg/PointCloud2` | frame `mlx_lidar`. ML-X 센서 드라이버가 냅니다 | S-005 | 표준 |
| `/localization/odometry` | `nav_msgs/msg/Odometry` | `pair360_map` → `mlx_lidar` | S-005 | 표준 |
| `/localization/status` | `hn_interfaces/msg/LocalizationStatus` | 상태 번호 0–5, 스캔마다 1개. `source`로 어댑터 구분, QoS reliable | S-005 | **이 패키지** |
| `/localization/reference_map` | `sensor_msgs/msg/PointCloud2` | 시작할 때 1회, transient-local(대시보드 README) | S-005 | 표준 |
| `/tf` | `tf2_msgs/msg/TFMessage` | `pair360_map` → `mlx_lidar`, odometry와 같은 시각. LIO 어댑터 내부 TF는 `/tf` 밖 | S-005 | 표준 |
| `/locomotion/status` | `hn_interfaces/msg/LocomotionStatus` | 상태 번호 0–6, QoS reliable + transient_local | G-006 | **이 패키지** |

- S-005의 LIO 어댑터(LiDAR-only, FAST-LIO2, 검토 중인 Super-LIO)는 교체할 수 있고, 동시에 하나만 실행합니다. `LocalizationStatus.source`가 `lidar_only`, `fastlio2`, `superlio`로 구분합니다. 대시보드와 Nav2는 위 고정 토픽만 구독하는 것이 약속입니다. Super-LIO는 2026-11-23 검토에서 같은 토픽을 낼 수 있음을 확인했고 교체는 결정하지 않았습니다(S-008). 시뮬레이터도 같은 토픽을 내면 같은 대시보드와 Nav2를 실기와 시뮬레이터에서 그대로 쓸 수 있습니다(계획 중, 아직 구현하지 않았습니다).
- 세 시뮬레이터가 지금 내는 것은 `/locomotion/status`와 `/clock`(시뮬레이션 시간, 정책 주기 50 Hz)이고, 고장 주입 서비스 `/sim/inject_fault`를 엽니다(`tools/demo/run_route.sh`로 띄우면 기본으로 켜짐). S-005 토픽을 내는 쪽은 S-006의 MuJoCo kinematic SIM(PR #24)입니다.

## Nav2 연결(계획)

2026-11-23 기준 아직 구현하지 않았습니다. Nav2(Jazzy)가 쓰는 인터페이스는 모두 표준 타입이라 이 패키지에 새 정의를 두지 않습니다. 아래는 맞춰야 할 이름과 타입을 적어 둔 것이고, 누가 발행·구독할지는 정해지지 않았습니다.

| 토픽·action | 타입 | 방향 | 비고 |
| --- | --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | Nav2 → 보행 제어 | 단위 m/s, rad/s. 받는 쪽(보행 정책 runner)은 미정 |
| `/odom` | `nav_msgs/msg/Odometry` | 로봇 → Nav2 | `odom` → `trunk`. 발행하는 쪽 미정 |
| `/map` | `nav_msgs/msg/OccupancyGrid` | map server → Nav2 | frame `pair360_map`([ADR-0005](../../docs/decisions/0005-pair360-map-frame.md), Proposed). 2D 지도는 아직 없습니다 |
| `/goal_pose` | `geometry_msgs/msg/PoseStamped` | 앱 → Nav2 | frame `pair360_map` |
| `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | 앱 → Nav2 | 진행 상황과 결과는 action feedback·result로 받습니다 |
| `/initialpose` | `geometry_msgs/msg/PoseWithCovarianceStamped` | 앱 → 위치추정 | `STATUS_LOST` 뒤 새 초기 위치. 받는 쪽은 아직 구현하지 않았습니다 |
| `/tf` | `tf2_msgs/msg/TFMessage` | 위치추정 → Nav2 | Nav2는 `pair360_map` → `odom` → `trunk`가 필요합니다 |

- 지금 S-005가 내는 TF는 `pair360_map` → `mlx_lidar` 하나입니다. Nav2에 맞추려면 `odom` 프레임을 누가 낼지와 `trunk` → `mlx_lidar` 장착 변환이 필요합니다. 장착 변환은 `description/`에만 둡니다. 핸드헬드 측정 장비에는 `trunk`가 없습니다.
- 속도 명령을 `TwistStamped`로 받을지는 정하지 않았습니다(Nav2 Jazzy 기본은 `Twist`).
- 여기에 없는 Nav2 전용 정의(예: 경로 진행 상태, 정지 요청)가 필요해지면 그때 이 패키지에 더하고 ADR을 거칩니다.

## 규칙

- 번호(enum 상수)는 한 번 정하면 바꾸거나 다른 뜻으로 재사용하지 않습니다. 앱이 번호로 분기하기 때문입니다.
- 필드나 상수를 바꾸면 발행하는 쪽과 구독하는 쪽이 같은 정의로 다시 빌드해야 합니다. ADR을 거쳐 바꿉니다.
- 새 항목은 `CMakeLists.txt`의 `rosidl_generate_interfaces`에 추가하고, 단위와 좌표, QoS를 메시지 파일 머리 주석에 적습니다.
- 번호가 바뀌지 않는지는 [`test/test_contract.py`](test/test_contract.py)가 확인합니다. 번호를 일부러 바꾸거나 더할 때는 이 표를 같이 고치고 ADR을 거칩니다. 쓰는 쪽 코드와 어긋나지 않는지는 쓰는 쪽의 시험이 확인합니다(예: `ros_pkgs/hn_robot_state/test/test_ros_node.py`).

## 빌드

저장소 최상위에서 컨테이너로 한 번 빌드합니다. `hn:sim` 기본 환경의 `VIRTUAL_ENV`(Isaac Lab venv)에는 `empy`가 없어서 해제하고 빌드합니다. 결과는 named volume에 쌓이고 `hn`으로 연 모든 프로세스가 자동으로 씁니다([docker/README.md](../../docker/README.md#ros-패키지-빌드-colcon)).

```bash
./docker/hn sim bash -c 'unset VIRTUAL_ENV && colcon build --base-paths ros_pkgs'
./docker/hn sim ros2 interface show hn_interfaces/msg/LocomotionStatus
```

## 알려진 미결정

- `LocalizationStatus`의 필드는 S-005 담당이 2026-11-23에 채웠습니다. 상수 이름(`STATUS_*`)과 맨 앞 두 필드는 먼저 있던 제안을 그대로 두었습니다. 대시보드의 상태 코드 필드 경로 기본값이 `status`라서 설정을 바꾸지 않고 읽혀야 하지만, 대시보드로 직접 확인하지는 않았습니다. 상태 판정 임계값은 실험값이고 어댑터 쪽 문서에 둡니다.
- Nav2에 필요한 `odom` 프레임과 `trunk` 기준 TF를 누가 낼지 정해지지 않았습니다([Nav2 연결(계획)](#nav2-연결계획)).
- SW팀에 넘길 인터페이스의 전체 목록(토픽, 서비스, action)은 정해지지 않았습니다. 지금은 위 표처럼 실제로 쓰는 것만 둡니다.
