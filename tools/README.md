# Tools

여러 사람이 반복해서 쓰는 개발·검증·변환 도구를 둡니다.

도구에는 이 정도를 같이 적습니다.

- 목적과 입력·출력
- 필요한 환경과 의존성 버전
- 사용 예시와 실패했을 때 되돌리는 방법

개인 경로가 박힌 일회성 script, 비밀정보, 생성된 binary는 넣지 마세요. 특정 패키지에서만 쓰는 도구는 그 패키지 가까이에 두고, 여러 영역에서 같이 쓰게 되면 그때 이 디렉터리로 올립니다.

## 이름 규칙

2026-11-26(S-018)부터 `tools/`와 `tests/`의 코드는 버전 번호 대신 **처음 저장소에 들어온 날짜**를 앞에 붙입니다. 날짜는 그 파일이 처음 커밋된 날(author date, `git log --diff-filter=A --follow`)입니다. 저장소 밖에서 만든 코드를 나중에 올린 경우에는 처음 만든 날을 씁니다(`map/1116_pair360_v2/`).

- **혼자 실행하는 파일**: `MMDD_이름.확장자`. `.sh` 실행기와 `.py` 구현처럼 짝인 파일은 같은 이름을 씁니다.
- **서로 import하는 여러 파일**: 폴더에 날짜를 붙이고(`MMDD_이름/`) 안의 파일 이름은 그대로 둡니다. Python은 숫자로 시작하는 모듈을 `import` 문으로 부를 수 없기 때문입니다.
- **분야 폴더**(`map/`, `demo/`, `description/`)에는 날짜를 붙이지 않습니다.
- **PAIR360 지도 도구**: 지도 버전마다 폴더 하나를 쓰고 날짜와 버전을 함께 붙입니다(`map/MMDD_pair360_vN/`). 실행기(`.sh`)도 그 폴더 안에 둡니다.
- **시험**: `tests/<분야>/MMDD_test_이름.py`. `pyproject.toml`의 `python_files`가 이 이름을 pytest에 알려 줍니다.

## 목록

| 날짜 | 경로 | 용도 |
| --- | --- | --- |
| 10-22 | `1022_setup-venv.sh` | 호스트 `.venv` 준비([Python 환경 안내](../docs/development/python-env.md)) |
| 10-22 | `1022_make_demo_bag.py`, `1022_check_demo_lio.py`, `1022_isaac_clock_pub.py` | 인지 데모 bag 생성, LIO 정답 경로 확인, Isaac `/clock` 발행([인지 빠른 시작](../docs/development/quickstart-perception.md)) |
| 10-30 | `description/1030_fetch_go2_meshes.py` | Go2 mesh 받기(`description/hn_v0_go2/`) |
| 11-11 | `description/1111_fetch_hyper_v1_meshes.py` | HYPER v1 mesh 받기(`description/hn_v1_hyper/`) |
| 11-16 | `demo/1116_run_route.sh`, `demo/1116_state_*.sh`, `demo/1116_state_run.sh` | 정책으로 경로 걷기, 상태 판정 시나리오. `1116_state_run.sh`는 `1116_state_*.sh`가 부르는 공통 실행기입니다([보행 상태](../docs/interfaces/locomotion-status.md)) |
| 10-30 | `map/1030_demo_sim_converter.{sh,py}` | 점군 전체를 분류 없이 voxel로 바꿔 USD·MuJoCo 장면을 만듭니다([장면 변환 안내](../sim_scenes/README.md)) |
| 11-09 | `map/1109_extract_pair360_demo.py` | PAIR360 T1 전체 점군에서 데모 구역을 잘라 냅니다(`pc_v1`의 출처) |
| 11-09 | `map/1109_pair360_v1/` | 지도 v1: S-004 지면(v7 → v8 전달본, v9 수관 아래 바닥), map_v1 PCD, `mesh_v1/`(11-16 코드, 기록용)([안내](map/1109_pair360_v1/README.md)) |
| 11-16 | `map/1116_pair360_v2/` | 지도 v2: `pc_v1` 우선 병합 map_v2·mesh_v2(기록용)([안내](map/1116_pair360_v2/README.md)) |
| 11-24 | `map/1124_pair360_v3/` | 지도 v3: map_v3, mesh_v3, Nav2 지도(1~11단계, 실행기 `build_pair360_v3.sh`), Nav2 금지 구역 검사 `check_nav2_keepout.sh` |

시험은 `tests/map/1030_test_demo_sim_scripts.py`(변환기), `tests/map/1109_test_*.py`(데모 자르기, S-004 지면·장면, 점군 입출력)입니다.

### 지운 코드 (2026-11-26)

| 코드 | 이유 |
| --- | --- |
| `map/demo_sim_disassembler.{sh,py}`와 그 시험 | 빈 출력 폴더만 만드는 미구현 틀이었습니다. 지면·물체 분리는 `1109_pair360_v1/`과 `1124_pair360_v3/`가 합니다 |

## PAIR360 지도 v1·v2·v3

지도와 지형 파일에는 버전 번호를 그대로 씁니다. 좌표계는 모두 `pair360_map`(PAIR360 T1 원시 XYZ, m, z 위쪽)입니다. 점군과 메시는 Git에 넣지 않고 팀 Drive `14. AI Team/`의 `data/map_vN/`, `meshes/mesh_vN/`에 둡니다. 장면 안내는 `sim_scenes/pair360_vN/`에 있습니다.

| 버전 | 입력 | 지도(점군) | 지형(메시) | 만든 코드 |
| --- | --- | --- | --- | --- |
| v1 | PAIR360 `pc_v1`만 | pc_v1 지면 v1 분할(지면 1,346,917점, 나머지 6,404,411점) | mesh_v1(2026-11-16): 지면 v1 + 나무·구조물 | `map/1109_pair360_v1/` |
| v2 | `pc_v1` + 2026-11-15 팀 촬영 `pc_v2`, **pc_v1 우선 병합** | map_v2(2026-11-16) | mesh_v2(2026-11-16) | `map/1116_pair360_v2/`(기록용) |
| v3 | `pc_v1` + `pc_v2`, **pc_v2 우선 병합** | map_v3(2026-11-18) | mesh_v3(2026-11-18), Nav2 지도(2026-11-24) | `map/1124_pair360_v3/` |

- v2는 "추가 촬영본만"이 아닙니다. 11-15 촬영본만으로 만든 지도·메시는 없습니다.
- mesh_v1 장면과 v2를 만든 11-16 코드는 고치지 않고 옮긴 기록용입니다. 당시 폴더 배치 기준이라 이 저장소에서 그대로 실행되지 않습니다.
- 지면 v1(v9)은 v3 2단계의 입력이기도 합니다(`map/1109_pair360_v1/continuous_ground_20261109_v9.json`).

## 다른 브랜치를 이 정리 위로 옮길 때 (2026-11-26)

main에 있던 아래 경로가 바뀌었습니다. 이 정리 전에 갈라진 브랜치는 main을 병합한 뒤 자기 변경의 경로를 맞춥니다.

| 옛 경로(main) | 새 경로 |
| --- | --- |
| `tools/setup-venv.sh` | `tools/1022_setup-venv.sh` |
| `tools/{make_demo_bag,check_demo_lio,isaac_clock_pub}.py` | `tools/1022_{…}.py` |
| `tools/description/fetch_go2_meshes.py` | `tools/description/1030_fetch_go2_meshes.py` |
| `tools/description/fetch_hyper_v1_meshes.py` | `tools/description/1111_fetch_hyper_v1_meshes.py` |
| `tools/demo/run_route.sh`, `tools/demo/state_*.sh` | `tools/demo/1116_run_route.sh`, `tools/demo/1116_state_*.sh` |
| `tools/demo/_state_run.sh` | `tools/demo/1116_state_run.sh` |
| `tools/map/demo_sim_converter.{sh,py}` | `tools/map/1030_demo_sim_converter.{sh,py}` |
| `tools/map/demo_sim_disassembler.{sh,py}` | 지움 |
| `tools/map/extract_pair360_demo.py` | `tools/map/1109_extract_pair360_demo.py` |
| `tools/map/{build_continuous_ground_v5,smooth_local_ground_v8,export_s004_layers,export_final_sim,reproduce_s004_final,review_cloud_io}.py`, `continuous_ground_20261104_v7.json` | `tools/map/1109_pair360_v1/` 안, 이름 그대로 |
| `tests/map/test_<이름>.py` | `tests/map/1030_test_demo_sim_scripts.py`, `tests/map/1109_test_<이름>.py` |
| `sim_scenes/S004_ground_final/` | `sim_scenes/pair360_v1/`(로컬 `input/`, `review/*.npz`, `result/`도 옮깁니다) |

옮기는 순서입니다.

1. main을 병합합니다(이 정리가 main에 들어간 뒤).
2. 브랜치에서 새로 만든 도구에 처음 커밋한 날짜를 붙입니다. 예: `git mv tools/map/hfield_scene_import.py tools/map/1120_hfield_scene_import.py`. 시험은 `tests/<분야>/MMDD_test_<이름>.py`입니다.
3. 문서·코드 속 옛 경로를 바꿉니다. `git grep -nE "tools/demo/(run_route|_state_run|state_)|tools/description/fetch_|tools/map/(demo_sim|extract_pair360|build_continuous|reproduce_s004)|S004_ground_final|tests/map/test_"`로 남은 곳을 찾습니다.
4. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest tests/map -q`와 바꾼 실행기의 `--help`로 확인합니다.

2026-11-26에 열린 브랜치 `feat/sim-fault-injection`, `feat/localization-status-fields`를 시험 병합해 보면, main과 이미 충돌하는 파일이 29개이고 이 정리로 늘어나는 충돌은 3개입니다(`policies/route_walk/__init__.py`, `policies/urdf_v0/policy_io.yaml`의 경로 한 줄씩, `sim_scenes/README.md`). 그 밖에 두 브랜치는 새 도구 3개(`tools/demo/compare_traces.py`, `tools/map/hfield_scene_import.py`, `tools/map/synthetic_hfield_scene.py`, 모두 11-20)의 이름을 바꾸고, `sim_scenes/pair360_map_v3/`를 지도 v3 폴더(`sim_scenes/pair360_v3/` 아래)로 옮기면 됩니다.
