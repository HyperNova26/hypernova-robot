<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# P2.3 하네스 제작표

2026-11-28 기준입니다. 표의 길이는 두 커넥터 접점 사이의 **시제품 최대 편도 길이**이고 제조사 제공 케이블은 별도로 표시했습니다. 별도 표기가 없으면 연동선 구리 도체를 씁니다. 서로 다른 방향에서 보는 암수 커넥터는 번호로 도통 검사합니다. 각 관절의 전 가동 범위에서 서비스 루프를 확보하고 길이를 늘리는 경우 전압·신호 시험을 반복합니다.

| 조립품·수량 | 길이·선경 | 캐리어 또는 출발 단자 → 상대 단자 |
| --- | --- | --- |
| 다리 통신 J3~J6 ×4 | 다리별 신호 경로 합계 1.0 m, 24 AWG 120 Ω 차동쌍 + 기준선 | XHP-3의 1=A, 2=B, 3=신호 GND → Unitree 어댑터 RS485 A, B, 기준 GND. 3모터를 순서대로 통과해 마지막 모터에 120 Ω을 둡니다. 각 모터의 전원은 별도로 분기합니다. |
| ToF J7~J10 ×4 | 각 0.20 m, 26 AWG 5심, 각 버스 선의 실효 케이블 정전용량 ≤100 pF/m | PHR-5의 1,2,3,4,5 → Pololu 3415의 VIN, GND, SCL, SDA, XSHUT. 모듈 1×7은 VDD 쪽부터 VDD, VIN, GND, SDA, SCL, XSHUT, GPIO1 순서이므로 2,3,5,4,6번에 대응합니다. VDD와 GPIO1은 비웁니다. |
| IMU J11 ×1 | 0.10 m, 28 AWG. 두 소켓을 공통 지지대에 고정합니다. | 1→P1.1·P1.2 (VDD/VDDIO), 2→P1.3·P2.6 (GND·PS), 3→P2.3 SCK, 4→P2.4 SDI, 5→P2.3 SDO, 6→P2.1 가속도 CS, 7→P2.5 자이로 CS, 8→P1.6 가속도 INT1, 9→P1.7 자이로 INT3. Bosch가 P1.7을 표에 GPIO3/INT2로 표시하며 회로에서는 U1.12입니다. P1·P2 나머지는 비웁니다. |
| INA228 디지털 J13 ×1 | 0.20 m, 26 AWG, ≤100 pF/m | PHR-4의 1=3.3 V, 2=GND, 3=SCL, 4=SDA → INA228EVM **J3.6, J3.4, J3.10, J3.12**. J3은 2.00 mm 2×6 수헤더입니다. SW0·SW1=GND로 주소 0x40을 선택합니다. SCB/PAMB와 USB는 빼고 나머지 접점을 비웁니다. |
| 캐리어 CAN J14 ×1 | 0.10 m, 26 AWG 6심 | XHP-6의 1→Click 7 (VIO 3.3 V), 2→8 (GND), 3→13 (U1.1 TxD), 4→14 (U1.4 RxD), 5→3 (U1.8 STB), 6→10 (U1.3 VCC, 보호 5 V). 좌우 1×8 소켓 두 개를 비틀림 방지 브래킷으로 고정합니다. |
| Jetson CAN ×1 | 0.10 m, 26 AWG | P3768의 **전용** J17.4 → Click 7, J17.3 → Click 8·3 (STB Low), CAN_TX → Click 13, CAN_RX ← Click 14. 5 V는 동일 Jetson J12.2 → Click 10. 디버그할 때도 두 Click 간 전원 핀을 이어 붙이지 않습니다. |
| CAN 버스 ×1 | 0.50 m, 24 AWG, 120 Ω 꼬임쌍 + GND | 각 Click의 수 플러그(제조사 CAD의 TE 5747840-5)에 TE 5-747905-5 암 솔더컵과 후드를 끼웁니다. 두 DE-9의 7↔7 CANH, 2↔2 CANL, 3↔3 GND만 결선합니다. 양끝 내장 60.4 Ω 두 개의 직렬 종단을 사용합니다. |
| 라이다 J15 ×1 | 캐리어 피그테일 0.15 m, 28 AWG. OEM ML-X-STANDARD-A-3M 3 m + 제조 공차 | GHR-04V-S 1→OEM SYNC 분기 SIG_OUT (원형 C1.7), 2→SIG_OUT_GND (C1.8). 캐비티 3·4는 비웁니다. OEM의 SIG_IN·SIG_IN_GND를 각각 절연합니다. OEM 하네스 세대에 따라 색상이 달라 신호 라벨을 확인합니다. |
| 경고음 J16 ×1 | 0.15 m, 26 AWG | PHR-2의 1=3.3 V → 180 Ω 직렬 → 피에조 +, 2=BUZZER_SINK → 피에조 −. 피에조 바로 양단에 2.2 kΩ 방전 저항을 둡니다. 저항과 단자에 수축튜브·장력 완화를 적용합니다. |
| 주 입력 J17 ×1 | 0.30 m, 22 AWG 전원·GND 쌍 | 외부 DDR-15L-5의 +V·−V → XHP-2의 1·2. 부하가 걸린 J17에서 5.15~5.25 V를 맞춥니다. |
| 보조접점 J18 ×0 기본, 옵션 ×1 | 0.50 m, 26 AWG 꼬임쌍 | PHR-3의 1→외부 NC 무전압 접점, 3→접점 공통, 2 비움. 주 모터 차단은 외부 하드웨어가 수행합니다. |
| RS-485 모듈 J19~J22 ×4 | 각각 0.08 m. VCC/GND 24 AWG, 로직 26 AWG, A/B 24 AWG 120 Ω 꼬임쌍 | XHP-7의 **1** 전용 3.3 V→EVM J6.1, **2** GND→J6.2, **3** RO←J1.3, **4** DI→J4.4, **5** RSE→J2.3(/RE)·J3.4(DE), **6** A→J17.1(Y), **7** B→J17.2(Z). RSE의 10 kΩ 풀다운은 EVM측 분기점–J6.2에 설치합니다. 해당 다리 버스는 J19↔J3, J20↔J4, J21↔J5, J22↔J6입니다. |
| RS-485 벅 J23 ×1 | 0.08 m. VIN과 GND_IN, VOUT과 GND_OUT 각각 22 AWG 한 쌍, PG/EN 26 AWG. 입력 루프 전체 ≤1 µH. | XHP-8의 **1** PG←TI TP4, **2** EN→J2.2, **3** 보호 VIN→J1.2, **4** GND_IN→J1.1, **5** +3V3_RS485←J4.1, **6** GND_OUT→J4.2. **7·8은 빈 캐비티**입니다. EVM J1/J4는 서로 다른 5 mm 나사 단자입니다. 8핀 J23과 6핀 J14가 서로 구분됩니다. |
| Nucleo 계통 승압 J24 ×1 | 0 m, 캐리어 2.54 mm 1×3 암소켓 직결 | Pololu #4942에 선실장한 수직 1×3 수헤더를 VIN→보호 전원, GND→공통 GND, VOUT→U6 입력에 끼웁니다. 양끝 VIN/VOUT 표시와 모듈 고정 가이드를 확인합니다. |

J19~J22 조립품은 EVM J1~J4의 Mill-Max 2×4 수헤더에 각각 전용 암소켓을 결합합니다. TI 핀 번호는 J1이 좌상단인 상면 기준이고, J1/J2와 J3/J4의 I/O 위치가 다릅니다. EVM J6.3 및 J17.3(EARTH), J5와 J14는 비웁니다. J7.1–2를 단락해 VL=VCC로 둡니다. J8의 2×10 암소켓에는 방향을 고정한 수플러그를 장착하고 **1–3** TERM_TX=VL, **5–7** H/F=VL, **10–12** TERM_RX=GND, **14–16** SLR=GND만 연결합니다. EVM J1~J4에는 정적 레벨 점퍼를 추가하지 않습니다. EVM의 R3을 공급자가 제거한 뒤 RO 유휴 High를 검사합니다. [TI THVD1424EVM 그림 3-1·4-2](https://www.ti.com/lit/ug/sllu356/sllu356.pdf)

J23의 TP4에는 제작자가 고정 리드를 납땜·절연하고 하네스를 EVM 지지대에 묶습니다. EVM J2의 점퍼를 제거하고 가운데 2번에만 결선한 3핀 암 하우징으로 EN을 연결합니다. J6 1–2를 MODE, J3 7–8을 FPWM으로 설정하고 고정 출력형 J5는 비웁니다. 모듈 J1 바로 옆에 **47 µF/25 V 전해와 단방향 P6KE8.2A**를 병렬 연결합니다. J1.2는 전해 +와 TVS K(띠), J1.1은 전해 −와 TVS A입니다. 각 접속부를 짧게 분기한 뒤 단자당 허용된 선 하나만 체결하도록 절연 압착·지지합니다. 두 부품과 단자 사이의 루프를 작게 유지하고, 말단 커패시터의 사용 조건 유효용량 ≥30 µF를 확인합니다. [TI 전원 EVM 회로도](https://www.ti.com/lit/ug/snvu846/snvu846.pdf)

J11의 삼각형/사각 패드와 대응하는 **빨간 피복 1번과 ‘1/VDD’ 라벨을 하네스 양끝**에 둡니다. 모듈 측 P2에는 별도 ‘P2.1/CS’ 표시를 붙입니다. 무전원에서 공급 및 공통 접지, 두 CS와 두 INT를 각각 검사합니다. [Bosch 셔틀 도면][bosch] · [Pololu ToF 핀맵][tof] · [TI INA228EVM 그림 6-1][ina]

J11 하네스 제작처는 22 × 14 mm 셔틀의 두 수헤더 중심 간격 **17.78 mm**와 각 열 1.27 mm 피치를 기준으로 7핀·9핀 소켓을 공통 지지기판에 실장합니다. Bosch 도면에 따라 두 줄의 시작 위치를 맞추고, 길이 3 mm·단면 0.4 mm인 수핀과 위에서 삽입하는 소켓의 물림이 1.40 mm 이상인지 확인합니다. 셔틀의 방향 표식과 기구 기준축을 함께 표시하고 케이블 장력이 소켓에 걸리지 않도록 고정합니다. [Bosch 외형도][bosch] · [Samtec 소켓 물림 치수](https://suddendocs.samtec.com/catalog_english/clp_sm.pdf)

DE-9 암수와 외형은 [Click 3D 도면](https://download.mikroe.com/documents/2d-3d-files/can_fd_3_click_2d_3d_files.rar)과 [짝 커넥터](https://www.te.com/en/product-5-747905-5.html)를 대조했습니다. CAN 모듈 두 개 모두 JP1 가운데(VIO)–3V3 위치에 도통하고 5V 위치가 개방인지 확인한 뒤 연결합니다. 선택 패드가 5 V에 놓인 모듈은 3.3 V 위치로 설정한 상태로 납품받습니다. J1과 J2는 한 쌍의 신호를 뽑는 패드이므로 쇼트캡을 끼우지 않습니다. 각 모듈 단독 CANH–CANL 약 121 Ω, 전체 무전원 버스 약 60 Ω을 확인합니다. [Click 회로도][can]

Jetson **P3768** 하드웨어 사양 SP-11324 v1.3 표 3-5는 J17.1=TX, J17.2=RX이고 Jetson Linux 문서에는 반대로 적혀 있습니다. J17이 미실장이면 1×4 헤더를 먼저 실장한 뒤, 하네스 TX/RX 접점을 삽입하기 전에 실제 보드 리비전의 회로도 또는 분리 상태 송신 파형으로 **Jetson 출력 → 트랜시버 TxD**, **트랜시버 RxD → Jetson 입력**인지 확인합니다. 40핀 확장 헤더에서 29/31번을 CAN으로 쓰는 다른 보드의 배정은 여기 적용하지 않습니다. [NVIDIA 캐리어 사양 다운로드][nv-hw] · [NVIDIA CAN 안내][nv-can]

## 외부 배터리·모터 하네스

아래 수량과 퓨즈는 **6S, 한 다리 3모터 고정 시험대 저부하 PoC**용입니다. 실물 팩 최대 충전전압 전형값은 25.2 V입니다. 퓨즈 선정에 쓰는 보수적인 PoC 운용 한도는 다리 합산 10 A 연속, 메인 합산 20 A 연속입니다. 모터 데이터시트에 기재된 토크와 무부하 속도는 같은 동작점에서의 팩 전류가 아닙니다. 네 다리 동시 구동에는 계측한 지속·피크·회생 파형과 분기별 허용 전류로 별도 산정합니다. [Unitree 모터·케이블][motor] · [Littelfuse 287 시리즈][fuses]

| 조립품·수량 | 길이·선경 | 배선과 보호 |
| --- | --- | --- |
| 메인 피드 ×1 | 배터리에서 분배부까지 0.30 m, +/− 10 AWG. 30 A 홀더의 짧은 12 AWG 팩토리 리드는 그대로 사용합니다. | 배터리 + → 단자에서 0.05 m 이내 30 A 메인 퓨즈 → 션트 LINE 전류단 → 션트 LOAD 전류단 → 분배부 +. 배터리 −는 분배부 음극 버스바에 직결합니다. 션트 뒤에서 Jetson·LiDAR·DC/DC·모터를 각각 분기합니다. 극성 표시가 있는 절연 단자와 보호 덮개를 사용합니다. |
| 다리 분기 ×1, 모터 피드 ×3 | 다리 입력 +/− 12 AWG 각 0.25 m, 각 모터 +/− 16 AWG 각 0.40 m | 외부 DC 정격 비상 차단 접점 → 다리별 15 A 퓨즈 → 3분배 → 모터별 독립 전원. 퓨즈 아래 가장 가는 16 AWG와 납품 XT30(2+2) 단자의 정격이 보호 범위에 드는지 확인합니다. 공용 전원선으로 모터 3대의 전류를 한 XT30 단자에 통과시키지 않습니다. |
| 모터 하이브리드 ×3 | 각 모터 피드와 동일, 전원 16 AWG 및 데이터 24 AWG 차동쌍 | Unitree XT30(2+2) 기성 케이블의 큰 접점 전원 +/−, 작은 접점 RS485 A/B. 분기점에서 전원은 병렬 분기, A/B는 다리 안에서 순차 연결합니다. A/B 기준 GND는 다리 입구의 지정 기준점에만 결합합니다. 어댑터의 표시와 모터 제조사 하네스로 도통 검사합니다. |
| 계측 ×1 | 션트에서 EVM까지 0.20 m, IN+/IN− 꼬임쌍과 VBUS 22 AWG. EVM 및 캐리어는 배터리 음극과 한 개의 정의된 기준 결합점을 사용합니다. | 션트 LINE 켈빈 나사 → 1 A 퓨즈 → EVM J1.5 (IN+), LOAD 켈빈 나사 → 별도 1 A 퓨즈 → J1.3 (IN−), LINE 켈빈 나사 → 별도 1 A 퓨즈 → J1.2 (VBUS). 각 퓨즈는 탭에서 0.05 m 이내입니다. J1.6/.4는 비웁니다. J1.1은 EVM GND로 J13 GND와 같습니다. GND 기준점과 원거리 EVM 사이에 모터 전류의 추가 리턴을 만들지 않습니다. |

ATO 퓨즈 예시는 32 V DC, 정격 차단용량 1 kA입니다. 설치 전 팩의 예상 단락전류와 회생을 포함한 최고 전압이 이 범위인지 확인합니다. 식별되지 않은 팩에서는 전류 제한형 실험 전원으로 위 PoC를 시작합니다. 30 A와 15 A의 시간–전류곡선은 모든 사고 전류에서 하위 퓨즈만 먼저 열리는 것을 보증하지 않습니다. 외부 DC/DC·Jetson·LiDAR 입력은 각 장치와 해당 분기선 정격에 맞는 독립 보호를 사용합니다. 캐리어 F1은 5 V 입력용입니다.

외장 션트는 Bourns/Riedon RSN-250-50B입니다. 250 A/50 mV, 0.2 mΩ ±0.1%, 제조사 연속 권장 상한 166.67 A입니다. 30 A에서 6 mV/0.18 W, 60 A에서 12 mV/0.72 W입니다. INA228의 ±40.96 mV에서는 약 ±204.8 A에서 포화합니다. 션트 값과 범위를 펌웨어에 설정하고 영점, 기준 계측값과 양방향 극성을 확인합니다. EVM R1은 미실장 상태입니다. IN+와 IN−의 퓨즈·홀더·리드 길이는 서로 맞추고 VBUS용 세 번째 퓨즈를 분리합니다. [Bourns 션트 정격][shunt] · [TI EVM 외부 션트 연결][ina] · [TI INA228][ina-chip]

[bosch]: https://www.bosch-sensortec.com/media/boschsensortec/downloads/shuttle_board_flyer/application_board_3_1/bst-bmi088-sf000.pdf
[tof]: https://www.pololu.com/product/3415
[ina]: https://www.ti.com/lit/ug/sbou241e/sbou241e.pdf
[ina-chip]: https://www.ti.com/lit/ds/symlink/ina228.pdf
[can]: https://download.mikroe.com/documents/add-on-boards/click/can_fd_3_click/can-fd-click-schematic-v100.pdf
[nv-hw]: https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/hardware_layout.html
[nv-can]: https://docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/HR/ControllerAreaNetworkCan.html
[motor]: https://shop.unitree.com/products/go1-motor
[fuses]: https://www.littelfuse.com/assetdocs/littelfuse_datasheet_287_atof_r2.7.pdf?assetguid=43dcdce8-8ca2-426f-8998-7e566f048d40
[shunt]: https://www.bourns.com/docs/product-datasheets/rsn.pdf
