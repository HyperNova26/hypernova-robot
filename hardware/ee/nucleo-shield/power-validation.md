<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Nucleo 캐리어 전원 검증

2026-11-28 기준 설계 검토입니다. J17 보호 회로와 Nucleo-G474RE를 사용하고, 외장 RS-485는 Waveshare 4777, ToF는 ShillehTek CJMCU-531을 검토합니다. 전류와 전압은 데이터시트와 회로에서 산출한 값입니다. 완성 하네스를 연결한 실측은 남아 있습니다.

## J17 입력과 E5V 여유

J17의 **5.15–5.25 V**는 실제 부하에서 커넥터 양단에 걸리는 전압입니다. Nucleo CN7 6번 E5V에는 정상 동작 중 **4.75–5.25 V**를 유지해야 하며 ST의 입력 전류 상한은 **500 mA**입니다. JP5를 5–6번 E5V로 두고 SB5를 연결합니다. Nucleo의 U12 `LD39050PU33R`가 3.3 V를 생성하고, ST-LINK는 별도 3.3 V 레귤레이터를 통해 E5V 또는 USB에서 전원 공급을 받습니다. [ST Nucleo 사용자 매뉴얼][nucleo] · [MB1367-G474RE 회로도][mb1367]

U6 `LT3086`의 명목 출력은 **4.95 V**, R37 2.00 kΩ 기준 명목 전류 제한은 **400 mA**입니다. 실제 제한점은 부품 허용오차와 전류 모니터 오차에 따라 달라집니다. 500 mA 조건에서 데이터시트의 최대 드롭아웃 235 mV를 쓰면, 5.15 V 입력에서 F1·동박·단자·리턴의 합산 전압 강하에 남는 여유는 **165 mV**입니다. F1 1 A 퓨즈의 냉간 저항 0.128 Ω을 적용하면 500 mA에서 약 64 mV가 소모되고, 나머지 경로와 동작 여유로 약 101 mV가 남습니다. [ADI LT3086 데이터시트][lt3086] · [Littelfuse 251 퓨즈][fuse]

P2.1의 J17–F1–U6–CN7 6번 양극 배선은 폭 0.45 mm이며, 구간별 16.40 mm·6.59 mm·76.53 mm로 합계 **99.52 mm**입니다. 35 µm 구리와 실온을 가정하면 저항 약 109 mΩ, 500 mA에서 강하 약 54 mV입니다. 퓨즈와 드롭아웃을 함께 적용한 E5V 추정치는 약 **4.797 V**이며, 접점·GND 리턴·온도·과도응답에 남은 여유는 약 **47 mV**입니다. TP1에서 CN7 6번까지도 68.33 mm이므로 실제 E5V는 CN7에서도 측정합니다.

과전압·저전압 비교기의 보조 전원 측 명목 임계는 각각 **5.20 V**와 **4.36 V**입니다. J17 측 임계는 F1·D10·R39의 강하까지 포함합니다. 특히 5.15 V에서 부하가 큰 경우 D10의 순방향 전압과 R39 강하까지 반영한 저전압 차단 여유를 실측합니다. U6 출력 전류가 제한점에 닿거나 외부 DC/DC가 전류 제한에 들어가면 입력·출력 전압이 낮아지고 재시동이 반복될 수 있습니다. J17 쪽 전압과 E5V를 동시에 측정해 구분합니다. [ADI LT3086 데이터시트][lt3086] · [Diodes SB1100 데이터시트][sb1100]

## 3.3 V 부하 예산

| 부하 | 전류 예산 | 실측 또는 확인 항목 |
| --- | --- | --- |
| RS-485 4채널, Waveshare 4777 `SP3485` | 송신 채널당 **75 mA**, 4채널 **300 mA** 설계 할당입니다. 54 Ω 차동 부하에서 3.6 V/54 Ω에 무부하 IC 전류와 모듈 LED, 스위칭 여유를 더한 값입니다. | 실제 전원은 **3.135–3.465 V**로 유지합니다. 칩의 무부하 전류 사양과 75 mA 산정값을 부하 송신 실측으로 확인합니다. 모듈에는 120 Ω 종단이 실장되어 있습니다. 각 버스의 반대쪽 끝에 120 Ω을 두며, 두 끝 사이의 불필요한 추가 종단을 제거합니다. [Waveshare 4777 제품 정보][rs485] · [모듈 회로도][rs485-sch] · [SP3485 데이터시트][sp3485] |
| ToF 4개, ShillehTek CJMCU-531 `VL53L1X` | 칩당 장거리 측정 중 평균 상한 **18 mA**와 피크 약 **40 mA**로 계산하면, 4개 합계 평균 72 mA와 동시 피크 160 mA입니다. 전압·온도는 칩 데이터시트의 명목 조건입니다. | 모듈의 레귤레이터·레벨 변환·풀업 전류와 시동 피크가 추가됩니다. 모든 센서에서 주소 지정과 최대 선택 측정 주기를 검증합니다. 모듈 문서의 입력 사양은 3.3–5 V입니다. [ST VL53L1X 데이터시트][tof] · [ShillehTek 모듈 안내][tof-module] |
| CAN 1개, Switch Science `SSCI-110044` / `TCAN3413` | 정상 종단 60 Ω에서 지배 상태 **55.3 mA** 상한을 사용합니다. VCC 55 mA와 VIO 0.3 mA를 포함합니다. | 실제 CAN FD 프레임과 종단에서 확인합니다. 50 Ω 시험 조건의 TI VCC 상한은 60 mA입니다. [TI TCAN3413 데이터시트][can] · [Switch Science 모듈][can-module] |
| IMU 1개, Boardoza BMI088 SPI | BMI088 칩의 정상 모드 **5.15 mA** 참고값입니다. | 모듈 총전류·시동전류를 측정합니다. 제조사 입력 범위 3.3–5.5 V를 모듈 단자에서 확인합니다. [Bosch BMI088][imu] · [Boardoza 모듈][imu-module] |
| INA228EVM 1개 | INA228 칩 최대 **1.1 mA**에 EVM LED와 I²C 풀업 전류를 더합니다. | R5·R6 각 4.7 kΩ 풀업이 이미 EVM에 있습니다. 캐리어 R11·R12는 파형을 확인한 후 필요할 때 실장합니다. [TI INA228 데이터시트][ina] · [EVM 회로도][ina-evm] |
| J16 외부 수동 피에조 | 사용할 경우 하네스 방전 저항과 구동 피크를 포함해 **최대 20 mA**를 배정합니다. | 선정 부저와 PWM에서 전류, 발생 음량과 3.3 V 변동을 확인합니다. |
| Nucleo 및 캐리어 부하 | STM32G474, U1, LED, 풀업, LiDAR 동기 신호와 U12 자체 소모를 더합니다. 초기 구성에서 J18·R28·R29·D7·D8·C4는 미실장입니다. | 타깃 MCU의 실행 클록, 실제 펌웨어·디버그 상태, LED, 하네스와 각 모듈의 입력 용량에 따라 달라집니다. Nucleo 단독 E5V와 3.3 V 전류부터 측정합니다. [ST STM32G474 데이터시트][mcu] |
| ST-LINK | Nucleo의 별도 ST-LINK 3.3 V 레귤레이터는 150 mA 정격입니다. 실제 전류는 USB 상태에 따라 달라집니다. | USB 연결 전 E5V에서 공급되는 전류, 연결 직후와 VCP 사용 중 E5V 및 USB 전류를 따로 측정합니다. 150 mA는 측정값으로 사용하지 않습니다. [MB1367-G474RE 회로도][mb1367] |

RS-485와 ToF가 겹치는 경우 표의 모듈 부하 예산은 **약 542 mA**입니다. ToF에 동시 피크 대신 측정 중 평균을 적용해도 **약 454 mA**입니다. STM32에 70 mA, 캐리어 기타 부하에 10 mA를 배정하면 전체 동시 피크 예산은 **약 622 mA + E5V에서 공급되는 ST-LINK 전류**입니다. STM32 70 mA는 170 MHz에서 주변장치를 끈 ST 특성표의 56 mA 최대값에 주변장치·I/O 여유 14 mA를 더한 설계값입니다. 모듈 실측과 최종 펌웨어가 필요한 예산이며, 시동 돌입전류는 별도입니다. 이 예산은 J17 명목 400 mA와 Nucleo U12의 500 mA 출력 정격을 넘습니다. 3.3 V에 400 mA가 흐르고 E5V가 4.75–5.05 V이면 U12 손실은 약 0.58–0.70 W입니다. [STM32G474 데이터시트 표 22·35][mcu] · [ST LD39050 데이터시트][ld39050]

RS-485 모듈을 J17 보호 회로 앞단에서 분기한 별도 안정화 3.3 V 전원으로 공급하면 4채널의 300 mA를 Nucleo 계통에서 분리할 수 있습니다. 이 경우 위의 MCU와 캐리어 배정을 포함한 E5V 동시 피크 예산은 **약 322 mA + ST-LINK 전류**입니다. 400 mA 기준 잔여분은 약 78 mA이며, 제한점이 350 mA일 때 약 28 mA입니다. 별도 전원은 300 mA 부하 급변과 모듈의 시동을 검증합니다. 전원 출력은 독립시키고 신호 기준 GND를 연결합니다. 한쪽 전원만 켠 상태의 RO·DI·RSE 역급전과 전원 순서도 검증합니다. P2.1의 기본 모듈 전원은 캐리어 3.3 V이므로 전원 분리 또는 허용 동시 구동 조건을 확정한 뒤 발주를 승인합니다.

## 실물 시험과 합격 기준

1. **캐리어 단독.** Nucleo·USB·배터리·모터·센서를 분리하고 TP1–TP3에 더미 부하를 둡니다. 전류 제한형 실험 전원과 오실로스코프로 J17, U6 IN, 비교기 보조 전원, U6 SHDN, TP1을 측정합니다. 5.15·5.20·5.25 V에서 전원 시동과 부하 급증·급감을 반복합니다. 정상 출력이 안정된 뒤의 E5V와 최대 출력이 각각 **4.75 V 이상**, **5.25 V 이하**인지를 확인합니다. 더미 부하를 올려 전원 자체의 전류 제한과 구분하여 U6 지속 제한점과 순간 피크를 기록합니다. 시험한 지속 제한점은 **500 mA 이내**여야 합니다. [ADI LT3086 데이터시트][lt3086]
2. **차단과 복귀.** 캐리어 단독으로 J17 입력의 느린 상승·하강, 과전압 단계 인가와 유지, 저전압 강하, 역극성을 각각 시험합니다. 차단·복귀 전압, SHDN 상태, TP1 최고값·방전 시간을 기록합니다. 차단 상태에서는 정상 E5V 공급이 중단되어야 하고, 과도 중에도 TP1은 **5.25 V 이하**여야 합니다. 정상 입력 범위로 돌아오면 E5V가 안정적으로 복귀하고 반복 시동이 발생하지 않는지 확인합니다. 시험 전압·전류는 검증 대상 부품과 실험 전원의 정격 범위에서 설정합니다.
3. **Nucleo 단독 시동.** JP5·SB5를 확인하고 J17만 켭니다. 녹색 LD3 확인 후 ST-LINK USB를 연결합니다. USB 연결·분리와 VCP 전송에서 E5V, TP2, MCU 리셋과 전류를 기록합니다. 외부 전원을 끈 상태에서 USB나 주변장치의 역급전이 캐리어 레일을 유지하지 않는지 확인합니다. [ST Nucleo 사용자 매뉴얼][nucleo]
4. **실제 하네스.** 주변장치를 하나씩 연결하고, 이후 실제 종단에서 RS-485 4채널 송신, ToF 4개 최대 설정 구동, CAN 통신, INA228 측정, IMU SPI와 부저를 겹쳐 시험합니다. J17이 5.15 V일 때 CN7 6번의 E5V와 각 모듈 단자 전압, 피크·평균 전류, U6·U12·F1 및 단자 온도를 기록합니다. SHDN이 낮아지거나 주기적 재부팅·데이터 손실이 발생하면 원인을 확인합니다. RS-485 모듈 단자 전압은 **3.135–3.465 V**를 유지해야 합니다. ToF·IMU 모듈 공급 하한은 각각의 제조사 조건을 적용하고, 3.30 V 미만으로 내려가는 경우 공급 대책 또는 낮은 입력을 보장하는 모듈이 필요합니다. [SP3485 데이터시트][sp3485] · [ShillehTek 모듈 안내][tof-module] · [Boardoza 모듈][imu-module]
5. **동작 범위 확정.** 시제품에서 정상 부하의 측정값이 U6 실측 제한점과 E5V 500 mA 상한 아래에 드는지 확인합니다. 의도한 최저·최고 주위 온도와 최장 하네스에서 시동과 부하 시험을 반복합니다. `LM393AP`의 주위 동작 정격 0–70 °C를 적용합니다. 검증한 전원 장치, 배선, 모듈 품번 및 리비전, 펌웨어와 송신·측정 패턴을 기록합니다. [TI LM393AP][lm393]

## 실물 확정 전 확인할 항목

- 안정화 DC/DC의 정확한 품번, 부하에서 J17까지의 전압 강하, 기동 전류 제한, 출력 리플과 회복 파형을 확정합니다.
- RS-485의 전원 분리 여부나 펌웨어 동시 구동 조건을 확정합니다. 모듈별 실측 송신 전류와 3.3 V 배선, 종단을 확인합니다.
- ToF·IMU 정확한 리비전과 허용 입력 최저값을 확정합니다. 커넥터와 케이블 끝에서의 전압, 시동 피크, XSHUT·SPI 신호 레벨을 확인합니다.
- J17 차단·복귀, 5.15 V 부하, 실제 모듈 시동·동작 온도 시험의 기록으로 허용 운용 조건을 확정합니다.

[nucleo]: https://www.st.com/resource/en/user_manual/um2505-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf
[mb1367]: https://www.st.com/resource/en/schematic_pack/mb1367-g474re-c05_schematic.pdf
[lt3086]: https://www.analog.com/media/en/technical-documentation/data-sheets/lt3086.pdf
[fuse]: https://www.littelfuse.com/ja-jp/products/fuses-overcurrent-protection/fuses/axial-radial-thru-hole-fuses/pico-fuses-axial-radial-thru-hole-fuses/251
[sb1100]: https://www.diodes.com/datasheet/download/SB1100.pdf
[rs485]: https://www.waveshare.com/product/rs485-board-3.3v.htm
[rs485-sch]: https://files.waveshare.com/upload/b/bf/RS485-Board-Schematic.pdf
[sp3485]: https://files.waveshare.com/upload/2/25/MaxLinear-SP3485.pdf
[tof]: https://www.st.com/resource/en/datasheet/vl53l1x.pdf
[tof-module]: https://shillehtek.com/blogs/shillehtek-product-manuals/vl53l1x-tof-sensor-4m-pre-soldered-esp32-manual
[can]: https://www.ti.com/lit/ds/symlink/tcan3413.pdf
[can-module]: https://www.switch-science.com/products/11004
[imu]: https://www.bosch-sensortec.com/en/products/motion-sensors/imus/bmi088
[imu-module]: https://github.com/Boardoza/Boardoza_BMI088_6-Axis_IMU_Breakout_Board
[ina]: https://www.ti.com/lit/ds/symlink/ina228.pdf
[ina-evm]: https://www.ti.com/lit/pdf/sbou241#page=23
[mcu]: https://www.st.com/resource/en/datasheet/stm32g474re.pdf
[ld39050]: https://www.st.com/resource/en/datasheet/ld39050.pdf
[lm393]: https://www.ti.com/product/LM393A/part-details/LM393AP
