<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# HyperNova Go2 임시 모델

기준일: 2026-10-30. SI 단위(m, kg, s, rad)를 사용합니다.
HYPERNOVA 실측 모델이 아닌 Go2 기반 시뮬레이션 근사 모델입니다.
최초 13 kg 요청은 사용자의 후속 지시에 따라 원본 질량·크기 유지로 변경됐습니다.

## 전달 파일

- `hypernova_go2.urdf`: 직접 관리하는 정본입니다. 메시 경로는 URDF 기준 상대경로입니다.
- `meshes/`: 고정 버전 공식 DAE에서 변환한 STL 7개와 원본 DAE입니다. Git에는 넣지 않고 전달 ZIP에 포함합니다.
- `mesh_manifest.json`: 원본 revision과 각 메시의 SHA-256입니다.
- `LICENSE.unitree`: 수정 URDF와 원본 메시의 BSD-3-Clause 고지입니다.
- `config/front_lidar.json`: 전방 RTX LiDAR의 사용자 요구 화각 및 임시 샘플링 설정입니다.
- [`attach_front_lidar.py`](../../ros_pkgs/isaac/attach_front_lidar.py): Isaac Sim용 센서 생성 도우미입니다.

Git checkout에서 메시가 없으면 저장소 루트에서 실행합니다.

```bash
python3 tools/description/fetch_go2_meshes.py --convert
```

변환에는 실행 Python 환경의 `trimesh`와 `pycollada`가 필요합니다. 전달 ZIP에는 변환 결과가 포함되어 설치가 필요 없습니다.
DAE scene transform을 반영하여 STL로 변환하며 단위·삼각형 형상을 유지하고 단순화하지 않습니다.
DAE의 내장 색상 대신 URDF material을 사용합니다.
변환 확인 환경: Python 3.12, trimesh 4.11.1, pycollada 0.9.3.

외부 저장소 전체를 복사하지 않고 필요한 메시만 내려받습니다. 총 약 25.9 MB이며,
`base.dae`가 10 MiB를 넘으므로 저장소 대형 파일 대신 로컬 의존성/전달 ZIP으로 관리합니다.

## 적용값과 근거

| 항목 | 값 / 해석 |
| --- | --- |
| 원본 로봇 질량 | 16.087 kg, 모든 inertial 합계 |
| 크기 | 원본 1.0배 유지 |
| 추가 장비 | 2.5 kg, 총 18.587 kg |
| 등 장비 형상 | 임시 0.24 × 0.14 × 0.08 m 상자 |
| 등 장비 COM | base 기준 (0.021112, 0, 0.14) m |
| 엉덩이·허벅지 | 최대 23.7 N·m, 최대 30 rad/s |
| 무릎 | 외부 감속 1.5:1 가정, 최대 35.55 N·m, 최대 20 rad/s |
| LiDAR 장착 | base 기준 (0.35, 0, 0.04) m, 회전 없음 |
| LiDAR 화각 | 수평 120°(±60°), 수직 35°(±17.5°) |

장비 x/y는 **base 링크 COM의 수평 투영**에 맞췄습니다. 다리 자세에 따라 움직이는
로봇 전체 COM을 추적하는 위치가 아닙니다. 높이와 상자 크기는 실측되지 않은 가정입니다.
추가 장비 관성은 균일 상자 공식으로 계산했습니다.
LiDAR의 질량도 2.5 kg에 포함하여 등에 집중시켰으므로 실제 전방 질량 분포는 근사입니다.

[공식 원본](https://github.com/unitreerobotics/unitree_ros/tree/38a9b00ecbff0b70e85a7627eb9c65db9a2341f7/robots/go2_description)의
링크 질량·관성·관절 배치·각도 범위·충돌 형상은 유지했습니다.
모터는 [Unitree GO-M8010-6 공식 출력 사양](https://www.unitree.com/go1/motor/)을 기준으로 합니다.
내부 6.33:1 감속은 출력 사양에 이미 반영되어 다시 곱하지 않습니다.
최신 HW 결정의 무릎 외부 1.5:1을 적용했으며, 이전 M-003의 전체 관절 23.7/30과 차이가 있습니다.
HW 문서의 20.06 rad/s 대신 공식 모터 30 / 1.5 = 20 rad/s를 사용합니다.

최대 토크와 최대 속도는 동시에 보장되는 운전점이나 지속 정격이 아닙니다.
감속 효율·토크-속도 곡선·마찰·감쇠·회전자 관성은 확인되지 않아 새 값을 만들지 않았습니다.
원본의 고정 rotor 링크는 반사 관성(armature)을 대신하지 않습니다.
원본 관성 보존이 실제 GO-M8010-6 장착 기체의 관성 일치를 뜻하지 않습니다.
Isaac Lab 사용 시 actuator의 실제 effort/velocity 제한도 이 값에 맞춰야 합니다.

## RTX LiDAR 연결

URDF에는 센서 하우징과 `front_lidar` 고정 frame이 들어 있습니다.
표준 URDF에는 RTX 센서 실행 의미가 없으므로 센서는 별도로 생성합니다.
Isaac Sim 6.0 계열을 대상으로 하며, 5.x 호환은 검증하지 않았습니다.

1. URDF를 import할 때 fixed-joint merge를 끄고 `front_lidar` frame을 보존합니다.
2. Isaac Sim Script Editor에서 다음을 실행합니다. 경로는 실제 checkout/import 경로로 바꿉니다.

```python
import runpy
helper = runpy.run_path('/absolute/repo/ros_pkgs/isaac/attach_front_lidar.py')
sensor = helper['attach_front_lidar']('/World/hypernova_go2/front_lidar')
```

센서는 frame에 로컬 항등변환으로 붙습니다. +X 전방, +Y 좌측, +Z 상방입니다.
센서 원본 `radar` frame은 유지하지만 활성화하지 않습니다.
10 Hz, 121 × 36개 ray, 0.1–100 m 범위는 **임시 시뮬레이션값**입니다.
화각만 사용자 요구값이며 특정 상용 LiDAR의 스캔 패턴·노이즈·반사 모델이 아닙니다.
JSON은 도우미 입력이며 Isaac Sim에 직접 넣는 native RTX profile이 아닙니다.
도우미는 ROS 발행이나 로봇 제어기를 설정하지 않습니다.

## 검증과 제한

`cadgen urdf validate`와 `check_urdf`로 구조, 메시 참조, 질량, 관절 제한을 확인합니다.
원본의 0 질량 imu/radar inertial은 frame-only 표현으로 정리하고 중복 material 요소를 제거했습니다.
원본 Head_lower와 네 thigh의 관성이 단순 충돌 도형의 균일 밀도 추정과 다르다는
경고 5개는 남습니다. 이를 없애려고 원본 관성을 임의 변경하지 않았습니다.
따라서 strict validation 통과 모델이라고 표현하지 않습니다.

이 모델은 실제 로봇 제어 설정이 아닙니다. 잘못된 감속비나 무제한 actuator 설정은
시뮬레이션의 비현실적 토크·속도를 만들 수 있습니다. 실기 적용은 감속비·정격·관성 검증이 필요합니다.
기존 로봇 설정을 수정하지 않았으므로 이 디렉터리/도우미를 사용하지 않으면 이전 상태로 돌아갑니다.
보행·정적 안정성·접촉·실기 검증과 M-003 전체 완료는 이번 모델 작성 범위에 포함되지 않습니다.

확인 결과: 44 links / 43 joints / 12 movable joints, 총 18.587 kg이며 모든 메시 참조가 해결됐습니다.
12개 관절의 하한·상한 24개 자세를 렌더링해 연결 상태를 확인했습니다.
극단적인 thigh 상한에서는 발/종아리가 등 장비와 겹칠 수 있으므로 원본 관절 한계가
충돌 없는 동작 범위라는 뜻은 아닙니다. 연속 경로 충돌 검사는 수행하지 않았습니다.
Isaac Sim 6.0.1-rc.7에서 RTX 센서 생성과 4,356개 ray 속성 작성은 통과했습니다.
해당 headless 실행에서 GPU가 인식되지 않아 실제 포인트클라우드 출력은 미검증입니다.
호스트의 `/usr/bin/python3.12` 및 `npx`가 없어 기존 Isaac Python 3.12 환경을 사용했으며,
Markdown lint는 실행하지 못했습니다. `git diff --check`와 새 파일 공백 검사는 통과했습니다.
