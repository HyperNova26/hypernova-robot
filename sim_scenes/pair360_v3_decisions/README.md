# PAIR360 map_v3·mesh_v3 사람이 정한 입력

2026-11-24 기준입니다. [`tools/map/1124_build_pair360_v3.sh`](../../tools/map/1124_build_pair360_v3.sh)가 점군 두 개로 지도와 지형을 만들 때, 자동으로 정할 수 없어 사람이 정한 값을 모았습니다. 좌표는 모두 지도 좌표계(`pair360_map`, PAIR360 T1 원시 XYZ, m, z 위쪽)입니다.

## 파일

| 파일 | 내용 | 정한 사람 |
| --- | --- | --- |
| `demo_route.json` | mesh_v3 참조 경로(지형 확인용)의 출발점·경유점·목표 | 장승민. 출발점은 2026-11-18 확인, 목표는 촬영 화면으로 추정(±3~5 m) |
| `route_review.json` | 자동 단계가 남긴 차량·버스·보행자 등 지울 물체 45개 | 후보는 Claude가 위·옆 화면으로 골랐고, 전부 장승민이 검토했습니다 |
| `terrain_edits.json` | 연석 3줄, 지도 범위에서 잘라낼 곳, 주차장 화단, 잘못 잡힌 나무·작은 장애물 수정 | 점군 단면을 보고 정했고, 2026-11-17~18에 장승민이 CloudCompare 묶음과 스케치로 확인했습니다 |

pc_v1 지면 검토(차량 32대, 제외 구역, 도로 복원, S-004 2026-11-09)는 지도 v1의 입력이라 [`tools/map/1109_s004_ground/continuous_ground_20261109_v9.json`](../../tools/map/1109_s004_ground/continuous_ground_20261109_v9.json)에 둡니다. 2단계가 이 파일을 읽습니다.

Nav2 지도의 장애물은 map_v3 점 높이(7단계 지면 위 0.25~1.0 m)로, 도로는 S-009 도로로 정합니다([`../pair360_nav2/`](../pair360_nav2/README.md)). `terrain_edits.json`의 이동 금지 영역은 Nav2 지도에 들어가지 않지만, 연석 턱과 지도 범위는 7단계 지면에 들어가 두 지도 모두에 영향을 줍니다.

`demo_route.json`은 mesh_v3의 참조 경로(9단계 기립 확인)에만 씁니다. Nav2 데모 출발점은 11-15 녹화 출발점 (−48.46, 119.61)입니다([`../pair360_nav2/`](../pair360_nav2/README.md)).

## 만드는 방법

팀 컨테이너(`./docker/hn ros` 또는 `./docker/hn sim`) 안에서 실행합니다. 필요한 Python 패키지(numpy, scipy, matplotlib, mujoco, Pillow)는 이미 `pyproject.toml`에 있습니다.

```bash
tools/map/1124_build_pair360_v3.sh --data <입력 폴더> --out <결과 폴더>
```

`--data` 폴더는 Git에 올리지 않습니다. 다음 구조여야 합니다.

| 경로 | 내용 |
| --- | --- |
| `raw/pc_v1_pair360_t1_parking_demo.ply` | PAIR360 T1_parking_Seq0 데모 크롭(7,751,328점, ODbL 1.0) |
| `raw/pc_v2_20261115.pcd` | 팀 촬영 점군(2026-11-15, 2,119,206점) |
| `reviewed/pc_v1_ground_v1/ground_surface.npz` | pc_v1 지면 v1 격자(`tools/map/1109_s004_ground/`의 v9 결과) |
| `reviewed/pc_v1_ground_v1_partition/ground.ply` | pc_v1 지면 v1 분할(원본 점 중 위 격자에서 0.15 m 안) |
| `models/unitree_go2/go2.xml` | MuJoCo Menagerie Go2(9단계 기립 확인용) |

단계는 `tools/map/1124_pair360_v3/`의 `s01`~`s11`입니다. `--steps`로 일부만 다시 돌릴 수 있습니다. 10단계(CloudCompare 확인 묶음)는 CloudCompare가 있어야 해서 `--cloudcompare`를 줄 때만 실행합니다.

| 단계 | 하는 일 | 결과(`--out` 아래) |
| --- | --- | --- |
| 1 | 두 점군 확인 | `map_v3/work/01_inputs.json` |
| 2 | 점마다 지면·장애물·차량·잡음 분류 | `map_v3/work/02_*` |
| 3~4 | `pc_v2`를 `pc_v1`에 정합하고 구간별 미세 보정 | `map_v3/work/03_*`, `04_*` |
| 5 | 한쪽 촬영에만 있는 사람·물체 제거 | `map_v3/work/05_*` |
| 6 | 병합(`pc_v2` 우선) | `map_v3/map_v3*.pcd` |
| 7 | 0.1 m 지면 높이 격자 | `mesh_v3/ground_surface.npz` |
| 8 | 이동 금지 칸, 나무, MuJoCo 장면 | `mesh_v3/mujoco/` |
| 9 | MuJoCo 경로 막힘·Go2 기립 확인 | `mesh_v3/mujoco/verification.json` |
| 11 | Nav2 지도(장애물 0.25~1.0 m)와 도로 밖 마스크(S-009 도로) | `nav2_v3/` |

## 한계

- 보행 제어기로 걷는 시험은 하지 않았습니다. 9단계는 경로 위 기립만 확인합니다.
- 라이선스: 이 폴더의 JSON은 CC BY 4.0입니다. 결과물은 PAIR360(ODbL 1.0) 파생 데이터입니다.
