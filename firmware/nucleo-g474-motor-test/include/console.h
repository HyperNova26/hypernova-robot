/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/* LPUART1 on PA2/PA3, wired to the ST-LINK virtual COM port. 115200 8N1, interrupt-driven rings. */
#ifndef CONSOLE_H
#define CONSOLE_H

#include <stdbool.h>
#include <stddef.h>

#define CONSOLE_BAUD 115200u

void console_init(void);
/* Queues bytes for transmission. Blocks only while the 2 KiB ring is full. */
void console_write(const char *data, size_t len);
/* Returns the next received byte, or -1 when none is waiting. */
int console_getc(void);
/* Waits until every queued byte has left the UART. */
void console_flush(void);

#endif
