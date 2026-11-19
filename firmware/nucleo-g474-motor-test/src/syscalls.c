/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/* Minimal newlib-nano system calls: stdout/stderr go to the console with LF -> CRLF. */
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>

#include "console.h"

extern char _end;            /* first free byte after .bss, from the linker script */
extern char _estack;         /* top of RAM */
extern char _Min_Stack_Size; /* reserved stack size; the symbol address is the value */

int _write(int fd, const char *buf, int len)
{
    (void)fd;
    int start = 0;
    for (int i = 0; i < len; ++i) {
        if (buf[i] == '\n') {
            console_write(&buf[start], (size_t)(i - start));
            console_write("\r\n", 2);
            start = i + 1;
        }
    }
    console_write(&buf[start], (size_t)(len - start));
    return len;
}

void *_sbrk(ptrdiff_t incr)
{
    static char *heap_end = &_end;
    char *const limit = &_estack - (uintptr_t)&_Min_Stack_Size;
    if (heap_end + incr > limit) {
        errno = ENOMEM;
        return (void *)-1;
    }
    char *const prev = heap_end;
    heap_end += incr;
    return prev;
}

int _read(int fd, char *buf, int len)
{
    (void)fd;
    (void)buf;
    (void)len;
    return 0;
}

int _close(int fd)
{
    (void)fd;
    return -1;
}

int _fstat(int fd, struct stat *st)
{
    (void)fd;
    st->st_mode = S_IFCHR;
    return 0;
}

int _isatty(int fd)
{
    (void)fd;
    return 1;
}

int _lseek(int fd, int offset, int whence)
{
    (void)fd;
    (void)offset;
    (void)whence;
    return 0;
}

int _getpid(void) { return 1; }

int _kill(int pid, int sig)
{
    (void)pid;
    (void)sig;
    errno = EINVAL;
    return -1;
}

void _exit(int status)
{
    (void)status;
    for (;;) {
    }
}
