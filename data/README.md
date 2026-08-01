# Data manifests

원시 데이터를 두는 곳이 아닙니다. 외부에 보관한 rosbag, MCAP, point cloud, 영상, dataset을 다시 찾아 쓸 수 있도록 manifest만 둡니다.

manifest에는 최소한 다음을 적습니다.

- 데이터 이름과 용도
- 원본 URL 또는 내부 저장 위치
- 수집일, 사용한 장비와 calibration
- 파일 크기와 SHA-256
- 라이선스와 공개 범위
- 재생 또는 전처리 명령

작은 test fixture가 필요하면 원본을 줄여 `tests/data/`에 두고 출처와 기대 결과를 함께 적습니다. 자세한 기준은 [저장소 정책](../docs/development/repository-policy.md)에 있습니다.
