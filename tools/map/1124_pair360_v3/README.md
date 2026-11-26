# PAIR360 지도 v3 도구

2026-11-26 기준입니다. 지도 v3는 PAIR360 T1 데모 점군(`pc_v1`)과 팀 촬영본(`pc_v2`, 2026-11-15)을 `pc_v2` 우선으로 합친 지도(map_v3), MuJoCo 지형(mesh_v3), Nav2 지도입니다. 좌표계는 `pair360_map`(PAIR360 원시 XYZ, m, z 위쪽)입니다. 결과 파일은 Git에 넣지 않고 팀 Drive `14. AI Team/data/map_v3/`, `meshes/mesh_v3/`에 둡니다. Nav2 지도는 [`sim_scenes/pair360_v3/nav2/`](../../../sim_scenes/pair360_v3/nav2/README.md)에 있습니다.

## 입력 준비

`--data` 폴더(Git 밖)를 아래 구조로 만듭니다. 실행기는 시작할 때 이 파일들이 있는지 검사합니다.

| 경로 | 내용 | 구하는 곳 |
| --- | --- | --- |
| `raw/pc_v1_pair360_t1_parking_demo.ply` | PAIR360 T1_parking_Seq0 데모 크롭, 7,751,328점, ODbL 1.0 | PAIR360 공개 데이터 데모 크롭. SHA-256 `d4304a35…34fbb3` |
| `raw/pc_v2_20261115.pcd` | 팀 FAST-LIO 촬영본(2026-11-15), 2,119,206점 | 촬영 원본. SHA-256 `9b289e14…7fecf42` |
| `reviewed/pc_v1_ground_v1/ground_surface.npz` | pc_v1 지면 v1(S-004 v9) 0.1 m 격자 | [`1109_pair360_v1/reproduce_s004_final.py --ground v9 --out <폴더>`](../1109_pair360_v1/README.md)의 `<폴더>/v9/ground_surface.npz` |
| `reviewed/pc_v1_ground_v1_partition/ground.ply` | 원본 점 중 위 격자에서 0.15 m 안(`original_index` 포함) | 같은 실행의 `<폴더>/pointcloud/ground.ply` |
| `models/unitree_go2/go2.xml` | Go2 모델(9단계 기립 확인용) | [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie)의 `unitree_go2/` 폴더 |

사람이 정한 입력(참조 경로, 지울 물체, 지형 수정)은 Git의 [`sim_scenes/pair360_v3/decisions/`](../../../sim_scenes/pair360_v3/decisions/README.md)에 있고, pc_v1 지면 판단은 [`../1109_pair360_v1/continuous_ground_20261109_v9.json`](../1109_pair360_v1/continuous_ground_20261109_v9.json)을 읽습니다. Nav2 도로 마스크는 `sim_scenes/pair360_v3/nav2/road_s009.png`입니다.

## 실행 순서

팀 컨테이너(`./docker/hn ros` 또는 `./docker/hn sim`) 안, 저장소 최상위에서 실행합니다.

```bash
# 1. pc_v1 지면 v1 만들기(입력의 reviewed/ 두 파일)
uv run python tools/map/1109_pair360_v1/reproduce_s004_final.py --ground v9 --out /tmp/pair360-v1

# 2. map_v3, mesh_v3, Nav2 지도(1~9, 11단계)
tools/map/1124_pair360_v3/build_pair360_v3.sh --data <입력 폴더> --out <결과 폴더>

# 3. Nav2 비용지도에서 도로 밖이 막히는지 검사(ROS 컨테이너)
tools/map/1124_pair360_v3/check_nav2_keepout.sh --help
```

- `--steps s07_ground s08_mesh`처럼 일부 단계만 다시 돌릴 수 있습니다(앞 단계 결과가 `--out`에 있어야 함).
- 10단계(CloudCompare 확인 묶음)는 CloudCompare가 필요해서 `--cloudcompare`를 줄 때만 돕니다. 실행 파일 위치는 환경 변수 `CLOUDCOMPARE`로 지정합니다.
- 결과를 하나의 PLY로 합칠 때는 `merge_meshes.py`를 씁니다.

## 파일

| 파일 | 하는 일 |
| --- | --- |
| `build_pair360_v3.sh`, `build_pair360_v3.py` | Python 환경을 고르고 단계를 차례로 실행합니다 |
| `s01_inputs.py` | 두 점군 확인 |
| `s02_dynamic.py`, `check_vehicles.py` | 점마다 지면·장애물·차량·잡음 분류, 차량 점검 |
| `s03_register.py`, `s04_local_fit.py` | `pc_v2`를 `pc_v1`에 정합하고 구간별 미세 보정 |
| `s05_change.py` | 한쪽 촬영에만 있는 사람·물체 제거 |
| `s06_merge.py` | `pc_v2` 우선 병합 → `map_v3*.pcd` |
| `s07_ground.py` | 0.1 m 지면 높이 격자 |
| `s08_mesh.py`, `trees.py`, `shapes.py` | 이동 금지 칸, 나무, MuJoCo 장면 |
| `s09_verify.py`, `load_go2.py`, `route_stand_check.py` | 경로 막힘과 Go2 기립 확인 |
| `s10_bundle.py` | CloudCompare 확인 묶음 |
| `s11_nav2.py`, `road_from_figure.py` | Nav2 정적 지도와 도로 밖 마스크(S-009 그림) |
| `check_nav2_keepout.sh`, `check_nav2_keepout.py` | Nav2를 띄워 금지 구역이 비용지도에서 막히는지 검사 |
| `merge_meshes.py` | mesh_v3 PLY를 `mesh_v3_all.ply` 하나로 합침 |
| `config.py`, `pcio.py`, `frames.py`, `edits.py`, `features.py` | 경로·공용 값, 점군 읽기·쓰기, 좌표 변환, 수정 적용, 특징 계산 |

단계별 결과 경로는 [`decisions/README.md`](../../../sim_scenes/pair360_v3/decisions/README.md#만드는-방법)에 있습니다.

## 한계

- 2026-11-24에 1~9·11단계를 다시 돌려 결과가 같았습니다. 2026-11-26 폴더 이름을 바꾼 뒤에는 전체를 다시 돌리지 않았습니다.
- 두 원시 점군(`raw/`)은 2026-11-26 기준 팀 Drive에 없습니다.
