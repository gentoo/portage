/* Copyright 2026 Gentoo Authors
 * SPDX-License-Identifier: GPL-2.0-or-later OR MIT
 */

#include "dep_parser_core.h"
#include <stdio.h>
#include <string.h>

static int failures = 0;
static int passes = 0;

#define FAIL(fmt, ...) \
    do { fprintf(stderr, "FAIL %s:%d: " fmt "\n", __FILE__, __LINE__, ##__VA_ARGS__); failures++; } while (0)
#define PASS() \
    do { passes++; } while (0)

#define CHECK(expr) \
    do { if (expr) { PASS(); } else { FAIL("%s", #expr); } } while (0)

static int span_eq(const char *ptr, size_t len, const char *expected)
{
    if (!expected)
        return ptr == NULL;

    if (!ptr)
        return 0;

    size_t elen = strlen(expected);
    return len == elen && memcmp(ptr, expected, elen) == 0;
}

/* Parse a complete atom string; return 1 on success and fill *info. */
static int parse_atom_str(const char *s, AtomInfo *info)
{
    DepScanner p = { s, s + strlen(s), NULL };
    if (!scan_atom(&p, info))
        return 0;

    return p.cur == p.end;  /* must consume all input */
}

static void test_scan_version(void)
{
    static const struct {
        const char *input;
        int ok;
        const char *ver;
    } cases[] = {
        { "1",                 1, "1"                },
        { "1.0",               1, "1.0"              },
        { "1.2.3",             1, "1.2.3"            },
        { "1.0a",              1, "1.0a"             },
        { "1.0_alpha",         1, "1.0_alpha"        },
        { "1.0_alpha1",        1, "1.0_alpha1"       },
        { "1.0_beta2_rc3",     1, "1.0_beta2_rc3"    },
        { "1.0_pre",           1, "1.0_pre"          },
        { "1.0_pre1",          1, "1.0_pre1"         },
        { "1.0_rc1",           1, "1.0_rc1"          },
        { "1.0_p1",            1, "1.0_p1"           },
        { "1.0_p",             1, "1.0_p"            },
        { "1.0-r1",            1, "1.0-r1"           },
        { "1.0-r12",           1, "1.0-r12"          },
        { "99999999",          1, "99999999"         },
        { "1.0*",              1, "1.0*"             },
        /* must stop at terminating chars */
        { "1.0 rest",          1, "1.0"              },
        { "1.0:slot",          1, "1.0"              },
        { "1.0[use]",          1, "1.0"              },
        { "1.0)",              1, "1.0"              },
        /* invalid */
        { "alpha",             0, NULL               },
        { ".1",                0, NULL               },
        { "1.",                0, NULL               },
    };

    for (int i = 0; i < ARRAY_SIZE(cases); i++) {
        const char *s = cases[i].input;
        DepScanner p = { s, s + strlen(s), NULL };
        int ok = scan_version(&p);
        if (ok != cases[i].ok) {
            FAIL("scan_version(%s): got %d, want %d", s, ok, cases[i].ok);
            continue;
        }
        if (ok && cases[i].ver) {
            size_t vlen = (size_t)(p.cur - s);
            if (!span_eq(s, vlen, cases[i].ver)) {
                FAIL("scan_version(%s): ver=%.*s, want %s", s, (int)vlen, s, cases[i].ver);
                continue;
            }
        }
        PASS();
    }
}

static void test_scan_atom_basic(void)
{
    AtomInfo a;

    /* simple unversioned */
    CHECK(parse_atom_str("cat/pkg", &a));
    CHECK(span_eq(a.cat, a.cat_len, "cat"));
    CHECK(span_eq(a.pkg, a.pkg_len, "pkg"));
    CHECK(a.ver == NULL);
    CHECK(a.op  == NULL);
    CHECK(a.block == NULL);

    /* operator + version */
    CHECK(parse_atom_str(">=cat/pkg-1.2.3", &a));
    CHECK(span_eq(a.op,  a.op_len,  ">="));
    CHECK(span_eq(a.cat, a.cat_len, "cat"));
    CHECK(span_eq(a.pkg, a.pkg_len, "pkg"));
    CHECK(span_eq(a.ver, a.ver_len, "1.2.3"));

    /* single blocker */
    CHECK(parse_atom_str("!cat/pkg", &a));
    CHECK(span_eq(a.block, a.block_len, "!"));

    /* double blocker */
    CHECK(parse_atom_str("!!cat/pkg", &a));
    CHECK(span_eq(a.block, a.block_len, "!!"));

    /* tilde operator */
    CHECK(parse_atom_str("~cat/pkg-1.0", &a));
    CHECK(span_eq(a.op, a.op_len, "~"));
    CHECK(span_eq(a.ver, a.ver_len, "1.0"));

    /* glob */
    CHECK(parse_atom_str("=cat/pkg-1.0*", &a));
    CHECK(span_eq(a.ver, a.ver_len, "1.0*"));
}

static void test_scan_atom_hyphenated_name(void)
{
    AtomInfo a;

    CHECK(parse_atom_str("sys-apps/portage", &a));
    CHECK(span_eq(a.cat, a.cat_len, "sys-apps"));
    CHECK(span_eq(a.pkg, a.pkg_len, "portage"));

    /* digit segment in package name */
    CHECK(parse_atom_str("=dev-java/log4j-12-api-2.0", &a));
    CHECK(span_eq(a.cat, a.cat_len, "dev-java"));
    CHECK(span_eq(a.pkg, a.pkg_len, "log4j-12-api"));
    CHECK(span_eq(a.ver, a.ver_len, "2.0"));

    /* multiple hyphen segments */
    CHECK(parse_atom_str("=dev-libs/libfoo-bar-baz-1.0", &a));
    CHECK(span_eq(a.pkg, a.pkg_len, "libfoo-bar-baz"));
    CHECK(span_eq(a.ver, a.ver_len, "1.0"));
}

static void test_scan_atom_slot(void)
{
    AtomInfo a;

    CHECK(parse_atom_str("cat/pkg:0", &a));
    CHECK(span_eq(a.slot_raw, a.slot_raw_len, "0"));

    CHECK(parse_atom_str("cat/pkg:0/53", &a));
    CHECK(span_eq(a.slot_raw, a.slot_raw_len, "0/53"));

    CHECK(parse_atom_str("cat/pkg:0=", &a));
    CHECK(span_eq(a.slot_raw, a.slot_raw_len, "0="));

    CHECK(parse_atom_str("cat/pkg:*", &a));
    CHECK(span_eq(a.slot_raw, a.slot_raw_len, "*"));

    CHECK(parse_atom_str("cat/pkg:=", &a));
    CHECK(span_eq(a.slot_raw, a.slot_raw_len, "="));

    /* no slot */
    CHECK(parse_atom_str("cat/pkg", &a));
    CHECK(a.slot_raw == NULL);
}

static void test_scan_atom_use(void)
{
    AtomInfo a;

    CHECK(parse_atom_str("cat/pkg[foo]", &a));
    CHECK(span_eq(a.use_raw, a.use_raw_len, "foo"));

    CHECK(parse_atom_str("cat/pkg[-foo]", &a));
    CHECK(span_eq(a.use_raw, a.use_raw_len, "-foo"));

    CHECK(parse_atom_str("cat/pkg[foo,bar]", &a));
    CHECK(span_eq(a.use_raw, a.use_raw_len, "foo,bar"));

    CHECK(parse_atom_str("cat/pkg[!foo=]", &a));
    CHECK(span_eq(a.use_raw, a.use_raw_len, "!foo="));

    CHECK(parse_atom_str("cat/pkg[foo(+)]", &a));
    CHECK(span_eq(a.use_raw, a.use_raw_len, "foo(+)"));

    /* @ in use flag name (old LINGUAS_en@euro style) */
    CHECK(parse_atom_str("cat/pkg[LINGUAS_en@euro]", &a));
    CHECK(span_eq(a.use_raw, a.use_raw_len, "LINGUAS_en@euro"));
}

static void test_scan_atom_combined(void)
{
    AtomInfo a;

    CHECK(parse_atom_str("=cat/pkg-1.0:2[foo,-bar]", &a));
    CHECK(span_eq(a.op,       a.op_len,       "="));
    CHECK(span_eq(a.cat,      a.cat_len,      "cat"));
    CHECK(span_eq(a.pkg,      a.pkg_len,      "pkg"));
    CHECK(span_eq(a.ver,      a.ver_len,      "1.0"));
    CHECK(span_eq(a.slot_raw, a.slot_raw_len, "2"));
    CHECK(span_eq(a.use_raw,  a.use_raw_len,  "foo,-bar"));
}

static void test_scan_atom_invalid(void)
{
    AtomInfo a;

    CHECK(!parse_atom_str("pkg", &a));            /* missing category */
    CHECK(!parse_atom_str("/pkg", &a));           /* empty category */
    CHECK(!parse_atom_str("cat/", &a));           /* empty package */
    CHECK(!parse_atom_str(".cat/pkg", &a));       /* leading dot in category */
    CHECK(!parse_atom_str("cat/pkg:/slot", &a));  /* invalid slot */
    CHECK(!parse_atom_str(">=cat/pkg", &a));       /* operator without version */
    CHECK(!parse_atom_str("=cat/pkg", &a));        /* operator without version */
    /* use before slot */
    CHECK(!parse_atom_str("cat/pkg[doc]:0", &a));
}

static void test_scan_slot(void)
{
    static const struct {
        const char *input;
        int ok;
        const char *slot;
    } cases[] = {
        { "0",       1, "0"      },
        { "myslot",  1, "myslot" },
        { "0/53",    1, "0/53"   },
        { "0=",      1, "0="     },
        { "0/53=",   1, "0/53="  },
        { "*",       1, "*"      },
        { "=",       1, "="      },
        { "",        0, NULL     },
        { "/slot",   0, NULL     },
        { "-slot",   0, NULL     },
        { "+slot",   0, NULL     },
        /* ":=" and ":*" are the whole slot dep, never a sub-slot. */
        { "0/*",     0, NULL     },
        { "0/=",     0, NULL     },
        { "0/",      0, NULL     },
        { "0/+sub",  0, NULL     },
        /* The '=' operator comes last, so "0=" is all that is consumed here
         * and the caller rejects the atom on the leftover "/53". */
        { "0=/53",   1, "0="     },
    };

    for (int i = 0; i < ARRAY_SIZE(cases); i++) {
        const char *s = cases[i].input;
        DepScanner p = { s, s + strlen(s), NULL };
        int ok = scan_slot(&p);
        if (ok != cases[i].ok) {
            FAIL("scan_slot(%s): got %d, want %d", s, ok, cases[i].ok);
            continue;
        }
        if (ok && cases[i].slot) {
            int slen = (int)(p.cur - s);
            if (!span_eq(s, slen, cases[i].slot)) {
                FAIL("scan_slot(%s): slot=%.*s, want %s", s, slen, s, cases[i].slot);
                continue;
            }
        }
        PASS();
    }
}

static void test_scan_use_flag(void)
{
    static const struct {
        const char *input;
        int ok;
    } cases[] = {
        { "foo",              1 },
        { "-foo",             1 },
        { "!foo=",            1 },
        { "!foo?",            1 },
        { "foo=",             1 },
        { "foo?",             1 },
        { "foo(+)",           1 },
        { "foo(-)",           1 },
        { "foo(+)=",          1 },
        { "!foo(-)=",         1 },
        /* flag names with - */
        { "foo-bar",          1 },
        { "-foo-bar",         1 },
        { "foo-bar?",         1 },
        { "!foo-bar?",        1 },
        { "foo-bar=",         1 },
        /* flag names with + (e.g. c++) */
        { "c++",              1 },
        { "-c++",             1 },
        { "c++?",             1 },
        { "!c++?",            1 },
        /* flag names with @ (old LINGUAS syntax) */
        { "LINGUAS_en@euro",  1 },
        { "-LINGUAS_en@euro", 1 },
        { "LINGUAS_en@euro?", 1 },
        /* invalid */
        { "!foo",             0 },  /* bare ! without ?/= */
        { "-foo=",            0 },  /* -foo with suffix */
        { "",                 0 },
    };

    for (int i = 0; i < ARRAY_SIZE(cases); i++) {
        const char *s = cases[i].input;
        DepScanner p = { s, s + strlen(s), NULL };
        int ok = scan_use_flag(&p);
        /* for valid flags, must also consume all input */
        if (ok && p.cur != p.end) ok = 0;
        if (ok != cases[i].ok) {
            FAIL("scan_use_flag(%s): got %d, want %d", s, ok, cases[i].ok);
        } else {
            PASS();
        }
    }
}

int main(void)
{
    init_cc_table();

    test_scan_version();
    test_scan_atom_basic();
    test_scan_atom_hyphenated_name();
    test_scan_atom_slot();
    test_scan_atom_use();
    test_scan_atom_combined();
    test_scan_atom_invalid();
    test_scan_slot();
    test_scan_use_flag();

    if (failures) {
        fprintf(stderr, "%d/%d tests failed\n", failures, failures + passes);
        return 1;
    }
    printf("%d tests passed\n", passes);
    return 0;
}

/* vim: set ts=4 sw=4 et: */
