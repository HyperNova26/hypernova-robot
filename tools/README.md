# Tools

여러 사람이 반복해서 쓰는 개발·검증·변환 도구를 둡니다.

도구에는 이 정도를 같이 적습니다.

- 목적과 입력·출력
- 필요한 환경과 의존성 버전
- 사용 예시와 실패했을 때 되돌리는 방법

개인 경로가 박힌 일회성 script, 비밀정보, 생성된 binary는 넣지 마세요. 특정 패키지에서만 쓰는 도구는 그 패키지 가까이에 두고, 여러 영역에서 같이 쓰게 되면 그때 이 디렉터리로 올립니다.

## 맵 장면 변환

2026-10-30 기준입니다. [`map/`](./map/)의 `.sh`는 Python 실행 환경을 선택하는 진입점이며, 실제 구현은 같은 이름의 `.py`에 있습니다.

| 도구 | 현재 동작 |
| --- | --- |
| `demo_sim_converter.sh` / `demo_sim_converter.py` | 전체 유한 XYZ 점군을 분류 없이 voxel화하여 `sim_scenes/MMDD_demo_whole/`에 Isaac USD·MuJoCo XML·metadata를 만듭니다. |
| `demo_sim_disassembler.sh` / `demo_sim_disassembler.py` | 입력 파일을 확인하고 `sim_scenes/MMDD_demo_disassembled/` 빈 폴더만 만듭니다. |

**ground 분리와 이후 cars·other 객체 segmentation 과정은 미완성입니다. S-004에서 구현·개선하고 실제 PAIR360 데이터로 검증해야 합니다.** 전체 장면 변환이나 빈 폴더 생성은 segmentation 완료를 의미하지 않습니다. 인수·의존성·좌표계·출력 보존 규칙은 [시뮬레이터 장면 변환 안내](../sim_scenes/README.md)를 따릅니다.
