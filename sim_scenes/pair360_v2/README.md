# PAIR360 지도 v2

2026-11-26 기준입니다. 지도 v2는 PAIR360 `pc_v1`(7,751,328점)과 2026-11-15 팀 촬영 점군(2,119,206점)을 합친 첫 병합본입니다(2026-11-16). 겹치는 곳은 **`pc_v1`을 우선**했고 0.08 m 복셀로 줄였습니다. 11-15 촬영본만으로 만든 지도는 아닙니다. v3는 반대로 11-15 촬영본을 우선합니다. 좌표계는 `pair360_map`(m, z 위쪽)입니다.

## 파일 위치

점군·메시는 Git에 넣지 않습니다.

| Drive `14. AI Team/` | 파일 | 내용 |
| --- | --- | --- |
| `data/map_v2/` | `map_v2.pcd`, `map_v2_ground.pcd`, `map_v2_obstacle.pcd`, `map_v2_removed_dynamic.pcd`, `manifest.json` | 정적 지도 5,430,210점(지면 850,600, 장애물 4,579,610)과 지운 차량·일시 물체 |
| `meshes/mesh_v2/` | `mesh_v2_ground.ply`, `mesh_v2_obstacle.ply`, `mesh_v2_trees.ply`, `manifest.json` | v9 지면에 11-15 촬영본 지면 보정을 더한 지형, 이동 금지 블록, 경로 주변 나무 |

만든 코드는 [`tools/map/1116_pair360_v2/`](../../tools/map/1116_pair360_v2/README.md)(기록용, 저장소에서 다시 실행하지 않음)입니다.

## 한계

- 정합은 5 m 칸 높이 보정까지만 했고, 정합 오차가 큰 칸의 11-15 촬영본 점은 버렸습니다(`manifest.json`의 `registration_tiles_dropped`).
- v3에서 고친 문제(차량 잔여, 경로 주변 물체, 메시 범위)는 반영돼 있지 않습니다.
