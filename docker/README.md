# Docker 개발 환경

HyperNova의 공통 개발 환경입니다. Ubuntu 24.04 + ROS 2 Jazzy를 기준으로, Dockerfile 하나에서 이미지 두 개를 만듭니다.

- 왜 이렇게 정했는지, 버전 표: [ADR-0002: 공통 개발 환경](../docs/decisions/0002-dev-environment.md)
- 진행 상황과 업무: [Notion — 개발 환경 구축](https://app.notion.com/p/3fe45bd8717881099a1dfe62c07a9fca)
- 호스트를 준비하고 이미지를 받은 뒤 따라 하는 빠른 시작: [보행 (`hn:sim`)](../docs/development/quickstart-locomotion.md), [인지·SW (`hn:ros`)](../docs/development/quickstart-perception.md)

## 어떤 이미지를 쓰나

| | 보행팀 — `hn:sim` | 인지팀·SW팀 — `hn:ros` |
| --- | --- | --- |
| 베이스 | NVIDIA 공식 Isaac Lab 이미지 (`nvcr.io/nvidia/isaac-lab:3.0.0`) | `ros:jazzy-ros-base` |
| 받는 방법 | 각자 PC에서 최초 한 번 빌드 | GitHub(GHCR)에서 완성 이미지 다운로드. CI가 `main` 병합 때 올리므로, 올라오기 전에는 `./docker/hn build ros` |
| 크기 | 베이스는 압축 다운로드 16.7 GB (15.6 GiB), Docker 로컬 51.4 GB. 우리 레이어까지 59.3 GB (+7.9 GB) | Docker 로컬 8.9 GB (압축 다운로드 약 2.1 GB) |
| 빌드 시간 | 10~17분 (9분 37초, 17분 14초를 쟀고 Ubuntu 미러 속도에 좌우됨) | 약 6분 (6분 20초) |
| 필요 장비 | RTX GPU, VRAM 12 GB 이상 | GPU 불필요, PC(amd64)·Jetson(arm64) |

크기와 시간은 2026-10-22에 20코어 PC(Ubuntu 24.04, Docker 29.9)에서 잰 값입니다. 빌드 시간은 apt 다운로드가 대부분이라 네트워크에 따라 달라지고, `hn:ros`는 압축 크기를 `docker save | gzip`으로 쟀습니다. 두 이미지는 같은 `docker/scripts`의 설치 스크립트로 ROS 레이어를 만들어서, 한쪽에서 만든 bag과 노드가 다른 쪽에서 그대로 돕니다.

### 보행팀 — `hn:sim`

빌드 명령이 Dockerfile 첫 줄(`FROM nvcr.io/nvidia/isaac-lab:3.0.0`)을 보고 **NVIDIA 공식 Isaac Lab 이미지를 자동으로 받아 온 뒤**, 그 위에 우리 레이어만 얹습니다. 따로 받을 필요도, NVIDIA 로그인도 없습니다. 2026-10-22 amd64 측정값은 압축 다운로드 16.7 GB(15.6 GiB), Docker 로컬 저장 51.4 GB이며, 우리 레이어와 shader cache까지 고려해 **여유 디스크 100 GB 이상**을 권장합니다.

- Isaac Sim 6.2.0 + Isaac Lab 3.0.0 (학습은 PhysX), RSL-RL 5.5.1, torch 2.11.0+cu130, warp 1.17.0 — 이미지에서 확인한 값입니다
- ROS 2 Jazzy + 공용 ROS 패키지 (rviz2, rqt, rosbag2/MCAP, rosbridge, foxglove bridge, joy/teleop). Isaac Sim의 ROS 2 bridge는 이 시스템 ROS를 그대로 씁니다
- sim2sim·배포용 venv(`/opt/hn-venv`): MuJoCo 3.12.0, onnxruntime 1.26.0, Open3D 0.19.0
- LIO 패키지는 `hn:ros`에만 있습니다. 시뮬 센서 bag은 파일로 남겨서 `hn:ros`에서 확인합니다.

데모 장면(캠퍼스 지형 + RTX LiDAR)은 VRAM 16 GB 이상에서 확인합니다. 12 GB는 headless 학습까지 충분합니다(RTX 4070 SUPER 12 GB에서 4096 환경 학습이 VRAM 약 5.6 GB).

### 인지팀·SW팀 — `hn:ros`

- ROS 2 Jazzy + 보행팀과 **같은** 공용 ROS 패키지. 같은 설치 스크립트를 쓰기 때문에 bag과 노드가 서로 호환됩니다.
- LIO: RKO-LIO (`ros-jazzy-rko-lio`), FAST-LIO2 (`ROS2` 브랜치, commit 고정) + `livox_ros_driver2` 메시지
- 지형·sim2sim venv(`/opt/hn-venv`): Open3D 0.19.0, MuJoCo 3.12.0, onnxruntime 1.26.0

## 호스트 준비

Ubuntu 24.04 기준이고 PC마다 한 번만 하면 됩니다.

| 단계 | 보행팀 (`sim`) | 인지팀·SW팀 (`ros`) |
| --- | --- | --- |
| [1. NVIDIA 드라이버](#1-nvidia-드라이버) | 필수 | 필요 없음 |
| [2. Docker Engine](#2-docker-engine) | 필수 | 필수 |
| [3. sudo 없이 docker 쓰기](#3-sudo-없이-docker-쓰기) | 필수 | 필수 |
| [4. NVIDIA Container Toolkit](#4-nvidia-container-toolkit) | 필수 | 필요 없음 |
| [5. 여유 디스크](#5-여유-디스크) | 약 100 GB 이상 | 작업량에 따라 다름 |

### 1. NVIDIA 드라이버

컨테이너는 호스트 드라이버를 그대로 씁니다. Isaac Sim 6.2와 torch cu130은 **580.65.06 이상**이 필요합니다.

```bash
nvidia-smi        # 오른쪽 위 Driver Version 확인
```

없거나 580보다 낮으면 설치합니다.

```bash
sudo ubuntu-drivers list                 # 설치 가능한 버전 확인
sudo apt install nvidia-driver-580-open  # 580 이상이면 됨
sudo reboot
```

- RTX 50 시리즈(5070, 5070 Ti)는 `-open` 드라이버만 지원합니다. RTX 40 시리즈는 둘 다 됩니다.
- 버전 번호는 `ubuntu-drivers list`에 나온 580 이상 중 하나를 고릅니다.

설치가 끝나면 **자동 업데이트를 막습니다.** Ubuntu 자동 업데이트가 드라이버를 바꾸면 Docker와 상관없이 Isaac Sim이 깨집니다.

```bash
dpkg-query -W -f='${binary:Package}\n' | grep -E '^(nvidia-|libnvidia-)' | xargs sudo apt-mark hold
apt-mark showhold   # 고정된 패키지 확인
```

드라이버를 일부러 올릴 때만 `apt-mark unhold`로 풀었다가 다시 고정합니다.

### 2. Docker Engine

**Docker Desktop이 아니라 Docker Engine을 설치합니다.** Linux용 Docker Desktop은 VM 안에서 돌아서 GPU를 쓸 수 없습니다.

Ubuntu 기본 저장소의 `docker.io` 같은 패키지가 있으면 먼저 지웁니다.

```bash
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y $pkg
done
```

Docker 공식 apt 저장소를 추가하고 설치합니다.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

확인:

```bash
sudo docker run --rm hello-world
docker --version          # 26 이상
docker compose version    # 2.25 이상
```

### 3. sudo 없이 docker 쓰기

현재 사용자를 `docker` 그룹에 넣습니다.

```bash
sudo groupadd -f docker
sudo usermod -aG docker $USER
```

**로그아웃 후 다시 로그인**해야 적용됩니다(재부팅도 됨). VS Code도 완전히 껐다 켭니다. 확인:

```bash
groups                    # 목록에 docker가 있어야 함
docker run --rm hello-world   # sudo 없이
```

> [!WARNING]
> `docker` 그룹은 사실상 root 권한입니다. 개인 PC에서만 이렇게 하고, 여러 사람이 쓰는 서버에서는 관리자와 먼저 이야기합니다.

### 4. NVIDIA Container Toolkit

컨테이너가 GPU를 쓸 수 있게 해 줍니다.

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

확인 — sudo 없이 GPU 이름이 나오면 호스트 준비 끝입니다.

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

### 5. 여유 디스크

`hn:sim`의 Isaac Lab 베이스는 로컬 Docker 저장소에서 약 51.4 GB를 차지합니다. ROS 레이어, 빌드 cache, Isaac Sim shader cache까지 남기므로 보행팀 PC에는 **여유 디스크 100 GB 이상**을 확보합니다. 처음 받는 압축 레이어 합계는 약 16.7 GB(15.6 GiB)지만, Docker가 푼 뒤의 크기와 같지 않습니다.

**빌드하는 동안에는 더 필요합니다.** 2026-10-22에 Docker 29.9(containerd image store)에서, 베이스를 이미 받은 PC의 `./docker/hn build sim`이 최대 **약 60 GB를 더 썼습니다**. 빌드가 베이스(51 GB)를 빌드용으로 한 번 더 풀기 때문입니다. 완성된 이미지는 59.3 GB(베이스 51.4 + 우리 7.9)입니다. 처음부터라면 압축 다운로드 16.7 GB + 풀린 베이스 51.4 GB + 빌드용 사본 약 51 GB + 우리 레이어 약 8 GB라서 최대 약 130 GB가 필요하다고 봐야 합니다(합산한 추정값). 그러니 **첫 `build sim` 전에 여유 디스크가 130 GB 이상**인지 확인하고, 빌드가 끝나면 `docker builder prune -f`로 빌드 cache를 지웁니다. 그 뒤에 계속 차지하는 것은 이미지 59 GB와 volume(shader cache 등)입니다. 예전 방식의 Docker(overlay2 graph driver)는 빌드가 베이스를 다시 풀지 않아 덜 쓸 수 있습니다.

## 처음 시작할 때

보행팀:

```bash
git clone https://github.com/HyperNova26/hypernova-robot.git
cd hypernova-robot
./docker/hn build sim   # 최초 한 번: Isaac Lab 이미지 자동 다운로드 + 우리 레이어 빌드
./docker/hn sim         # 컨테이너 생성 + 셸 진입
```

인지팀·SW팀:

```bash
git clone https://github.com/HyperNova26/hypernova-robot.git
cd hypernova-robot
./docker/hn pull ros    # 최초 한 번: 완성 이미지 다운로드 (아직 안 올라왔으면 ./docker/hn build ros)
./docker/hn ros         # 컨테이너 생성 + 셸 진입
```

- 첫 실행 때 `docker/.env.local`이 자동으로 만들어지고 개인 `ROS_DOMAIN_ID`(1~100 중 무작위)가 배정됩니다. 무엇을 했는지 화면에 나옵니다. 이 파일은 커밋하지 않습니다.
- `hn`이 `~/hypernova-data`와 저장소의 `build/ install/ log/` 폴더도 내 계정으로 미리 만듭니다. Docker가 만들면 root 소유가 돼서 컨테이너가 쓸 수 없습니다. `docker compose`를 직접 치지 말고 항상 `hn`으로 실행하세요.
- Isaac Sim 첫 실행은 shader·커널 컴파일 때문에 느립니다. 캐시가 volume에 남아서 다음부터는 빨라집니다(이 PC에서 학습 첫 실행은 5 iteration에 80초, 캐시가 쌓인 뒤에는 20 iteration이 44초).
- 로봇 USD 같은 Isaac 에셋은 처음에 NVIDIA 서버에서 받아 옵니다. 오프라인이면 실패합니다.

## 명령 한눈에 보기

| 명령 | 하는 일 |
| --- | --- |
| `./docker/hn build sim` / `ros` | 이미지 빌드 |
| `./docker/hn pull ros` | 완성된 ros 이미지를 GHCR에서 받기 (`sim`은 배포하지 않음) |
| `./docker/hn sim` / `ros` | 컨테이너가 꺼져 있으면 켜고 셸을 엽니다. 켜져 있으면 셸만 하나 더 엽니다 |
| `./docker/hn sim <명령>` / `ros <명령>` | 셸 대신 그 명령을 컨테이너 환경에서 실행. 예: `./docker/hn ros ros2 topic list` |
| `./docker/hn train` / `play` `[인자…]` | (보행팀) Isaac Lab 학습·재생. `physics=isaacsim_physx`, `--rl_library rsl_rl`을 자동으로 붙임. 컨테이너 안에서는 `hn-rl train\|play` |
| `./docker/hn stop [sim\|ros]` | 컨테이너 멈추기 |
| `./docker/hn reset [sim\|ros]` | 컨테이너 지우기. 꼬였을 때, `docker/.env.local`을 고친 뒤에 씁니다. volume(빌드 결과·캐시)은 남습니다 |
| `./docker/hn status` | 설정, GPU, 이미지, 컨테이너 상태 |

- 저장소 안 어디서 실행해도 됩니다.
- 이미지를 새로 빌드한 뒤에 `sim`/`ros`를 치면 컨테이너를 알아서 다시 만듭니다(그때 열려 있던 셸은 종료). 이미지가 같으면 실행 중인 컨테이너를 건드리지 않습니다.
- 셸에 `export`해 둔 `ROS_DOMAIN_ID` 같은 변수는 무시하고 `docker/.env`, `docker/.env.local` 값을 씁니다.
- 다른 폴더에 clone한 저장소가 쓰는 컨테이너가 떠 있으면 거부합니다(엉뚱한 저장소를 편집하는 사고 방지). `reset` 후 다시 실행하세요.
- 실행 전에 Docker 접근 권한, NVIDIA 런타임, 드라이버(580.65.06 이상)를 확인하고, 안 맞으면 해결 방법을 알려 줍니다.

## 매일, 그리고 터미널을 새로 열 때마다

```bash
cd hypernova-robot
./docker/hn sim         # 보행팀
./docker/hn ros         # 인지팀·SW팀
```

- 컨테이너가 꺼져 있으면 켜고, 켜져 있으면 셸만 하나 더 엽니다. 터미널을 여러 개 쓰려면 같은 명령을 다시 치면 됩니다.
- 다시 빌드하지 않습니다.
- 프롬프트 앞에 `(hn:sim)` 또는 `(hn:ros)`가 붙으면 컨테이너 안입니다.

## 컨테이너 안에서 알아 둘 것

| 경로 | 내용 |
| --- | --- |
| `/workspace/hypernova` | 이 저장소(호스트와 같은 파일). 호스트에서 저장하면 바로 반영 |
| `/data` | 호스트 `~/hypernova-data`. rosbag, 학습 결과, 지형 데이터 (`docker/.env.local`의 `HN_DATA_DIR`) |
| `/workspace/hypernova/data/PAIR360_data`, `/workspace/hypernova/data/PAIR360_demo` | (2026-10-30 기준) PAIR360 원본과 기존 변환 결과. 코드 mount에 포함되며 Git 추적에서 제외합니다 |
| `/workspace/hypernova/sim_scenes/MMDD_demo_whole` | 전체 점군 변환기의 USD, MuJoCo XML, metadata. 기본 출력 경로이며 Git 추적에서 제외합니다 |
| `/workspace/hypernova/sim_scenes/MMDD_demo_disassembled` | 미구현 분해 스크립트가 준비하는 빈 폴더. 파일이나 하위 폴더를 만들지 않으며 Git 추적에서 제외합니다 |
| `/workspace/isaaclab` | (sim) Isaac Lab. 안의 `logs/`는 `/data/isaaclab/logs`에 연결돼서 학습 결과가 호스트에 남습니다 |
| `/opt/hn-venv` | robot venv. MuJoCo, onnxruntime, Open3D 등. 저장소 `uv.lock` 그대로 |
| `/opt/isaaclab-venv` | (sim) Isaac Lab venv. 건드리지 않습니다 |
| `/opt/ros/jazzy`, `/opt/hn_ws` | 시스템 ROS와 LIO underlay(`ros`에만 내용이 있음) |
| `/opt/hn` | 이미지에 구워 둔 스크립트(`scripts/selftest.sh` 등)와 설정 |

PAIR360 폴더 이동으로 `/data` mount나 `HN_DATA_DIR` 기본값이 바뀌지는 않습니다. 저장소 최상위 `data/PAIR360_data/`, `data/PAIR360_demo/`는 위의 `/workspace/hypernova/data/` 경로로 읽습니다. 현재 [시뮬레이터 장면 변환 안내](../sim_scenes/README.md)의 전체 점군 변환기는 기본적으로 `sim_scenes/MMDD_demo_whole/`에 결과를 만들고 기존 출력 경로는 거부합니다. 다른 위치는 `--output-root`로 지정합니다. Python은 명시한 `HN_MAP_PYTHON`을 우선하고, 그 외에는 컨테이너의 `/opt/hn-venv/bin/python`을 사용합니다. CloudCompare native BIN 변환은 선택적인 CloudCompare 실행 파일이 필요하며, 컨테이너에 설치되어 있다고 가정하지 않습니다.

`tools/map/`의 `.sh`는 같은 이름의 `.py` 구현을 호출하는 실행기입니다. `demo_sim_converter`는 유한한 XYZ 전체를 기본 0.5 m voxel 점유로 변환하여 정적 USD 삼각형 Mesh와 MuJoCo box geom을 내보내며, 지면 추출이나 heightfield 생성, simulator 실행은 수행하지 않습니다. `demo_sim_disassembler`는 입력 파일 확인 후 빈 폴더만 만듭니다. 지면 분리와 후속 차량·기타 객체 분류·분리는 미완료이며, 구현·개선과 실제 PAIR360 데이터 검증은 S-004 후속 작업에서 다룹니다.

- 컨테이너는 **호스트 UID/GID**로 실행됩니다. 그래서 `/workspace/hypernova`와 `/data`에 만든 파일의 주인이 내 계정입니다(root가 아님). 사용자 이름은 `ubuntu`로 보이거나 없을 수 있습니다.
- Python이 둘입니다. ROS 노드와 같은 interpreter인 robot venv는 `/opt/hn-venv/bin/python`으로 부르고, **`activate`하지 않습니다**. `sim`에서 활성화하면 `isaaclab.sh`가 거부합니다. Isaac Lab은 `./isaaclab.sh -p ...`로 씁니다(`deprecated` 경고는 3.1에서 없어진다는 안내일 뿐 정상 동작).
- 환경이 의심스러우면 `/opt/hn/scripts/selftest.sh`를 돌립니다. ROS 패키지, venv 버전이 이미지에 들어간 `uv.lock`과 같은지, rclpy가 venv에서 import되는지 확인하고 하나라도 틀리면 `FAIL` 줄을 보여 줍니다. `sim`은 `--isaac`을 붙이면 Isaac Lab import까지 봅니다.

무엇이 남고 무엇이 사라지나:

| 남음 | 사라짐 (컨테이너를 `reset`하면) |
| --- | --- |
| 저장소, `/data`(호스트 폴더) | 컨테이너 안에서 `apt`/`pip`로 설치한 것 |
| colcon 빌드 결과, Isaac shader·Kit 캐시 (named volume) | `~/.ros/log`, `/tmp`(Isaac 에셋 다운로드 캐시 포함. 다시 받음) |

## ROS 패키지 빌드 (colcon)

저장소 최상위에서 `ros_pkgs`만 지정해서 빌드합니다(`.venv` 같은 폴더를 훑지 않게).

```bash
colcon build --base-paths ros_pkgs
```

- 결과(`build/ install/ log/`)는 호스트 저장소가 아니라 named volume에 쌓입니다. 호스트의 같은 이름 폴더는 비어 있고(`.gitignore`), 컨테이너를 지워도 결과는 남습니다.
- `hn`으로 연 모든 셸이 `install/`을 자동으로 source합니다.
- `sim`과 `ros`가 **같은 volume을 씁니다.** 한쪽에서 빌드한 결과를 다른 쪽에서 쓸 수 있습니다. 두 컨테이너에서 동시에 빌드하지 마세요.
  - 순수 Python 패키지와 메시지 패키지는 양쪽에서 그대로 돕니다.
  - LIO underlay(`/opt/hn_ws`의 `fast_lio`, `livox_ros_driver2`)는 `ros`에만 내용이 있습니다. 여기에 link하거나 의존하는 패키지는 `ros`에서 빌드하면 `sim`의 `install/`에도 **보이지만**, `sim`에서 실행하면 라이브러리나 패키지를 찾지 못해 실패합니다. 이런 패키지는 `ros`에서만 빌드하고 실행하세요.

## `sim`과 `ros` 사이 ROS 통신

두 컨테이너는 호스트 네트워크를 쓰고, 같은 `docker/.env.local`의 `ROS_DOMAIN_ID`를 받으므로 따로 설정할 것이 없습니다. Fast DDS는 `docker/fastdds.xml`로 **UDP만** 쓰게 해 두었습니다.

확인하는 방법(두 이미지가 있는 PC): 터미널 하나에서 Isaac Sim이 `/clock`을 내보내고, 다른 터미널의 `ros`에서 받습니다. 자세한 단계는 [인지·SW 빠른 시작](../docs/development/quickstart-perception.md#5-다른-컨테이너의-토픽-받기)에 있습니다.

shared memory를 끈 이유는 실험 결과입니다(2026-10-22, `hn:sim`이 2 MB 메시지를 초당 10번 발행):

| 받는 쪽 | 기본값(SHM+UDP) | UDP만 (현재 설정) |
| --- | --- | --- |
| `hn ros` (host IPC, 같은 UID) | 받음 | 받음 |
| 일회용 컨테이너, IPC 분리 | **0개** (토픽 이름은 보임) | 받음 |
| 일회용 컨테이너, host IPC, root | **0개** | 받음 |
| 일회용 컨테이너, host IPC, 다른 UID | **0개** | 받음 |

- 기본값은 두 쪽의 IPC namespace나 사용자가 다르면 "토픽 이름은 보이는데 데이터가 안 오는" 상태가 되고 오류도 안 납니다. 컨테이너를 `docker run`으로 직접 띄우거나 root로 띄우면 바로 겪습니다.
- UDP만 쓰면 모두 통하고, 기본값을 쓰는 상대(호스트에 네이티브로 설치한 ROS)와도 통합니다.
- 속도 손해는 없었습니다. 같은 PC에서 8 MB × 20 Hz, 16 MB × 20 Hz(최대 320 MB/s)까지 유실 없이 받았습니다.
- `--ipc=host`는 ROS 통신 때문이 아니라 호스트 `/dev/shm`을 그대로 쓰려고(PyTorch, Isaac Sim) 유지합니다.

## 버전을 올리거나 패키지를 추가할 때 (Dockerfile PR)

컨테이너 안에서 설치하지 않고, 아래 순서로 PR을 냅니다. `docker/`는 AICV·SW 공동 소유라서 두 팀 중 한 명의 승인이 필요합니다.

1. `docker/scripts/`, `docker/ros/hypernova.repos`, `docker/.env`(버전), 저장소 최상위 `pyproject.toml`/`uv.lock` 중 필요한 것을 고칩니다. 두 target이 같은 스크립트를 쓰므로 **`./docker/hn build ros`와 `./docker/hn build sim`을 둘 다** 돌려서 확인합니다.
2. `docker/.env`의 `HN_IMAGE_TAG`를 올립니다. 태그가 바뀌어야 팀원이 `git pull` 뒤에 새 이미지를 받아야 한다는 것을 알 수 있습니다.
3. PR을 내면 CI(`.github/workflows/docker-ros.yml`)가 `ros`를 amd64·arm64로 빌드하고 `selftest.sh`를 돌립니다. `main`에 병합되면 `ghcr.io/hypernova26/hn:ros-<태그>`로 올립니다. `sim`은 CI에서 빌드하지 않습니다.
4. 병합 뒤 팀원은 `git pull` → 보행팀 `./docker/hn build sim`, 인지팀·SW팀 `./docker/hn pull ros`.

고정값을 갱신하는 방법:

| 무엇 | 어떻게 |
| --- | --- |
| 베이스 이미지 다이제스트 | `docker buildx imagetools inspect <이미지:태그>`의 맨 위 `Digest`를 `docker/.env`의 `ROS_BASE_IMAGE`/`ISAACLAB_BASE_IMAGE`에 |
| ROS snapshot 날짜 | `docker/.env`의 `ROS_SNAPSHOT_DATE`. `http://snapshots.ros.org/jazzy/<날짜>/ubuntu`가 있는 날짜만 됩니다. snapshot 서명 키(`docker/ros/ros-snapshots.asc`)는 2027-06-01에 만료됩니다 |
| uv | `UV_VERSION`과 두 아키텍처의 sha256(`docker/.env`). 릴리스의 `.sha256` 파일 값 |
| LIO 소스 의존성 | `docker/ros/hypernova.repos`의 commit SHA |

> [!NOTE]
> GHCR에 처음 올라간 패키지는 **private**으로 만들어집니다. 저장소 관리자가 한 번 패키지 설정(Package settings → Change visibility)에서 Public으로 바꿔야 팀원이 로그인 없이 `pull`할 수 있습니다.

## arm64 이미지 (Jetson)

`ros`는 arm64로도 빌드하지만(CI, QEMU 에뮬레이션) 이 PC에서는 arm64 빌드를 확인하지 못했습니다. QEMU 설정이 호스트 변경이라 하지 않았습니다. 대신 ROS snapshot(`snapshots.ros.org`)에 필요한 ROS 패키지가 arm64로 있는지, `uv.lock`의 wheel이 aarch64용으로 있는지만 확인했습니다(Open3D만 없음). 첫 CI 실행 결과로 확인해야 합니다.

- **Open3D는 arm64 이미지에 일부러 넣지 않습니다.** Jetson에서는 필요 없고 `open3d==0.19.0`은 Linux aarch64 wheel도 없습니다. lock과 고정 버전은 그대로 두고 `install_robot_venv.sh`가 aarch64에서만 건너뜁니다(ADR-0002 §4).
- arm64 빌드는 QEMU라서 느립니다. 너무 오래 걸리면 GitHub의 arm64 runner로 나눠 빌드하는 방법을 검토합니다.

## 작업 규칙

- 코드는 컨테이너 안 `/workspace/hypernova`에 연결돼 있습니다. 호스트(VS Code)에서 저장하면 컨테이너에 바로 반영됩니다. rosbag·학습 결과는 `/data`(호스트 기본 `~/hypernova-data`)에 둡니다. 저장소 안으로 옮긴 PAIR360 원본·변환 결과는 `/workspace/hypernova/data/PAIR360_data/`와 `/workspace/hypernova/data/PAIR360_demo/`를 사용합니다.
- git은 호스트에서 씁니다. 컨테이너 안에서는 실행과 빌드만 합니다.
- 코드나 설정에 개인 절대경로(`/home/이름/...`)를 넣지 않습니다. 저장소 상대경로나 `/data/...`를 씁니다.
- 패키지가 더 필요하면 컨테이너 안에서 `apt`나 `pip`로 설치하지 말고 Dockerfile을 고치는 PR을 냅니다. 컨테이너를 다시 만들면 안에서 설치한 것은 사라집니다.
- 컨테이너 없이 호스트에서 Python 도구(맵·지형 처리 등)를 돌릴 때는 [공용 Python 환경](../docs/development/python-env.md)(`./tools/setup-venv.sh`)을 씁니다. 이미지의 robot venv와 같은 `uv.lock`을 씁니다.
- 이미지 버전이 바뀌면(`git pull` 후 `docker/.env`의 태그가 바뀜) 보행팀은 `./docker/hn build sim`, 인지팀·SW팀은 `./docker/hn pull ros`를 다시 실행합니다.
- 끝낼 때는 `./docker/hn stop`(안 해도 됨). 컨테이너가 꼬였으면 `./docker/hn reset`. 빌드 결과와 캐시는 남습니다.
- 디스크: `sim`을 빌드하면 BuildKit cache가 수십 GB 남습니다. 빌드가 끝난 뒤 `docker builder prune -f`로 지우면 회수됩니다(이미지와 volume은 그대로). 측정값은 [5. 여유 디스크](#5-여유-디스크)에 있습니다.

## 알아 둘 제약과 겪은 문제

| 무엇 | 내용 |
| --- | --- |
| Isaac Lab 3.0.0 기본 physics | 내장 과제의 기본이 `newton_mjwarp`입니다. 그래서 학습·재생은 `physics=isaacsim_physx`를 자동으로 붙이는 `hn-rl train\|play`(호스트에서는 `./docker/hn train\|play`)로 실행합니다. `./isaaclab.sh -p .../train.py`를 직접 치면 이 보호가 없습니다 ([보행 빠른 시작](../docs/development/quickstart-locomotion.md)) |
| 학습 스크립트 경로 | `scripts/reinforcement_learning/train.py --rl_library rsl_rl`. `rsl_rl/` 하위 폴더와 `--headless` 옵션은 없습니다 |
| ONNX 내보내기 | `policy.onnx`와 `policy.onnx.data`(가중치)가 쌍입니다. 같이 옮기세요 |
| 베이스 이미지의 환경변수 | 베이스는 `VIRTUAL_ENV`, `UV_PROJECT_ENVIRONMENT`, `UV_PYTHON`을 Isaac Lab venv로 설정해 둡니다. robot venv 설치 스크립트가 이를 지우고 자기 uv(`/opt/hn/bin/uv`)로 만들며, 그러지 않으면 Isaac Lab venv의 numpy가 1.26.4로 덮어써집니다 |
| 베이스 이미지의 홈 | `/root`가 UID 1000 전용(750)이라 다른 UID로 실행하면 캐시를 못 씁니다. 그래서 `HOME=/home/hn`(모든 UID가 쓸 수 있음)과, 같은 권한으로 만든 캐시 폴더를 씁니다 |
| 베이스 이미지의 HEALTHCHECK | Isaac Sim 앱이 주 프로세스일 때만 통과하므로 `HEALTHCHECK NONE`으로 껐습니다(안 그러면 `docker ps`에 계속 `unhealthy`) |
| FAST-LIO | CMake가 `-std=c++14`를 박아 두는데 Jazzy는 C++17이 필요해서 빌드 때 `sed`로 고칩니다(`install_lio.sh`). 지도 저장(`pcd_save_en`)과 `Log`는 소스 폴더(`ROOT_DIR`)에 쓰는 구조라 이미지에서는 동작하지 않습니다 |
| `livox_ros_driver2` | FAST-LIO가 컴파일에 쓰는 메시지(`CustomMsg`)만 빌드합니다. 드라이버 본체는 Livox-SDK2가 따로 필요하고 저장소에 `package.xml`도 없어서(공식 절차는 `build.sh`가 파일을 바꿔치기) 가장 덜 깨지는 쪽을 택했습니다. 실제 Livox 센서를 붙일 때 전체 드라이버 빌드로 바꿉니다 |
| `ros2 doctor` 경고 | `foxglove_bridge`가 최신(3.6.3)보다 낮다는 경고는 snapshot 날짜 고정의 결과라 정상입니다. 소스로 빌드한 `fast_lio`, `livox_ros_driver2`는 최신 버전을 못 찾는다고 나옵니다 |
| 공개 샘플 bag | 작은 LiDAR+IMU ROS 2 bag을 찾지 못했습니다(NVIDIA r2b는 1.2 GB 이상, IMU–LiDAR 변환 없음). 그래서 합성 bag 생성기 `tools/make_demo_bag.py`를 둡니다 |

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| `permission denied ... docker.sock` | [3단계](#3-sudo-없이-docker-쓰기) 후 다시 로그인했는지 |
| `could not select device driver "nvidia"` | [4단계](#4-nvidia-container-toolkit)의 `nvidia-ctk runtime configure`와 docker 재시작 |
| 호스트에서는 `nvidia-smi`가 되는데 컨테이너에서는 안 됨 | Docker Desktop을 쓰고 있지 않은지, 같은 PC의 터미널에서 실행했는지(WSL·원격·dev container 아님) |
| 토픽 이름은 보이는데 `ros2 topic echo`에 데이터가 안 옴 | 한쪽이 `docker/fastdds.xml`(UDP 전용 프로파일) 없이 떠 있음. `hn:sim`·`hn:ros` 이미지는 `docker run`으로 직접 띄워도 이미지 ENV로 항상 적용됩니다. 다른 이미지(예: 순정 `ros:jazzy`)와 섞어 쓸 때는 그쪽에도 `-e FASTRTPS_DEFAULT_PROFILES_FILE=...`로 같은 프로필을 줍니다. `ros2 topic echo`는 토픽이 아직 없으면 바로 끝나므로 타입을 같이 적습니다(`ros2 topic echo /clock rosgraph_msgs/msg/Clock`) |
| 남의 토픽이 보임 | `docker/.env.local`의 `ROS_DOMAIN_ID`가 다른 사람과 겹치는지. 고친 뒤 `./docker/hn reset` |
| 컨테이너가 만든 파일이 root 소유 | `docker/.env.local`의 UID·GID가 `id -u`, `id -g`와 같은지. `docker compose`를 직접 쳤다면 `hn`으로 다시 |
| 저장소에 root 소유 `build/` 폴더가 생김 | `hn`이 아닌 방법으로 컨테이너를 띄웠음. `sudo chown -R $USER:$USER build install log` |
| Isaac Sim 창이 안 뜸 | 호스트 데스크톱 세션에서 실행했는지, `echo $DISPLAY` 값이 있는지. `hn`이 `xhost`로 접근을 허용해 줍니다. X11 세션에서 확인했고 Wayland 세션은 확인하지 못했습니다 |
| rviz2 창이 느리거나 GPU 경고가 나옴 | `ros` 이미지는 GPU 없이 소프트웨어 렌더링(llvmpipe)을 씁니다. `glx: failed to create dri3 screen` 같은 메시지는 무시해도 됩니다 |
| 이미지가 없다는 오류(`hn:sim-...`) | `./docker/hn build sim`을 먼저 실행 |
| 셸마다 `not found: "/opt/hn_ws/install/local_setup.bash"` | 이전 이미지로 만든 colcon 결과가 새 이미지에 없는 underlay를 가리킴. 이미지를 다시 빌드하거나 받으세요 |
