# 로봇 상태 토픽 인터페이스 (`/locomotion/status`)

2026-11-15 기준 초안입니다(G-006). 팀 간 합의를 받은 확정 인터페이스가 아니라, 구현한 내용과 시험한 범위를 그대로 적은 문서입니다. 상태 코드 표와 메시지 타입은 확정 전에 SW팀과 맞춥니다. 번호, 이름, 이유 문자열은 [ADR-0004](../decisions/0004-locomotion-status-topic.md)(Proposed)로 올렸습니다([알려진 한계와 미결정](#알려진-한계와-미결정) 참고).

## 무엇을 하는가

로봇의 저수준 상태(자세, 속도, 지면 정보)를 정지·보행·낙상 같은 상위 상태 하나와 이유로 요약해서 ROS 토픽으로 내보냅니다. SW팀 앱의 표시나 대처 판단에 쓰는 것이 목적입니다.

- 판정 코어는 numpy와 pyyaml만 씁니다. MuJoCo, Isaac Sim, Isaac Lab, 실기에서 같은 코드가 돌 수 있게 ROS와 시뮬레이터에 의존하지 않습니다.
- 현재 이 토픽을 내보내는 곳은 시뮬레이터 시험 하네스(`policies/route_walk/state_scenarios.py`)뿐입니다. 실기에서 같은 입력을 만들어 코어에 넣는 노드는 아직 없습니다.
- 위치는 `ros_pkgs/hn_robot_state/`입니다. `package.xml`이 없는 순수 Python 모듈이라 `colcon build`나 `ros2 run` 대상이 아닙니다.

## 한눈에 보기

| 항목 | 값 |
| --- | --- |
| 토픽 | `/locomotion/status` |
| 타입 | `diagnostic_msgs/msg/DiagnosticArray` (`status`는 항상 1개) |
| QoS | reliable, transient_local, KEEP_LAST, depth 1 |
| 발행 시점 | 상태가 바뀌면 즉시, 그 밖에는 10 Hz heartbeat로 마지막 보고를 다시 냅니다 |
| 입력이 끊겼을 때 | heartbeat가 `STALE_INPUT`을 냅니다 |
| `hardware_id` | 기본 `hn_v0_go2` (하네스의 `--robot-id`로 바꿈) |
| `status[0].name` | `locomotion/state` |

S-005의 `/localization/status`와 짝이 되도록 이름 규칙과 숫자 enum 방식을 따랐습니다. 타입은 S-005가 쓰는 `hn_interfaces`를 확인하지 못해 표준 메시지로 시작했습니다.

## 상태 코드

`values`의 `code`와 `status[0].message`의 이름이 같은 상태를 가리킵니다.

| code | 이름 | `level` | `reason` | 의미와 판정 조건 |
| --- | --- | --- | --- | --- |
| 0 | `INITIALIZING` | OK (0) | `calibrating` | 시작 직후입니다. 기울기 15° 미만, 수직 속도 0.2 m/s 미만이 1.0 s 이어지면 끝나고, 그 동안의 높이 중앙값을 서 있는 높이 `h0`로 씁니다. |
| 1 | `STANDING` | OK (0) | `idle` | 명령과 속도가 모두 작은 상태가 0.5 s 이어졌습니다. |
| 2 | `WALKING` | OK (0) | `moving` | 명령이나 속도 중 하나라도 크게 나온 상태가 0.1 s 이어졌습니다. |
| 3 | `TILTING` | - | - | 번호만 예약했고 아직 내보내지 않습니다. |
| 4 | `SLIPPING` | - | - | 번호만 예약했고 아직 내보내지 않습니다. |
| 5 | `FALLEN` | ERROR (2) | `tilt`, `off_ground`, `low_height` | 낙상 조건이 0.2 s 이어졌습니다. 조건은 아래 표입니다. |
| 6 | `STALE_INPUT` | STALE (3) | `no_input` | 입력이 wall 시간으로 0.5 s 넘게 끊겼습니다. 판정 상태는 바꾸지 않고 마지막 특징을 그대로 싣습니다. |

`level`은 `diagnostic_msgs/DiagnosticStatus`의 상수와 같은 값입니다(OK 0, WARN 1, ERROR 2, STALE 3). WARN은 `TILTING`을 넣을 때 쓸 자리입니다.

### FALLEN 조건

세 조건 중 하나가 0.2 s 이어지면 `FALLEN`입니다. 여러 조건이 겹치면 `tilt`, `off_ground`, `low_height` 순서로 이유를 정합니다.

| `reason` | 조건 | 비고 |
| --- | --- | --- |
| `tilt` | 기울기 70° 초과 | 방향과 상관없습니다. 옆으로 넘어져도, 뒤집혀도 같습니다. |
| `off_ground` | 몸통 아래 height scan 중심 3×3 칸 중 유효한 칸이 50% 미만 | 지형 밖으로 나갔거나 추락 중입니다. |
| `low_height` | 지면 위 높이가 `h0`의 50% 미만 | 주저앉은 경우입니다. 기울기는 작아도 걸립니다. |

해제는 기울기 25° 미만, 지면 있음, 높이가 `h0`의 80% 초과(높이 입력이 있을 때)인 상태가 1.0 s 이어질 때입니다. 즉 로봇이 스스로 일어나면 `FALLEN`은 풀립니다.

## 메시지 필드

`status[0].values`는 문자열 key-value입니다. 값이 없는 특징은 key 자체를 생략합니다(빈 문자열이나 `nan`을 넣지 않습니다).

| key | 단위 | 설명 |
| --- | --- | --- |
| `code` | - | 위 상태 코드 |
| `state` | - | 상태 이름 |
| `reason` | - | 위 표의 이유 |
| `since_s` | s | 이 상태가 시작된 뒤 지난 시간. `STALE_INPUT`은 입력이 끊긴 wall 시간 |
| `sim_t` | s | 판정에 쓴 입력의 시간(시뮬레이션 시간 또는 로봇 시간). 필드 이름은 `sim_t`이지만 실기에서는 로봇 시간을 넣습니다 |
| `tilt_deg` | deg | 중력 방향 기준 총 기울기 |
| `roll_deg`, `pitch_deg` | deg | roll은 x축, pitch는 y축 둘레(ZYX 오일러). 양의 pitch는 앞이 내려간 상태입니다 |
| `speed_mps` | m/s | 몸통 수평 속도 |
| `height_m` | m | 몸통 아래 지면에서 몸통까지 높이(height scan이 있을 때) |

좌표는 정책 base 프레임입니다(+X 전방, +Y 좌, +Z 상). `header.frame_id`는 비어 있습니다.

`FALLEN`일 때 메시지는 이렇게 나옵니다. `report_to_msg`로 만든 출력이고, 값은 형식을 보이려고 정한 예시이며 측정값이 아닙니다.

```text
level = b'\x02' | name = locomotion/state | message = FALLEN | hardware_id = hn_v0_go2
  code = 5
  state = FALLEN
  reason = tilt
  since_s = 0.00
  sim_t = 8.28
  tilt_deg = 117.040
  roll_deg = 116.300
  pitch_deg = 8.100
  speed_mps = 0.000
  height_m = 0.071
```

## 시간 규칙

ROS 시계와 시뮬레이터 시계가 어긋나는 문제를 피하려고 이렇게 정했습니다.

- `header.stamp`는 노드 시계가 아니라 시스템 시간(`time.time_ns()`)입니다. 시뮬레이션 시간은 `values`의 `sim_t`로 따로 싣습니다.
- 발행 노드는 `use_sim_time=False`를 강제합니다. `true`인데 `/clock`이 없으면 ROS 시계가 0에 멈춰 heartbeat 타이머가 돌지 않습니다.
- 발행 노드는 전용 rclpy Context와 전용 스레드를 씁니다. 같은 프로세스의 다른 rclpy 사용(예: Isaac Sim의 ROS 확장)과 전역 상태를 나누지 않습니다.
- 입력 시간이 거꾸로 가면 판정기를 초기화합니다. 0.5 s보다 크게 건너뛰면 진행 중인 지속 시간 계산만 다시 시작하고 상태는 유지합니다.
- 입력 끊김은 wall 시간으로 감시합니다. 시뮬레이션이 멈추거나 느려져도 끊김을 알 수 있어야 하기 때문입니다.

## 구독하는 쪽

`level`은 rclpy에서 정수가 아니라 `bytes`입니다(`b'\x02'`). 숫자로 쓰려면 `level[0]`을 읽습니다.

```python
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                 history=HistoryPolicy.KEEP_LAST, depth=1)

def on_status(msg: DiagnosticArray) -> None:
    status = msg.status[0]
    level = status.level[0]                              # 0 OK, 1 WARN, 2 ERROR, 3 STALE
    values = {kv.key: kv.value for kv in status.values}
    print(int(values["code"]), status.message, values["reason"], level)

rclpy.init()
node = Node("status_listener")
node.create_subscription(DiagnosticArray, "/locomotion/status", on_status, QOS)
rclpy.spin(node)
```

`hn:sim` 컨테이너에서 명령줄로 보려면 이렇게 합니다. `transient_local`을 지정하면 붙은 시점의 마지막 상태를 바로 받습니다.

```bash
./docker/hn sim ros2 topic echo /locomotion/status --qos-durability transient_local --qos-reliability reliable
```

대시보드 쪽 경로는 S-005 선례(`foxglove_bridge`가 ROS 2 토픽을 WebSocket으로 내보냄)를 따를 수 있습니다. `foxglove_bridge`는 `diagnostic_msgs/msg/DiagnosticArray`를 스키마와 함께 광고하고 프레임을 전달하는 것을 확인했습니다.

## 직접 실행해 보기

시뮬레이터 창이 뜨고 실시간 속도로 진행합니다. 저장소 최상위의 데스크톱 터미널에서, 인자 없이 실행합니다. 컨테이너(`hn:sim`)는 스크립트가 알아서 씁니다.

| 시나리오 | MuJoCo | Isaac Sim | Isaac Lab |
| --- | --- | --- | --- |
| 출발지에서 목적지까지 정상 보행 | `./tools/demo/state_walk_mujoco.sh` | `./tools/demo/state_walk_isaacsim.sh` | `./tools/demo/state_walk_isaaclab.sh` |
| 걷다가 주저앉기 | `./tools/demo/state_collapse_mujoco.sh` | `./tools/demo/state_collapse_isaacsim.sh` | `./tools/demo/state_collapse_isaaclab.sh` |
| 걷다가 옆으로 넘어지기 | `./tools/demo/state_flip_mujoco.sh` | `./tools/demo/state_flip_isaacsim.sh` | `./tools/demo/state_flip_isaaclab.sh` |

- 값은 각 파일 위쪽 하이퍼파라미터 블록에서 고칩니다(`WINDOW`, `ROUTE`, `STAND_S`, `AT`, `UNTIL`, `EXIT_ON_ARRIVAL`, `FLIP_RATE`, `THIGH`, `CALF`, `ROS_TOPIC`, `ROS_LOCAL`, 스크립트마다 해당하는 것만 있습니다). 명령줄 인자는 없습니다.
- 걷기 스크립트는 `STAND_S`(기본 5 s) 동안 속도 명령을 0으로 해서 서 있다가 걷기 시작합니다. 한 번 실행에서 `INITIALIZING → STANDING → WALKING`이 모두 나옵니다. 0으로 두면 바로 걷고, 0이 아니면 3 s 이상이어야 합니다. 도착 시간은 그만큼 늦어집니다.
- 끝나면 요약에 판정 결과와 PASS/FAIL 검사가 나옵니다. walk의 PASS는 "FALLEN과 STALE 오탐이 없고, 대기 중 STANDING이며, 걷기 시작하면 WALKING이 된다"는 뜻이지 "도착했다"는 뜻이 아닙니다.
- 판정 기록은 JSONL로 컨테이너 `/data/state_logger/`에 남습니다(호스트 `~/hypernova-data/state_logger/`). `header`, `transition`, `sample`, `fault_start`와 고장 이벤트, `summary` 줄로 이뤄집니다.
- ROS로 내보려면 `ROS_TOPIC="/locomotion/status"`로 설정합니다. 같은 `ROS_DOMAIN_ID`를 쓰는 다른 PC에 시험용 `FALLEN`이 퍼지지 않도록 `ROS_LOCAL=1`이 기본입니다.
- 필요한 데이터(정책 가중치, 지형, 장면, mesh)는 Git 밖에 있습니다. 준비 상태는 `./tools/demo/run_route.sh check`로 확인합니다.
- 스크립트 9개에 없는 두 가지(입력 끊김, 오래 서 있기)는 내부 실행기 `tools/demo/_state_run.sh`를 직접 불러 확인합니다(저장소 최상위, 창 없는 모드, MuJoCo 기준. `mujoco` 자리에 `isaacsim`, `isaaclab`도 됩니다). 하네스의 모든 옵션도 이 실행기로 씁니다.

  ```bash
  # 입력 끊김: 8 s부터 3 s 동안 판정기에 입력을 주지 않음(WALKING -> STALE_INPUT -> WALKING)
  ./tools/demo/_state_run.sh mujoco stale --at 8 --gap 3
  # 정지: 명령 없이 20 s 서 있음(INITIALIZING -> STANDING, 서 있는 시간이 95% 이상인지 검사)
  ROUTE=none ./tools/demo/_state_run.sh mujoco baseline --until 20 --expect stand -- --vmax 0
  ```

단위 시험(75개)은 `hn:sim` 컨테이너에서 이렇게 돌립니다.

```bash
./docker/hn sim bash -c 'cd /workspace/hypernova && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/hn-venv/bin/python -m pytest -p no:cacheprovider ros_pkgs/hn_robot_state/test -q'
```

## 판정 임계값

`ros_pkgs/hn_robot_state/config/thresholds.yaml`에 있고 모든 키를 명시해야 합니다. 값을 바꾸면 `core.py`의 `Thresholds` 기본값도 같이 바꿉니다(단위 시험이 둘이 같은지 검사합니다). 아래는 주요 값입니다.

| 구분 | 값 | 단위 |
| --- | --- | --- |
| 낙상 기울기 | 70 | deg |
| 낙상 낮은 높이 비율 | 0.5 (`h0` 대비) | - |
| 낙상 진입 지속 | 0.2 | s |
| 해제 기울기, 높이 비율, 지속 | 25, 0.8, 1.0 | deg, -, s |
| 정지 판정(명령, 속도, 지속) | 0.05 m/s와 0.05 rad/s, 0.10 m/s, 0.5 | -, -, s |
| 보행 판정(명령, 속도, 지속) | 0.10 m/s와 0.10 rad/s, 0.15 m/s, 0.1 | -, -, s |
| 입력 끊김 | 0.5 (wall) | s |

이 값은 시뮬레이션 로그로 맞춘 초기값입니다. 실기 IMU 노이즈와 모터 지연은 반영되지 않았습니다. 실기에 올리기 전에 다시 맞춰야 합니다.

## 시험 결과 (2026-11-15 기준)

환경은 `hn:sim` 컨테이너(Ubuntu 24.04, ROS 2 Jazzy, `rmw_fastrtps_cpp`, UDP 전용 `docker/fastdds.xml`), 정책은 `model_3849`(PR #21의 pretrained, sha256 `e50fa996…`), 경로는 데모 경로 A입니다. 아래 표는 창 없는 모드로 9개 스크립트를 돌린 결과입니다. 창 모드에서는 걷기 3종과 넘어지기 3종, MuJoCo 주저앉기를 돌려 PASS를 확인했고, Isaac Sim과 Isaac Lab의 주저앉기는 창 모드로 돌리지 않았습니다.

| 시험 | MuJoCo | Isaac Sim | Isaac Lab |
| --- | --- | --- | --- |
| 정상 보행 중 `FALLEN`·`STALE_INPUT` 오탐 | 0프레임 | 0프레임 | 0프레임 |
| 보행 중 기울기 최대 (`STAND_S=0`) | 12.8° | 46.9° | 13.2° |
| 보행 중 기울기 최대 (`STAND_S=5`, 걷기 스크립트 기본) | 14.5° | 48.5° | 12.6° |
| `INITIALIZING` → `STANDING` (`STAND_S=5`) | 1.20 s | 1.18 s | 1.22 s |
| 대기 5 s 중 초기화 뒤 `STANDING` 비율 | 100% | 100% | 100% |
| 대기가 끝나고 걷는 명령이 나온 뒤 → `WALKING` | 0.10 s | 0.10 s | 0.10 s |
| 경로 A 도착 시각 (`STAND_S=0` / `5`) | 348.0 / 354.8 s | 421.7 / 421.7 s | 349.6 / 354.6 s |
| 주저앉기 시작 → `FALLEN` | 0.42 s | 0.40 s | 0.40 s |
| 옆으로 넘어짐 시작 → `FALLEN` | 0.28 s | 0.26 s | 0.30 s |

- `STAND_S=5` 열은 걷기 스크립트가 내부 실행기에 넘기는 것과 같은 인자(`_state_run.sh <sim> baseline --label walk --stand-s 5`)로 창 없는 모드에서 직접 돌린 결과입니다. 스크립트가 `STAND_S`를 그 인자로 바꾸는 부분은 실행기를 스텁으로 바꿔 확인했고, 걷기 스크립트 자체를 창 모드로 돌려 보지는 않았습니다. 주저앉기와 넘어지기 행은 `STAND_S` 없이(걷다가 `AT`에서 고장) 돌린 결과입니다.
- 위 시간은 시뮬레이션 시간이고, 고장 시작부터 판정기가 `FALLEN`을 내기까지입니다. 판정기의 지연은 항상 0.20 s(debounce)이고 나머지는 로봇이 실제로 쓰러지는 시간입니다.
- 옆으로 넘어짐은 몸통 roll 각속도 27 rad/s를 한 번 더해서 만들었습니다. 이 크기가 맞는 구간은 좁습니다. 24는 Isaac Lab에서 버텨 일어났고 30은 MuJoCo에서 한 바퀴 돌아 다시 섰습니다. 26에서 28 사이는 세 시뮬레이터 모두 누운 채 `FALLEN`이 유지됐습니다.
- ROS 전달(MuJoCo 주저앉기, 같은 컨테이너의 독립 프로세스): 발행 243건, 전달 지연 중앙값 0.5 ms(p95 1.3 ms), heartbeat 간격 중앙값 100 ms(최대 101 ms). `FALLEN` 첫 메시지의 `since_s`는 0.00으로 즉시 나갔습니다.
- Kit 프로세스 안에서도 발행됩니다(Isaac Sim 114건, Isaac Lab 122건 발행, 구독자가 각각 89건, 115건 수신). 수신이 더 적은 것은 구독자가 붙기까지 놓친 메시지가 있기 때문으로 보입니다(MuJoCo 시험에서는 처음 약 1.4 s가 그랬습니다).

## 알려진 한계와 미결정

- **실기 연결 없음.** 실기의 IMU와 엔코더로 입력 dict(`projected_gravity_b`, `base_lin_vel_b`, `command` 등)를 만들어 코어에 넣는 노드가 없습니다. 입력 dict의 키는 정책 러너가 받는 것과 같습니다.
- **메시지 타입은 임시입니다.** `hn_interfaces`는 2026-11-15에 조직 저장소 코드, 원격 브랜치, 컨테이너, 이 PC에서 찾지 못했고 위치와 소유자는 확인되지 않았습니다. `diagnostic_msgs`를 커스텀 메시지로 바꾸는 코드는 몇 줄이지만, 실제 비용은 패키지 작성, 빌드 환경(`hn:sim` 기본 `VIRTUAL_ENV` 때문에 `colcon build`가 empy를 못 찾음), 모든 구독 쪽 빌드 배포, 구독자 타입 변경 조율입니다. 구독자가 생기기 전에 정하는 편이 쌉니다. 받는 쪽에 인터페이스 패키지가 없으면 `ros2 topic echo`와 `foxglove_bridge`가 그 채널을 쓰지 못합니다.
- **코드 표는 팀 간 결정입니다.** 상태 번호와 이유 문자열은 SW팀 앱이 의존하게 되므로 [ADR-0004](../decisions/0004-locomotion-status-topic.md)로 올렸습니다. 상태는 `Proposed`이고 SW팀이 동의하기 전까지는 확정이 아닙니다.
- **Isaac Sim의 정상 보행 기울기 여유가 작습니다.** 최대 46.9°(`STAND_S=0`, 99번째 백분위수 35.1°) 또는 48.5°(`STAND_S=5`, 99번째 백분위수 30.2°)라서 70° 기준까지 21.5°에서 23°뿐입니다. 후반 오르막(250 s에서 350 s)에 몰립니다. `TILTING`을 넣을 때 35°에서 40° 기준을 쓰면 정상 보행이 걸립니다. 시뮬레이터별 여유를 먼저 확인해야 합니다.
- **걸린 로봇은 감지하지 못합니다.** 명령은 전진인데 속도가 0이어도 `WALKING`으로 남습니다(`SLIPPING` 미구현). 수정 전 Isaac Sim 창 모드 보행에서 실제로 나온 경우입니다(재생기의 시작 조건 문제였고 지금은 고쳤습니다).
- **스스로 일어나는 전복은 `FALLEN`이 풀립니다.** `FALLEN` 유지 시간으로 낙상 여부를 판단하면 안 됩니다. 해제 이벤트도 함께 봐야 합니다.
- **낙상 상태로 시작하면 `low_height`를 못 잡습니다.** `h0`를 못 재기 때문입니다(`tilt`, `off_ground`는 작동). 실기에서 서 있는 높이를 알면 `nominal_height_m`을 주면 됩니다.
- **지형 가장자리에서 `off_ground` 오탐이 날 수 있습니다.** 경로 A에서는 나오지 않았지만 다른 지형에서는 확인하지 않았습니다.
- **새 구독자의 첫 수신이 늦을 수 있습니다.** DDS 탐색 때문에 `transient_local`로도 첫 수신까지 0.12 s에서 2.39 s로 편차가 컸습니다. 구독자가 붙기 전에 발행자가 사라지면 아무것도 받지 못합니다.
- **시험하지 않은 것:** `hn:ros` 이미지(이 PC에 없음), 실제 대시보드나 Foxglove 패널, 창 모드 Kit 안에서의 ROS 발행, 실기.

## 관련 파일

| 경로 | 내용 |
| --- | --- |
| `ros_pkgs/hn_robot_state/hn_robot_state/core.py` | 판정 코어(`StateEstimator`, `StaleWatchdog`) |
| `ros_pkgs/hn_robot_state/hn_robot_state/ros_node.py` | ROS 어댑터(`StatusPublisher`, `report_to_msg`) |
| `ros_pkgs/hn_robot_state/hn_robot_state/jsonl_log.py` | JSONL 기록기 |
| `ros_pkgs/hn_robot_state/config/thresholds.yaml` | 임계값 |
| `ros_pkgs/hn_robot_state/test/` | 단위 시험 |
| `policies/route_walk/state_scenarios.py` | 시뮬레이터 시험 하네스(재생기를 수정하지 않고 감싸 고장을 넣음) |
| `tools/demo/state_{walk,collapse,flip}_{mujoco,isaacsim,isaaclab}.sh` | 사용자용 실행 스크립트 9개 |
| `tools/demo/_state_run.sh` | 내부 실행기 |
