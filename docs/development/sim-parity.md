# 시뮬레이터 사이 보행 차이

2026-11-19 기준입니다. 같은 정책을 MuJoCo, Isaac Sim, Isaac Lab에서 돌릴 때 도착 시간이 서로 다른 이유를 찾고, 학습 환경인 Isaac Lab에 가깝게 맞춘 기록입니다. 환경은 `hn:sim`(MuJoCo 3.12.0, Isaac Lab 3.0.0, PhysX)이고 정책은 HYPER v1 Rough GT(model_2998)이며, v0(model_3849)로 영향을 확인했습니다. 창 없이 돌렸고 명령 속도 0.5 m/s에서만 확인했습니다.

## 요약

- 정책은 Isaac Lab에서 학습했으므로 **Isaac Lab을 기준**으로 삼습니다. 다른 두 시뮬레이터는 같은 정책이 더 느리게 걷습니다.
- 가장 큰 원인은 **Isaac Lab 3.0의 Newton 액추에이터 경로**입니다. 토크 계산은 우리 모터 모델과 정확히 같은데, 걸음이 학습 환경에서 더 빠르고 이를 지연으로 재현할 수 있습니다. 다음은 **MuJoCo의 연한 접촉**입니다. GPU와 CPU PhysX의 차이는 원인이 아니었습니다(아래 정정).
- 두 보정을 `tools/demo/run_route.sh`의 기본값으로 켰습니다. v3 경로 A(101 m) 도착은 Isaac Lab 207.5 s, Isaac Sim 209.8 s(+1.1%), MuJoCo 211.4 s(+1.9%)입니다.
- 토크 지연 보정은 **v1의 걸음에 맞춘 경험적 모델**입니다. v0에는 맞지 않아서(오히려 4.6% 멀어짐) v1에만 켰습니다. 정책을 바꾸면 이 절차를 다시 해야 합니다.

## 정정

같은 날 오전 판에서 "GPU와 CPU PhysX의 차이(−2.1%)"를 원인으로 적었는데 틀렸습니다. Isaac Lab을 CPU로 돌리면 느려지는 것은 맞지만, **Isaac Sim 단독은 CPU와 GPU가 같습니다**(속도 비율 0.921, 0.921, 각 6회 반복). Isaac Lab에서 장치를 바꾸면 달라지는 것은 PhysX가 아니라 Isaac Lab의 액추에이터 경로였습니다.

## 결과

v3 경로 A에서 v1 로봇이 넘어짐 없이 걸어 목표 0.30 m 안에 도착한 시간입니다.

| 구성 | 보정 전 | 보정 후(기본값) | Isaac Lab 대비 |
| --- | --- | --- | --- |
| Isaac Lab (GPU, 학습 환경) | 207.5 s | 207.5 s | - |
| Isaac Sim | 216.9 s | 209.8 s | +1.1% |
| MuJoCo | 225.9 s | 211.4 s | +1.9% |

경로 추종기를 빼려고 합성 지형에서 명령을 고정해 걷게 했습니다(40 s, 처음 10 s 제외). 비율은 몸통 전진 속도를 명령으로 나눈 값입니다.

| 구성 | 평지 | 10° 경사로 |
| --- | --- | --- |
| Isaac Lab (GPU) | 0.953 | 1.012 |
| Isaac Lab (CPU) | 0.933 | 0.981 |
| Isaac Lab (GPU, 예전 액추에이터) | 0.912 | - |
| Isaac Sim, 보정 전 | 0.921 | 0.962 |
| Isaac Sim, 토크 1스텝 지연 | 0.949 | 0.986 |
| MuJoCo, 보정 전 | 0.900 | 0.901 |
| MuJoCo, 접촉 보정 | 0.915 | 0.951 |
| MuJoCo, 접촉 보정 + 토크 6.25 ms 지연 | 0.948 | 0.975 |

낙하 높이를 0~15 mm로 6가지 바꿔 반복해도 구성 안의 표준편차는 0.05~0.19%였습니다. 구성 사이의 차이(1.9~5.2%)는 그보다 16~77배 커서 걸음의 변동이 아니라 체계적인 차이입니다.

## 원인

### Newton 액추에이터 경로(가장 큼)

학습 설정(`use_newton_actuators: true`)에서 Isaac Lab의 액추에이터는 새 경로로 돕니다. 이 경로를 예전(torch) 경로로 바꾸면 Isaac Lab도 느려져서 Isaac Sim, MuJoCo와 같은 수준이 됩니다(평지 GPU 0.953 → 0.912, CPU 0.933 → 0.916).

- **토크 계산은 같습니다.** 물리 하위 스텝(정책 스텝당 4번)마다 PhysX의 실제 관절 상태와 액추에이터가 적용한 토크를 기록해 비교하니, 우리 모터 모델(kp 25, kd 0.5, DC 클램프)이 **그 하위 스텝의 실제 상태로 계산한 값과 잔차 0.0000으로 일치**했습니다. 지연, 정책 주기 고정, 오래된 상태 가설은 모두 틀렸습니다. 이 걸음의 토크는 평균 1~5 N·m로 포화 상한(23.7 N·m)에 닿지 않아 클램프 규칙의 차이도 영향이 없습니다.
- **그런데 동작은 다릅니다.** 정책 없이 기본 자세를 유지하게 하고 0.4 m에서 떨어뜨리면(`--hold-default`) Isaac Lab만 더 깊이 착지하고 정지 후에도 흔들립니다. 같은 일이 MuJoCo에서 **토크를 늦게 적용하면 재현**됩니다. 6.25 ms 지연은 Isaac Lab CPU와, 8.75 ms 지연은 Isaac Lab GPU와 착지 높이, 흔들림, thigh 오차, 착지 각도가 거의 같았습니다(예: thigh FL 오차 0.0302 대 0.0287, 0.0444 대 0.0427).
- **코드에는 지연 성분이 없습니다.** `DCMotorCfg`는 `PDControl + DCMotorClamping`으로 매핑되고 지연은 `DelayedPDActuatorCfg`일 때만 붙습니다. 지연처럼 행동하는 정확한 이유는 찾지 못했습니다. 그래서 이 보정은 효과를 재현하는 경험적 모델입니다.
- **정책마다 다릅니다.** v0는 예전 액추에이터에서 353.0 s로 Newton 경로(349.6 s)와 1%만 다르고, MuJoCo에 지연을 넣으면 348.7 s에서 365.8 s로 Isaac Lab에서 멀어집니다. v1(4%)과 반대 방향이므로 지연 보정은 v1에만 켰습니다.
- **한계**: 걸음이 안정한 지연은 MuJoCo에서 6.25 ms까지입니다. Isaac Lab GPU의 정지 통제 실험을 재현하는 8.75 ms는 걸음이 불안정해져서 쓸 수 없습니다. 그래서 보정 후에도 경사로에서 Isaac Lab보다 느립니다(0.975, 0.986 대 1.012).

### MuJoCo의 연한 접촉

MuJoCo 기본 접촉(`solref` 시정수 0.02 s)은 PhysX보다 연해서 발이 더 가라앉고 덜 밀어 줍니다. 아래 설정이 안정하게 돌고 효과가 가장 컸습니다. `solref`를 스텝의 2배보다 작게 두면 MuJoCo가 자동으로 클램프하고, 그 안전장치를 끄면 첫 스텝부터 발산했습니다.

```text
--substeps 4  --solref 0.002,1  --solimp 0.99,0.999,0.001
```

평지 0.900 → 0.915, 경사로 0.901 → 0.951입니다. 스텝을 8개로 쪼개고 더 딱딱하게 해도 같았습니다. 대가로 실행 시간이 2배쯤 늘고, 토크를 1.25 ms마다 다시 계산하므로 학습 조건(5 ms 유지)과는 조금 다릅니다(스텝 분할만의 효과는 −0.8%).

### 고친 결함

- **Isaac Sim의 초기 조건**: 플레이어가 상태를 설정한 뒤 PhysX 초기화 5스텝을 토크 없이 돌려서 로봇이 이미 떨어지는 중(`base_z` 0.396 m, 수직 속도 −0.245 m/s)에 출발했습니다. 초기화 스텝을 먼저 돌리고 상태를 나중에 설정하도록 고쳤습니다. 정상 상태 속도는 그대로였습니다(0.921).
- **Isaac Lab의 20 s 리셋**: 경로 없는 고정 명령 모드에서 에피소드 시간제한으로 20 s마다 리셋됐습니다. 경로 모드는 원래 풀려 있었습니다. 이 버그 때문에 평지·경사로의 Isaac Lab 수치가 한동안 틀렸습니다.

### 원인이 아닌 것

각각 직접 확인했습니다.

- **지형**: 세 시뮬레이터가 같은 hfield에서 나온 지형을 씁니다.
- **로봇 모델**: MuJoCo가 컴파일한 모델과 USD의 링크 질량, 무게중심, 관성이 1e-8 수준까지 같고, Isaac Sim과 Isaac Lab의 런타임 PhysX 값(질량, 관성, armature, 관절 마찰, 속도·토크 한계, 형상 62개의 재질)이 완전히 같습니다.
- **GPU와 CPU**: Isaac Sim은 `--device cuda`로 장면이 실제 GPU 동역학(`enableGPUDynamics`)이 되어도 결과가 같습니다.
- **MuJoCo의 적분과 솔버**: 물리 스텝 분할(2, 4, 8), 적분기(Euler, implicit, RK4), 마찰 원뿔, 솔버 반복을 바꿔도 ±1% 안쪽입니다.
- **마찰계수**: MuJoCo에서 0.5에서 1.3까지 바꿔도 비율이 0.886~0.905 안에 있습니다(2.0은 0.851).
- **Isaac Sim의 PhysX 속성**: Isaac Lab 런타임 덤프의 속성 383개(링크 강체, 충돌체, 관절, articulation, 장면)를 그대로 적용하면 정지 통제 실험은 Isaac Lab 쪽으로 반쯤 움직이지만 걸음 속도는 그대로입니다(0.920). 정지 실험에 영향을 주는 속성은 장면의 `enableExternalForcesEveryIteration` 하나였습니다.

## 아직 설명하지 못한 것

- Newton 경로가 토크를 어떻게 적용해서 지연처럼 보이는지, 그리고 GPU가 CPU보다 지연이 더 커 보이는 이유.
- 보정 후 남은 차이(Isaac Lab 대비 속도 비율): 평지 0.4~0.5%, 경사로 2.6~3.7%.
- 한 정책(v1)과 한 속도(0.5 m/s)로 맞춘 보정입니다. 다른 속도, 회전, 계단에서는 달라질 수 있고 v0는 따로 맞지 않습니다.

## 재현 방법

저장소 최상위에서 컨테이너(`hn:sim`)로 실행합니다. 합성 지형은 `tools/map/synthetic_hfield_scene.py`로 만들고 `tools/map/hfield_scene_import.py`로 세 시뮬레이터용으로 바꿉니다(사용법은 각 파일 머리말).

```bash
python3 tools/map/synthetic_hfield_scene.py --kind flat --out ~/hypernova-data/sim_parity/flat
./docker/hn sim /opt/hn-venv/bin/python /workspace/hypernova/tools/map/hfield_scene_import.py \
  --scene /data/sim_parity/flat/scene/scene.xml --out /data/sim_parity/flat/derived \
  --robot-usd v1=/data/usd/hn_v1_hyper/hypernova_hyper/hypernova_hyper.usda

# 경로 없이 명령 고정(ROUTE=none), 2000 스텝(40 s), 기록 저장. 보정은 기본으로 켜져 있습니다
T=/data/sim_parity/traces
MAP=flat ROUTE=none HEADLESS=1 ./tools/demo/run_route.sh mujoco   --max-steps 2000 --trace $T/flat_mujoco.bin
MAP=flat ROUTE=none HEADLESS=1 ./tools/demo/run_route.sh isaacsim --max-steps 2000 --trace $T/flat_isaacsim.bin
MAP=flat ROUTE=none HEADLESS=1 ./tools/demo/run_route.sh isaaclab --max_steps 2000 --hn-trace=$T/flat_isaaclab.bin
python3 tools/demo/compare_traces.py 10 40 "MuJoCo=.../flat_mujoco.bin" "Isaac Sim=.../flat_isaacsim.bin" "Isaac Lab=.../flat_isaaclab.bin"
```

2026-11-20부터 `run_route.sh`는 기본으로 상태 판정 하네스(`policies/route_walk/state_scenarios.py`)를 거칩니다. 위 MuJoCo 평지 기록은 하네스가 있을 때와 없을 때(`STATE=0`) 바이트까지 같았습니다(1000 스텝). 하네스 없이 돌리려면 `STATE=0`을 붙입니다.

보정은 `MJ_CALIB=0`(MuJoCo 접촉)과 `ACT_DELAY=0`(토크 지연)으로 끕니다. 둘 다 끄면 2026-11-15 이전 기록값(예: v0 예전 지형 MuJoCo 348.0 s)이 재현됩니다.

비교용 옵션입니다. 모두 기본값이면 기존 동작과 같습니다.

| 옵션 | 내용 |
| --- | --- |
| `--trace`, `--hn-trace` | 정책 입출력(명령, 몸통 속도, 관절, 행동, 직전 토크)을 매 스텝 파일에 기록. 열 이름은 파일 옆 `.json` |
| `--hold-default`, `--hn-hold-default=1` | 정책 대신 기본 자세를 목표로 고정(물리만 비교하는 통제 실험) |
| `--drop-offset`, `--hn-drop-offset` | 처음 낙하 높이(0.40 m)에 더함. 초기 조건 변동을 재는 실험용 |
| MuJoCo `--mj-opt`, `--substeps`, `--solref`, `--solimp`, `--torque-delay` | `model.opt` 직접 변경, 물리 스텝 분할, 접촉 강성, 토크 지연(분할한 스텝 단위) |
| MuJoCo `--dump-model` | 컴파일한 링크 질량·관성과 관절 속성을 JSON으로 |
| Isaac Sim `--device`, `--torque-delay` | PhysX 파이프라인(cpu, cuda), 토크 지연(5 ms 단위) |
| Isaac Sim `--physx-scene`, `--robot-material`, `--rigid-props`, `--apply-physx-dump`, `--apply-physx-only` | PhysX 장면·재질·강체 속성을 바꾸거나 Isaac Lab 덤프의 속성을 그대로 적용 |
| Isaac Sim `--dump-physx`, Isaac Lab `--hn-dump-physx` | 런타임 PhysX 파라미터(텐서 API와 스테이지 속성)를 JSON으로 |
| Isaac Lab `--device cpu`, `--hn-no-newton=1` | CPU 물리, 예전(torch) 액추에이터 경로 |
| Isaac Lab `--hn-substep-probe` | 물리 하위 스텝마다 실제 관절 상태와 적용된 토크를 기록 |
