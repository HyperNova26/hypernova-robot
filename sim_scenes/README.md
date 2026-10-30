# 시뮬레이터 장면 변환 안내

2026-10-30 기준입니다. `tools/map/`의 도구는 `.sh` 실행기와 같은 이름의 `.py` 구현 파일로 구성됩니다. `.sh`는 환경과 Python 실행기를 선택하고 인수를 전달합니다.

- [`demo_sim_converter.sh`](../tools/map/demo_sim_converter.sh) / [`demo_sim_converter.py`](../tools/map/demo_sim_converter.py): 점군 전체를 공통 voxel 점유로 변환하여 USD와 MuJoCo XML을 만듭니다.
- [`demo_sim_disassembler.sh`](../tools/map/demo_sim_disassembler.sh) / [`demo_sim_disassembler.py`](../tools/map/demo_sim_disassembler.py): 입력 파일을 확인하고 날짜별 빈 출력 폴더를 만듭니다. 분해 기능은 미구현입니다.

지면 분리와 그 뒤의 차량·기타 객체 분류·분리 과정은 아직 완성되지 않았습니다. 이 과정의 구현·개선과 실제 PAIR360 데이터 검증은 **[S-004 후속 작업](https://app.notion.com/p/40645bd87178819e9242cff36b48cb3d)**에서 다룹니다. 전체 점군 변환 결과나 기존 quick 산출물은 지면 분리 및 객체 분류 정확도를 입증하지 않습니다.

로봇 형상과 joint는 [`description/`](../description/), ROS 2 node·launch·simulator adapter는 [`ros_pkgs/`](../ros_pkgs/)에 둡니다. 이 안내의 스크립트는 오프라인 변환 도구이며 simulator를 자동으로 실행하지 않습니다.

## 실행 환경과 입력

저장소 최상위에서 실행합니다. 공용 Python 환경은 [Python 환경 안내](../docs/development/python-env.md), 컨테이너 사용법은 [Docker 안내](../docker/README.md)를 따릅니다. `.sh` 실행기의 Python 선택 순서는 다음과 같습니다.

1. `HN_MAP_PYTHON`을 지정하면 해당 Python 실행 파일을 사용합니다.
2. 지정하지 않았고 `/opt/hn-venv/bin/python`이 있으면 컨테이너의 robot venv를 사용합니다.
3. 그 외에는 `uv run --no-sync --project <저장소 경로> python`을 사용합니다.

스크립트 실행 시 의존성을 설치하거나 lock을 갱신하지 않습니다. `HN_MAP_PYTHON`에는 인수가 아닌 실행 파일 경로를 지정합니다. 예를 들어 준비된 호스트 venv를 선택할 수 있습니다.

```bash
HN_MAP_PYTHON="$PWD/.venv/bin/python" \
  ./tools/map/demo_sim_converter.sh /path/to/input.ply
```

`.py`를 직접 실행할 수도 있습니다. 이때 Python 환경은 호출자가 선택하며 두 실행 방식의 CLI와 기본 출력 경로는 같습니다. 저장소 경로는 Python 파일의 위치를 기준으로 결정합니다.

```bash
uv run --no-sync python tools/map/demo_sim_converter.py /path/to/input.ply
uv run --no-sync python tools/map/demo_sim_disassembler.py /path/to/input.ply
```

변환에는 준비된 NumPy, Open3D, usd-core가 필요합니다. 분해 출력 폴더 준비와 두 도구의 `--help`는 Python 표준 라이브러리만 사용하며 타사 패키지를 불러오지 않습니다. 도움말 실행에도 Python은 필요합니다.

변환기는 Open3D가 지원하는 일반 점군 형식과 CloudCompare native BIN을 받습니다. 확장자를 바꾸어 지원하지 않는 형식을 대신 입력할 수 없습니다. 지원하지 않는 형식, 읽을 수 없는 파일, 유효한 XYZ가 없는 입력은 오류로 중단합니다. 일반 점군 형식은 PLY, PCD, XYZ, XYZN, XYZRGB, PTS입니다. BIN은 임의의 raw LiDAR binary가 아니라 CloudCompare에서 저장한 BIN이어야 합니다.

CloudCompare native BIN을 읽으려면 별도의 CloudCompare 실행 파일이 필요합니다. `--cloudcompare EXEC`으로 지정하거나 사용 가능한 실행 파일을 사용합니다. BIN은 임시 사본에서만 변환하며 원본을 저장·덮어쓰지 않습니다. CloudCompare는 선택적인 호스트 도구입니다. 컨테이너에 설치되어 있다고 가정하지 않으며, 컨테이너에서 호스트의 실행 파일 경로만 전달한다고 호스트 프로그램이 실행되는 것은 아닙니다. 컨테이너에서 BIN 변환을 사용할 수 없으면 호스트에서 사본을 PLY로 변환한 후 해당 PLY를 입력합니다.

현재 사용자가 지정한 입력은 다음 파일입니다.

```text
data/PAIR360_data/T1_Parking_and_OpenTheater/T1_parking_Seq0_demo.bin
```

## 전체 점군 변환

```text
./tools/map/demo_sim_converter.sh INPUT \
  [--voxel-size METERS] [--origin X Y Z] [--scale FACTOR] \
  [--date MMDD] [--output-root DIR] [--max-geoms COUNT] \
  [--cloudcompare EXEC]
```

| 인수 | 기본값과 의미 |
| --- | --- |
| `INPUT` | 필수 입력 점군 파일입니다. |
| `--voxel-size METERS` | `0.5` m입니다. 변환한 점군을 채울 voxel 한 변의 길이입니다. |
| `--origin X Y Z` | `0 0 0`입니다. 입력 좌표에서 뺄 원점이며 입력과 같은 단위를 씁니다. |
| `--scale FACTOR` | `1`입니다. 원점을 뺀 좌표에 곱하는 양의 배율입니다. 출력 단위는 m입니다. |
| `--date MMDD` | Asia/Seoul 기준 실행 날짜입니다. 예: `1030`입니다. |
| `--output-root DIR` | 저장소의 `sim_scenes/`입니다. 실행 위치와 관계없이 같은 기본 경로를 씁니다. |
| `--max-geoms COUNT` | `100000`입니다. 인접한 점유 voxel을 병합한 뒤 MuJoCo box geom 수가 이를 넘으면 생략하지 않고 오류로 중단합니다. |
| `--cloudcompare EXEC` | native BIN 사본 변환에 사용할 CloudCompare 실행 파일입니다. |

현재 PAIR360 BIN을 기본 해상도로 변환하는 예시입니다. CloudCompare가 자동으로 발견되지 않으면 `--cloudcompare /path/to/CloudCompare`로 실제 실행 파일을 명시합니다.

```bash
./tools/map/demo_sim_converter.sh \
  data/PAIR360_data/T1_Parking_and_OpenTheater/T1_parking_Seq0_demo.bin \
  --voxel-size 0.5
```

기본값으로 2026년 10월 30일에 실행하면 다음 세 파일을 만듭니다.

```text
sim_scenes/1030_demo_whole/
├── terrain.usd
├── terrain.xml
└── scene.json
```

`--date 1030 --output-root /path/to/new-results`를 지정하면 `/path/to/new-results/1030_demo_whole/`에 만듭니다. 해당 날짜의 출력 경로가 이미 있으면 덮어쓰지 않고 중단합니다. 입력 파일과 기존 결과를 수정하지 않습니다.

### 공통 기하와 한계

입력의 유한한 XYZ 전체를 사용합니다. 좌표 변환은 `(XYZ - origin) × scale`이며 회전·지면 수평화·GPS 정합을 수행하지 않습니다. 입력 축을 그대로 사용하므로 simulator의 z-up 및 필요한 단위에 맞는 점군을 준비합니다. PAIR360 pose 파일이나 [`pair360_parking/frame.yaml`](./pair360_parking/frame.yaml)은 필요하지 않습니다.

같은 점유 voxel을 두 형식에 기록합니다.

- `terrain.usd`: 정적인 삼각형 `Mesh` 하나입니다. 여러 높이의 점유를 같은 3차원 장면에 보존합니다.
- `terrain.xml`: 같은 점유 공간을 나타내는 정적인 box geom을 가진 MuJoCo 장면입니다. 인접한 점유 voxel을 정확히 병합하여 geom 수를 줄이며, 빈 공간은 채우지 않습니다.
- `scene.json`: 입력·변환 설정·점유 수·생성 코드 정보 등 결과를 확인할 metadata입니다.

이는 지면 높이 하나를 XY 격자에 저장하는 heightfield가 아닙니다. ground·차량·건물·기타 객체 분류, instance 분리, Nav2 지도, SLAM 인계 자료를 만들지 않습니다. 입력에서 관측되지 않은 공간을 채우거나 닫힌 실제 표면을 복원하지 않으며, voxel 경계에는 계단 모양의 양자화 오차가 생깁니다. 작은 voxel은 점유 수와 메모리 사용량을 늘리고, 인접 병합 후에도 geom 수가 커질 수 있습니다. 상한을 넘으면 목적에 맞는 voxel 크기로 새 실행을 준비합니다.

파일 생성과 구조 검사는 simulator GUI 표시나 물리 동작 성공을 의미하지 않습니다. 생성 뒤 Isaac Sim 또는 MuJoCo에서 실제 배치·축·충돌을 별도로 확인합니다. 스크립트는 viewer나 simulator를 실행하지 않습니다. MuJoCo XML의 box geom 수가 많으면 첫 모델 로딩이 수 분 이상 걸릴 수 있으며, 변환 시간과 모델 로딩 시간은 다릅니다. 로딩 부담을 줄이려면 더 큰 `--voxel-size`를 명시합니다.

## 분해 출력 폴더 준비

```text
./tools/map/demo_sim_disassembler.sh INPUT [--date MMDD] [--output-root DIR]
```

이 스크립트는 입력이 파일인지 확인한 뒤 `MMDD_demo_disassembled/` 빈 폴더 하나만 만들고 `not implemented`를 출력합니다. 파일이나 하위 폴더, 분류 결과를 만들지 않습니다. 날짜는 Asia/Seoul 기준이며 `--date`와 `--output-root`의 기본값은 변환기와 같습니다. 기존 출력 경로가 있으면 덮어쓰지 않습니다.

S-004에서는 먼저 지면을 나누는 과정과 이후 비지면 점군에서 차량·기타 객체를 분류·분리하는 과정을 각각 구현·개선하고, 실제 데이터에서 결과를 검증해야 합니다. 빈 출력 폴더 생성은 이 과정의 완료를 의미하지 않습니다.

```bash
./tools/map/demo_sim_disassembler.sh \
  data/PAIR360_data/T1_Parking_and_OpenTheater/T1_parking_Seq0_demo.bin
```

## 데이터 보존과 확인

- `data/PAIR360_data/` 원본과 `data/PAIR360_demo/` 기존 결과는 보존합니다. 원본은 읽기만 합니다.
- `sim_scenes/MMDD_demo_whole/`과 `sim_scenes/MMDD_demo_disassembled/`은 생성 결과이며 Git 추적에서 제외합니다. 별도 `--output-root`를 지정한 결과도 Git에 넣지 않습니다.
- 기존 PAIR360 장면의 [`frame.yaml`과 보관 기록](./pair360_parking/README.md)은 유지하지만 현재 변환기의 설정으로 사용하지 않습니다.
- PAIR360에서 만든 결과를 공유할 때에는 원본의 출처와 ODbL 1.0 조건을 확인합니다. 새 변환기는 출처 문서를 자동으로 만들어 주지 않습니다. [저장소 및 데이터 정책](../docs/development/repository-policy.md)을 함께 따릅니다.

준비된 공용 Python 환경에서 회귀시험을 실행합니다.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest tests/map -q
npx markdownlint-cli2
```

합성 시험은 스크립트의 입력·출력 계약과 기본 기하를 확인합니다. 실제 PAIR360 전체 변환 완료, 의미 분류 정확도, simulator GUI 및 로봇 물리 검증을 대신하지 않습니다.
