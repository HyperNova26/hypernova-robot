# 공용 Python 환경

호스트에서 Python 도구(맵·지형 처리, sim2sim 스크립트, 변환 도구)를 돌릴 때 쓰는 환경입니다. 2026-10-22 기준이고, [ADR-0002 §4](../decisions/0002-dev-environment.md#4-버전-고정)의 robot venv를 호스트에서도 같은 버전으로 쓰게 하는 것이 목적입니다.

- 패키지 목록: 저장소 최상위 [`pyproject.toml`](../../pyproject.toml)
- 정확한 버전: [`uv.lock`](../../uv.lock) (직접 고치지 않음)
- 만들고 갱신하는 스크립트: [`tools/setup-venv.sh`](../../tools/setup-venv.sh)
- venv 위치: `<저장소>/.venv` (`.gitignore`에 들어 있음)

## 왜 시스템 Python에 바로 `pip install`하지 않나

Ubuntu 24.04에서 `pip install`을 치면 `error: externally-managed-environment`가 납니다. 고장이 아니라 일부러 막아 둔 것입니다([PEP 668](https://peps.python.org/pep-0668/), Ubuntu 23.04부터). 시스템 Python의 패키지는 apt가 관리하고, ROS 2 Jazzy(`rclpy`, `colcon` 등)도 거기에 설치됩니다. pip가 그 위에 다른 버전을 덮어쓰면 ROS나 시스템 도구가 몇 주 뒤에 엉뚱한 곳에서 깨집니다.

그래서 `sudo pip install`, `pip install --user`, `--break-system-packages`는 쓰지 않습니다. 필요한 패키지는 아래 방법으로 이 환경에 넣습니다.

## 처음 한 번

1. uv를 설치합니다. sudo가 필요 없고 `~/.local/bin`에 들어갑니다.

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   설치 후 **터미널을 새로 엽니다.** `uv --version`이 나오면 됩니다.

2. 저장소 최상위에서 환경을 만듭니다.

   ```bash
   ./tools/setup-venv.sh
   ```

   처음에는 Open3D 등을 받느라 1분 안팎 걸립니다. Python을 따로 설치할 필요는 없습니다. Ubuntu 24.04의 `/usr/bin/python3.12`를 씁니다.

## 쓰는 법

```bash
uv run python -c "import open3d; print(open3d.__version__)"   # 설치 확인
uv run python <스크립트.py>
```

- `uv run`은 activate 없이 `.venv`로 실행합니다. 셸에서 계속 쓰려면 `source .venv/bin/activate`도 됩니다.
- VS Code: `Python: Select Interpreter` → `./.venv/bin/python`
- `git pull` 뒤에 `uv.lock`이 바뀌었으면 `./tools/setup-venv.sh`를 다시 실행합니다. 몇 초면 끝납니다.

## 패키지를 추가할 때

```bash
uv add <패키지>          # pyproject.toml과 uv.lock이 같이 바뀜
./tools/setup-venv.sh    # 확인
```

- `pyproject.toml`과 `uv.lock`을 **같은 커밋**에 넣습니다. lock이 안 맞으면 다른 사람의 `setup-venv.sh`가 멈춥니다.
- `pip install`이나 `uv pip install`로 venv에 직접 넣지 않습니다. 내 PC에서만 되는 환경이 됩니다.
- ADR-0002 §4에 버전이 고정된 패키지(MuJoCo, onnx, onnxruntime, Open3D)는 ADR을 고치는 PR로만 올립니다. Isaac Lab lock과 같은 버전을 쓰기 위해서입니다.

## 이 환경에 넣지 않는 것

| 무엇 | 어디서 |
| --- | --- |
| ROS 2 (`rclpy`, 메시지 패키지, colcon) | apt 또는 `hn:ros` 이미지. venv가 `--system-site-packages`라서 네이티브로 설치한 ROS를 venv 안에서 import할 수 있습니다. |
| Isaac Sim / Isaac Lab, torch | `hn:sim` 이미지의 Isaac Lab venv. 의존성이 240개쯤 맞물려 있어 섞으면 깨집니다. |
| CloudCompare | 앱입니다. `sudo snap install cloudcompare` |
| PDAL | Python 바인딩이 시스템 C++ 라이브러리를 요구해서 pip만으로 깔끔하게 안 됩니다. Open3D + numpy/scipy로 대신합니다. |

## numpy를 1.26.4로 고정한 이유

ROS 2 Jazzy의 메시지 바인딩은 Ubuntu 24.04의 numpy(1.26.4) C API로 빌드돼 있습니다. venv에 numpy 2.x가 들어가면 시스템 numpy를 가려서, ROS를 같이 쓰는 스크립트에서 메시지 import가 깨집니다. Jazzy가 numpy 2로 넘어가기 전까지는 올리지 않습니다.

## 컨테이너에서 쓸 때

저장소가 컨테이너 `/workspace/hypernova`에 mount되므로 호스트의 `.venv`도 컨테이너에 보입니다. 하지만 venv 안 실행 파일은 호스트 경로를 가리키고 있어 컨테이너에서는 쓸 수 없습니다. 이미지에서는 venv를 저장소 밖에 둡니다.

```dockerfile
ENV UV_PROJECT_ENVIRONMENT=/opt/hn-venv
RUN ./tools/setup-venv.sh   # pyproject.toml, uv.lock을 COPY한 뒤
```

이렇게 하면 호스트와 컨테이너가 같은 `uv.lock`을 쓰고, 서로의 venv를 건드리지 않습니다.

## colcon과 같이 쓸 때

colcon을 저장소 최상위에서 돌리면 `.venv` 안까지 훑을 수 있습니다. `--base-paths ros_pkgs`처럼 범위를 좁혀 둡니다.

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| `uv: command not found` | uv 설치 후 터미널을 새로 열었는지. 그래도 안 되면 `~/.local/bin`이 `PATH`에 있는지 |
| `/usr/bin/python3.12 가 없습니다` | Ubuntu 24.04가 아님. 22.04라면 컨테이너(`./docker/hn ros`)를 씁니다 |
| `The lockfile at uv.lock needs to be updated` | `git pull`을 다 받았는지. 내가 `pyproject.toml`을 고쳤다면 `uv lock` 후 둘 다 커밋 |
| `error: externally-managed-environment` | 시스템 `pip`를 쓰고 있음. `uv add`로 추가하고 `uv run`으로 실행 |
| `numpy.core.multiarray failed to import` (ROS 같이 쓸 때) | 누군가 numpy 2.x를 넣었는지 `uv run python -c "import numpy; print(numpy.__version__)"` |
| Open3D 창이 안 뜸 | 호스트 데스크톱에서 실행했는지. SSH나 컨테이너 안에서는 시각화 창이 뜨지 않습니다 |
