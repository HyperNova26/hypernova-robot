# Description

실기와 시뮬레이션이 함께 쓰는 로봇 형상과 구조 정의를 둡니다.

Fusion·KiCad 설계 원본과 부품 선정 기록은 각 도구와 Notion에서 관리합니다. 여기에는 ROS 2와 시뮬레이터가 직접 읽는 최종 산출물만 둡니다.

## 포함하는 것

- URDF·Xacro와 frame, joint, transmission 정의
- visual·collision mesh
- joint limit, 관성, 센서 pose처럼 모델을 재현하는 설정
- source revision, export 도구와 단위를 설명하는 문서

## 기본 규칙

- 같은 기체 정의를 실기와 시뮬레이션이 함께 씁니다.
- mesh에는 단위와 좌표축을 적고, visual인지 collision인지 구분합니다.
- 생성 파일은 손대지 말고, 원본 위치와 생성 방법을 남깁니다.
- Fusion·KiCad 원본, 개인 작업 export, 제조 중간 산출물은 커밋하지 마세요.
- 대형 바이너리를 추가하기 전에 [저장소 정책](../docs/development/repository-policy.md)을 보세요.

세부 디렉터리와 ROS 2 package 형식은 첫 기체 모델을 넣을 때 정합니다. 빈 구조를 미리 만들어 두지 않습니다.
