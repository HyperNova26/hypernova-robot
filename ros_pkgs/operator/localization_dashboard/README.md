<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# 위치추정 대시보드 (S-005·S-006·S-010)

2026-11-28 기준입니다. ROS 2 토픽을 `foxglove_bridge`로 받아 기준 지도 위에 로봇 위치·궤적, LiDAR, 위치추정 상태, 보행 상태, 글로벌 경로, 로그를 보여 주는 **읽기 전용** 웹 대시보드입니다. React + Three.js로 만들었고 Foxglove WebSocket의 CDR(Common Data Representation)·ros2msg 메시지를 해석합니다. 브라우저는 어떤 ROS 메시지도 발행하지 않습니다.

데이터가 bag 재생에서 오는지, 시뮬레이터나 실물 로봇에서 오는지는 구분하지 않습니다. 아래 [토픽](#토픽) 이름과 형식으로 들어오면 똑같이 그립니다. 지금 끝까지 확인한 원천은 **11-15 핸드헬드 기록(rosbag2) → Super-LIO 재생** 하나입니다.

- **실행 방법**: [RUN.md](RUN.md)에 핸드헬드 기록·시뮬레이터·실물 로봇별로 정리했습니다. 처음이면 아래 '처음 받은 팀원이 할 일'만 따라 하면 됩니다.
- **package 상태**: 아직 colcon package가 아닙니다. `ros_pkgs/README.md`의 `operator` 후보 경계에 두었고, package 구성과 위치는 리뷰에서 정합니다.

## 처음 받은 팀원이 할 일

Ubuntu 24.04와 Windows의 WSL2(Ubuntu 24.04)에서 같은 명령입니다. Node.js는 없어도 됩니다(없으면 Docker 안에서 빌드).

- **Windows**: WSL2 Ubuntu 24.04와 Docker Desktop을 설치하고, Docker Desktop의 WSL integration에서 그 Ubuntu를 켭니다. 아래 명령은 모두 Ubuntu 터미널에서 실행합니다.
- **네이티브 Ubuntu 24.04**: WSL·Docker Desktop 설치와 연동은 필요 없습니다. Docker Engine만 있으면 아래 1번의 `./docker/hn pull ros`부터 그대로 합니다.

1. **Docker 준비**: 저장소 최상위에서 `./docker/hn pull ros`로 팀 ROS 이미지를 받습니다. WSL이면 Docker Desktop → Settings → Resources → WSL integration에서 쓰는 Ubuntu를 켜고(Apply & restart), 저장소와 데이터는 Windows 폴더(`/mnt/c/...`)가 아니라 WSL 홈(`~/`)에 둡니다. `/mnt/c`를 거치면 파일 읽기·쓰기가 크게 느립니다.
2. **데이터 받기**: 팀 Drive `14. AI Team/`에서 아래 두 곳을 같은 폴더 구조로 `~/hypernova-data/ai-team/`(또는 `--data`로 지정한 곳)에 받습니다.

   | Drive 경로 | 크기 | 쓰는 곳 |
   | --- | --- | --- |
   | `data/recordings/20261115T120809_074988Z_measurement_e03893/rosbag2/` | 약 1.9 GB | 핸드헬드 기록 재생 |
   | `data/dashboard_public/` | 약 11 MB | 지형 메시·지도 프리뷰·로봇 모델(`public/`) |

3. **준비**: `replay/run-demo.sh setup`. Drive 사본을 확인하고 `dashboard_public`의 해시를 대조한 뒤 `public/`에 복사합니다. 없는 재생 이미지(FAST-LIO2 twist, Super-LIO)를 빌드합니다(처음 한 번 약 10분).
4. **실행**: `replay/run-demo.sh bag`(핸드헬드 기록 재생, `--rate 0.5`처럼 배속 지정 가능). 브라우저가 열리면 데이터 소스 '핸드헬드 기록 재생'을 고르고 '수신 시작'을 누릅니다. 끝낼 때는 `replay/run-demo.sh stop`.

컨테이너는 `ROS_DOMAIN_ID=42`로 띄웁니다. 같은 호스트의 다른 ROS 컨테이너와 같은 domain이면 토픽이 섞입니다.

### 연결 주소

- 미리 정한 데이터 소스는 모두 `ws://localhost:8765`입니다. localhost는 대시보드를 연 그 PC라는 뜻이라, 각자 자기 PC에서 위 스크립트로 띄우면 주소를 바꿀 필요가 없습니다.
- **다른 PC나 실기 로봇의 데이터를 볼 때**: 데이터를 내는 쪽에서 `foxglove_bridge`가 모든 주소에서 받도록 띄웁니다(`address:=0.0.0.0`, 이 스크립트는 `--expose`). 대시보드 쪽은 톱니(연결 설정) → Foxglove WebSocket 주소를 `ws://<그 PC IP>:8765`로 바꿉니다. 같은 네트워크여야 하고 방화벽에서 8765/TCP가 열려 있어야 합니다. 바뀐 주소와 토픽은 그 브라우저에 저장됩니다.

## 확인한 범위 (2026-11-28)

| 항목 | 결과 |
| --- | --- |
| 단위·인터페이스 시험 | `npm test` 77개 통과, `tsc`·`vite build` 통과 (Windows, Node.js 24.19.0). `public/robot/`이 없으면 URDF 사본 시험 1개는 건너뜁니다 |
| 핸드헬드 bag → Super-LIO → 대시보드 | WSL2에서 11-15 기록 1배속 전체 재생. 위치·궤적·로그·LiDAR 누적 실시간 갱신, 경사로 구간(z 약 6 m)에서도 로봇이 지형 위에 섬 |
| 위치추정 상태 | 같은 재생에서 `localization_status.py`가 `ACQUIRING` → `TRACKING`(10 Hz), 재생이 끝나면 `INPUT_TIMEOUT`. 대시보드에 `TRACKING · CODE 1` 표시 |
| 지도 정합 | `replay/registration/1115_superlio.env`. FAST-LIO2 정합 경로 대비 수평 차이 중앙값 0.46 m, p95 0.69 m. 같은 기록 안에서만 유효합니다 |
| WSL2 실행 | Windows 10 + Docker Desktop 29.9 + WSL2 Ubuntu 24.04, Node.js 없음: `setup` 6 s, `bag`(Docker 안 웹 빌드 70 s 포함) → 위치·LiDAR 수신 |
| 보행 상태 (G-006) | main(#22)의 `/locomotion/status`(`DiagnosticArray`) 해석을 `tests/locomotion.test.ts`로 확인. 11-27 연결 시험용 SIM에서 WALKING → `FALLEN · tilt` 표시 확인 |
| 글로벌 경로 (S-012 준비) | `nav_msgs/Path` 구독·해석을 `tests/path.test.ts`로 확인. 11-27 연결 시험용 SIM의 `/plan` 200점이 지도에 자홍색 선으로 표시 |

확인하지 못한 것:

- 보행팀 시뮬레이터(MuJoCo·Isaac)와 실물 로봇 연결. 로봇에 LiDAR·IMU가 들어가고 위치·LiDAR 토픽을 낸 뒤 합니다.
- 지도 정합(relocalization). 첫 위치를 한 번 맞춘 뒤 LIO가 이동량을 쌓는 방식이라 누적 오차가 보정되지 않습니다. 화면의 로봇이 지형 메시의 차량·나무와 겹쳐 보이는 곳은 이 오차, 지도와 기록의 촬영 날짜 차이, 표시용 메시 단순화(0.4 m) 때문입니다.
- LiDAR–IMU 외부 보정(추정값 사용), 실제 `hn_interfaces` 메시지, Nav2 실제 `/plan` 출력.

## 토픽

| 역할 | 기본 토픽 | 형식·좌표 | 핸드헬드 재생에서 내는 곳 |
| --- | --- | --- | --- |
| 추정 위치·자세 (필수) | `/localization/odometry` | `nav_msgs/msg/Odometry`, `pair360_map → mlx_lidar` | Super-LIO `/lio/odom` → `adapters/lio_adapter.py`가 frame을 바꿔 발행 |
| 현재 LiDAR | `/lidar/points` | `sensor_msgs/msg/PointCloud2` | Super-LIO의 정합 스캔(`/lio/cloud_world`, `world` frame) |
| 좌표 변환 | `/tf`, `/tf_static` | `tf2_msgs/msg/TFMessage` | `static_transform_publisher`: `pair360_map → world`(정합값), `imu → mlx_lidar` |
| 시각 | `/clock` | `rosgraph_msgs/msg/Clock` | `ros2 bag play --clock` |
| 위치추정 상태 | `/localization/status` | 임시 `diagnostic_msgs/msg/DiagnosticArray`([localization-status.md](../../../docs/interfaces/localization-status.md)) 또는 `hn_interfaces/msg/LocalizationStatus` 초안, 코드 0~5 | `adapters/localization_status.py` |
| 기준 지도 | `/localization/reference_map` | `sensor_msgs/msg/PointCloud2`, 시작 시 1회, transient-local | `adapters/reference_map_ros.py`(`public/map-*.pcd`) |
| 보행 상태 (G-006) | `/locomotion/status` | `diagnostic_msgs/msg/DiagnosticArray`([locomotion-status.md](../../../docs/interfaces/locomotion-status.md)) 또는 `hn_interfaces/LocomotionStatus` 초안 | 없음. 보행팀 시뮬(`tools/demo/state_walk_mujoco.sh --ros-topic /locomotion/status`)이 냄 |
| 글로벌 경로 (S-012) | `/plan` | `nav_msgs/msg/Path` | 없음. Nav2 planner_server가 낼 예정 |
| GT (선택) | 기본값 없음, '시뮬레이터' 소스는 `/ground_truth/odom` | `nav_msgs/msg/Odometry` | 없음. 시뮬에서만 지정, 실기는 비웁니다 |

- 모든 토픽은 같은 `ROS_DOMAIN_ID`의 `foxglove_bridge`를 거쳐 브라우저로 옵니다. 구독 목록은 `src/bridge.ts`, 기본 토픽 이름은 `src/model.ts`의 기본 설정에 있고, 화면 톱니(연결 설정)에서 바꿀 수 있습니다.
- 지형 메시·지도 프리뷰·로봇 모델은 ROS를 거치지 않습니다. `setup`이 Drive `dashboard_public`을 `public/`에 복사하고 웹 서버가 파일로 읽습니다.
- 위치추정 상태 코드: 0 `ACQUIRING`, 1 `TRACKING`, 2 `DEGRADED`, 3 `LOST`, 4 `STALE_INPUT`, 5 `INPUT_TIMEOUT`. `localization_status.py`는 Odometry의 주기·끊김·튐으로 판정합니다(지도 기준 정확도 판정은 아님). `hn_interfaces` 형식의 코드 필드 경로 기본값 `status`는 가정이며 설정에서 바꿀 수 있습니다.
- 상태 메시지를 한 번도 받지 못하면 '상태 메시지 없음'으로 표시합니다. 알고리즘 상태와 통신 상태(Odometry 수신 여부)는 따로 표시합니다.
- 글로벌 경로는 frame이 `pair360_map`이 아니면 TF로 바꿔 그립니다. Nav2 `map` frame을 쓰면 `pair360_map ↔ map` TF가 bridge에 함께 나와야 합니다.
- 보행팀 시뮬은 현재(2026-11-27 main 확인) 보행 상태만 냅니다. 지도 위 로봇·궤적·LiDAR까지 보려면 시뮬에서 `/localization/odometry`, `/lidar/points`, `/clock`을 내야 합니다. 예시 훅이 `adapters/mujoco_ros.py`입니다.

## 좌표·시각 규칙

- 위치·자세의 기준은 몸체 중심이 아니라 `mlx_lidar`입니다. 팀 URDF의 LiDAR frame은 `front_lidar`이므로, 두 이름을 하나로 맞추거나 정적 TF로 이어야 합니다.
- GT는 ±50 ms 안의 가장 가까운 표본과 비교합니다(보간 없음). parent·child frame이 다르면 GT 오차는 N/A입니다.
- 현재 스캔은 최신 Odometry 측정 시각 ±120 ms 안에서 고릅니다. LiDAR가 10 Hz보다 느리면 스캔이 표시되지 않을 수 있습니다.
- 동적 TF는 ±50 ms 안에서만 쓰고, 정적 TF는 시각과 무관하게 씁니다.
- 주행 속력은 기본적으로 LIO가 추정한 선속도(Odometry `twist.linear`)입니다. REP-105에 따라 twist는 child frame 기준이므로 같은 메시지의 자세로 지도 좌표로 돌린 뒤 수평 성분의 크기를 씁니다. 세 성분이 모두 정확히 0이면 채우지 않은 값으로 보고 연속 위치 차분(`0 < Δt ≤ 1 s`)으로 대체합니다. 화면·CSV에 속력 출처(`LIO twist 선속도`, `pose 차분 (twist 미기재)`, `pose 차분`)를 남깁니다.
- 팀 이미지의 FAST-LIO2(`docker/ros/hypernova.repos`의 ROS2 branch `a4743b0`)는 twist를 0으로 두므로 위치 차분이 쓰입니다. `adapters/fast_lio_twist/`는 twist를 채우도록 다시 빌드한 로컬 시험 이미지입니다. 어댑터가 child를 `mlx_lidar`로 바꿀 때는 속도도 장착 회전과 레버암만큼 바꿔야 합니다.
- wall 시각으로 찍힌 기록(약 1.8e9 s)은 세션 시작 뒤 경과 초로 보여 주고, CSV에는 원래 stamp를 남깁니다. `/clock`이 뒤로 가면 새 세션으로 보고 동적 기록을 지웁니다.

## 화면

- **배치**: 메뉴 한 줄, 왼쪽 위 [3D 지도 | 위치], 왼쪽 아래 [상태 | LiDAR], 오른쪽 [로그]. 패널 사이 손잡이 4개로 크기를 바꾸고 브라우저에 저장합니다(두 번 누르면 기본값).
- **데이터 소스**: `핸드헬드 기록 재생`, `시뮬레이터`(GT 토픽 자동 설정), `실물 로봇`, `직접 지정`. 소스마다 주소와 GT 토픽만 다릅니다. 선택과 연결 설정은 localStorage에 남습니다.
- **연결 오류 안내**: 한 번도 열리지 않은 경우(데이터 소스가 꺼져 있음)와 열린 뒤 끊긴 경우(bag 재생 종료 등)를 나눠 보여 줍니다.
- **시점**: '로봇 따라가기 / 지도 전체 / 평면도'. '로봇 따라가기'는 로봇 뒤 7 m·위 4 m에서 시작해 로봇이 도는 만큼 같이 돕니다.
- **지형 메시**: pair360-map mesh_v3 PLY(지면·장애물·나무)를 0.4 m 군집으로 단순화한 회색 표시용 메시입니다(`python adapters/prepare-terrain-ply.py <mesh_v3 폴더>`). 충돌면이 아닙니다.
- **LiDAR 누적**: 받은 모든 스캔을 0.07 m voxel당 1점으로 최대 300만 점까지 쌓고, 바로 아래 지면 기준 높이(0–5 m)로 무지개색(turbo)을 칠합니다. 현재 스캔은 흰색입니다.
- **로봇**: `description/hn_v1_hyper` URDF를 `python adapters/prepare-robot.py <description/hn_v1_hyper> --cell-mm 3`으로 `public/robot/hn_v1_hyper/`에 경량화해 그립니다(시각 메시 약 55만 → 8만 삼각형). 로봇 형상의 정본은 `description/`이므로 이 사본은 커밋하지 않고, 없으면 간략 모델로 돌아갑니다. 위치·방향(yaw)은 `mlx_lidar` 추정값에 URDF `front_lidar` 장착 오프셋을 반영하고, 높이는 바로 아래 지면 + 서 있는 높이입니다. 다리는 `src/gait.ts`의 trot 표시용 애니메이션이며 관절 실측이나 보행 정책 출력이 아닙니다.
- **글로벌 경로**: `/plan`을 받으면 자홍색 선과 '글로벌 경로' 레이어·범례가 나타납니다.
- **화면 갱신**: 패널은 120 ms 간격으로 묶어 다시 그리고 로그는 최근 100행만 그립니다. 3D 화면은 매 프레임 store를 직접 읽습니다.

## 폴더 구성

| 경로 | 내용 |
| --- | --- |
| `src/` | 웹 화면. `bridge.ts`(Foxglove 연결·구독), `model.ts`(메시지 해석·기본 설정), `store.ts`, `MapView.tsx`(3D 지도), `LidarView.tsx`, `recorder.ts`(bag 기록) |
| `tests/` | vitest 시험과 합성 CDR 시험 서버(`foxglove-fixture.mjs`) |
| `replay/run-demo.sh` | `setup`·`bag`·`stop`. Docker 재생과 웹 화면을 함께 띄움 |
| `replay/run_bag_superlio.sh`, `super_lio_mlx.yaml`, `Dockerfile.superlio` | bag 재생 → Super-LIO(`f89f48d`) → 어댑터 → `foxglove_bridge` (컨테이너 안) |
| `replay/run_bag_lio.sh`, `fast_lio_mlx.yaml` | 같은 재생을 FAST-LIO2로 (이전 경로) |
| `replay/registration/` | `pair360_map` 정합값(`1115*.env`·`.json`)과 정합 스크립트. 비밀값이 아니라 좌표(m, rad)입니다 |
| `replay/record_demo.mjs`, `probe_fps.mjs` | S-015 영상 녹화·화면 fps 측정 (headless Chrome) |
| `adapters/lio_adapter.py`, `localization_status.py`, `reference_map_ros.py` | 재생 중 ROS 토픽을 내는 노드 (위 [토픽](#토픽) 표) |
| `adapters/prepare-*.py`, `prepare-*.mjs`, `sync-map.mjs` | `public/`에 넣는 지형·지도·로봇 표시 파일 생성 |
| `adapters/mujoco_ros.py`, `inspect_mujoco.py` | MuJoCo 시뮬에 붙이는 읽기 전용 발행 훅 예시와 모델 이름 확인 도구 (팀 보행 runner 연결은 미확인) |
| `adapters/fast_lio_twist/` | twist를 채운 FAST-LIO2 로컬 시험 이미지 |

원본 bag, 점군, 지형·로봇 메시는 커밋하지 않습니다(`.gitignore`).

## 개발 명령

이 폴더에서 실행합니다. Node.js가 없으면 `run-demo.sh`가 Docker 안에서 빌드하므로 필요 없습니다.

```bash
npm ci
npm run dev        # http://127.0.0.1:5173/  (데이터 소스는 replay/run-demo.sh로 띄움)
npm test
npm run build
```

## bag 기록 (브라우저)

ROS 수신 중 로그 패널의 'bag 기록'을 누르면, 받은 메시지를 디코딩 전 원본 CDR 그대로 ROS 2 bag(MCAP, profile `ros2`, 스키마 `ros2msg`)으로 기록합니다. '기록 종료', 수신 중지·재연결, 또는 메시지 합계 1 GB에서 `hyper-<시작 시각>.mcap`으로 내려받습니다.

- 기준 지도와 `/tf_static`처럼 한 번만 오는 토픽은 마지막 메시지를 bag 맨 앞에 넣고, transient-local QoS를 channel metadata에 기록합니다. 재생 때 늦게 붙은 구독자도 받습니다.
- 대시보드가 구독한 토픽만, Bridge가 전달한 만큼만 들어갑니다. 브라우저 메모리에 쌓으므로 긴 기록은 로봇에서 `ros2 bag record -s mcap`을 씁니다.
- Jazzy `ros2 bag info`의 토픽 목록에는 지도 토픽이 빠지지만 메시지 수에는 포함되고 재생도 됩니다(2026-11-16 확인).

```bash
ros2 bag info hyper-<시각>.mcap
ros2 bag play hyper-<시각>.mcap --clock
```

## 지도 레이어와 프리뷰 만들기

prior는 지면 점군, 비지면 점군(차량·노이즈 제외), 지형 메시 세 겹이고, 그 위에 LiDAR와 GT를 얹습니다. 각 레이어는 지도 아래 체크로 켜고 끕니다.

- 라벨 번호는 S-004 분류 결과를 따릅니다: 0 미확정, 1 지면, 2 줄기, 3 수관·관목, 4 시설물, 5 차량, 6 노이즈. 5·6은 prior로 그리지 않습니다.
- 로컬 지도는 실시간 연결 중 '지도 좌표와 표시 frame의 정합을 확인함'을 켜야 궤적과 겹칩니다. ROS로 받은 지도는 header frame이 표시 frame과 같으면 그대로 겹칩니다.

지금 팀원은 Drive `dashboard_public`을 받아 쓰면 됩니다. 지도 릴리스가 바뀌어 프리뷰를 다시 만들 때만 아래를 씁니다.

```bash
HN_MAP_RELEASE=/data/map-release npm run map:sync -- --check   # 최신 여부만 확인
HN_MAP_RELEASE=/data/map-release npm run map:sync              # 바뀐 경우에만 다시 생성
```

- 릴리스 폴더 구조: `output/manifest.json`, `output/reference_map.pcd`, `terrain/scene/{scene.xml,manifest.json,hfields/}`.
- `prepare-map.mjs`는 PCD sha256이 manifest의 `reference_sha256`과 같을 때만 프리뷰(voxel·라벨당 실측점 1개, 8만 점 이하)를 만들고, 검수 상태(`status`)를 그대로 화면에 보여 줍니다.
- `prepare-terrain.mjs`는 MuJoCo heightfield를, `prepare-terrain-usd.py`는 Isaac Sim USD를 표시용 메시로 만듭니다. 지금 쓰는 지형은 위 '화면'의 mesh_v3 PLY 판입니다.

## 남은 일

- 위치추정 상태: 임시 DiagnosticArray 판정을 지도 정합 점수 기반으로 바꾸고 `hn_interfaces` 형식 확정
- 지도 정합(relocalization): 누적 오차 보정과 실기 첫 위치 정합
- S-012: Nav2 실제 `/plan` 연결, waypoint 순서·keepout 구역 표시, 대시보드에서 waypoint 찍기(발행이 생기므로 읽기 전용 원칙과 안전 조건을 함께 정함)
- 보행팀 시뮬·실물 로봇 연결 (로봇에 LiDAR·IMU가 들어간 뒤)
- GT 토픽 이름과 `mlx_lidar`·`front_lidar` frame 이름 합의
- LiDAR–IMU 외부 보정
- 이 폴더를 colcon package(launch·config 포함)로 정리할지 결정

## 변경 이력

- **2026-11-16**: 첫 판. 합성 CDR 시험 서버와 MuJoCo 운동학 SIM으로 웹 연결·브라우저 bag 기록 확인.
- **2026-11-26**: 11-15 핸드헬드 기록을 Super-LIO로 재생해 `pair360_map` 위에 표시. mesh_v3 지형, LiDAR 누적, 팀 URDF 로봇 표시.
- **2026-11-27**: 화면 재배치, 데이터 소스 선택, G-006 보행 상태(`DiagnosticArray`) 연결, 글로벌 경로 표시, `run-demo.sh`(Ubuntu·WSL2 공통)로 PowerShell판 대체, S-015 녹화 도구.
- **2026-11-28**: 임시 위치추정 상태 발행(`localization_status.py`), [RUN.md](RUN.md) 추가, main(#22·#25) 병합. 11-16~11-27에 화면 연결 시험용으로 쓰던 MuJoCo 운동학 SIM(`mujoco_route_sim.py`, `run-demo.sh sim`)은 보행 시뮬로 오해될 수 있어 뺐습니다.
