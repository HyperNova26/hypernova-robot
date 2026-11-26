# Tools

여러 사람이 반복해서 쓰는 개발·검증·변환 도구를 둡니다.

도구에는 이 정도를 같이 적습니다.

- 목적과 입력·출력
- 필요한 환경과 의존성 버전
- 사용 예시와 실패했을 때 되돌리는 방법

개인 경로가 박힌 일회성 script, 비밀정보, 생성된 binary는 넣지 마세요. 특정 패키지에서만 쓰는 도구는 그 패키지 가까이에 두고, 여러 영역에서 같이 쓰게 되면 그때 이 디렉터리로 올립니다.

## 이름 규칙

2026-11-26(S-018)부터 `tools/`와 `tests/`의 코드는 버전 번호 대신 **처음 저장소에 들어온 날짜**를 앞에 붙입니다. 날짜는 그 파일이 처음 커밋된 날(author date, `git log --diff-filter=A --follow`)입니다.

- **혼자 실행하는 파일**: `MMDD_이름.확장자`. `.sh` 실행기와 `.py` 구현처럼 짝인 파일은 같은 이름을 씁니다.
- **서로 import하는 여러 파일**: 폴더에 날짜를 붙이고(`MMDD_이름/`) 안의 파일 이름은 그대로 둡니다. Python은 숫자로 시작하는 모듈을 `import` 문으로 부를 수 없기 때문입니다.
- **분야 폴더**(`map/`, `demo/`, `description/`)에는 날짜를 붙이지 않습니다.
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
| 11-09 | `map/1109_s004_ground/` | PAIR360 지면(S-004). v7 표면 → v8 국소 보정 → 전달본, 그리고 v9(수관 아래 바닥) |
| 11-24 | `map/1124_pair360_v3/`, `map/1124_build_pair360_v3.{sh,py}` | 두 점군을 합친 지도 map_v3, 지형 mesh_v3, Nav2 지도(1~11단계) |
| 11-24 | `map/1124_check_nav2_keepout.{sh,py}` | Nav2 비용지도에서 금지 구역이 막히는지 검사 |

시험은 `tests/map/1030_test_demo_sim_scripts.py`(변환기), `tests/map/1109_test_*.py`(데모 자르기, S-004 지면·장면, 점군 입출력)입니다.

### 지운 코드 (2026-11-26)

| 코드 | 이유 |
| --- | --- |
| `map/demo_sim_disassembler.{sh,py}`와 그 시험 | 빈 출력 폴더만 만드는 미구현 틀이었습니다. 지면·물체 분리는 `1109_s004_ground/`와 `1124_pair360_v3/`가 합니다 |

## PAIR360 지도 v1·v2·v3

지도와 지형 파일에는 버전 번호를 그대로 씁니다. 좌표계는 모두 `pair360_map`(PAIR360 T1 원시 XYZ, m, z 위쪽)입니다. 점군과 메시는 Git에 넣지 않고 팀 Drive `14. AI Team/`의 `data/map_vN/`, `meshes/`에 둡니다.

| 버전 | 입력 | 지도(점군) | 지형(메시) | 만든 코드 |
| --- | --- | --- | --- | --- |
| v1 | PAIR360 `pc_v1`만 | pc_v1 지면 v1 분할(지면 1,346,917점, 나머지 6,404,411점) | mesh_v1(2026-11-16): 지면 v1 + 나무·구조물 | 지면: `map/1109_s004_ground/`(v9). 장면: 저장소 밖 |
| v2 | `pc_v1` + 2026-11-15 팀 촬영 `pc_v2`, **pc_v1 우선 병합** | map_v2(2026-11-16) | mesh_v2(2026-11-16) | 저장소 밖 |
| v3 | `pc_v1` + `pc_v2`, **pc_v2 우선 병합** | map_v3(2026-11-18) | mesh_v3(2026-11-18), Nav2 지도(2026-11-24) | `map/1124_pair360_v3/` |

- v2는 "추가 촬영본만"이 아닙니다. 11-15 촬영본만으로 만든 지도·메시는 없습니다.
- mesh_v1 장면과 v2를 만든 코드는 11-16의 이전 파이프라인입니다. v3가 대체해서 이 저장소에는 넣지 않았습니다. 기록용 사본은 Drive의 해당 버전 폴더에 함께 둡니다.
- 지면 v1(v9)은 v3 2단계의 입력이기도 합니다(`map/1109_s004_ground/continuous_ground_20261109_v9.json`).
