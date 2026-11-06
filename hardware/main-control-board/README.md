# Hypernova 메인 제어 보드 · PCBA 1차 프로토타입

Unitree GO-M8010-6 모터 12개를 다리별 RS-485 4개 버스로 연결하고, Jetson Orin Nano Super와 CAN-FD로 통신하는 제어·센서 보드다. 모터 구동기는 모터에 내장되어 있으며, 모터 대전류와 E-stop 차단은 외부 하네스가 담당한다. 이 보드는 로직 전원, 통신, IMU, 전압·전류 감시를 맡는다.

## 현재 상태와 파일

회로도 6장, 부품 145개, 핀 480개, 넷 89개다. PCB는 100 × 80 mm, 4층이며 트랙 1,212구간과 via 491개가 저장되어 있다. 윗면 실장 대상은 43종·106개다.


| 파일 | 용도와 의존성 |
| --- | --- |
| [hypernova-main-board.eprj3](hypernova-main-board.eprj3) | EasyEDA에서 여는 프로젝트 인덱스. `sch/`, `pcb/`와 함께 복사한다 |
| [sch/Schematic1/](sch/Schematic1/) | 회로도 6장과 `.ecfg`, `.evar`. 시트만 따로 옮기지 않는다 |
| [pcb/PCB1.epcb2](pcb/PCB1.epcb2) | 배치·배선·pour가 포함된 PCB |
| [main-control-board.ioc](../../firmware/main-control-board/main-control-board.ioc) | MCU 핀·클럭 설정. STM32CubeMX 6.18.1, STM32Cube FW_G4 V1.6.3 |
| [verification.json](verification.json) | 저장된 DRC·netlist·실장 검사 결과와 원본/제조 출력 SHA-256. |

`manufacturing/`의 Gerber·BOM·CPL은 로컬 출력이며 Git에서 제외한다. 위 EDA 원본 묶음을 공유 기준으로 삼고, EDA 파일을 바꾸면 검증 기록과 필요할 때 생성하는 이미지도 같은 원본을 기준으로 갱신한다. `.ioc`와 회로도가 다르면 한쪽을 임의로 우선하지 말고 핀 배정부터 대조한다.


## 구성과 설계 근거

| 블록 | 채택한 구성 | 이유·주의점 |
| --- | --- | --- |
| MCU | STM32G474RET6, 24 MHz HSE, 170 MHz SYSCLK | NUCLEO-G474RE PoC와 같은 MCU. RS-485 4채널에 하드웨어 DE 사용 |
| 모터 통신 | SP3485EN-L/TR ×4, 4 Mbps 반이중, 다리당 모터 3개 | 17 B 명령+16 B 응답의 선로 시간은 모터당 82.5 µs. 응답 지연을 포함한 실제 주기는 PoC에서 측정 |
| 송신 허용 | SN74LVC08A가 각 DE와 `RS485_TXEN`을 AND | ROM bootloader가 PB14를 출력으로 쓸 수 있어 DE 풀다운만으로 송신을 막을 수 없음. [ST AN2606](https://www.st.com/resource/en/application_note/an2606-stm32microcontroller-system-memory-boot-mode-stmicroelectronics.pdf) Rev 71 Table 118 |
| Jetson | TCAN3413DR CAN-FD, USB FS 예비 링크 | CAN은 별도 트랜시버와 Jetson pinmux 필요. TCAN3403 대신 당시 조달 가능한 TCAN3413 채택 |
| IMU | BMI088, SPI1, 가속도·자이로 별도 CS/인터럽트 | 2번 핀은 라이브러리 이름이 NC여도 데이터시트 연결 표에 따라 GND. [BMI088](https://cdn.sparkfun.com/assets/c/c/e/4/7/BMI088_Datasheet.pdf) rev 1.3 Table 14 |
| 전류·전압 | INA228, I2C3, 외부 high-side Kelvin shunt | INA229 대신 당시 조달 가능한 I2C형 채택. VBUS는 역접속 보호 뒤 `VIN_6S`라 배터리보다 다이오드 강하만큼 낮게 읽음 |
| 로직 전원 | 6S → 퓨즈·역접속 보호·TVS → TPSM365R6V5 → LDL1117 3.3 V | E-stop 앞에서 받아 모터 차단 후에도 상태를 기록. LiDAR·Jetson 전원은 외부에서 별도 공급 |
| USB 전원 | 100 nF, 1 Ω, 4.7 µF, LM66100 역류 차단 | 배터리 없이 로직 구동. 다이오드 누설의 typ 값에 의존하지 않도록 [LM66100](https://www.ti.com/lit/ds/symlink/lm66100.pdf) 사용 |
| 모터 버스 감지 | 100 kΩ/4.7 kΩ 분압 + 100 nF → PA0 | 30 V에서 약 1.35 V. E-stop 후단을 읽으며 차단 자체는 외부 하드웨어가 담당 |
| 디버그 | STDC14, SWD/SWO, USART1 VCP | STLINK-V3용. NUCLEO-G474RE 내장 STLINK-V3E를 외부 보드용 프로브로 가정하지 않음 |

TPSM365R6의 `VCC_U1`은 내부 LDO 출력(약 3.125~3.22 V)이며 5 V 레일이 아니다. PGOOD 풀업은 이 레일에 연결했다. 5 V 출력 캐패시터는 1206 22 µF 3개로, 공차·온도·노화를 반영한 기존 검토 계산은 약 30.8 µF다. [TPSM365R6 데이터시트](https://www.ti.com/lit/ds/symlink/tpsm365r6.pdf)의 실효 용량 요구와 부품 DC bias 특성을 함께 확인해야 한다.

BMI088은 초기 dummy read로 가속도계 SPI 모드를 활성화한다. CS 두 개는 4.7 kΩ 풀업, CAN STB도 풀업으로 기본 대기 상태다. INA228 감지 입력에는 10 Ω 두 개와 차동 100 nF를 둔다. 션트 저항과 감지선 보호 소자는 실제 전류·하네스 조건에 맞춰 확정한다.

## MCU 핀과 펌웨어 조건

| net | 핀 (번호) | MCU 기능 | 연결 대상 |
| --- | --- | --- | --- |
| `RS485_1_TX` | PA2 (14) | USART2_TX | RS-485 1 트랜시버 DI |
| `RS485_1_RX` | PA3 (17) | USART2_RX | RS-485 1 트랜시버 RO |
| `RS485_1_DE` | PA1 (13) | USART2_DE | U13 게이트 입력, 4.7 kΩ 풀다운. 게이트 출력 `RS485_1_DE_G`가 트랜시버 DE와 /RE |
| `RS485_2_TX` | PB10 (30) | USART3_TX | RS-485 2 DI |
| `RS485_2_RX` | PB11 (33) | USART3_RX | RS-485 2 RO |
| `RS485_2_DE` | PB14 (36) | USART3_DE | U13 게이트 입력, 4.7 kΩ 풀다운. 게이트 출력 `RS485_2_DE_G`가 트랜시버 DE와 /RE |
| `RS485_3_TX` | PC10 (52) | UART4_TX | RS-485 3 DI |
| `RS485_3_RX` | PC11 (53) | UART4_RX | RS-485 3 RO |
| `RS485_3_DE` | PA15 (51) | UART4_DE | U13 게이트 입력, 4.7 kΩ 풀다운. 게이트 출력 `RS485_3_DE_G`가 트랜시버 DE와 /RE |
| `RS485_4_TX` | PC12 (54) | UART5_TX | RS-485 4 DI |
| `RS485_4_RX` | PD2 (55) | UART5_RX | RS-485 4 RO |
| `RS485_4_DE` | PB4 (57) | UART5_DE | U13 게이트 입력, 4.7 kΩ 풀다운. 게이트 출력 `RS485_4_DE_G`가 트랜시버 DE와 /RE |
| `RS485_TXEN` | PB2 (26) | GPIO 출력, 초기 Low | U13 게이트 4개의 B 입력, 10 kΩ 풀다운. High일 때만 송신 가능 |
| `CAN_TXD` | PB13 (35) | FDCAN2_TX | TCAN3413 TXD |
| `CAN_RXD` | PB12 (34) | FDCAN2_RX | TCAN3413 RXD |
| `CAN_STB` | PB15 (37) | GPIO 출력, 초기 High | TCAN3413 STB, 4.7 kΩ 풀업(기본 대기). Low에서 정상 모드 |
| `USB_DM` | PA11 (45) | USB_DM | USB-C D−, USBLC6 |
| `USB_DP` | PA12 (46) | USB_DP | USB-C D+, USBLC6 |
| `USB_VBUS_SENSE` | PC4 (22) | ADC2_IN5 | VBUS 10 kΩ/10 kΩ 분압. 문턱 연결 1.90 V, 해제 1.70 V |
| `IMU_SCK` | PA5 (19) | SPI1_SCK | BMI088 SCx |
| `IMU_MISO` | PA6 (20) | SPI1_MISO | BMI088 SDO1, SDO2 |
| `IMU_MOSI` | PA7 (21) | SPI1_MOSI | BMI088 SDx |
| `IMU_CS_ACC` | PA4 (18) | GPIO 출력, 초기 High | BMI088 CSB1, 4.7 kΩ 풀업 |
| `IMU_CS_GYR` | PB0 (24) | GPIO 출력, 초기 High | BMI088 CSB2, 4.7 kΩ 풀업 |
| `IMU_INT_ACC` | PC2 (10) | EXTI2, 상승 에지, 내부 풀다운 | BMI088 INT1 |
| `IMU_INT_GYR` | PC3 (11) | EXTI3, 상승 에지, 내부 풀다운 | BMI088 INT3 |
| `I2C_SCL` | PC8 (40) | I2C3_SCL | INA228 SCL, 4.7 kΩ 풀업 |
| `I2C_SDA` | PC9 (41) | I2C3_SDA | INA228 SDA, 4.7 kΩ 풀업 |
| `INA_ALERT` | PC5 (23) | EXTI5, 하강 에지 | INA228 ALERT, 10 kΩ 풀업 |
| `VMOT_ADC` | PA0 (12) | ADC1_IN1 | 모터 버스 분압(100 kΩ/4.7 kΩ, 비율 0.0449) 중간점. 커넥터 쪽 `VMOT_SENSE`(최대 30 V)와 다른 net |
| `PGOOD_5V` | PB1 (25) | GPIO 입력 | TPSM365R6 PGOOD, 10 kΩ로 `VCC_U1`에 풀업 |
| `LED_HB` | PB6 (59) | GPIO 출력 | heartbeat LED (High에서 켜짐) |
| `LED_ERR` | PB7 (60) | GPIO 출력 | 오류 LED (High에서 켜짐) |
| `HSE_IN` | PF0 (5) | RCC_OSC_IN | 24 MHz 크리스털 |
| `HSE_OUT` | PF1 (6) | RCC_OSC_OUT | 24 MHz 크리스털 |
| `SWDIO` | PA13 (49) | SWD | J2 STDC14 4번 |
| `SWCLK` | PA14 (50) | SWD | J2 STDC14 6번 |
| `SWO` | PB3 (56) | SYS Trace Asynchronous Sw | J2 STDC14 8번 |
| `USART1_TX` | PA9 (43) | USART1_TX | J2 STDC14 14번(STLINK VCP), J3 3번. ROM bootloader USART |
| `USART1_RX` | PA10 (44) | USART1_RX | J2 STDC14 13번(STLINK VCP), J3 4번 |
| `NRST` | PG10-NRST (7) | 리셋 | RESET 버튼, 100 nF, J2 STDC14 12번 |
| `BOOT0` | PB8-BOOT0 (61) | 부트 선택 | BOOT0 버튼, 10 kΩ 풀다운. 다른 기능에 쓰지 않음 |


HSE 24 MHz에서 PLL M=6, N=85, R=2로 170 MHz를 만든다. USB는 HSI48+CRS(USB SOF)를 사용한다. UART는 4 Mbps, 8배 오버샘플링 설정이며 실제 통신 타이밍은 벤치에서 확인한다. CAN nominal/data bitrate는 PoC에서 확정한다.

펌웨어는 UART와 DE 설정을 마친 뒤 `RS485_TXEN`을 올리고, safe state·E-stop 감지 시 내린다. CAN은 준비 후 `CAN_STB`를 Low로 전환한다. USB VBUS 감지의 기존 설계 문턱은 연결 1.90 V, 해제 1.70 V이며 실제 역급전·hot-plug 조건에서 검증한다. 모터의 명령 끊김 동작과 watchdog 시간은 아직 실측이 필요하다.

## 커넥터와 하네스

| 커넥터 | 현재 핀 배정 | 확인 사항 |
| --- | --- | --- |
| J1, JST PH 6핀 | 1 VBAT_IN, 2 GND, 3 SHUNT_P, 4 SHUNT_N, 5 VMOT_SENSE, 6 GND | 로직 전원·감지 전용. 션트 두 선은 Kelvin 인출, 감지선 보호는 션트 쪽에 배치 |
| J4~J7, JST GH 3핀 | 1 SP3485 A, 2 SP3485 B, 3 GND | 채널 1~4. 순정 Unitree 케이블 핀배치와 극성 실측 대기 |
| J8, JST GH 4핀 | 1 비움, 2 CANH, 3 CANL, 4 GND | Jetson 측 트랜시버로 연결. 1번에 전원을 넣지 않음 |
| J9, USB-C | USB FS 데이터와 5 V 입력 | 데이터 지원 A–C 케이블로 Jetson 호스트에 연결 |
| J2, STDC14 | SWDIO 4, SWCLK 6, SWO 8, NRST 12, MCU RX 13, MCU TX 14 | 실물 케이블의 1번 방향 확인 |
| J3, 여분 I/O | PA8, PA9/PA10, PB5, PC0, PC6/PC7 등 | USART1은 J2 VCP와 공유. I2C4 풀업은 보드에 없음 |

다리당 GH 신호 하네스 → Unitree 변환보드 → XT30(2+2) → 모터 3개로 연결한다. 네 다리의 모터 전원은 E-stop 후단에서 별도로 분기한다. JP1~JP4는 RS-485, JP5는 CAN 120 Ω 종단 선택용이다. 종단은 버스 양끝에만 두며 기존 모터 측 종단을 먼저 확인한다.

Unitree 문서의 A/B 표기와 SP3485 표기는 문자만으로 대응시키지 않는다. 기존 정상 USB–RS-485 조합의 실제 프레임 정지 비트에서 높은 선/낮은 선을 확인하고 도통 핀표를 작성한다. 보드의 SP3485 A는 송신 논리 1에서 높은 선이다. [Unitree 매뉴얼](https://techshare.co.jp/faq/wp-content/uploads/2023/12/GO-M8010-6_Motor_Data_User_Manual_V1.0.pdf), [SP3485 데이터시트](https://www.maxlinear.com/ds/sp3485.pdf).

Jetson P3768 J17의 1·2번 TX/RX는 [캐리어 사양서](https://developer.nvidia.com/downloads/assets/embedded/secure/jetson/orin_nano/docs/jetson_orin_nano_devkit_carrier_board_specification_sp.pdf)와 [Linux R36.4.4 CAN 가이드](https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/HR/ControllerAreaNetworkCan.html)의 표기가 다르다. 실제 캐리어 모델·리비전과 회로도를 확인하고 TX 파형으로 판별한다. 외부 CAN-FD 트랜시버, 신호 GND, 동일 bitrate가 필요하다.

## 실장 부품

아래 표는 현재 로컬 제조 BOM에서 가져온 43종·106개다. 과거 재고·가격은 현재 구매 조건으로 옮기지 않았다. 주문 전 재고, 대체품, 회전과 1번 핀을 다시 확인한다.

| 참조번호 | 부품 | 패키지 | LCSC | 수량 |
| --- | --- | --- | --- | ---: |
| C1 | MVK50V47M6.3*8 6.3TP | CAP-SMD_BD6.3-L6.6-W6.6-FD | C165527 | 1 |
| C2 | C3225X7R2A225KT5L0U | C1210 | C76686 | 1 |
| C3 | CL10B104KC8NNNC | C0603 | C15725 | 1 |
| C4,C5,C6 | CL31A226KAHNNNE | C1206 | C12891 | 3 |
| C7,C8,C17,C18 | CL10A105KB8NNNC | C0603 | C15849 | 4 |
| C9,C15,C34 | CL10A475KO8NNNC | C0603 | C19666 | 3 |
| C10,C11,C12,C13,C14,C16,C21,C22,C23,C24,C25,C26,C27,C28,C29,C30,C31,C32,C33,C35 | CC0603KRX7R9BB104 | C0603 | C14663 | 20 |
| C19,C20 | CL10C150JB8NNNC | C0603 | C1644 | 2 |
| D1,D2 | B5819W SL | SOD-123_L2.7-W1.6-LS3.7-RD-1 | C8598 | 2 |
| D4 | SMBJ33A | SMB_L4.6-W3.6-LS5.3-RD | C224019 | 1 |
| D5,D6,D7,D8 | PSM712-LF-T7 | SOT-23-3_L3.0-W1.7-P0.95-LS2.9-BR | C32677 | 4 |
| D9 | PESD2CANFD24V-TR | SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR | C552486 | 1 |
| F1 | 0466001.NRHF | F1206 | C151135 | 1 |
| FB1 | GZ2012D101TF | L0805 | C1015 | 1 |
| J1 | S6B-PH-SM4-TB(LF)(SN) | CONN-SMD_S6B-PH-SM4-TB-LF-SN | C265405 | 1 |
| J2 | HC-PZ127-7.2L-2x7PS | HDR-SMD_14P-P1.27-V-M-R2-C7-LS5.5 | C27985148 | 1 |
| J3 | PZ254-2-05-S | HDR-SMD_10P-P2.54-V-M-R2-C5-LS7.5 | C3294463 | 1 |
| J4,J5,J6,J7 | SM03B-GHS-TB(LF)(SN) | CONN-TH_SM03B-GHS-TB-LF-SN | C514175 | 4 |
| J8 | SM04B-GHS-TB(LF)(SN) | CONN-SMD_4P-P1.25_SM04B-GHS-TB-LF-SN | C189895 | 1 |
| J9 | TYPE-C-31-M-12 | USB-C_SMD-TYPE-C-31-M-12_1 | C165948 | 1 |
| LED1,LED2,LED3 | KT-0603R | LED-SMD_L1.6-W0.8-R-RD | C2286 | 3 |
| R1,R34 | 0603WAF1003T5E | R0603 | C25803 | 2 |
| R2 | 0603WAF9101T5E | R0603 | C23260 | 1 |
| R3,R5,R33,R36,R40,R41 | 0603WAF1002T5E | R0603 | C25804 | 6 |
| R4 | 0603WAF0000T5E | R0603 | C21189 | 1 |
| R6,R7,R8 | 0603WAF1001T5E | R0603 | C21190 | 3 |
| R9,R13,R17,R21,R25,R31,R32,R35,R37,R38 | 0603WAF4701T5E | R0603 | C23162 | 10 |
| R12,R16,R20,R24,R26 | 0603WAF1200T5E | R0603 | C22787 | 5 |
| R27,R28 | 0603WAF5101T5E | R0603 | C23186 | 2 |
| R29,R30 | 0603WAF100JT5E | R0603 | C22859 | 2 |
| R39 | 1206W4F100KT5E | R1206 | C17928 | 1 |
| SW1,SW2 | TS-1187A-B-A-B | SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5 | C318884 | 2 |
| U1 | TPSM365R6V5RDNR | QFN-11_L4.5-W3.5-P0.50-TL_TPSM365R6FRDNR | C19078014 | 1 |
| U2 | LDL1117S33R | SOT-223-4_L6.5-W3.5-P2.30-LS7.0-BR | C435835 | 1 |
| U4 | STM32G474RET6 | LQFP-64_L10.0-W10.0-P0.50-LS12.0-BL | C521608 | 1 |
| U5,U6,U7,U8 | SP3485EN-L/TR | SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL | C8963 | 4 |
| U9 | TCAN3413DR | SOP-8_L4.9-W3.9-P1.27-LS6.0-BL-1 | C22433320 | 1 |
| U10 | USBLC6-2SC6 | SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL | C7519 | 1 |
| U11 | BMI088 | LGA-16_L4.5-W3.0-P0.50-BL | C194919 | 1 |
| U12 | INA228AIDGSR | VSSOP-10_L3.0-W3.0-P0.50-LS4.9-BL | C2887910 | 1 |
| U13 | SN74LVC08ADR | SOIC-14_L8.7-W3.9-P1.27-LS6.0-BL | C468253 | 1 |
| U14 | LM66100DCKR | SC-70-6_L2.0-W1.3-P0.65-LS2.1-BL | C2869734 | 1 |
| Y1 | X322524MOB4SI | CRYSTAL-SMD_4P-L3.2-W2.5-BL | C70590 | 1 |

실장 제외 39개: U3(Pololu 백업), D3(USB 다이오드 대안), R10/R11/R14/R15/R18/R19/R22/R23(바이어스 DNP), JP1~JP5, TP1~TP20, H1~H4. U3를 사용하려면 모듈 핀 순서를 확인하고 R4를 먼저 제거한다. D3 대안을 쓰려면 U14를 제거한다. 솔더 점퍼·테스트 패드·장착 구멍은 별도 구매 부품이 아니다.

## 배선·제조와 남은 확인

적층 의도는 L1 신호/GND pour, L2 GND, L3 3V3, L4 신호/GND pour다. 주문에서 **JLC04161H-7628, 1.6 mm, 외층 1 oz/내층 0.5 oz**를 지정한다. 프로젝트의 물리 적층 메타데이터에는 내부층 두께·유전체가 완전히 정의되지 않아 주문 사양으로 그대로 쓰면 안 된다.

기존 기록의 USB D+/D− 구리 총길이는 26.122/25.988 mm, 차이는 0.134 mm(허용 0.254 mm)다. 주 직선부 폭 0.28 mm, 간격 약 0.155 mm이며 L2 GND를 기준면으로 쓴다. 90 Ω은 설계 목표다.

| 남은 확인 | 완료 기준 |
| --- | --- |
| G2 최종 판정 | 수정본에 대한 위임 검토 결과 기록 |
| 기구·케이블 | 100 × 80 mm, M3 홀 4개(중심 간격 92 × 72 mm), USB 돌출·삽입 공간, 다리별 채널 확정 |
| 제조사 DFM·조립 | U1 마스크 브리지, J9 쉘 하부 배선, 핀 1/회전 확인. 좌우 조립 레일과 fiducial 지정 |
| 부품 확보 | MCU·BMI088 등 재고 및 대체품 확인, BOM/CPL 대조 |
| 전원·감지 | 로직 소비전류·퓨즈, 션트·감지선 보호, USB 돌입/역류, LDO 온도·안정성 측정 |
| 통신·안전 | 1모터→3모터→4버스 순서로 CRC·주기 확인, 명령 끊김·watchdog·E-stop 시험 |

Bring-up은 육안/쇼트 검사 → 전류 제한 전원과 5 V/3.3 V 확인 → SWD/펌웨어 → USB·IMU·INA228 → RS-485 → Jetson CAN-FD → E-stop 감지 순서로 진행한다. 안전 관련 변경에는 [안전 지침](../../docs/operations/safety.md)에 따라 영향·실패 모드·확인·복원 방법을 남긴다.

## 주문 사양과 견적

2026-11-06 JLCPCB 견적 기준이며 금액 단위는 USD다. 한국 수입 부가세·관세는 포함하지 않았다.

| 항목 | 지정값 |
| --- | --- |
| 수량 | PCB 5장, 조립 2장(JLC 최소 수량) |
| PCB | FR-4 4층, 1.6 mm, 녹색, ENIG 1 U". 적층은 위 지정값 사용 |
| 패널 | Panel by JLCPCB, 1×1, V-CUT, 좌우 레일 5 mm, 패널 110 × 80 mm |
| 조립 | Standard PCBA, 윗면 |
| 배송 | UPS Worldwide Express Saver, 한국, 3~5영업일 |

| 금액 항목 | USD |
| --- | ---: |
| PCB 5장 | 48.10 |
| PCBA 2장(부품비 88.14 포함) | 195.21 |
| 배송 | 9.84 |
| New User SMT 쿠폰 | −10.00 |
| **합계** | **243.15** |

- BMI088(C194919)은 JLC에서 Standard Only로 표시되어 Economic PCBA로 조립할 수 없다.
- Single PCB에서 레일을 JLC에 맡기면 크기가 100 × 90 mm로 바뀐다. 80 mm 방향이 늘어나므로 레일이 위·아래 변에 붙는 것으로 판단했고, 윗변에는 USB-C 쉘이 약 1 mm 돌출한다. 그래서 Panel로 좌우 레일을 지정했으며 추가 비용은 약 22.50이다.
- 표면처리 추가금은 유연 HASL 0, 무연 HASL 5.20, ENIG 17.60이다. BMI088(LGA)과 0.5 mm QFN의 납땜을 고려해 ENIG를 골랐다.

### 싼 버전 추정

BMI088을 Economic으로 조립할 수 있는 IMU로 바꾸고 레일 없는 Single PCB로 주문할 때의 추정치다. 실제 견적이 아니며 180~200 범위로 본다.

| 금액 항목 | 현재 견적 | 추정 | 근거 |
| --- | ---: | ---: | --- |
| PCB 5장 | 48.10 | 25.60 | Single PCB + ENIG 견적값 |
| 부품비 | 88.14 | 약 85 | Economic BOM 화면 합계 84.95. 대체 IMU 가격을 BMI088과 같다고 가정 |
| Setup·스텐실 | 34.02 | 약 10 | Economic setup 8(JLC 도움말) + 스텐실 약 1.50(가정) |
| Extended·feeder | 66.65 | 약 67 | Extended 22종 유지 가정 |
| SMT·X-ray·포장 | 6.40 | 약 3 | Economic 항목에 X-ray 없음 |
| 배송 | 9.84 | 9.84 | 같은 UPS 가정 |
| New User SMT 쿠폰 | −10.00 | −10.00 | 같은 쿠폰 가정 |
| **합계** | **243.15** | **약 190** | |

- 표면처리를 바꾸면 무연 HASL 약 178, 유연 HASL 약 173이다.
- Economic BOM 화면에서 BMI088 외 42종은 자동 선택됐다. 대체 IMU의 Economic 가능 여부는 확인하지 않았으며, LGA 패키지라면 같은 제한에 걸릴 수 있다.
- IMU를 바꾸면 회로도, PCB, `.ioc`, 펌웨어, 검증 기록을 다시 작업해야 한다.
- Economic에서는 Panel을 고를 수 없어 좌우 레일을 지정하지 못한다. USB-C가 돌출한 보드를 레일 없이 조립해 주는지 JLC 확인이 필요하다.

## 협업 환경과 독립 검증

사용한 EDA는 **嘉立创EDA专业版, EasyEDA Pro 중국 내수용 Linux V4.1.94**다. 다른 지역판·버전과의 V4 프로젝트 호환성은 검증하지 않았다. 이어서 작업할 때 우선 같은 버전에서 프로젝트 묶음을 열어 확인한다.

회로도·초기 PCB 생성에는 EasyEDA가 공개한 공식 [easyeda-eprj3-skill](https://github.com/easyeda/easyeda-eprj3-skill)을 사용했다. 당시 사용본은 로컬에서 수정한 버전이다.

남아 있는 주의점은 **NC 핀 처리**다. 작업 당시에는 여러 NC 핀이 같은 net으로 묶이는 문제를 로컬에서 수정했다. 공식 2.2.4는 NC 표식을 추가했지만 stub·동일 이름 label과 PCB net을 유지한다고 [변경 이력](https://github.com/easyeda/easyeda-eprj3-skill/blob/22fd028a768de2b2b8d1ead6aae40a4cd84a4d22/CHANGELOG.md)에 명시되어 있어, 완전히 해결됐다고 판단하지 않았다. 최신 클라이언트에서 재현 시험은 하지 않았으며, 재빌드 시 NC 핀의 실제 netlist와 PCB 연결을 확인해야 한다.

다른 PC에서는 저장소를 받은 뒤 이 폴더의 `.eprj3`, `sch/`, `pcb/`를 함께 열어 작업을 시작한다. 핀 설정은 저장소의 `.ioc`와 대조한다. 기존 작성자의 생성 입력, 로컬 스킬 수정본, 캐시, 검토 스크립트는 작업을 이어가기 위한 필수 의존성이 아니다. 자동 생성이나 재빌드를 시도할 때는 배치·배선이 바뀔 수 있으므로 원본을 보존한 별도 사본에서 진행한다.

새로 발견한 문제는 해당 부품·핀·넷, 판단 근거와 재현 방법을 함께 기록한다. 검증 결과에는 대상 커밋 또는 파일 해시, 사용한 도구·버전, 검사 방법과 확인하지 못한 범위를 남긴다. 수정 후에는 변경한 원본을 기준으로 다시 검증하고 이 문서와 검증 기록을 갱신한다.
