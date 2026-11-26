<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# 위치추정 대시보드 (S-005·S-006)

2026-11-16 기준입니다. S-005 공통 localization 토픽을 `foxglove_bridge`로 받아 기준 지도 위에 추정 궤적, GT, 현재 LiDAR 스캔, 위치추정 상태, Logger를 보여 주는 **읽기 전용** 웹 대시보드입니다. React + Three.js로 만들었고 Foxglove WebSocket의 CDR(Common Data Representation)·ros2msg 메시지를 해석합니다. 브라우저는 어떤 ROS 메시지도 발행하지 않습니다.

아직 colcon package가 아닙니다. `ros_pkgs/README.md`의 `operator` 후보 경계에 두었고, package 구성과 위치는 리뷰에서 정합니다.

## 확인한 범위

| 항목 | 결과 |
| --- | --- |
| 단위·인터페이스 시험 | `npm test` 37개 통과, `tsc`·`vite build` 통과 (Windows, Node.js 24.19.0, npm 11.17.0) |
| 합성 CDR 수신 | `tests/foxglove-fixture.mjs` 시험 서버로 확인 |
| MuJoCo SIM 실시간 연결 | `hn:ros` 이미지(로컬 빌드, `docker/.env`의 `2026.10.1`)에서 `adapters/mujoco_route_sim.py` + `foxglove_bridge`를 띄워 웹 연결까지 확인 |
| bag 기록 | 위 SIM에서 기록한 MCAP을 `ros2 bag info`로 읽고 `ros2 bag play`로 재생 확인 |
| 확인하지 못한 것 | 팀 LIO 어댑터 출력, 실제 LIO twist 값, 실제 `LocalizationStatus` 메시지, 실기·실센서, 팀 보행 runner와의 연결 |

MuJoCo SIM은 보행 시뮬레이션이 아닙니다. LiDAR만 단 mocap 몸체를 지형 위 경로로 옮기는 kinematic 재생이며, `/localization/odometry`에는 LIO 추정이 아니라 SIM 자세가 들어갑니다.

## 2026-11-26 갱신: 실측 bag 재생과 로봇 표시

11-15 핸드헬드 기록(rosbag2)을 Super-LIO로 다시 추정해 `pair360_map` 위에 보여 줍니다. 위의 '확인한 범위' 표는 11-16 기준이며, 이번 갱신에서 확인한 것은 다음과 같습니다.

| 항목 | 결과 |
| --- | --- |
| 단위·인터페이스 시험 | `npm test` 59개 통과, `tsc` 통과 (Windows, Node.js 24.19.0). `public/robot/`이 없으면 URDF 사본 시험 1개는 건너뜁니다 |
| 실측 bag → Super-LIO → 대시보드 | `replay/run-demo.ps1 -Bag <11-15 rosbag2>`, 0.5배속. 출발점(x -46.7 m)부터 지형 위 로봇, 궤적, LiDAR 누적 갱신을 화면으로 확인 |
| 지도 정합 | `replay/registration/1115_superlio.env`. FAST-LIO2 정합 경로 대비 수평 차이 중앙값 0.46 m, p95 0.69 m. 같은 기록 안에서만 유효합니다 |
| 확인하지 못한 것 | LiDAR–IMU 외부 보정(추정값 사용), 실제 `LocalizationStatus`, 실기 보행, 다른 기록의 정합 |

화면에서 바뀐 점은 다음과 같습니다.

- **지형 메시**: pair360-map mesh_v3 PLY(지면·장애물·나무) 전체를 0.4 m 군집으로 단순화한 회색 표시용 메시입니다(`python adapters/prepare-terrain-ply.py <mesh_v3 폴더>`). 이전 Isaac USD 메시는 경로 A 둘레 30 m로 잘려 11-15 출발점이 빠졌습니다.
- **LiDAR 누적**: 수신한 `/lidar/points`를 0.1 m voxel당 1점으로 최대 200만 점까지 쌓고, 바로 아래 지면 기준 높이(0–5 m)로 무지개색(turbo)을 칠합니다. 현재 스캔은 흰색입니다.
- **로봇 표시**: `description/hn_v1_hyper` URDF를 `python adapters/prepare-robot.py <description/hn_v1_hyper> --cell-mm 3`으로 `public/robot/hn_v1_hyper/`에 복사·경량화해 그립니다(시각 메시 약 55만 → 8만 삼각형). 로봇 형상의 정본은 `description/`이므로 이 사본은 커밋하지 않습니다. 사본이 없으면 간략 모델로 돌아갑니다. 위치·방향(yaw)은 `mlx_lidar` 추정값에 URDF `front_lidar` 장착 오프셋을 반영하고, 높이는 지형 메시 + 서 있는 높이입니다. 다리는 `src/gait.ts`의 trot 표시용 애니메이션(이동 거리로 위상 진행, 2링크 IK)이며 관절 실측이나 보행 정책 출력이 아닙니다.

### 재생 실행 (`replay/`)

| 파일 | 역할 |
| --- | --- |
| `adapters/fast_lio_twist/Dockerfile` | `hn:ros-2026.10.1-local`에 twist를 채우는 FAST-LIO2를 다시 빌드한 `hn:ros-2026.10.1-local-twist` |
| `replay/Dockerfile.superlio` | 위 이미지에 Super-LIO(`f89f48d`)를 더한 `hn:ros-2026.10.1-local-superlio` |
| `replay/run_bag_superlio.sh`, `super_lio_mlx.yaml` | bag 재생 → Super-LIO → `adapters/lio_adapter.py` → `foxglove_bridge` |
| `replay/run_bag_lio.sh`, `fast_lio_mlx.yaml` | 같은 재생을 FAST-LIO2로 (이전 경로) |
| `replay/registration/` | `pair360_map` 정합값(`1115*.env`·`.json`)과 정합 스크립트 |
| `replay/run-demo.ps1` | Docker 재생과 dev server를 함께 띄우는 Windows 실행 스크립트 |

```powershell
cd replay
docker build -t hn:ros-2026.10.1-local-twist ../adapters/fast_lio_twist
docker build -t hn:ros-2026.10.1-local-superlio -f Dockerfile.superlio .
./run-demo.ps1 -Bag <20261115T120809_074988Z_measurement_e03893/rosbag2> -Rate 0.5
```

컨테이너는 `ROS_DOMAIN_ID=42`로 띄웁니다. 같은 호스트의 다른 ROS 컨테이너(예: MuJoCo SIM)와 같은 domain이면 토픽이 섞입니다. 대시보드의 ROS 주소 설정은 새로고침하면 기본값으로 돌아가므로, 재생 전에 주소를 다시 확인합니다. 원본 bag과 지도·지형 파일은 커밋하지 않습니다.

## 실행

이 폴더에서 실행합니다.

```bash
npm ci
npm run dev        # http://127.0.0.1:5173/  (?demo=1 또는 데이터 소스의 가상 데이터)
npm test
npm run build
```

데이터 소스는 브라우저가 만드는 가상 데이터와 ROS 수신 두 가지입니다. ROS 수신은 '연결 설정'에서 `ws://localhost:8765`를 지정합니다. 수신 중에는 '수신 중지', 멈추면 '수신 시작'으로 마지막 소스에 다시 연결합니다.

## 입력 토픽

근거는 S-005 '대시보드 데이터 구조' Notion 명세입니다.

| 역할 | 기본 토픽 | 타입·좌표 |
| --- | --- | --- |
| 추정 위치·자세 | `/localization/odometry` | `nav_msgs/msg/Odometry`, `pair360_map → mlx_lidar` |
| 위치추정 상태 | `/localization/status` | `hn_interfaces/msg/LocalizationStatus`, 코드 0~5 |
| 기준 지도 | `/localization/reference_map` | `sensor_msgs/msg/PointCloud2`, 시작 시 1회, transient-local |
| 현재 LiDAR | `/lidar/points` | `sensor_msgs/msg/PointCloud2` |
| 좌표 변환 | `/tf`, `/tf_static` | `tf2_msgs/msg/TFMessage` |
| SIM 시각 | `/clock` | `rosgraph_msgs/msg/Clock` |
| GT (선택) | 기본값 없음 | `nav_msgs/msg/Odometry`. SIM에서만 지정, REAL은 비웁니다 |

- 상태 코드: 0 `ACQUIRING`, 1 `TRACKING`, 2 `DEGRADED`, 3 `LOST`, 4 `STALE_INPUT`, 5 `INPUT_TIMEOUT`. `LocalizationStatus.msg`의 필드 정의가 아직 없어 코드 필드 경로 기본값 `status`는 가정입니다. 설정에서 바꿀 수 있습니다.
- 연결 중 상태 메시지를 한 번도 받지 못하면 '상태 메시지 없음'으로 표시합니다. 알고리즘 상태와 통신 상태(Odometry 수신 여부)는 따로 표시합니다.
- GT 토픽은 S-005에서 정하지 않았습니다. MuJoCo SIM은 `tools/check_demo_lio.py`의 데모 bag 이름을 따라 `/ground_truth/odom`을 내지만, 웹 기본값에는 넣지 않았습니다.

## 좌표·시각 규칙

- 위치·자세의 기준은 몸체 중심이 아니라 `mlx_lidar`입니다. 팀 URDF의 LiDAR frame은 `front_lidar`이므로, 두 이름을 하나로 맞추거나 정적 TF로 이어야 합니다.
- GT는 ±50 ms 안의 가장 가까운 표본과 비교합니다(보간 없음). parent·child frame이 다르면 GT 오차는 N/A입니다.
- 현재 스캔은 최신 Odometry 측정 시각 ±120 ms 안에서 고릅니다. LiDAR가 10 Hz보다 느리면 스캔이 표시되지 않을 수 있습니다.
- 동적 TF는 ±50 ms 안에서만 쓰고, 정적 TF는 시각과 무관하게 씁니다.
- 주행 속력은 기본적으로 LIO가 추정한 선속도(Odometry `twist.linear`)입니다. REP-105에 따라 twist는 child frame 기준이므로 같은 메시지의 자세로 지도 좌표로 돌린 뒤 수평 성분의 크기를 씁니다. 세 성분이 모두 정확히 0이면 채우지 않은 값으로 보고 연속 위치 차분(`0 < Δt ≤ 1 s`)으로 대체합니다. 화면·CSV에 속력 출처(`LIO twist 선속도`, `pose 차분 (twist 미기재)`, `pose 차분`)를 남깁니다.
- 현재 FAST-LIO2(`docker/ros/hypernova.repos`의 ROS2 branch `a4743b0`)는 twist를 0으로 두므로 위치 차분이 쓰입니다. FAST-LIO2 내부 속도를 쓰려면 `publish_odometry`에서 `state_point.vel`을 child frame으로 돌려 채우는 패치가 따로 필요합니다(이 PR에 포함하지 않음). RKO-LIO는 twist를 채우지만 기준 frame을 확인하지 않았습니다. 어댑터가 child를 `mlx_lidar`로 바꿀 때는 속도도 장착 회전과 레버암만큼 바꿔야 합니다.
- `/clock`이 뒤로 가면 새 세션으로 보고 동적 기록을 지웁니다.

## bag 기록

ROS 수신 중 Logger의 'bag 기록'을 누르면, 받은 메시지를 디코딩 전 원본 CDR 그대로 ROS 2 bag(MCAP, profile `ros2`, 스키마 `ros2msg`)으로 기록합니다. '기록 종료', 수신 중지·재연결, 또는 메시지 합계 1 GB에서 `hyper-<시작 시각>.mcap`으로 내려받습니다.

- 기준 지도와 `/tf_static`처럼 한 번만 오는 토픽은 마지막 메시지를 bag 맨 앞에 넣고, transient-local QoS를 channel metadata에 기록합니다. 재생 때 늦게 붙은 구독자도 받습니다.
- 대시보드가 구독한 토픽만, Bridge가 전달한 만큼만 들어갑니다. 브라우저 메모리에 쌓으므로 긴 기록은 로봇에서 `ros2 bag record -s mcap`을 씁니다.
- 2026-11-16 MuJoCo SIM 확인: 10초 기록 958개 메시지를 `ros2 bag info`로 읽었고, `ros2 bag play --loop`에서 각 토픽이 재생됐습니다(LiDAR 약 6 Hz, Odometry 약 30 Hz). 4초 늦게 붙은 구독자도 지도를 받았습니다. Jazzy `ros2 bag info`의 토픽 목록에는 지도 토픽이 빠지지만 메시지 수에는 포함되고 재생도 됩니다.

```bash
ros2 bag info hyper-<시각>.mcap
ros2 bag play hyper-<시각>.mcap --clock
```

## 지도 레이어

prior는 지면 점군, 비지면 점군(차량·노이즈 제외), 지형 메시 세 겹이고, 그 위에 현재 LiDAR와 GT를 얹습니다. 각 레이어는 지도 아래 체크로 켜고 끕니다.

- 라벨 번호는 S-004 분류 결과를 따릅니다: 0 미확정, 1 지면, 2 줄기, 3 수관·관목, 4 시설물, 5 차량, 6 노이즈. 5·6은 prior로 그리지 않습니다.
- 로컬 지도는 실시간 연결 중 '지도 좌표와 표시 frame의 정합을 확인함'을 켜야 궤적과 겹칩니다. ROS로 받은 지도는 header frame이 표시 frame과 같으면 그대로 겹칩니다.

### 지도·메시 프리뷰 만들기

점군과 메시는 Git에 넣지 않습니다(`.gitignore`). 지도 릴리스 폴더에서 표시용 프리뷰를 만들어 `public/`에 둡니다.

```bash
HN_MAP_RELEASE=/data/map-release npm run map:sync -- --check   # 최신 여부만 확인
HN_MAP_RELEASE=/data/map-release npm run map:sync              # 바뀐 경우에만 다시 생성
```

- 릴리스 폴더 구조: `output/manifest.json`, `output/reference_map.pcd`, `terrain/scene/{scene.xml,manifest.json,hfields/}`.
- `prepare-map.mjs`는 PCD sha256이 manifest의 `reference_sha256`과 같을 때만 프리뷰(voxel·라벨당 실측점 1개, 8만 점 이하)를 만들고, 검수 상태(`status`)를 그대로 화면에 보여 줍니다.
- `prepare-terrain.mjs`는 MuJoCo heightfield를 4칸 간격으로 샘플링해 표시용 메시를 만듭니다. 충돌면 그 자체가 아닙니다.

## MuJoCo 경로 SIM

`adapters/mujoco_route_sim.py`는 지형 패키지의 `route_xyz_m`을 따라 LiDAR mocap 몸체를 0.6 m/s로 왕복시키고 다음을 발행합니다.

| 토픽 | 내용 |
| --- | --- |
| `/localization/odometry` | SIM 자세, `pair360_map → mlx_lidar` (LIO 추정 아님) |
| `/ground_truth/odom` | 같은 SIM 자세 (`--gt-topic ''`로 끔) |
| `/lidar/points` | 팀 URDF `config/front_lidar.json`을 따른 전방 120°, 16×121 ray, 10 Hz (`mj_multiRay`) |
| `/clock` | SIM 시각 |

`LocalizationStatus`는 `hn_interfaces`가 없어 발행하지 않습니다. 보행 제어기·관절·접촉·IMU는 없습니다.

`hn:ros` 컨테이너 안에서 실행합니다. MuJoCo는 시스템 `python3`가 아니라 `/opt/hn-venv/bin/python`에 있습니다. 지도 릴리스는 `/data/map-release`에 있다고 가정합니다.

```bash
./docker/hn ros bash -lc '
cd ros_pkgs/operator/localization_dashboard/adapters
/opt/hn-venv/bin/python mujoco_route_sim.py /data/map-release/terrain/scene &
/opt/hn-venv/bin/python reference_map_ros.py ../public/map-<hash12>.pcd --frame pair360_map &
ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:=127.0.0.1 port:=8765'
```

측정값(Windows Docker Desktop, 2026-11-16): heightfield 305개 대상 ray 1개가 약 27 µs라 스캔 1회가 약 52 ms입니다. LiDAR 약 8 Hz, Odometry 약 26 Hz(벽시계)로 SIM이 실시간의 약 0.8배로 돌았습니다.

## 그 밖의 adapter

| 파일 | 역할 |
| --- | --- |
| `adapters/mujoco_ros.py` | 기존 MuJoCo runner의 `mj_step` 뒤에 부르는 읽기 전용 훅. `mujoco_route_sim.py`가 사용 (팀 보행 runner 연결은 미확인) |
| `adapters/reference_map_ros.py` | PCD를 `/localization/reference_map`으로 1회 발행 (transient-local) |

## 남은 일

- `hn_interfaces/msg/LocalizationStatus` 정의와 상태 판정 조건
- GT 토픽 이름과 `mlx_lidar`·`front_lidar` frame 이름 합의
- 팀 LIO 어댑터 출력으로 실제 추정 궤적 확인 (11-15 bag 재생으로 Super-LIO 경로는 확인, 실기 미확인)
- LiDAR–IMU 외부 보정과 대시보드 ROS 주소 설정 유지
- S-012 전역 경로(`/navigation/global_path`, `nav_msgs/msg/Path`) 표시
- 이 폴더를 colcon package(launch·config 포함)로 정리할지 결정
