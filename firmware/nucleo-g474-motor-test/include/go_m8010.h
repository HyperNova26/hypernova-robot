/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/*
 * Unitree GO-M8010-6 RS-485 frame codec, following unitree_actuator_sdk
 * include/unitreeMotor/include/motor_msg_GO-M8010-6.h.
 *
 *   TX 17 B: FE EE | id:4 mode:3 | tau q8 | dq q8/2pi | q q15/2pi | kp*1280 | kd*1280 | CRC16
 *   RX 16 B: FD EE | id:4 mode:3 | tau q8 | dq q8/2pi | q q15/2pi | temp | merror:3 force:12 | CRC16
 *
 * Every value on the wire is rotor side. Callers convert to the output shaft with
 * GO_M8010_GEAR_RATIO. Pure C with no MCU dependency so the host test can build it.
 */
#ifndef GO_M8010_H
#define GO_M8010_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define GO_M8010_TX_LEN 17u
#define GO_M8010_RX_LEN 16u
#define GO_M8010_GEAR_RATIO 6.33f
#define GO_M8010_MAX_ID 14u /* 15 is broadcast; motors do not reply to it */

/* SDK queryMotorMode(GO_M8010_6, ...). Mode 2 (encoder calibration) is never sent. */
#define GO_M8010_MODE_BRAKE 0u
#define GO_M8010_MODE_FOC 1u

typedef struct {
    uint8_t id;
    uint8_t mode;
    float tau; /* rotor N*m */
    float dq;  /* rotor rad/s */
    float q;   /* rotor rad */
    float kp;  /* rotor N*m/rad */
    float kd;  /* rotor N*m*s/rad */
} go_m8010_cmd_t;

typedef struct {
    uint8_t id;
    uint8_t mode;
    float tau; /* rotor N*m */
    float dq;  /* rotor rad/s */
    float q;   /* rotor rad */
    int8_t temp_c;
    uint8_t merror; /* 0 OK, 1 overheat, 2 overcurrent, 3 overvoltage, 4 encoder fault */
    uint16_t force;
} go_m8010_fbk_t;

uint16_t go_m8010_crc(const uint8_t *data, size_t len);
void go_m8010_encode(const go_m8010_cmd_t *cmd, uint8_t frame[GO_M8010_TX_LEN]);
/* Returns false on a bad header or CRC. */
bool go_m8010_decode(const uint8_t frame[GO_M8010_RX_LEN], go_m8010_fbk_t *fbk);
/* True when frame holds a header and CRC that match a feedback frame. */
bool go_m8010_is_feedback(const uint8_t frame[GO_M8010_RX_LEN]);
const char *go_m8010_error_name(uint8_t merror);

#endif
