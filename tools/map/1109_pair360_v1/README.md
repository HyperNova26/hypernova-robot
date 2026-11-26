# PAIR360 지도 v1 도구

2026-11-26 기준입니다. 지도 v1은 PAIR360 T1 데모 점군(`pc_v1`, 7,751,328점)**만으로** 만든 지도와 지형입니다. 좌표계는 `pair360_map`(PAIR360 원시 XYZ, m, z 위쪽)입니다. 결과 파일은 Git에 넣지 않고 팀 Drive `14. AI Team/data/map_v1/`, `meshes/mesh_v1/`에 둡니다. 장면 설명은 [`sim_scenes/pair360_v1/`](../../../sim_scenes/pair360_v1/README.md)에 있습니다.

## 결과물과 만드는 코드

| 결과물 | 내용 | 코드 |
| --- | --- | --- |
| S-004 전달본(v8, 2026-11-05) | 지면 메시와 MuJoCo·Isaac 장면 | `reproduce_s004_final.py` |
| pc_v1 지면 v1(v9, 2026-11-09) | v8 입력에 수관 아래 바닥 보강을 더한 지면 표면과 지면 분할(지면 1,346,917점) | `reproduce_s004_final.py --ground v9` |
| map_v1 (`map_v1*.pcd`) | 원본 행을 v9 지면 분할로 나눈 점군. label 1 지면, 2 나머지(차량·나무·건물을 나누지 않음) | `export_map_v1_pcd.py` |
| mesh_v1 (2026-11-16) | v9 지면 heightfield + 나무·구조물, MuJoCo 장면 | `mesh_v1/` |

v9 지면은 지도 v3 2단계의 입력이기도 합니다(`continuous_ground_20261109_v9.json`).

## 파일

| 파일 | 하는 일 |
| --- | --- |
| `build_continuous_ground_v5.py` | 검토 격자와 판단 JSON으로 0.1 m 연속 지면 표면을 만듭니다. `canopy_floor` 결정은 수관 아래 칸의 바닥을 가장 낮은 점들로 다시 잡습니다 |
| `continuous_ground_20261104_v7.json`, `continuous_ground_20261109_v9.json` | 허용·제외 구역, 차량 다각형, 도로 복원, 수관 아래 바닥(v9) |
| `smooth_local_ground_v8.py` | 주차장의 고립된 돌출 후보를 국소 보정합니다 |
| `export_s004_layers.py` | 표면에서 0.15 m 안의 원본 점을 지면으로 나눕니다(`ground.ply`, `non_ground.ply`) |
| `export_final_sim.py` | v8 표면으로 MuJoCo·USD 장면을 만듭니다 |
| `reproduce_s004_final.py` | 위 단계를 차례로 실행하고 `sim_scenes/pair360_v1/checksums.json`과 해시를 대조합니다 |
| `review_cloud_io.py` | XYZI PLY 읽기, 원본 행 대응, 검토용 PLY 쓰기 |
| `export_map_v1_pcd.py` | map_v1 PCD 세 개를 씁니다. 필드는 map_v3와 같습니다(x y z intensity label source rgb) |
| `mesh_v1/` | mesh_v1을 만든 2026-11-16 코드(아래) |

## 실행

저장소 최상위에서 실행합니다. 입력은 `sim_scenes/pair360_v1/input/original.ply`와 `review/*.npz`(Git 밖)입니다.

```bash
uv run python tools/map/1109_pair360_v1/reproduce_s004_final.py --ground v9 --out /tmp/pair360-v1
uv run python tools/map/1109_pair360_v1/export_map_v1_pcd.py \
  --source sim_scenes/pair360_v1/input/original.ply --ground /tmp/pair360-v1/pointcloud/ground.ply --out /tmp/map_v1
```

2026-11-26 팀 컨테이너 `hn:ros-2026.10.1-local`에서 v8과 v9의 메시·지면 분할 해시가 기존 결과와 같았습니다. `export_map_v1_pcd.py`의 세 PCD도 Drive에 올릴 파일과 SHA-256이 같았습니다.

## mesh_v1/ (2026-11-16 코드, 기록용)

mesh_v1을 만든 코드를 고치지 않고 옮겼습니다(개인 경로가 든 사용 예 두 줄만 바꿨습니다). 당시 폴더 배치(`map-release/terrain/`)를 기준으로 경로가 적혀 있어 **이 저장소 배치에서는 그대로 실행되지 않으며, 저장소에서 다시 실행해 확인하지 않았습니다.** 다시 돌리려면 `import`할 폴더(`export_final_sim`은 `../`, `register_maps`는 `../../1116_pair360_v2/`)를 가리키는 몇 줄만 고치면 됩니다. 당시 결과를 만든 코드 그대로 남기려고 고치지 않았습니다.

| 파일 | 하는 일 |
| --- | --- |
| `build_terrain.py` | v9 지면 표면을 MuJoCo heightfield로, 기준 점군의 나무·구조물을 충돌체로 만듭니다 |
| `trees.py` | 데모 경로 주변 나무를 수관 높이로 나누고 줄기·수관 형상을 만듭니다 |
| `export_preview.py` | 장면을 `mesh_v1_ground.ply`, `mesh_v1_obstacle.ply`로 내보냅니다 |
| `audit_ground.py` | heightfield 높이를 기준 지면과 비교합니다 |
| `load_go2.py`, `verify_terrain.py`, `route_stand_check.py` | Go2를 올려 기립·광선 검사를 합니다 |
| `package_terrain.py` | 검증한 장면을 보행팀 전달 묶음으로 압축합니다 |

당시 배치에서 이 코드는 S-004의 `export_final_sim.py`, v2 도구의 `register_maps.py`(`../../1116_pair360_v2/`)를 함께 불렀습니다. mesh_v1의 바깥 지면 단계는 다른 촬영본 지면을 쓸 수 있었지만, 실제 결과는 heightfield 0개, 면 0개였습니다(`manifest.json`의 `exterior_ground`). 그래서 mesh_v1은 사실상 `pc_v1`만으로 만든 지형입니다.
