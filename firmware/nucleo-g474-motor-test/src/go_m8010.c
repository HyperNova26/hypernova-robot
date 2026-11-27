/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
#include "go_m8010.h"

/* The SDK scales with this truncated constant, so the encoder must use it too. */
#define SDK_TWO_PI 6.28318f

static float clampf(float x, float lo, float hi)
{
    return x < lo ? lo : (x > hi ? hi : x);
}

static void put_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static void put_u32(uint8_t *p, uint32_t v)
{
    put_u16(p, (uint16_t)v);
    put_u16(p + 2, (uint16_t)(v >> 16));
}

static uint16_t get_u16(const uint8_t *p)
{
    return (uint16_t)(p[0] | (p[1] << 8));
}

static uint32_t get_u32(const uint8_t *p)
{
    return (uint32_t)get_u16(p) | ((uint32_t)get_u16(p + 2) << 16);
}

uint16_t go_m8010_crc(const uint8_t *data, size_t len)
{
    /* Linux crc_ccitt: reflected polynomial 0x8408, initial value 0. */
    uint16_t crc = 0;
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 1u) ? (uint16_t)((crc >> 1) ^ 0x8408u) : (uint16_t)(crc >> 1);
        }
    }
    return crc;
}

void go_m8010_encode(const go_m8010_cmd_t *cmd, uint8_t frame[GO_M8010_TX_LEN])
{
    const float tau = clampf(cmd->tau, -127.99f, 127.99f);
    const float dq = clampf(cmd->dq, -804.0f, 804.0f);
    const float q = clampf(cmd->q, -411774.0f, 411774.0f);
    const float kp = clampf(cmd->kp, 0.0f, 25.599f);
    const float kd = clampf(cmd->kd, 0.0f, 25.599f);

    frame[0] = 0xFE;
    frame[1] = 0xEE;
    frame[2] = (uint8_t)((cmd->id & 0x0Fu) | ((cmd->mode & 0x07u) << 4));
    /* Casts truncate toward zero, matching the SDK and go_m8010_test.py. */
    put_u16(&frame[3], (uint16_t)(int16_t)(tau * 256.0f));
    put_u16(&frame[5], (uint16_t)(int16_t)(dq * 256.0f / SDK_TWO_PI));
    put_u32(&frame[7], (uint32_t)(int32_t)(q * 32768.0f / SDK_TWO_PI));
    put_u16(&frame[11], (uint16_t)(kp * 1280.0f));
    put_u16(&frame[13], (uint16_t)(kd * 1280.0f));
    put_u16(&frame[15], go_m8010_crc(frame, 15));
}

bool go_m8010_is_feedback(const uint8_t frame[GO_M8010_RX_LEN])
{
    return frame[0] == 0xFD && frame[1] == 0xEE && get_u16(&frame[14]) == go_m8010_crc(frame, 14);
}

bool go_m8010_decode(const uint8_t frame[GO_M8010_RX_LEN], go_m8010_fbk_t *fbk)
{
    if (!go_m8010_is_feedback(frame)) {
        return false;
    }
    const uint16_t err_force = get_u16(&frame[12]);
    fbk->id = frame[2] & 0x0Fu;
    fbk->mode = (frame[2] >> 4) & 0x07u;
    fbk->tau = (float)(int16_t)get_u16(&frame[3]) / 256.0f;
    fbk->dq = (float)(int16_t)get_u16(&frame[5]) / 256.0f * SDK_TWO_PI;
    fbk->q = (float)(int32_t)get_u32(&frame[7]) * SDK_TWO_PI / 32768.0f;
    fbk->temp_c = (int8_t)frame[11];
    fbk->merror = err_force & 0x07u;
    fbk->force = (err_force >> 3) & 0x0FFFu;
    return true;
}

const char *go_m8010_error_name(uint8_t merror)
{
    static const char *const names[] = {"OK", "overheat", "overcurrent", "overvoltage", "encoder fault"};
    return merror < sizeof names / sizeof names[0] ? names[merror] : "unknown";
}
