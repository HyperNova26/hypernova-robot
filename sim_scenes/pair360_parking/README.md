# PAIR360 주차장 데모 지형

2026-10-27 기준입니다. PAIR360 T1 Sequence0 지도에서 CloudCompare Cross Section으로 잘라 둔 주차장 crop을 MuJoCo·Isaac Lab·Nav2·SLAM이 같은 좌표로 사용하도록 변환합니다. 원본 전체 지도는 읽지 않습니다.

## 출처와 라이선스

원본: Geunu Kim, Daeho Kim, Jaeyun Jang, Hyoseok Hwang, *PAIR360: A Paired Dataset of High-Resolution 360° Panoramic Images and LiDAR Scans*, IEEE RA-L, 2024. [논문](https://doi.org/10.1109/LRA.2024.3460418), [데이터 및 ODbL 안내](https://airlabkhu.github.io/PAIR-360-Dataset/).

PAIR360은 ODbL 1.0입니다. 공유·공개하는 파생 지형, 지도, pose 데이터도 ODbL 1.0을 유지하고 원저자·논문·원본 위치·변경 내용을 표시합니다. 출력의 `ATTRIBUTION.txt`를 함께 전달합니다. 저장소의 도구·설정은 Apache-2.0, 이 문서는 CC BY 4.0이며 데이터 라이선스와 구분합니다.

원시 BIN/PCD/PLY, 생성한 heightfield·mesh·USD·지도·인계 ZIP은 Git에 넣지 않습니다. 원시 데이터 폴더는 읽기만 합니다. BIN 변환도 출력 폴더에 만든 사본에서 수행합니다.

## 좌표계

모든 처리값은 [frame.yaml](./frame.yaml)에 있습니다.

- 원본: T1S0 LIO map, 즉 Sequence0의 첫 LiDAR frame입니다.
- 원점: map에서 `[-31.9364, 110.2582, -0.4447]` m입니다.
- 초기 yaw: map → ENU `-93.17°`이며 GPS 2D fit의 RMS는 약 1.6 m입니다.
- demo: x=동, y=북, z=위, 단위 m입니다. 시작 yaw=0은 동쪽 도로 방향입니다.
- 원점 반경 5 m, 초기 `|z| < 0.3 m`의 점에서 RANSAC 평면을 구해 법선을 +z로 회전하고 평면이 원점에서 z=0을 지나도록 z를 옮깁니다.

최종 회전에는 작은 roll/pitch가 들어가므로 demo는 수평화한 ENU 근사입니다. GPS anchor 정확도는 3 m이며 정밀 측량 좌표가 아닙니다. 원본에서 고른 시작점이 지면 평면과 다르면 최종 원점의 z에는 평면 보정량이 남습니다. 실제 변환과 검사값은 출력의 `frame_resolved.yaml`이 기준입니다. 기울기 3° 초과는 경고합니다. 원점이 crop 밖이거나 원점 부근 지면이 ±0.10 m를 벗어나면 중단합니다. CloudCompare global shift를 임의로 보정하지 않습니다.

`generated_from_data` 절에는 검증한 출력의 최종 행렬과 기울기를 복사합니다. 이 절은 처리 입력에 쓰지 않으므로 기록을 추가해도 결과가 바뀌지 않습니다. 파이프라인 자체는 저장소 설정을 수정하지 않습니다.

## 다시 만들기

저장소 최상위, ADR의 Ubuntu 24.04·Python 3.12 robot venv에서 실행합니다. 아래 변수는 각자의 위치로 정합니다. 현재 `output.directory`는 저장소 옆의 `PAIR360_demo/2026-10-26_v1`입니다. 컨테이너에서 사용할 때는 이 폴더를 `/data` 아래에 연결합니다.

```bash
./tools/setup-venv.sh
RAW=/path/to/PAIR360/T1_Parking_and_OpenTheater/extra
OUT="../PAIR360_demo/2026-10-26_v1"
uv run python tools/map/pair360_demo.py \
  --config sim_scenes/pair360_parking/frame.yaml \
  --input "$RAW/T1_parking_Seq0_demo.bin" \
  --poses "$RAW/T1-Parking_and_Peace_Amphitheater-0-lidar_pose.txt" \
  --out "$OUT"
```

같은 이름의 PLY/PCD가 있으면 BIN보다 먼저 읽습니다. crop 이름이 `demo.bin`이면 그 이름을 전달합니다. CloudCompare 실행 파일을 자동으로 찾지 못하면 `--cloudcompare <실행파일>`을 지정합니다. v2.11.1의 silent/offscreen CLI로 사본을 binary little-endian PLY로 변환합니다. 변환에 실패하면 GUI에서 crop을 binary PLY로 다시 저장해야 합니다.

먼저 `--out`을 생략하고 `--quick`을 붙여 전체 단계를 확인하면 기본 출력 아래 `quick/`에 저장합니다. quick은 voxel·heightfield·2D map이 0.2 m이므로 5 cm 정밀도 확인용이 아닙니다. 명시한 `--out`은 그대로 사용하므로 정식 결과와 다른 폴더를 지정합니다.

## 결과와 범위

Ground는 법선·평면성·이웃 연속성으로 고릅니다. 겹치는 patch마다 최대 두 평면을 유지하고, 원점 근처의 확정 ground에서 확장하며 주변 예측 높이에 맞는 후보를 선택합니다. 조밀한 지붕보다 성긴 두 번째 지면 평면이 선택될 수 있습니다. `ground_report.yaml`과 `ground_patches.npz`에 선택 근거를 남깁니다. 차는 roof patch와 측면 법선·크기로 찾으며 확신이 없으면 `other`에 남깁니다. 자세한 임계값과 한계는 [맵 도구 안내](../../tools/map/README.md)에 있습니다.

`heightfield.npy`가 두 시뮬레이터의 공통 원본입니다. MuJoCo는 `walk_box`를 잘라 `terrain.hfield`와 `terrain.xml`로, Isaac은 전체 범위를 `terrain.obj`와 collision mesh 하나인 `terrain.usd`로 내보냅니다. 현재 walk box는 **원점 중심 80 × 80 m 임시값**이며 데이터 범위와 겹치는 grid node까지만 사용합니다.

분류 결과는 `ground.ply`, `cars.ply`, `other.ply` 세 개입니다. 건물은 별도 class 없이 `other`에 포함하며 지형에는 ground만 사용합니다. 2026-10-27에 `buildings.npy/ply`와 건물 블록 굽기·관련 설정을 제거했습니다. 이전 출력은 보존하고 ground·차량 선택 규칙은 수정하지 않았습니다. `map2d.pgm`·`map2d.yaml`은 Nav2 지도이며, `slam_handoff.zip`에는 변환·지도·선택된 T1S0 LiDAR pose·시간 구간·설정·출처·검사 결과가 들어갑니다. 큰 점군, heightfield 배열, mesh는 ZIP에 넣지 않고 별도로 전달합니다. ZIP의 manifest는 압축 직전까지 완료한 단계의 기록입니다.

Nav2 장애물의 기본 높이 범위는 최종 heightfield 위 0.10–1.00 m입니다. non-ground로 남은 15 cm curb를 포함하도록 사용자가 하한을 0.10 m로 선택했습니다. curb가 heightfield 자체에 들어간 경우 상대 높이가 낮아져 제외될 수 있습니다.

단계별 파일, 재실행, 알려진 한계와 simulator 사용법은 [맵 도구 안내](../../tools/map/README.md)를 봅니다.

## 2026-10-26 v1 quick 확인

법선·국소 평면 두 후보·주변 ground 연속성으로 바꾼 뒤 `PAIR360_demo/2026-10-26_v1/quick`에 한 번 실행했습니다. 합성 시험 16개는 26.70초, 실제 quick은 3분 35초에 통과했고 최대 RSS는 약 1.02 GiB였습니다. 이전 변환 PLY와 원본 BIN의 SHA256이 기존 변환 기록과 같은지 확인한 뒤 그 PLY를 읽었습니다. 원시 데이터와 이전 결과는 수정하지 않았습니다.

| 항목 | 결과 |
| --- | --- |
| ground / cars / buildings / other | 104,132 / 6,325 / 0 / 1,433,513점 |
| 두 후보 patch / 두 번째 후보 선택 | 7,068 / 618개 |
| 확정 ground patch | 14,349개 |
| mesh 삼각형 | 1,268,106 → 225,390 |
| 전체 probe 최대 수직 오차 | 0.0186732 m |
| MuJoCo·USD·Nav2·pose 검사 | 통과 |

현재 ground는 원점의 신뢰 가능한 ground에 연결되는 영역만 보수적으로 확정합니다. 기존 quick보다 ground 점수가 줄었고 buildings도 0점이므로 의미 분류가 개선되었다고 단정하지 않습니다. `quick/segmentation_preview.png`와 CloudCompare의 네 PLY를 함께 확인합니다. 단차·가림으로 분리된 지면과 연결된 건물의 묶음은 추가 조정이 필요할 수 있습니다. 정식 해상도 실행과 Isaac Sim GUI 확인은 하지 않았습니다.

## 이전 실제 crop quick 확인

2026-10-23에 원본 BIN 사본을 snap CloudCompare v2.11.1로 변환하고 `--quick`을 한 번 실행했습니다. 원본 BIN·pose의 전후 SHA256이 같았습니다. 원본 7,751,328점에서 ground 195,572, cars 4,153, buildings 112,164, other 1,232,081점이 남았습니다.

아래 기록과 보관 중인 quick 지도·인계 ZIP은 변경 전 하한 0.20 m 설정으로 생성했습니다. 현재 기본값 0.10 m는 합성 시험으로 확인하며, 실제 데이터 지도와 ZIP은 새 출력 폴더에서 다시 생성해야 합니다.

| 항목 | 결과 |
| --- | --- |
| 원점 포함 / 주변 측정 지면 | 포함 / z=+0.00550 m |
| 수평화 기울기 | 0.99036° |
| heightfield | 764×832, 0.2 m |
| sample 범위 | x=-50.6…115.6 m, y=-100.8…51.8 m |
| mesh 삼각형 | 1,268,106 → 1,014,483, 약 20% 감소 |
| 전체 probe 최대 수직 오차 | 0.000315 m |
| random probe p95 수직 오차 | 0.00000505 m |
| traversal / 선택 pose | 4구간 / 183개 |
| SLAM ZIP | 약 66 KiB |

MuJoCo load와 origin ray, USD의 mesh 하나 및 collision API, Nav2 metadata 검사를 통과했습니다. 낮은 triangle target은 오차·ray 누락 검사에서 거부되어 더 많은 삼각형을 유지했습니다. 상세값은 출력의 `smoke_report.yaml`, `mesh_report.yaml`, `traversals.yaml`이 기준입니다.

이 호스트는 Ubuntu 22.04이며 `/usr/bin/python3.12`가 없어 `setup-venv.sh`는 실패했습니다. 이 확인에서는 기존 uv-managed Python 3.12로 저장소 `.venv`를 준비하고 `UV_PYTHON_PREFERENCE=managed uv run --no-sync`를 사용했습니다. ADR의 system interpreter 규칙은 바꾸지 않았고 `uv lock --check`는 통과했습니다. host의 ROS Humble Python 경로와 pytest plugin은 시험에서 분리했습니다. 정식 개발 환경 준비가 별도로 필요합니다.

원본에서 고른 시작점은 최종 demo에서 z=-0.25864 m로 옮겨졌습니다. 이는 평면을 z=0으로 옮긴 결과이며 global shift가 아닙니다. 로봇의 지면 시작 위치는 설정의 demo `[0,0,0]`을 사용합니다. 정식 실행도 원본 crop으로 평면을 다시 추정하므로 출력의 최종 행렬을 확인합니다.
