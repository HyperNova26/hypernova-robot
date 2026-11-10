# 빠른 시작 — 보행 (`hn:sim`)

`hn:sim`에서 Isaac Lab 내장 사족보행 rough-terrain 과제를 headless로 짧게 학습하고, 재생하면서 ONNX를 내보낸 뒤, 그 ONNX를 robot venv의 onnxruntime으로 실행해 보는 과정입니다. 학습 코드 자체를 익히는 문서가 아니라 **환경이 처음부터 끝까지 이어지는지** 확인하는 문서입니다.

2026-10-22에 RTX 4070 SUPER(12 GB), 드라이버 595.99.02, Isaac Lab 3.0.0 / Isaac Sim 6.2.0 이미지에서 아래 명령을 그대로 실행해 확인했습니다. 창을 띄우는 재생(4단계 첫 명령)을 뺀 컨테이너 안 명령은 이미지와 캐시가 있을 때 이 PC에서 전체 약 2분 걸렸습니다.

## 준비

[Docker 개발 환경](../../docker/README.md)의 호스트 준비(NVIDIA 드라이버 580.65.06 이상, Docker Engine, NVIDIA Container Toolkit)를 마치고 이미지를 빌드합니다. 최초 한 번이고 이 PC에서 10~17분 걸립니다(Ubuntu 미러 속도에 따라). 디스크가 빌드 중에 최대 60 GB(처음부터라면 약 130 GB) 필요합니다([여유 디스크](../../docker/README.md#5-여유-디스크)).

```bash
./docker/hn build sim
```

## 1. 컨테이너에 들어가기

```bash
./docker/hn sim
```

프롬프트가 `(hn:sim) /workspace/isaaclab $`로 바뀌면 컨테이너 안입니다. 아래 명령은 모두 이 셸에서 칩니다. 터미널을 더 열려면 호스트에서 같은 명령을 다시 칩니다.

환경이 제대로 깔렸는지 먼저 확인합니다(약 30초). 모든 줄이 `OK`이고 마지막에 `모두 통과`가 나와야 합니다.

```bash
/opt/hn/scripts/selftest.sh --isaac
```

## 2. 과제 고르기

```bash
./isaaclab.sh -p scripts/environments/list_envs.py --keyword Velocity-Rough --show_presets
```

사족보행 rough-terrain 속도 추종 과제는 `Isaac-Velocity-Rough-UnitreeGo2`, `Isaac-Velocity-Rough-AnymalD` 등이 있습니다. 이 문서는 Go2를 씁니다.

> [!WARNING]
> Isaac Lab 3.0.0에서 이 과제들의 **기본 physics는 PhysX가 아니라 `newton_mjwarp`** 입니다. 지정하지 않으면 아무 오류 없이 다른 엔진으로 학습됩니다. 우리는 PhysX로 학습하기로 했으므로(ADR-0002) 학습과 재생은 `hn-rl` wrapper로 실행합니다. `hn-rl`이 `physics=isaacsim_physx`와 `--rl_library rsl_rl`을 대신 붙이고, 직접 `physics=...`를 주면 그 값을 쓰면서 경고를 냅니다. 시작할 때 나오는 표의 `Physics` 줄로 확인할 수 있습니다.
>
> 호스트에서 컨테이너 밖에 있을 때는 `./docker/hn train ...`, `./docker/hn play ...`가 같은 일을 합니다.

`./isaaclab.sh`를 실행하면 "deprecated" 경고가 나옵니다. Isaac Lab 3.1에서 없어질 예정이라는 안내이고, 3.0.0에서는 정상 동작합니다.

## 3. 학습 (headless, PhysX, 20 iteration)

```bash
hn-rl train --task Isaac-Velocity-Rough-UnitreeGo2 --num_envs 2048 --max_iterations 20
```

`hn-rl train`은 `scripts/reinforcement_learning/train.py --rl_library rsl_rl ... physics=isaacsim_physx`를 실행합니다(예전 문서의 `rsl_rl/train.py` 경로는 3.0.0에 없습니다). 창 없이 도는 것이 기본이고, 창을 띄우려면 `--visualizer kit`을 붙입니다.

처음에 이런 표가 나와야 합니다.

```text
╭─ Isaac Lab · train ────────────────────────────╮
│ Task          Isaac-Velocity-Rough-UnitreeGo2  │
│ Workflow      manager-based                    │
│ RL library    rsl_rl                           │
│ Physics       isaacsim_physx                   │
│ Renderer      n/a (no camera sensors)          │
│ Visualizer    none (headless)                  │
│ Device        cuda:0                           │
│ Environments  2048                             │
╰────────────────────────────────────────────────╯
```

iteration마다 이런 블록이 찍히고, 끝나면 시간이 나옵니다. 값은 실행마다 조금씩 다릅니다.

```text
                            Learning iteration 19/20
                               Run name: ...
                            Total steps: 983040
                       Steps per second: 38690
                        Collection time: 1.201s
                          Learning time: 0.070s
                            Mean reward: -12.27
...
Training time: 25.47 seconds
```

20 iteration은 파이프라인 점검용이라 보상이 아직 오르지 않습니다. 실제로 걷는 policy는 훨씬 많은 iteration이 필요합니다(이 문서에서는 확인하지 않았습니다).

같은 PC(RTX 4070 SUPER 12 GB)에서 `--max_iterations 20`으로 잰 값입니다. Isaac Sim 시작에 약 30초가 따로 듭니다.

| `--num_envs` | steps/s (첫 iteration 제외 평균) | VRAM 최대(프로세스) | 학습 시간 |
| --- | --- | --- | --- |
| 2048 | 약 39,800 | 약 4.4 GB | 25초 |
| 4096 | 약 47,400 | 약 5.6 GB | 42초 |

12 GB GPU에서 4096 환경이 6 GB도 안 쓰므로 VRAM은 넉넉합니다. 메모리가 모자라면 `--num_envs`를 줄입니다.

결과는 컨테이너 안 `/data/isaaclab/logs/rsl_rl/unitree_go2_rough/<날짜_시각>/`에 쌓이고, 호스트에서는 `~/hypernova-data/isaaclab/logs/...`로 보입니다(소유자는 내 계정). 컨테이너를 지워도 남습니다.

## 4. 재생하고 ONNX 내보내기

가장 최근 학습 폴더 이름을 변수에 담습니다.

```bash
RUN=$(ls -t /data/isaaclab/logs/rsl_rl/unitree_go2_rough | head -1); echo $RUN
```

창을 띄워서 재생합니다(호스트 데스크톱 세션에서 실행해야 합니다). 창은 금방 뜨지만 뷰포트가 검게 비어 있다가, 이 PC에서는 약 2분 반 뒤에 Go2 16마리가 거친 지형 위에 나타나고 뷰포트 위쪽에 `Physics: PhysX`가 표시됐습니다. 20 iteration짜리 policy라서 제대로 걷지는 못합니다. `Ctrl+C`로 끝냅니다.

```bash
hn-rl play --task Isaac-Velocity-Rough-UnitreeGo2 --num_envs 16 --checkpoint /data/isaaclab/logs/rsl_rl/unitree_go2_rough/$RUN/model_19.pt --visualizer kit
```

ONNX 파일은 재생을 시작하기 **전에** 만들어집니다. 창이 필요 없으면 아래처럼 잠깐 돌리고 끝내도 됩니다(`timeout`이 끊으므로 종료 코드 124는 정상입니다).

```bash
timeout 60 hn-rl play --task Isaac-Velocity-Rough-UnitreeGo2 --num_envs 16 --checkpoint /data/isaaclab/logs/rsl_rl/unitree_go2_rough/$RUN/model_19.pt
```

```bash
ls -la /data/isaaclab/logs/rsl_rl/unitree_go2_rough/$RUN/exported/
```

```text
policy.onnx         10830
policy.onnx.data  1146368
policy.pt         1159574
```

> [!WARNING]
> `policy.onnx`는 그래프만 담은 10 KB짜리 파일이고, 가중치는 같은 폴더의 `policy.onnx.data`에 따로 있습니다(torch 2.11의 ONNX exporter 동작). **두 파일을 항상 같이** 옮기세요. `policy.onnx`만 복사하면 열 때 `External data path does not exist: ".../policy.onnx.data"` 오류가 납니다.

## 5. robot venv의 onnxruntime으로 실행

ONNX Runtime은 robot venv(`/opt/hn-venv`)에만 있습니다. Isaac Lab venv에는 없고 추가하지도 않습니다. `/opt/hn-venv/bin/python`을 경로로 직접 부릅니다(`activate`하지 않습니다).

```bash
/opt/hn-venv/bin/python - <<'EOF'
import glob, numpy as np, onnxruntime as ort
path = sorted(glob.glob("/data/isaaclab/logs/rsl_rl/unitree_go2_rough/*/exported/policy.onnx"))[-1]
sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
inp, out = sess.get_inputs()[0], sess.get_outputs()[0]
print(path)
print("입력", inp.name, inp.shape, "-> 출력", out.name, out.shape)
action = sess.run(None, {inp.name: np.zeros((1, inp.shape[1]), dtype=np.float32)})[0]
print("action", action.shape, np.round(action[0][:4], 3))
EOF
```

```text
/data/isaaclab/logs/rsl_rl/unitree_go2_rough/2026-10-22_16-56-11/exported/policy.onnx
입력 obs [1, 235] -> 출력 actions [1, 12]
action (1, 12) [...]
```

관측 235차원(`obs`)을 넣으면 관절 목표 12개(`actions`)가 나옵니다. CPU에서 한 번 추론하는 데 0.02 ms 안팎입니다. 같은 파일을 `hn:ros`에서도 읽을 수 있습니다(`/data`가 두 컨테이너에서 같은 폴더). 나중에 sim2sim 스크립트와 실기 노드는 이 경로로 policy를 읽게 됩니다.

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| `Physics` 줄이 `newton_mjwarp` | `hn-rl` 없이 `./isaaclab.sh -p .../train.py`를 직접 쳤거나 `physics=newton_mjwarp`를 직접 줌 |
| `unrecognized arguments: --headless` | 3.0.0에는 없는 옵션. 창 없이 도는 것이 기본이고 창은 `--visualizer kit` |
| `exported/`에 `policy.onnx`가 없음 | 4단계의 `play.py`를 실행했는지, `--checkpoint` 경로가 맞는지 |
| `External data path does not exist: ".../policy.onnx.data"` | `policy.onnx.data`를 `policy.onnx`와 같은 폴더에 두었는지 |
| 창이 안 뜸 | 호스트 데스크톱 세션의 터미널에서 실행했는지, `echo $DISPLAY` 값이 있는지 |
| 처음 실행이 오래 걸림 | Isaac Sim shader 컴파일(처음 한 번만, 캐시는 volume에 남음). 로봇 USD도 처음에 NVIDIA 서버에서 받으므로 오프라인이면 실패 |
| `CUDA out of memory` | `--num_envs`를 줄임. 다른 GPU 프로그램(브라우저 등)이 쓰는 VRAM도 확인 |
