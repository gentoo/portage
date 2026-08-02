/* Copyright 2026 Gentoo Authors
 * SPDX-License-Identifier: GPL-2.0-or-later OR MIT
 */

#include "dep_atom.h"
#include "dep_parser_core.h"
#include <assert.h>
#include <string.h>

#define MODULE_NAME "portage.dep._parser"

typedef struct {
    PyObject *useset;   /* frozenset of active USE flags, or NULL */
    int       matchall;
} UseContext;

static inline void py_decref_p(PyObject **p) {
    Py_XDECREF(*p);
}
#define AUTO_PY __attribute__((cleanup(py_decref_p))) PyObject *

static struct {
    /* operator strings */
    PyObject *op_lt, *op_gt, *op_le, *op_ge, *op_eq, *op_tilde;
    /* blocker strings */
    PyObject *blocker_weak, *blocker_strong;   /* "!" weak, "!!" strong */
    /* slot operator strings */
    PyObject *slot_op_eq, *slot_op_star;
} interned;

static int init_globals(void)
{
    init_cc_table();

    if (PyType_Ready(&AtomType) < 0)
        return 0;

#define INTERN(var, s) \
    do { interned.var = PyUnicode_InternFromString(s); if (!interned.var) return 0; } while (0)
    INTERN(op_lt,          "<");
    INTERN(op_gt,          ">");
    INTERN(op_le,          "<=");
    INTERN(op_ge,          ">=");
    INTERN(op_eq,          "=");
    INTERN(op_tilde,       "~");
    INTERN(blocker_weak,   "!");
    INTERN(blocker_strong, "!!");
    INTERN(slot_op_eq,     "=");
    INTERN(slot_op_star,   "*");
#undef INTERN

    return 1;
}

/* Return an interned operator string, avoiding allocation for the common cases. */
static PyObject *op_str(const char *op, int len)
{
    if (len == 1) {
        if (op[0] == '<') return Py_NewRef(interned.op_lt);
        if (op[0] == '>') return Py_NewRef(interned.op_gt);
        if (op[0] == '=') return Py_NewRef(interned.op_eq);
        if (op[0] == '~') return Py_NewRef(interned.op_tilde);
    } else if (len == 2) {
        if (op[0] == '<') return Py_NewRef(interned.op_le);
        if (op[0] == '>') return Py_NewRef(interned.op_ge);
    }
    return PyUnicode_FromStringAndSize(op, len);
}

static PyObject *blocker_str(int len)
{
    assert(len == 1 || len == 2);
    return Py_NewRef(len == 1 ? interned.blocker_weak : interned.blocker_strong);
}

/* Split the raw text between ':' and the end of the slot into the three
 * fields portage.dep.Atom keeps, following PMS 8.3.3:
 *
 *   "0"     -> slot "0",  sub_slot None, op None
 *   "0/53"  -> slot "0",  sub_slot "53", op None
 *   "0="    -> slot "0",  sub_slot None, op "="
 *   "0/53=" -> slot "0",  sub_slot "53", op "="
 *   "="     -> slot None, sub_slot None, op "="
 *   "*"     -> slot None, sub_slot None, op "*"
 *
 * The scanner has already validated the text, so this only has to divide it.
 * Each out parameter is set to a new reference. */
static void parse_slot_raw(const char *raw, int rlen,
                            PyObject **out_slot, PyObject **out_sub,
                            PyObject **out_op)
{
    if (rlen == 1 && (raw[0] == '*' || raw[0] == '=')) {
        *out_slot = Py_NewRef(Py_None);
        *out_sub  = Py_NewRef(Py_None);
        *out_op   = raw[0] == '=' ? Py_NewRef(interned.slot_op_eq) : Py_NewRef(interned.slot_op_star);
        return;
    }

    const char *slash = memchr(raw, '/', rlen);
    char slot_op = 0;

    if (!slash) {
        int slen = rlen;
        if (slen > 0 && raw[slen - 1] == '=') {
            slot_op = '=';
            slen--;
        }
        *out_slot = PyUnicode_FromStringAndSize(raw, slen);
        *out_sub  = Py_NewRef(Py_None);
    } else {
        int main_len = (int)(slash - raw);
        if (main_len > 0 && raw[main_len - 1] == '=') {
            slot_op = '=';
            main_len--;
        }
        *out_slot = PyUnicode_FromStringAndSize(raw, main_len);

        const char *sub = slash + 1;
        int sub_len = rlen - (int)(sub - raw);
        if (sub_len == 1 && (sub[0] == '*' || sub[0] == '=')) {
            *out_sub = Py_NewRef(Py_None);
            slot_op = sub[0];
        } else {
            if (sub_len > 0 && sub[sub_len - 1] == '=') {
                slot_op = '=';
                sub_len--;
            }
            *out_sub = PyUnicode_FromStringAndSize(sub, sub_len);
        }
    }

    if (slot_op == '=') {
        *out_op = Py_NewRef(interned.slot_op_eq);
    } else if (slot_op == '*') {
        *out_op = Py_NewRef(interned.slot_op_star);
    } else {
        *out_op = Py_NewRef(Py_None);
    }
}

/* Split the raw text between '[' and ']' into one string per flag:
 *
 *   "foo,-bar,baz?" -> ("foo", "-bar", "baz?")
 *
 * The prefixes and suffixes are left on; _use_dep (or classify_use_deps)
 * interprets them.  The scanner has already validated the text, so a ',' here
 * can only be a separator. */
static PyObject *parse_use_raw(const char *raw, int rlen)
{
    int count = 1;
    for (int i = 0; i < rlen; i++) {
        if (raw[i] == ',') {
            count++;
        }
    }

    PyObject *tup = PyTuple_New(count);
    if (!tup)
        return NULL;

    int idx = 0, start = 0;
    for (int j = 0; j <= rlen; j++) {
        if (j == rlen || raw[j] == ',') {
            PyObject *flag = PyUnicode_FromStringAndSize(raw + start, j - start);
            if (!flag) {
                Py_DECREF(tup);
                return NULL;
            }

            PyTuple_SET_ITEM(tup, idx++, flag);
            start = j + 1;
        }
    }
    return tup;
}

/* Join the pieces of an atom into one string:
 *
 *   ("dev-libs", "foo", NULL)  -> "dev-libs/foo"
 *   ("dev-libs", "foo", "1.2") -> "dev-libs/foo-1.2"
 *
 * The scanner reports spans into the caller's dep string rather than
 * NUL-terminated pieces, so they have to be copied to be joined.  Category and
 * package names are unbounded, so a stack buffer big enough for every real
 * atom is used where it fits and the heap otherwise; rejecting a long atom
 * here would make the C path refuse a dep string the regex path accepts. */
static PyObject *join_atom_string(const char *cat, int cat_len,
                                  const char *pkg, int pkg_len,
                                  const char *ver, int ver_len)
{
    char  stack_buf[256];
    char *buf = stack_buf;
    int   len = cat_len + 1 + pkg_len + (ver ? 1 + ver_len : 0);

    if (len > (int)sizeof(stack_buf)) {
        buf = PyMem_Malloc(len);
        if (!buf)
            return PyErr_NoMemory();
    }

    char *w = buf;
    memcpy(w, cat, cat_len);
    w += cat_len;
    *w++ = '/';
    memcpy(w, pkg, pkg_len);
    w += pkg_len;
    if (ver) {
        *w++ = '-';
        memcpy(w, ver, ver_len);
    }

    PyObject *result = PyUnicode_FromStringAndSize(buf, len);
    if (buf != stack_buf)
        PyMem_Free(buf);
    return result;
}

static PyObject *build_atom_obj(const AtomInfo *a, const char *tok, int tok_len)
{
    PyObject *py_str = PyUnicode_FromStringAndSize(tok, tok_len);
    if (!py_str)
        return NULL;

    PyObject *py_cp = join_atom_string(a->cat, a->cat_len,
                                       a->pkg, a->pkg_len, NULL, 0);
    if (!py_cp) {
        Py_DECREF(py_str);
        return NULL;
    }

    PyObject *py_ver, *py_cpv;
    if (a->ver) {
        py_ver = PyUnicode_FromStringAndSize(a->ver, a->ver_len);
        py_cpv = py_ver ? join_atom_string(a->cat, a->cat_len, a->pkg,
                                           a->pkg_len, a->ver, a->ver_len)
                        : NULL;
        if (!py_cpv) {
            Py_DECREF(py_str);
            Py_DECREF(py_cp);
            Py_XDECREF(py_ver);
            return NULL;
        }
    } else {
        py_ver = Py_NewRef(Py_None);
        py_cpv = Py_NewRef(py_cp);
    }

    PyObject *py_operator = a->op ?
        op_str(a->op, a->op_len)  : Py_NewRef(Py_None);
    PyObject *py_blocker  = a->block ?
        blocker_str(a->block_len) : Py_NewRef(Py_None);

    PyObject *py_slot, *py_sub, *py_slot_op;
    if (a->slot_raw) {
        parse_slot_raw(a->slot_raw, a->slot_raw_len,
                       &py_slot, &py_sub, &py_slot_op);
    } else {
        py_slot    = Py_NewRef(Py_None);
        py_sub     = Py_NewRef(Py_None);
        py_slot_op = Py_NewRef(Py_None);
    }

    PyObject *py_use = a->use_raw
        ? parse_use_raw(a->use_raw, a->use_raw_len)
        : Py_NewRef(Py_None);

    if (!py_operator || !py_blocker || !py_slot || !py_sub || !py_slot_op || !py_use)
        goto cleanup;

    PyObject *obj = atom_new(py_str, py_cp, py_cpv, py_ver, py_operator, py_blocker,
                             py_slot, py_sub, py_slot_op, py_use);
    if (obj)
        return obj;

cleanup:
    Py_DECREF(py_str);
    Py_DECREF(py_cp);
    Py_DECREF(py_cpv);
    Py_DECREF(py_ver);
    Py_XDECREF(py_operator);
    Py_XDECREF(py_blocker);
    Py_XDECREF(py_slot);
    Py_XDECREF(py_sub);
    Py_XDECREF(py_slot_op);
    Py_XDECREF(py_use);
    return NULL;
}

typedef struct {
    PyObject *list;
    PyObject *op;
} PyGroupFrame;

/* Groups nest only a few levels deep in practice, so the first levels live in
 * the context itself and deeper nesting spills to the heap.  There is no fixed
 * ceiling: the pure-Python path has none either, and rejecting a dep string it
 * accepts would be a divergence between the two. */
#define PY_PARSE_INLINE_DEPTH 32

typedef struct {
    PyGroupFrame  inline_frames[PY_PARSE_INLINE_DEPTH];
    PyGroupFrame *frames;
    int         depth;
    int         capacity;
    PyObject   *useset;
    int         matchall;
} PyParseContext;

static int py_ctx_grow(PyParseContext *ctx)
{
    int new_cap = ctx->capacity * 2;
    PyGroupFrame *frames;

    if (ctx->frames == ctx->inline_frames) {
        frames = PyMem_New(PyGroupFrame, new_cap);
        if (frames)
            memcpy(frames, ctx->inline_frames, sizeof(ctx->inline_frames));
    } else {
        frames = PyMem_Realloc(ctx->frames, new_cap * sizeof(*frames));
    }

    if (!frames) {
        PyErr_NoMemory();
        return 0;
    }

    ctx->frames   = frames;
    ctx->capacity = new_cap;
    return 1;
}

static void py_ctx_free(PyParseContext *ctx)
{
    if (ctx->frames != ctx->inline_frames)
        PyMem_Free(ctx->frames);
}

static int py_on_atom(void *vctx, const char *start, int len, const AtomInfo *info)
{
    PyParseContext *ctx = vctx;
    PyObject *obj = build_atom_obj(info, start, len);
    if (!obj)
        return 0;

    int rc = PyList_Append(ctx->frames[ctx->depth - 1].list, obj);
    Py_DECREF(obj);
    return rc >= 0;
}

static int py_on_group_start(void *vctx, const char *op, int op_len)
{
    PyParseContext *ctx = vctx;
    if (ctx->depth >= ctx->capacity && !py_ctx_grow(ctx))
        return 0;

    PyObject *group_op = PyUnicode_FromStringAndSize(op, op_len);
    if (!group_op)
        return 0;

    PyObject *sublist = PyList_New(0);
    if (!sublist) {
        Py_DECREF(group_op);
        return 0;
    }

    ctx->frames[ctx->depth].op   = group_op;
    ctx->frames[ctx->depth].list = sublist;
    ctx->depth++;
    return 1;
}

static int py_on_group_end(void *vctx)
{
    PyParseContext *ctx      = vctx;
    ctx->depth--;
    PyObject *group_op = ctx->frames[ctx->depth].op;
    PyObject *sublist  = ctx->frames[ctx->depth].list;
    PyObject *parent   = ctx->frames[ctx->depth - 1].list;

    int rc = PyList_Append(parent, group_op);
    Py_DECREF(group_op);
    if (rc < 0) {
        Py_DECREF(sublist);
        return 0;
    }

    rc = PyList_Append(parent, sublist);
    Py_DECREF(sublist);
    return rc >= 0;
}

static int py_use_active(void *vctx, const char *flag, int len, int is_neg)
{
    PyParseContext *ctx = vctx;
    if (ctx->matchall)
        return 1;
    int in_set = 0;
    if (ctx->useset) {
        PyObject *key = PyUnicode_FromStringAndSize(flag, len);
        if (!key)
            return -1;
        in_set = PySet_Contains(ctx->useset, key);
        Py_DECREF(key);
        if (in_set < 0)
            return -1;
    }
    return is_neg ? !in_set : in_set;
}

static int dep_parse(const char *s, Py_ssize_t n, const char **err,
                     PyObject *result, UseContext *use)
{
    DepScanner p = { s, s + n, NULL };

    PyParseContext ctx = {
        .depth    = 1,
        .capacity = PY_PARSE_INLINE_DEPTH,
        .useset   = use->useset,
        .matchall = use->matchall,
    };

    ctx.frames = ctx.inline_frames;
    ctx.frames[0].list = result;
    ctx.frames[0].op   = NULL;
    DepVisitor v = {
        .ctx            = &ctx,
        .on_atom        = py_on_atom,
        .on_group_start = py_on_group_start,
        .on_group_end   = py_on_group_end,
        .use_active     = py_use_active,
    };

    skip_whitespace(&p);

    if (p.cur < p.end && !scan_dep_list(&p, &v)) {
        for (int i = 1; i < ctx.depth; i++) {  /* frame 0's list is caller-owned */
            Py_XDECREF(ctx.frames[i].op);
            Py_XDECREF(ctx.frames[i].list);
        }
        py_ctx_free(&ctx);

        if (PyErr_Occurred())
            return 0;

        if (err)
            *err = p.err ? p.err : "parse error";
        return 0;
    }

    py_ctx_free(&ctx);

    skip_whitespace(&p);

    if (p.cur < p.end) {
        if (err)
            *err = "unexpected token";
        return 0;
    }
    return 1;
}

/*
 * classify_use_deps(tokens) -> tuple or None
 *
 * Classify a sequence of use-dep token strings (already split at ',') into
 * the sets that _use_dep.__init__ would produce, bypassing its per-token
 * regex.  Returns a 6-tuple:
 *   (enabled_fs, disabled_fs, missing_enabled_fs, missing_disabled_fs,
 *    conditional_dict_or_None, required_fs)
 * where the frozensets and dict match exactly what _use_dep expects in its
 * shortcut constructor path (enabled_flags is not None).
 * Raises ValueError if any token cannot be classified.
 */
static PyObject *
py_classify_use_deps(UNUSED PyObject *self, PyObject *arg)
{
    AUTO_PY seq  = PySequence_Fast(arg, "expected sequence");
    if (!seq)
        return NULL;

    Py_ssize_t ntok = PySequence_Fast_GET_SIZE(seq);

    AUTO_PY en   = PySet_New(NULL);
    AUTO_PY dis  = PySet_New(NULL);
    AUTO_PY me   = PySet_New(NULL);
    AUTO_PY md   = PySet_New(NULL);
    AUTO_PY req  = PySet_New(NULL);
    AUTO_PY cen  = NULL;
    AUTO_PY cdis = NULL;
    AUTO_PY ceq  = NULL;
    AUTO_PY cneq = NULL;
    if (!en || !dis || !me || !md || !req)
        return NULL;

#define SET_ADD(set, f)  do { if (PySet_Add((set), (f)) < 0) return NULL; } while (0)
#define SET_LAZY(ptr)    do { if (!(ptr) && !((ptr) = PySet_New(NULL))) return NULL; } while (0)

    for (Py_ssize_t i = 0; i < ntok; i++) {
        PyObject *tok = PySequence_Fast_GET_ITEM(seq, i);  /* borrowed */
        Py_ssize_t slen;

        const char *s = PyUnicode_AsUTF8AndSize(tok, &slen);
        if (!s)
            return NULL;

        const char *p = s, *end = s + slen;

        int is_neg = 0, is_dis_pfx = 0;
        if (p < end && *p == '!') {
            is_neg = 1;
            p++;
        } else if (p < end && *p == '-') {
            is_dis_pfx = 1;
            p++;
        }

        if (p >= end || !is_nw_char(*p)) {
            PyErr_Format(PyExc_ValueError, "invalid use dep token: %R", tok);
            return NULL;
        }

        const char *flag_start = p++;
        while (p < end && is_use_char(*p)) {
            p++;
        }
        const char *flag_end = p;

        /* optional default: (+) or (-) */
        int def = 0;  /* 0=none, +1=(+), -1=(-) */
        if (p + 3 <= end && p[0] == '(' && p[2] == ')') {
            if (p[1] == '+') {
                def = 1;
                p += 3;
            } else if (p[1] == '-') {
                def = -1;
                p += 3;
            }
        }

        /* optional suffix */
        char suf = 0;
        if (p < end && (*p == '?' || *p == '=')) {
            suf = *p++;
        }

        if (p != end || (is_neg && !suf) || (is_dis_pfx && suf)) {
            PyErr_Format(PyExc_ValueError, "invalid use dep token: %R", tok);
            return NULL;
        }

        AUTO_PY flag = PyUnicode_FromStringAndSize(flag_start, flag_end - flag_start);
        if (!flag)
            return NULL;

        /* classify into enabled/disabled/conditional */
        if (!is_neg && !is_dis_pfx && !suf) {
            SET_ADD(en, flag);
        } else if (is_dis_pfx) {
            SET_ADD(dis, flag);
        } else if (!is_neg && suf == '?') {
            SET_LAZY(cen);  SET_ADD(cen, flag);
        } else if (!is_neg && suf == '=') {
            SET_LAZY(ceq);  SET_ADD(ceq, flag);
        } else if (is_neg && suf == '?') {
            SET_LAZY(cdis); SET_ADD(cdis, flag);
        } else {  /* is_neg && suf == '=' */
            SET_LAZY(cneq); SET_ADD(cneq, flag);
        }

        /* required = flags without a default */
        if (!def)         SET_ADD(req, flag);
        if (def > 0)      SET_ADD(me,  flag);
        else if (def < 0) SET_ADD(md,  flag);
    }

#undef SET_ADD
#undef SET_LAZY

    AUTO_PY cond = NULL;
    if (cen || cdis || ceq || cneq) {
        cond = PyDict_New();
        if (!cond)
            return NULL;

#define COND_SET(key, obj) \
        if (obj) { \
            AUTO_PY fs = PyFrozenSet_New(obj); \
            if (!fs || PyDict_SetItemString(cond, key, fs) < 0) return NULL; \
        }
        COND_SET("enabled",   cen)
        COND_SET("disabled",  cdis)
        COND_SET("equal",     ceq)
        COND_SET("not_equal", cneq)
#undef COND_SET
    } else {
        cond = Py_NewRef(Py_None);
    }

    AUTO_PY fen  = PyFrozenSet_New(en);
    AUTO_PY fdis = PyFrozenSet_New(dis);
    AUTO_PY fme  = PyFrozenSet_New(me);
    AUTO_PY fmd  = PyFrozenSet_New(md);
    AUTO_PY freq = PyFrozenSet_New(req);
    if (!fen || !fdis || !fme || !fmd || !freq)
        return NULL;

    return PyTuple_Pack(6, fen, fdis, fme, fmd, cond, freq);
}

static PyObject *
py_parse(UNUSED PyObject *self, PyObject *args, PyObject *kwargs)
{
    static const char * const kwlist[] = {"s", "uselist", "matchall", NULL};
    PyObject *py_str;
    PyObject *py_uselist = Py_None;
    int matchall = 0;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|Op", (char **)kwlist,
                                      &py_str, &py_uselist, &matchall))
        return NULL;

    const char *s;
    Py_ssize_t n;
    s = PyUnicode_AsUTF8AndSize(py_str, &n);
    if (!s)
        return NULL;

    AUTO_PY useset = NULL;
    if (py_uselist != Py_None) {
        useset = PyFrozenSet_New(py_uselist);
        if (!useset) {
            return NULL;
        }
    }

    UseContext use = { useset, matchall };
    AUTO_PY result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    const char *err = NULL;
    if (!dep_parse(s, n, &err, result, &use)) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_ValueError, err ? err : "parse error");
        }
        return NULL;
    }
    return Py_NewRef(result);
}

static PyMethodDef methods[] = {
    {
        .ml_name  = "parse",
        .ml_meth  = (PyCFunction)py_parse,
        .ml_flags = METH_VARARGS | METH_KEYWORDS,
        .ml_doc   =
            "parse(s, uselist=None, matchall=False) -> list\n"
            "Parse a Gentoo dep spec. Returns a list of Atom objects, where\n"
            "|| / ^^ / ?? groups appear as the operator string followed by a\n"
            "sublist and a plain all-of group appears as a bare sublist.\n"
            "Use conditionals are evaluated: an active one contributes a\n"
            "sublist, an inactive one contributes nothing.",
    },
    {
        .ml_name  = "classify_use_deps",
        .ml_meth  = py_classify_use_deps,
        .ml_flags = METH_O,
        .ml_doc   =
            "classify_use_deps(tokens) -> tuple\n"
            "Classify pre-split use-dep tokens into (enabled_fs, disabled_fs,\n"
            "missing_enabled_fs, missing_disabled_fs, conditional_dict_or_None,\n"
            "required_fs). Raises ValueError if a token cannot be classified.",
    },
    { NULL, NULL, 0, NULL },
};

static struct PyModuleDef module = {
    .m_base    = PyModuleDef_HEAD_INIT,
    .m_name    = MODULE_NAME,
    .m_doc     = NULL,
    .m_size    = -1,
    .m_methods = methods,
};

PyMODINIT_FUNC
PyInit__parser(void)
{
    if (!init_globals())
        return NULL;

    PyObject *m = PyModule_Create(&module);
    if (!m)
        return NULL;

    if (atom_add_to_module(m) < 0) {
        Py_DECREF(m);
        return NULL;
    }

#ifdef Py_GIL_DISABLED
    /* Safe to run without the GIL: the character-class table and the interned
     * strings are written once here and only read afterwards, the scanner
     * keeps all of its state on the stack or in a per-call context, and Atom
     * is an ordinary refcounted object with no mutable fields. */
    if (PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED) < 0) {
        Py_DECREF(m);
        return NULL;
    }
#endif

    return m;
}

/* vim: set ts=4 sw=4 et: */
