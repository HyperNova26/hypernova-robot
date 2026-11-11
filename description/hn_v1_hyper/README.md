<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# HyperNova HYPER v1 모델

기준일: 2026-11-11. SI 단위(m, kg, s, rad)를 사용합니다.
HYPERNOVA v1 기체 CAD(Inventor 조립품 `trunk-hip-thigh-calf-foot.iam`)에서 질량 특성과 관절 위치를 추출한 모델입니다.
좌표 규약, 링크·관절 이름, 관절 위치 한계는 Unitree Go2를 따르고, 토크·속도는 실제 모터 Unitree GO-M8010-6 값입니다.

## 출처

- 원본: [jaemin0319/HYPER](https://github.com/jaemin0319/HYPER) @ `e5f9ed59ce04bc668f6830da51bafec7e75aef74`의 `urdf/hyper.urdf`
- 물성치·관절 표, 충돌 근사 검증, 확인이 필요한 점은 원본 README를 기준으로 봅니다.
- 원본의 `usd/`, `isaacsim/`, `isaaclab/`, `mujoco/`, `deploy/`는 가져오지 않았습니다. USD는 아래처럼 이 URDF에서 다시 변환합니다.

## 전달 파일

- `hypernova_hyper.urdf`: 원본 URDF에서 두 가지만 바꿨습니다. 로봇 이름(`hyper_v1` → `hn_v1_hyper`)과 메시 경로(`../meshes/` → `meshes/`)입니다. 바꾼 내용은 파일 머리 주석에도 적었습니다.
- `mesh_manifest.json`: 원본 commit과 URDF가 참조하는 메시 41개의 SHA-256입니다.
- `meshes/`: Git에 넣지 않습니다. 약 54 MB이고 `trunk.stl`이 12.8 MB(10 MiB 초과)라서 v0처럼 로컬 의존성으로 관리합니다.

Git checkout에서 메시가 없으면 저장소 루트에서 한 번 실행합니다. 표준 라이브러리만 씁니다.

```bash
python3 tools/description/fetch_hyper_v1_meshes.py
```

## 구성

| 항목 | 값 |
| --- | --- |
| 링크 / 관절 | 17개 / 회전 12개 + 고정 4개(`*_foot_joint`) |
| 총 질량 | 12.329 kg |
| 허벅지 / 종아리(무릎 축 → 발 중심) / 발 반지름 | 0.2000 / 0.2165 / 0.0250 m |
| 모터 | GO-M8010-6, 모든 관절 23.7 N·m, 30 rad/s. calf는 thigh에 달린 모터가 벨트 1:1로 구동 |
| 몸통 링크 이름 | `base` (표준 이름 규칙의 `trunk`와 다름. 메시 파일 이름만 `trunk.stl`) |

## 충돌 설정

원본 HYPER의 충돌 방식을 Isaac Lab 3.0.0에서 같게 맞췄습니다. 설정은 [`policies/urdf_v1/robot.py`](../../policies/urdf_v1/robot.py)에 있습니다.

| 원본(Isaac Lab 2.3, `isaacsim/convert_urdf.py`) | 여기(Isaac Lab 3.0.0) |
| --- | --- |
| 부품별 충돌 STL, `collider_type="convex_hull"` | `collision_type="Convex Hull"` |
| `self_collision=True`, `enabled_self_collisions=True` | 같음 |
| `link_density=0.0`(URDF 질량·관성 그대로) | 같음 |
| `merge_fixed_joints=True` + 발 관절 `dont_collapse` | `merge_fixed_joints=False`. 3.0 변환기는 고정 관절을 모두 합치므로 끄고, 고정 관절이 발 4개뿐이라 결과는 같습니다 |

변환한 USD는 생성 파일이라 저장소 밖 `/data/usd/hn_v1_hyper/`(호스트 `~/hypernova-data/usd/hn_v1_hyper/`)에 캐시합니다.
원본 README의 학습 환경 변경(몸체-지면 접촉만 보는 `base_contact` 종료, 허벅지 접촉 페널티)은 과제 설정(`policies/urdf_v1/env.py`)에서 따로 옮깁니다.

## 확인 결과

2026-11-11, `hn:sim`(Isaac Lab 3.0.0, PhysX) 컨테이너에서 확인했습니다.

- 변환 USD: rigid body 17개, 관절 16개(회전 12, 고정 4), 총 질량 12.329 kg
- 충돌체 62개: 메시 58개 모두 `convexHull`, 발 구 4개. 링크별 개수는 base 10, hip 3, thigh 7, calf 2, foot 1로 원본 URDF와 같음
- `physxArticulation:enabledSelfCollisions = True`
- 관절 순서(Isaac Lab): `FL/FR/RL/RR_hip`, `_thigh`, `_calf`. 원본 `deploy/policies/flat/deploy.json`과 같음
- 선 자세: v0 Flat 과제에 로봇만 바꿔 0 action으로 4초, env 4개. base 높이 0.289–0.302 m(원본 MuJoCo 0.2969 m), 넘어짐 0회, 기본 자세와 관절 오차 최대 0.32 rad

## 제한

- 보행 과제(`TASKS`)와 학습은 아직 없습니다.
- CAD 간섭 각도(예: 앞 허벅지 약 1.40 rad에서 몸체 접촉)와 같은 자기충돌 결과가 나오는지는 따로 확인하지 않았습니다.
- 전방 LiDAR(SOSLAB ML-X 120, 860 g)와 외장 IMU의 질량·위치는 URDF에 없습니다.
- 무릎 하한, 발 공 질량 등 원본 README의 "확인이 필요한 점"은 그대로 남아 있습니다.
- 라이선스: HYPERNOVA 형상 산출물이므로 [저장소 정책](../../LICENSE.md)에 따라 CERN-OHL-S-2.0을 적용할 예정이며, 원본 작성자 확인이 필요합니다. 관절 위치 한계는 Unitree Go2 값을 옮긴 것입니다.
- 실기 검증은 하지 않았습니다.
