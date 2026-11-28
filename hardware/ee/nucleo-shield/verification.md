<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# P2.1 설계 검증

2026-11-28 기준 검토본입니다. 121 × 108 mm, 1.6 mm, 2층 PCB이며, 실물 시제품의 전원 및 조립 시험은 남아 있습니다.

| 검사 | 환경과 범위 | 결과 |
| --- | --- | --- |
| 회로도 ERC | KiCad 10.0.6, 모든 심각도 | 0건 |
| PCB DRC | KiCad 10.0.6, 모든 배선 오류 및 심각도 | 0건 |
| PCB 미연결 | 동박 영역 채움 이후 검사 | 0건 |
| 회로도–PCB 대조 | DRC의 회로도 대조 옵션 적용 | 0건 |
| MCU 배선 | P2와 P2.1의 XML 네트리스트에서 J1·J2 76개 위치를 비교 | 사용 신호 36개 및 PA11 예비 위치 일치 |

J19–J22의 RO·DI·RSE와 A/B, J3–J6의 A/B/GND, U1의 74HC08 출력 핀, J11의 아홉 핀, J15의 SYNC·GND 배선을 대조했습니다. R30–R33과 R49–R56, J18 및 보조 회로는 회로도와 PCB 양쪽에서 DNP로 확인했습니다. J15의 3·4번은 회로도에서 미연결로 지정되어 있습니다.

공유 프로젝트의 검사 설정을 사용했습니다. 아래 명령을 프로젝트 디렉터리에서 실행해 [ERC](erc.json)와 [DRC](drc.json)를 재현할 수 있습니다.

```text
kicad-cli sch erc --format json --severity-all --exit-code-violations -o erc.json nucleo-shield.kicad_sch
kicad-cli pcb drc --format json --all-track-errors --schematic-parity --severity-all --exit-code-violations -o drc.json nucleo-shield.kicad_pcb
```

발주 판단에는 네 채널 동시 송신의 전원 예산과 최종 센서 전압 범위 확정이 필요합니다. 시제품에서 실부하 E5V와 3.3 V, 시동·차단·복귀, 4 Mbps 동시 송수신, 모듈 하네스 체결 여유를 검증합니다. [전원 계산·시험 조건](power-validation.md) · [조립 안내](assembly.md)
