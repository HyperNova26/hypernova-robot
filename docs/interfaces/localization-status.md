# 위치추정 상태 토픽 인터페이스 (`/localization/status`)

2026-11-28 기준 **임시 초안**입니다. S-005 대시보드 명세의 상태 코드 0~5를 쓰되, 아직 없는 `hn_interfaces/msg/LocalizationStatus` 대신 보행 상태(G-006, [locomotion-status.md](locomotion-status.md))와 같은 `diagnostic_msgs/DiagnosticArray` 형식으로 내보냅니다. 팀 합의를 받은 확정 인터페이스가 아닙니다. 판정 조건은 위치추정 담당과 다시 정합니다.

## 무엇을 하는가

위치추정 결과(`nav_msgs/Odometry`)가 **제대로 나오고 있는지**를 상태 하나로 요약합니다.

- 위치추정 알고리즘(Super-LIO, FAST-LIO2, 시뮬레이터 정답 위치, 실기)과 상관없이 같은 노드가 붙습니다. Odometry만 보기 때문입니다.
- **지도 기준 정확도는 판정하지 않습니다.** 기준 지도와 맞춰 보는 모듈이 아직 없어서, `TRACKING`은 "위치가 끊기지 않고 튀지 않는다"는 뜻이지 "지도 위 위치가 맞다"는 뜻이 아닙니다.
- 구현은 `ros_pkgs/operator/localization_dashboard/adapters/localization_status.py`입니다. 판정 로직(`Judge`)은 ROS 없이 쓸 수 있게 분리했습니다.

## 한눈에 보기

| 항목 | 값 |
| --- | --- |
| 토픽 | `/localization/status` |
| 타입 | `diagnostic_msgs/msg/DiagnosticArray` (`status`는 항상 1개) |
| QoS | reliable, transient_local, KEEP_LAST, depth 1 |
| 발행 시점 | 상태가 바뀌면 즉시, 그 밖에는 5 Hz heartbeat |
| `status[0].name` | `localization/state` |
| `hardware_id` | 기본 `hn_v1_hyper` (`--robot-id`) |
| 입력 | `--odom`(기본 `/localization/odometry`), 선택 `--scan`(예: `/lidar/points`) |

## 상태 코드

위에서부터 먼저 맞는 조건이 적용됩니다.

| code | 이름 | `level` | `reason` | 조건 (기본값) |
| --- | --- | --- | --- | --- |
| 5 | `INPUT_TIMEOUT` | ERROR (2) | `no_odom` | Odometry가 한 번 이상 들어온 뒤 wall 시간 1.0 s 넘게 끊김 (`--timeout`) |
| 4 | `STALE_INPUT` | STALE (3) | `no_scan` | `--scan`을 준 경우, LiDAR가 1.0 s 넘게 끊김 (Odometry는 들어오는데 입력 센서가 멈춤) |
| 3 | `LOST` | ERROR (2) | `jump`, `non_finite` | 0.05 s 이상 떨어진 두 자세 사이 속도가 5 m/s 초과(`--max-speed`, `--min-dt`)이거나 자세에 NaN·Inf가 있음. 2 s 유지(`--hold`) |
| 0 | `ACQUIRING` | WARN (1) | `waiting_odom`, `warming_up` | 아직 Odometry가 없거나, 첫 Odometry 뒤 2 s(메시지 시간)가 안 지남 |
| 2 | `DEGRADED` | WARN (1) | `low_rate` | 최근 2 s(메시지 시간) Odometry 주기가 5 Hz 미만 (`--min-rate`, `--window`) |
| 1 | `TRACKING` | OK (0) | `ok` | 위 조건에 모두 해당하지 않음 |

- 5 m/s는 사람이 들고 걷거나 4족 로봇이 걷는 속도(약 0.5~1.5 m/s)보다 충분히 큰 값입니다. 차량에 실으면 올려야 합니다.
- 메시지 시간이 거꾸로 가면(bag을 처음부터 다시 재생) 판정기를 초기화합니다.
- 공분산은 쓰지 않습니다. Super-LIO와 지금 어댑터는 공분산을 유효한 값으로 채우지 않습니다.

## 메시지 필드

`status[0].values`는 문자열 key-value이고, 값이 없으면 key를 생략합니다.

| key | 단위 | 설명 |
| --- | --- | --- |
| `code`, `state`, `reason` | - | 위 표 |
| `since_s` | s | 이 상태가 시작된 뒤 지난 wall 시간 |
| `sim_t` | s | 마지막 Odometry의 `header.stamp`(시뮬레이션·bag·로봇 시간). 대시보드는 이 값으로 Logger 행과 맞춥니다 |
| `age_s` | s | 마지막 Odometry를 받은 뒤 지난 wall 시간 |
| `rate_hz` | Hz | 최근 2 s Odometry 주기(메시지 시간 기준) |
| `speed_mps` | m/s | 마지막으로 잰 이동 속도 |
| `source` | - | 판정한 Odometry 토픽 |

`header.stamp`는 G-006과 같이 시스템 시간이고, 노드는 `use_sim_time=False`로 돕니다. `/clock`이 멈춰도 끊김을 알 수 있어야 하기 때문입니다.

## 실행

```bash
/opt/hn-venv/bin/python adapters/localization_status.py --odom /localization/odometry --scan /lidar/points
```

`replay/run_bag_superlio.sh`(즉 `replay/run-demo.sh bag`)는 이 노드를 함께 띄웁니다. 시뮬레이터나 실기에서는 위치추정 노드 옆에서 같은 명령을 실행합니다.

## 시험 결과 (2026-11-28)

| 시험 | 결과 |
| --- | --- |
| 판정 로직 (ROS 모듈을 대신한 Windows Python) | 6개 상태가 모두 기대대로 나옴. 1 ms 간격 두 자세(2 cm)는 `LOST`가 아님 |
| 11-15 bag + Super-LIO (WSL2, `hn:ros-2026.10.1-local-superlio`, 1배속 전체) | `ACQUIRING(waiting_odom)` → `ACQUIRING(warming_up)` → `TRACKING(ok)`, 10.0 Hz. 재생 중 한 번 Odometry·LiDAR가 함께 1 s 넘게 멈춰 `INPUT_TIMEOUT` → `STALE_INPUT` → `TRACKING`이 0.2 s 안에 지나감(원인 미확인, 재생 쪽 지연으로 추정). bag이 끝나면 `INPUT_TIMEOUT`. 대시보드에 `TRACKING · CODE 1`, 끝에 `INPUT_TIMEOUT` 표시 |
| 수정 전 오탐 | 첫 판정식(바로 앞 자세와 비교)은 1 ms 간격 자세 때문에 `LOST(jump)`를 냈습니다. 0.05 s 이상 간격으로 고쳤습니다 |
| 확인하지 못한 것 | 실기, 시뮬레이터, 다른 LIO. 실제로 길을 잃는 상황(`LOST`의 참 양성) |

## 알려진 한계

- **지도 기준 판정이 아닙니다.** 누적 오차(drift)가 커져도 위치가 매끄럽게 나오면 `TRACKING`입니다. 지도 정합(relocalization) 모듈이 생기면 그 정합 점수로 `DEGRADED`·`LOST`를 다시 정의해야 합니다.
- **SW팀 계약과 타입이 다릅니다.** SW팀 PR #28(`docs/interfaces/sw-contract.md`, 열림)은 이 토픽을 `hn_interfaces/LocalizationStatus`의 `status` 필드로 받고, `TRACKING`이 아니거나 300 ms 넘게 안 오면 위치를 무효로 봅니다. 코드 0~5의 뜻은 같고, 발행 간격(heartbeat 200 ms)도 300 ms 안입니다. 타입만 다르므로 `hn_interfaces`를 누가 언제 만들지 SW팀과 정해야 합니다.
- **메시지 타입은 임시입니다.** `hn_interfaces`가 생기면 바꾸고, 대시보드는 두 형식을 모두 받습니다(`src/model.ts`의 `localizationFromDiagnostics`, `localizationStatus`).
- 임계값은 11-15 기록 하나로만 확인했습니다.
