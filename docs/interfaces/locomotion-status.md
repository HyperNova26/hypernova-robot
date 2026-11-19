# 로봇 상태 토픽 인터페이스 (`/locomotion/status`)

2026-11-20 기준 초안입니다(G-006). 팀 간 합의를 받은 확정 인터페이스가 아니라, 구현한 내용과 시험한 범위를 그대로 적은 문서입니다. 상태 코드 표와 메시지 정의는 확정 전에 SW팀과 맞춥니다. 메시지 타입은 `hn_interfaces/msg/LocomotionStatus`입니다(2026-11-18에 표준 `DiagnosticArray`에서 바꿈). 번호, 이름, 이유 문자열은 [ADR-0004](../decisions/0004-locomotion-status-topic.md)(Proposed)로 올렸습니다([알려진 한계와 미결정](#알려진-한계와-미결정) 참고).

## 무엇을 하는가

로봇의 저수준 상태(자세, 속도, 지면 정보)를 정지·보행·기울어짐·낙상 같은 상위 상태 하나와 이유로 요약해서 ROS 토픽으로 내보냅니다. SW팀 앱의 표시나 대처 판단에 쓰는 것이 목적입니다.

- 판정 코어는 numpy와 pyyaml만 씁니다. MuJoCo, Isaac Sim, Isaac Lab, 실기에서 같은 코드가 돌 수 있게 ROS와 시뮬레이터에 의존하지 않습니다.
- 현재 이 토픽을 내보내는 곳은 시뮬레이터 시험 하네스(`policies/route_walk/state_scenarios.py`)뿐입니다. 실기에서 같은 입력을 만들어 코어에 넣는 노드는 아직 없습니다.
- 판정 코드는 `ros_pkgs/hn_robot_state/`에 있습니다. `package.xml`이 없는 순수 Python 모듈이라 `colcon build`나 `ros2 run` 대상이 아닙니다.
- 메시지 정의는 `ros_pkgs/hn_interfaces/`에 있습니다. 이쪽은 ROS 2 패키지이고 한 번 빌드해야 합니다([빌드](#빌드)).

## 한눈에 보기

| 항목 | 값 |
| --- | --- |
| 토픽 | `/locomotion/status` |
| 타입 | `hn_interfaces/msg/LocomotionStatus` ([정의](../../ros_pkgs/hn_interfaces/msg/LocomotionStatus.msg)) |
| QoS | reliable, transient_local, KEEP_LAST, depth 1 |
| 발행 시점 | 상태가 바뀌면 즉시, 그 밖에는 10 Hz heartbeat로 마지막 보고를 다시 냅니다 |
| 입력이 끊겼을 때 | heartbeat가 `STALE_INPUT`을 냅니다 |
| `robot_id` | `hn_v1_hyper`(v1 로봇) 또는 `hn_v0_go2`(v0). `run_route.sh`가 `POLICY`에 맞춰 넘깁니다 |

S-005의 `/localization/status`와 짝이 되도록 이름 규칙과 숫자 enum 방식을 따랐습니다.

## 빌드

`hn_interfaces`는 저장소 최상위에서 한 번 빌드합니다. 컨테이너에서 하고, `hn:sim` 기본 환경의 `VIRTUAL_ENV`(Isaac Lab venv)에는 메시지 생성에 필요한 `empy`가 없어서 해제하고 빌드합니다. 결과는 named volume에 남고, `hn`으로 연 모든 셸과 프로세스(세 시뮬레이터, `foxglove_bridge`)가 자동으로 씁니다([docker/README.md](../../docker/README.md#ros-패키지-빌드-colcon)).

```bash
./docker/hn sim bash -c 'unset VIRTUAL_ENV && colcon build --base-paths ros_pkgs'
```

받는 쪽도 `hn_interfaces`가 있어야 이 토픽을 읽습니다. 없으면 `ros2 topic echo`가 타입을 못 찾고 `foxglove_bridge`가 이 채널을 광고하지 않습니다.

## 상태 코드

`code`와 `state`(이름)가 같은 상태를 가리킵니다. 앱은 `code`로 분기하고 `state`는 표시용으로 씁니다. 언제 어느 상태가 되는지는 [판정 기준](#판정-기준)에 있습니다.

| code | 이름 | `severity` | `reason` | 뜻 |
| --- | --- | --- | --- | --- |
| 0 | `INITIALIZING` | OK (0) | `calibrating` | 시작 직후. 서 있는 높이 `h0`를 재는 중 |
| 1 | `STANDING` | OK (0) | `idle` | 서 있음 |
| 2 | `WALKING` | OK (0) | `moving` | 걷거나 제자리에서 도는 중 |
| 3 | `TILTING` | WARN (1) | `tilt` | 크게 기울었지만 넘어지지는 않음 |
| 4 | `SLIPPING` | - | - | 번호만 예약. 아직 내보내지 않음 |
| 5 | `FALLEN` | ERROR (2) | `tilt`, `off_ground`, `low_height` | 넘어짐. 이유는 어느 조건으로 판정했는지 |
| 6 | `STALE_INPUT` | STALE (3) | `no_input` | 판정기가 입력을 못 받음(로봇이 아니라 판정기의 상태) |

`severity`는 `LocomotionStatus.SEVERITY_*` 상수입니다(OK 0, WARN 1, ERROR 2, STALE 3). `diagnostic_msgs/DiagnosticStatus.level`과 같은 값입니다. 코드도 `LocomotionStatus.CODE_*` 상수로 있습니다. `TILTING`과 `FALLEN`이 같은 `reason` 문자열 `tilt`를 쓰지만 뜻은 `code`로 구분합니다(`TILTING`은 35°에서 70° 사이, `FALLEN`의 `tilt`는 70° 초과).

## 판정 기준

2026-11-20 기준입니다. 판정기(`ros_pkgs/hn_robot_state/hn_robot_state/core.py`)는 정책 주기(50 Hz)마다 입력 하나를 받아 상태 하나를 정합니다. 숫자는 모두 `ros_pkgs/hn_robot_state/config/thresholds.yaml`에 있고, 값을 바꾸면 `core.py`의 `Thresholds` 기본값도 같이 바꿉니다(단위 시험이 둘이 같은지 검사). 근거는 시뮬레이터(v1 로봇, PAIR360 맵 v3) 측정이고 실기에서는 확인하지 않았습니다. 실기 IMU 노이즈와 모터 지연은 반영되지 않았으므로 실기에 올리기 전에 다시 맞춰야 합니다.

### 입력에서 계산하는 값

입력은 정책이 받는 상태 dict와 같습니다(정책 base 프레임: +X 전방, +Y 좌, +Z 상).

| 값 | 계산 | 입력 |
| --- | --- | --- |
| 기울기 `tilt_deg` | 몸통 z축과 수직 사이 각도. 방향과 상관없음(옆, 앞, 뒤집힘 모두) | `projected_gravity_b` |
| `roll_deg`, `pitch_deg` | ZYX 오일러. 양의 roll은 오른쪽이 내려감, 양의 pitch는 앞이 내려감 | `projected_gravity_b` |
| 수평 속도 `speed_mps` | 몸통 속도의 수평 크기 | `base_lin_vel_b` |
| 명령 크기 | 선속도 `hypot(vx, vy)`, 각속도 `wz`의 절댓값 | `command` |
| 높이 `height_m` | 몸통 z − 몸통 아래 height scan 중심 3×3 칸의 중앙값 | `base_pos_z`, `height_hits_z`(없으면 기울기만으로 판정) |
| 지면 있음 | 중심 3×3 칸 중 유효한 칸(값이 100 m 미만)이 50% 이상 | `height_hits_z` |

### 판정 순서

매 입력마다 위에서부터 봅니다. 먼저 걸리는 것이 이깁니다.

1. 입력이 끊기면(wall 시간 0.5 s 초과) 발행 쪽 heartbeat가 `STALE_INPUT`을 냅니다. 판정 상태 자체는 바꾸지 않아서, 입력이 돌아오면 끊기기 전 상태로 바로 돌아갑니다.
2. `FALLEN`이 아닌 모든 상태(`INITIALIZING` 포함)에서 낙상 조건을 먼저 봅니다. 0.2 s 이어지면 `FALLEN`입니다.
3. `FALLEN`이면 해제 조건만 봅니다.
4. `INITIALIZING`이면 초기화가 끝났는지만 봅니다. 이 동안에는 `TILTING`으로 가지 않습니다.
5. `TILTING`이면 기울기가 돌아왔는지만 봅니다.
6. `STANDING`이나 `WALKING`이면 먼저 `TILTING` 조건을 보고, 아니면 정지/보행을 나눕니다.

입력 시간이 거꾸로 가면 처음(`INITIALIZING`)부터 다시 시작하고, 0.5 s보다 크게 건너뛰면 진행 중인 지속 시간 계산만 다시 시작합니다(상태는 유지).

### 상태별 조건

| 상태 | 들어가는 조건 | 나오는 조건 |
| --- | --- | --- |
| `INITIALIZING` | 시작할 때. 또는 `h0`를 못 잰 채 `FALLEN`에서 풀릴 때 | 기울기 < 15°, 수직 속도 < 0.2 m/s, 지면 있음이 1.0 s 이어지면 끝납니다. 그 동안 높이의 중앙값을 `h0`로 쓰고 `STANDING`이나 `WALKING`으로 갑니다 |
| `STANDING` | 명령 선속도 < 0.05 m/s, 명령 각속도 < 0.05 rad/s, 몸통 속도 < 0.10 m/s가 모두 0.5 s 이어짐 | `WALKING`, `TILTING`, `FALLEN` 조건 |
| `WALKING` | 명령 선속도 ≥ 0.10 m/s, 명령 각속도 ≥ 0.10 rad/s, 몸통 속도 ≥ 0.15 m/s 중 하나가 0.1 s 이어짐 | `STANDING`, `TILTING`, `FALLEN` 조건. 정지와 보행 기준 사이의 값에서는 상태를 유지합니다(히스테리시스) |
| `TILTING` | `STANDING`이나 `WALKING`에서 기울기 > 35°가 0.3 s 이어짐 | 기울기 < 30°가 0.5 s 이어지면 `STANDING`이나 `WALKING`. 낙상 조건이 먼저 걸리면 `FALLEN` |
| `FALLEN` | 아래 셋 중 하나가 0.2 s 이어짐. 겹치면 `tilt`, `off_ground`, `low_height` 순서로 이유를 정함. `tilt`: 기울기 > 70°. `off_ground`: 지면 없음(지형 밖, 추락). `low_height`: 높이 < 0.5 × `h0`(주저앉음, 기울기가 작아도 걸림) | 기울기 < 25°, 지면 있음, 높이 > 0.8 × `h0`(높이 입력이 있을 때)가 1.0 s 이어지면 풀립니다. 로봇이 스스로 일어나도 풀립니다 |
| `STALE_INPUT` | 입력이 wall 시간으로 0.5 s 넘게 안 옴 | 입력이 다시 오면 바로 |

### 기준값과 근거

| 기준 | 값 | 근거 |
| --- | --- | --- |
| 낙상 기울기 | 70° | 재생기(MuJoCo, Isaac Sim)가 원래 넘어짐으로 보고 실행을 끝내던 값과 같습니다. 정상 보행 최대 12.7°에서 13.6°라 여유가 56° 넘습니다 |
| 낙상 낮은 높이 | 0.5 × `h0` | 정상 보행 최저 0.95 × `h0`, 주저앉은 뒤 0.38에서 0.43 × `h0`였습니다. 둘 사이에 있습니다 |
| 지면 없음 | 중심 3×3 칸 중 유효 50% 미만 | 경로 A 정상 보행에서 0프레임이었습니다. 지형 가장자리는 확인하지 않았습니다 |
| 낙상 진입 지속 | 0.2 s | 순간 튐을 무시하려는 값입니다(0.1 s 튐은 무시되는 것을 단위 시험이 확인). 고장부터 `FALLEN`까지 0.28 s에서 0.66 s 중 판정기 몫이 이 0.2 s이고 나머지는 실제로 쓰러지는 시간입니다 |
| 낙상 해제 | 25°, 0.8 × `h0`, 1.0 s | 진입(70°, 0.5 × `h0`, 0.2 s)보다 엄해서 확실히 다시 섰을 때만 풀립니다. `reset`으로 다시 세우면 1.0 s 뒤에 풀렸습니다(세 시뮬레이터 모두) |
| 기울어짐 경고 | 35°에 0.3 s, 해제 30°에 0.5 s | 정상 보행 최대 13.6°, 99번째 백분위수 약 11°라 오탐 여유가 20° 넘습니다. `tilt` 고장은 약 42°에 머물러 확실히 걸리고, 약한 뒤집기(버티고 일어남)는 50°에서 61°까지 갔다가 돌아옵니다. 해제가 5° 낮아서 35° 근처에서 상태가 깜빡이지 않습니다. 해제 30°는 낙상 해제 25° 이상이어야 합니다(낙상에서 풀리자마자 `TILTING`이 되지 않게) |
| 정지·보행 | 명령 0.05/0.10, 속도 0.10/0.15, 0.5 s/0.1 s | 시뮬레이션 로그로 정한 초기값입니다. 경로 추종기의 명령(정지 0, 보행 0.5 m/s, 제자리 회전 최대 0.8 rad/s)과 멀리 떨어져 있습니다. 시험에서 대기 중 `STANDING` 100%, 걷는 명령 뒤 0.10 s에 `WALKING`이었습니다. 보행 진입(0.1 s)이 정지 진입(0.5 s)보다 짧아서, 걷다가 잠깐 느려져도 `STANDING`이 되지 않습니다 |
| 초기화 | 15°, 0.2 m/s, 1.0 s | 시작할 때 지면 위 0.4 m에서 떨어뜨리므로 착지해 자리 잡을 때까지 기다립니다. 초기화는 1.18 s에서 1.46 s에 끝났습니다. `h0`는 시뮬레이터와 모델마다 달라(0.24 m에서 0.34 m) 절대값 대신 스스로 잽니다. 실기에서 서 있는 높이를 알면 `nominal_height_m`으로 줄 수 있습니다 |
| 입력 끊김 | 0.5 s (wall) | 정책 25스텝입니다. 시뮬레이터가 멈춰도 알 수 있게 시뮬레이션 시간이 아니라 wall 시간으로 잽니다 |

## 메시지 필드

타입이 있는 필드입니다. 값을 알 수 없는 실수 필드(측정값)는 `NaN`입니다. 정의 파일이 기준이고 아래는 요약입니다.

| 필드 | 타입 | 단위 | 설명 |
| --- | --- | --- | --- |
| `header.stamp` | `Time` | - | 발행 시각. 시스템 시간입니다([시간 규칙](#시간-규칙)). `frame_id`는 비어 있습니다 |
| `code` | `uint8` | - | 위 상태 코드(`CODE_*`) |
| `state` | `string` | - | 상태 이름. 표시용 |
| `severity` | `uint8` | - | `SEVERITY_*` |
| `reason` | `string` | - | 위 표의 이유. 표시용 |
| `since_s` | `float32` | s | 이 상태가 시작된 뒤 지난 시간. `STALE_INPUT`은 입력이 끊긴 wall 시간 |
| `robot_id` | `string` | - | 로봇 식별자 |
| `sim_time_s` | `float64` | s | 판정에 쓴 입력의 시간. 시뮬레이터에서는 시뮬레이션 시간입니다 |
| `tilt_deg` | `float32` | deg | 중력 방향 기준 총 기울기 |
| `roll_deg`, `pitch_deg` | `float32` | deg | roll은 x축, pitch는 y축 둘레(ZYX 오일러). 양의 pitch는 앞이 내려간 상태입니다 |
| `speed_mps` | `float32` | m/s | 몸통 수평 속도 |
| `height_m` | `float32` | m | 몸통 아래 지면에서 몸통까지 높이(height scan이 있을 때) |

좌표는 정책 base 프레임입니다(+X 전방, +Y 좌, +Z 상).

`FALLEN`일 때 `ros2 topic echo`로 보이는 출력입니다. 값은 형식을 보이려고 정한 예시이며 측정값이 아닙니다. `float32` 필드는 `float64`로 출력되며 끝자리가 길게 나옵니다.

```text
header:
  stamp:
    sec: 1795013939
    nanosec: 259685947
  frame_id: ''
code: 5
state: FALLEN
severity: 2
reason: tilt
since_s: 0.0
robot_id: hn_v1_hyper
sim_time_s: 8.28
tilt_deg: 117.04000091552734
roll_deg: 116.30000305175781
pitch_deg: 8.100000381469727
speed_mps: 0.0
height_m: 0.07100000232458115
```

## 시간 규칙

ROS 시계와 시뮬레이터 시계가 어긋나는 문제를 피하려고 이렇게 정했습니다.

- `header.stamp`는 노드 시계가 아니라 시스템 시간(`time.time_ns()`)입니다. 시뮬레이션 시간은 `sim_time_s`로 따로 싣습니다.
- 세 시뮬레이터는 `/clock`(`rosgraph_msgs/msg/Clock`)을 같은 방식으로 냅니다. 정책 스텝(50 Hz)마다 그 스텝의 시뮬레이션 시간을 내며, `use_sim_time=true`인 노드(Nav2, RViz 등)가 이 시간을 따릅니다. `sim_time_s`와 같은 시간입니다.
- 시뮬레이터에서 `header.stamp`도 시뮬레이션 시간으로 쓰려면 하네스 옵션 `--stamp sim`을 줍니다(`STATE_ARGS="--stamp sim"`). 기본값은 위 규칙대로 시스템 시간이고, 바꿀지는 SW팀과 정합니다([ADR-0004](../decisions/0004-locomotion-status-topic.md)의 다시 볼 조건).
- 발행 노드는 `use_sim_time=False`를 강제합니다. `true`이면 `/clock`이 없거나 시뮬레이터가 멈췄을 때 ROS 시계가 멈춰 heartbeat 타이머가 돌지 않고, 입력이 끊겨도 `STALE_INPUT`을 낼 수 없습니다.
- 발행 노드는 전용 rclpy Context와 전용 스레드를 씁니다. 같은 프로세스의 다른 rclpy 사용(예: Isaac Sim의 ROS 확장)과 전역 상태를 나누지 않습니다.
- 입력 시간이 거꾸로 가면 판정기를 초기화합니다. 0.5 s보다 크게 건너뛰면 진행 중인 지속 시간 계산만 다시 시작하고 상태는 유지합니다.
- 입력 끊김은 wall 시간으로 감시합니다. 시뮬레이션이 멈추거나 느려져도 끊김을 알 수 있어야 하기 때문입니다.

## 구독하는 쪽

`hn_interfaces`가 빌드되어 있어야 합니다([빌드](#빌드)). `code`와 `severity`는 정수입니다.

```python
import rclpy
from hn_interfaces.msg import LocomotionStatus
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                 history=HistoryPolicy.KEEP_LAST, depth=1)

def on_status(msg: LocomotionStatus) -> None:
    if msg.code == LocomotionStatus.CODE_FALLEN:
        print("넘어짐:", msg.reason)
    print(msg.code, msg.state, msg.reason, msg.severity)

rclpy.init()
node = Node("status_listener")
node.create_subscription(LocomotionStatus, "/locomotion/status", on_status, QOS)
rclpy.spin(node)
```

`hn:sim` 컨테이너에서 명령줄로 보려면 이렇게 합니다. `transient_local`을 지정하면 붙은 시점의 마지막 상태를 바로 받습니다.

```bash
./docker/hn sim ros2 topic echo /locomotion/status --qos-durability transient_local --qos-reliability reliable
```

대시보드 쪽 경로는 S-005 선례(`foxglove_bridge`가 ROS 2 토픽을 WebSocket으로 내보냄)를 따를 수 있습니다. `hn_interfaces`가 빌드된 환경에서 `foxglove_bridge`(3.6.0)는 이 토픽을 `hn_interfaces/msg/LocomotionStatus`, cdr 인코딩, 스키마 2,823자와 함께 광고하는 것을 확인했습니다(2026-11-18, WebSocket 클라이언트로 `advertise` 메시지를 읽음). 프레임 전달과 Foxglove 패널 표시는 이 타입으로 다시 확인하지 않았습니다.

## 직접 실행해 보기

저장소 최상위의 데스크톱 터미널에서 실행합니다. 컨테이너(`hn:sim`)는 스크립트가 알아서 씁니다. 로봇·정책·지도·경로는 `tools/demo/run_route.sh`의 기본값(v1 로봇, PAIR360 맵 v3, 경로 A)을 따릅니다. 필요한 데이터는 `./tools/demo/run_route.sh check`로 확인하고, `hn_interfaces`는 먼저 빌드합니다([빌드](#빌드)).

### 걸으면서 고장 넣기

터미널 1에서 시뮬레이터를 띄우고, 로봇이 걷는 동안 터미널 2의 컨테이너 셸에서 고장 주입 서비스를 직접 부릅니다. 시뮬레이터는 `mujoco`, `isaacsim`, `isaaclab` 중 하나입니다. `run_route.sh`는 기본으로 재생기를 시험 하네스로 감싸 판정·발행·서비스를 켭니다(2026-11-20부터. `STATE=0`을 앞에 붙이면 하네스 없이 걷기만 합니다).

```bash
# 터미널 1
./tools/demo/run_route.sh mujoco
# 터미널 2: 컨테이너 셸을 엽니다(ROS 환경과 hn_interfaces가 잡혀 있음)
./docker/hn sim
```

터미널 2의 컨테이너 셸에서 부릅니다.

```bash
ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: tilt}"       # 옆으로 기울이기 -> TILTING
ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: clear}"      # 진행 중인 고장을 모두 끝냄(자세는 그대로)
ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: reset}"      # 고장을 끝내고 로봇을 그 자리에 다시 세움 -> 1 s 뒤 WALKING
ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: stale, duration_s: 3}"   # 판정기 입력 3 s 끊기 -> STALE_INPUT
ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: flip}"       # 옆으로 뒤집기 -> FALLEN
ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: collapse}"   # 주저앉기 -> FALLEN
ros2 service call /sim/inject_fault hn_interfaces/srv/InjectFault "{kind: push, magnitude: 200, direction_deg: 90}"   # 왼쪽으로 200 N, 0.2 s 밀기
ros2 topic echo /locomotion/status                                                      # 판정 상태 보기(10 Hz)
ros2 interface show hn_interfaces/srv/InjectFault                                       # 요청·응답 필드와 설명
```

- 요청 필드는 `kind`, `magnitude`, `duration_s`, `direction_deg`이고, 빼면 0입니다. `magnitude`는 flip의 각속도 [rad/s], tilt의 목표 roll [deg](양수는 오른쪽, 음수는 왼쪽이 내려감), push의 힘 [N]이고 0이면 기본값입니다. `duration_s`가 0이면 `clear`를 보낼 때까지 이어지고(push는 0.2 s), 값을 주면 그 시간 뒤에 저절로 끝납니다. `direction_deg`는 push의 방향으로, 넣는 순간 로봇이 보는 방향 기준입니다(0 앞, 90 왼쪽, 180 뒤, -90 오른쪽). 숫자는 정수로 적어도 됩니다.
- `clear`는 진행 중인 고장(collapse, tilt, stale, push)을 멈출 뿐 로봇을 일으키지 않습니다. 지금 정책은 누운 상태에서 일어나는 법을 학습하지 않았으므로, 넘어진 뒤에는 `reset`으로 다시 세웁니다. `reset`은 로봇을 지금 x, y의 지면 위 0.4 m에 지금 방향으로 똑바로 놓고(시작할 때와 같은 방식) 관절을 기본 자세로 돌린 뒤 경로를 이어서 걷게 합니다. 판정기는 그대로 두므로 `FALLEN`은 다시 선 지 1 s 뒤에 풀립니다.
- 응답의 `accepted`가 `True`면 접수된 것이고, 시뮬레이션 루프가 다음 정책 스텝에 적용합니다. 시뮬레이터가 아직 뜨지 않았으면 `ros2 service call`은 `waiting for service to become available...`에서 기다립니다.
- 판정 상태는 MuJoCo 창 왼쪽 위 글자, Isaac Sim과 Isaac Lab은 작은 창 `Locomotion state (G-006)`에 나옵니다. 상태 전환과 고장 시작·끝은 터미널 1에 한 줄씩 나옵니다.
- 로봇이 걷기 시작한 뒤에 넣습니다. 판정기는 시작 뒤 약 1.2~1.5 s 동안 초기화(`INITIALIZING`)하며, 그 사이에는 `TILTING`, `STANDING`, `WALKING`을 내지 않습니다(`FALLEN`은 냄). 초기화 중에 넣으면 터미널 1에 주의가 나옵니다.
- 창을 닫거나 Ctrl+C로 끝내면, 넣은 고장마다 기대 상태가 나왔는지 PASS/FAIL로 요약합니다.
- 같은 PC에서 시뮬레이터를 둘 이상 띄우면 서비스와 토픽 이름이 겹쳐 요청이 다른 시뮬레이터로 갈 수 있습니다. 그때는 `ROS_DOMAIN=<번호> ./tools/demo/run_route.sh ...`로 띄우고, 서비스를 부르는 셸에서도 `export ROS_DOMAIN_ID=<같은 번호>`를 합니다.
- 시뮬레이터의 ROS 탐색은 이 PC 안으로 제한합니다(`ROS_LOCAL=1`, 기본). 같은 `ROS_DOMAIN_ID`를 쓰는 다른 PC에 시험용 `FALLEN`이 퍼지지 않게 하려는 것이고, 같은 PC의 컨테이너 셸에서는 그대로 보입니다(2026-11-20 확인).

고장마다 하는 일과 기대 상태입니다. 세 시뮬레이터가 같은 방식으로 넣습니다.

| 고장 | 하는 일 | 기대 상태 |
| --- | --- | --- |
| `collapse` | 정책 출력을 주저앉는 자세(thigh 1.6 rad, calf -2.7 rad)로 바꿉니다 | `FALLEN`(`low_height`) |
| `flip` | 몸통 roll 각속도를 한 번 더합니다. 기본값은 MuJoCo 36, Isaac Sim 40, Isaac Lab 42 rad/s입니다 | `FALLEN`(`tilt`). 로봇이 한 바퀴 돌아 다시 서면 풀립니다 |
| `stale` | 판정기에 입력을 주지 않습니다. 로봇은 계속 걷습니다 | `STALE_INPUT` |
| `tilt` | 한쪽 다리를 접고 반대쪽 다리를 펴서 몸통을 옆으로 기울입니다. 다리가 넘어지지 않게 약 2 s에 걸쳐 접힙니다 | `TILTING`. 끝나면 `WALKING` |
| `reset` | 고장을 모두 끝내고 로봇을 그 자리에 다시 세웁니다(고장이 아니라 시험을 이어 가기 위한 요청) | 1 s 뒤 `FALLEN`이 풀리고 `WALKING` |
| `push` | 몸통 질량 중심에 수평 외력을 겁니다(기본 100 N, 0.2 s). 세 시뮬레이터 모두 world 좌표계의 같은 힘입니다 | 힘에 따라 다릅니다. 버티면 `WALKING`(크게 흔들리면 잠깐 `TILTING`), 못 버티면 `FALLEN`. 요약에는 PASS/FAIL 대신 결과(INFO)가 나옵니다 |

### 고장 예약과 자동 검사

`FAULT`를 주면 `AT` 초(기본 8)에 고장을 넣고, 고장이 끝나고 4 s 뒤에 요약을 내고 끝납니다. `HEADLESS=1`이면 창 없이 돕니다.

```bash
FAULT=tilt ./tools/demo/run_route.sh isaacsim                           # 창으로 보기
FAULT=collapse AT=20 HEADLESS=1 ./tools/demo/run_route.sh isaaclab      # 창 없이 자동 검사
HEADLESS=1 STAND_S=5 ./tools/demo/run_route.sh mujoco                   # 고장 없이 경로 끝까지(오탐 검사). 처음 5 s는 서 있다가 출발
HEADLESS=1 STAND_S=20 UNTIL=20 STATE_ARGS="--expect stand" ./tools/demo/run_route.sh mujoco   # 20 s 서 있기
```

- 환경 변수는 `run_route.sh` 머리말에 있습니다. `FAULT_S`(지속 시간), `UNTIL`(끝내는 시뮬레이션 시간), `STAND_S`(처음 서 있는 시간, 0 또는 3 이상), `ROS`, `LOG`, `STATE_ARGS`(하네스 옵션을 그대로 넘김, 예: `--tilt-deg -40`, `--stamp sim`)를 씁니다.
- 창 없는 모드는 ROS를 기본으로 끄고 최대 속도로 돕니다. `ROS=1`을 주면 켜고, 서비스로 고장을 넣을 수 있게 실시간으로 늦춰 돕니다. 창 모드는 ROS가 기본으로 켜집니다.
- 하네스는 넘어진 뒤를 관찰하려고 재생기의 넘어짐 종료(기울기 70°)를 뺍니다. 창 없는 모드에서 고장을 넣지 않았는데 `FALLEN`이 3 s 이어지면 끝냅니다(예전처럼 넘어지면 끝나게). 창 모드는 창을 닫을 때까지 이어집니다.
- 판정 기록은 JSONL로 컨테이너 `/data/state_logger/`에 남습니다(호스트는 데이터 폴더의 `state_logger/`). `header`, `transition`, `sample`, `fault_start`, `fault_end`, `summary` 줄로 이뤄집니다.
- 요약의 PASS는 "고장 전 오탐이 없고, 넣은 고장마다 기대 상태가 정해진 시간 안에 나왔다"는 뜻이지 "도착했다"는 뜻이 아닙니다.
- 2026-11-18까지 쓰던 시나리오 스크립트 9개(`tools/demo/state_<walk|collapse|flip>_<시뮬레이터>.sh`)와 내부 실행기(`_state_run.sh`)는 이 방식으로 합치고 지웠습니다(2026-11-19). 그 스크립트들은 v0 로봇과 예전 데모 지형에 고정돼 있었습니다.

단위 시험은 `hn:sim` 컨테이너에서 이렇게 돌립니다(`hn_robot_state` 86개, `hn_interfaces` 4개).

```bash
./docker/hn sim bash -c 'cd /workspace/hypernova && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/hn-venv/bin/python -m pytest -p no:cacheprovider ros_pkgs/hn_robot_state/test ros_pkgs/hn_interfaces/test -q'
```

## 시험 결과

2026-11-19 기준입니다. 환경은 `hn:sim` 컨테이너(Ubuntu 24.04, ROS 2 Jazzy, `rmw_fastrtps_cpp`, UDP 전용 `docker/fastdds.xml`), 로봇은 v1(HYPER)과 Rough GT 정책 `model_2998`, 지도는 PAIR360 맵 v3의 경로 A(101 m)이고, 시뮬레이터 보정은 `run_route.sh` 기본값(켬, [시뮬레이터 차이](../development/sim-parity.md))입니다. 고장은 8 s에 예약해 창 없는 모드로 넣었습니다(`FAULT=<종류> AT=8 HEADLESS=1 ROS=0`). 시간은 시뮬레이션 시간이고, 고장을 넣은 때부터 잽니다.

| 시험 | MuJoCo | Isaac Sim | Isaac Lab |
| --- | --- | --- | --- |
| 경로 A 정상 보행 중 `FALLEN`, `TILTING`, `STALE_INPUT` 오탐 | 0프레임 | 0프레임 | 0프레임 |
| 정상 보행 기울기 최대 / 99번째 백분위수 | 12.7° / 10.6° | 13.6° / 11.1° | 12.9° / 11.1° |
| 정상 보행 높이/`h0` 최저 | 0.95 | 0.95 | 0.97 |
| 경로 A 도착 시각 | 211.4 s | 209.8 s | 207.5 s |
| `INITIALIZING` 끝 | 1.18 s | 1.46 s | 1.22 s |
| 주저앉기 → `FALLEN`(`low_height`) | 0.66 s | 0.36 s | 0.36 s |
| 옆으로 뒤집기 → `FALLEN`(`tilt`) (충격) | 0.28 s (36 rad/s) | 0.28 s (40 rad/s) | 0.44 s (42 rad/s) |
| 입력 끊김 → `STALE_INPUT` / 입력 복귀 → 해제 | 0.34 s / 0.00 s | 0.18 s / 0.00 s | 0.26 s / 0.00 s |
| 옆으로 기울이기 → `TILTING` (최대 기울기) | 1.68 s (42°) | 1.76 s (42°) | 1.66 s (42°) |
| 기울이기가 끝난 뒤 → `WALKING` | 0.58 s | 0.58 s | 0.56 s |
| 옆으로 밀기 100 N × 0.2 s (최대 기울기) | 버팀 (19°) | 버팀 (18°) | 버팀 (17°) |
| 옆으로 밀기 200 N × 0.2 s → `FALLEN`(`tilt`) | 0.58 s | 0.60 s | 0.62 s |

- 도착 시각은 하네스 없이 잰 [시뮬레이터 차이](../development/sim-parity.md)의 값과 같습니다. MuJoCo 평지 1000 스텝의 정책 입출력 기록(`--trace`)도 하네스가 있을 때와 없을 때 바이트까지 같았습니다(2026-11-20). 판정기와 하네스는 물리에 영향을 주지 않습니다.
- `FALLEN`과 `TILTING`의 판정기 몫은 각각 0.20 s, 0.30 s(debounce)이고, 나머지는 로봇이 실제로 쓰러지거나 기우는 시간입니다. 기울이기는 넘어지지 않게 다리를 약 2 s에 걸쳐 접습니다.
- 기울이기는 한쪽 다리를 다 접고 반대쪽을 다 펴도 v1이 약 42°까지만 기웁니다. 목표 45°는 그 자세에 머문다는 뜻입니다. 처음 만든 빠른 접기(1 s)는 걷던 관성으로 MuJoCo에서 넘어졌습니다(113°).
- 뒤집기는 같은 몸체 프레임 충격이라도 시뮬레이터마다 결과가 다릅니다. v1이 누운 채 남은 범위는 MuJoCo 32~40, Isaac Sim 36~44, Isaac Lab 40 이상 rad/s였고(8 s에 넣음), 더 약하면 버텨 일어나고(이때는 잠깐 `TILTING`), 더 세면 한 바퀴 돌아 다시 섭니다. 그래서 `run_route.sh`가 시뮬레이터별 기본값을 넘깁니다. 같은 값이라도 넣는 순간의 걸음에 따라 한 바퀴 돌아 일어날 수 있습니다(MuJoCo 36 rad/s를 34 s에 넣었을 때).
- `reset`(2026-11-20, 서비스로): 세 시뮬레이터 모두 뒤집기와 주저앉기 뒤에 다시 세우면 1.02 s 뒤 `FALLEN`이 풀리고 경로를 이어 걸었습니다.
- 밀기는 2026-11-20에 쟀습니다(왼쪽, 8 s에 넣음). 세 시뮬레이터가 거의 같게 반응했습니다. MuJoCo에서 옆으로 0.2 s 밀 때 135 N까지는 버티고 150 N부터 넘어졌고, 앞으로는 300 N에도 버텼습니다. 기본값 100 N은 버티는 쪽입니다. 서비스로 넣는 밀기(방향 지정 포함)는 MuJoCo에서 확인했습니다.
- 창 모드는 세 시뮬레이터에서 짧게 돌려(MuJoCo 기울이기, Isaac Sim 입력 끊김, Isaac Lab 주저앉기) 화면 표시 코드가 오류 없이 돌고 판정이 같은 것을 확인했습니다. 화면에 표시된 글자는 사람이 보고 확인하지 않았습니다.
- ROS(2026-11-19, MuJoCo, 같은 컨테이너의 다른 프로세스): 한 실행에서 서비스로 기울이기, 입력 끊김, 주저앉기를 차례로 넣어 모두 PASS였고, `/locomotion/status`에 `TILTING`이 code 3, severity 1로 나왔습니다(466건 발행). 왼쪽 기울이기를 `clear`로 끝내기와 서비스로 넣은 뒤집기도 확인했습니다. `/clock`은 50.0 Hz였습니다. Isaac Sim과 Isaac Lab의 Kit 프로세스 안에서도 상태를 발행했고(창 모드, 328건, 227건), 창 없는 모드에서 서비스로 기울이기와 입력 끊김을 넣어 둘 다 적용되는 것을 확인했습니다.

2026-11-15에 v0 로봇과 예전 데모 지형으로 잰 이전 결과에서는 Isaac Sim의 정상 보행 기울기가 최대 46.9°였습니다(MuJoCo 12.8°, Isaac Lab 13.2°). v1과 맵 v3에서는 세 시뮬레이터가 비슷합니다. 그 사이 로봇, 지도, Isaac Sim 재생기의 시작 조건([시뮬레이터 차이](../development/sim-parity.md))이 모두 바뀌어서 무엇 때문에 줄었는지는 따로 확인하지 않았습니다.

## 알려진 한계와 미결정

- **실기 연결 없음.** 실기의 IMU와 엔코더로 입력 dict(`projected_gravity_b`, `base_lin_vel_b`, `command` 등)를 만들어 코어에 넣는 노드가 없습니다. 입력 dict의 키는 정책 러너가 받는 것과 같습니다.
- **`hn_interfaces`는 이 저장소에 새로 만든 패키지입니다(2026-11-18).** S-005가 쓰는 `hn_interfaces/LocalizationStatus`는 정의가 어디에도 없어서(S-006 대시보드 PR #24가 필드를 가정함) 이 패키지에 같이 만들었습니다(2026-11-19). 정의는 S-005 담당자가 정하기 전의 제안이라 알려야 합니다. S-005 토픽 전체 표는 [hn_interfaces README](../../ros_pkgs/hn_interfaces/README.md)에 있습니다.
- **코드 표는 팀 간 결정입니다.** 상태 번호와 이유 문자열은 SW팀 앱이 의존하게 되므로 [ADR-0004](../decisions/0004-locomotion-status-topic.md)로 올렸습니다. 상태는 `Proposed`이고 SW팀이 동의하기 전까지는 확정이 아닙니다. `TILTING`(2026-11-19 추가)도 같습니다.
- **`TILTING` 동안은 정지와 보행을 구분하지 않습니다.** 상태가 하나라서 기울어진 채 걷는지 서 있는지는 `speed_mps`로 봐야 합니다.
- **`TILTING` 기준은 v1과 맵 v3에서만 맞췄습니다.** v0 로봇은 예전 데모 지형의 Isaac Sim에서 정상 보행 중 47°까지 기울어(2026-11-15) `TILTING` 오탐이 납니다. 경사가 더 큰 지형에서도 확인하지 않았습니다.
- **`header.stamp`를 시뮬레이션 시간으로 쓸지는 미결정입니다.** 세 시뮬레이터는 `/clock`을 내지만 상태 메시지의 stamp는 기본이 시스템 시간입니다. Nav2처럼 `use_sim_time`을 쓰는 노드와 맞추려면 `--stamp sim`이 있고, 바꿀지는 SW팀과 정합니다.
- **걸린 로봇은 감지하지 못합니다.** 명령은 전진인데 속도가 0이어도 `WALKING`으로 남습니다(`SLIPPING` 미구현).
- **스스로 일어나는 전복은 `FALLEN`이 풀립니다.** `FALLEN` 유지 시간으로 낙상 여부를 판단하면 안 됩니다. 해제 이벤트도 함께 봐야 합니다.
- **낙상 상태로 시작하면 `low_height`를 못 잡습니다.** `h0`를 못 재기 때문입니다(`tilt`, `off_ground`는 작동). 실기에서 서 있는 높이를 알면 `nominal_height_m`을 주면 됩니다.
- **지형 가장자리에서 `off_ground` 오탐이 날 수 있습니다.** 경로 A에서는 나오지 않았지만 다른 지형에서는 확인하지 않았습니다.
- **새 구독자의 첫 수신이 늦을 수 있습니다.** DDS 탐색 때문에 `transient_local`로도 첫 수신까지 0.12 s에서 2.39 s로 편차가 컸습니다(2026-11-15). 구독자가 붙기 전에 발행자가 사라지면 아무것도 받지 못합니다.
- **시험하지 않은 것:** `hn:ros` 이미지(이 PC에 없음), 실제 대시보드나 Foxglove 패널, Isaac Sim과 Isaac Lab에서 서비스로 넣는 주저앉기·뒤집기·밀기, v0 로봇의 새 고장(`tilt`)과 새 뒤집기 충격, 실기.

## 관련 파일

| 경로 | 내용 |
| --- | --- |
| `ros_pkgs/hn_robot_state/hn_robot_state/core.py` | 판정 코어(`StateEstimator`, `StaleWatchdog`) |
| `ros_pkgs/hn_robot_state/hn_robot_state/ros_node.py` | ROS 어댑터(`StatusPublisher`, `report_to_msg`) |
| `ros_pkgs/hn_robot_state/hn_robot_state/jsonl_log.py` | JSONL 기록기 |
| `ros_pkgs/hn_robot_state/config/thresholds.yaml` | 임계값 |
| `ros_pkgs/hn_robot_state/test/` | 단위 시험 |
| `ros_pkgs/hn_interfaces/srv/InjectFault.srv` | 고장 주입 서비스 정의(시뮬레이터 시험용) |
| `policies/route_walk/state_scenarios.py` | 시뮬레이터 시험 하네스(재생기를 수정하지 않고 감싸 판정하고 고장을 넣음) |
| `policies/route_walk/sim_ros.py` | 하네스의 시뮬레이터 쪽 ROS 연결(`/clock`, `/sim/inject_fault`) |
| `tools/demo/run_route.sh` | 실행 스크립트(기본으로 하네스를 거침, `FAULT=<종류>`, `STATE=0`) |
