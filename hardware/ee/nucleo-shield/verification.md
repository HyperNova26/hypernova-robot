<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# P2.3 설계 검증

P2.3의 비교 기준은 P2.2 커밋 `b73f9d1`입니다. 검토할 회로도·PCB·전용 라이브러리·BOM·하네스 표·검사 보고서·제조 출력은 같은 Git 리비전에 있습니다. 전기적 합격 기준은 아래의 CAD 검사, 전원 계산, 시제품 시험으로 추적합니다. [P2.2 비교 기준](https://github.com/HyperNova26/hypernova-robot/commit/b73f9d1) · [전원 계산·시험표](power-validation.md)

## CAD 및 제조 출력 검사

| 검사 | 방법 | 결과 |
| --- | --- | --- |
| 회로도 ERC | KiCad 10.0.6 프로젝트 기본 규칙, 모든 심각도 | 0건 |
| PCB DRC | 양면 GND 동박을 재채워 저장한 뒤 모든 심각도와 모든 배선 오류 검사 | 0건 |
| PCB 미연결 | 동박 재채움 후 미연결 패드·네트 검사 | 0건 |
| 회로도–PCB 연결 대조 | 동일 프로젝트의 KiCad 회로도 대조 | 0건 |
| 넷리스트·실장 상태 | 회로도 XML과 PCB의 패드별 네트·부품값·DNP 대조, P2.2와 Nucleo J1·J2의 76개 위치 비교 | 전체 일치 |
| 제조 데이터 | Gerber 7개와 Excellon 2개를 Gerbonara로 판독하고 앞·뒷면을 렌더링. 외곽 폐합 및 원본 패드·비아 좌표와 드릴 지름 대조 | 양면 외곽·패드·배선·비아와 드릴 전체 일치. 도금홀 1,074개, 비도금홀 3개 |

[ERC 원본](erc.json) · [DRC·미연결·대조 원본](drc.json) · [Gerber·드릴 ZIP](P2.3-gerber-drill.zip)

GND 패드·배선·비아 791개가 J17-2와 연결됩니다. J9·J10 센서 리턴은 가까운 비아로 주 접지면에 연결합니다. 최종 PCB에는 0.60/0.30 mm 비아 522개와 1.10/0.60 mm 전력 비아 6개가 있습니다. 동일 층·넷·폭에서 양 끝 좌표까지 일치하는 중복 선분을 제거한 뒤 동박을 재계산했습니다. 85 °C에서 센서 3.3 V 양극 배선 강하는 동시 부하 모델 기준 J7–J10에서 4.88–8.73 mV, J11에서 4.45 mV입니다. [부하 조건과 리턴 예산](power-validation.md)

## 기판과 조립

외곽선 중심 치수는 **121.00 × 150.00 mm**입니다. FR-4 2층, 완성 두께 1.60 mm, 양면 각각 **완성 동박 최소 70 µm**, 무연 HASL로 제작 요청합니다. Ø3.2 mm 비도금 고정홀 3개의 양면 8 × 8 mm 동박·배선 금지 구역을 유지합니다. 각 도면의 외곽선 폭을 치수에 포함하는지 제조 CAM에서 확인합니다.

기판에는 풋프린트 153개가 있습니다. 기본 미실장 23개와 고정홀·동박 테스트 포인트를 제외한 캐리어 실장 부품은 124개입니다. 캐리어 기판의 수납땜은 관통홀 496곳, 표면실장 6곳입니다. 표면실장 검사 대상은 J15 JST-GH 1.25 mm 뒷면 커넥터의 신호 핀과 양쪽 고정 탭입니다. J11은 2.54 mm 1×9이고, PCB 양면·하네스 양단의 1번 표식을 맞춥니다. J15의 3·4번과 PA11/J18은 예비 항목입니다. J18과 보조 회로는 기본 미실장입니다. [조립 안내](assembly.md)

J19–J22는 완성 모듈 THVD1424EVM 4개를 사용합니다. 공급자에게 각 EVM의 RO 표시 LED 직렬 저항 **R3 제거**를 지정하고, RO와 외부 DE, VIO–VCC 연결, 20 Mbps 모드, Y/Z 내장 종단 설정을 확인합니다. 버스 반대쪽에는 120 Ω을 한 개씩 사용합니다. RS 전원·디커플링·A 풀업 옵션은 전용 +3V3_RS485로 공급하고, ToF·BMI088 1번은 Nucleo 3.3 V를 사용합니다. J23은 J14와 구별되는 **JST-XH 8핀**으로, 1 PG·2 EN·3 VIN·4 입력 GND·5 VOUT·6 출력 GND에 배선하고 7·8은 비웁니다. [모듈·짝 커넥터 BOM](modules-and-mates.csv) · [하네스 제작표](harnesses.md)

## 전원 계산과 실물 판정

J17 5.15 V에서 두 분기의 설계 입력전류는 합계 **1.17 A**입니다. U16·Q3/Q4가 입력을 공동 보호하고, J24의 6 V 부스트가 U6의 최대 드롭아웃을 반영한 후에도 272 mV의 여유를 확보합니다. U6→U14→TP1→CN7-6 구간은 1.35 mm이고, TP1–CN7-6은 4.03 mm입니다. 목표 전압은 Nucleo CN7-6과 CN7-8 GND 사이에서 측정합니다.

| 항목 | 계산 결과 | 판단 기준 |
| --- | ---: | --- |
| CN7-6 최대 정상 부하 | 4.842 V 하한 | 4.75 V까지 92 mV. J14-6의 CAN 부하를 포함해 U14 정상 ≤380 mA |
| U14 지속 전류 제한 | 394.4–493.6 mA | 최저점이 정상 380 mA보다 높고 최고점이 500 mA 이내 |
| J23 벅 모듈의 400 mA 부하 입력 | 3.931 V 하한 | 설계 하한 3.90 V, VIN 기동 임계 상한 3.60 V |
| 두 전원 정상 시 U13 RS 감시점 | 3.167 V 하한 | 최고 감시 임계 3.138 V 대비 29 mV |
| 최장 THVD1424EVM VCC/VIO | 첫 송신 허가 3.053 V, 정착 후 3.127 V | 모듈 하한 3.00 V까지 각각 53 mV, 127 mV |

이 수치는 완성 동박·하네스·접점 저항과 온도, 80% 이상 변환 효율을 전제로 합니다. TI 벅의 입력·부하 변화 사양은 제조사 대표 응용회로에 대한 값입니다. 소스 5.15 V에서 두 변환기가 함께 기동하는지와 R74 및 EVM 입력 커패시터의 과도응답은 실제 하네스에서 확인합니다. +25.2 V 오인가 때 R75의 전류 상한만으로 FET의 안전동작영역, TVS 에너지 및 F1 생존을 판정할 수 없습니다. 시험표의 별도 50.4 V는 개방전압·직렬 ≥27 Ω·≤1 ms 단발 발생기 조건입니다. [전원 계산·고장 시험 조건](power-validation.md) · [계산 재현 스크립트](check-power-margins.py)

발주 전에는 ST-LINK의 USB 분리·열거·디버그 상황을 포함해 실제 E5V 정상 합산 전류 ≤380 mA를 확인합니다. 시제품에서는 J17 **5.15·5.20·5.25 V** 각각에서 냉·온간 기동, 최장 센서 하네스 끝 전압, 보호 차단·복귀, USB 삽입·분리와 단일 전원의 역급전, U6·U12·양쪽 DC/DC·Q3/Q4의 온도를 측정합니다. 네 RS-485 버스를 동시에 4 Mbps로 운용하고, 400 kHz I²C는 최장 하네스에서 두 선의 상승 시간 ≤300 ns를 확인합니다. [시제품 시험 및 합격 기준](power-validation.md)

## 재현 및 제조 파일

프로젝트 디렉터리에서 KiCad 10.0.6 CLI로 실행합니다. 비어 있는 `fab` 디렉터리를 출력 대상으로 사용합니다.

```text
kicad-cli sch erc --format json --severity-all --exit-code-violations -o erc.json nucleo-shield.kicad_sch
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity --refill-zones --save-board --exit-code-violations -o drc.json nucleo-shield.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts --no-protel-ext --check-zones --output fab/ nucleo-shield.kicad_pcb
kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm --excellon-separate-th --generate-report --report-path fab/drill-report.txt --output fab/ nucleo-shield.kicad_pcb
python check-power-margins.py
```

제조 ZIP에는 Gerber X2 7개, 도금·비도금 드릴 2개, Gerber Job, 드릴 보고서, 제작 사양서가 있습니다. 드릴 좌표·지름 대조의 허용 오차는 0.00051 mm입니다. ZIP의 SHA-256은 `e1c6b98fba7d804547ce9b2772d2c5d4fc1fc337b0fcca5279fa0e84d7a37ba7`입니다.

제조 데이터 생성에 사용한 PCB 파일의 SHA-256은 KiCad가 Windows에서 저장한 CRLF 원본에서 `6831cdb0abe4548fe52633d82b4a5b9214819cddb8a2dd1590c9676dc3d24b97`, Git의 LF 원본에서 `95d18cdce6c9324d540b4ee2749037d07552fd0e337dfdab0f502bf498ab1301`입니다. 두 파일의 줄바꿈을 LF로 맞춰 전체 바이트 일치를 확인했습니다.
