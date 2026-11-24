<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# HyperNova 로봇 관제 데모 (S-005·S-006)

2026-11-24 기준입니다. 브라우저에서 캠퍼스 시설 순찰, 수동 개입, 이상 대응, 관련 기록 확인을 시연합니다. 기존 React·TypeScript·Vite·Three.js 앱의 3D 지도, LiDAR, TF, GT 비교, Foxglove 수신, CSV·MCAP 내보내기를 사용합니다.

이 대시보드는 `ros_pkgs/README.md`의 `operator` 후보 경계에 있는 웹 앱입니다. ROS 2 연결은 Foxglove WebSocket의 CDR·ros2msg 구독을 사용합니다.

## 실행

이 폴더에서 Node.js 22와 npm을 사용합니다.

```bash
npm ci
npm run dev
```

브라우저에서 <http://127.0.0.1:5173/>를 엽니다. 초기 화면은 **DEMO · TELEOP 대기**입니다. 앱에 포함된 지도와 브라우저에서 생성하는 위치·속도·알람을 사용합니다. 기본 시연은 지도 서버 연결 없이 실행됩니다.

## 운용 구역과 현장 지도

프로젝트의 최종 운용 범위는 **경희대학교 국제캠퍼스 내부**입니다. 초기 화면은 OpenStreetMap 실지도를 열고 **전자정보대학관 바로 북쪽 도로의 건물 중앙 맞은편**에 모의 로봇을 배치합니다. 초기 방향은 사색의 광장으로 이어지는 도로를 향하며, **시연 초기화**를 누르면 같은 위치로 돌아갑니다. TELEOP 이동, AUTO 임무 경로, 진행 상태, 알람 위치를 이 지도에서 확인합니다. **로봇 위치로 이동** 버튼은 현재 모의 위치를 중심에 놓습니다.

- [경희대학교 국제캠퍼스 안내도](https://www.khu.ac.kr/kor/user/contents/view.do?menuNo=200086)

### 관련 브랜치 검토

| 브랜치 | 관제에 반영할 범위 |
| --- | --- |
| `main` (`c8c0cf2`) | 벤치 펌웨어와 HYPER v1 정책·상태 문서가 포함되어 있습니다. 대시보드 기반은 `9b6a360`, `909db9e`입니다. |
| `feat/localization-status-fields` (`8b19cbd`) | 수신 시 위치추정 진단에 출처와 정합 품질을 표시합니다. [상태 메시지 정의](https://github.com/HyperNova26/hypernova-robot/blob/8b19cbdb8540f1f1d29cd484b4dda2e4b4cdfb2f/ros_pkgs/hn_interfaces/msg/LocalizationStatus.msg) |
| `feat/localization-status-fields`, `feat/sim-fault-injection` | PAIR360 실측 구역의 v3 경로는 원시 `pair360_map`을 사용합니다. 전자정보대학관 주변 모의 경로에 적용할 좌표 변환은 제공되지 않습니다. [v3 지도·경로 문서](https://github.com/HyperNova26/hypernova-robot/blob/feat/localization-status-fields/sim_scenes/pair360_map_v3/README.md) |
| `sw/msgs` | 지도·임무·제어권·사건 계약 초안을 향후 연동에 참고합니다. [SW 인터페이스 초안](https://github.com/HyperNova26/hypernova-robot/blob/sw/msgs/docs/interfaces/sw-contract.md) |

## 실제 지도에서 보행로 경로 만들기

1. **운용 → AUTO**에서 기본 지도를 그대로 사용합니다. **대학관 주변**은 전자정보대학관을, **사색의 광장**은 연결된 보행로를, **캠퍼스 전체**는 지도에 등록된 캠퍼스 경계를 보여 줍니다.
2. **경로 그리기**에서 청록색으로 표시된 보행로 가까이를 드래그합니다. 그린 선과 보정 경로를 확인한 뒤 **보정 경로 적용**을 누릅니다. 임무 이름을 입력하고 **임무 저장**을 누르면 **임무 관리**에서 다시 열 수 있습니다. 저장 임무를 열기 전에 **TELEOP**으로 전환합니다. 이전에 이 브라우저에 보정 경로를 저장했다면 **이전 보정 경로 가져오기**로 임무 초안을 만들 수 있습니다.
3. **임무 시작**을 누르면 모의 로봇이 첫 경유점에서 출발합니다. 실제 지도에서 모의 위치·궤적·현재 목표와 남은 거리를 확인할 수 있습니다. 일시정지와 재개는 AUTO 조작에서 선택합니다.

캠퍼스 임무는 OSM 지도 ID·추출본 버전·로컬 frame과 함께 저장됩니다. 임무를 시작하거나 재개하기 전에 각 구간의 연결을 확인합니다. 지도 정보가 일치하지 않으면 실행이 차단됩니다. 브라우저에 저장되어 있던 합성 임무는 **임무 관리 → 이전 합성 임무 보관함**에서 열람할 수 있습니다.

바탕 지도와 보행로는 2026-11-24에 받은 OpenStreetMap 데이터입니다. 전자정보대학관 중심 약 150 m 범위와 겹치는 교내 진입로·주차 통로 등은 DEMO 보행로로도 등록합니다. 캠퍼스 경계와 접근 제한을 적용하며 계단은 제외합니다. AUTO 경로 보정은 청록색으로 표시된 등록 구간과 공유 OSM 교차점만 사용합니다.

데이터는 `public/khu-osm.json`에서 제공합니다. 추출본은 [© OpenStreetMap contributors, ODbL](https://www.openstreetmap.org/copyright)로 배포합니다. 앱은 현장 장애물, 보행로 폭·경사, 로봇 통과 가능 여부를 실측하지 않습니다. 실기 임무에는 현장 확인과 로봇 좌표계 정합이 필요합니다.

## 반복 시연

1. **TELEOP**에서 방향키와 Z / X 또는 화면 버튼을 누르고 있다가 떼어 모의 로봇의 이동·회전·정지를 확인합니다. 캠퍼스 경계를 넘는 이동은 제한되며 **운용 정지**는 모의 이동을 멈추고 실행 중인 임무를 일시정지합니다.
2. **임무 관리 → 새 임무**에서 지도를 열어 경로를 그리고 저장합니다. 대학관 북쪽 도로는 **예제 임무 열기**로 바로 불러올 수 있습니다.
3. **AUTO → 임무 시작**을 누르고 지도에서 위치, 경유점, 남은 거리를 확인합니다.
4. **진행자용 시나리오**를 열고 **보행로 통행 방해물**을 발생시킵니다. 알람과 지도 마커를 열어 위치와 영향을 확인하고, **알람 확인**을 누른 뒤 대응 내용을 남깁니다.
5. **사건 시점 기록 열기**를 누릅니다. 활성 기록은 해당 사건 시점에서 열립니다. **재생**, 탐색과 배속을 확인한 뒤 **현재 운용으로 돌아가기**를 누릅니다.
6. 실행 중인 임무에서 **장애물로 진행 불가**를 발생시키거나 **위치추정·입력 복구** 시나리오에서 유실을 발생시킵니다. 임무의 일시정지와 재개 조건을 확인합니다. 장애물 상태에서는 TELEOP으로 개입할 수 있습니다.
7. 진행자 패널 또는 알람 상세에서 원인을 해소합니다. **AUTO → 임무 재개**를 눌러 주행을 계속합니다. 임무가 끝나면 **운용 기록 종료** 후 **기록 열람**에서 세션과 완료 이벤트를 확인합니다.
8. 다시 시연하려면 **시연 초기화**를 누릅니다. 새 모의 세션이 시작되고 저장한 임무와 초안은 다음 시연에서도 사용할 수 있습니다.

운용 기록은 기본 DEMO 세션 시작과 함께 수집합니다. 상단 기록 제어에서 시작과 종료를 확인할 수 있습니다. 운용 텔레메트리는 브라우저 탭 메모리에 최근 12개, 기록당 최대 4분을 보관합니다. 새로고침 후에도 임무·초안·사건 이력 메타데이터와 앱에 포함된 12초 합성 예제를 사용할 수 있습니다.

## 포함 자산 재생성

- `public/khu-osm.json`은 OpenStreetMap API에서 2026-11-24 05:00:32 UTC에 받은 XML로 생성했습니다. 원본 XML의 SHA-256은 `c99c634af038cffd981af6fa13d78a16cceb1d55970be15e13bfbda1ef772aa0`이며, 추출은 Python 3.12.3으로 실행했습니다.
- `public/demo-patrol.webm`은 `src/recordings.ts`의 예제 좌표와 시각에 맞춰 스크립트가 그린 HYPERNOVA 합성 영상입니다. Python 3.12.3과 FFmpeg `6.1.1-3ubuntu5`의 libvpx VP8 인코더로 480×270 픽셀, 12 fps, 12초 길이로 생성했습니다. 시연 영상은 CC BY 4.0 문서 자료로 제공합니다.

이 폴더에서 원본 XML 경로를 지정해 지도와 예제 영상을 재생성합니다.

```bash
python3 adapters/prepare-khu-osm.py --xml /path/to/khu.osm --timestamp 2026-11-24T05:00:32Z
python3 adapters/generate-demo-video.py
```

## AUTO 일시정지 후 수동 개입

일시정지 중 TELEOP으로 로봇을 이동한 경우, 현재 위치와 일시정지 지점 사이의 직선 구간이 등록된 보행로에 연결되어야 AUTO를 재개할 수 있습니다. 현재 위치에서 바로 재개할 수 없으면 TELEOP으로 일시정지 지점 쪽 보행로에 복귀하거나 임무를 취소합니다.

## 데이터 출처와 연동 경계

| 출처 | 현재 동작 |
| --- | --- |
| DEMO | OpenStreetMap 캠퍼스 지도, 브라우저 내부 모의 로봇·명령·사건 |
| ROS LIVE | 읽기 전용 Foxglove 연결, 수신 상태와 마지막 위치, ROS 토픽·TF 진단 및 MCAP 기록 |
| REPLAY | 기록 시점의 영상과 텔레메트리 표시. 상단에는 별도로 현재 로봇 상태와 활성 알람이 계속 표시됩니다. |

**ROS LIVE**를 선택하고 ROS 주소·토픽을 지정합니다. 기본 주소는 `ws://localhost:8765`입니다. 연결이 끊기면 마지막 수신 위치와 경과 시간을 표시합니다. **진단**에서 로컬 PCD 로드, LiDAR, GT, CSV·MCAP을 확인합니다. 프리뷰 지도와 ROS pose를 겹치려면 frame 정합을 먼저 확인합니다.

실제 로봇 제어, 카메라 및 navigation은 미연결입니다. 웹의 운용 정지는 DEMO 명령입니다. 물리 E-stop과 실물 시험 절차는 [로봇 안전 지침](../../../docs/operations/safety.md)을 따릅니다.

향후 연동할 경우 다음 경계를 사용합니다.

- `src/sources.ts`의 `TelemetrySource`로 수신, 합성, 재생의 데이터 출처를 지정합니다. ROS pose의 시작점은 `pair360_map → mlx_lidar`이며 몸체와의 관계는 검증된 TF가 필요합니다.
- `src/operation.ts`의 `CommandAdapter`에 실제 명령 전송 어댑터를 연결합니다. 명령 ID, 적용 결과, 시간 초과, 제어권 및 정지 상태를 확인할 전송 계약이 필요합니다.
- 임무 실행에는 지도 ID·버전·frame, 목표 수락, 진행·일시정지·취소 피드백이 필요합니다. 경유점 연결선을 실제 planner 경로로 사용하려면 별도 navigation 통합이 필요합니다.
- 카메라 영상은 스트림 연결 상태, 세션 ID, 시간 기준, 영상 offset, 보관 구간을 함께 제공해야 합니다. `src/recordings.ts`의 정규화 기록과 기존 MCAP은 각자 독립적으로 관리합니다.

## 검사

```bash
npm test
npm run build
```

로컬 합성 Foxglove 시험은 별도 터미널에서 `node tests/foxglove-fixture.mjs`를 실행하고 ROS 주소에 `ws://127.0.0.1:8766`을 지정합니다. 기존 실시간 연동 확인 이력은 아래와 같습니다.

## 기존 위치추정 연동 확인 이력

| 항목 | 결과 |
| --- | --- |
| 단위·인터페이스 시험 | `npm test` 37개 통과, `tsc`·`vite build` 통과 (Windows, Node.js 24.19.0, npm 11.17.0) |
| 합성 CDR 수신 | `tests/foxglove-fixture.mjs` 시험 서버로 확인 |
| MuJoCo SIM 실시간 연결 | `hn:ros` 이미지(로컬 빌드, `docker/.env`의 `2026.10.1`)에서 `adapters/mujoco_route_sim.py` + `foxglove_bridge`를 띄워 웹 연결까지 확인 |
| bag 기록 | 위 SIM에서 기록한 MCAP을 `ros2 bag info`로 읽고 `ros2 bag play`로 재생 확인 |
| 확인하지 못한 것 | 팀 LIO 어댑터 출력, 실제 LIO twist 값, 실제 `LocalizationStatus` 메시지, 실기·실센서, 팀 보행 runner와의 연결 |

MuJoCo SIM은 보행 시뮬레이션이 아닙니다. LiDAR만 단 mocap 몸체를 지형 위 경로로 옮기는 kinematic 재생이며, `/localization/odometry`에는 LIO 추정이 아니라 SIM 자세가 들어갑니다.

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

- 상태 코드: 0 `ACQUIRING`, 1 `TRACKING`, 2 `DEGRADED`, 3 `LOST`, 4 `STALE_INPUT`, 5 `INPUT_TIMEOUT`. 상태 코드 필드 경로 기본값은 `status`이며 설정에서 바꿀 수 있습니다. 추정기, 자세 발행 여부, 지연, inlier 비율, RMSE는 수신한 메시지에 값이 있을 때 진단에 표시합니다.
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
- 팀 LIO 어댑터 출력으로 실제 추정 궤적 확인
- 이 폴더를 colcon package(launch·config 포함)로 정리할지 결정
