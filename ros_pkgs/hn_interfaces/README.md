<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# hn_interfaces

2026-11-19 기준입니다. 로봇과 SW팀 앱이 주고받는 ROS 2 message, service, action과 시뮬레이터 시험용 service의 **정의만** 둡니다. 코드는 없습니다. 통신은 Fast DDS를 쓰기로 SW팀과 정했습니다(2026-11-18, `docker/fastdds.xml`).

## 들어 있는 것

이 패키지가 정의하는 메시지입니다.

| 종류 | 이름 | 토픽 | 상태 | 기준 문서 |
| --- | --- | --- | --- | --- |
| message | [`LocalizationStatus`](msg/LocalizationStatus.msg) | `/localization/status` | 제안(2026-11-19). 번호는 S-005 표를 따랐고 필드는 대시보드가 가정한 `header` + `uint8 status`뿐입니다. 아직 아무도 발행하지 않습니다 | S-005 |
| message | [`LocomotionStatus`](msg/LocomotionStatus.msg) | `/locomotion/status` | 제안(ADR-0004 Proposed). 시뮬레이터에서 발행을 확인했습니다 | [인터페이스 문서](../../docs/interfaces/locomotion-status.md), [ADR-0004](../../docs/decisions/0004-locomotion-status-topic.md) |
| service | [`InjectFault`](srv/InjectFault.srv) | `/sim/inject_fault` | 시험용(2026-11-19). 시뮬레이터 하네스만 제공하고 실기에는 없습니다. SW팀 앱이 쓰는 인터페이스가 아닙니다 | [인터페이스 문서의 직접 실행해 보기](../../docs/interfaces/locomotion-status.md#직접-실행해-보기) |

## 고정 토픽 목록

로봇과 SW팀 앱·대시보드가 주고받는 토픽을 한곳에 모은 표입니다. 표준 인터페이스가 있는 것(`cmd_vel`, `odom`, `map`, Nav2의 action 등)은 새로 정의하지 않고 표준 타입을 씁니다. S-005 행은 S-005 인터페이스 그림(`localization-dashboard-interface`)과 PR #24 대시보드 README의 표를 옮긴 것입니다.

| 토픽 | 타입 | 좌표·비고 | 출처 | 정의 |
| --- | --- | --- | --- | --- |
| `/lidar/points` | `sensor_msgs/msg/PointCloud2` | frame `mlx_lidar`. ML-X 센서 드라이버가 냅니다 | S-005 | 표준 |
| `/localization/odometry` | `nav_msgs/msg/Odometry` | `pair360_map` → `mlx_lidar` | S-005 | 표준 |
| `/localization/status` | `hn_interfaces/msg/LocalizationStatus` | 상태 번호 0–5 | S-005 | **이 패키지** |
| `/localization/reference_map` | `sensor_msgs/msg/PointCloud2` | 시작할 때 1회, transient-local(대시보드 README) | S-005 | 표준 |
| `/tf` | `tf2_msgs/msg/TFMessage` | `pair360_map` → `mlx_lidar`, odometry와 같은 시각. LIO 어댑터 내부 TF는 `/tf` 밖 | S-005 | 표준 |
| `/locomotion/status` | `hn_interfaces/msg/LocomotionStatus` | 상태 번호 0–6, QoS reliable + transient_local | G-006 | **이 패키지** |

- S-005의 LIO 어댑터(FAST-LIO2 또는 LiDAR-only)는 교체할 수 있고, 위 고정 토픽만 구독하는 것이 약속입니다. 시뮬레이터도 같은 토픽을 내면 같은 대시보드와 Nav2를 실기와 시뮬레이터에서 그대로 쓸 수 있습니다(계획 중, 아직 구현하지 않았습니다).
- 세 시뮬레이터가 지금 내는 것은 `/locomotion/status`와 `/clock`(시뮬레이션 시간, 정책 주기 50 Hz)이고, 고장 주입 서비스 `/sim/inject_fault`를 엽니다(`tools/demo/run_route.sh`로 띄우면 기본으로 켜짐). S-005 토픽을 내는 쪽은 S-006의 MuJoCo kinematic SIM(PR #24)입니다.

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

- `LocalizationStatus`는 S-005 담당자가 정하기 전에 먼저 만든 제안입니다. 정의가 없던 `hn_interfaces/LocalizationStatus`를 S-006 대시보드가 가정으로 쓰고 있어서, 그 가정에 맞췄습니다. S-005 담당자가 판정 조건과 추가 필드를 정하면 바꿀 수 있고, 필드를 더하는 것은 LIO 어댑터가 발행하기 전에 정하는 편이 쌉니다. 대시보드의 상태 코드 필드 경로 기본값이 `status`라서 이 메시지는 설정을 바꾸지 않고 읽혀야 하지만, 대시보드로 직접 확인하지는 않았습니다.
- SW팀에 넘길 인터페이스의 전체 목록(토픽, 서비스, action)은 정해지지 않았습니다. 지금은 위 표처럼 실제로 쓰는 것만 둡니다.
