<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Nucleo 캐리어 조립과 하네스

2026-11-28 기준 P2.3 시제품 조립 안내입니다. 2층 베어 PCB를 발주하고 캐리어 커넥터와 필수 부품을 손납땜합니다. RS-485 트랜시버와 외부 센서는 커넥터나 헤더가 실장된 완성 모듈과 변환 하네스로 연결합니다. 전원과 하네스는 이 문서의 핀 배정을 적용합니다. [Notion EE 요구사항][requirements]

## 기판과 실장면

최종 외곽·적층은 [PCB 검증 기록](verification.md)에 기재합니다. 앞면에 Nucleo용 J1·J2, 뒷면에 하네스 포트와 손납땜 부품을 실장합니다. 커넥터 잠금턱과 케이블 굽힘, 지지대·모듈 간격을 확인합니다.

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
| J14 | JST XH `B6B-XH-A`, `XHP-6` | VIO 3.3 V, GND, `CAN_TX`, `CAN_RX`, `CAN_STB`, 보호 E5V |
| J15 | 1.25 mm 측면 삽입형 SMT JST GH `SM04B-GHS-TB`, `GHR-04V-S` 및 `SSHL-002T-P0.2` 단자 | LiDAR `EX_OUT`, `EX_OUT_GND`, 예비 `EX_IN`, 예비 `EX_IN_GND` |
| J16 | JST PH `B2B-PH-K-S`, `PHR-2` | 3.3 V, `BUZZER_SINK` |
| J17 | 상부 삽입형 JST XH `B2B-XH-A`, `XHP-2` | 외부 안정화 5.15–5.25 V, GND |
| J18 | 기본 미실장, 상부 삽입형 JST PH `B3B-PH-K`, `PHR-3` | 비상정지 NC 보조접점, 미연결, GND |
| J19–J22 | 상부 삽입형 JST XH `B7B-XH-A`, `XHP-7` 및 `SXH-001T-P0.6` 단자(22–28 AWG) | 전용 +3V3_RS485, GND, 모듈 RO, 모듈 DI, 모듈 RSE, RS-485 A, RS-485 B |
| J23 | JST XH `B8B-XH-A`, `XHP-8` | PG, EN, 보호 VIN, GND_IN, +3V3_RS485 VOUT, GND_OUT, 미연결, 미연결 (7·8번은 단자 미삽입) |
| J24 | 2.54 mm 1×3 암소켓과 #4942 선실장 수직 수헤더 | 보호 VIN, 공통 GND, 승압 6 V VOUT (핀 1과 양끝 라벨을 맞춤) |

PH는 2.00 mm, XH는 2.50 mm, GH는 1.25 mm 피치입니다. ToF, RS-485 모듈, 모터 하네스 양쪽 끝에 채널 번호를 표시합니다. 전선 규격에 맞는 압착 단자나 기성 피그테일을 씁니다. J11은 방향 키가 없어 하네스 양쪽에 1번을 표시하고 전원을 넣기 전 3.3 V와 GND의 도통을 확인합니다. [JST PH 제품 정보][ph] · [JST XH 데이터시트][xh] · [Harwin 수헤더][imu-header] · [Harwin 암 하우징][imu-housing] · [Harwin 압착 단자][imu-contact]

J15는 표면실장 커넥터입니다. 기판 뒷면에 GH 4핀의 신호 패드와 금속 고정 탭을 납땜하고, 확대 검사와 하네스 도통 검사를 합니다. 첫 시제품은 1·2번만 사용하며, 3·4번은 예약합니다. [JST GH 제품 정보][gh]

## 전원과 조립 순서

J17에서 부하 시 5.15~5.25 V를 받습니다. F1 뒤 D9가 원입력 과도를 제한하고, R75·U16·외부 MOSFET 및 R68을 거친 공통 보호 출력에서 두 전원을 분기합니다. U16은 역극성을 차단하고 과전압 때 출력을 조절한 뒤 TMR 만료 시 분리합니다. J24의 6 V 승압 출력은 U6와 U14를 거쳐 CN7-6 및 J14.6에 공급됩니다. 다른 분기는 R74를 거쳐 J23 벅의 입력으로 갑니다. 벅 EN은 기존 입력 창과 연동하며, PG와 U13 양전원 감시가 성립해야 송신을 허용합니다. [전원·고장 조건과 시험 순서](power-validation.md)

Nucleo JP5를 5–6번 E5V에 두고 U12용 SB5를 확인합니다. J11 SPI1은 SB6를 개방합니다. J19~J22의 1번은 J23 VOUT이며 CN7-16과 독립입니다. 통전 전 두 출력 간 단락 및 공통 GND를 검사합니다. U13·U14·U16은 IC와 기계핀을 공급자가 납땜한 DIP 변환 조립품입니다. U16의 PA0005와 16핀 SOIC IC의 1번 방향을 맞춰 조립한 뒤, DIP 핀 1→16의 순서 **OUT, SENSE, NC, DGATE, SOURCE, HGATE, NC, VCC, SHDN, UV, OV, GND, FLT, ENOUT, TMR, FB**를 핀별 도통 검사합니다. U16.9(SHDN)의 기계핀은 실장하되 캐리어 패드는 미연결이고, U16.10(UV)은 J17_GATE에 연결됩니다. Q3·Q4는 G=1, D=2 및 탭, S=3입니다. 서로 다른 드레인의 금속 탭과 기구 사이를 절연합니다. D16은 K를 보호 출력, A를 GND에 두고 C24는 +를 J24 VIN에 향하게 합니다. 외부 전원으로 먼저 기동한 뒤 데이터 가능한 ST-LINK USB를 연결합니다. [ADI U16 핀·보호 동작](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4364-1-4364-2.pdf) · [PA0005 치수](https://www.proto-advantage.com/store/datasheets/PA0005.pdf) · [ST Nucleo 설정][nucleo]

D17은 LT1634CCZ-2.5#PBF TO-92 직선 리드입니다. 가운데 핀 2(VOUT/캐소드)는 +3V3_RS485, 바깥 핀 1·3(GND/TEST)은 모두 R63 상단의 로컬 아노드에 연결합니다. 이 접점은 시스템 GND에서 떠 있습니다. R63 576 Ω과 R64 2.49 kΩ이 직렬로 기준소자에 약 0.2 mA를 공급하고, 중간점을 U13 ADJ2로 보냅니다. C13과 C26이 J24 승압 출력의 U6 입력을 바이패스하는지 도통 검사합니다. D17 C등급의 보증 주위온도는 0~70 °C입니다. [ADI LT1634 핀맵·전기 사양](https://www.analog.com/media/en/technical-documentation/data-sheets/1634ff.pdf)

DIP 조립품의 상면 1번 표식과 캐리어의 사각 패드를 맞춥니다. U13은 핀 1→8이 ADJ1, ADJ2, REF, GND, /RST, VCC, TMR, SEL입니다. U14는 핀 1→6이 IN, GND, EN, /FAULT, ILIM, OUT입니다. U13의 REF 및 U14의 /FAULT는 캐리어에서 미사용입니다. 조립업체가 어댑터 핀–IC 리드의 도통 기록을 제공하고 첫 캐리어에 납땜하기 전 이 표와 대조합니다. [LTC2909 핀맵](https://www.analog.com/media/en/technical-documentation/data-sheets/2909fb.pdf) · [TPS2553 DBV 핀맵](https://www.ti.com/lit/ds/symlink/tps2553.pdf)

## 선택 실장하는 비상정지 보조접점

모터 전원 차단은 외부 비상정지 하드웨어에서 독립적으로 수행합니다. 상태 입력이 필요한 경우 J18과 R28·R29·D7·D8·C4를 함께 실장하고, 외부의 **무전압 NC 보조접점**을 J18의 1번과 3번에 연결합니다. 약 0.3 mA의 저레벨 신호에 적합한 접점을 사용하고, 연결 전에 도통과 외부 전압이 걸려 있지 않은지 확인합니다. 접점이 닫히면 PA11이 저레벨이고, 비상정지로 접점이 열리거나 하네스가 분리되면 고레벨입니다. 펌웨어에서 이 옵션을 사용할 때는 비상정지나 배선 분리를 감지하면 구동 허용을 해제하고, 운용 절차에 따라 재허용을 받아야 합니다. [실물 시험 지침][safety]

## 실장 부품과 완성 모듈

[캐리어 BOM](carrier-bom.csv)은 최종 KiCad 회로도의 부품값·풋프린트·실장 상태를, [구매 BOM](modules-and-mates.csv)은 공급 품번·짝 커넥터와 하네스 부품을 담습니다. [하네스 제작표](harnesses.md)의 길이와 양끝 핀맵을 적용합니다. 완성 모듈의 전원 및 커넥터 방향을 검사한 뒤 캐리어에 꽂습니다.

| 포트·부품 | 시제품 조립 기준 |
| --- | --- |
| J7~J10 | Pololu 3415에 2.54 mm 1×7 수직 수헤더를 **출하 전 실장한 구성**으로 4개 조달합니다. 소매 표준품은 헤더가 동봉됩니다. 구매 발주에 헤더 실장·도통 검사·센서면 방향을 명시하고 견적에서 이 항목을 확인합니다. [Pololu 제품 사양][tof] |
| J11 | Bosch BMI088 Shuttle Board 3.0, `BST00767`의 실장된 1.27 mm 두 줄을 전용 분기 하네스로 받습니다. P1/P2, 두 1번 표식, 3.3 V→VDD·VDDIO, PS→GND를 확인합니다. [제조사 도면][imu] |
| J13 | TI 주문품번 `INA228EVM`, SENS063의 INA228AIDGSR 탑재형을 씁니다. SENS063의 공통 기판명으로 237/238 변형을 구별할 수 없어 구매 품번과 DIE_ID의 상위 12비트(0x228)를 확인합니다. 2 mm J3 수헤더의 **짝수 핀**을 쓰고 J1에는 켈빈 센스·VBUS만 배선합니다. [TI EVM 사용자 가이드][ina228] |
| J14·Jetson | `MIKROE-3992` CAN FD 3 Click을 양쪽에 각 1개 사용합니다. 두 모듈에 로컬 5 V와 3.3 V VIO를 각각 공급합니다. 캐리어 PB15가 STB를 제어하며 Jetson STB는 GND입니다. 내장 분할 종단은 약 120.8 Ω입니다. [제조사 회로도][can] |
| J15 | GH 네 신호 패드와 두 금속 고정 탭을 모두 납땜하고 확대 검사합니다. 1번은 EX_OUT, 2번은 반환선, 3·4번은 예비로 비워 둡니다. |
| J16 | 경고음은 필수입니다. PUI Audio `AT-1740-TT-3-R` 수동 피에조를 하네스에 부착합니다. 4 kHz PWM과 모듈별 패턴을 적용하고 기구 조립 후 시작음·오류음을 확인합니다. 정격 3 Vpp에서 78 dBA/10 cm이며 실물 동작 음량은 측정 대상입니다. 180 Ω 직렬 저항이 3.40 V에서 충전 순간을 약 19 mA로 제한하고 2.2 kΩ이 꺼짐 구간에 방전합니다. D6은 기본 미실장입니다. [PUI 데이터시트][piezo] |
| J19~J22 | TI THVD1424EVM ×4를 각각 독립 지지대에 고정합니다. J7로 VCC와 VL을 묶고 J8은 반이중·20 Mbps 모드 및 Y/Z 내장 종단을 선택합니다. RO 유휴 전압을 위해 EVM R3만 공급자가 제거합니다. C5~C8과 선택 A측 바이어스의 공급은 +3V3_RS485입니다. R30~R33 및 R49~R56은 기본 미실장입니다. [TI EVM][rs485-manual] |
| J23 | TI TPSM365R6V3EVM의 고정 3.3 V/600 mA 변형입니다. 입력 나사 단자 바로 옆에 P6KE8.2A와 47 µF/25 V를 병렬 선조립합니다. 핀 순서·점퍼·양방향 전원 리턴은 하네스 표를 따릅니다. 단일 EVM 및 네 EVM 부하 전환에서 입력·출력·PG와 모듈 단자 전압을 기록합니다. [TI EVM 안내](https://www.ti.com/lit/ug/snvu846/snvu846.pdf) |
| J24 | Pololu #4942 U3V16F6, 6 V ±4%를 선정합니다. 동봉 1×3 수직 헤더를 납품 전에 실장하고 13.1×8.1 mm 모듈을 캐리어에 직결합니다. 실크의 VIN·GND·VOUT를 확인하고 역삽을 차단하는 비도전성 가이드로 지지합니다. [Pololu 사양](https://www.pololu.com/product/4942) |

TI 평가보드와 해당 전용 하네스는 고정 시험대 시제품을 대상으로 합니다. 양산 BOM에는 THVD1424EVM과 전원 EVM의 공급·사용 조건 및 실제 기구 진동 조건을 별도로 검토합니다. [TI EVM 사용 조건][rs485-manual]

## 센서 단자 전압과 I²C

센서 전원은 Nucleo U12의 3.3 V입니다. 부하에서 CN7-16 **3.20 V 이상**, CN7과 포트 간 공용 전원·GND 전압 강하 **30 mV 이하**, 접점·리드를 포함한 포트~모듈 왕복 저항 **0.25 Ω 이하**를 시제품 설계/검사 한계로 둡니다. 구리선 26 AWG(20 °C 약 0.134 Ω/m)를 0.20 m 사용한 왕복 저항은 약 54 mΩ, 28 AWG·0.10 m는 약 43 mΩ입니다. 단자·온도·압착 편차를 포함한 실제 루프 저항과 시동 과도응답은 실물 확인 대상입니다.

| 센서 | 모듈 조건 | 계산된 최저 단자 전압 / 하한 여유 |
| --- | --- | --- |
| ToF 3415 | VIN 2.6~5.5 V, 모듈 측정 피크 약 40 mA | 3.20 − 0.030 − 0.040×0.25 = **3.160 V / 0.560 V**. XSHUT을 MCU 오픈드레인으로 구동합니다. [Pololu 사양][tof] |
| BMI088 BST00767 | 모듈 도면의 공급 경로는 P1→JP1/JP2→IC입니다. JP1/JP2 도통 확인, VDD 2.4~3.6 V, VDDIO 1.2~3.6 V. 여유를 둔 10 mA 예산입니다. | 3.20 − 0.030 − 0.010×0.25 = **3.1675 V / 0.7675 V**. 공급 상한과 SPI/인터럽트 양쪽 유효 레벨도 확인합니다. [Bosch 셔틀 회로][imu] · [BMI088 전기 사양](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi088-ds001.pdf) |

R9/R10과 R11/R12 모두 기본 미실장입니다. 아래는 4개 ToF가 모두 연결된 400 kHz 설계의 상한 배분입니다. C는 각 SCL·SDA **한 선당 총합**입니다. 저항 오차 ±5%, 최고 로직 전압 3.40 V 및 Low 0.4 V를 사용합니다. [NXP I²C 규격][i2c]

| 버스 | 등가 풀업·Low 전류 | 최대 길이 상승 시간 예산 (30~70%) |
| --- | --- | --- |
| I2C2 ToF | 네 모듈의 바깥쪽 10 kΩ 병렬 = 2.50 kΩ. Low에서는 각 FET 반대편의 2.8 V/10 kΩ 네 개까지 포함해 4×[(3.40−0.4)+(2.94−0.4)]/9.50 kΩ = **2.34 mA**. 3 mA 기준 이하입니다. | 각 0.20 m × 4 × 100 pF/m + 보드·커넥터·소자·프로브 50 pF = 130 pF. 외측의 완만한 RC 경계는 0.8473×2.625 kΩ×130 pF = **289 ns**입니다. 레벨시프터 내부 램프/용량도 시험 파형에 포함합니다. [모듈 회로도](https://www.pololu.com/file/0J1188/vl53l0x-and-vl53l1x-time-of-flight-sensor-schematic.pdf) |
| I2C3 INA228 | SENS063 R5/R6 각 4.70 kΩ 하나. Low 전류 ≤(3.40−0.4)/4.465 kΩ = **0.672 mA**. | 0.20 m × 100 pF/m + 보드·커넥터·소자·프로브 40 pF = 60 pF, 0.8473×4.935 kΩ×60 pF = **251 ns**. [TI EVM 회로도][ina228] |

센서가 적으면 I2C2의 등가 저항도 달라집니다. 한 모듈로 시작하는 진단은 100 kHz부터 실행합니다. 400 kHz 허용 기준은 최대 하네스·최대 센서 구성에서 MCU 및 최원단 모두 **tr ≤300 ns**, Low ≤0.4 V와 주소 초기화/ACK 연속 성공입니다. 최장 분기 파형이나 실제 정전용량이 예산을 벗어나면 하네스를 줄이거나 100 kHz를 검증합니다. 빠른 모드에 필요한 경우에는 저항을 임의로 더 실장하기 전에 합산 Low 전류를 다시 계산합니다.

## RS-485 버스 배선

J3–J6의 독립 반이중 버스를 다리별로 하나씩 사용합니다. J19↔J3, J20↔J4, J21↔J5, J22↔J6으로 각 외부 모듈과 모터 버스가 연결됩니다. A/B는 특성 임피던스 120 Ω의 꼬임쌍으로 배선하고, 신호 기준용 GND를 함께 연결합니다. 모듈과 캐리어 사이 A/B도 짧게 짝지어 배선하고, 모터 전원과 리턴은 전용 하네스로 배선합니다. [TI RS-485 설계 지침][rs485-guide]

THVD1424EVM의 H/F=High에서는 Y와 Z가 송수신을 함께 담당합니다. J8 플러그로 TERM_TX=High를 설정해 캐리어 끝에 공칭 120 Ω을 걸고 최원단에는 120 Ω ±1% 한 개를 둡니다. EVM의 R25/R26, 캐리어 R30~R33, 중간 노드는 미실장입니다. 회로의 선택 바이어스 A 풀업·B 풀다운도 기본 미실장입니다. [TI EVM 회로도][rs485-manual] · [TI 전기 사양][rs485-ic]

THVD1424 수신기는 버스 개방·단락·유휴 시 High를 내보냅니다. 다른 장치까지 연결한 각 버스에서 유휴 A–B와 UART RX High를 측정합니다. 환경 노이즈 때문에 바이어스를 장착하려면 해당 채널의 두 저항과 종단 부하를 반영해 전류·차동전압을 재계산합니다. [TI 전기 사양][rs485-ic]

RSE Low는 수신, High는 송신입니다. 하네스 말단에서 RSE를 EVM의 /RE와 DE에 함께 연결하고 10 kΩ을 GND로 둡니다. EVM의 C9 및 C10·C11이 공급을 로컬 바이패스합니다. EVM의 R3을 제거해야 송신 중 고임피던스 RO가 모니터 LED로 방전되지 않습니다. 캐리어의 모듈 측 풀업과 MCU 측 RN2 양쪽에서 RX 유휴 High를 확인합니다. 두 전원 중 하나만 인가하거나 RSE 선을 분리해 송신 해제와 역급전 여부를 확인합니다. 마지막 정지 비트와 방향 전환 뒤 첫 수신 바이트를 네 채널에서 확인합니다. [TI RS-485 EVM][rs485-manual]

## 외장 션트와 Jetson SOC 표시

배터리 양극에서 메인 퓨즈, 외장 션트, 부하 분배 순으로 연결합니다. 모터 비상 차단은 분기 이후 외부 모터 전원 하네스에 둡니다. 배터리 부하 전류 전체는 외부 하네스로 흐릅니다.

INA228의 IN+와 IN−는 션트 배터리 측과 부하 측 켈빈 단자에 각각 연결합니다. VBUS는 메인 퓨즈 뒤 션트의 배터리 측에 연결합니다. TI EVM 기준 IN+는 EVM J1의 5·6번, IN−는 3·4번, VBUS는 2번, 시스템 GND는 1번입니다. **캐리어 J13에는 3.3 V·GND·SCL·SDA만** 연결합니다. 선정품 RSN-250-50B의 0.2 mΩ·±0.1%와 보정값을 적용합니다. 전체 기체의 실제 연속·피크·회생 전류와 부품 온도를 확인합니다. [TI EVM 외장 션트 배선][ina228]

배터리 전위에 연결되는 가는 IN+·IN−·VBUS 센스선에는 분기점 가까이에 각각의 단락 보호를 둡니다. 보호소자의 DC 정격, 차단 용량과 동작 특성을 최대 팩 전압, 예상 단락전류, 센스선 굵기에 맞춥니다. IN+와 IN−는 켈빈 쌍으로 함께 배선하고 양쪽의 보호소자·입력 필터 임피던스를 맞춥니다. 보호소자를 포함해 무부하 영점, 알려진 전류에서의 측정 오차와 극성, VBUS를 확인한 뒤 캘리브레이션합니다. 센스선 단선이나 측정 이상이 확인되면 전류와 SOC를 무효로 처리합니다. [INA228 입력 필터 지침][ina228-datasheet]

Jetson에서 배터리 SOC와 측정 유효 상태를 표시합니다. 이를 위해 Nucleo에서 J13의 INA228 전압·전류·누적 전하를 읽고 ST-LINK USB 가상 시리얼로 배터리 텔레메트리를 Jetson에 전달하는 소프트웨어 연동이 필요합니다. [TI INA228 데이터시트][ina228-datasheet]

## 제작과 첫 전원 인가 전 확인

1. Nucleo 핀 1, 솔더 브리지, 38핀 소켓 결합 방향, 지지대 높이, USB 접근, 기판 위아래 커넥터와 하네스 간섭을 실물로 확인합니다. 하네스 전수 도통 검사와 전원 핀의 단락 검사를 합니다. [ST UM2505][nucleo]
2. 첫 시제품에서는 Nucleo·USB·배터리·모터·외부 모듈을 분리하고 TP1–TP3 사이에 더미 부하를 연결합니다. 전류 제한형 실험 전원으로 정상 시동, 서서히 올리거나 급격히 올린 과전압에서의 차단과 차단 상태 유지, 정상 전압에서의 복귀, 역극성 차단을 확인합니다. J17 입력과 TP1을 오실로스코프로 동시에 측정합니다. 차단·복귀 전압과 TP1 방전 시간을 기록하고, 시동·보호 동작 중 TP1 최고 전압이 5.25 V 이내인지 확인합니다. 부하를 단계적으로 올려 지속 전류 제한점이 500 mA 이내인지 확인하고, 시동·부하 급변 시 전류 피크와 U6 온도를 기록합니다. [ADI LT3086][lt3086] · [ST UM2505][nucleo]
3. J17 보호 시험을 통과한 뒤 Nucleo를 연결합니다. 정상 전원에서 E5V와 3.3 V를 확인하고, 외부 전원이 꺼진 경우 ST-LINK USB에 의한 역급전 여부를 확인합니다. RS-485 양 끝을 종단하고 4채널 동시 송신, ToF 전체 동작과 연결한 외부 부하를 사용해 시동·정상 동작 전류, E5V와 3.3 V의 최소 전압, U6와 Nucleo 레귤레이터 온도를 기록합니다. 각 THVD1424EVM의 J6에서 첫 송신 허용부터 네 채널 동시 송신까지 3.0 V 동작 하한과 계산서의 시제품 전압 기준을 확인합니다. 필수 경고음 J16의 4 kHz PWM, 스위칭 피크와 음압을 측정합니다. [ST UM2505][nucleo] · [TI THVD1424 데이터시트][rs485-ic]
4. 원단 수동 종단을 분리해 무전원에서 120 Ω ±1%를 확인합니다. 캐리어 끝 내장 종단은 전원·TERM_TX가 유효할 때 측정합니다. 모터와 원단 종단을 분리하고 EVM을 수신(DE Low)에 둔 뒤 전류 제한된 차동 시험원으로 TI 그림 7-9의 VZ=0 V, VY=2 V를 인가해 2 V/전류가 102~138 Ω인지 확인합니다. 같은 상태에서 원단 120 Ω을 연결했을 때 계산치는 약 55~65 Ω입니다. 전원 인가된 버스에 저항계를 직접 연결하지 않습니다. 모터 동작 전 A/B 극성, RSE 단선·리셋 시 송신 해제, 4 Mbps 동시 전송 및 첫 응답을 확인합니다. CAN의 양끝 종단과 STB 전환도 검사합니다. [TI 종단 시험][rs485-ic]
5. ToF 네 개의 XSHUT을 모두 저레벨로 둔 뒤 한 개씩 해제해 주소를 할당합니다. 네 하네스를 연결하고 100 kHz에서 측정한 뒤 SCL·SDA의 저레벨과 상승 시간을 각 센서 단에서 확인합니다. 400 kHz를 쓰려면 상승 시간 300 ns 이내를 확인합니다. 실제 케이블로 BMI088 양쪽 CS와 INT를 검사합니다. LiDAR 변환 하네스의 도통, SYNC의 MCU 입력 전압과 극성을 검사합니다. [NXP I²C 사양][i2c]
6. 외장 션트의 영점·오차·극성과 VBUS를 확인합니다. 모터 동작을 허용하기 전 외부 비상정지 하드웨어 차단, MCU 리셋과 통신 단절 시 구동 응답, 차단 해제 후 재구동 조건을 검증합니다. 비상정지 보조접점을 실장한 경우 PA11 상태 보고와 하네스 분리 감지도 확인합니다. [실물 시험 지침][safety]

시제품 발주는 설계팀이 전원 계산서·하네스·KiCad 검증 기록을 검토한 뒤 결정합니다. 제작 후 J17 5.15·5.20·5.25 V에서 기동과 최대 동시 부하를 시험하고 CN7-6 및 각 센서 끝단 최저 전압, 단일 전원/USB 역급전, Q3·Q4·U6·U12·U14·승압·벅 온도와 RS-485 네 채널 4 Mbps 통신을 기록합니다. 보호 차단·복귀는 별도 시험합니다.

[requirements]: https://app.notion.com/p/42345bd871788017a5bbf7cbe5e0e705
[ph]: https://www.jst.com/products/crimp-style-connectors-wire-to-board-type/ph-connector/
[xh]: https://www.jst.com/wp-content/uploads/2025/06/eXH.pdf
[gh]: https://www.jst-mfg.com/product/index.php?lang=2&series=105
[imu-header]: https://www.harwin.com/products/M20-9990945
[imu-housing]: https://www.harwin.com/products/M20-1060900
[imu-contact]: https://www.harwin.com/products/M20-1180042
[lt3086]: https://www.analog.com/media/en/technical-documentation/data-sheets/lt3086.pdf
[rs485-manual]: https://www.ti.com/lit/ug/sllu356/sllu356.pdf

[rs485-ic]: https://www.ti.com/lit/ds/symlink/thvd1424.pdf
[rs485-guide]: https://www.ti.com/lit/an/slla272d/slla272d.pdf
[tof]: https://www.pololu.com/product/3415
[imu]: https://www.bosch-sensortec.com/media/boschsensortec/downloads/shuttle_board_flyer/application_board_3_1/bst-bmi088-sf000.pdf
[piezo]: https://api.puiaudio.com/filename/AT-1740-TT-3-R.pdf
[ina228]: https://www.ti.com/lit/ug/sbou241e/sbou241e.pdf
[ina228-datasheet]: https://www.ti.com/lit/ds/symlink/ina228.pdf
[can]: https://download.mikroe.com/documents/add-on-boards/click/can_fd_3_click/can-fd-click-schematic-v100.pdf
[nucleo]: https://www.st.com/resource/en/user_manual/um2505-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf
[mb1367]: https://www.st.com/resource/en/board_manufacturing_specification/mb1367_bdp.zip
[ssw]: https://www.samtec.com/products/ssw-119-03-g-d
[i2c]: https://www.nxp.com/docs/en/user-guide/UM10204.pdf
[safety]: ../../../docs/operations/safety.md
