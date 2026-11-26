# PAIR360 데모 구역 Nav2 지도와 금지 구역

S-017 "통행 가능 영역 분리"의 Nav2 입력입니다. Nav2가 길을 찾을 때 쓰는 **정적 지도**와 **금지 구역 마스크**를 담았습니다. 기준은 S-009(Nav2 글로벌 경로, 김완준)와 같습니다. 2026-11-24 기준입니다.

<p><img src="figures/nav2_costmap_check.png" alt="Nav2 global costmap에 두 파일을 넣은 결과" width="640"></p>

그림은 Nav2(Jazzy)에 두 파일을 실제로 넣어 받은 global costmap입니다.

- **흰색**: 걸을 수 있는 도로입니다.
- **검정**: 장애물입니다. 지면 위 0.25~1.0 m에 점이 있는 칸입니다.
- **주황**: 장애물 주변 여유(inflation 0.35 m)입니다.
- **빨강**: 도로 밖(keepout)입니다.
- **회청색**: 지도 밖입니다.
- **파란 선**: 11-15 녹화 경로입니다. 데모 출발점은 녹화 출발점 (−48.46, 119.61)이고, 목표는 (21.9, 184.4)입니다.

## 파일

| 파일 | 쓰는 곳 | 값 |
| --- | --- | --- |
| `map.yaml`, `map.png` | `map_server` → costmap `static_layer` | 254 걸을 수 있는 땅, 0 장애물(지면 위 0.25~1.0 m), 205 지도 밖 |
| `keepout_mask.yaml`, `keepout_mask.png` | `filter_mask_server` → `KeepoutFilter` | 0 도로 밖과 지도 밖 전체, 254 도로 |
| `road_s009.png` | `keepout_mask` 생성 입력 | S-009 그림의 통행 도로를 0.1 m 격자로 옮긴 것. 255 도로, 0 도로 밖 |
| `nav2_params.example.yaml` | Nav2 설정 예 | map_server, KeepoutFilter, global costmap |
| `figures/` | 확인 그림 | `nav2_costmap_check.png`, 입력 미리보기 `preview.png` |

- **좌표**: 지도 좌표계(`pair360_map`, PAIR360 지도 v1·v2·v3 공통, m, z 위쪽)입니다. 0.1 m 격자, 1611 × 1616칸이며 원점(왼쪽 아래 모서리)은 (−82.55, 63.45)입니다.
- **걸을 수 있는 면적**: 3,244 m²입니다(도로 3,391 m²에서 장애물 칸을 뺀 값).
- **형식**: 이미지는 무손실 PNG입니다.

## 기준

S-009 Notion 페이지의 기준을 따랐습니다.

- **장애물**: map_v3 정적 점 중 7단계 지면보다 0.25~1.0 m 높은 점이 하나라도 있는 0.1 m 칸입니다. 연석·화단 같은 사람이 그린 수정은 넣지 않았습니다.
- **도로 밖(keepout)**: S-009 그림 "통행 도로와 통행불가 구역(실기용)"(김완준, 2026-11-23)에서 칠한 도로만 남기고 나머지를 막았습니다. 그 그림에는 도로 가장자리 여유 0.4 m가 이미 통행불가로 칠해져 있습니다.
- `road_s009.png`는 그 그림(1200 × 1320 px)을 `tools/map/1124_pair360_v3/road_from_figure.py`로 지도 격자에 옮긴 것입니다.

11-15 녹화 경로 6,170점은 모두 도로 안에 있습니다. 0.5%(29점)는 도로 가장자리 장애물 칸(화단 가지, 경사로 연석 모서리)에 걸칩니다.

## Nav2에 넣을 때 주의할 점

1. **올리는 순서**: 금지 구역 마스크가 비용지도보다 늦게 도착하면 첫 전체 갱신에서 빠지고, 금지 구역이 일부(시험에서 7%)만 반영됩니다. `filter_mask_server`·`costmap_filter_info_server` → costmap → `map_server` 순서로 올리면 100% 반영됩니다.
2. **`free_thresh: 0.1`**: map_server는 205를 점유 확률 (255 − 205) / 255 = 0.196으로 읽습니다. 흔히 쓰는 0.25로 두면 지도 밖이 "빈 땅"이 됩니다.
3. **지도 밖도 마스크에 넣은 이유**: 시험한 순서에서는 static layer가 지도 밖 칸을 비용 0으로 남겼습니다. 경로 계획기는 기본 설정에서 "모름" 칸을 지나갈 수 있으므로 마스크로 막았습니다.
4. **`map_topic: /map`은 절대 이름으로**: costmap이 네임스페이스 안에 있으면 상대 이름 `map`이 `/global_costmap/map`이 되어 지도를 받지 못합니다.
5. **노드 이름 충돌**: 같은 네트워크에서 다른 Nav2(예: RViz 확인용 컨테이너)가 같은 노드 이름으로 돌고 있으면 lifecycle 전환이 실패합니다. 이때는 `ROS_DOMAIN_ID`를 다르게 줍니다.

## 확인 방법

팀 ROS 컨테이너(`./docker/hn ros`) 안에서 실행합니다.

```bash
sudo apt-get update && sudo apt-get install -y ros-jazzy-nav2-map-server ros-jazzy-nav2-costmap-2d ros-jazzy-nav2-lifecycle-manager
tools/map/1124_check_nav2_keepout.sh sim_scenes/pair360_nav2
```

팀 ROS 이미지에는 아직 Nav2가 없어 첫 줄로 한 번 설치합니다. 없으면 스크립트가 이 설치 명령을 알려 주고 끝납니다. 스크립트는 위 순서대로 노드를 띄우고, 각 노드가 lifecycle `active`가 된 것을 확인한 뒤 다음 노드로 넘어갑니다. 그다음 비용지도에서 도로 밖과 지도 밖이 모두 통행 불가인지 검사합니다. `--save <폴더>`를 주면 세 격자를 `nav2_grids.npz`로 저장합니다.

2026-11-24 결과는 다음과 같습니다.

- 도로 밖과 지도 밖: 100% 통행 불가
- 걸을 수 있는 칸: 88%가 비용 0(나머지는 장애물 주변 여유)

이 검사는 비용지도가 맞게 만들어지는지만 봅니다. 경로 계획과 실기 주행은 확인하지 않았으며, G-009(sim–Nav2 연결)에서 다룹니다.

## 출처와 생성

- **입력**: PAIR360 T1 주차장 점군(v1, Kim et al., *PAIR360*, IEEE RA-L 2024, ODbL 1.0), 팀 FAST-LIO 촬영 점군(v2, 2026-11-15), 둘을 합친 map_v3와 지면 격자(mesh_v3 7단계), S-009 그림의 통행 도로입니다.
- **생성**: [`tools/map/1124_build_pair360_v3.sh`](../../tools/map/1124_build_pair360_v3.sh)의 11단계(`tools/map/1124_pair360_v3/s11_nav2.py`)입니다. 입력과 단계 설명은 [`../pair360_v3_decisions/README.md`](../pair360_v3_decisions/README.md)에 있습니다.

  ```bash
  tools/map/1124_build_pair360_v3.sh --data <입력 폴더> --out <결과 폴더>   # 결과: <결과 폴더>/nav2_v3/
  ```

- **라이선스**: 지도 이미지는 PAIR360(ODbL 1.0)에서 파생한 데이터입니다. 공유할 때 원저자·논문·변경 내용을 함께 밝힙니다. 설정 파일과 도구는 Apache-2.0, 이 문서는 CC BY 4.0입니다.

## 한계

- Nav2 경로 계획과 실기 주행은 확인하지 않았습니다(G-009).
