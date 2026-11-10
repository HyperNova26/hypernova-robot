# 문서 색인

2026-10-30 기준입니다.

## 프로젝트

- [프로젝트 범위](./project-scope.md)
- [아키텍처](./architecture/README.md)

## 개발

- [개발 시작 안내](./development/getting-started.md)
- [Docker 개발 환경](../docker/README.md) — 호스트 준비, 이미지, `./docker/hn` 사용법
- [빠른 시작 — 보행](./development/quickstart-locomotion.md) — `hn:sim`에서 학습, ONNX export, onnxruntime 실행
- [빠른 시작 — 인지·SW](./development/quickstart-perception.md) — `hn:ros`에서 LIO, 시각화, 컨테이너 사이 통신
- [공용 Python 환경](./development/python-env.md)
- [시뮬레이터 장면 변환 안내](../sim_scenes/README.md) — `.sh` 실행기·`.py` 구현, 기본 0.5 m 전체 점군 voxel 변환과 빈 분해 출력 폴더 준비
- [기존 PAIR360 주차장 장면 보관 안내](../sim_scenes/pair360_parking/README.md)
- [저장소 및 데이터 정책](./development/repository-policy.md)
- [라이선스 정책](../LICENSE.md)

지면 분리와 후속 차량·기타 객체 분류·분리는 미완료입니다. 구현·개선과 실제 PAIR360 데이터 검증은 S-004 후속 작업에서 다룹니다. 현재 전체 점군 변환과 빈 출력 폴더 생성은 이 과정의 완료를 의미하지 않습니다.

## 운용

- [안전 지침](./operations/safety.md)

## 결정과 근거

- [ADR 목록](./decisions/README.md)
- [GitHub 저장소 설정](./governance/github-settings.md)

## 문서를 쓸 때

- 언제 기준의 내용인지 드러나게 씁니다.
- 명령, 설정, 측정값에는 실행 환경과 단위를 붙입니다.
- 결론만 남기지 말고 왜 그렇게 정했는지, 무엇이 아직 불확실한지도 적습니다.
- 낡은 문서는 지우기 전에 대신 볼 문서를 연결합니다.
