# S-004 ground 기준선 확인 기록

2026년 11월 2일, 사용자가 제공한 원래 `T1_parking_Seq0_demo.bin`을 확보했습니다. 다운로드 파일을 `data/PAIR360_data/T1_Parking_and_OpenTheater/`에 복사했으며 SHA-256은 `f3b22a067521030e4cff035c98b33daa3546cf39ba0271c2940191da8bd73c50`으로 현재 브랜치의 `sim_scenes/pair360_parking/frame.yaml`에 보관된 값과 일치합니다. 앞으로는 이 BIN을 기준 입력으로 사용합니다. 아래 AABB 재생성·장면 진단은 원본 확보 전의 참고 기록입니다.

원본의 작업 사본을 CloudCompare 2.13.2에서 열어 7,751,328점을 확인하고 binary little-endian PLY로 저장했습니다. 작업 파일과 변환 로그는 `data/PAIR360_demo/20261102_original_bin_conversion/`에 있습니다. 다운로드 원본과 저장소에 배치한 BIN은 보존했습니다. S-004 요구사항의 출처는 사용자가 대화에 붙여 준 노션 본문입니다.

기존 `tools/map/demo_sim_converter.py`로 `sim_scenes/1102_demo_whole/`에 `terrain.usd`, `terrain.xml`, `scene.json`을 생성했습니다. 0.5 m voxel 350,693개를 MuJoCo box 75,832개와 USD 삼각형 714,730개로 내보냈습니다. origin은 `[0, 0, 0]`, scale은 `1`이며 과거 frame의 회전·수평화는 적용하지 않았습니다. 전체 점군 변환이므로 ground 분리나 S-004 완료를 의미하지 않습니다.

WSL의 Windows mount에 직접 저장하면 마지막 `renameat2` 호출이 `EINVAL`로 실패했습니다. Linux 임시 경로에서 생성한 뒤 같은 실행 안에서 저장소로 복사했습니다. 재현용 실행·검사 스크립트는 위 작업 디렉터리의 `run_whole.py`, `verify_scene.py`이며 기존 변환기 코드는 수정하지 않았습니다. 검증 결과는 산출물 폴더의 `validation.json`을 기준으로 확인합니다.

USD 삼각형 인덱스·유한 좌표·Z-up·meter 단위·collision `none`과 XML box 크기를 검사했고, 두 형식의 전체 좌표 범위가 일치했습니다. MuJoCo headless 모델 로드는 60초 제한에 걸려 실행 성공을 확인하지 못했습니다. Isaac Sim GUI와 로봇 물리도 미검증입니다. 전달용 ZIP은 `data/PAIR360_demo/20261102_demo_whole_handoff.zip`이며 전체 장면 파일, README, 입력 이력과 검증 결과를 포함합니다.

## 확인 결과

| 항목 | 결과 |
| --- | --- |
| 저장소 | `feat/pair360-demo-terrain`, commit `29e6bf5` |
| 실행환경 | WSL 2 Ubuntu 24.04, CPython 3.12.3, uv 0.13.6 |
| Python 환경 | `$HOME/.venv_hypernova_ground`, NumPy 1.26.4, Open3D 0.19.0, USD 26.11 |
| CloudCompare | Windows 2.13.2, CSF·3DMASC plugin 확인 |
| 공식 원본 PCD | 42,500,935점, 680,015,125 bytes |
| 재생성 crop PLY | 7,777,239점, 124,436,013 bytes |
| 과거 crop 기록 | 7,751,328점 |
| 차이 | 재생성본이 25,911점 많음, 과거 crop 대비 약 0.33% |
| CloudCompare 로드 | 원본 PCD와 crop PLY를 한 세션에서 각각 12.45초, 1.55초에 정상 로드 |
| Global Shift | 적용하지 않음. 좌표 최댓값이 약 224 m라 CloudCompare 자동 shift 기준보다 작음 |

## 내려받은 원본

공식 NAS의 `Traversal1/Parking_and_Open_theater/extra/`에서 필요한 두 파일만 내려받았다. 원본은 읽기 전용으로 유지하며 Git에서 제외한다.

| 파일 | 크기 | SHA-256 |
| --- | ---: | --- |
| `T1_parking_Seq0.pcd` | 680,015,125 bytes | `b14e6def9d20cd8db65fc35ac22efa7ea34aefe9c22e026953b9468433813ed1` |
| `T1-Parking_and_Peace_Amphitheater-0-lidar_pose.txt` | 123,679 bytes | `b95716a02f1803e87a17813c85ee4617306e265b7dc18ffbfffa1f40ed036096` |

저장 위치는 다음과 같다.

```text
data/PAIR360_data/T1_Parking_and_OpenTheater/extra/
├── T1_parking_Seq0.pcd
└── T1-Parking_and_Peace_Amphitheater-0-lidar_pose.txt
```

PCD 헤더는 `FIELDS x y z intensity`, `SIZE 4 4 4 4`, `TYPE F F F F`, `DATA binary`다. 각 점은 little-endian float32 네 개로 구성되며 파일 크기와 `POINTS 42500935`가 일치한다.

## crop 재생성

과거 `tools/map/pair360_demo.py`는 crop을 만들지 않았다. 이미 잘린 BIN·PLY·PCD를 받아 변환하는 코드였으며, README에는 CloudCompare Cross Section으로 수동 crop했다고 적혀 있다. 정확한 Cross Section 박스 설정은 저장소에 남아 있지 않다.

이번에는 과거 `scene.json`에 남아 있던 XYZ 최솟값과 최댓값을 inclusive AABB로 적용했다.

```text
min = [-81.3052749633789, 64.42131042480469, -12.098955154418945]
max = [ 64.14539337158203, 223.58726501464844, 38.09461975097656]
```

재현 명령은 다음과 같다.

```bash
uv run --no-sync python tools/map/extract_pair360_demo.py \
  data/PAIR360_data/T1_Parking_and_OpenTheater/extra/T1_parking_Seq0.pcd \
  --output data/PAIR360_demo/T1_parking_Seq0_demo_binary.ply
```

산출물은 다음 두 파일이다.

```text
data/PAIR360_demo/T1_parking_Seq0_demo_binary.ply
data/PAIR360_demo/T1_parking_Seq0_demo_binary.json
```

PLY SHA-256은 `bf453fcdf9201520a5b2b57665dfaa6cd1aec92dfce8d9f2c6ae28e0902821ab`다. 형식은 binary little-endian이며 `x`, `y`, `z`, `intensity`를 float32로 보존한다. 기존 출력과 `.part` 파일이 있으면 덮어쓰지 않고 중단한다.

## 기존 crop과의 차이

AABB crop은 7,777,239점을 선택했다. 과거 BIN은 7,751,328점이므로 25,911점이 더 들어갔다. 0.5 m 점유 voxel도 과거 350,693개에서 352,784개로 2,091개 늘었다. 점 수 차이는 약 0.33%, voxel 차이는 약 0.60%다.

최소·최대 좌표만으로는 수동 Cross Section의 정확한 선택 영역을 복구할 수 없다. 따라서 이 PLY를 과거 BIN과 동일하다고 취급하지 않는다. 원래 BIN을 확보하고 해시 일치를 확인했으므로 AABB 재생성본은 실험 기준에서 제외한다. 추가 점이 생긴 정확한 원인은 크롭 설정이 없어 확정하지 못했다.

## 좌표와 Global Shift

| 확인 항목 | 결과 | 근거 |
| --- | --- | --- |
| 좌표축 | 원본 T1S0 map의 X·Y·Z, Z-up | 저장소 frame 기록과 장면 높이 분포 대조 |
| 단위 | m | 저장소 설정, 차량·건물 크기와 전체 범위 대조 |
| X 범위 | -81.305275 ~ 64.145393 m | PCD 청크 검사와 PLY manifest |
| Y 범위 | 64.421310 ~ 223.587265 m | PCD 청크 검사와 PLY manifest |
| Z 범위 | -12.098955 ~ 38.094620 m | PCD 청크 검사와 PLY manifest |
| Global Shift | `[0, 0, 0]`, 추가 shift 없음 | 생성 코드가 원좌표를 보존하고 CloudCompare CLI에서 shift를 적용하지 않음 |

이 좌표는 M-002 공통 원점 frame이 아니다. 후속 ground 산출물은 `frame.yaml`의 `origin_in_map`, yaw와 leveling을 검증한 뒤 공통 frame으로 변환해야 한다.

## 장면 기준선

1 m XY, 0.1 m Z histogram으로 밀도·높이·이중층 후보를 만들었다. 이 결과는 의미 분류 정답이 아니라 CloudCompare에서 볼 구역을 좁히는 진단 자료다.

- 자동차 행: source-map 기준 `x=-80~-20 m` 부근에서 `y=149~156 m`, `173~183 m`, `191~201 m`에 반복되는 차량 크기 구조가 뚜렷하다. `y=119~125 m`에도 한 줄이 보인다.
- 건물 후보: `x=25~65 m, y=85~163 m`의 큰 ㄴ자 구조가 가장 선명하다. `x=-15~12 m, y=64~188 m`의 세로 띠에는 벽·수목·경사 구조가 섞여 있어 건물로 단정하지 않는다.
- 빈 영역: 큰 구조물 안쪽 `x=34~62 m, y=88~157 m`, 패치 동쪽 경계, 차량 아래와 건물 뒤편에 관측 공백이 있다. 측정 지면에서 먼 영역은 heightfield에서 잘라내거나 미측정 상태로 남겨야 한다.
- 이중 지면: 자동 후보가 자동차 지붕·수목까지 함께 잡아 위치를 확정하지 못했다. 서쪽 통로 후보인 `x=-45~-33 m, y=74~95 m`와 인접 구역을 CloudCompare 측면 시점·단면으로 우선 확인한다. 0.3~0.6 m 간격의 두 층 중 주변 지면과 이어지는 한 층만 남긴다.

진단 자료는 아래에 있다.

```text
data/PAIR360_demo/T1_parking_Seq0_demo_diagnostics_v2.png
data/PAIR360_demo/T1_parking_Seq0_demo_diagnostics_v2.json
```

CloudCompare 2.13.2 CLI는 원본 PCD와 crop PLY를 한 세션에서 정상 로드했다. 별도 PLY 확인에서는 cloud 1개와 7,777,239점을 확인했다. GUI에서는 PLY 속성 매핑 대화상자에서 `x`, `y`, `z`를 좌표로, `intensity`를 scalar field로 확인한 뒤 열면 된다.

## 검증 상태와 한계

- crop 추출 합성시험 2개가 통과했다.
- CloudCompare CLI 실파일 로드가 통과했다.
- 원본 PCD와 pose의 크기·SHA-256을 기록했다.
- 원본과 생성물은 `.gitignore`의 `/data/` 규칙으로 Git에서 제외된다.
- 기존 map 회귀시험 전체는 아직 실행하지 않았다. WSL에서 Windows NTFS를 반복 접근하는 속도가 느려 앞선 환경 확인에서는 4개까지만 진행했다.
- 이중 지면은 아직 CloudCompare 단면으로 확정하지 않았다.
- ground/non-ground 분리, CSF·SMRF 비교, ground mesh, Isaac Lab 물리 확인은 시작 전이다.

## 다음 작업

다음 개발 루프는 `원본·crop 시각 확인 → CSF 기준선 → SMRF 비교 → 노이즈·이중 지면 정책 → ground 전용 mesh → Isaac Lab 확인` 순서로 진행한다. 첫 단계에서는 CloudCompare에서 위 네 구역을 확인하고 스크린샷과 단면 좌표를 남긴다. 이후 같은 crop과 공통 frame을 고정한 상태에서 CSF와 SMRF만 비교한다.
