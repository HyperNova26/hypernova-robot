# Docker 개발 환경

HyperNova의 공통 개발 환경입니다. Ubuntu 24.04 + ROS 2 Jazzy를 기준으로, Dockerfile 하나에서 이미지 두 개를 만듭니다.

- 왜 이렇게 정했는지, 버전 표: [ADR-0002: 공통 개발 환경](../docs/decisions/0002-dev-environment.md)
- 진행 상황과 업무: [Notion — 개발 환경 구축](https://app.notion.com/p/3fe45bd8717881099a1dfe62c07a9fca)

## 어떤 이미지를 쓰나

| | 보행팀 — `hn:sim` | 인지팀·SW팀 — `hn:ros` |
| --- | --- | --- |
| 베이스 | NVIDIA 공식 Isaac Lab 이미지 (`nvcr.io/nvidia/isaac-lab:3.0.0`) | `ros:jazzy` |
| 받는 방법 | 각자 PC에서 최초 한 번 빌드 | GitHub(GHCR)에서 완성 이미지 다운로드 |
| 크기 | 압축 다운로드 16.7 GB (15.6 GiB), Docker 로컬 51.4 GB | 약 3 GB |
| 필요 장비 | RTX GPU, VRAM 12 GB 이상 | GPU 불필요, PC(amd64)·Jetson(arm64) |

### 보행팀 — `hn:sim`

빌드 명령이 Dockerfile 첫 줄(`FROM nvcr.io/nvidia/isaac-lab:3.0.0`)을 보고 **NVIDIA 공식 Isaac Lab 이미지를 자동으로 받아 온 뒤**, 그 위에 우리 레이어만 얹습니다. 따로 받을 필요도, NVIDIA 로그인도 없습니다. 2026-10-22 amd64 측정값은 압축 다운로드 16.7 GB(15.6 GiB), Docker 로컬 저장 51.4 GB이며, 우리 레이어와 shader cache까지 고려해 **여유 디스크 100 GB 이상**을 권장합니다.

- Isaac Sim 6.2.0 + Isaac Lab 3.0.0 (학습은 PhysX), RSL-RL, torch 2.11 (cu130)
- ROS 2 Jazzy + 공용 ROS 패키지 (rviz2, rosbag2/MCAP, rosbridge, foxglove bridge, joy/teleop)
- sim2sim·배포용 venv: MuJoCo 3.12.0, onnxruntime 1.26.0, Open3D 0.19.0
- LIO 패키지 (시뮬 LiDAR bag 확인용)

데모 장면(캠퍼스 지형 + RTX LiDAR)은 VRAM 16 GB 이상에서 확인합니다. 12 GB는 headless 학습까지 충분합니다.

### 인지팀·SW팀 — `hn:ros`

- ROS 2 Jazzy + 보행팀과 **같은** 공용 ROS 패키지. 같은 설치 스크립트를 쓰기 때문에 bag과 노드가 서로 호환됩니다.
- LIO: RKO-LIO (`ros-jazzy-rko-lio`), FAST-LIO2 (`ROS2` 브랜치) + `livox_ros_driver2`
- 지형·sim2sim venv: Open3D 0.19.0, MuJoCo 3.12.0, onnxruntime 1.26.0

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

`hn:sim`의 Isaac Lab 베이스는 로컬 Docker 저장소에서 약 51.4 GB를 차지합니다. ROS·LIO 레이어, 빌드 cache, Isaac Sim shader cache까지 남기므로 보행팀 PC에는 **여유 디스크 100 GB 이상**을 확보합니다. 처음 받는 압축 레이어 합계는 약 16.7 GB(15.6 GiB)지만, Docker가 푼 뒤의 크기와 같지 않습니다.

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
./docker/hn pull ros    # 최초 한 번: 완성 이미지 다운로드
./docker/hn ros         # 컨테이너 생성 + 셸 진입
```

- 첫 실행 때 `docker/.env.local`이 자동으로 만들어지고 개인 `ROS_DOMAIN_ID`가 배정됩니다. 이 파일은 커밋하지 않습니다.
- Isaac Sim 첫 실행은 shader 컴파일 때문에 느립니다. 캐시가 남아서 다음부터는 빠릅니다.

## 매일, 그리고 터미널을 새로 열 때마다

```bash
cd hypernova-robot
./docker/hn sim         # 보행팀
./docker/hn ros         # 인지팀·SW팀
```

- 컨테이너가 꺼져 있으면 켜고, 켜져 있으면 셸만 하나 더 엽니다. 터미널을 여러 개 쓰려면 같은 명령을 다시 치면 됩니다.
- 다시 빌드하지 않습니다.

## 작업 규칙

- 코드는 컨테이너 안 `/workspace/hypernova`에 연결돼 있습니다. 호스트(VS Code)에서 저장하면 컨테이너에 바로 반영됩니다. 데이터는 `/data`(호스트 `~/hypernova-data`)에 둡니다.
- git은 호스트에서 씁니다. 컨테이너 안에서는 실행과 빌드만 합니다.
- 코드나 설정에 개인 절대경로(`/home/이름/...`)를 넣지 않습니다. 저장소 상대경로나 `/data/...`를 씁니다.
- 패키지가 더 필요하면 컨테이너 안에서 `apt`나 `pip`로 설치하지 말고 Dockerfile을 고치는 PR을 냅니다. 컨테이너를 다시 만들면 안에서 설치한 것은 사라집니다.
- 컨테이너 없이 호스트에서 Python 도구(맵·지형 처리 등)를 돌릴 때는 [공용 Python 환경](../docs/development/python-env.md)(`./tools/setup-venv.sh`)을 씁니다. 이미지의 robot venv와 같은 `uv.lock`을 씁니다.
- 이미지 버전이 바뀌면(`git pull` 후 `docker/.env`의 태그가 바뀜) 보행팀은 `./docker/hn build sim`, 인지팀·SW팀은 `./docker/hn pull ros`를 다시 실행합니다.
- 끝낼 때는 `./docker/hn stop`(안 해도 됨). 컨테이너가 꼬였으면 `./docker/hn reset`. 빌드 결과와 캐시는 남습니다.

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| `permission denied ... docker.sock` | [3단계](#3-sudo-없이-docker-쓰기) 후 다시 로그인했는지 |
| `could not select device driver "nvidia"` | [4단계](#4-nvidia-container-toolkit)의 `nvidia-ctk runtime configure`와 docker 재시작 |
| 호스트에서는 `nvidia-smi`가 되는데 컨테이너에서는 안 됨 | Docker Desktop을 쓰고 있지 않은지, 같은 PC의 터미널에서 실행했는지(WSL·원격·dev container 아님) |
| 토픽 이름은 보이는데 `ros2 topic echo`에 데이터가 안 옴 | 컨테이너가 `hn` 스크립트로 실행됐는지(`--ipc=host` 필요) |
| 남의 토픽이 보임 | `docker/.env.local`의 `ROS_DOMAIN_ID`가 다른 사람과 겹치는지 |
| 컨테이너가 만든 파일이 root 소유 | `docker/.env.local`의 UID·GID가 `id -u`, `id -g`와 같은지 |
| Isaac Sim 창이 안 뜸 | 호스트 데스크톱 세션에서 실행했는지, `echo $DISPLAY` 값이 있는지 |
