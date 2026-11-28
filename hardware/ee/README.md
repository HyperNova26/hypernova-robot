# NUCLEO 실드 PCB · 1차 PoC

KiCad에서 [nucleo-shield.kicad_pro](nucleo-shield/nucleo-shield.kicad_pro)를 엽니다. 12모터용 P2.1 Nucleo 캐리어의 회로도와 121 × 108 mm 2층 베어 PCB를 포함합니다. J17에는 과전압 차단과 전류 제한을 적용합니다. 외부 3.3 V RS-485 모듈 네 개는 J19–J22에 연결해 J3–J6에서 다리별 독립 반이중 A/B/GND 버스를 제공합니다. J11은 BMI088 하네스용 2.54 mm 1×9 수헤더, J15는 LiDAR 동기 신호용 JST GH 4핀 SMT입니다. J18 비상정지 보조접점 회로는 선택 실장이고, 모터 전원 비상 차단은 외부 하드웨어가 수행합니다. [조립·하네스 안내](nucleo-shield/assembly.md)

P2.1은 발주 전 검토본입니다. 4채널과 센서의 동시 부하가 J17 전원 예산을 넘으므로 전원 구성을 확정해야 합니다. [전원 계산과 시제품 시험](nucleo-shield/power-validation.md) · [모듈·짝 커넥터 BOM](nucleo-shield/modules-and-mates.csv) · [KiCad 검증 결과](nucleo-shield/verification.md)

배터리 측정은 J13의 외장 INA228을 사용합니다. SOC 표시는 Jetson과의 소프트웨어 연동 요구사항입니다. J16에는 3.3 V PWM으로 구동하는 외부 수동 피에조를 연결할 수 있습니다.

프로젝트 설정(`.kicad_pro`), 회로도(`.kicad_sch`), 보드(`.kicad_pcb`)를 Git으로 함께 관리합니다. 개인 화면 설정, 잠금 파일, 자동 백업은 Git에서 제외합니다.

2026-11-28 기준 KiCad 10.0.6으로 확인했습니다. 프로젝트의 로컬 심볼과 풋프린트 라이브러리는 회로도·PCB와 함께 사용합니다. 전자 설계에는 CERN-OHL-S-2.0, 이 안내에는 CC BY 4.0을 적용합니다. [라이선스 정책](../../LICENSE.md)
