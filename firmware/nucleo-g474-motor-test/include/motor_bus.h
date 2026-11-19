/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/*
 * One RS-485 half-duplex bus on UART4 at 4 Mbps (PC10 TX, PC11 RX, PA15 hardware DE).
 * Each exchange sends one 17-byte command and polls for the 16-byte reply.
 */
#ifndef MOTOR_BUS_H
#define MOTOR_BUS_H

#include <stdbool.h>
#include <stdint.h>

#include "go_m8010.h"

#define MOTOR_BUS_BAUD 4000000u
#define MOTOR_BUS_REPLY_TIMEOUT_US 2000u /* measured from the end of our stop bit */

typedef enum {
    MOTOR_BUS_OK,
    MOTOR_BUS_TIMEOUT,  /* no frame with a valid header and CRC arrived in time */
    MOTOR_BUS_TX_STUCK, /* the UART did not finish sending; clock or init problem */
} motor_bus_status_t;

typedef struct {
    uint32_t sent;
    uint32_t ok;
    uint32_t timeouts;
    uint32_t rx_errors; /* framing, noise or overrun flags seen while waiting */
    uint32_t junk_bytes; /* received bytes that did not end up in a valid frame */
} motor_bus_stats_t;

bool motor_bus_init(void);
/* Actual baud rate after BRR rounding, in bit/s. */
uint32_t motor_bus_actual_baud(void);
/* rtt_us: from the first command byte written to the last reply byte read. May be NULL. */
motor_bus_status_t motor_bus_exchange(const go_m8010_cmd_t *cmd, go_m8010_fbk_t *fbk, uint32_t *rtt_us);
void motor_bus_stats(motor_bus_stats_t *out);
void motor_bus_stats_reset(void);

#endif
