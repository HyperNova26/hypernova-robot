<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Nucleo 캐리어 조립과 하네스

2026-11-28 기준 P2.1 시제품 조립 안내입니다. 2층 베어 PCB를 발주하고 캐리어 커넥터와 필수 부품을 손납땜합니다. RS-485 트랜시버와 외부 센서는 커넥터나 헤더가 실장된 완성 모듈과 변환 하네스로 연결합니다. 전원과 하네스는 이 문서의 핀 배정을 적용합니다. [Notion EE 요구사항][requirements]

## 기판과 실장면

기판 외곽은 **121 × 108 mm**이고, 두께는 **1.6 mm**입니다. J19–J22의 하네스와 부품 간격을 확보하기 위해 기존 P2보다 아래쪽을 9 mm 늘렸습니다. 앞면에는 Nucleo용 J1·J2를, 뒷면에는 나머지 커넥터와 부품을 실장합니다. 모듈 케이블의 삽입·탈착과 굽힘에 필요한 프레임 여유는 실물로 확인합니다.

CN7·CN10 소켓의 1번 간격은 60.96 mm이고, 각 소켓은 2.54 mm 피치입니다. 실장면에서 ST-LINK가 위를 향할 때 두 소켓 모두 1번은 왼쪽이고 2번은 오른쪽입니다. 3개의 Ø3.2 mm 고정홀을 MB1367 위치에 맞췄으며, 각 홀 중심의 양면 **8 × 8 mm** 구역에 배선·비아·동박 채우기를 제한했습니다. 소켓은 Samtec `SSW-119-03-G-D` 기준입니다. 실제 Nucleo·소켓·지지대를 결합해 핀 삽입 깊이와 부품 간섭을 확인하고, 나사 머리와 와셔의 외곽이 동박 금지 영역 안에 드는지 확인합니다. [ST MB1367 설계 원본][mb1367] · [Samtec SSW 소켓][ssw]

## 캐리어 커넥터

표의 핀은 **캐리어 풋프린트의 1번부터** 나열합니다. 하네스는 기판 실크의 핀 1 표시와 모듈의 신호명을 기준으로 제작합니다. 커넥터를 뒷면에 실장할 때도 핀 번호를 그대로 사용합니다.

| 캐리어 | 커넥터 및 짝 | 핀 1부터 순서 |
| --- | --- | --- |
| J1, J2 | 2.54 mm 2×19 암소켓, Nucleo CN7·CN10 하부 헤더와 결합 | 회로도의 CN7·CN10 핀 번호 |
| J3–J6 | 측면 삽입형 JST XH `S3B-XH-A`, `XHP-3` | RS-485 A, RS-485 B, 신호 GND |
| J7–J10 | 측면 삽입형 JST PH `S5B-PH-K-S`, `PHR-5` | 3.3 V, GND, `TOF_SCL`, `TOF_SDA`, 채널별 XSHUT |
| J11 | 2.54 mm 1×9 수직 수헤더 Harwin `M20-9990945`, 암 하우징 `M20-1060900` 및 `M20-1180042` 단자 | 3.3 V, GND, SCK, MOSI, MISO, CSB1, CSB2, INT1, INT3 |
| J13 | JST PH `B4B-PH-K-S`, `PHR-4` | 3.3 V, GND, `LOCAL_SCL`, `LOCAL_SDA` |
| J14 | JST XH `B5B-XH-A`, `XHP-5` | 3.3 V, GND, `CAN_TX`, `CAN_RX`, `CAN_STB` |
| J15 | 1.25 mm 측면 삽입형 SMT JST GH `SM04B-GHS-TB`, `GHR-04V-S` 및 `SSHL-002T-P0.2` 단자 | LiDAR `EX_OUT`, `EX_OUT_GND`, 예비 `EX_IN`, 예비 `EX_IN_GND` |
| J16 | JST PH `B2B-PH-K-S`, `PHR-2` | 3.3 V, `BUZZER_SINK` |
| J17 | 상부 삽입형 JST XH `B2B-XH-A`, `XHP-2` | 외부 안정화 5.15–5.25 V, GND |
| J18 | 기본 미실장, 상부 삽입형 JST PH `B3B-PH-K`, `PHR-3` | 비상정지 NC 보조접점, 미연결, GND |
| J19–J22 | 상부 삽입형 JST XH `B7B-XH-A`, `XHP-7` 및 `SXH-001T-P0.6` 단자(22–28 AWG) | 3.3 V, GND, 모듈 RO, 모듈 DI, 모듈 RSE, RS-485 A, RS-485 B |

PH는 2.00 mm, XH는 2.50 mm, GH는 1.25 mm 피치입니다. ToF, RS-485 모듈, 모터 하네스 양쪽 끝에 채널 번호를 표시합니다. 전선 규격에 맞는 압착 단자나 기성 피그테일을 씁니다. J11은 방향 키가 없어 하네스 양쪽에 1번을 표시하고 전원을 넣기 전 3.3 V와 GND의 도통을 확인합니다. [JST PH 제품 정보][ph] · [JST XH 데이터시트][xh] · [Harwin 수헤더][imu-header] · [Harwin 암 하우징][imu-housing] · [Harwin 압착 단자][imu-contact]

J15는 표면실장 커넥터입니다. 기판 뒷면에 GH 4핀의 신호 패드와 금속 고정 탭을 납땜하고, 확대 검사와 하네스 도통 검사를 합니다. 첫 시제품은 1·2번만 사용하며, 3·4번은 예약합니다. [JST GH 제품 정보][gh]

## 외부 5 V 전원

J17에는 **실부하에서 커넥터 기준 5.15–5.25 V인 안정화 전원**을 연결합니다. 배터리는 외부 DC/DC 전원과 모터 전원 하네스에 연결합니다. J17 입력은 F1을 거쳐 U6으로 들어갑니다. U7 전압 비교 회로는 보조 전압이 설정 범위를 벗어나면 U6 출력을 끄고, U6는 역극성 보호와 전류 제한을 제공합니다. D9는 입력 펄스용 TVS입니다. F1의 1 A 정격은 입력측 보조 보호에 적용됩니다. [ADI LT3086 데이터시트][lt3086] · [Littelfuse P6KE 데이터시트][p6ke]

비교기 보조 전원의 설계 기준은 과전압 **5.20 V**, 저전압 **4.36 V**입니다. J17에서 실제로 보이는 차단·복귀 전압에는 F1, D10, R39의 전압 강하가 반영됩니다. U6의 설정값은 출력 약 **4.95 V**, 정상 상태 전류 제한 약 **400 mA**입니다. 전류 제한 보상 회로 때문에 시동이나 급격한 부하 변화에서 전류가 순간적으로 설정값을 넘을 수 있어 파형도 확인합니다. TP1은 Nucleo CN7 6번으로 공급되는 E5V, TP2는 3.3 V, TP3은 GND입니다. 실부하의 E5V가 **4.75–5.25 V** 범위를 유지하고, 정상 동작 전류가 실측 전류 제한점보다 낮으며 ST의 **500 mA** 이내인지 확인합니다. [ADI LT3086 데이터시트][lt3086] · [ST UM2505 표 7 및 §7.4.1][nucleo]

Nucleo JP5는 **5–6번 E5V**에 두고, U12가 3.3 V를 만드는 SB5 연결을 유지합니다. 먼저 외부 전원을 켜고 Nucleo의 녹색 전원 LED LD3을 확인한 뒤 ST-LINK USB를 꽂습니다. [ST UM2505 §7.4][nucleo]

## 선택 실장하는 비상정지 보조접점

모터 전원 차단은 외부 비상정지 하드웨어에서 독립적으로 수행합니다. 상태 입력이 필요한 경우 J18과 R28·R29·D7·D8·C4를 함께 실장하고, 외부의 **무전압 NC 보조접점**을 J18의 1번과 3번에 연결합니다. 약 0.3 mA의 저레벨 신호에 적합한 접점을 사용하고, 연결 전에 도통과 외부 전압이 걸려 있지 않은지 확인합니다. 접점이 닫히면 PA11이 저레벨이고, 비상정지로 접점이 열리거나 하네스가 분리되면 고레벨입니다. 펌웨어에서 이 옵션을 사용할 때는 비상정지나 배선 분리를 감지하면 구동 허용을 해제하고, 운용 절차에 따라 재허용을 받아야 합니다. [실물 시험 지침][safety]

## 캐리어 부품과 선택 실장

기본 실장 대상은 75개이며, 관통홀 납땜점 300개와 J15의 표면실장 납땜점 6개가 있습니다. J15의 납땜점은 신호 4개와 고정 탭 2개입니다. 기본 미실장 23개, 고정홀과 테스트 패드는 이 실장 수량에서 제외했습니다. [모듈·짝 커넥터 BOM](modules-and-mates.csv)

| 부품 | 실장 기준 |
| --- | --- |
| U1, RN1 | 3.3 V에서 사용하는 74HC08 DIP-14와 4.7 kΩ ×4 공통단자 SIP5. RN1 1번은 GND입니다. |
| RN2 | UART RX 풀업용 10 kΩ ×4 공통단자 SIP5 1개입니다. RN2 1번은 3.3 V입니다. |
| C1, C2 | 4.7 µF, 100 nF. 2.50 mm 피치 THT와 3.3 V 전원에 맞는 정격을 사용합니다. |
| R1, R7, R8, R19 | 10 kΩ. R6만 4.7 kΩ, R13은 1.5 kΩ, R14–R18은 1 kΩ입니다. 소형 수직 리드형 풋프린트입니다. |
| D1–D3, D4–D5, Q1 | 3 mm LED, BAT43 두 개, 2N3904 한 개. LED는 기판 뒷면 CAN·RUN·FLT 표시를 따릅니다. |
| J18, R28, R29, C4, D7–D8 | 기본 미실장입니다. 비상정지 상태 입력용 커넥터, 1 kΩ, 10 kΩ, 100 nF, BAT43 두 개입니다. |
| C5–C8 | 각 RS-485 모듈 포트의 100 nF 전원 디커플링입니다. |
| R30–R33 | RS-485 채널별 120 Ω A/B 종단 옵션으로, 기본 미실장입니다. 4777 모듈의 내장 120 Ω을 우선 사용합니다. [Waveshare 회로도][rs485-schematic] |
| R49–R56 | 각 RS-485 채널의 A–3.3 V와 B–GND에 쓰는 390 Ω 바이어스 옵션으로, 기본 미실장입니다. 다리 1부터 차례로 R49·R50, R51·R52, R53·R54, R55·R56입니다. 2.54 mm 피치의 수직 리드형 풋프린트입니다. |
| R9–R12 | 4.7 kΩ I²C 풀업, 기본 미실장입니다. R9·R10은 ToF용, R11·R12는 INA228용입니다. 모듈의 기존 풀업과 실측 파형을 보고 필요한 쌍을 장착합니다. |
| D6 | `BAT43`, 기본 미실장입니다. 유도성 부저의 플라이백 보호가 필요할 때 장착합니다. |

### J17 보호 회로 부품

표는 기판 한 장의 J17 보호 회로 부품 기준입니다.

| 부품 | 실장 기준 |
| --- | --- |
| U6, U7, D11 | `LT3086ET7#PBF` TO-220-7, `LM393AP` DIP-8, `LM4040AIZ-2.5/NOPB` TO-92 각 1개입니다. U6는 홀 위치가 교차하는 풋프린트에 맞춰 장착합니다. U7의 정격 주위 온도는 0–70 °C입니다. [ADI LT3086][lt3086] · [TI LM393AP][lm393] · [TI LM4040AIZ-2.5][lm4040] |
| F1, Q2 | Littelfuse `0251001.MXL` 1 A/125 V 축형 퓨즈, `2N3904` TO-92 각 1개입니다. |
| D9, D10, D12 | 양방향 TVS `P6KE30CA`, 제어 전원 경로용 `SB1100-T` 100 V 축형 쇼트키 다이오드, 비교기 전원 클램프용 `1N4750A` 각 1개입니다. [Littelfuse P6KE][p6ke] · [Diodes SB1100][sb1100] |
| C3, C14 | 각각 22 µF/25 V X7R, 리드 피치 5 mm입니다. TDK `FG22X7R1E226MRT00` 또는 `FG22X7R1E226MRT06`을 사용하며, 동작 조건에서 두 커패시터의 유효 용량 합계가 10 µF 이상인지 확인합니다. [ADI LT3086][lt3086] · [TDK FG22][tdk-fg22] |
| C9, C12, C13 | C9는 Nichicon `UES1H220MPM` 무극성 22 µF/50 V, Ø10 × 12.5 mm, 리드 피치 5 mm입니다. C12는 제어 전원 바이패스용 100 nF, C13은 퓨즈 뒤 입력의 100 nF/50 V입니다. [Nichicon UES][nichicon-ues] |
| R35–R38, C10–C11 | R35는 91.0 kΩ 0.1%, R36은 3.9 kΩ, R37은 2.00 kΩ 1%, R38은 1 kΩ입니다. C10·C11은 각 10 nF입니다. |
| R39–R42 | R39는 100 Ω, R40은 4.7 kΩ, R41·R42는 각각 10.0 kΩ 0.1%입니다. |
| R43–R48 | R43은 31.6 kΩ, R44는 10 kΩ, R45는 24.9 kΩ, R46은 10 kΩ이며 4개 모두 0.1%입니다. R47은 22 kΩ, R48은 15 kΩ입니다. |

## 완성 모듈과 변환 하네스 후보

아래 품번은 실물 검증용 후보입니다. 모듈의 커넥터 실장 옵션과 하네스 길이를 구입 전에 확인합니다.

| 포트 | 모듈 후보 | 하네스와 확인할 사항 |
| --- | --- | --- |
| J19–J22 | Waveshare `RS485 Board (3.3V)` SKU `4777` | 캐리어 XH 7핀에서 모듈의 VCC·GND·RO·DI·RSE 5핀 수헤더에 맞는 암 피그테일과 별도 A·B 헤더 또는 나사 단자로 분기합니다. 각 모듈 쪽 RSE–GND 사이에 10 kΩ을 연결합니다. 3.3 V 모델의 실제 부품, 내장 종단, 부하 전류와 4 Mbps 동작을 확인합니다. [Waveshare 제품 정보][rs485-module] · [Waveshare 사용자 설명서][rs485-manual] |
| J7–J10 | 헤더 실장형 ShillehTek VL53L1X CJMCU-531 | PH-5에서 모듈 암 단자로 연결합니다. 모듈 GPIO1은 비워 두고, XSHUT의 모듈 측 풀업 전압과 MCU 오픈드레인 제어를 확인합니다. [제품 설명][tof] |
| J11 | Boardoza BMI088 SPI | 1×9 암 피그테일을 모듈 J1의 SCK·MOSI·nCS2·nCS1·MISO·GND, J2의 3.3 V·GND, J3의 INT1·INT3에 신호명대로 분기합니다. SPI 기본 설정과 모듈에 실장된 커넥터 옵션을 확인합니다. [제조사 핀맵][imu] |
| J13 | TI `INA228_237_238EVM`의 INA228EVM 보드 | 정확한 IC 변형과 R1 미실장을 확인합니다. J13의 3.3 V·GND·SCL·SDA는 EVM의 디지털 헤더에 연결합니다. 켈빈 센스선은 아래 외장 션트 배선에 따라 연결합니다. [TI EVM 사용자 가이드][ina228] |
| J14 | Switch Science `SSCI-110044`, TCAN3413 | 3.3 V는 VCC와 VIO에, `CAN_TX`는 TXD에, `CAN_RX`는 RXD에 연결합니다. `CAN_STB`는 STB에 연결하고 STB를 GND에 고정하는 SJ1은 개방합니다. CANH/L은 모듈에서 연결합니다. 장착된 헤더와 버스 단자가 있는 공급 옵션이 확인되면 사용합니다. [제조사 제품 설명][can] |
| J15 | ML-X120 LiDAR | 캐리어 쪽 `GHR-04V-S` 피그테일을 LiDAR 하네스의 `EX_OUT`·`EX_OUT_GND`에 신호명으로 연결합니다. 조립 전에 양 끝의 핀 번호와 도통을 확인합니다. [Notion EE 요구사항][requirements] |

## 외부 부저 J16

J16은 외부 수동 피에조용 3.3 V PWM 구동을 지원합니다. PH 2핀의 1번은 3.3 V, 2번은 Q1 `2N3904`가 접지로 당기는 `BUZZER_SINK`입니다. 3.3 V에서 동작하는 소자를 쓰고, 방전 저항과 스위칭 피크를 포함한 J16 부하 전류를 **20 mA 이내**로 확인합니다. [Murata 피에조 구동 회로][piezo]

수동 피에조를 외부 하네스에 연결할 때 두 단자 사이에 병렬 방전 저항을 둡니다. 방전 경로가 들어 있는 완성 모듈도 사용할 수 있습니다. 선정한 피에조의 권장 구동 주파수를 PWM에 적용하고 필요 시 직렬 저항으로 피크 전류를 제한합니다. 수동 피에조 구성에서 D6은 기본 미실장 상태로 둡니다. [Murata 피에조 구동 회로][piezo]

## RS-485 버스 배선

J3–J6의 독립 반이중 버스를 다리별로 하나씩 사용합니다. J19↔J3, J20↔J4, J21↔J5, J22↔J6으로 각 외부 모듈과 모터 버스가 연결됩니다. A/B는 특성 임피던스 120 Ω의 꼬임쌍으로 배선하고, 신호 기준용 GND를 함께 연결합니다. 모듈과 캐리어 사이 A/B도 짧게 짝지어 배선하고, 모터 전원과 리턴은 전용 하네스로 배선합니다. [TI RS-485 설계 지침][rs485-guide]

4777 모듈의 내장 120 Ω을 캐리어 쪽 버스 끝 종단으로 사용하고, 반대쪽 끝의 120 Ω을 하나 확인합니다. 캐리어의 R30–R33과 중간 노드 종단은 기본 미실장 상태로 둡니다. 모듈을 교체하는 경우 실제 종단 위치와 저항값을 다시 확인합니다. 상대 장치의 A/B 표기와 신호 극성은 핀맵과 파형으로 확인합니다. [Waveshare 회로도][rs485-schematic] · [TI RS-485 설계 지침][rs485-guide]

SP3485의 차동 입력 임계값은 ±200 mV 범위입니다. 모든 장치가 수신 중일 때 각 채널에서 A–B 전압과 UART RX 유휴 고레벨을 확인합니다. 유휴 수준이 불안정하면 해당 채널에 바이어스 저항 한 쌍을 실장하고, 실제 종단과 부하에서 신호 여유와 전원 전류를 다시 확인합니다. [MaxLinear SP3485 데이터시트][rs485-ic] · [TI RS-485 설계 지침][rs485-guide]

RSE가 저레벨이면 수신이고 고레벨이면 송신입니다. 하네스의 모듈 쪽에 있는 10 kΩ 풀다운은 RSE 선이 끊어져도 모듈을 수신 상태로 유지합니다. 각 모듈의 VCC·GND 사이 바이패스 커패시터를 실물에서 확인하고, 없는 경우 모듈 전원 단자 가까이에 100 nF를 연결합니다. 송신 중 RO가 하이 임피던스일 때 RN2의 10 kΩ 풀업이 MCU의 UART RX를 유휴 고레벨로 유지합니다. 마지막 비트 전송이 끝난 뒤 RSE를 저레벨로 되돌리고 첫 응답 바이트가 수신되는지 확인합니다. [Waveshare 사용자 설명서][rs485-manual] · [Waveshare 회로도][rs485-schematic]

## 외장 션트와 Jetson SOC 표시

배터리 양극에서 메인 퓨즈, 외장 션트, 부하 분배 순으로 연결합니다. 모터 비상 차단은 분기 이후 외부 모터 전원 하네스에 둡니다. 배터리 부하 전류 전체는 외부 하네스로 흐릅니다.

INA228의 IN+와 IN−는 션트 배터리 측과 부하 측 켈빈 단자에 각각 연결합니다. VBUS는 메인 퓨즈 뒤 션트의 배터리 측에 연결합니다. TI EVM 기준 IN+는 EVM J1의 5·6번, IN−는 3·4번, VBUS는 2번, 시스템 GND는 1번입니다. **캐리어 J13에는 3.3 V·GND·SCL·SDA만** 연결합니다. 션트의 0.2 mΩ·±1%는 측정 설계 기준입니다. 션트 품번과 전력 정격은 실제 연속·피크·회생 전류에 맞춥니다. [TI EVM 외장 션트 배선][ina228]

배터리 전위에 연결되는 가는 IN+·IN−·VBUS 센스선에는 분기점 가까이에 각각의 단락 보호를 둡니다. 보호소자의 DC 정격, 차단 용량과 동작 특성을 최대 팩 전압, 예상 단락전류, 센스선 굵기에 맞춥니다. IN+와 IN−는 켈빈 쌍으로 함께 배선하고 양쪽의 보호소자·입력 필터 임피던스를 맞춥니다. 보호소자를 포함해 무부하 영점, 알려진 전류에서의 측정 오차와 극성, VBUS를 확인한 뒤 캘리브레이션합니다. 센스선 단선이나 측정 이상이 확인되면 전류와 SOC를 무효로 처리합니다. [INA228 입력 필터 지침][ina228-datasheet]

Jetson에서 배터리 SOC와 측정 유효 상태를 표시합니다. 이를 위해 Nucleo에서 J13의 INA228 전압·전류·누적 전하를 읽고 ST-LINK USB 가상 시리얼로 배터리 텔레메트리를 Jetson에 전달하는 소프트웨어 연동이 필요합니다. [TI INA228 데이터시트][ina228-datasheet]

## 제작과 첫 전원 인가 전 확인

1. Nucleo 핀 1, 솔더 브리지, 38핀 소켓 결합 방향, 지지대 높이, USB 접근, 기판 위아래 커넥터와 하네스 간섭을 실물로 확인합니다. 하네스 전수 도통 검사와 전원 핀의 단락 검사를 합니다. [ST UM2505][nucleo]
2. 첫 시제품에서는 Nucleo·USB·배터리·모터·외부 모듈을 분리하고 TP1–TP3 사이에 더미 부하를 연결합니다. 전류 제한형 실험 전원으로 정상 시동, 서서히 올리거나 급격히 올린 과전압에서의 차단과 차단 상태 유지, 정상 전압에서의 복귀, 역극성 차단을 확인합니다. J17 입력과 TP1을 오실로스코프로 동시에 측정합니다. 차단·복귀 전압과 TP1 방전 시간을 기록하고, 시동·보호 동작 중 TP1 최고 전압이 5.25 V 이내인지 확인합니다. 부하를 단계적으로 올려 지속 전류 제한점이 500 mA 이내인지 확인하고, 시동·부하 급변 시 전류 피크와 U6 온도를 기록합니다. [ADI LT3086][lt3086] · [ST UM2505][nucleo]
3. J17 보호 시험을 통과한 뒤 Nucleo를 연결합니다. 정상 전원에서 E5V와 3.3 V를 확인하고, 외부 전원이 꺼진 경우 ST-LINK USB에 의한 역급전 여부를 확인합니다. RS-485 양 끝을 종단하고 4채널 동시 송신, ToF 전체 동작과 연결한 외부 부하를 사용해 시동·정상 동작 전류, E5V와 3.3 V의 최소 전압, U6와 Nucleo 레귤레이터 온도를 기록합니다. 각 SP3485 모듈 전원 단자에서 3.3 V ±5%를 확인합니다. J16을 사용하는 경우 PWM과 부하 전류를 측정합니다. [ST UM2505][nucleo] · [MaxLinear SP3485 데이터시트][rs485-ic]
4. 각 RS-485 모듈에서 A/B 사이의 내장 120 Ω을 무전원 상태로 실측합니다. 조립한 각 채널에서 양 끝의 수동 120 Ω이 연결되면 A/B 사이가 약 60 Ω인지 측정합니다. 모터를 구동하기 전 A/B 극성, MCU 리셋·RSE 선 단선·캐리어 무전원 상태에서의 송신 해제, 버스 유휴 상태와 송신 중 MCU RX의 유휴 고레벨, 네 채널 4 Mbps 파형, 방향 전환 직후 첫 응답 바이트를 확인합니다. CAN의 양 끝 120 Ω, STB 전환, 목표 CAN-FD 속도도 확인합니다.
5. ToF 네 개의 XSHUT을 모두 저레벨로 둔 뒤 한 개씩 해제해 주소를 할당합니다. 네 하네스를 연결하고 100 kHz에서 측정한 뒤 SCL·SDA의 저레벨과 상승 시간을 각 센서 단에서 확인합니다. 400 kHz를 쓰려면 상승 시간 300 ns 이내를 확인합니다. 실제 케이블로 BMI088 양쪽 CS와 INT를 검사합니다. LiDAR 변환 하네스의 도통, SYNC의 MCU 입력 전압과 극성을 검사합니다. [NXP I²C 사양][i2c]
6. 외장 션트의 영점·오차·극성과 VBUS를 확인합니다. 모터 동작을 허용하기 전 외부 비상정지 하드웨어 차단, MCU 리셋과 통신 단절 시 구동 응답, 차단 해제 후 재구동 조건을 검증합니다. 비상정지 보조접점을 실장한 경우 PA11 상태 보고와 하네스 분리 감지도 확인합니다. [실물 시험 지침][safety]

양산용 기판 발주는 J17 시동·과전압·역극성·부하·온도 시험을 통과한 뒤 진행합니다.

[requirements]: https://app.notion.com/p/42345bd871788017a5bbf7cbe5e0e705
[ph]: https://www.jst.com/products/crimp-style-connectors-wire-to-board-type/ph-connector/
[xh]: https://www.jst.com/wp-content/uploads/2025/06/eXH.pdf
[gh]: https://www.jst-mfg.com/product/index.php?lang=2&series=105
[imu-header]: https://www.harwin.com/products/M20-9990945
[imu-housing]: https://www.harwin.com/products/M20-1060900
[imu-contact]: https://www.harwin.com/products/M20-1180042
[lt3086]: https://www.analog.com/media/en/technical-documentation/data-sheets/lt3086.pdf
[lm393]: https://www.ti.com/product/LM393A/part-details/LM393AP
[lm4040]: https://www.ti.com/product/LM4040-N/part-details/LM4040AIZ-2.5/NOPB
[p6ke]: https://www.littelfuse.com/assetdocs/tvs-diodes-p6ke-datasheet?assetguid=620a3cb5-3282-4670-8b03-66f21bc75523
[sb1100]: https://www.diodes.com/datasheet/download/SB1100.pdf
[tdk-fg22]: https://product.tdk.com/en/search/capacitor/ceramic/lead-mlcc/info?part_no=FG22X7R1E226MRT00
[nichicon-ues]: https://www.nichicon.com/en-us/part/ues1h220mpm/5423/
[rs485-module]: https://www.waveshare.com/product/rs485-board-3.3v.htm
[rs485-manual]: https://files.waveshare.com/upload/9/95/RS485-Board-UserManual.pdf
[rs485-schematic]: https://files.waveshare.com/upload/b/bf/RS485-Board-Schematic.pdf
[rs485-ic]: https://files.waveshare.com/upload/2/25/MaxLinear-SP3485.pdf
[rs485-guide]: https://www.ti.com/lit/an/slla272d/slla272d.pdf
[tof]: https://shillehtek.com/products/vl53l1x-tof-sensor-4m-pre-soldered-esp32
[imu]: https://github.com/Boardoza/Boardoza_BMI088_6-Axis_IMU_Breakout_Board
[piezo]: https://www.murata.com/support/faqs/sound/sounder/char/sch0001
[ina228]: https://www.ti.com/lit/ug/sbou241e/sbou241e.pdf
[ina228-datasheet]: https://www.ti.com/lit/ds/symlink/ina228.pdf
[can]: https://www.switch-science.com/products/11004
[nucleo]: https://www.st.com/resource/en/user_manual/um2505-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf
[mb1367]: https://www.st.com/resource/en/board_manufacturing_specification/mb1367_bdp.zip
[ssw]: https://www.samtec.com/products/ssw-119-03-g-d
[i2c]: https://www.nxp.com/docs/en/user-guide/UM10204.pdf
[safety]: ../../../docs/operations/safety.md
