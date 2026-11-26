# PAIR360 지도 v2 도구 (2026-11-16, 기록용)

2026-11-26 기준입니다. 지도 v2는 PAIR360 `pc_v1`과 2026-11-15 팀 촬영 점군을 합친 첫 병합본입니다. **겹치는 곳은 `pc_v1`을 우선했습니다**(v3는 반대로 11-15 촬영본 우선). 11-15 촬영본만으로 만든 지도는 아닙니다. 결과 파일은 Git에 넣지 않고 팀 Drive `14. AI Team/data/map_v2/`, `meshes/mesh_v2/`에 둡니다. 장면 설명은 [`sim_scenes/pair360_v2/`](../../../sim_scenes/pair360_v2/README.md)에 있습니다.

이 코드는 v3(`../1124_pair360_v3/`)로 대체됐습니다. v2 결과물이 어떻게 나왔는지 남기려고 2026-11-16 코드를 고치지 않고 옮겼습니다(개인 경로가 든 사용 예 한 줄만 바꿨습니다). 당시 폴더 배치(`map-release/`)를 기준으로 경로가 적혀 있어 **이 저장소 배치에서는 그대로 실행되지 않으며, 저장소에서 다시 실행해 확인하지 않았습니다.** 다시 돌리려면 경로 수정만으로는 부족합니다. map_v2의 입력은 pc_v1과 11-15 촬영본 두 개이고 둘 다 Drive `data/raw/`에 있습니다(`manifest.json`). 하지만 코드가 당시 폴더의 중간 결과와 등록 시험용 11-11 촬영본 경로를 함께 읽고, 그 중간 결과를 만든 코드가 여기 없습니다. 결과물은 Drive `data/map_v2/`, `meshes/mesh_v2/`에 보존했습니다. 폴더 날짜 1116은 코드를 처음 만든 날입니다(저장소에는 2026-11-26에 들어옴).

## 파일

| 파일 | 하는 일 | 당시 출력 |
| --- | --- | --- |
| `classify.py` | 세 점군을 점마다 지면·줄기·잎·구조물·차량·잡음으로 분류 | `classification/<pc>_merged_labels.npy` |
| `register_maps.py` | 내려받은 점군 두 개를 S-004 지면(`pc_v1`)에 정합 | `output/frame.json`, `registration_*.json` |
| `separate_ground.py` | S-004 실측 지면에, S-004가 못 본 곳만 다른 촬영본 지면을 5 m 칸 높이 보정 후 더함 | `output/map_v1_ground.pcd` |
| `build_map_v2.py` | 병합 지도(지면·장애물, 차량·일시 물체 제거, 0.08 m 복셀, `pc_v1` 행 우선) | `map_v2/pc/map_v2*.pcd`, `manifest.json` |
| `build_mesh_v2.py` | v9 지면 + 11-15 촬영본 지면 보정, 이동 금지 heightfield, 경로 주변 나무로 MuJoCo 장면과 PLY | `mesh_v2/` |
| `make_cc_view.py` | CloudCompare 확인 폴더 | `cc_view/` |

`build_mesh_v2.py`는 당시 `terrain/`의 `trees.py`, `load_go2.py`, `export_preview.py`를 불렀습니다. 그 파일들은 mesh_v1과 함께 [`../1109_pair360_v1/mesh_v1/`](../1109_pair360_v1/mesh_v1/)에 있습니다.

## 당시 이름

이 코드 안의 이름은 지금과 다릅니다.

| 코드 안 이름 | 지금 이름 |
| --- | --- |
| `pc_v1` | `pc_v1`(PAIR360 T1 데모 크롭) |
| `pc_v2` (`Downloads/map_preview.pcd`, 1,003,647점) | 이전 팀 촬영본. 지도 v2·v3에는 쓰지 않았습니다 |
| `pc_v3` (`input/pc_v3_20261115.pcd`, 2,119,206점) | 지금의 `pc_v2`(2026-11-15 촬영) |
| `output/map_v1_ground.pcd` | 지금의 지도 v1과 다릅니다(지면만 모은 중간 결과) |
