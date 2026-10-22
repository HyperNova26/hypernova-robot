# ADR-0002: 공통 개발 환경

- 상태: **Proposed**
- 제안: 2026-10-21
- 관련: [#14](https://github.com/HyperNova26/hypernova-robot/issues/14)

## 배경

[개발 시작 안내](../development/getting-started.md)는 OS, ROS 2 배포판, 컨테이너, 시뮬레이터 버전을 첫 소프트웨어 ADR에서 정한다고만 적어 두었습니다. 11월 1일 킥오프부터 AICV와 SW 팀원이 같은 기준으로 개발을 시작해야 합니다.

이 환경에서 가장 어려운 부분은 OS나 ROS가 아니라 시뮬레이션·학습 스택입니다. Isaac Sim과 Isaac Lab은 약 240개 Python 패키지(torch, warp, Newton 등)가 서로 맞물린 묶음이라 새 인원이 직접 설치하다가 가장 많은 시간을 잃는 부분입니다. ROS apt 저장소도 최신 빌드만 남기기 때문에, 같은 `apt install`이라도 설치한 날짜에 따라 버전이 달라집니다.

SW 팀의 ROS 작업, 인지 트랙(LIO, 지형, 대시보드), 나중에 Jetson에 올릴 코드가 모두 같은 ROS 환경을 써야 합니다. 학습은 우선 팀원 개인 GPU(RTX 5070 Ti, 5070, 4070 Super)에서 하고, 학교 클러스터 Seraph는 드라이버(535)가 너무 낮아 이번 범위에서 뺍니다.

## 검토한 선택지

**A. 네이티브 설치만** — 도구가 적어 단순합니다. 대신 Isaac 스택 설치 비용이 사람마다 반복되고, apt·pip 버전이 설치 시점에 따라 갈라지며, 공용 GPU 머신에서 한 사람의 설치가 다른 사람 환경을 깨뜨릴 수 있습니다.

**B. 팀별 이미지** — 팀마다 필요한 것만 넣습니다. 하지만 같은 ROS 의존성이 이미지마다 중복되고, 팀 이름으로 경계를 나누는 것은 [ADR-0001](./0001-monorepo-first.md)의 원칙과 맞지 않습니다.

**C. `ros:jazzy` 위에 Isaac Sim을 pip로 설치한 이미지 하나** — ROS 이미지와 시뮬레이션 이미지가 실제 레이어를 공유합니다. 대신 NVIDIA 공식 이미지가 미리 해 둔 Vulkan·렌더링·캐시·권한 설정을 직접 맞춰야 해서, 킥오프 일정 안에서는 위험이 큽니다.

**D. Isaac Lab 2.x + Isaac Sim 5.1 이하** — 자료와 사례가 더 많습니다. 하지만 Isaac Sim 5.x는 Python 3.11이라 Jazzy(Python 3.12)와 맞지 않고, Isaac Lab 3.0은 Isaac Sim 5.1 이하를 지원하지 않습니다. 나중에 올리려면 task 코드를 다시 써야 합니다.

**E. 기능 기준 Dockerfile 하나에 build target 두 개** — NVIDIA 공식 Isaac Lab 이미지를 시뮬레이션 쪽 베이스로 쓰고, ROS 쪽은 `ros:jazzy`에서 시작합니다. 두 target이 같은 설치 스크립트와 같은 버전 고정을 씁니다.

## 결정

E로 갑니다.

### 1. 플랫폼

호스트, 컨테이너, Jetson 모두 **Ubuntu 24.04 + ROS 2 Jazzy**로 맞춥니다. Isaac Sim 6.2.0 공식 컨테이너와 Jetson용 JetPack 7.2.1이 모두 Ubuntu 24.04 기반이고, Isaac Sim 6.x의 Python 3.12가 Jazzy와 같습니다.

### 2. 이미지 두 개, Dockerfile 하나

| | `hn:sim` | `hn:ros` |
| --- | --- | --- |
| 베이스 | `nvcr.io/nvidia/isaac-lab:3.0.0` (Isaac Sim 6.2.0) | `ros:jazzy-ros-base` |
| 추가 | 공용 ROS 의존성, robot venv | 공용 ROS 의존성, robot venv, LIO |
| 필요 장비 | RTX GPU, VRAM 12 GB 이상 | GPU 불필요, amd64·arm64 |
| 받는 방법 | `./docker/hn build sim` (최초 한 번) | `./docker/hn pull ros` |
| 주 사용처 | 보행 학습·export·재생, 시뮬 센서 bag 기록, 데모 | SW ROS 작업, 인지(LIO·지형·대시보드), sim2sim |

- 두 target은 `docker/scripts/`의 같은 설치 스크립트를 씁니다. 그래서 한쪽에서 만든 bag과 노드가 다른 쪽에서 그대로 돕니다.
- 팀별 추가 의존성은 공용 스크립트에 섞지 않고 별도 스크립트로 둡니다.
- 두 베이스 이미지는 태그와 다이제스트로 고정합니다(`docker/.env`). `nvcr.io/nvidia/isaac-lab:3.0.0`은 NVIDIA 로그인 없이 받을 수 있습니다(2026-10-22 확인).

### 3. 이미지 배포

- `hn:ros`는 CI가 빌드해 GHCR(`ghcr.io/hypernova26/hn`)에 **public**으로 올립니다. public 패키지는 무료입니다.
- `hn:sim`은 **호스팅하지 않습니다.** 각자 NVIDIA 레지스트리에서 베이스를 받고, 우리 레이어만 로컬에서 빌드합니다. 20 GB가 넘는 NVIDIA 파생 이미지를 재배포할 때 생기는 라이선스 확인, private 패키지 용량, GHCR의 레이어당 10 GB·업로드 10분 제한을 모두 피합니다.
- 로컬 빌드의 재현성은 아래 버전 고정과 날짜를 고정한 ROS snapshot apt 저장소로 맞춥니다.

### 4. 버전 고정

| 항목 | 버전 | 근거 |
| --- | --- | --- |
| Ubuntu / ROS 2 | 24.04 / Jazzy | 호스트·컨테이너·Jetson 공통 |
| Isaac Sim | 6.2.0 | 최신 안정판. 7.0.0a1은 alpha |
| Isaac Lab | v3.0.0 (`e3f7d9f`) | Isaac Sim 6.x를 지원하는 유일한 버전. 2026-10-19 태그라 commit으로 고정 |
| 학습 physics | PhysX | 데모 runtime(Isaac Sim)과 같은 물리 엔진. 두 번째 엔진 검증은 MuJoCo가 맡음. Isaac Lab 3.0.0 내장 과제의 기본값은 `newton_mjwarp`라서 학습·재생 wrapper(`hn-rl`, `./docker/hn train\|play`)가 `physics=isaacsim_physx`를 자동으로 붙이고, 직접 지정하면 그 값을 씀 |
| torch / warp / RSL-RL | 2.11.0+cu130 / 1.17.0 / 5.5.1 | Isaac Lab `uv.lock` 그대로. `isaac-lab:3.0.0` 이미지의 `/opt/isaaclab-venv`에서 2026-10-22에 확인. 따로 올리지 않음 |
| MuJoCo | 3.12.0 | Isaac Lab lock과 같은 버전. 이미지 안에 MuJoCo 버전을 하나만 둠 |
| ONNX | 1.22.0 | Isaac Lab venv와 같은 버전. export opset은 명시(예: 17) |
| ONNX Runtime | 1.26.0 (CPU) | `/opt/hn-venv`에만 설치. Isaac Lab venv에는 포함되지 않으며 추가하지 않음 |
| Open3D | 0.19.0 | Isaac Lab lock과 같음. arm64(Jetson) 이미지에는 일부러 넣지 않음([결과](#결과) 참고) |
| numpy | robot venv 1.26.4 / Isaac Lab venv 2.5.1 | 서로 다른 venv라 의도한 차이. robot venv는 ROS Jazzy 메시지 바인딩(numpy 1.x C API)에 맞춰 1.26.4로 고정 |
| LIO | `ros-jazzy-rko-lio`, FAST-LIO `ROS2` 브랜치 + `livox_ros_driver2` | 소스 빌드분은 `.repos`에 commit 고정 |
| RMW | `rmw_fastrtps_cpp` | Jazzy 기본값, Isaac Sim이 검증한 조합 |
| rosbag 저장 형식 | MCAP | Jazzy 기본값 |

robot venv(`/opt/hn-venv`: MuJoCo, ONNX Runtime, Open3D 등)는 Isaac Lab venv와 분리해서 시스템 Python 3.12에 `--system-site-packages`로 만들고, 버전은 저장소 최상위 `uv.lock`이 정합니다(`uv sync --locked`, Dockerfile에는 따로 적지 않음). MuJoCo·ONNX·Open3D는 Isaac Lab venv와 같은 버전을 쓰지만, ONNX Runtime 1.26.0은 robot venv 전용입니다. 실제 `isaac-lab:3.0.0`의 Isaac Lab venv에는 ONNX Runtime이 없으므로 추가하지 않습니다. ROS 노드와 같은 interpreter라서 sim2sim 스크립트를 나중에 실기 노드로 그대로 옮길 수 있고, Isaac Lab의 관측 코드를 실수로 import하지 않습니다.

### 5. 호스트 요구사항

- NVIDIA driver **580.65.06 이상**, 권장 595.x. 설치 후 `apt-mark hold`로 자동 업데이트를 막습니다. 컨테이너는 호스트 드라이버를 그대로 쓰므로 Docker가 이 부분을 대신 지켜 주지 않습니다.
- Docker Engine 26 이상, Docker Compose 2.25 이상, NVIDIA Container Toolkit
- `hn:sim`은 RTX GPU가 필요합니다. VRAM 12 GB에서는 headless 학습까지, 캠퍼스 지형 + RTX LiDAR 데모 장면은 16 GB 이상에서 확인합니다.
- `hn:sim`을 쓰는 PC는 Docker 이미지·빌드 레이어·shader cache를 위해 **여유 디스크 약 100 GB 이상**이 필요합니다. 2026-10-22에 확인한 Isaac Lab 3.0.0 amd64 베이스는 압축 다운로드 16.7 GB(15.6 GiB), Docker 로컬 저장 51.4 GB이고, 우리 레이어를 얹은 `hn:sim`은 59.3 GB입니다. 빌드하는 동안에는 일시적으로 더 필요합니다. Docker 29.9(containerd image store)에서 베이스를 이미 받은 PC가 최대 60 GB를 더 썼고(빌드가 베이스를 한 번 더 풂), 처음부터라면 약 130 GB가 필요합니다(추정). 빌드 뒤 `docker builder prune -f`로 회수합니다.

### 6. 실행 규약

- 네트워크는 `--net=host --ipc=host`. 컨테이너가 호스트 네트워크를 그대로 씁니다.
- **결정: Fast DDS는 `docker/fastdds.xml`로 UDP만 쓰고 shared memory(SHM) 전송은 끕니다.** 근거는 2026-10-22 실험([docker/README](../../docker/README.md#sim과-ros-사이-ros-통신))입니다. 기본값(SHM+UDP)은 두 쪽의 IPC namespace나 사용자(UID)가 다르면(IPC 분리, root, 다른 UID) "토픽 이름은 보이는데 데이터는 0개"가 되고 오류도 나지 않았습니다. UDP만 쓰면 모든 조합에서 통했고, 같은 PC에서 8 MB × 20 Hz, 16 MB × 20 Hz(최대 320 MB/s)까지 유실이 없었습니다. `--ipc=host`는 ROS 통신이 아니라 호스트 `/dev/shm`을 쓰려고(PyTorch, Isaac Sim) 유지합니다.
  - 후속: Jetson에서 큰 점구름이나 이미지의 처리량이 나쁘면, 같은 호스트의 프로세스끼리는 SHM을 다시 켜는 것을 검토합니다(그때 IPC·UID 조건을 함께 정리).
- mount: 저장소 → `/workspace/hypernova`, 데이터 → `/data`. 어떤 경로에 clone했든 컨테이너 안 경로는 모두 같습니다. Isaac Lab 학습 결과(`logs/`)는 `/data/isaaclab/logs`에 남깁니다.
- colcon build 결과와 Isaac shader cache는 named volume에 둡니다. 컨테이너를 다시 만들어도 남습니다.
- 컨테이너는 호스트 사용자 UID로 실행해서 mount한 파일의 소유자가 root가 되지 않게 합니다. UID가 1000이 아니어도 HOME과 캐시·colcon volume에 쓸 수 있도록 `HOME=/home/hn`과 캐시 경로 권한을 이미지에서 맞춥니다.
- `ROS_DOMAIN_ID`는 사람마다 따로 씁니다(개인 `docker/.env.local`, 처음 실행할 때 1~100 중 무작위로 배정). 통합 시험 때만 공용 ID를 씁니다.
- 진입점은 `./docker/hn`(`build`, `pull`, `sim`, `ros`, `stop`, `reset`, `status`) 하나입니다.
- 패키지가 더 필요하면 컨테이너 안에서 설치하지 않고 Dockerfile을 고치는 PR을 냅니다. 이미지 태그가 바뀌면 `docker/.env`의 태그를 올립니다.
- git은 호스트에서 씁니다. 컨테이너 안에서는 실행과 빌드만 합니다.

### 7. 네이티브 설치

ROS만 쓰는 작업(LIO, 지형, 대시보드, SW 노드)은 네이티브 설치도 허용합니다. 단, 같은 Ubuntu·ROS 버전과 같은 Python lock, 같은 ROS snapshot 날짜를 씁니다. Python lock은 저장소 최상위 `pyproject.toml`·`uv.lock`이고, 호스트에서는 `tools/setup-venv.sh`로 robot venv를 만듭니다([공용 Python 환경](../development/python-env.md)). Isaac Sim·Isaac Lab 작업과 공용 GPU 머신, 데모는 컨테이너만 씁니다.

### 8. 저장소 구조

최상위에 `docker/`를 추가합니다. ADR-0001의 기능·산출물 경계 목록을 이 디렉터리만큼 확장합니다. `docker/`는 AICV와 SW가 같이 쓰므로 `CODEOWNERS`에서 두 팀 공동 소유로 둡니다.

## 결과

- 새 팀원은 저장소 clone, 이미지 받기, `./docker/hn` 실행만으로 시작할 수 있습니다.
- 모든 SW·AICV 작업이 같은 ROS 배포판과 같은 의존성 버전을 기준으로 합니다.
- Jetson도 같은 Ubuntu·ROS라서 `hn:ros`를 arm64로 그대로 올릴 수 있습니다.
- 대신 처음 받을 때 용량이 큽니다. 2026-10-22 기준 `hn:sim` 베이스는 압축 레이어 16.7 GB(15.6 GiB)를 내려받고 Docker 로컬에는 51.4 GB를 차지하며, 완성된 `hn:sim`은 59.3 GB입니다. `hn:ros`는 Docker 로컬 8.9 GB(압축 다운로드 약 2.1 GB)입니다. 우리 레이어와 shader cache까지 고려해 여유 디스크 100 GB 이상을 잡고, `sim`을 빌드하는 동안에는 더 필요합니다(위 §5). 빌드 시간은 `hn:ros` 약 6분, `hn:sim` 10~17분(네트워크에 따라)이고, Isaac Sim 첫 실행은 shader 컴파일로 느립니다.
- Isaac Sim GUI는 X11 전달이나 livestream이 필요해서 네이티브보다 설정이 한 단계 더 있습니다.
- Isaac Lab 3.0.0은 막 나온 버전이라 초기 버그가 있을 수 있습니다. S0 smoke test에서 먼저 확인합니다.
- 두 이미지는 실제 레이어를 공유하지 않습니다. 같은 스크립트로 내용을 맞추는 방식이라, 스크립트를 고칠 때 두 target을 모두 빌드해 확인해야 합니다.
- `hn:ros`의 arm64(Jetson) 이미지에는 **Open3D를 일부러 넣지 않습니다.** Jetson에서는 필요 없고, `open3d==0.19.0`은 PyPI에 Linux aarch64 wheel도 없습니다. lock과 버전 고정은 그대로 두고 `install_robot_venv.sh`가 aarch64에서만 건너뜁니다.
- arm64 빌드는 로컬에서 확인하지 못했고(QEMU 설정이 호스트 변경) 첫 CI 실행에서 확인합니다.

## 다시 볼 조건

- Isaac Lab 3.0.x 패치나 Isaac Sim 7 안정판이 나왔을 때
- Seraph 드라이버가 580 이상으로 올라가 클러스터 학습이 가능해졌을 때. Singularity `.sif` 변환과 Slurm 제출 절차를 추가합니다.
- Jetson 배포 단계에 들어가 GPU 가속(TensorRT 등)이 필요해졌을 때
- 이미지 크기나 빌드 시간 때문에 온보딩이 눈에 띄게 늦어질 때
- Jetson에서 Open3D가 필요해졌을 때(0.20.0부터 aarch64 wheel이 있어 버전을 올리는 방법을 먼저 검토)
- Isaac Lab 3.1이 나와 `isaaclab.sh`가 없어질 때(`uv run isaaclab`으로 문서와 빠른 시작을 고칩니다)
- NVIDIA 이미지 라이선스나 GHCR 과금 정책이 바뀌었을 때
