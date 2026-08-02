/* Copyright 2026 Gentoo Authors
 * SPDX-License-Identifier: GPL-2.0-or-later OR MIT
 */

#pragma once
#include <stdint.h>

/* Cursor over the dep string being scanned.  Every scan_* function advances
 * cur on success and leaves it untouched on failure, so a caller can try one
 * production and fall back to another. */
typedef struct {
    const char *cur;   /* next unconsumed character */
    const char *end;   /* one past the last character */
    const char *err;   /* static message describing the first failure */
} DepScanner;

typedef enum {
    CC_CAT   = 1 << 0,  /* category / slot:  alnum + _ + . - */
    CC_NW    = 1 << 1,  /* name-word:        alnum + _        */
    CC_USE   = 1 << 2,  /* use dep:          alnum + _ @ - +  */
    CC_DIGIT = 1 << 3,
    CC_LOWER = 1 << 4,
    CC_ALPHA = 1 << 5,  /* any letter */
} CC_flag;

extern uint8_t CC[256];  /* filled by init_cc_table() */

#define is_cat_char(c)  (CC[(unsigned char)(c)] & CC_CAT)
#define is_nw_char(c)   (CC[(unsigned char)(c)] & CC_NW)
/* PMS gives slot names and category names the same character set, so this is
 * deliberately an alias; it is spelled out for readability at the use sites. */
#define is_slot_char(c) is_cat_char(c)
#define is_use_char(c)  (CC[(unsigned char)(c)] & CC_USE)
#define is_digit_c(c)   (CC[(unsigned char)(c)] & CC_DIGIT)
#define is_lower_c(c)   (CC[(unsigned char)(c)] & CC_LOWER)
#define is_alpha_c(c)   (CC[(unsigned char)(c)] & CC_ALPHA)

#define ARRAY_SIZE(a) ((int)(sizeof(a) / sizeof((a)[0])))

/* For parameters a function must declare to match a signature but never
 * reads, so that -Wunused-parameter stays usable. */
#define UNUSED __attribute__((unused))

/* Declare a pointer+length pair.  With an initializer: SPAN(name, NULL). */
#define SPAN(name, ...)  const char *name __VA_OPT__(= __VA_ARGS__); int name##_len __VA_OPT__(= 0)
/* Copy locals `name` / `name_len` into the matching SPAN fields of *s. */
#define SPAN_SET(s, name)  do { (s)->name = name; (s)->name##_len = name##_len; } while (0)

static inline int is_whitespace(char c)
{
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

typedef struct {
    SPAN(block);
    SPAN(op);
    SPAN(cat);
    SPAN(pkg);
    SPAN(ver);       /* NULL if absent */
    SPAN(slot_raw);  /* NULL if absent */
    SPAN(use_raw);   /* NULL if absent */
} AtomInfo;

void init_cc_table(void);
void skip_whitespace(DepScanner *p);
int  scan_version(DepScanner *p);
int  scan_slot(DepScanner *p);
int  scan_use_flag(DepScanner *p);
int  scan_usedep(DepScanner *p);
int  scan_atom(DepScanner *p, AtomInfo *info);

typedef struct {
    void *ctx;
    /* Called for each atom token. Returns 1 on success, 0 on error. */
    int (*on_atom)(void *ctx, const char *start, int len, const AtomInfo *info);
    /* Called before/after || ^^ ?? group contents. */
    int (*on_group_start)(void *ctx, const char *op, int op_len);
    int (*on_group_end)(void *ctx);
    /* Returns 1 if the use flag is active, 0 if not, -1 on error. */
    int (*use_active)(void *ctx, const char *flag, int len, int is_neg);
} DepVisitor;

int scan_dep_list(DepScanner *p, DepVisitor *v);

/* vim: set ts=4 sw=4 et: */
