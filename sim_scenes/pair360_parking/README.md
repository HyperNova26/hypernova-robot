# 기존 PAIR360 주차장 장면 보관 안내

2026-10-30 기준입니다. 현재 점군 변환 실행법은 [시뮬레이터 장면 변환 안내](../README.md)를 사용합니다. 이 폴더는 이전 PAIR360 전용 처리의 설정과 기록을 보존하는 곳입니다.

## 보존 범위

- [`frame.yaml`](./frame.yaml): T1 Sequence0 LIO map의 원점·ENU 근사 회전, 이전 ground·객체 분류, heightfield와 map2d 설정, 과거 실데이터 quick 결과의 변환 행렬을 보존합니다.
- `frame.yaml`의 `output.directory: ../PAIR360_demo/2026-10-26_v1`은 과거 경로입니다. 현재 스크립트는 이 값을 읽지 않습니다.
- `data/PAIR360_demo/261026_1200_v0/`와 `data/PAIR360_demo/261026_1800_v1/` 등 기존 로컬 결과 및 이 장면 폴더에 있는 로컬 산출물은 보존합니다. 생성 데이터를 Git에 추가하지 않습니다.
- 이전 heightfield, ground·cars·other 점군, Nav2 지도, SLAM 인계 자료는 당시 구현과 설정으로 만든 기록입니다. 현재 두 스크립트의 결과나 검증 증거로 해석하지 않습니다.

기존 Python 처리 구현과 그 회귀시험은 제거되었습니다. 현재 변환기는 입력의 유한한 XYZ 전체를 voxel 점유로 내보내며, 이 설정이나 pose 파일 없이 실행합니다. ground·차량 분류와 heightfield 생성은 제공하지 않습니다. 새 결과는 `sim_scenes/MMDD_demo_whole/`에 만들고 기존 결과를 덮어쓰지 않습니다. 분해 스크립트는 날짜별 빈 출력 폴더만 준비하며 분해 기능은 미구현입니다.

지면 분리와 이후 차량·기타 객체 분류·분리 과정은 미완료입니다. 기존 quick 산출물의 존재는 지면 분리 정확도나 후속 객체 분류 정확도를 입증하지 않습니다. 이 과정의 구현·개선과 실제 PAIR360 데이터 검증은 **S-004 후속 작업**에서 다루며, 현재 도구의 범위와 실행법은 [시뮬레이터 장면 변환 안내](../README.md)를 따릅니다.

현재 사용자가 지정한 입력은 `data/PAIR360_data/T1_Parking_and_OpenTheater/T1_parking_Seq0_demo.bin`입니다. 원시 데이터는 읽기만 하며 native BIN의 CloudCompare 변환도 사본에서 수행합니다. 컨테이너에서는 저장소 mount의 `/workspace/hypernova/data/`로 접근합니다. `/data` mount와 `HN_DATA_DIR`은 [Docker 안내](../../docker/README.md#컨테이너-안에서-알아-둘-것)를 따릅니다.

## 출처와 라이선스

원본은 Geunu Kim, Daeho Kim, Jaeyun Jang, Hyoseok Hwang의 *PAIR360: A Paired Dataset of High-Resolution 360° Panoramic Images and LiDAR Scans*, IEEE RA-L, 2024입니다. [논문](https://doi.org/10.1109/LRA.2024.3460418), [데이터 및 ODbL 안내](https://airlabkhu.github.io/PAIR-360-Dataset/)를 확인합니다.

PAIR360 데이터의 라이선스는 ODbL 1.0입니다. 파생 지형·지도·pose 자료를 공유할 때 원저자·논문·원본 위치·변경 내용과 적용 조건을 확인합니다. 기존 결과의 `ATTRIBUTION.txt`는 해당 결과와 함께 보존합니다. 저장소 도구·설정의 Apache-2.0, 문서의 CC BY 4.0과 데이터 라이선스를 구분합니다.
