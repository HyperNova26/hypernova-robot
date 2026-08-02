# 저장소 및 데이터 정책

Git 기록을 가볍게 두고, 파일을 어디에 둘지 매번 고민하지 않으려고 적어 둔 규칙입니다.

## Git에 넣는 것

- 사람이 작성한 소스 코드와 스크립트
- 재현에 필요한 설정, launch, calibration과 작은 test fixture
- URDF/SDF/MJCF와 실행에 필요한 mesh
- 결정 기록, 시험 방법, 검증 결과 요약

## Git에 넣지 않는 것

- `build/`, `install/`, `log/`와 컴파일 산출물
- 원시 rosbag, MCAP, PCD/PLY, 장시간 센서 영상
- 학습 checkpoint, 모델 weight, 실험 실행 결과
- Fusion·KiCad의 설계 원본, 개인 export와 CAD·EDA 중간 산출물
- 비밀키, token, 장비 계정, 개인 `.env`
- 개인 임시 export, IDE 설정, CAD·EDA lock·backup 파일

작은 회귀시험 데이터가 꼭 필요하면 `tests/data/` 아래에 목적과 출처를 적고 리뷰를 받습니다.

## 대형 파일

파일이 10 MiB를 넘거나 자주 바뀌는 바이너리라면, 커밋하기 전에 어디에 둘지부터 정합니다.

1. 실행에 정말 필요한 파일인지 되짚어 봅니다.
2. 원시 데이터라면 밖에 두고, 그걸 쓰는 package나 policy 가까이에 출처와 버전, checksum을 적습니다.
3. 배포용 산출물이라면 GitHub Release asset을 씁니다.
4. 독립된 외부 Git 저장소가 필요하면 submodule로 commit을 고정합니다.
5. 실행에 필요한 대형 mesh라면 Git LFS를 쓸지 먼저 정하고 `.gitattributes`에 추가합니다.

나중에 LFS로 옮기려면 기록을 다시 써야 합니다. 첫 대형 mesh를 넣기 전에 정하는 편이 낫습니다.

## 설정과 calibration

- 어떤 기체·센서 revision에 적용되는 설정인지 알아볼 수 있게 적습니다.
- 물리량에는 단위를, pose에는 parent/child frame과 좌표축 규약을 붙입니다.
- 비밀값과 네트워크 자격 증명은 설정 파일에서 빼냅니다.
- runtime 설정은 그걸 쓰는 package 가까이에 둡니다.

## 생성 파일

생성 파일은 직접 손대지 않습니다. 커밋해야 할 사정이 있다면 외부 원본의 위치와 revision, 생성 명령, 도구 버전을 함께 남깁니다.

## 의존성

외부 코드는 복사해 넣지 말고 package manager나 `.repos`, submodule로 버전을 고정합니다. 외부 asset과 코드에는 출처, 버전 또는 commit, 라이선스를 적습니다.

## 라이선스

- 새 파일에는 [저장소 라이선스 정책](../../LICENSE.md)에 맞는 라이선스를 적용합니다.
- description에 넣는 HYPERNOVA 형상·제조 산출물에는 CERN-OHL-S-2.0 표기와 외부 원본 위치를 남깁니다.
- 서드파티 파일은 원래 라이선스와 저작권 고지를 그대로 둡니다.
- HYPERNOVA 이름과 로고, 배너를 외부 자료에 넣기 전에는 별도 사용 권한을 확인합니다.
