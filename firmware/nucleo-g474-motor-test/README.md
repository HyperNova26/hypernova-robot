# NUCLEO-G474RE 모터 벤치 펌웨어 · 1차 PoC

PC에서 USB–RS-485 어댑터로 돌리던 GO-M8010-6 시험(`moter_test`의 `go_chain.cpp`, `go_m8010_test.py`)을 NUCLEO-G474RE에서 돌리는 펌웨어입니다. 메인 제어 보드 Rev A와 같은 MCU·같은 핀(UART4 PC10/PC11, DE PA15, 송신 허용 PB2)을 써서, 4 Mbps 통신 여유와 모터 응답 시간을 미리 측정합니다.

**상태 (2026-11-19, Asia/Seoul)**: 빌드와 codec host test만 확인했습니다. Nucleo 실물, RS-485 배선, 모터 구동은 아직 시험하지 않았습니다.

## 지원 범위

| 항목 | 내용 |
| --- | --- |
| 보드 | NUCLEO-G474RE (MB1367), STM32G474RET6, HSE 24 MHz crystal |
| 모터 | Unitree GO-M8010-6 최대 3대, ID 0·1·2, RS-485 버스 1개 |
| 트랜시버 | SparkFun BOB-10124 (SP3485, 3.3 V, 10 Mbps) |
| 툴체인 | STM32CubeCLT 1.22.0: arm-none-eabi-gcc 14.3.1, CMake 4.3.1, Ninja, STM32_Programmer_CLI |
| ST 라이브러리 | cmsis-core v5.9.0, cmsis-device-g4 v1.2.6, stm32g4xx-hal-driver v1.2.7 |

ST 라이브러리는 저장소에 복사하지 않습니다. 첫 configure 때 [cmake/stm32cube-g4.cmake](cmake/stm32cube-g4.cmake)가 GitHub에서 commit 고정 archive를 받아 SHA256을 확인합니다(약 18 MB, `build/_deps/`). 라이선스는 cmsis-core·cmsis-device-g4가 Apache-2.0, HAL이 BSD-3-Clause입니다.

## 빌드와 플래시

이 디렉터리에서 실행합니다. `arm-none-eabi-gcc`와 `cmake`는 STM32CubeCLT 설치 경로가 `PATH`에 있어야 합니다.

```bash
cmake --preset nucleo
```

```bash
cmake --build --preset nucleo
```

Nucleo를 USB로 연결한 뒤 ST-LINK로 씁니다.

```bash
cmake --build --preset nucleo --target flash
```

콘솔은 ST-LINK 가상 COM 포트입니다(115200 8N1, 보통 `/dev/ttyACM0`).

```bash
picocom -b 115200 /dev/ttyACM0
```

- 기본 preset `nucleo`는 SYSCLK 170 MHz입니다. 메인 보드와 같은 클럭이며, 4 Mbps가 나누어떨어지지 않아 실제 baud가 4.048 Mbps(+1.19 %)입니다.
- `nucleo-160mhz` preset은 SYSCLK 160 MHz로 정확히 4 Mbps를 냅니다. 170 MHz에서 통신 오류가 보이면 이 preset으로 같은 시험을 반복해 비교합니다. 두 결과는 메인 보드 클럭 결정에 씁니다.
- codec host test(호스트 gcc)는 SDK가 만든 명령 frame 4개와 비교합니다.

```bash
cmake -S test -B build/host-test && cmake --build build/host-test && ctest --test-dir build/host-test
```

## 배선 (캐리어 PCB 전, 점퍼선)

모터 전원을 끈 상태에서 연결합니다. CN 번호는 Nucleo 윗면 기준입니다([UM2505](https://www.st.com/resource/en/user_manual/dm00556337-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf) 핀맵).

| Nucleo | 신호 | BOB-10124 JP9 |
| --- | --- | --- |
| CN7-1 · PC10 | UART4_TX | 2 · RX-I (SP3485 DI) |
| CN7-2 · PC11 | UART4_RX | 3 · TX-O (SP3485 RO) |
| CN7-17 · PA15 | UART4_DE, 4.7 kΩ로 GND 풀다운 | 4 · RTS (SP3485 DE와 /RE) |
| CN7-16 · 3V3 | 전원 | 1 · 3-5V |
| CN7-20 · GND | 접지 | 5 · GND |

- PA15는 리셋 직후 JTDI 내부 풀업이 켜져 있습니다. 4.7 kΩ 풀다운이 없으면 부팅하는 몇 ms 동안 트랜시버가 버스를 구동합니다.
- PB2(CN10-22)는 캐리어 PCB에서 74HC08로 DE를 한 번 더 막는 송신 허용 신호입니다. 펌웨어가 UART 초기화 뒤 High로 올립니다. 점퍼선 시험에서는 연결하지 않아도 됩니다.
- BOB의 A·B를 모터 신호선 A·B에, BOB GND를 모터 전원 음극(V−)에 연결합니다. 공통 접지가 없으면 수신이 불안정합니다. Unitree 변환보드 쪽 A·B 순서는 PC에서 쓰던 USB–RS-485 어댑터 배선과 대조합니다.
- 종단은 버스 양끝에만 A–B 사이 약 120 Ω입니다. BOB와 마지막 모터 쪽 기존 종단을 테스터로 먼저 잽니다.
- 흔한 MAX485 5 V 모듈은 2.5 Mbps급이라 4 Mbps에 쓰지 않습니다.

## 콘솔 명령

| 명령 | 동작 |
| --- | --- |
| `info` | SYSCLK, HSE 사용 여부, UART4 실제 baud와 오차, 직전 리셋 원인 |
| `scan` | ID 0~14에 mode 0(정지)을 보내 응답한 ID 표시 |
| `check [n]` | ID 0~n−1에 mode 0, 각도와 온도 표시. `n`은 1~3, 기본 3 |
| `bench [n] [count]` | mode 0을 `count`회 연속 송수신(기본 3대, 1000회). 응답률, 왕복 시간 최소/평균/최대, 버스 오류 수 |
| `read <id>` | 토크 0 FOC(kp=kd=τ=0)로 10 Hz 피드백. 손으로 출력축을 돌려 봅니다 |
| `run [n]` | `go_chain run`과 같은 프로필. 3대는 0.1 rev/s 3초, 1~2대는 0.5 rev/s(30 rpm) 15초 |
| `stop` | ID 0~2에 mode 0 |

- `run`은 먼저 `check`를 통과해야 시작합니다. 가속·감속 구간(3대 0.5초, 1~2대 2초)이 있고, 1.25초마다 각 출력축이 정방향으로 1° 이상 움직였는지 봅니다. 아니면 전체 정지합니다.
- 1~2대 프로필은 출력축마다 약 6.5회전합니다. 연속 회전이 가능한 무부하 축에서만 실행합니다.
- FOC 명령의 감쇠는 출력축 기준 kd 1.6 N·m·s/rad입니다(`go_chain.cpp`와 같음).
- `bench`의 왕복 시간은 명령 첫 바이트 송신부터 응답 마지막 바이트 수신까지입니다. 선로 시간만 82.5 µs(17 B + 16 B, 4 Mbps)이고, 나머지가 DE 전환과 모터 응답 지연입니다.

## 정지와 안전 동작

| 상황 | 펌웨어 동작 |
| --- | --- |
| 부팅 | ID 0~2에 mode 0을 한 번씩 보냅니다. 구동 중 리셋됐을 때를 대비합니다 |
| `run`·`read`·`bench` 중 B1 또는 아무 키 | 루프를 끝내고 대상 ID에 mode 0을 최대 3회 보냅니다 |
| 응답 누락, CRC 오류, 모터 오류 코드, mode 불일치 | `run`은 즉시 전체 정지를 시도합니다 |
| 펌웨어 멈춤 | IWDG 약 0.5초(LSI 오차로 0.4~0.6초) 뒤 MCU 리셋, 부팅 정지 명령 |

- 통신이 끊긴 모터는 펌웨어가 멈출 수 없습니다. 명령이 끊겼을 때 GO-M8010-6가 스스로 멈추는지도 아직 확인하지 않았습니다. 모터 전원 차단 스위치를 손 닿는 곳에 둡니다.
- B1은 부팅 때 읽은 레벨을 "안 눌림"으로 기억합니다. 리셋할 때 B1을 누르고 있지 않습니다.
- 시험 단계와 중단 기준은 [안전 지침](../../docs/operations/safety.md)을 따릅니다.

## 첫 시험 순서

1. 모터 전원 없이 Nucleo만 연결해 플래시하고 `info`를 확인합니다. `HSE 24 MHz crystal`과 baud 오차(170 MHz +1.19 %, 160 MHz 0.00 %)가 보여야 합니다.
2. 전원을 끄고 트랜시버와 모터 한 대(ID 0)를 연결합니다. 모터 몸체는 고정하고 출력축은 비웁니다.
3. 모터 전원을 켜고 `scan` → `check 1` → `bench 1 1000` 순서로 응답과 왕복 시간을 기록합니다.
4. `read 0`으로 출력축을 손으로 돌려 각도 부호와 크기를 확인합니다.
5. `run 1`로 30 rpm 구동을 확인합니다.
6. 세 대를 연결해 `check`, `bench`, `run 3`, `run 2`를 반복합니다.
7. 오류가 있으면 `nucleo-160mhz`로 다시 플래시해 같은 순서로 비교합니다.

`scan`에 아무것도 안 보이면 모터 전원, A·B 순서, 공통 GND, PA15–RTS 배선, CN7-17과 MCU PA15 사이 도통 순서로 봅니다.

## 시험 기록

결과는 커밋, preset, 모터 대수, 전원(전압·전류 제한)과 함께 남깁니다.

| 날짜 | 커밋 | preset | 모터 | `bench` 응답률 | 왕복 시간 min/avg/max (µs) | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 미측정 | | | | | | |

## 남은 일

- 실물 Nucleo·모터 시험과 위 표 채우기
- 170 MHz와 160 MHz 측정 결과를 메인 보드 클럭·UART 설정에 반영
- FDCAN2(PB12/PB13, STB PB15)와 TCAN3403으로 Jetson 연결
- 팀 보유 IMU 연결(모델·전압·인터페이스 확인 후)

## 참고

- 프로토콜과 기준 frame: [Unitree actuator SDK](https://github.com/unitreerobotics/unitree_actuator_sdk) `motor_msg_GO-M8010-6.h`, 그리고 같은 frame을 검증한 `moter_test/go_m8010_test.py selftest`
- `check`·`run` 동작: `moter_test/go_chain.cpp` (저장소 밖 로컬 시험 코드)
