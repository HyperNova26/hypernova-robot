# ADR-0005: Policy IO schema 2 (LiDAR 기억 height map)

- 상태: **Proposed**
- 제안: 2026-11-24
- 관련: 로드맵 G-002(Policy IO 통일), `policies/urdf_v1/policy_io.yaml`, `policies/common/heightmap.py`

## 배경

정책 입출력 계약 schema 1(`policies/urdf_v0/policy_io.yaml`, 로더 `policies/route_walk/policy_io.py`)은 height map을 GT height scan(몸통 위 20 m에서 수직으로 쏜 광선)으로만 정의합니다. GT height scan은 실기에서 만들 수 없습니다.

v1 HYPER 배포용 과제 `HN-Velocity-Rough-HYPERv1-Lidar`는 actor height map을 실제 센서(SOSLAB ML-X 120)로 만듭니다. LiDAR가 맞힌 점을 칸으로 줄여 기억하고, 못 본 칸은 발끝 평면으로 채웁니다. 2026-11-19에는 actor 입력에 몸통 선속도(`base_lin_vel`)도 추가했습니다. 그래서 입력이 232차원에서 235차원으로 바뀌었고, height map을 만드는 방법과 grid 위치(앞으로 0.45 m)를 계약에 적어야 실기 쪽이 같은 입력을 만들 수 있습니다.

## 검토한 선택지

**A. schema 1 그대로 두고 차원만 고치기** — 가장 빠릅니다. 하지만 height map을 만드는 방법이 계약에 없어서, 실기 쪽에서 같은 입력을 만들 수 없습니다.

**B. LiDAR 정책용 yaml을 새로 따로 두기** — 기존 계약을 건드리지 않습니다. 대신 v1 계약 파일이 두 개가 되고, 232차원 GT 정책은 지금 과제로 돌아가지 않아 남겨 둘 이유가 적습니다.

**C. schema 2를 정의하고 v1 `policy_io.yaml`을 교체하기** — schema 1에 height map 생성 방법(`method`), grid 위치(`center_offset_m`), 입력 `base_lin_vel`을 더합니다. v1 계약 파일은 하나로 유지합니다.

## 결정

C안으로 하고, 아래를 제안합니다. 합의 전까지는 `Proposed`입니다.

| 항목 | schema 1 | schema 2 |
| --- | --- | --- |
| `schema_version` | 1 | 2 |
| actor 입력 | 232 (선속도 없음) | 235 (맨 앞에 `base_lin_vel` 3) |
| `height_scan.method` | 없음(GT 전제) | `gt_raycast` 또는 `lidar_memory` |
| `height_scan.grid.center_offset_m` | 없음(중심 = base) | `[x, y]` m, v1은 `[0.45, 0.0]` |
| `height_scan.lidar_memory` | 없음 | 센서 frame과 시야, scan 주기, 기억 시간, 칸 값 규칙, 못 본 칸 채우기 |

- v1 `policies/urdf_v1/policy_io.yaml`을 Rough-Lidar `model_4999` 계약(schema 2)으로 교체합니다.
- 232차원 Rough GT 체크포인트(`hn_hyperv1_rough_model_2998.pt`)와 그 계약은 저장소에서 지웁니다. 둘 다 커밋 `acff5c6`에 남아 있습니다.
- 로더(`policies/route_walk/`)는 이 ADR에서 바꾸지 않습니다. 담당자가 schema 2를 읽도록 따로 맞춥니다. 알려진 문제는 `apply_policy_io`가 height scanner offset을 `(0, 0, start_height)`로 덮어써서 `center_offset_m`이 사라지는 것입니다.

## 결과

- 실기 쪽은 yaml만 보고 actor 입력 235차원을 만들 수 있습니다. LiDAR 점을 world 좌표로 옮기는 몸통 자세는 추정값(IMU, 다리 기구학, LIO)을 씁니다.
- 지금 로더로는 v1 yaml을 읽을 수 없습니다(schema 1만 지원). 로더를 맞추기 전까지 v1 정책은 Isaac Lab 학습 환경(`teleop.py`, `hn play`)으로만 돌립니다.
- 체크포인트를 바꿀 때마다 yaml의 `checkpoint`와 바뀐 항목만 고칩니다.

## 다시 볼 조건

- LiDAR 설정이나 height map 만드는 방법을 바꿀 때(예: 내려가는 계단 가림 처리로 입력에 "봤는지" 표시를 더하면 차원이 바뀜)
- height map grid 범위(앞 끝 거리)나 칸 수를 바꿀 때
- 실기 LiDAR 장착 위치·각도·질량을 실측해 바꿀 때
