# PAIR360 지도 v3

2026-11-26 기준입니다. 지도 v3는 PAIR360 `pc_v1`과 2026-11-15 팀 촬영 점군(`pc_v2`)을 합친 지도입니다. 겹치는 곳은 더 정밀한 `pc_v2`를 우선합니다. 좌표계는 `pair360_map`(m, z 위쪽)입니다. 코드는 [`tools/map/1124_pair360_v3/`](../../tools/map/1124_pair360_v3/)에 있습니다.

| 폴더 | 내용 |
| --- | --- |
| [`decisions/`](decisions/README.md) | map_v3·mesh_v3를 만들 때 사람이 정한 입력(참조 경로, 지울 물체, 지형 수정)과 실행 방법 |
| [`nav2/`](nav2/README.md) | S-017 Nav2 정적 지도, 도로 밖 금지 구역 마스크, Nav2 설정 예, 확인 그림 |

점군·메시는 Git에 넣지 않고 팀 Drive `14. AI Team/data/map_v3/`(map_v3 점군 4개)와 `meshes/mesh_v3/`(mesh_v3 PLY, MuJoCo 묶음)에 둡니다.

## 통행 불가 영역

| 종류 | 기준 | 어디에 |
| --- | --- | --- |
| 지형상 불가(Nav2 `map.png`의 0) | map_v3 정적 점 중 7단계 지면 위 0.25~1.0 m 점이 있는 0.1 m 칸 | `nav2/map.png`, 11단계 `s11_nav2.py` |
| 지정 통행 불가(Nav2 `keepout_mask.png`의 0) | S-009 그림의 도로 밖(여유 0.4 m 포함)과 지도 밖 전체 | `nav2/keepout_mask.png`, 입력 `nav2/road_s009.png` |
| MuJoCo 이동 금지 | 지면 위 0.15~0.5 m 점, 0.5 m 안 0.2 m 넘는 높이차, 화단·연석 손 편집 → heightfield +0.8 m | mesh_v3 장면, 8단계 `s08_mesh.py`. Nav2 지도에는 들어가지 않습니다 |
