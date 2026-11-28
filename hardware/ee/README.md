<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# HyperNova Nucleo 캐리어 P2.2

2026-11-28 시제품 발주 전 설계 검토본입니다. NUCLEO-G474RE가 다리별 RS-485 버스 4개로 모터 12대를 제어합니다. KiCad 10.0.6에서 [전용 라이브러리를 포함한 프로젝트](nucleo-shield/nucleo-shield.kicad_pro)를 엽니다.

J17에는 부하가 걸린 상태에서 5.15–5.25 V인 안정화 전원을 연결합니다. F1 뒤에서 E5V와 RS-485 벅 입력을 분기하고, J19–J22의 모듈에는 전용 3.3 V를 공급합니다. Nucleo와 모듈의 GND는 공통입니다. 두 전원의 상태, 펌웨어의 공통 허용 신호와 해당 채널의 DE가 모두 송신을 허용해야 모듈 드라이버가 켜집니다. J7–J11의 센서 전원은 Nucleo 3.3 V입니다.

J14의 CAN FD 모듈을 통해 Jetson에 통신하고, 외장 션트와 J13의 INA228으로 얻은 측정값을 Jetson의 배터리 잔량 표시에 사용합니다. J15는 라이다 동기 입력이고 J16은 필수 경고음용 피에조입니다. 모터 전력·퓨즈·비상 차단은 외부 하네스에 두며, PA11의 J18은 기본 미실장입니다.

| 검토 자료 | 확인할 내용 |
| --- | --- |
| [전원 계산서와 시제품 시험표](nucleo-shield/power-validation.md) | F1·U6·U14 정격, 배선과 접촉저항, J17 하한의 여유, USB 및 단일 전원 시험 |
| [KiCad 및 제조 파일 검증](nucleo-shield/verification.md) | 검사 환경과 결과, 동박 사양, Gerber·드릴 검토본 |
| [캐리어 BOM](nucleo-shield/carrier-bom.csv) · [구매 BOM](nucleo-shield/modules-and-mates.csv) | 실장·DNP, 완성 모듈, 커넥터와 하네스 부품의 구매 조건 |
| [조립 안내](nucleo-shield/assembly.md) · [하네스 제작표](nucleo-shield/harnesses.md) | 조립면, 핀 순서, 선경·길이, 종단·센스선 보호 |

발주 결정은 설계팀 검토 후 진행합니다. 시제품 전원과 통신의 실측 결과를 양산 판단에 사용합니다. 전자 설계에는 CERN-OHL-S-2.0, 문서에는 CC BY 4.0을 적용합니다. [저장소 라이선스](../../LICENSE.md)
