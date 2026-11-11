# Policies

2026-11-11 기준입니다. Isaac Lab 3.0.0(`hn:sim`)에서 로봇의 학습·평가·export를 수행합니다.

## 정책 실행: 순서대로

Docker 이미지와 로봇 mesh가 준비된 상태에서 실행합니다. 처음 사용하는 checkout은 아래 [처음 준비](#처음-준비와-문제-해결)를 먼저 확인합니다.

1. **호스트의 저장소 루트**에서 컨테이너에 들어갑니다. GUI가 열리는 데스크톱 터미널을 사용합니다.

   ```bash
   ./docker/hn sim
   ```

2. **컨테이너 `(hn:sim)` 안**에서 과제와 checkpoint를 선택하고 실행합니다. 아래는 포함된 v0 Rough policy를 평지에서 조종하는 예시입니다.

   ```bash
   cd /workspace/isaaclab
   TASK_ID=HN-Velocity-Rough-Go2v0
   CHECKPOINT=/workspace/hypernova/policies/urdf_v0/pretrained/hn_go2v0_rough_model_3849.pt

   ./isaaclab.sh -p /workspace/hypernova/policies/teleop.py \
     --task "$TASK_ID" \
     --checkpoint "$CHECKPOINT" \
     --terrain flat --level 0 \
     --visualizer kit
   ```

3. **Isaac Sim 창을 클릭**해 조종합니다. 종료는 터미널에서 `Ctrl+C`입니다.

   | 키 | 동작 |
   | --- | --- |
   | `↑` / `↓` | 전진 / 후진 |
   | `←` / `→` | 옆걸음 |
   | `Z` / `X` | 회전 |
   | `L` | 속도 명령을 0으로 설정 |

   기본은 키를 누르고 있는 동안만 움직입니다. RustDesk 같은 원격 데스크톱에서는 누르고 있는 키가 곧바로 뗀 것으로 전달되어 로봇이 잠깐 움직이고 멈춥니다. 이때는 2단계 명령에 `--incremental`을 붙입니다. 키를 누를 때마다 그 방향으로 한 단계(기본 `--vx` 0.8 m/s, `--vy` 0.4 m/s, `--wz` 1.0 rad/s)씩 더하고 떼도 유지하며, 반대 방향 키로 한 단계씩 줄이거나 `L`로 멈춥니다. 키 입력을 확인하려면 `--log_keys`로 받은 키 이벤트를 출력합니다.

`teleop.py`가 과제를 등록하고 로봇 한 대를 PhysX로 실행합니다. 별도의 `PYTHONPATH` 설정이나 venv 활성화는 필요하지 않습니다. 첫 실행은 USD 변환과 shader 준비 때문에 오래 걸릴 수 있습니다.

준비된 다른 URDF 버전은 **2단계의 `TASK_ID`와 `CHECKPOINT`만** 해당 버전의 값으로 바꿉니다. 과제 ID는 각 `urdf_v*/__init__.py`의 `TASKS`에서 확인하고 로봇·관측·행동 설정이 맞는 checkpoint를 사용합니다. 현재 `urdf_v1`은 `TASKS`가 비어 있어 실행할 수 없습니다.

Rough checkpoint는 평지에서도 Rough 과제 ID를 유지합니다. 지형만 바꾸려면 `--terrain flat --level 0`을 `--terrain stairs --level 3` 등으로 바꿉니다. 지원 선택은 `all`, `flat`, `slope`, `stairs`, `boxes`, `rough`이며 난이도는 0–9입니다. 해당 지형이 버전의 `env.py`에 있어야 합니다.

## 처음 준비와 문제 해결

- **이미지가 없을 때:** 호스트에서 `./docker/hn build sim`을 실행합니다. 자세한 환경 준비는 [Docker 안내](../docker/README.md)를 따릅니다.
- **로봇 mesh가 없을 때:** 해당 [로봇 모델 안내](../description/)를 따릅니다. 현재 Go2 모델은 컨테이너에서 다음을 한 번 실행한 뒤 위의 2단계로 진행합니다.

  ```bash
  /opt/isaaclab-venv/bin/python \
    /workspace/hypernova/tools/description/fetch_go2_meshes.py --convert
  ```

- **`PermissionError: '/data/usd'`가 발생할 때:** 호스트 데이터 폴더의 쓰기 권한을 확인합니다. 현재 Go2 설정은 다음 임시 cache를 지정한 뒤 2단계를 다시 실행할 수도 있습니다.

  ```bash
  export HN_GO2_USD_DIR=/tmp/hn-usd/urdf_v0
  mkdir -p "$HN_GO2_USD_DIR"
  ```

  cache 경로는 로봇 버전별로 분리합니다. `/tmp` cache는 컨테이너 재생성 시 사라지며, 영구 보관하려면 쓰기 가능한 `/data` 아래 경로를 지정합니다. 버전별 기본값과 환경변수는 `robot.py`에서 확인합니다.

## 선택: 자동 재생과 학습

위의 2단계와 같은 셸에서 `TASK_ID`와 `CHECKPOINT`를 사용합니다. 키보드 없이 재생하려면 다음을 실행합니다.

```bash
export PYTHONPATH="/workspace/hypernova${PYTHONPATH:+:$PYTHONPATH}"
hn-rl play \
  --task "$TASK_ID" \
  --external_callback policies.register.register_tasks \
  --checkpoint "$CHECKPOINT" \
  --num_envs 1 --visualizer kit
```

새 학습은 같은 `PYTHONPATH` 설정에서 `hn-rl train --task "$TASK_ID" --external_callback policies.register.register_tasks`로 시작합니다. `hn-rl`은 RSL-RL과 PhysX를 선택하며 학습 결과는 `/data/isaaclab/logs/rsl_rl/`에 저장합니다. export 절차는 [보행 빠른 시작](../docs/development/quickstart-locomotion.md)을 참고합니다.

## 파일 구조와 관리

`policies/`가 Python package이며, 형상 원본은 [`description/`](../description/), ROS 2 inference node는 [`ros_pkgs/`](../ros_pkgs/), 학습·평가용 scene은 [`sim_scenes/`](../sim_scenes/)에 둡니다.

| 경로 | 내용 |
| --- | --- |
| `teleop.py` | 버전 공용 키보드 실행기 |
| `register.py` | `VERSIONS`의 package와 각 `TASKS`를 읽어 과제 등록 |
| `rewards.py` | 공용 보상과 발 body 설정 |
| `urdf_v0/` | `robot.py`, `env.py`, `TASKS`, `pretrained/` |
| `urdf_v1/` | 작업 중이며 등록된 과제 없음 |

새 버전은 `robot.py`, `env.py`, `TASKS`를 구현하고 `register.py`의 `VERSIONS`에 추가합니다. 외부 dataset·checkpoint는 출처·버전·checksum과 재현 방법을 기록하며, 새 데이터·weight·실행 log는 Git에 추가하지 않습니다. 외부 저장소를 통째로 사용할 때는 commit을 고정한 submodule을 사용합니다.
