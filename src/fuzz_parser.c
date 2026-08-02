/* Copyright 2026 Gentoo Authors
 * SPDX-License-Identifier: GPL-2.0-or-later OR MIT
 */

/* libFuzzer entry point for the dep-string scanner.
 *
 * This drives the pure-C side only -- no Python objects are built -- so it can
 * run without an interpreter.  Build it with:
 *
 *     meson setup build -Dfuzzing=true -Db_sanitize=address,undefined
 *     ninja -C build src/fuzz_parser
 *     ./build/src/fuzz_parser corpus/
 *
 * It is not part of `meson test`; the fixed cases live in test_parser.c.
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "dep_parser_core.h"

/* Counting visitor: exercises the callback paths without allocating. */
static int fuzz_on_atom(void *ctx, UNUSED const char *start, UNUSED int len,
                        UNUSED const AtomInfo *info)
{
    ++*(unsigned long *)ctx;
    return 1;
}

static int fuzz_on_group_start(UNUSED void *ctx, UNUSED const char *op,
                               UNUSED int op_len)
{
    return 1;
}

static int fuzz_on_group_end(UNUSED void *ctx)
{
    return 1;
}

/* Derive activity from the flag text so both branches get explored without
 * needing a USE list in the input. */
static int fuzz_use_active(UNUSED void *ctx, const char *flag, int len,
                           int is_neg)
{
    int active = len > 0 && (flag[0] & 1);
    return is_neg ? !active : active;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    static int initialized;
    if (!initialized) {
        init_cc_table();
        initialized = 1;
    }

    /* Copy so the scanner runs against an exactly-sized buffer and any read
     * past the end is caught by the sanitizer rather than landing in slack. */
    char *buf = malloc(size ? size : 1);
    if (!buf)
        return 0;
    memcpy(buf, data, size);

    unsigned long atoms = 0;
    DepVisitor visitor = {
        .ctx            = &atoms,
        .on_atom        = fuzz_on_atom,
        .on_group_start = fuzz_on_group_start,
        .on_group_end   = fuzz_on_group_end,
        .use_active     = fuzz_use_active,
    };

    DepScanner scanner = { buf, buf + size, NULL };
    skip_whitespace(&scanner);
    if (scanner.cur < scanner.end)
        scan_dep_list(&scanner, &visitor);

    /* Also drive the single-atom entry, which has its own validation. */
    DepScanner atom_scanner = { buf, buf + size, NULL };
    AtomInfo info;
    scan_atom(&atom_scanner, &info);

    free(buf);
    return 0;
}

/* vim: set ts=4 sw=4 et: */
