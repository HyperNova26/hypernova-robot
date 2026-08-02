# Simulation scenes

시뮬레이터에서 쓰는 환경과 검증 시나리오를 둡니다.

- 계단, 경사, 요철 같은 검증용 world와 scene
- 시험 시작 상태, 목표와 합격 기준을 담은 scenario
- scene 전용 texture, model과 작은 fixture
- simulator별 parameter 근거와 알려진 한계

로봇 본체의 형상과 joint 정의는 [`description/`](../description/)을 기준으로 씁니다. ROS 2 node, launch, simulator adapter가 package 형태라면 [`ros_pkgs/`](../ros_pkgs/)에 둡니다.

학습 log, checkpoint, 대규모 recording, 매 실행 결과는 커밋하지 않습니다. 기준 결과가 필요하면 요약 지표만 남기고 어떤 commit과 설정에서 나온 숫자인지 적습니다.
