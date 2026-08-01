# 저장소 및 데이터 정책

Git 기록을 가볍게 유지하고, 어떤 파일이 어디에 있어야 하는지 헷갈리지 않게 하는 것이 목적입니다.

## Git에 넣는 것

- 사람이 작성한 소스 코드와 스크립트
- 재현에 필요한 설정, launch, calibration과 작은 test fixture
- 기준본으로 정한 CAD·EDA 원본, BOM, 제작 문서
- URDF/SDF/MJCF와 실행에 필요한 mesh
- 결정 기록, 시험 방법, 검증 결과 요약

## Git에 넣지 않는 것

- `build/`, `install/`, `log/`와 컴파일 산출물
- 원시 rosbag, MCAP, PCD/PLY, 장시간 센서 영상
- 학습 checkpoint, 모델 weight, 실험 실행 결과
- 비밀키, token, 장비 계정, 개인 `.env`
- 개인 임시 export, IDE 설정, CAD·EDA lock·backup 파일

작은 회귀시험 데이터가 필요하면 `tests/data/` 아래에 목적과 출처를 적고 리뷰를 받습니다.

## 대형 파일

파일이 10 MiB를 넘거나 자주 바뀌는 바이너리라면 커밋 전에 어디에 둘지 정합니다.

1. 실행에 꼭 필요한 파일인지 확인합니다.
2. 원시 데이터라면 외부에 두고 [`data/`](../../data/)에 manifest만 커밋합니다.
3. 배포용 산출물이라면 GitHub Release asset을 씁니다.
4. 버전 관리가 필요한 CAD·EDA 바이너리라면 Git LFS 사용 여부를 먼저 정하고 `.gitattributes`에 추가합니다.

나중에 LFS로 옮기면 기록을 다시 써야 하므로, 첫 대형 CAD 파일을 넣기 전에 정하는 편이 낫습니다.

## 설정과 calibration

- 어떤 기체·센서 revision에 적용되는 설정인지 알 수 있게 적습니다.
- 물리량에는 단위를, pose에는 parent/child frame과 좌표축 규약을 적습니다.
- 비밀값과 네트워크 자격 증명은 설정 파일에서 분리합니다.
- runtime 설정은 그것을 쓰는 package 가까이에 둡니다.

## 생성 파일

생성 파일을 커밋해야 한다면 원본, 생성 명령, 도구 버전을 함께 남깁니다. 생성 파일을 직접 고치지 않습니다.

## 의존성

외부 코드를 복사해 넣기보다 package manager나 `.repos` 같은 manifest로 버전을 고정합니다. 외부 asset과 코드는 출처, 버전 또는 commit, 라이선스를 기록합니다.
