# Policies

로봇의 학습 기반 policy를 만들고 검증하는 코드와 설정을 둡니다.

## 포함하는 것

- 학습·평가·export 코드
- 재현 가능한 hyperparameter와 환경 설정
- 관측, 행동, reward와 종료 조건 정의
- 평가 시나리오와 기준 결과 요약
- 외부 dataset·checkpoint의 출처, 버전과 checksum

ROS 2 inference node와 배포용 wrapper는 [`ros_pkgs/`](../ros_pkgs/)에 두고, 학습·평가용 scene은 [`sim_scenes/`](../sim_scenes/)에 있는 걸 씁니다.

dataset, checkpoint, model weight, 실행 log는 여기에 커밋하지 않습니다. 외부 Git 저장소를 통째로 써야 할 때만 submodule로 commit을 고정하고, 나머지는 어디에 있고 어떻게 재현하는지만 적어 둡니다.

세부 디렉터리는 첫 policy를 구현할 때 만듭니다. 빈 학습 구조를 미리 깔아 두지 않습니다.
