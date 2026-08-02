/* Copyright 2026 Gentoo Authors
 * SPDX-License-Identifier: GPL-2.0-or-later OR MIT
 */

#include <string.h>
#include "dep_parser_core.h"

uint8_t CC[256];

void init_cc_table(void)
{
    for (int c = 0; c < ARRAY_SIZE(CC); c++) {
        unsigned char uc = (unsigned char)c;
        uint8_t v = 0;

        /* digits */
        if (uc >= '0' && uc <= '9') {
            v |= CC_DIGIT | CC_NW | CC_CAT | CC_USE;
        }

        /* letters */
        if ((uc >= 'a' && uc <= 'z') || (uc >= 'A' && uc <= 'Z')) {
            v |= CC_ALPHA | CC_NW | CC_CAT | CC_USE;

            if (uc >= 'a' && uc <= 'z') {
                v |= CC_LOWER;
            }
        }
        /* extra name-word chars */
        if (uc == '+' || uc == '_') v |= CC_NW | CC_CAT | CC_USE;
        if (uc == '.') v |= CC_CAT;
        if (uc == '-') v |= CC_CAT | CC_USE;
        if (uc == '@') v |= CC_USE;
        CC[c] = v;
    }
}

void skip_whitespace(DepScanner *p)
{
    while (p->cur < p->end && is_whitespace(*p->cur)) {
        p->cur++;
    }
}

/* PMS 3.2: a version is digits, optionally dot-separated, an optional single
 * letter, zero or more _alpha/_beta/_pre/_rc/_p suffixes with optional
 * numbers, and an optional -rN revision.  A trailing '*' is accepted here and
 * rejected later unless the operator is '='.
 *
 *   "1.2.3"        -> consumed
 *   "1.0_alpha1"   -> consumed
 *   "1.0-r1"       -> consumed
 *   "1.2*"         -> consumed
 *   "1.0 rest"     -> consumes "1.0", stops at the space
 *   "alpha"        -> rejected, must start with a digit
 *
 * Advances cur past the version and returns 1, or leaves cur alone and
 * returns 0.  A version must end at whitespace, ':', '[' or ')'. */
int scan_version(DepScanner *p)
{
    static const struct {
        const char *str;
        int len;
    } sfx[] = {
#define SFX(s) { s, (int)(sizeof(s) - 1) }
        SFX("_alpha"), SFX("_beta"), SFX("_pre"), SFX("_rc"), SFX("_p"),
#undef SFX
    };

    const char *s = p->cur;

    if (s >= p->end || !is_digit_c(*s))
        return 0;

    while (s < p->end && is_digit_c(*s)) {
        s++;
    }

    while (s < p->end && *s == '.') {
        s++;
        if (s >= p->end || !is_digit_c(*s))
            return 0;

        while (s < p->end && is_digit_c(*s)) {
            s++;
        }
    }

    if (s < p->end && is_lower_c(*s))
        s++;

    for (;;) {
        int hit = 0;
        for (int i = 0; i < ARRAY_SIZE(sfx); i++) {
            int l = sfx[i].len;
            if (s + l <= p->end && memcmp(s, sfx[i].str, l) == 0 &&
                (s + l >= p->end || !is_alpha_c(s[l]))) {
                s += l;
                while (s < p->end && is_digit_c(*s)) {
                    s++;
                }
                hit = 1;
                break;
            }
        }
        if (!hit) {
            break;
        }
    }

    if (s + 2 < p->end && s[0] == '-' && s[1] == 'r' &&
        is_digit_c(s[2])) {
        s += 2;
        while (s < p->end && is_digit_c(*s)) {
            s++;
        }
    }

    if (s < p->end && *s == '*') {
        s++;  /* glob: =cat/pkg-1.2* */
    }

    if (s >= p->end || is_whitespace(*s) || *s == ':' || *s == '[' || *s == ')') {
        p->cur = s;
        return 1;
    }
    return 0;
}

/* The examples below spell out a "0/" slot followed by '*', which the
 * compiler sees as a comment opener. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wcomment"
/* PMS 8.3.3: the text after ':' -- a slot, an optional /sub-slot, and an
 * optional '=' operator, or a bare ':=' / ':*'.
 *
 *   "0"     "myslot"   "0/53"   "0="   "0/53="   "="   "*"   -> consumed
 *   "/slot"  "-slot"                                        -> rejected
 *
 * Slot names share the category character set, except that the first
 * character may not be '+'. */
#pragma GCC diagnostic pop
int scan_slot(DepScanner *p)
{
    const char *s = p->cur;
    if (s >= p->end)
        return 0;

    if (*s == '*' || *s == '=') {
        p->cur = s + 1;
        return 1;
    }

    if (!is_nw_char(*s))
        return 0;

    s++;
    while (s < p->end && is_slot_char(*s)) {
        s++;
    }
    if (s < p->end && *s == '=') {
        s++;
    }

    if (s < p->end && *s == '/') {
        s++;
        if (s < p->end && (*s == '*' || *s == '=')) {
            s++;
        } else if (s < p->end && is_nw_char(*s)) {
            s++;
            while (s < p->end && is_slot_char(*s)) {
                s++;
            }
            if (s < p->end && *s == '=') {
                s++;
            }
        } else {
            return 0;
        }
    }

    p->cur = s;
    return 1;
}

/* PMS 8.3.4: one use dep, with its optional prefix, (+)/(-) default and
 * suffix.  Flag names may contain '-', '+' and '@' (c++, LINGUAS_en@euro), so
 * the name body is scanned with is_use_char rather than the name-word set.
 *
 *   "foo"  "-foo"  "foo?"  "foo="  "foo(+)"  "!foo?"  "!foo(-)="  -> consumed
 *   "!foo"   -> rejected, '!' requires a '?' or '=' suffix
 *   "-foo="  -> rejected, '-' and a suffix are mutually exclusive
 *
 * Advances cur past the flag and returns 1, or returns 0. */
int scan_use_flag(DepScanner *p)
{
    const char *s = p->cur;
    if (s >= p->end)
        return 0;

    int is_neg = 0, is_dis = 0;
    if (*s == '!') {
        is_neg = 1;
        s++;
    } else if (*s == '-') {
        is_dis = 1;
        s++;
    }

    if (s >= p->end || !is_nw_char(*s))
        return 0;

    s++;
    while (s < p->end && is_use_char(*s)) {
        s++;
    }

    if (s + 2 < p->end && *s == '(' && (s[1] == '+' || s[1] == '-') && s[2] == ')')
        s += 3;

    if (is_neg) {
        if (s < p->end && (*s == '?' || *s == '=')) {
            s++;
        } else {
            return 0;
        }
    } else if (!is_dis) {
        if (s < p->end && (*s == '?' || *s == '=' || *s == '-')) {
            s++;
        }
    }

    p->cur = s;
    return 1;
}

int scan_usedep(DepScanner *p)
{
    for (;;) {
        if (!scan_use_flag(p))
            return 0;

        if (p->cur < p->end && *p->cur == ',') {
            p->cur++;
        } else {
            break;
        }
    }
    return 1;
}

/* One whole atom: [blocker][operator]category/package[-version][:slot][use].
 *
 *   "dev-libs/foo"                  -> cat "dev-libs", pkg "foo"
 *   ">=dev-libs/foo-1.2:0=[a,-b]"   -> op ">=", ver "1.2", slot ":0=", use "a,-b"
 *   "!!dev-libs/foo"                -> block "!!"
 *
 * Package names may contain hyphens, so the boundary between name and version
 * is ambiguous ("log4j-12-api-2.0") and is resolved by trying to scan a
 * version after each '-'.  On success the spans in *info point into the
 * caller's string; on failure cur is restored and 0 is returned, which lets
 * the caller try a different production. */
int scan_atom(DepScanner *p, AtomInfo *info)
{
    const char *start = p->cur;
    const char *s = start;

    /* block */
    SPAN(block, NULL);
    if (s < p->end && *s == '!') {
        block = s; s++;
        if (s < p->end && *s == '!') {
            s++;
        }
        block_len = (int)(s - block);
    }

    /* operator */
    SPAN(op, NULL);
    if (s < p->end) {
        if ((s[0] == '<' || s[0] == '>') && s + 1 < p->end && s[1] == '=') {
            op = s;
            op_len = 2;
            s += 2;
        } else if (s[0] == '<' || s[0] == '>' || s[0] == '=' || s[0] == '~') {
            op = s;
            op_len = 1;
            s++;
        }
    }

    /* category */
    const char *cat = s;
    if (s >= p->end || !is_nw_char(*s))
        goto fail;

    s++;
    while (s < p->end && is_cat_char(*s)) {
        s++;
    }
    int cat_len = (int)(s - cat);

    if (s >= p->end || *s != '/')
        goto fail;
    s++;

    /* first name-word */
    const char *pkg = s;
    if (s >= p->end)
        goto fail;

    if (is_alpha_c(*s) || *s == '_') {
        s++;
        while (s < p->end && is_nw_char(*s)) {
            s++;
        }
    } else if (is_digit_c(*s)) {
        while (s < p->end && is_digit_c(*s)) {
            s++;
        }

        if (s >= p->end || (!is_alpha_c(*s) && *s != '_'))
            goto fail;

        s++;
        while (s < p->end && is_nw_char(*s)) {
            s++;
        }
    } else {
        goto fail;
    }

    {
        int pkg_len = 0;
        SPAN(ver, NULL);

        const char *pkg_end = s;

        /* additional '-' segments: name-word or version */
        for (;;) {
            if (s >= p->end || *s != '-' || s + 1 >= p->end)
                break;

            char nxt = s[1];
            if (is_digit_c(nxt)) {
                DepScanner tmp = { s + 1, p->end, NULL };
                if (scan_version(&tmp)) {
                    ver = s + 1;
                    ver_len = (int)(tmp.cur - ver);
                    pkg_end = s;
                    s = tmp.cur;
                    goto after_pkgver;
                }

                const char *t = s + 1;
                while (t < p->end && is_digit_c(*t)) {
                    t++;
                }

                if (t < p->end && (is_alpha_c(*t) || *t == '_')) {
                    t++;
                    while (t < p->end && is_nw_char(*t)) {
                        t++;
                    }
                    s = t;
                } else if (t < p->end && *t == '-') {
                    s = t;
                } else {
                    break;
                }
            } else if (is_alpha_c(nxt) || nxt == '_') {
                s += 2;
                while (s < p->end && is_nw_char(*s)) {
                    s++;
                }
            } else {
                break;
            }
        }
        pkg_end = s;

after_pkgver:
        pkg_len = (int)(pkg_end - pkg);
        p->cur = s;

        /* optional ':' slot */
        SPAN(slot_raw, NULL);
        if (p->cur < p->end && *p->cur == ':') {
            p->cur++;
            slot_raw = p->cur;
            if (!scan_slot(p))
                goto fail;
            slot_raw_len = (int)(p->cur - slot_raw);
        }

        /* optional '[' usedep ']' */
        SPAN(use_raw, NULL);
        if (p->cur < p->end && *p->cur == '[') {
            p->cur++;
            use_raw = p->cur;

            if (!scan_usedep(p))
                goto fail;

            use_raw_len = (int)(p->cur - use_raw);

            if (p->cur >= p->end || *p->cur != ']')
                goto fail;

            p->cur++;
        }

        if (op && !ver)
            goto fail;

        if (info) {
            SPAN_SET(info, block);
            SPAN_SET(info, op);
            SPAN_SET(info, cat);
            SPAN_SET(info, pkg);
            SPAN_SET(info, ver);
            SPAN_SET(info, slot_raw);
            SPAN_SET(info, use_raw);
        }
        return 1;
    }

fail:
    p->cur = start;
    return 0;
}

static int scan_item(DepScanner *p, DepVisitor *v);

/* Read items until ')' (stopping before it). */
static int scan_group_contents(DepScanner *p, DepVisitor *v);

/* Skipping the body of an inactive USE-conditional group still has to
 * validate its contents -- "x? ( bogus )" is a malformed dep string whether or
 * not x is set -- so the body is scanned with the real grammar and this
 * visitor, which builds nothing and reports every nested conditional inactive
 * so its body is skipped in turn.  The alternative, a second copy of the
 * grammar that only skips, is one more thing to keep in sync. */
static int skip_on_atom(UNUSED void *ctx, UNUSED const char *start,
                        UNUSED int len, UNUSED const AtomInfo *info)
{
    return 1;
}

static int skip_on_group_start(UNUSED void *ctx, UNUSED const char *op,
                               UNUSED int op_len)
{
    return 1;
}

static int skip_on_group_end(UNUSED void *ctx)
{
    return 1;
}

static int skip_use_active(UNUSED void *ctx, UNUSED const char *flag,
                           UNUSED int len, UNUSED int is_neg)
{
    return 0;
}

static DepVisitor skip_visitor = {
    .ctx            = NULL,
    .on_atom        = skip_on_atom,
    .on_group_start = skip_on_group_start,
    .on_group_end   = skip_on_group_end,
    .use_active     = skip_use_active,
};

static int scan_group_contents(DepScanner *p, DepVisitor *v)
{
    for (;;) {
        if (!scan_item(p, v))
            return 0;

        if (p->cur >= p->end || !is_whitespace(*p->cur)) {
            p->err = "expected whitespace after item in group";
            return 0;
        }
        skip_whitespace(p);

        if (p->cur < p->end && *p->cur == ')')
            return 1;

        if (p->cur >= p->end) {
            p->err = "unexpected end inside group";
            return 0;
        }
    }
}

/* One element of a dep list: an atom, a plain "( ... )" group, an operator
 * group "|| ( ... )", or a use conditional "flag? ( ... )".
 *
 *   "dev-libs/a"          -> on_atom
 *   "( a b )"             -> on_group_start(""), items, on_group_end
 *   "|| ( a b )"          -> on_group_start("||"), items, on_group_end
 *   "foo? ( a )", active  -> on_group_start(""), items, on_group_end
 *   "foo? ( a )", not     -> nothing reported; body still validated
 *
 * A conditional group is reported as a plain group rather than inlined so
 * that a conjunction inside an any-of keeps its nesting. */
static int scan_item(DepScanner *p, DepVisitor *v)
{
    const char *save      = p->cur;
    const char *tok_start = p->cur;
    AtomInfo    info;

    if (scan_atom(p, &info))
        return v->on_atom(v->ctx, tok_start, (int)(p->cur - tok_start), &info);
    p->cur = save;

    const char *s = p->cur;

    /* Plain "( items )": reported as a group with an empty operator rather
     * than inlined, so a conjunction inside an any-of keeps its nesting. */
    if (s < p->end && *s == '(') {
        p->cur = s + 1;
        if (p->cur >= p->end || !is_whitespace(*p->cur)) {
            p->err = "expected whitespace after '('";
            return 0;
        }
        skip_whitespace(p);

        if (!v->on_group_start(v->ctx, "", 0))
            return 0;

        if (!scan_group_contents(p, v))
            return 0;

        p->cur++;  /* consume ')' */
        return v->on_group_end(v->ctx);
    }

    int         is_group_op = 0;
    int         is_neg      = 0;
    SPAN(flag, NULL);
    const char *op          = NULL;
    int         op_len      = 0;

    if (s + 2 <= p->end &&
        (s[0] == s[1] && (s[0] == '|' || s[0] == '^' || s[0] == '?'))) {
        op          = s;
        op_len      = 2;
        is_group_op = 1;
        p->cur        = s + 2;
    } else {
        if (s < p->end && *s == '!') {
            is_neg = 1;
            s++;
        }
        if (s < p->end && is_nw_char(*s)) {
            flag = s++;
            while (s < p->end && is_use_char(*s)) {
                s++;
            }
            flag_len = (int)(s - flag);

            if (s < p->end && *s == '?') {
                p->cur = s + 1;
            } else {
                p->err = "expected '?'";
                return 0;
            }
        } else {
            p->err = "expected atom or group";
            return 0;
        }
    }

    if (p->cur >= p->end || !is_whitespace(*p->cur)) {
        p->err = "expected whitespace after prefix";
        return 0;
    }
    skip_whitespace(p);

    if (p->cur >= p->end || *p->cur != '(') {
        p->err = "expected '('";
        return 0;
    }
    p->cur++;

    if (p->cur >= p->end || !is_whitespace(*p->cur)) {
        p->err = "expected whitespace after '('";
        return 0;
    }
    skip_whitespace(p);

    if (is_group_op) {
        if (!v->on_group_start(v->ctx, op, op_len))
            return 0;

        if (!scan_group_contents(p, v))
            return 0;

        p->cur++;  /* consume ')' */
        return v->on_group_end(v->ctx);
    } else {
        int active = v->use_active(v->ctx, flag, flag_len, is_neg);
        if (active < 0)
            return 0;

        if (active) {
            /* active conditional: emit as naked all-of to preserve nesting */
            if (!v->on_group_start(v->ctx, "", 0))
                return 0;
            if (!scan_group_contents(p, v))
                return 0;
            p->cur++;  /* consume ')' */
            return v->on_group_end(v->ctx);
        } else {
            if (!scan_group_contents(p, &skip_visitor)) {
                return 0;
            }
            p->cur++;  /* consume ')' */
            return 1;
        }
    }
}

int scan_dep_list(DepScanner *p, DepVisitor *v)
{
    if (!scan_item(p, v))
        return 0;

    while (p->cur < p->end && is_whitespace(*p->cur)) {
        skip_whitespace(p);

        if (p->cur >= p->end)
            return 1;

        if (!scan_item(p, v))
            return 0;
    }
    return 1;
}

/* vim: set ts=4 sw=4 et: */
