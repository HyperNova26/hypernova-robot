# PAIR360 mesh_v3 지형

2026-11-19 기준입니다. 지형 팀이 2026-11-18에 전달한 MuJoCo용 PAIR360 장면(`PAIR360-Go2-MuJoCo_mesh_v3.zip`)과, 이것을 MuJoCo, Isaac Sim, Isaac Lab이 같이 쓰도록 바꾸는 방법을 적습니다. 원본과 생성 파일은 Git에 올리지 않습니다(데이터 폴더 `~/hypernova-data/pair360_map_v3/`). 이 폴더에는 문서, 경로 파일, 해시만 있습니다.

## 좌표

`pair360_map`(PAIR360 T1 원시 XYZ, m, Z-up)을 **변환 없이** 씁니다. 팀 공통 원점(M-002)은 적용 전입니다. 이유와 대안은 [ADR-0005](../../docs/decisions/0005-pair360-map-frame.md)(Proposed)에 있습니다.

## 받은 것

| 항목 | 내용 |
| --- | --- |
| 지면 hfield | `pair360_ground_000`, group 0. 1616행 × 1611열, 간격 0.1 m, x −82.5 ~ 78.5, y 63.5 ~ 225.0, z −1.74 ~ 14.58 |
| 이동 금지 hfield | `pair360_nogo_000`, group 4. 같은 격자. 장애물 자리를 지면보다 약 0.8 m 높이고, 그 밖에는 지면보다 0.05 m 아래에 있어 보이지 않음 |
| 나무 | 줄기 54개(원기둥)와 밑동 54개(타원체)는 충돌(group 2), 수관 198개는 광선 전용(group 3, `contype 0`) |
| `manifest.json` | 시작 (−16.7, 123.4) yaw 87.1°, 목표 (21.9, 184.4), 경유점 2개, 참조 경로 `route_xyz_m` |

전달 zip의 sha256은 `8dd62a6d4dee756dbbc2db0beacd315ed1444e978f62d3c2bb5d69fe3c087027`이고 파일별 해시는 [`checksums.json`](checksums.json)에 있습니다. `scene.xml`의 해시는 지형 팀의 `verification.json`에 적힌 값과 같습니다.

지형 팀 README가 적은 한계입니다. 보행 제어기로 걷는 시험은 하지 않았고(기립만 확인), 목표는 촬영 화면과 측정 흔적으로 추정한 값(±3~5 m)입니다. 지형은 두 점군이 덮는 범위만 있고 가장자리에 보이지 않는 이동 금지 벽이 있습니다. `manifest.json`이 나열한 PLY 3개는 zip에 들어 있지 않고 2026-11-19에 따로 받았습니다([PLY 비교](#지형-팀-ply와-비교)).

## 만든 것

[`tools/map/hfield_scene_import.py`](../../tools/map/hfield_scene_import.py)가 hfield에서 세 시뮬레이터용 입력을 만듭니다. MuJoCo는 받은 `scene.xml`을 그대로 씁니다.

| 파일 | 내용 |
| --- | --- |
| `ground_grid.npz` | 지면 높이 격자(전체). 재생기가 시작 높이와 Isaac Sim의 height scan에 씁니다 |
| `isaac/terrain_ground.usdc` | 지면 삼각형 메시 250만 개(경로 둘레 30 m). 충돌과 height scan ray가 맞는 면, 마찰 1.0(기존 데모 지형 USD와 같음) |
| `isaac/terrain_obstacles.usdc` | 이동 금지 장애물 메시와 나무 줄기·밑동 108개. 충돌만 하고 height scan에는 보이지 않습니다(MuJoCo의 height scan이 group 0만 보는 것과 같음) |
| `isaac/scene_v0.usda`, `scene_v1.usda` | Isaac Sim 장면(지형 둘 + 로봇 참조) |
| `report.json` | 입력·출력 해시, 크기, 검증 결과, 실행 인자 |

만드는 명령(컨테이너, 출력 폴더가 이미 있으면 거부합니다):

```bash
./docker/hn sim /opt/hn-venv/bin/python /workspace/hypernova/tools/map/hfield_scene_import.py \
  --scene /data/pair360_map_v3/src/PAIR360-Go2-mesh_v3/scene/scene.xml --out /data/pair360_map_v3/derived \
  --robot-usd v0=/data/usd/hn_v0_go2/hypernova_go2_1/hypernova_go2.usda \
  --robot-usd v1=/data/usd/hn_v1_hyper/hypernova_hyper/hypernova_hyper.usda \
  --route-yaml /workspace/hypernova/sim_scenes/pair360_map_v3/routes.yaml
```

`routes.yaml`은 이 도구가 `manifest.json`에서 만든 파일이라 손으로 고치지 않습니다. 경로 `A`는 지형 팀이 막힘 없음을 확인한 참조 경로(`route_xyz_m`)이고, 도구가 지면·이동 금지·나무 줄기와의 거리를 다시 점검해 0.3 m 이상 떨어진 경로만 씁니다. manifest의 시작 → 경유점 → 목표 직선(`via`)은 나무 줄기와 겹쳐서(−0.03 m) 쓰지 않았습니다.

## 확인한 것

2026-11-19, `hn:sim` 컨테이너(MuJoCo 3.12.0, Isaac Lab 3.0.0)에서 확인했습니다.

- MuJoCo가 hfield 셀을 나누는 대각선은 방향 A(셀의 (열, 행)과 (열+1, 행+1)을 잇는 쪽)입니다. 임의의 3000점에서 해석 높이와 MuJoCo 광선 높이의 최대 차이가 A는 2e-13 m, B는 0.36 m였습니다.
- 쓴 USD 메시를 다시 읽어 같은 종류의 3000점을 MuJoCo 광선과 비교하니 최대 3.0e-05 m, 평균 2.6e-07 m였습니다.
- 경로 A의 길이 101.08 m와 최대 경사 13.5%가 지형 팀의 `manifest.json`·`verification.json` 값과 같습니다. 이동 금지까지 최소 0.56 m, 나무 줄기까지 최소 0.88 m입니다.
- v1 로봇(HYPER v1, model_2998)이 경로 A를 세 시뮬레이터에서 넘어짐 없이 걸어 목표 0.30 m 안에 도착했습니다(창 없음, 단일 실행).

| 시뮬레이터 | 보정 전 | 보정 후(기본값) | 비고 |
| --- | --- | --- | --- |
| Isaac Lab | 207.5 s | 207.5 s | 학습 환경. 같은 조건으로 두 번 돌려 같은 값. `check_env` OK, 장애물 메시 109개 모두 충돌 |
| Isaac Sim | 216.9 s | 209.8 s | 장면에 지면·이동 금지·나무 108개가 충돌 메시로 합성됨. 토크 1스텝 지연 보정 |
| MuJoCo | 225.9 s | 211.4 s | 접촉 보정 + 토크 지연 보정 |

보정 전에는 세 시뮬레이터의 지형이 같은 hfield에서 나왔는데도 도착 시간이 8.9% 벌어졌고, 구간마다 같은 비율이라 지형이 원인이 아니었습니다. 원인(Isaac Lab의 Newton 액추에이터 경로와 MuJoCo의 연한 접촉)과 보정은 [시뮬레이터 사이 보행 차이](../../docs/development/sim-parity.md)에 있습니다. 보정은 v1 정책에 맞춘 것이고 `MJ_CALIB=0 ACT_DELAY=0`으로 끌 수 있습니다.

## 지형 팀 PLY와 비교

2026-11-19에 지형 팀이 `mesh_v3_{all,ground,obstacle,route,trees}.ply` 5개를 따로 전달했습니다(데이터 폴더 `pair360_map_v3/src/ply/`, 해시는 [`checksums.json`](checksums.json)). 전부 `pair360_map` 좌표(m, Z-up)이고 `all`은 지면, 장애물, 나무를 이어 붙인 것입니다(꼭짓점 1,852,249개, 삼각형 3,661,446개, 앞 세 파일의 합과 정확히 같음). manifest의 `meshes` 숫자는 바이트가 아니라 **삼각형 개수**였습니다.

| 파일 | 확인 결과 |
| --- | --- |
| ground | 꼭짓점 1,505,580개(manifest의 scope 셀 수와 같음)가 hfield 격자 위에 정확히 놓이고, 같은 꼭짓점의 높이가 hfield와 최대 9.5e-07 m(float32 반올림)만 다릅니다. 삼각형 3,003,612개 모두 대각선 A(MuJoCo hfield가 쓰는 방향)입니다. **hfield와 같은 데이터이고 범위만 scope로 한정한 것**이라, 이 문서의 Isaac 지면 메시와 같은 지형입니다 |
| obstacle | 꼭짓점의 89.2%가 `nogo` hfield와 같습니다. 나머지 10.8%(34,063개)는 PLY가 더 낮습니다(26,410개는 정확히 0.8 m, 약 7,600개는 0~0.3 m). 장애물 경계에서 PLY는 실제 장애물 표면이고 `nogo` hfield는 그보다 조금 부풀린 차단 지도로 보입니다. 가장자리의 1.8 m 이동 금지 벽은 PLY에 없고 hfield에만 있습니다 |
| trees | 연결 성분 306개로, `scene.xml`의 줄기 54 + 밑동 54 + 수관 198과 같습니다. 줄기 54개 모두 PLY 나무 성분 중심과 0.00 m 차이입니다. `scene.xml` 도형을 삼각형으로 만든 것입니다 |
| route | 참조 경로를 따라가는 띠(꼭짓점 1064개). 처음과 끝이 시작점·목표 근처입니다 |

이 비교로 Isaac 지형을 바꿀 필요는 없었습니다. MuJoCo가 충돌에 쓰는 것은 hfield이므로 세 시뮬레이터의 충돌 지형은 hfield에서 만든 현재 방식이 맞습니다. 장애물 PLY와 `nogo` hfield의 경계 차이(부풀림)가 의도인지는 지형 팀에 확인해야 합니다. 수관 PLY는 시뮬레이터 LiDAR로 수관을 보게 할 때 쓸 수 있습니다.

## 확인하지 못한 것

- 창 모드의 화면(MuJoCo는 충돌 메시로 그려집니다). 사람 눈으로 본 확인이 없습니다.
- 나무와 이동 금지 장애물에 닿는 접촉을 세 시뮬레이터에서 비교하지 않았습니다. 경로 A는 장애물에서 0.5 m 이상 떨어져 있어 이번 실행에서는 닿지 않았을 것입니다.
- 경로 둘레 30 m 밖에는 Isaac 지형이 없습니다(MuJoCo에는 전체 hfield가 있음). 멀리 가는 시험에는 `--margin`을 늘려 다시 만듭니다.
- 수관(광선 전용)은 Isaac에 넣지 않았습니다. 시뮬레이터 LiDAR로 수관을 보려면 따로 넣어야 합니다.
- 이동 금지 메시는 hfield 꼭짓점 단위로 만든 것이라 장애물 가장자리 경사의 모양이 MuJoCo의 두 hfield 합집합과 조금 다를 수 있습니다.

## 실행

저장소 최상위에서, 컨테이너 `hn:sim`으로 실행합니다. 지도는 `MAP=v3`(기본)입니다.

```bash
./tools/demo/run_route.sh check                       # 필요한 파일 점검
HEADLESS=1 ./tools/demo/run_route.sh mujoco           # 창 없이 끝까지 걷고 결과만 출력
./tools/demo/run_route.sh isaaclab                    # 창(데스크톱 터미널에서)
POLICY=v0 ./tools/demo/run_route.sh isaacsim          # v0(Go2) 로봇으로
MAP=demo ./tools/demo/run_route.sh mujoco             # 예전 데모 지형(비교·회귀용)
```
