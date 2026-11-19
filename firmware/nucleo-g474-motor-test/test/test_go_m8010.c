/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/*
 * Host test for the GO-M8010-6 codec. The encode vectors were produced by the
 * official libUnitreeMotorSDK_Linux64.so (MotorCmd::modify_data) and are the
 * same ones go_m8010_test.py selftest checks.
 */
#include "go_m8010.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures;

static void expect(int ok, const char *what)
{
    printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
    failures += !ok;
}

static int hex_to_bytes(const char *hex, uint8_t *out, size_t max)
{
    size_t n = 0;
    unsigned v;
    int used;
    while (n < max && sscanf(hex, " %2x%n", &v, &used) == 1) {
        out[n++] = (uint8_t)v;
        hex += used;
    }
    return (int)n;
}

static void test_encode(void)
{
    static const struct {
        go_m8010_cmd_t cmd;
        const char *ref;
    } cases[] = {
        {{0, 1, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}, "FE EE 10 00 00 00 00 00 00 00 00 00 00 00 00 B5 79"},
        {{0, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f}, "FE EE 00 00 00 00 00 00 00 00 00 00 00 00 00 65 23"},
        {{3, 1, 1.5f, -6.28f * 6.33f, 12.345f, 0.1f, 0.02f}, "FE EE 13 80 01 AD F9 7D FB 00 00 80 00 19 00 7C D3"},
        {{14, 1, -0.75f, 10.0f, -3.3f, 1.0f, 0.5f}, "FE EE 1E 40 FF 97 01 C6 BC FF FF 00 05 80 02 1E FB"},
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        uint8_t want[GO_M8010_TX_LEN], got[GO_M8010_TX_LEN];
        char label[96];
        hex_to_bytes(cases[i].ref, want, sizeof want);
        go_m8010_encode(&cases[i].cmd, got);
        snprintf(label, sizeof label, "encode vector %zu matches the SDK", i);
        expect(memcmp(want, got, sizeof want) == 0, label);
    }
}

static void test_decode(void)
{
    /* id 2, mode 1, tau 1.5, dq 4 counts, q 0x00010000, temp -5, merror 2, force 100 */
    uint8_t f[GO_M8010_RX_LEN] = {0xFD, 0xEE, 0x12, 0x80, 0x01, 0x04, 0x00, 0x00, 0x00, 0x01, 0x00,
                                  0xFB, (uint8_t)((100 << 3) | 2), (uint8_t)((100 << 3) >> 8)};
    const uint16_t crc = go_m8010_crc(f, 14);
    f[14] = (uint8_t)crc;
    f[15] = (uint8_t)(crc >> 8);

    go_m8010_fbk_t fb;
    expect(go_m8010_decode(f, &fb), "decode accepts a valid frame");
    expect(fb.id == 2 && fb.mode == 1, "decode id and mode");
    expect(fabsf(fb.tau - 1.5f) < 1e-6f, "decode tau");
    expect(fabsf(fb.dq - 4.0f / 256.0f * 6.28318f) < 1e-6f, "decode dq");
    expect(fabsf(fb.q - 65536.0f * 6.28318f / 32768.0f) < 1e-4f, "decode q");
    expect(fb.temp_c == -5 && fb.merror == 2 && fb.force == 100, "decode temp, merror, force");

    f[5] ^= 0x01;
    expect(!go_m8010_decode(f, &fb), "decode rejects a CRC mismatch");
    f[5] ^= 0x01;
    f[0] = 0xFE;
    expect(!go_m8010_decode(f, &fb), "decode rejects a command header");
}

static void test_clamp(void)
{
    const go_m8010_cmd_t cmd = {15, 7, 1000.0f, -1000.0f, 1e9f, 99.0f, -1.0f};
    uint8_t f[GO_M8010_TX_LEN];
    go_m8010_encode(&cmd, f);
    expect(f[2] == 0x7F, "id and mode are masked to 4 and 3 bits");
    expect((int16_t)(f[3] | f[4] << 8) == (int16_t)(127.99f * 256.0f), "tau clamps to +127.99");
    expect((uint16_t)(f[11] | f[12] << 8) == (uint16_t)(25.599f * 1280.0f), "kp clamps to 25.599");
    expect(f[13] == 0 && f[14] == 0, "kd clamps to 0");
}

int main(void)
{
    test_encode();
    test_decode();
    test_clamp();
    printf(failures ? "%d FAILED\n" : "all passed\n", failures);
    return failures != 0;
}
