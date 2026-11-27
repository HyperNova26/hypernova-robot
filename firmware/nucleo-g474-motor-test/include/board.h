/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/* NUCLEO-G474RE board support: clock, LD2, B1, RS-485 transmit enable, cycle timer, watchdog. */
#ifndef BOARD_H
#define BOARD_H

#include <stdbool.h>
#include <stdint.h>

#include "stm32g4xx_hal.h"

#ifndef HN_SYSCLK_MHZ
#define HN_SYSCLK_MHZ 170
#endif

typedef enum {
    BOARD_RESET_POWER_OR_PIN,
    BOARD_RESET_WATCHDOG,
    BOARD_RESET_SOFTWARE,
    BOARD_RESET_OTHER,
} board_reset_t;

void board_init(void);
bool board_hse_ok(void); /* false when the crystal did not start and HSI16 drives the PLL */
board_reset_t board_reset_cause(void);

static inline uint32_t board_cycles(void) { return DWT->CYCCNT; }
static inline uint32_t board_cycles_per_us(void) { return SystemCoreClock / 1000000u; }

void board_led(bool on);
void board_led_toggle(void);
bool board_button_pressed(void); /* B1, polarity learned at boot (do not hold it while resetting) */

/* PB2 "transmit allowed": second input of the carrier's 74HC08 gate in front of the transceiver DE. */
void board_rs485_tx_allow(bool allow);

void board_watchdog_start(void); /* IWDG about 0.5 s, frozen while the core is halted by a debugger */
void board_watchdog_kick(void);

#endif
