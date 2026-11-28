<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# 대시보드 실행 가이드

2026-11-28 기준입니다. 핸드헬드 기록, 시뮬레이터(Isaac Sim·Isaac Lab·MuJoCo), 실물 로봇 세 경우를 한 문서에 정리했습니다. 처음 설치는 [README의 '처음 받은 팀원이 할 일'](README.md#처음-받은-팀원이-할-일)을 따릅니다.

## 대시보드가 하는 일

대시보드는 **ROS 2 토픽을 보는 웹 화면**입니다. 데이터가 bag에서 오는지, 시뮬레이터에서 오는지, 로봇에서 오는지 구분하지 않습니다. 정해진 토픽 이름과 형식으로 들어오기만 하면 똑같이 그립니다.

```text
데이터 원천 (bag 재생 / 시뮬레이터 / 로봇)
   │ ROS 2 토픽 (같은 ROS_DOMAIN_ID)
   ▼
foxglove_bridge  ── WebSocket :8765 ──▶  브라우저 대시보드 (읽기 전용)
```

- 장점: 시뮬레이터를 바꾸거나 실기로 넘어가도 대시보드 코드는 그대로입니다. 원천 쪽에서 토픽만 맞추면 됩니다.
- 한계: 시뮬레이터 화면 자체(MuJoCo·Isaac 창)를 보여 주지 않습니다. 원천이 토픽을 내지 않으면 해당 패널은 비어 있습니다.

## 토픽 약속

| 무엇 | 토픽 | 형식 | 없으면 |
| --- | --- | --- | --- |
| 위치·자세 (필수) | `/localization/odometry` | `nav_msgs/Odometry`, `pair360_map` → `mlx_lidar` | 지도 위 로봇·궤적이 안 나옴 |
| 현재 LiDAR | `/lidar/points` | `sensor_msgs/PointCloud2` | LiDAR 패널·누적 지도가 빔 |
| 시간 | `/clock` | `rosgraph_msgs/Clock` | 경과 시간을 메시지 시간으로만 셈 |
| 좌표 변환 | `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | LiDAR frame이 `pair360_map`이 아니면 점을 못 그림 |
| 위치추정 상태 | `/localization/status` | `DiagnosticArray` ([임시 초안](../../../docs/interfaces/localization-status.md)) | '상태 메시지 없음' |
| 보행 상태 (G-006) | `/locomotion/status` | `DiagnosticArray` ([locomotion-status.md](../../../docs/interfaces/locomotion-status.md)) | '상태 메시지 없음' |
| 글로벌 경로 (S-012) | `/plan` | `nav_msgs/Path` | 경로 레이어가 안 나옴 |
| 기준 지도 | `/localization/reference_map` | `PointCloud2`, transient_local | 지형 메시·프리뷰만 보임 |
| 정답 위치 (시뮬만) | `/ground_truth/odom` | `nav_msgs/Odometry` | 오차 비교를 안 함 |

토픽 이름이 다르면 화면 오른쪽 위 ⚙(연결 설정)에서 바꿀 수 있습니다.

## A. 핸드헬드 기록 재생 (지금 바로 됨)

11-15에 센서를 들고 걸으며 녹화한 bag을 Super-LIO에 다시 넣어, 실제 데이터로 위치추정이 어떻게 나오는지 봅니다.

```bash
replay/run-demo.sh bag                 # 1배속, 약 5분 30초
replay/run-demo.sh bag --rate 0.5      # 느린 PC
replay/run-demo.sh stop
```

브라우저에서 데이터 소스 **'핸드헬드 기록 재생'** → **'수신 시작'**을 누릅니다.

| 보이는 것 | 안 보이는 것 |
| --- | --- |
| Super-LIO 위치·궤적, LiDAR, 누적 지도, 위치추정 상태(`TRACKING` 등) | 보행 상태(사람이 들고 걸은 기록), 글로벌 경로 |

- 위치는 처음 한 번 지도에 맞춘 값(`replay/registration/1115_superlio.env`)에서 시작해 LIO가 이동량을 쌓는 방식입니다. 지도와 계속 맞춰 보정하지는 않습니다(아래 [남은 일](#남은-일)).
- 정합값은 11-15 기록에만 맞습니다. 다른 bag(`--bag`)은 시작 위치를 따로 구해야 합니다.

## B. 시뮬레이터 (Isaac Sim·Isaac Lab·MuJoCo)

**보행 시뮬은 보행팀 스크립트(`tools/demo/state_*`)가 돌립니다.** 대시보드는 그 시뮬이 내는 토픽을 받아서 볼 뿐입니다.

2026-11-27 기준 보행팀 시뮬은 `/locomotion/status`만 냅니다. 그래서 붙이면 보행 상태 패널만 바뀌고, 지도 위 로봇은 움직이지 않습니다. 로봇까지 보려면 시뮬 쪽에 아래를 더해야 합니다.

| 추가할 것 | MuJoCo | Isaac Sim·Isaac Lab |
| --- | --- | --- |
| 위치 `/localization/odometry` | `mj_step` 뒤 LiDAR body 자세 발행. 예시 `adapters/mujoco_ros.py`의 `MujocoTelemetry` | ROS 2 Bridge 확장의 odometry 그래프, 또는 Kit 안 rclpy(G-006 `StatusPublisher`와 같은 방식) |
| LiDAR `/lidar/points` | `mj_multiRay` 레이캐스트(같은 예시) | RTX LiDAR + ROS 2 Bridge의 PointCloud2 발행 |
| 시간 `/clock` | 시뮬 시간 발행 | ROS 2 Bridge의 clock 노드 |
| 위치추정 상태 | `adapters/localization_status.py`를 옆에서 실행 | 같음 |

- 시뮬의 위치는 **정답값**이라 위치추정 성능을 보여 주지 않습니다. 위치추정까지 시험하려면 시뮬 LiDAR·IMU를 Super-LIO에 넣고, 그 결과를 `/localization/odometry`로, 시뮬 자세를 `/ground_truth/odom`으로 냅니다. 그러면 대시보드가 둘의 오차를 보여 줍니다.
- 같은 `ROS_DOMAIN_ID`에서 `ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765`를 띄우고, 데이터 소스 **'시뮬레이터'**를 고릅니다.
- Isaac Sim·Isaac Lab과의 연결은 아직 시험하지 않았습니다.

## C. 실물 로봇

로봇 PC에서 데이터를 내고, 노트북 브라우저에서 원격으로 봅니다. 아직 로봇용 launch 파일은 없고, 아래는 구성 계획입니다.

```text
로봇 PC: LiDAR·IMU 드라이버 → Super-LIO → lio_adapter.py → /localization/odometry
         localization_status.py → /localization/status
         hn_robot_state(G-006) → /locomotion/status
         foxglove_bridge address:=0.0.0.0 port:=8765
노트북:  브라우저 → 데이터 소스 '실물 로봇' → ⚙에서 ws://<로봇 IP>:8765 → 수신 시작
```

- 같은 네트워크여야 하고, 로봇 PC 방화벽에서 8765/TCP를 엽니다.
- 무선에서는 LiDAR 점군이 무겁습니다(10 Hz 전체 스캔). 끊기면 로봇에서 점을 줄여(voxel downsample) 다른 토픽으로 내고, ⚙의 LiDAR 토픽을 그쪽으로 바꿉니다.
- 매번 출발 위치가 달라서, 지도 좌표(`pair360_map`)에 맞추는 첫 정합이 필요합니다. 지금은 11-15 기록에 대해서만 손으로 구한 값이 있습니다. 실기에서는 지도 정합 모듈이 이 일을 해야 합니다.

## 연결 주소

- `ws://localhost:8765`의 localhost는 **브라우저를 연 그 PC**입니다. 각자 자기 PC에서 A나 B를 띄우면 주소를 안 바꿔도 됩니다.
- 다른 PC나 로봇의 데이터를 보려면, 데이터 쪽 bridge를 `address:=0.0.0.0`(이 스크립트는 `--expose`)로 띄우고 ⚙에서 `ws://<그 PC IP>:8765`를 넣습니다.

## 자주 막히는 곳

| 증상 | 원인과 해결 |
| --- | --- |
| '주소에 연결하지 못했습니다' | 데이터 원천이 안 떠 있습니다. bag은 끝나면 컨테이너가 지워지므로 다시 `run-demo.sh bag` |
| 연결은 되는데 지도에 로봇이 없음 | `/localization/odometry`가 안 옴. 원천에서 `ros2 topic hz /localization/odometry` |
| 상태 패널이 '상태 메시지 없음' | 그 원천이 상태 토픽을 안 냄(위 표). bag의 보행 상태는 정상적으로 없음 |
| LiDAR 점이 안 그려짐 | 점군 frame에서 `pair360_map`까지 TF가 없음 |
| WSL에서 매우 느림 | 저장소·데이터를 `/mnt/c`가 아니라 WSL 홈(`~/`)에 둠 |

## 확인한 범위 (2026-11-28)

| 경우 | 결과 |
| --- | --- |
| A. 핸드헬드 기록 | WSL2 + Docker에서 bag 재생, 위치·LiDAR·위치추정 상태(`TRACKING`, 10 Hz) 표시 확인 |
| B. 시뮬레이터 | 시험하지 않음. 보행팀 로봇에 LiDAR·IMU가 들어가고 시뮬이 위치·LiDAR 토픽을 낸 뒤 연결 |
| C. 실물 로봇 | 시험하지 않음 |

## 남은 일

- **지도 정합(relocalization)**: 기준 지도와 현재 스캔을 맞춰 누적 오차를 고치고, 실기의 첫 위치를 자동으로 잡는 모듈. 위치추정 담당 범위이며, 생기면 대시보드는 그 결과를 그대로 받습니다.
- 보행팀 시뮬에 위치·LiDAR·`/clock` 발행 추가.
- 로봇 PC용 launch 파일.
- `hn_interfaces` 확정 시 상태 메시지 타입 교체.
