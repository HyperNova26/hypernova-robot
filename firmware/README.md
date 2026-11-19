# Firmware

MCU, 모터 컨트롤러, 센서 인터페이스처럼 보드에 올라가는 저수준 소프트웨어를 둡니다.

target마다 가능하면 이만큼은 남깁니다.

- 지원 보드와 하드웨어 revision
- toolchain과 버전
- build, flash, 복구 절차
- pinout, bus ID, 통신 protocol과 timing
- bench test 결과
- watchdog, safe state, fault code

빌드된 binary와 개인 IDE 설정은 커밋하지 않습니다. release에 binary가 필요하면 source commit, toolchain, checksum, 지원 보드 revision을 같이 배포합니다.

## Target

| 디렉터리 | 보드 | 상태 (2026-11-19) |
| --- | --- | --- |
| [nucleo-g474-motor-test](nucleo-g474-motor-test/README.md) | NUCLEO-G474RE + RS-485 트랜시버 + GO-M8010-6 최대 3대 | 1차 PoC 벤치 펌웨어. 빌드와 host test만 확인, 실물 미시험 |
