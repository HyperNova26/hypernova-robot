# PAIR360 crop → 데모 지형 파이프라인

2026-10-27 기준입니다. 한 crop에서 MuJoCo heightfield, Isaac 정적 collision mesh, Nav2 지도, SLAM 인계 자료를 만듭니다. 설정은 [frame.yaml](../../sim_scenes/pair360_parking/frame.yaml) 하나이고, 장면·좌표·라이선스는 [장면 안내](../../sim_scenes/pair360_parking/README.md)에 있습니다. 이 도구는 원시 데이터에 쓰지 않고 모든 처리 결과를 설정의 `output.directory` 또는 명시한 `--out` 아래에 둡니다.

## 실행

ADR-0002의 Ubuntu 24.04 및 `/usr/bin/python3.12`가 필요합니다. `./tools/setup-venv.sh`로 준비하고 `uv run`을 사용합니다. 의존성은 기존 numpy/scipy/Open3D/usd-core와 dev 의존성 pytest입니다. CSF·torch·PDAL·PCL Python binding은 추가하지 않습니다. 법선·국소 평면과 이웃 지면의 연속성을 사용합니다.

```bash
./tools/setup-venv.sh
uv lock --check
RAW=/path/to/PAIR360/T1_Parking_and_OpenTheater/extra
OUT="../PAIR360_demo/2026-10-26_v1"
uv run python tools/map/pair360_demo.py \
  --config sim_scenes/pair360_parking/frame.yaml \
  --input "$RAW/T1_parking_Seq0_demo.bin" \
  --poses "$RAW/T1-Parking_and_Peace_Amphitheater-0-lidar_pose.txt" \
  --out "$OUT"
```

`--input`은 잘라 둔 crop만 받습니다. 전체 42.5M 점 지도는 전달하지 않습니다. 입력이 CloudCompare native BIN이면 같은 stem의 PLY, PCD를 먼저 찾습니다. 없으면 `crop_input.bin` 사본을 출력에 만들고 다음 CLI를 사용합니다. Open3D로 BIN을 직접 읽지 않습니다.

```bash
QT_QPA_PLATFORM=offscreen CloudCompare -SILENT -AUTO_SAVE OFF \
  -O <출력의_BIN_사본> -C_EXPORT_FMT PLY -PLY_EXPORT_FMT BINARY_LE \
  -NO_TIMESTAMP -SAVE_CLOUDS
```

snap 설치도 `cloudcompare.CloudCompare`로 자동 탐색합니다. `--cloudcompare`로 다른 실행 파일을 지정할 수 있습니다. `cloudcompare.log`, 원본/변환본 SHA256 및 사용한 명령을 남깁니다. 실패하면 중단하고 GUI에서 binary PLY로 다시 저장합니다. 여러 cloud가 들어 있는 BIN도 자동 합치지 않고 중단합니다.

입력·pose 폴더와 출력은 서로 분리해야 합니다. `--out`을 생략하면 저장소 최상위 기준 `output.directory`를 사용합니다. 현재 정식 출력은 `../PAIR360_demo/2026-10-26_v1`이고 `--quick`의 기본 출력은 그 안의 `quick/`입니다. 명시한 `--out`에는 하위 폴더를 자동 추가하지 않습니다. `--quick`은 clean/ground/class voxel과 heightfield·Nav2 grid를 0.2 m로, 임의 mesh 검사점을 2,000개로 줄입니다. 정식 실행에는 `--quick`을 뺍니다.

## 단계와 파일

| 단계 | 입력 | 출력 |
| --- | --- | --- |
| `transform` | crop, 13열 T1S0 pose, 설정 | `transformed.npy`, `poses_map.npy`, `frame_resolved.yaml`, `input_provenance.yaml` |
| `clean` | transformed | `clean.npy`: 3 cm voxel + 20-neighbor statistical outlier 제거 |
| `ground` | clean | `ground.npy/ply`, `non_ground.npy`, `ground_surface.npy/yaml`, `ground_patches.npz`, `ground_report.yaml` |
| `classify` | non-ground, coarse ground surface | `cars/other.npy/ply`, `classes.yaml` |
| `heightfield` | ground, clean의 범위 | `heightfield.npy`, `heightfield_measured.npy`, `heightfield.yaml` |
| `mujoco` | heightfield | `terrain.hfield`, `terrain.xml`, `mujoco.yaml` |
| `isaac` | heightfield | `terrain.obj`, `terrain.usd`, `mesh_report.yaml` |
| `map2d` | heightfield, measured mask, 모든 non-ground | `map2d.pgm`, `map2d.yaml`, `map2d_report.yaml` |
| `handoff` | 저장한 원본 pose, 최종 변환, 원본 crop 범위 | `traversals.yaml`, `gt_poses_demo.tum`, `HANDOFF.md`, `ATTRIBUTION.txt` |
| `check` | 앞 단계 결과 | `smoke_report.yaml`, `slam_handoff.zip` |

선행 단계가 있으면 입력 경로 없이 개별 단계를 다시 실행할 수 있습니다. 지정한 단계는 항상 위 순서로 실행합니다. quick 결과를 재실행할 때에도 `--quick`을 붙입니다.

```bash
uv run python tools/map/pair360_demo.py \
  --config sim_scenes/pair360_parking/frame.yaml \
  --out "$OUT" --stages mujoco map2d check
```

`effective_config.yaml`은 실제 사용한 설정입니다. `manifest.yaml`은 설정·코드 및 단계 파일의 SHA256과 시간을 기록합니다. 설정·코드·quick 여부가 다르면 같은 출력을 재사용하지 않습니다. 설정을 바꿀 때는 새 출력 폴더를 씁니다. 선행 결과가 없거나 바뀌었으면 중단합니다. 단계를 다시 쓰기 전에 해당 단계와 모든 후속 단계의 완료 기록을 무효화합니다. 실패한 단계는 `failure.yaml`에 남습니다.

## 처리 기준

수평화는 초기 변환 뒤 원점 부근 지면만 RANSAC으로 맞춥니다. seed·fit 점수 상한을 고정합니다. 최종 행렬을 출력에 기록하고, 검증 후 설정의 `generated_from_data` 절에 복사합니다. crop 원점 포함 여부, origin 부근 측정 지면, MuJoCo origin ray, traversal 존재 여부 중 하나라도 실패하면 중단합니다. global shift를 추측해 보정하지 않습니다.

Ground 분석은 0.1 m voxel에서 법선과 covariance 고윳값으로 국소 평면성을 구합니다. 반경 0.4 m 안에서 최소 8점이 있고 선 모양이 아닌 평면만 후보로 사용합니다. 최대 경사 0.4 m/m를 넘는 표면은 지면 후보에서 제외합니다. 0.5 m 간격의 기준점마다 반경 0.85 m의 **겹치는** 이웃에서 최대 두 평면을 맞춥니다. 최소 8점·XY 방향의 충분한 분포·4 cm fitting 오차를 확인하고 10 cm 미만으로 겹치는 층은 중복으로 봅니다. 가장 많은 점을 가진 평면이 rank 0이며 rank 1도 지면 후보로 유지합니다. 패치당 최대 256점과 결정적인 point-normal 가설을 사용합니다.

수평화한 원점 반경 1 m의 신뢰 가능한 평면 중 원점 예상 높이와 8 cm 이내인 후보에서 시작합니다. 주변의 확정 지면과 공유 중간 위치에서 예상 높이·법선을 비교합니다. 이웃의 60% 이상이 높이 차이 8 cm·법선 차이 20° 이내로 동의해야 확장합니다. 두 후보 점수가 3 cm 이내이면 보류하고 새 이웃이 확정될 때 다시 평가합니다. 따라서 지붕의 점수가 더 많더라도 주변 지면에 맞는 두 번째 평면을 선택할 수 있습니다. 점이 가장 낮다는 이유만으로 선택하지 않습니다.

모든 clean 점은 가까운 확정 평면 최대 네 개의 예측 높이를 거리 가중으로 결합한 값과 비교합니다. 허용 범위는 아래 0.10 m, 위 0.12 m이며 patch 안의 일정한 높이와 비교하지 않습니다. 확정 평면의 반경 밖에는 ground label을 주지 않습니다. 지붕만 보이는 곳에 가짜 ground 점을 만들지 않습니다. `ground_surface.npy`에는 분류용으로 미측정 영역까지 외삽한 참조값이 있지만 실제 측정 마스크와는 다릅니다.

`ground_patches.npz`에는 `xy`, `planes`, `support`, `median_error_m`, `selected`, `ambiguous`가 있습니다. `planes[k,rank]`의 `[a,b,c]`는 `z=a*(x-xy[k,0])+b*(y-xy[k,1])+c`입니다. `selected=-1`은 미확정, 0/1은 선택한 후보입니다. `ground_report.yaml`에는 두 후보가 있는 패치 수, 두 번째 후보를 선택한 수, 미확정 패치·ground 점수를 기록합니다.

Non-ground는 0.1 m voxel에서 신뢰 가능한 상향 법선의 roof patch를 묶습니다. 공간 거리·법선 각도·점과 접평면의 거리를 모두 확인하고, roof 주위에서 측면의 법선이 footprint 주축과 맞는지 검사한 뒤 차량 크기 필터를 적용합니다. 완전히 닫힌 상자는 요구하지 않지만 지붕만 보이고 측면 근거가 없으면 `other`로 남습니다. 남은 점은 모두 `other`이며 공간 연결·높이·수직 법선 비율은 진단 기록에만 남깁니다. 그래프에는 점마다 최대 16개 이웃만 저장하며 기존 radius DBSCAN의 전체 이웃 캐시는 사용하지 않습니다. label은 3D 최근접 voxel 거리의 1.75배 이내에서만 원래 점으로 전달합니다. 임계값은 설정에서 바꿉니다.

Heightfield는 기본 0.05 m입니다. ground z의 cell별 median을 구하고 linear interpolation, convex hull 밖 nearest fill, 3×3 median filter를 거칩니다. `heightfield_measured.npy`는 보간 전에 ground 점이 실제 들어 있던 cell만 true입니다. 지형에는 ground만 사용합니다. 2026-10-27에 건물 class·`buildings.npy/ply`·건물 블록 굽기와 관련 설정을 제거했습니다. 건물 점도 `other`에 포함하며 기존 출력 폴더는 변경하지 않습니다. Ground·차량 선택 규칙은 이 변경에서 수정하지 않았습니다.

- `hf[i,j]`의 sample 위치는 `x=x0+j*resolution`, `y=y0+i*resolution`이며 i가 +y, j가 +x입니다.
- ground median의 집계 구간은 해당 sample에서 +x/+y 방향의 한 cell입니다. 완만한 경사에서는 node와 cell 중심 사이 반 cell 이하의 집계 편차가 있습니다.
- `z_min/z_max`는 m 단위 실제 높이이며 정규화하지 않습니다.
- MuJoCo binary는 int32 행·열 뒤 little-endian float32이고 파일의 첫 행은 min y입니다. PNG/XML elevation의 row 규약을 binary에 그대로 적용하지 않습니다. XML의 z range·z 최소값·XY 중심은 실제 crop 범위에서 구합니다. 방향은 비대칭 bump의 `mj_ray` 시험으로 확인합니다.
- Isaac grid mesh는 동일 sample의 두 삼각형 `(a,b,d)`, `(a,d,c)`로 구성하며 좌표를 재중심화하지 않습니다.
- Nav2의 origin은 `[x0,y0,0]`이고 PGM 첫 행은 max y입니다. 픽셀은 그 origin에서 시작하는 cell 영역이므로 픽셀 중심은 sample 위치보다 반 cell +x/+y에 있습니다.

Open3D 0.19의 `simplify_quadric_decimation(maximum_error=0.02**2, boundary_weight=100)`를 tile마다 사용합니다. [Open3D API](https://www.open3d.org/html/python_api/open3d.geometry.TriangleMesh.html)의 quadric cost는 거리 m와 같지 않으므로, 별도로 seeded random XY, 모든 원본 node·cell 중심, decimated vertex에서 수직 ray를 쏘아 높이 오차를 측정합니다. 최대가 0.02 m를 넘거나 ray가 놓치면 목표 삼각형 수를 늘려 재시도합니다. 허용되는 decimation이 없으면 해당 tile의 원본 grid를 유지하고 `raw_fallback`으로 기록합니다. 원본 grid도 ray 검사를 통과하지 못하면 중단합니다. max/p95와 triangle count를 기록합니다. **이는 검사 위치에서의 수직 오차 한계이며 연속 표면 전체의 Hausdorff 오차 증명은 아닙니다.**

Nav2는 모든 non-ground의 높이를 z=0 대신 최종 heightfield와 비교해 기본 0.1–1.0 m인 점만 occupied로 만듭니다. 8방향 한 cell 팽창 후 occupied=0, measured ground=254, 미측정=205입니다. 사용자가 선택한 10 cm 하한으로, heightfield보다 15 cm 높은 non-ground curb도 occupied에 포함합니다. 합성 시험은 저장소의 기본 설정으로 이 동작을 확인하고 5 cm 점은 제외되는지 검사합니다. 지형에 이미 들어간 curb는 상대 높이가 줄므로 지도에서 장애물로 남는다는 보장이 없습니다.

## Isaac 단계의 RAM과 진행 표시

2026-10-26에 정식 5 cm heightfield가 3,046×3,284 sample, 약 2천만 삼각형이 되는 것을 확인했습니다. 전체 mesh를 한 번에 QEM에 넣던 구현은 큰 인접 자료구조를 만들고 오랜 시간 진행 표시 없이 CPU를 사용했습니다. CPU가 계속 움직이는 상태와 OOM으로 종료된 상태는 구분해야 합니다.

현재 `processing.isaac.tile_cells` 기본값은 256이며 16–512 범위에서 설정합니다. QEM과 ray scene은 tile 하나씩 만들므로 기본값에서 한 번에 원본 삼각형 131,072개까지만 처리합니다. sample 해상도는 5 cm 그대로 유지합니다. 최종 mesh 조립·OBJ·USD 저장의 메모리는 결과 크기에 비례하므로 전체 RAM 사용이 고정되는 것은 아닙니다.

QEM의 boundary weight만으로 경계를 고정했다고 가정하지 않습니다. 각 tile의 경계를 원본 grid node로 되돌리고 긴 boundary edge를 분할한 뒤 오차를 다시 검사합니다. 공유 경계의 모든 node와 z를 보존하고 정확히 같은 좌표끼리 weld하므로 tile 사이 T-junction을 방지합니다. 출력 USD는 여전히 Mesh prim 하나입니다. 합성 시험에서 seam에 내부 boundary가 없는지와 weld 후 전체 ray 오차를 따로 확인합니다.

로그는 tile 번호, QEM 시도·목표 삼각형 수, ray 검사 결과, weld, OBJ·USD 저장을 표시합니다. `mesh_report.yaml`에는 tile별 시도와 원본 유지 여부, 전체 probe 최대 오차, tile 면적에 따라 나눈 random probe 전체의 p95가 들어갑니다.

현재 코드와 ground·분류 설정으로 heightfield 단계까지 끝났다면 이전 실행을 종료한 뒤 아래처럼 **새 출력 폴더**로 이어갑니다. raw 입력은 다시 읽지 않습니다. 기본적으로 `mujoco isaac map2d handoff check`만 실행합니다. 예전 최소 높이 filter 결과는 새 ground 설정과 호환되지 않으므로 재사용하지 않습니다.

```bash
OLD_OUT="../PAIR360_demo/2026-10-26_v1"
OUT="../PAIR360_demo/2026-10-26_v1_tiled"
uv run python tools/map/pair360_demo.py \
  --config sim_scenes/pair360_parking/frame.yaml \
  --reuse-heightfield-from "$OLD_OUT" \
  --out "$OUT"
```

`--reuse-heightfield-from`은 원본 manifest와 effective config를 확인하고, transform부터 heightfield까지 모든 파일의 SHA256을 검사한 뒤 독립 사본을 만듭니다. frame·clean·ground·분류·heightfield 설정이 다르면 거부합니다. simulator·2D map·handoff 설정은 새 결과에 적용할 수 있습니다. quick 결과는 `--quick`을 함께 전달해야 합니다. 원본 설정·코드 hash는 `reused_heightfield.yaml`, `reused_source_config.yaml` 및 새 manifest에 남겨 가져온 결과와 새로 계산한 결과를 구분합니다. 일반 실행의 config/code hash 검사는 그대로 유지합니다.

## simulator에서 확인

MuJoCo는 robot venv에서 엽니다.

```bash
uv run python -m mujoco.viewer --mjcf="$OUT/terrain.xml"
```

Isaac Lab에서는 호스트 출력이 `/data/pair360/parking_demo`에 연결된 `hn:sim` 안에서 다음 설정을 씁니다. 도구는 Isaac Sim을 실행하지 않습니다.

```python
from isaaclab.terrains import TerrainImporterCfg

terrain = TerrainImporterCfg(
    prim_path="/World/ground",
    terrain_type="usd",
    usd_path="/data/pair360/parking_demo/terrain.usd",
)
```

USD는 `metersPerUnit=1`, `upAxis=Z`, Mesh prim 하나, `UsdPhysics.CollisionAPI`와 `MeshCollisionAPI(approximation="none")`를 가지며 rigid body는 없습니다. Isaac Lab height scanner가 읽을 정적 mesh 하나입니다. 참조 변환 경로는 `hn:sim`의 Isaac Lab `scripts/tools/convert_mesh.py`이며 collision approximation은 `none`으로 지정합니다. 실제 converter 옵션과 physics 동작은 해당 컨테이너에서 확인합니다.

두 simulator에서 원점, bump·경사·curb 같은 동일 marker의 x/y/z를 비교합니다. MuJoCo는 임시 80×80 m walk box만 담으므로 비교점이 그 안에 있어야 합니다.

## 빠른 시험과 한계

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest tools/map/tests -q
```

합성 점군으로 2° 수평화, 알려진 원점, 10% 경사·15 cm curb, 차량 분류와 높은 물체의 `other` 포함, 2 cm 높이, MuJoCo quadrant, mesh 감소·오차, Nav2 방향·상대 높이, USD collision, pose 구간, 개별 단계·오래된 결과 거부를 확인합니다. 두 방향 경사와 낮은 outlier, 지면보다 조밀한 평행 지붕과 rank 1 선택, 지붕 아래 measured mask, 회전 차량과 측면 없는 판도 검사합니다. 원본 시험은 `--quick` 한 번만 수행합니다. 정식 해상도 처리, viewer, Isaac load는 사용자가 확인합니다.

T1S0 지도에는 반복 주행으로 0.3–0.6 m 이중 지면이 있습니다. 후보 두 개와 주변 연속성으로 선택을 도울 수 있지만 원본 정합 오차나 이중 지면을 해결하는 것은 아닙니다. 신뢰 가능한 ground와 연결되지 않은 지면은 미확정으로 남을 수 있습니다. 계단·급격한 단차·심한 곡률, 세 개 이상의 층도 별도 처리가 필요합니다. 붙어 있는 차의 지붕이 한 patch로 합쳐지거나 한쪽 면만 보여 크기를 충족하지 못하면 차량을 놓칠 수 있습니다. `ground.ply`, `cars.ply`, `other.ply`의 의미 정확도는 CloudCompare에서 확인해야 합니다.

Heightfield는 overhang·터널·수직 벽을 표현하지 못합니다. 미측정 구간의 지형 보간은 주행 가능 판정이 아니며 Nav2에서는 unknown을 유지합니다. QEM은 얇은 구조와 경계를 바꿀 수 있고 검사점 사이의 오차는 남을 수 있습니다. full resolution은 점수·grid 크기에 따라 메모리와 시간이 크게 늘어납니다.

Pose 선택은 원본 map XY AABB 포함 판정이고 crop의 실제 다각형 판정은 아닙니다. 시각은 원본 Unix 초를 유지하며 TUM quaternion은 최종 회전까지 적용한 LiDAR 자세입니다. 연속 sample이 crop 밖으로 나가거나 2초 넘게 끊기면 구간을 나눕니다. T3는 다른 frame이라 포함하지 않습니다.
