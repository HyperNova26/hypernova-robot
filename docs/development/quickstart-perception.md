# 빠른 시작 — 인지·SW (`hn:ros`)

`hn:ros`에서 LIO(RKO-LIO)를 샘플 bag으로 돌려 정답 경로와 비교하고, rviz2·Foxglove로 보고, 다른 컨테이너(`hn:sim`)가 내보낸 토픽이 **데이터까지** 받아지는지 확인하는 과정입니다. LIO 알고리즘을 튜닝하는 문서가 아니라 **환경이 처음부터 끝까지 이어지는지** 확인하는 문서입니다.

2026-10-22에 Ubuntu 24.04 PC(20코어)의 `hn:ros`, `hn:sim` 이미지에서 아래 명령을 그대로 실행해 확인했습니다. 1~4단계는 GPU 없이 됩니다. 5단계의 Isaac Sim 부분만 `hn:sim` 이미지와 GPU가 있는 PC에서 합니다.

## 준비

[Docker 개발 환경](../../docker/README.md)의 호스트 준비(Docker Engine, sudo 없이 쓰기)를 마치고 이미지를 받습니다. GHCR에 아직 올라오지 않았으면 직접 빌드합니다(이 PC에서 약 6분).

```bash
./docker/hn pull ros
```

```bash
./docker/hn build ros
```

## 1. 컨테이너에 들어가기

```bash
./docker/hn ros
```

프롬프트가 `(hn:ros) /workspace/hypernova $`로 바뀌면 컨테이너 안입니다. 아래 명령은 모두 이 셸에서 칩니다. 터미널이 더 필요하면 호스트에서 같은 명령을 다시 치면 같은 컨테이너에 셸이 하나 더 열립니다. 이 문서의 "터미널 1", "터미널 2"가 그것입니다.

환경이 제대로 깔렸는지 먼저 확인합니다. 모든 줄이 `OK`이고 마지막에 `모두 통과`가 나와야 합니다.

```bash
/opt/hn/scripts/selftest.sh
```

## 2. 샘플 bag 준비

작은 공개 LiDAR+IMU ROS 2 bag을 찾지 못했습니다. NVIDIA r2b 데이터셋(CC-BY-4.0)은 LiDAR가 든 sequence가 1.2~3.9 GB이고 IMU–LiDAR 변환(TF)이 없습니다. 그래서 같은 환경에서 몇 초 만에 만드는 합성 bag 생성기를 저장소에 두었습니다. 방 하나를 8자 경로로 도는 로봇의 LiDAR(16채널, 점마다 측정 시각 포함)와 IMU, 정적 TF, 정답 경로를 담은 MCAP입니다.

```bash
/opt/hn-venv/bin/python tools/make_demo_bag.py
```

```text
만들었습니다: /data/bags/demo-room  (17.9 MB, 30초, LiDAR 299회, IMU 6000개)
마지막 스캔 시작 시각 29.8초 기준 정답 — 시작 자세를 원점으로 본 로봇(base_link) 자세
  위치 x=-0.963 y=+2.754 z=+0.000 m,  yaw=-177.0 deg
```

```bash
ros2 bag info /data/bags/demo-room
```

| 토픽 | 타입 | 주기 |
| --- | --- | --- |
| `/lidar/points` | `sensor_msgs/msg/PointCloud2` (`x y z intensity t`) | 10 Hz |
| `/imu/data` | `sensor_msgs/msg/Imu` | 200 Hz |
| `/tf_static` | `tf2_msgs/msg/TFMessage` (`base_link`→`lidar`, `imu_link`) | 1회 |
| `/ground_truth/odom` | `nav_msgs/msg/Odometry` (평가용) | 20 Hz |

bag은 호스트 `~/hypernova-data/bags/demo-room`에 생깁니다. 같은 `--seed`면 항상 같은 bag이고, 이미 있으면 `--force`로 덮어씁니다.

### 내 bag을 쓰려면

호스트 `~/hypernova-data/bags/<이름>/` 폴더째로 두면(`metadata.yaml`과 `*.mcap`/`*.db3`가 같이 있어야 함) 컨테이너 안 `/data/bags/<이름>`으로 보입니다. RKO-LIO가 요구하는 조건은 다음과 같습니다.

- LiDAR 점구름에 점별 시각 필드(`t`, `time`, `timestamp`, `timestamps`, `stamps` 중 하나)가 있어야 합니다. 없으면 deskew를 끌 수밖에 없습니다.
- IMU와 LiDAR가 같은 시계로 동기돼 있어야 하고, IMU는 가속도 m/s²·각속도 rad/s이며 정지 상태에서 +z가 +g를 가리켜야 합니다.
- IMU–LiDAR–base 외부 파라미터는 bag의 TF 트리에 있거나 설정 파일의 `extrinsic_imu2base_quat_xyzw_xyz`, `extrinsic_lidar2base_quat_xyzw_xyz`(`[qx,qy,qz,qw,x,y,z]`)로 줍니다.

bag은 Git에 넣지 않습니다([저장소 정책](./repository-policy.md)).

## 3. LIO 돌리기 (RKO-LIO)

`ros-jazzy-rko-lio`가 이미지에 들어 있습니다. bag을 끝까지 처리하는 offline 모드가 가장 빠릅니다(약 3초).

터미널 1 — 결과를 정답과 비교할 스크립트를 먼저 켜 둡니다(`/rko_lio/odom`을 기다림).

```bash
./docker/hn ros /opt/hn-venv/bin/python tools/check_demo_lio.py /data/bags/demo-room
```

터미널 2 — LIO를 돌립니다.

```bash
./docker/hn ros ros2 launch rko_lio odometry.launch.py mode:=offline bag_path:=/data/bags/demo-room initialization_phase:=true rviz:=false
```

터미널 2는 `RKO LIO Offline Node took 2.8 seconds` 같은 줄과 처리 시간 통계를 찍고 끝납니다. 터미널 1은 odom이 8초 동안 멈추면 결과를 냅니다.

```text
odom 299개를 받았습니다.
마지막 자세  LIO  x=-0.949 y=+2.718 z=+0.018 m  yaw=-175.1 deg
             정답 x=-0.997 y=+2.752 z=+0.000 m  yaw=-174.8 deg
위치 오차: 마지막 6.2 cm, 평균 6.1 cm, 최대 18.5 cm
yaw 오차: 마지막 -0.29 deg
결과: 정상
```

- `initialization_phase:=true`는 로봇이 정지한 채 시작하는 bag이라서 줍니다(IMU로 초기 자세와 bias를 추정).
- 토픽 이름과 프레임은 bag에서 자동으로 찾고, IMU–LiDAR 외부 파라미터는 bag의 `/tf_static`에서 읽습니다.
- 오차 평균이 25 cm를 넘으면 `결과:` 줄이 실패를 알리고 종료 코드 1입니다(`--max-mean-error`로 조정).
- 합성 데이터라서 위 값은 LIO의 성능 지표가 아니라 환경 점검용입니다. 같은 seed면 값이 같습니다.

알고리즘 옵션은 `ros2 launch rko_lio odometry.launch.py -s`로 볼 수 있습니다.

## 4. 눈으로 보기

### rviz2

실제 센서처럼 시간에 맞춰 재생하면서 보려면 online 모드로 돌립니다.

터미널 1:

```bash
./docker/hn ros ros2 launch rko_lio odometry.launch.py lidar_topic:=/lidar/points imu_topic:=/imu/data base_frame:=base_link autodetect:=false initialization_phase:=true publish_local_map:=true rviz:=true
```

터미널 2 (30초 재생):

```bash
./docker/hn ros ros2 bag play /data/bags/demo-room
```

rviz2 창에 방의 점구름(local map)과 이동 경로가 나타납니다. `ros` 이미지는 GPU 없이 소프트웨어로 그려서 큰 점구름에서는 느릴 수 있고, 터미널에 `glx: failed to create dri3 screen` 같은 메시지가 나와도 무시해도 됩니다. 창이 안 뜨면 호스트 데스크톱 세션의 터미널에서 실행했는지 확인합니다.

### Foxglove

브라우저나 데스크톱의 Foxglove로 보려면 bridge를 켭니다. 호스트 네트워크를 쓰므로 `localhost`로 접속됩니다.

```bash
./docker/hn ros ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:=127.0.0.1
```

Foxglove 앱에서 Open connection → Foxglove WebSocket → `ws://localhost:8765`로 연결하고 3D 패널에 `/lidar/points`, `/rko_lio/local_map` 등을 추가합니다. 위의 LIO와 `ros2 bag play`를 같이 돌려 둔 상태에서 보면 됩니다.

> [!WARNING]
> `address:=127.0.0.1`을 빼면 bridge가 `0.0.0.0`에서 받아서, 같은 네트워크의 다른 PC가 이 PC의 ROS 토픽을 볼 수 있습니다. 호스트 네트워크 컨테이너라서 그렇습니다. 학교 네트워크 같은 공용망에서는 반드시 붙이세요.

이 환경에서 확인한 것은 bridge가 뜨고 호스트에서 `ws://localhost:8765`에 WebSocket(`foxglove.sdk.v1`)이 열리는 것까지입니다. Foxglove 앱 화면은 확인하지 못했습니다. bridge 3.6.0은 `foxglove.sdk.v1`만 받으므로 앱은 최신 버전을 씁니다.

## 5. 다른 컨테이너의 토픽 받기

`hn:sim`과 `hn:ros`는 호스트 네트워크를 쓰고 같은 `docker/.env.local`의 `ROS_DOMAIN_ID`를 받으므로, 한 컨테이너가 내보낸 토픽을 다른 컨테이너가 바로 받습니다. 이 단계는 두 이미지가 모두 있는 PC에서 합니다(`./docker/hn build sim`을 한 PC).

### Isaac Sim 없이 빠르게

터미널 1 (`sim`이 발행):

```bash
./docker/hn sim ros2 topic pub -r 5 /hn_test std_msgs/msg/String "{data: hello}"
```

터미널 2 (`ros`가 받음):

```bash
./docker/hn ros ros2 topic echo /hn_test std_msgs/msg/String
```

`data: hello`가 계속 나오면 컨테이너 사이 통신이 됩니다. `Ctrl+C`로 끝냅니다. 타입(`std_msgs/msg/String`)을 적지 않으면 토픽이 아직 없을 때 `echo`가 바로 끝납니다.

### Isaac Sim의 `/clock`

Isaac Sim ROS 2 bridge가 시뮬레이션 시각을 `/clock`으로 내보내게 하고 `ros`에서 받습니다. Isaac Sim이 뜨고 bridge가 켜질 때까지 20초쯤 걸립니다.

터미널 1 (`sim`, 90초 동안 발행):

```bash
./docker/hn sim ./isaaclab.sh -p /workspace/hypernova/tools/isaac_clock_pub.py --seconds 90
```

터미널 2 (`ros`, 토픽이 생길 때까지 기다렸다가 한 개 받음):

```bash
./docker/hn ros ros2 topic echo /clock rosgraph_msgs/msg/Clock --once
```

```text
clock:
  sec: 2
  nanosec: 783333333
```

시각 값은 실행마다 다릅니다.

```bash
./docker/hn ros ros2 topic hz /clock
```

`average rate`가 수백 Hz로 나옵니다(headless에서 프레임마다 발행. 이 PC에서 약 300 Hz). `Ctrl+C`로 끝냅니다.

Isaac Sim이 쓰는 ROS 라이브러리는 이미지에 설치한 시스템 Jazzy입니다(시작 로그의 `Attempting to load system rclpy` → `rclpy loaded`). 통신에 shared memory를 쓰지 않고 UDP만 쓰므로 컨테이너를 어떻게 띄웠든 통합니다([이유와 실험 결과](../../docker/README.md#sim과-ros-사이-ros-통신)).

## 6. FAST-LIO

FAST-LIO2(`fast_lio`)와 `livox_ros_driver2` 메시지도 `hn:ros`에 들어 있고 `/opt/hn_ws`에 설치돼 있습니다. 실행 파일과 의존 라이브러리가 제대로 있는지는 이렇게 확인합니다.

```bash
./docker/hn ros timeout 6 ros2 launch fast_lio mapping.launch.py config_file:=velodyne.yaml rviz:=false
```

`Node init finished`가 나오면 뜬 것입니다. FAST-LIO는 센서에 맞는 설정(`config/*.yaml`: LiDAR 종류, 토픽, IMU–LiDAR 외부 파라미터)을 직접 써야 하므로 위 데모 bag에는 바로 쓰지 않습니다. 소스 폴더에 지도(PCD)와 로그를 쓰는 구조라 이미지에서는 지도 저장(`pcd_save_en`)이 동작하지 않습니다([알아 둘 제약](../../docker/README.md#알아-둘-제약과-겪은-문제)).

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| `Could not determine the type for the passed topic`, `echo`가 바로 끝남 | 토픽이 아직 없음. 타입을 같이 적습니다(`ros2 topic echo /clock rosgraph_msgs/msg/Clock`) |
| 다른 컨테이너 토픽 이름은 보이는데 데이터가 없음 | 한쪽이 `docker run`으로 직접 띄워져 UDP 전용 프로파일이 빠졌는지([문제 해결](../../docker/README.md#문제-해결)) |
| 남의 토픽이 보임 | `docker/.env.local`의 `ROS_DOMAIN_ID`가 다른 사람과 겹침. 고친 뒤 `./docker/hn reset` |
| `make_demo_bag.py`가 `이미 있습니다` | 이미 만든 bag. 그대로 쓰거나 `--force` |
| LIO 결과가 `odom`을 못 받음 | 터미널 1을 먼저 켰는지, bag 경로가 맞는지. 처리 중 로그의 `Skipping IMU, waiting for first LiDAR message`는 정상 |
| `transform lookup` 경고 | online 모드 시작 직후 `/tf_static`이 도착하기 전의 경고. 곧 사라집니다 |
| rviz2 창이 안 뜸 | 호스트 데스크톱 세션에서 실행했는지, `echo $DISPLAY` |
| 5단계 `hn sim`이 실패 | NVIDIA 드라이버·Container Toolkit이 필요합니다([호스트 준비](../../docker/README.md#호스트-준비)). 인지팀 PC에 GPU가 없으면 이 단계는 건너뜁니다 |
