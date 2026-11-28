<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# P2.2 설계 검증

2026-11-28에 로컬 P2.1의 회로도·PCB를 기준으로 P2.2를 검증했습니다. Git에서 비교할 P2.1 커밋은 `fa2e99734cf4c6fe7818bf7381103dff9c950a9d`입니다. 아래 수치는 CAD와 제조 출력 검사 결과입니다.

| 검사 | 방법 | 결과 |
| --- | --- | --- |
| 회로도 ERC | KiCad 10.0.6, 프로젝트 기본 규칙, 모든 심각도 | 0건 |
| PCB DRC | 양면 GND 동박 재채움 후 저장, 모든 심각도와 모든 배선 오류 검사 | 0건 |
| PCB 미연결 | 재채움한 PCB에서 검사 | 0건 |
| 회로도–PCB 연결 대조 | 동일 프로젝트의 KiCad 회로도 대조 기능 | 0건 |
| 넷리스트 및 실장 상태 | 회로도 XML과 PCB의 전기 패드별 네트·DNP 대조, P2.1과 J1·J2 비교 | 일치. Nucleo 헤더 76개 위치 유지 |
| 제조 출력 | Gerbonara 1.6.3으로 7개 Gerber와 두 Excellon 파일을 독립 판독하고 앞·뒷면 렌더링 | 외곽 폐합. 도금홀 743개와 비도금홀 3개 전부 원본 좌표·지름과 일치 |

[ERC 원본](erc.json) · [DRC·미연결·대조 원본](drc.json) · [Gerber·드릴 ZIP](P2.2-gerber-drill.zip)

## 기판과 조립

외곽선 중심 기준 **121.00 × 124.00 mm**, FR-4 2층, 완성 두께 1.60 mm, **양면 각각 완성 동박 최소 70 µm**, 무연 HASL입니다. 견적서에 완성 동박 두께를 명시합니다. Gerber Job의 외접 치수 121.05 × 124.05 mm에는 외곽선을 그리는 펜 폭이 포함됩니다. Ø3.2 mm 비도금 고정홀 3개와 홀 중심의 양면 8 × 8 mm 동박·배선 금지 구역을 유지했습니다.

J17→F1→U6 배선 폭은 1.50 mm, U6→U14→TP1→CN7-6은 1.35 mm입니다. TP1에서 CN7-6까지 배선 길이는 4.031 mm입니다. GND의 주요 경로는 1.20–1.50 mm이고 양면에 GND 동박을 채웠습니다. J19–J22의 전원·디커플링·A측 선택 풀업이 전용 RS 전원에, ToF·BMI088 포트 1번이 Nucleo 3.3 V에 연결됐음을 확인했습니다.

기판에 풋프린트가 132개 있습니다. 미실장 23개, 고정홀 3개, 동박 테스트 포인트 3개를 제외하면 캐리어 실장 부품은 103개입니다. 패드 기준 관통홀 납땜 433곳과 J15의 표면실장 6곳(신호 4, 고정 탭 2)입니다. J11은 2.54 mm 1×9이며 기판 앞·뒷면과 하네스 양단에 1번을 표시합니다. J15는 뒷면 JST-GH 1.25 mm입니다. 하네스의 예비 접점 3·4번은 PCB에서 미연결입니다. J18 및 보조 회로는 기본 미실장입니다. [조립 안내](assembly.md) · [하네스 제작표](harnesses.md)

## 재현 및 제조 파일

프로젝트 디렉터리에서 KiCad 10.0.6 CLI로 실행합니다. 새 빈 출력 디렉터리 `fab`을 사용합니다.

```text
kicad-cli sch erc --format json --severity-all --exit-code-violations -o erc.json nucleo-shield.kicad_sch
kicad-cli pcb drc --format json --severity-all --all-track-errors --schematic-parity --refill-zones --save-board --exit-code-violations -o drc.json nucleo-shield.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts --no-protel-ext --check-zones --output fab/ nucleo-shield.kicad_pcb
kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm --excellon-separate-th --generate-report --report-path fab/drill-report.txt --output fab/ nucleo-shield.kicad_pcb
```

ZIP에는 Gerber X2 7개, 도금·비도금 드릴 2개, Gerber Job, 드릴 보고서, 제작 사양서가 있습니다. 드릴 좌표와 지름을 PCB 원본의 패드·비아와 개별 대조한 허용 오차는 0.00051 mm입니다. ZIP의 SHA-256은 `ecc040712c271a05d60f303bf74b3fc391511208bae31972713ecfd3a3f0d905`입니다.

## 발주 검토와 시제품 판정

J17 5.15 V에서 CN7-6의 계산 하한은 4.762 V로 목표까지 11.6 mV가 남습니다. RS 송신을 처음 허용하는 최악 조건에서 원격 SP3485 단자의 하한 여유는 3.8 mV입니다. 두 값은 계산서에 명시한 접촉저항·부하·온도 조건에 의존합니다. 설계팀이 발주를 결정할 때 ST-LINK를 포함한 U14 정상 합산 부하 ≤380 mA, 벅 개체 선별 및 어댑터·헤더 선실장 가능 여부를 함께 검토합니다.

시제품에서는 J17 5.15·5.20·5.25 V에서 실제 CN7-6/GND와 최장 센서 하네스 끝 전압, USB 연결·분리와 단일 전원 역급전, U6·U12·벅 온도, 보호 차단·복귀, 네 버스의 동시 4 Mbps를 측정합니다. 400 kHz I²C는 최장 하네스에서 상승 시간 300 ns 이하를 확인합니다. 측정 전 항목은 [전원 계산·시험표](power-validation.md)에 시험 조건과 합격 기준으로 기록했습니다.
