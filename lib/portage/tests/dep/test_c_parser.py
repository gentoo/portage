# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import contextlib
import operator
import os
import subprocess
import sys
from pathlib import Path

try:
    import _testcapi
except ImportError:
    _testcapi = None
else:
    # PyPy ships a _testcapi module, but not the allocator hooks that the
    # allocation-failure sweep needs.
    if not all(hasattr(_testcapi, x) for x in ("set_nomemory", "remove_mem_hooks")):
        _testcapi = None

import portage
import portage.dep as _dep_mod
from portage.dep import Atom, _get_eapi_attrs, _use_dep, use_reduce
from portage.exception import InvalidDependString
from portage.tests import TestCase

_orig_c_dep_parser = _dep_mod._c_dep_parser


@contextlib.contextmanager
def _use_c_parser(enabled):
    """Select the parser used by portage.dep for the duration of the block.

    portage.dep._c_dep_parser is module state, so a test may not leave it
    toggled and two tests may not toggle it concurrently in one interpreter.
    Every toggle in this file goes through here, and always around a single
    call, so a failing assertion cannot leak the setting into the next test.
    pytest-xdist distributes over processes rather than threads, so each
    worker has its own copy of the module and cannot race with another."""
    _dep_mod._c_dep_parser = _orig_c_dep_parser if enabled else None
    try:
        yield
    finally:
        _dep_mod._c_dep_parser = _orig_c_dep_parser


def _c_parser():
    try:
        from portage.dep import _parser

        return _parser
    except ImportError:
        return None


def _atoms_equal(a, b):
    for f in (
        "_string",
        "_cp",
        "_cpv",
        "_version",
        "_operator",
        "_slot",
        "_sub_slot",
        "_slot_operator",
        "_eapi",
        "_extended_syntax",
        "_build_id",
    ):
        av, bv = getattr(a, f), getattr(b, f)
        if av != bv:
            return False, f"{f}: {av!r} != {bv!r}"

    ab, bb = a._blocker_obj, b._blocker_obj
    if bool(ab) != bool(bb):
        return False, f"_blocker_obj presence: {ab!r} != {bb!r}"
    if ab and bb and ab.overlap.forbid != bb.overlap.forbid:
        return False, "_blocker_obj.overlap.forbid mismatch"

    au, bu = a._use, b._use
    if (au is None) != (bu is None):
        return False, f"_use presence: {au!r} != {bu!r}"
    if au is not None and bu is not None:
        for attr in (
            "tokens",
            "enabled",
            "disabled",
            "required",
            "missing_enabled",
            "missing_disabled",
        ):
            av2, bv2 = getattr(au, attr), getattr(bu, attr)
            if av2 != bv2:
                return False, f"_use.{attr}: {av2!r} != {bv2!r}"
        ac, bc = au.conditional, bu.conditional
        if (ac is None) != (bc is None):
            return False, f"_use.conditional presence: {ac!r} != {bc!r}"
        if ac is not None and bc is not None:
            for k in ("enabled", "disabled", "equal", "not_equal"):
                av2, bv2 = getattr(ac, k), getattr(bc, k)
                if av2 != bv2:
                    return False, f"_use.conditional.{k}: {av2!r} != {bv2!r}"
    return True, ""


def _result_equal(c_result, py_result):
    if len(c_result) != len(py_result):
        return False, f"length {len(c_result)} != {len(py_result)}"
    for i, (ci, pi) in enumerate(zip(c_result, py_result)):
        if isinstance(ci, list) and isinstance(pi, list):
            ok, msg = _result_equal(ci, pi)
            if not ok:
                return False, f"[{i}]: {msg}"
        elif isinstance(ci, str) and isinstance(pi, str):
            if ci != pi:
                return False, f"[{i}]: {ci!r} != {pi!r}"
        elif isinstance(ci, Atom) and isinstance(pi, Atom):
            ok, msg = _atoms_equal(ci, pi)
            if not ok:
                return False, f"[{i}] Atom mismatch: {msg}"
        else:
            return False, f"[{i}]: type mismatch {type(ci)} vs {type(pi)}"
    return True, ""


class _UseReduceTests:
    """Mixin run with USE_C_PARSER True or False; subclasses set it."""

    USE_C_PARSER = False

    def setUp(self):
        _dep_mod._c_dep_parser = _orig_c_dep_parser if self.USE_C_PARSER else None

    def tearDown(self):
        _dep_mod._c_dep_parser = _orig_c_dep_parser

    def _reduce(self, depstr, uselist=None, matchall=False, eapi="8", **kw):
        return use_reduce(
            depstr,
            uselist=uselist or [],
            matchall=matchall,
            token_class=Atom,
            eapi=eapi,
            **kw,
        )

    def _atom(self, depstr, **kw):
        result = self._reduce(depstr, **kw)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Atom)
        return result[0]

    def test_unversioned_atom_fields(self):
        a = self._atom("dev-libs/foo", matchall=True)
        self.assertEqual(a._cp, "dev-libs/foo")
        self.assertEqual(a._cpv, "dev-libs/foo")
        self.assertIsNone(a._version)
        self.assertIsNone(a._operator)
        self.assertIsNone(a._slot)
        self.assertIsNone(a._sub_slot)
        self.assertIsNone(a._slot_operator)
        self.assertIsNone(a._use)
        self.assertIsNone(a._blocker_obj)

    def test_versioned_atom_fields(self):
        a = self._atom("=dev-libs/foo-1.2.3-r1", matchall=True)
        self.assertEqual(a._cp, "dev-libs/foo")
        self.assertEqual(a._version, "1.2.3-r1")
        self.assertEqual(a._operator, "=")
        self.assertEqual(a._cpv, "dev-libs/foo-1.2.3-r1")

    def test_all_operators(self):
        for op in ("=", ">=", ">", "<=", "<", "~"):
            with self.subTest(op=op):
                a = self._atom(f"{op}cat/pkg-1.0", matchall=True)
                self.assertEqual(a._operator, op)
                self.assertEqual(a._version, "1.0")

    def test_version_suffixes(self):
        for ver in ("1.0_alpha1", "1.0_beta2", "1.0_pre1", "1.0_rc1", "1.0_p1"):
            with self.subTest(ver=ver):
                a = self._atom(f"=cat/pkg-{ver}", matchall=True)
                self.assertEqual(a._version, ver)

    def test_slot_fields(self):
        a = self._atom("dev-libs/foo:1", matchall=True)
        self.assertEqual(a._slot, "1")
        self.assertIsNone(a._sub_slot)
        self.assertIsNone(a._slot_operator)

    def test_sub_slot_fields(self):
        a = self._atom("dev-libs/foo:0/53", matchall=True)
        self.assertEqual(a._slot, "0")
        self.assertEqual(a._sub_slot, "53")
        self.assertIsNone(a._slot_operator)

    def test_slot_operator_eq(self):
        a = self._atom("dev-libs/foo:0=", matchall=True)
        self.assertEqual(a._slot, "0")
        self.assertEqual(a._slot_operator, "=")

    def test_slot_operator_star(self):
        a = self._atom("dev-libs/foo:*", matchall=True)
        self.assertIsNone(a._slot)
        self.assertEqual(a._slot_operator, "*")

    def test_slot_operator_bare_eq(self):
        a = self._atom("dev-libs/foo:=", matchall=True)
        self.assertIsNone(a._slot)
        self.assertEqual(a._slot_operator, "=")

    def test_blocker_weak(self):
        a = self._atom("!dev-libs/foo", matchall=True)
        self.assertIsNotNone(a._blocker_obj)
        self.assertFalse(a._blocker_obj.overlap.forbid)

    def test_blocker_strong(self):
        a = self._atom("!!dev-libs/foo", matchall=True)
        self.assertIsNotNone(a._blocker_obj)
        self.assertTrue(a._blocker_obj.overlap.forbid)

    def test_combined_fields(self):
        a = self._atom(
            "=sys-apps/portage-2.1-r1:0[doc,a=,!b=,c?,!d?,-e]",
            matchall=True,
        )
        self.assertEqual(a._cp, "sys-apps/portage")
        self.assertEqual(a._version, "2.1-r1")
        self.assertEqual(a._operator, "=")
        self.assertEqual(a._slot, "0")
        self.assertIsNotNone(a._use)
        self.assertEqual(a._use.tokens, ("doc", "a=", "!b=", "c?", "!d?", "-e"))

    def test_use_enabled(self):
        a = self._atom("dev-libs/foo[bar]", matchall=True)
        self.assertIsNotNone(a._use)
        self.assertIn("bar", a._use.enabled)
        self.assertEqual(a._use.disabled, frozenset())

    def test_use_disabled(self):
        a = self._atom("dev-libs/foo[-bar]", matchall=True)
        self.assertIn("bar", a._use.disabled)
        self.assertEqual(a._use.enabled, frozenset())

    def test_use_conditional_enabled(self):
        a = self._atom("dev-libs/foo[bar?]", matchall=True)
        self.assertIsNotNone(a._use.conditional)
        self.assertIn("bar", a._use.conditional.enabled)

    def test_use_conditional_disabled(self):
        a = self._atom("dev-libs/foo[!bar?]", matchall=True)
        self.assertIsNotNone(a._use.conditional)
        self.assertIn("bar", a._use.conditional.disabled)

    def test_use_equal(self):
        a = self._atom("dev-libs/foo[bar=]", matchall=True)
        self.assertIn("bar", a._use.conditional.equal)

    def test_use_not_equal(self):
        a = self._atom("dev-libs/foo[!bar=]", matchall=True)
        self.assertIn("bar", a._use.conditional.not_equal)

    def test_use_missing_enabled_default(self):
        a = self._atom("dev-libs/foo[bar(+)]", matchall=True)
        self.assertIn("bar", a._use.missing_enabled)

    def test_use_missing_disabled_default(self):
        a = self._atom("dev-libs/foo[bar(-)]", matchall=True)
        self.assertIn("bar", a._use.missing_disabled)

    def test_use_str(self):
        a = self._atom("dev-libs/foo[bar,-baz]", matchall=True)
        self.assertEqual(str(a._use), "[bar,-baz]")

    def test_conditional_active(self):
        a = self._atom("dev-libs/foo[bar?]", uselist=["bar"])
        self.assertIsNone(a._use.conditional)
        self.assertIn("bar", a._use.enabled)

    def test_conditional_inactive(self):
        a = self._atom("dev-libs/foo[bar?]", uselist=[])
        self.assertIsNone(a._use)

    def test_conditional_not_equal_active(self):
        a = self._atom("dev-libs/foo[!bar=]", uselist=["bar"])
        self.assertIsNone(a._use.conditional)
        self.assertIn("bar", a._use.disabled)

    def test_conditional_not_equal_inactive(self):
        a = self._atom("dev-libs/foo[!bar=]", uselist=[])
        self.assertIsNone(a._use.conditional)
        self.assertIn("bar", a._use.enabled)

    def test_or_group(self):
        result = self._reduce("|| ( dev-libs/a dev-libs/b )", matchall=True)
        self.assertEqual(result[0], "||")
        self.assertIsInstance(result[1], list)
        self.assertEqual(len(result[1]), 2)

    def test_use_conditional_group_active(self):
        result = self._reduce("foo? ( dev-libs/a dev-libs/b )", uselist=["foo"])
        atoms = [x for x in result if isinstance(x, Atom)]
        self.assertEqual(len(atoms), 2)

    def test_use_conditional_group_inactive(self):
        result = self._reduce("foo? ( dev-libs/a dev-libs/b )", uselist=[])
        self.assertEqual(result, [])

    def test_nested_groups(self):
        result = self._reduce(
            "a? ( || ( dev-libs/a1 dev-libs/a2 ) b? ( dev-libs/b ) )",
            uselist=["a", "b"],
        )
        self.assertIn("||", result)

    def test_matchall_expands_all(self):
        result = self._reduce("a? ( dev-libs/A ) !b? ( dev-libs/B )", matchall=True)
        cps = [a._cp for a in result if isinstance(a, Atom)]
        self.assertIn("dev-libs/A", cps)
        self.assertIn("dev-libs/B", cps)

    def test_glob_version(self):
        a = self._atom("=dev-libs/foo-1.2*", matchall=True)
        self.assertEqual(a._cp, "dev-libs/foo")
        self.assertEqual(a._operator, "=*")
        self.assertIn("1.2", a._version)

    def test_complex_depstr(self):
        result = self._reduce(
            "dev-libs/A >=dev-libs/B-2.0 || ( dev-libs/C dev-libs/D ) "
            "foo? ( =dev-libs/E-1.0:0[bar,baz?] )",
            uselist=["foo"],
        )
        cps = [a._cp for a in result if isinstance(a, Atom)]
        self.assertIn("dev-libs/A", cps)
        self.assertIn("dev-libs/B", cps)
        self.assertIn("dev-libs/E", cps)
        self.assertEqual(result[2], "||")
        self.assertIsInstance(result[3], list)
        or_cps = [a._cp for a in result[3] if isinstance(a, Atom)]
        self.assertIn("dev-libs/C", or_cps)
        self.assertIn("dev-libs/D", or_cps)

    def test_opconvert(self):
        result = use_reduce(
            "|| ( dev-libs/a dev-libs/b )",
            token_class=Atom,
            matchall=True,
            eapi="8",
            opconvert=True,
        )
        self.assertIsInstance(result, list)

    def test_flat(self):
        result = use_reduce(
            "a? ( dev-libs/a ) dev-libs/b",
            token_class=Atom,
            matchall=True,
            eapi="8",
            flat=True,
        )
        self.assertIsInstance(result, list)

    def test_no_token_class(self):
        result = use_reduce("dev-libs/a dev-libs/b", matchall=True, eapi="8")
        self.assertTrue(all(isinstance(x, str) for x in result))

    def test_invalid_missing_close_paren(self):
        with self.assertRaises(InvalidDependString):
            self._reduce("|| ( dev-libs/a dev-libs/b", matchall=True)

    def test_invalid_extra_close_paren(self):
        with self.assertRaises(InvalidDependString):
            self._reduce("dev-libs/a )", matchall=True)

    def test_invalid_atom_no_category(self):
        with self.assertRaises(InvalidDependString):
            self._reduce("foo", matchall=True)

    def test_invalid_operator_no_version(self):
        with self.assertRaises(InvalidDependString):
            self._reduce(">=dev-libs/foo", matchall=True)

    def test_eapi5(self):
        a = self._atom("dev-libs/foo[bar=]", matchall=True, eapi="5")
        self.assertIn("bar", a._use.conditional.equal)

    def test_eapi6(self):
        a = self._atom("dev-libs/foo:0/1=[bar,!baz?]", matchall=True, eapi="6")
        self.assertEqual(a._slot, "0")
        self.assertEqual(a._sub_slot, "1")


class TestUseReducePythonPath(_UseReduceTests, TestCase):
    USE_C_PARSER = False


class TestUseReduceCPath(_UseReduceTests, TestCase):
    USE_C_PARSER = True

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")
        super().setUp()


class TestCParserRawAtom(TestCase):
    def setUp(self):
        self._parser = _c_parser()
        if self._parser is None:
            self.skipTest("_parser extension not available")

    def test_parse_returns_list(self):
        result = self._parser.parse("cat/pkg", matchall=True)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], self._parser.Atom)

    def test_raw_atom_fields(self):
        a = self._parser.parse(
            "=sys-apps/portage-2.1-r1:0/1=[foo,-bar]", matchall=True
        )[0]
        self.assertEqual(a.cp, "sys-apps/portage")
        self.assertEqual(a.version, "2.1-r1")
        self.assertEqual(a.operator, "=")
        self.assertEqual(a.slot, "0")
        self.assertEqual(a.sub_slot, "1")
        self.assertEqual(a.slot_operator, "=")
        self.assertEqual(tuple(a.use), ("foo", "-bar"))
        self.assertIsNone(a.blocker)

    def test_raw_atom_blocker(self):
        a = self._parser.parse("!!dev-libs/foo", matchall=True)[0]
        self.assertEqual(a.blocker, "!!")
        a2 = self._parser.parse("!dev-libs/foo", matchall=True)[0]
        self.assertEqual(a2.blocker, "!")

    def test_raw_atom_glob_version(self):
        a = self._parser.parse("=dev-libs/foo-1.2*", matchall=True)[0]
        self.assertEqual(a.cp, "dev-libs/foo")
        self.assertEqual(a.operator, "=")  # _c_atom_from_c converts this to "=*"
        self.assertEqual(a.version, "1.2*")


class TestClassifyUseDeps(TestCase):
    def setUp(self):
        self._parser = _c_parser()
        if self._parser is None:
            self.skipTest("_parser extension not available")

    def _classify(self, tokens):
        return self._parser.classify_use_deps(tokens)

    def test_enabled(self):
        en, dis, _, _, cond, req = self._classify(("foo",))
        self.assertEqual(en, frozenset({"foo"}))
        self.assertEqual(dis, frozenset())
        self.assertIsNone(cond)
        self.assertEqual(req, frozenset({"foo"}))

    def test_disabled(self):
        en, dis, _, _, cond, req = self._classify(("-foo",))
        self.assertEqual(en, frozenset())
        self.assertEqual(dis, frozenset({"foo"}))
        self.assertIsNone(cond)
        self.assertEqual(req, frozenset({"foo"}))

    def test_conditional_enabled(self):
        _, _, _, _, cond, _ = self._classify(("foo?",))
        self.assertIsNotNone(cond)
        self.assertEqual(cond["enabled"], frozenset({"foo"}))

    def test_conditional_disabled(self):
        _, _, _, _, cond, _ = self._classify(("!foo?",))
        self.assertIsNotNone(cond)
        self.assertEqual(cond["disabled"], frozenset({"foo"}))

    def test_conditional_equal(self):
        _, _, _, _, cond, _ = self._classify(("foo=",))
        self.assertIsNotNone(cond)
        self.assertEqual(cond["equal"], frozenset({"foo"}))

    def test_conditional_not_equal(self):
        _, _, _, _, cond, _ = self._classify(("!foo=",))
        self.assertIsNotNone(cond)
        self.assertEqual(cond["not_equal"], frozenset({"foo"}))

    def test_missing_enabled_default(self):
        en, _, miss_en, miss_dis, _, req = self._classify(("foo(+)",))
        self.assertEqual(en, frozenset({"foo"}))
        self.assertEqual(miss_en, frozenset({"foo"}))
        self.assertEqual(miss_dis, frozenset())
        self.assertEqual(req, frozenset())  # has default, not required

    def test_missing_disabled_default(self):
        _, _, miss_en, miss_dis, _, req = self._classify(("foo(-)",))
        self.assertEqual(miss_en, frozenset())
        self.assertEqual(miss_dis, frozenset({"foo"}))
        self.assertEqual(req, frozenset())

    def test_disabled_with_default(self):
        _, dis, miss_en, _, _, req = self._classify(("-foo(+)",))
        self.assertEqual(dis, frozenset({"foo"}))
        self.assertEqual(miss_en, frozenset({"foo"}))
        self.assertEqual(req, frozenset())

    def test_mixed(self):
        en, dis, _, _, cond, req = self._classify(("foo", "-bar", "!baz?", "qux="))
        self.assertEqual(en, frozenset({"foo"}))
        self.assertEqual(dis, frozenset({"bar"}))
        self.assertIsNotNone(cond)
        self.assertEqual(cond["disabled"], frozenset({"baz"}))
        self.assertEqual(cond["equal"], frozenset({"qux"}))
        self.assertEqual(req, frozenset({"foo", "bar", "baz", "qux"}))

    def test_flag_with_hyphen(self):
        en, dis, _, _, cond, req = self._classify(("foo-bar",))
        self.assertEqual(en, frozenset({"foo-bar"}))
        self.assertEqual(req, frozenset({"foo-bar"}))

    def test_disabled_flag_with_hyphen(self):
        _, dis, _, _, _, req = self._classify(("-foo-bar",))
        self.assertEqual(dis, frozenset({"foo-bar"}))
        self.assertEqual(req, frozenset({"foo-bar"}))

    def test_conditional_flag_with_hyphen(self):
        _, _, _, _, cond, _ = self._classify(("foo-bar?",))
        self.assertEqual(cond["enabled"], frozenset({"foo-bar"}))

    def test_flag_with_plus(self):
        en, _, _, _, _, _ = self._classify(("c++",))
        self.assertEqual(en, frozenset({"c++"}))

    def test_conditional_flag_with_plus(self):
        _, _, _, _, cond, _ = self._classify(("c++?",))
        self.assertEqual(cond["enabled"], frozenset({"c++"}))

    def test_flag_with_at(self):
        en, _, _, _, _, _ = self._classify(("LINGUAS_en@euro",))
        self.assertEqual(en, frozenset({"LINGUAS_en@euro"}))

    def test_disabled_flag_with_at(self):
        _, dis, _, _, _, _ = self._classify(("-LINGUAS_en@euro",))
        self.assertEqual(dis, frozenset({"LINGUAS_en@euro"}))

    def test_invalid_token_raises(self):
        for bad in ("!foo", "!!foo", "?", "=", "foo??", ""):
            with self.subTest(token=bad), self.assertRaises(ValueError):
                self._parser.classify_use_deps((bad,))

    def test_matches_python_use_dep(self):
        eapi_attrs = _get_eapi_attrs("8")
        cases = [
            ("foo",),
            ("-foo",),
            ("foo?",),
            ("!foo?",),
            ("foo=",),
            ("!foo=",),
            ("foo(+)",),
            ("foo(-)",),
            ("-foo(+)",),
            ("foo", "-bar", "!baz?", "qux=", "quux(+)"),
            ("a", "b?", "!c?", "d=", "!e=", "-f", "g(+)", "h(-)"),
            ("foo-bar",),
            ("-foo-bar",),
            ("foo-bar?",),
            ("c++",),
            ("-c++",),
            ("c++?",),
            ("LINGUAS_en@euro",),
            ("-LINGUAS_en@euro",),
        ]
        for tokens in cases:
            with self.subTest(tokens=tokens):
                en, dis, miss_en, miss_dis, cond, req = self._parser.classify_use_deps(
                    tokens
                )
                c_use = _use_dep(
                    tokens,
                    eapi_attrs,
                    enabled_flags=en,
                    disabled_flags=dis,
                    missing_enabled=miss_en,
                    missing_disabled=miss_dis,
                    conditional=cond,
                    required=req,
                )
                py_use = _use_dep(list(tokens), eapi_attrs)
                for attr in (
                    "enabled",
                    "disabled",
                    "required",
                    "missing_enabled",
                    "missing_disabled",
                ):
                    self.assertEqual(
                        getattr(c_use, attr),
                        getattr(py_use, attr),
                        f"{attr} mismatch for {tokens}",
                    )
                if py_use.conditional is None:
                    self.assertIsNone(c_use.conditional)
                else:
                    self.assertIsNotNone(c_use.conditional)
                    for k in ("enabled", "disabled", "equal", "not_equal"):
                        self.assertEqual(
                            getattr(c_use.conditional, k, frozenset()),
                            getattr(py_use.conditional, k, frozenset()),
                            f"conditional.{k} for {tokens}",
                        )


class TestCFastVsPython(TestCase):
    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _compare(self, depstr, uselist=None, matchall=False, eapi="8", flat=False):
        kw = dict(
            token_class=Atom,
            matchall=matchall,
            eapi=eapi,
            uselist=uselist or [],
            flat=flat,
        )
        with _use_c_parser(False):
            py_result = use_reduce(depstr, **kw)
        c_result = use_reduce(depstr, **kw)
        ok, msg = _result_equal(c_result, py_result)
        self.assertTrue(ok, f"{depstr!r} (flat={flat}): {msg}")

    def test_simple_atom(self):
        self._compare("dev-libs/foo")

    def test_versioned_atom(self):
        self._compare("=dev-libs/foo-1.2.3-r1")

    def test_blocker_weak(self):
        self._compare("!dev-libs/foo")

    def test_blocker_strong(self):
        self._compare("!!dev-libs/foo")

    def test_slot(self):
        self._compare("dev-libs/foo:1")

    def test_sub_slot(self):
        self._compare("dev-libs/foo:1/2")

    def test_slot_operator(self):
        self._compare("dev-libs/foo:=")

    def test_slot_and_operator(self):
        self._compare("dev-libs/foo:1=")

    def test_use_enabled(self):
        self._compare("dev-libs/foo[bar]", matchall=True)

    def test_use_disabled(self):
        self._compare("dev-libs/foo[-bar]", matchall=True)

    def test_use_multiple(self):
        self._compare("dev-libs/foo[a,b,c,-d]", matchall=True)

    def test_use_conditional_enabled(self):
        self._compare("dev-libs/foo[bar?]", matchall=True)

    def test_use_conditional_disabled(self):
        self._compare("dev-libs/foo[!bar?]", matchall=True)

    def test_use_equal(self):
        self._compare("dev-libs/foo[bar=]", matchall=True)

    def test_use_not_equal(self):
        self._compare("dev-libs/foo[!bar=]", matchall=True)

    def test_use_miss_en_default(self):
        self._compare("dev-libs/foo[bar(+)]", matchall=True)

    def test_use_miss_dis_default(self):
        self._compare("dev-libs/foo[bar(-)]", matchall=True)

    def test_use_complex(self):
        self._compare("=sys-apps/portage-2.1-r1:0[doc,a=,!b=,c?,!d?,-e]", matchall=True)

    def test_cond_eval_active(self):
        self._compare("dev-libs/foo[bar?]", uselist=["bar"])

    def test_cond_eval_inactive(self):
        self._compare("dev-libs/foo[bar?]", uselist=[])

    def test_cond_not_eq_active(self):
        self._compare("dev-libs/foo[!bar=]", uselist=["bar"])

    def test_or_group(self):
        self._compare("|| ( dev-libs/a dev-libs/b )", matchall=True)

    def test_use_cond_group(self):
        self._compare("foo? ( dev-libs/a dev-libs/b )", uselist=["foo"])

    def test_nested_groups(self):
        self._compare(
            "a? ( || ( dev-libs/a1 dev-libs/a2 ) b? ( dev-libs/b ) )",
            uselist=["a", "b"],
        )

    def test_complex(self):
        self._compare(
            "dev-libs/A >=dev-libs/B-2.0 || ( dev-libs/C dev-libs/D ) "
            "foo? ( =dev-libs/E-1.0:0[bar,baz?] )",
            uselist=["foo"],
        )

    def test_matchall(self):
        self._compare("a? ( dev-libs/A ) !b? ( dev-libs/B )", matchall=True)

    def test_eapi5(self):
        self._compare("dev-libs/foo[bar=]", matchall=True, eapi="5")

    def test_eapi6(self):
        self._compare("dev-libs/foo:0/1=[bar,!baz?]", matchall=True, eapi="6")

    # '@' in USE flag names, deprecated but allowed per PMS (old LINGUAS flags)
    def test_use_at_sign(self):
        self._compare("dev-libs/foo[LINGUAS_en@euro]", matchall=True)

    def test_use_at_sign_disabled(self):
        self._compare("dev-libs/foo[-LINGUAS_en@euro]", matchall=True)

    def test_glob_version(self):
        self._compare("=dev-libs/foo-1.2*", matchall=True)

    def test_slot_operator_bare_eq(self):
        self._compare("dev-libs/foo:=", matchall=True)

    def test_anyof_conjunction_alternative(self):
        # ( a b ) inside || is a conjunction and must stay nested, not flattened.
        self._compare("|| ( ( dev-libs/a dev-libs/b ) dev-libs/c )", matchall=True)

    def test_anyof_conjunction_second(self):
        self._compare("|| ( dev-libs/a ( dev-libs/b dev-libs/c ) )", matchall=True)

    def test_anyof_two_conjunctions(self):
        self._compare(
            "|| ( ( dev-libs/a dev-libs/b ) ( dev-libs/c dev-libs/d ) )",
            matchall=True,
        )

    def test_anyof_active_conditional_conjunction(self):
        # An active USE-conditional group inside || is also a conjunction.
        self._compare(
            "|| ( foo? ( dev-libs/a dev-libs/b ) dev-libs/c )", uselist=["foo"]
        )

    def test_anyof_nested_anyof_flattens(self):
        self._compare("|| ( dev-libs/a || ( dev-libs/b dev-libs/c ) )", matchall=True)

    def test_anyof_naked_wrapping_anyof(self):
        # ( || ( b c ) ) inside || flattens its alternatives up.
        self._compare(
            "|| ( ( || ( dev-libs/b dev-libs/c ) ) dev-libs/a )", matchall=True
        )

    def test_anyof_deeply_nested_conjunctions(self):
        self._compare(
            "|| ( ( dev-libs/a ( dev-libs/b dev-libs/c ) ) dev-libs/e )",
            matchall=True,
        )

    def test_anyof_empty_conditional_eapi7(self):
        # Empty || after USE evaluation yields a placeholder atom in EAPI 7+.
        self._compare("|| ( foo? ( dev-libs/a ) )", uselist=[], eapi="8")
        self._compare("|| ( foo? ( dev-libs/a ) )", uselist=[], eapi="6")

    def test_flat_simple(self):
        self._compare("dev-libs/a dev-libs/b", matchall=True, flat=True)

    def test_flat_or_group(self):
        self._compare("|| ( dev-libs/a dev-libs/b )", matchall=True, flat=True)

    def test_flat_nested_or(self):
        # Nested any-of groups keep a '||' token per level in flat mode.
        self._compare(
            "|| ( dev-libs/a || ( dev-libs/b dev-libs/c ) )",
            matchall=True,
            flat=True,
        )

    def test_flat_use_conditional_active(self):
        self._compare("foo? ( dev-libs/a dev-libs/b )", uselist=["foo"], flat=True)

    def test_flat_use_conditional_inactive(self):
        self._compare("foo? ( dev-libs/a dev-libs/b )", uselist=[], flat=True)

    def test_flat_nested_conditionals(self):
        self._compare(
            "a? ( dev-libs/a b? ( dev-libs/b ) ) c? ( dev-libs/c )",
            uselist=["a", "c"],
            flat=True,
        )

    def test_flat_conditional_or_mix(self):
        self._compare(
            "foo? ( || ( dev-libs/a dev-libs/b ) ) dev-libs/c",
            uselist=["foo"],
            flat=True,
        )

    def test_flat_atoms_with_use(self):
        self._compare(
            "dev-libs/a[x] foo? ( =dev-libs/b-1[y?] )", uselist=["foo"], flat=True
        )

    def test_flat_matchall(self):
        self._compare(
            "a? ( dev-libs/a ) !b? ( dev-libs/b ) || ( dev-libs/c dev-libs/d )",
            matchall=True,
            flat=True,
        )

    def test_flat_complex(self):
        self._compare(
            "dev-libs/A >=dev-libs/B-2.0 || ( dev-libs/C dev-libs/D ) "
            "foo? ( =dev-libs/E-1.0:0[bar,baz?] || ( dev-libs/F dev-libs/G ) )",
            uselist=["foo"],
            flat=True,
        )

    def test_invalid_raises_same_exception(self):
        bad_cases = [
            "|| ( dev-libs/a dev-libs/b",
            "dev-libs/a )",
            ">=dev-libs/foo",
        ]
        kw = dict(token_class=Atom, matchall=True, eapi="8", uselist=[])
        for depstr in bad_cases:
            with self.subTest(depstr=depstr):
                with _use_c_parser(False):
                    with self.assertRaises(InvalidDependString):
                        use_reduce(depstr, **kw)
                with self.assertRaises(InvalidDependString):
                    use_reduce(depstr, **kw)


class TestDeepNesting(TestCase):
    """The C parser keeps its group stack on the heap, so it must not impose a
    nesting limit the pure-Python path does not have."""

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _reduce(self, depstr, use_c):
        with _use_c_parser(use_c):
            return use_reduce(
                depstr, token_class=Atom, matchall=True, eapi="8", uselist=[]
            )

    def test_nesting_parity(self):
        for depth in (1, 8, 31, 32, 33, 64, 65, 200):
            with self.subTest(depth=depth):
                depstr = "( " * depth + "dev-libs/a" + " )" * depth
                self.assertEqual(
                    self._reduce(depstr, use_c=True),
                    self._reduce(depstr, use_c=False),
                )

    def test_nesting_parity_any_of(self):
        for depth in (1, 8, 31, 32, 33, 64, 65, 200):
            with self.subTest(depth=depth):
                depstr = "|| ( " * depth + "dev-libs/a" + " )" * depth
                self.assertEqual(
                    self._reduce(depstr, use_c=True),
                    self._reduce(depstr, use_c=False),
                )


class TestLongAtoms(TestCase):
    """Category and package names are not length-limited, so the C path must
    not reject an atom that the pure-Python path accepts."""

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _reduce(self, depstr, use_c):
        with _use_c_parser(use_c):
            return use_reduce(
                depstr, token_class=Atom, matchall=True, eapi="8", uselist=[]
            )

    def test_long_package_name(self):
        for length in (8, 250, 255, 256, 300, 512, 1000):
            with self.subTest(length=length):
                depstr = "cat/" + "a" * length
                self.assertEqual(
                    self._reduce(depstr, use_c=True),
                    self._reduce(depstr, use_c=False),
                )

    def test_long_versioned_atom(self):
        for length in (250, 256, 600):
            with self.subTest(length=length):
                depstr = "=cat/" + "a" * length + "-1.0"
                c = self._reduce(depstr, use_c=True)
                py = self._reduce(depstr, use_c=False)
                self.assertEqual(c, py)
                self.assertEqual(c[0]._cpv, py[0]._cpv)

    def test_long_category(self):
        depstr = "c" * 400 + "/pkg"
        self.assertEqual(
            self._reduce(depstr, use_c=True), self._reduce(depstr, use_c=False)
        )


class _AtomParityMixin:
    """Helpers for asserting that _parser.scan_atom + Atom._c_fast_init agrees
    with the pure-Python regex path, both on what it accepts and on the fields
    it produces."""

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _both(self, s, **kw):
        with _use_c_parser(False):
            try:
                py = Atom(s, **kw)
                py_exc = None
            except Exception as e:
                py, py_exc = None, type(e)
        try:
            c = Atom(s, **kw)
            c_exc = None
        except Exception as e:
            c, c_exc = None, type(e)
        return (py, py_exc), (c, c_exc)

    def _assert_use_reduce_same(self, s, eapi="8"):
        """Assert that both paths accept or reject s identically.

        Atom() falls back to the regex path when scan_atom rejects a string,
        so _assert_same passes even for a scanner that rejects too much.
        use_reduce has no such fallback: a token the C parser will not scan
        as an atom is a hard error there."""
        results = []
        for use_c in (False, True):
            with _use_c_parser(use_c):
                try:
                    results.append(str(use_reduce(s, token_class=Atom, eapi=eapi)))
                except InvalidDependString:
                    results.append(None)
        self.assertEqual(results[0], results[1], f"{s!r}: use_reduce mismatch")

    def _assert_same(self, s, **kw):
        (py, pe), (c, ce) = self._both(s, **kw)
        self.assertEqual(pe, ce, f"{s!r}: exception {pe} vs {ce}")
        if pe is None:
            for attr in (
                "_cp",
                "_cpv",
                "_version",
                "_operator",
                "_slot",
                "_sub_slot",
                "_slot_operator",
                "_repo",
                "_build_id",
                "_extended_syntax",
            ):
                self.assertEqual(getattr(py, attr), getattr(c, attr), f"{s!r}: {attr}")
            self.assertEqual(str(py._use or ""), str(c._use or ""), f"{s!r}: use")
            self.assertEqual(str(py), str(c))


class TestScanAtom(_AtomParityMixin, TestCase):
    """Test that _parser.scan_atom + Atom._c_fast_init matches the pure-Python
    regex path for both valid atoms and invalid ones."""

    def test_valid_atoms(self):
        for s in (
            "sys-apps/portage",
            "=sys-apps/portage-2.1",
            ">=dev-libs/foo-1.2.3-r1:0/1=[a,-b,c?,!d?,e=]",
            "!!media-libs/x:2",
            "~cat/pkg-1.0",
            "cat/pkg:0/1=",
            "dev-libs/gtk+",
        ):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")
                self._assert_same(s, eapi=None)

    def test_glob_only_with_equals(self):
        self._assert_same("=cat/pkg-1.2*", eapi="8")
        self._assert_same(">=cat/pkg-1.2*", eapi="8")  # invalid -> both reject
        self._assert_same("<cat/pkg-1*", eapi="8")

    def test_version_requires_operator(self):
        self._assert_same("cat/pkg-1", eapi="8")  # invalid
        self._assert_same("cat/pkg-1.2.3", eapi="8")  # invalid

    def test_name_must_not_end_in_version(self):
        for s in ("<cat/bar-2-0", "=foo/bar-1-r1-1-r1", "=cat/libc-2-9999"):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")  # invalid, both reject

    def test_leading_plus_rejected(self):
        for s in ("+cat/pkg", "cat/pkg:+slot", "cat/pkg:0/+sub"):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")

    def test_conflicting_use_rejected(self):
        self._assert_same("cat/pkg[a(+),-a]", eapi="8")
        self._assert_same("cat/pkg[a,a]", eapi="8")

    def test_repo_and_build_id_fall_back(self):
        # scan_atom rejects these; the regex path handles them when allowed.
        self._assert_same("cat/pkg::gentoo", eapi=None, allow_repo=True)
        self._assert_same("=cat/pkg-1-3", eapi=None, allow_build_id=True)

    def test_eapi_incompatibility(self):
        self._assert_same("cat/pkg:0", eapi="0")  # slot deps invalid in EAPI 0
        self._assert_same("cat/pkg[a]", eapi="1")  # use deps invalid in EAPI 1
        self._assert_same("cat/pkg[a(+)]", eapi="4")  # defaults invalid in EAPI 4

    def test_is_valid_flag(self):
        # The conditional-flag-in-IUSE check runs in the fast path too.
        def accept_all(flag):
            return True

        def reject_x(flag):
            return not flag.startswith("x")

        self._assert_same("cat/pkg[a?,!b?]", eapi="8", is_valid_flag=accept_all)
        self._assert_same("cat/pkg[x?]", eapi="8", is_valid_flag=reject_x)  # invalid
        self._assert_same("cat/pkg[x=]", eapi="8", is_valid_flag=reject_x)  # invalid
        # Non-conditional flags are not validated by is_valid_flag.
        self._assert_same("cat/pkg[x,-y]", eapi="8", is_valid_flag=reject_x)

    def test_wildcard_falls_back(self):
        # Extended/wildcard atoms fail scan_atom and use the regex path;
        # results (extended_syntax etc.) must still match.
        for s in ("*/*", "cat/*", "*/pkg", "dev-*/foo", "=cat/pkg-*1*"):
            with self.subTest(s=s):
                self._assert_same(s, allow_wildcard=True)


class TestScanAtomNameGrammar(_AtomParityMixin, TestCase):
    """Category, package-name, version and revision edge cases, adapted from
    pkgcore's tests/ebuild/test_cpv.py.

    The corpus only supplies awkward shapes; it does not assert which of them
    are valid. Portage's own regex path is the reference, and every string is
    checked for parity against it, so a C scanner that is stricter or laxer
    than portage anywhere in this grammar fails."""

    # Names that are legal per PMS 3.1.1/3.1.2, including the ones that look
    # like they should not be: a bare "_" category, a category with a dot in
    # it, and package names ending in hyphens or in a hyphen-digit sequence
    # that is not a version.
    GOOD_CATS = (
        "dev-util",
        "dev+",
        "DEV-UTIL+",
        "aaa0",
        "aaa-0",
        "multi--hyphen",
        "_dev",
        "_",
        "cross-hppa2.0-unknown-linux-gnu",
    )
    BAD_CATS = (
        "",
        ".reject",
        " reject",
        "-",
        "+",
        "dev-util ",
        "multi/blah/depth",
        "multi//depth",
    )
    GOOD_PKGS = (
        "diffball",
        "a9",
        "a9+",
        "a-100dpi",
        "diff-mode-",
        "multi--hyphen",
        "timidity--",
        "frob---",
        "diffball-9-",
        "7z",
        "81",
        "2048",
        "81-libretro",
        "12+",
        "xf86-video-r128",
        "emacs-cvs",
    )
    # "diffball-9" and "bar-11-r3" are rejected because an unversioned atom's
    # name may not end in something that parses as a version.
    BAD_PKGS = (
        "diffball ",
        "diffball-9",
        "a-3D",
        "-df",
        "+dfa",
        "timidity--9f",
        "ormaybe---13_beta",
        "bar-11-r3",
    )

    GOOD_VERS = ("1", "2.3.4", "2.3.4a", "02.3", "2.03", "3d")
    BAD_VERS = ("2.3a.4", "2.a.3", "2.3_", "2.3 ", "2.3.", "cvs.2", "3D")
    GOOD_REVS = ("", "-r0", "-r1", "-r300", "-r1000000000000000000")
    BAD_REVS = ("-r", "-ra", "-R1")

    SIMPLE_SUFS = ("_alpha", "_beta", "_pre", "_p", "_rc")
    GOOD_SUFS = SIMPLE_SUFS + tuple(f"{x}{n}" for n, x in enumerate(SIMPLE_SUFS))
    BAD_SUFS = ("_a", "_9", "_") + tuple(f"{x} " for x in SIMPLE_SUFS)

    def test_category_grammar(self):
        for cat in self.GOOD_CATS + self.BAD_CATS:
            with self.subTest(cat=cat):
                self._assert_same(f"{cat}/diffball", eapi="8")

    def test_package_name_grammar(self):
        for pkg in self.GOOD_PKGS + self.BAD_PKGS:
            with self.subTest(pkg=pkg):
                self._assert_same(f"dev-util/{pkg}", eapi="8")

    def test_category_package_matrix(self):
        for cat in self.GOOD_CATS:
            for pkg in self.GOOD_PKGS:
                with self.subTest(cat=cat, pkg=pkg):
                    self._assert_same(f"{cat}/{pkg}", eapi="8")

    def test_version_grammar(self):
        for ver in self.GOOD_VERS + self.BAD_VERS:
            with self.subTest(ver=ver):
                self._assert_same(f"=dev-util/diffball-{ver}", eapi="8")
                self._assert_same(f"~dev-util/diffball-{ver}", eapi="8")

    def test_revision_grammar(self):
        for rev in self.GOOD_REVS + self.BAD_REVS:
            with self.subTest(rev=rev):
                self._assert_same(f"=dev-util/diffball-2.3.4{rev}", eapi="8")

    def test_version_suffix_grammar(self):
        for suf in self.GOOD_SUFS + self.BAD_SUFS:
            with self.subTest(suf=suf):
                self._assert_same(f"=dev-util/diffball-1{suf}", eapi="8")
                self._assert_same(f"=dev-util/diffball-1{suf}-r1", eapi="8")

    def test_version_suffix_and_revision_matrix(self):
        for ver in self.GOOD_VERS:
            for rev in self.GOOD_REVS + self.BAD_REVS:
                with self.subTest(ver=ver, rev=rev):
                    self._assert_same(f"=dev-util/diffball-{ver}{rev}", eapi="8")

    def test_version_glob_grammar(self):
        for ver in self.GOOD_VERS + self.BAD_VERS:
            with self.subTest(ver=ver):
                self._assert_same(f"=dev-util/diffball-{ver}*", eapi="8")

    def test_package_name_containing_version_like_words(self):
        # A hyphen-digit run only terminates the name if what follows it is a
        # complete version, so these all stay part of the package name.
        for s in (
            "dev-util/diffball-blah-monkeys",
            "bah/f-100dpi",
            "dev-ut-asdf/emacs-cvs",
            "bbb-9/foon",
            "dev-util/foo-123-bar",
            "app-text/foo-2abc",
            "app-text/foo-2_bar",
        ):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")

    def test_hyphens_that_do_not_start_a_version(self):
        # A '-' that is not followed by a complete version is an ordinary
        # name character, wherever it appears, so these names run to the end
        # of the token rather than ending at the '-'.
        for s in (
            "dev-util/diff-mode-",
            "dev-util/timidity--",
            "dev-util/frob---",
            "dev-util/diffball-9-",
            "dev-util/foo-2048+",
            "dev-util/foo-9-bar",
        ):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")
                self._assert_use_reduce_same(s)

    def test_all_digit_name_word(self):
        # bug 981298: a name word made only of digits is a name, not a
        # version, so "games-emulation/81-libretro" is an ordinary
        # unversioned atom.
        for s in (
            "games-emulation/81-libretro",
            "games-emulation/2048-libretro",
            "games-arcade/2048",
            "cat/81",
            "cat/81:0",
            "cat/81[foo]",
            "!cat/81",
            "cat/81-r1",
            "=cat/81-1.0",
            "=games-emulation/81-libretro-1.2-r3",
            "cat/81-1.0",
        ):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")
                self._assert_use_reduce_same(s)

    def test_slot_grammar(self):
        # ":=" and ":*" are whole slot deps, not sub-slots, and the "="
        # operator only ever comes last.
        for s in (
            "cat/pkg:0",
            "cat/pkg:0/53",
            "cat/pkg:0=",
            "cat/pkg:0/53=",
            "cat/pkg:=",
            "cat/pkg:*",
            "cat/pkg:my-slot_2.1/other+sub=",
            "cat/pkg:0/*",  # invalid
            "cat/pkg:0/=",  # invalid
            "cat/pkg:0=/53",  # invalid
            "cat/pkg:0=/53=",  # invalid
            "cat/pkg:0/",  # invalid
            "cat/pkg:",  # invalid
            "cat/pkg:/53",  # invalid
            "cat/pkg:-slot",  # invalid
            "cat/pkg:0//53",  # invalid
            "cat/pkg:0/53/54",  # invalid
            "cat/pkg:*=",  # invalid
            "cat/pkg:=*",  # invalid
        ):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")

    def test_truncated_atoms(self):
        for s in ("cat/", "cat/pkg[", "cat/pkg[a", "cat/pkg[]", "cat", "/pkg", "/"):
            with self.subTest(s=s):
                self._assert_same(s, eapi="8")

    def test_pathological_name(self):
        # https://github.com/pkgcore/pkgcore/issues/463 and the oversized name
        # from pkgcore's test_cpv.py, which also exercises the heap fallback in
        # join_atom_string().
        cat = "dev-java"
        pkg = (
            "log5j-777777777777777777777777777777777-777777777777777777"
            "-7777777777777777777-7777777-7dev-q!7778"
        )
        self._assert_same(f"{cat}/{pkg}", eapi="8")
        self._assert_same("cross-hppa2.0-unknown-linux-gnu/gcc", eapi="8")


class TestCParserMalformedGroups(TestCase):
    """Whitespace and delimiter errors in group syntax. Every one of these has
    a distinct error path in scan_item()/scan_group_contents(), and each must
    be rejected by both parsers."""

    CASES = (
        "( dev-libs/a",  # no closing paren
        "( dev-libs/a dev-libs/b",  # no closing paren, multiple items
        "|| ( dev-libs/a ",  # trailing whitespace, still unterminated
        "(dev-libs/a )",  # no whitespace after '('
        "|| (dev-libs/a )",  # no whitespace after '(' in an any-of
        "foo? (dev-libs/a )",  # no whitespace after '(' in a conditional
        "||( dev-libs/a )",  # no whitespace after the '||' prefix
        "foo?( dev-libs/a )",  # no whitespace after the 'foo?' prefix
        "|| dev-libs/a",  # any-of with no group at all
        "foo? dev-libs/a",  # conditional with no group at all
        "|| dev-libs/a dev-libs/b",
        "( dev-libs/a )dev-libs/b",  # no whitespace after ')'
        "|| (",
        "foo?",
        "||",
    )

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _reduce(self, depstr, use_c):
        with _use_c_parser(use_c):
            return use_reduce(depstr, token_class=Atom, eapi="8", uselist=["foo"])

    def test_both_paths_reject(self):
        for depstr in self.CASES:
            with self.subTest(depstr=depstr):
                with self.assertRaises(InvalidDependString):
                    self._reduce(depstr, use_c=False)
                with self.assertRaises(InvalidDependString):
                    self._reduce(depstr, use_c=True)


class TestCParserWhitespace(TestCase):
    """The C parser sees the dep string unsplit, so leading, trailing and
    repeated whitespace is its own business rather than str.split()'s."""

    CASES = (
        "dev-libs/a ",
        " dev-libs/a",
        "\tdev-libs/a\n",
        "dev-libs/a  dev-libs/b",
        "|| ( dev-libs/a dev-libs/b )   ",
        "\n|| (\n\tdev-libs/a\n\tdev-libs/b\n)\n",
        "   ",
        "",
    )

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _reduce(self, depstr, use_c):
        with _use_c_parser(use_c):
            return use_reduce(depstr, token_class=Atom, eapi="8", matchall=True)

    def test_parity(self):
        for depstr in self.CASES:
            with self.subTest(depstr=depstr):
                py = self._reduce(depstr, use_c=False)
                c = self._reduce(depstr, use_c=True)
                ok, msg = _result_equal(c, py)
                self.assertTrue(ok, f"{depstr!r}: {msg}")


class TestCParserInactiveConditionalBodies(TestCase):
    """The body of an inactive use conditional is not emitted, but it is still
    parsed with the real grammar (via the skip visitor) so that syntax errors
    inside it are still reported. Nested groups and nested conditionals inside
    an inactive body are the interesting cases."""

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _reduce(self, depstr, use_c, uselist=()):
        with _use_c_parser(use_c):
            return use_reduce(depstr, token_class=Atom, eapi="8", uselist=list(uselist))

    VALID = (
        ("foo? ( ( dev-libs/a ) )", ()),
        ("foo? ( || ( dev-libs/a dev-libs/b ) )", ()),
        ("foo? ( bar? ( dev-libs/a ) )", ()),
        ("foo? ( bar? ( dev-libs/a ) )", ("bar",)),
        ("!foo? ( bar? ( dev-libs/a ) )", ("foo", "bar")),
        ("foo? ( !bar? ( dev-libs/a ) )", ()),
        ("foo? ( bar? ( || ( dev-libs/a dev-libs/b ) ) )", ()),
        ("foo? ( dev-libs/a ) bar? ( dev-libs/b )", ("bar",)),
    )

    # Syntax errors that only appear inside a body that is never emitted.
    INVALID = (
        ("foo? ( ||( dev-libs/a ) )", ()),
        ("foo? ( (dev-libs/a ) )", ()),
        ("foo? ( bar? ( noslash ) )", ()),
        ("foo? ( bar? ( dev-libs/a )", ()),
        ("foo? ( >=dev-libs/a )", ()),
    )

    def test_inactive_bodies_parity(self):
        for depstr, uselist in self.VALID:
            with self.subTest(depstr=depstr, uselist=uselist):
                py = self._reduce(depstr, use_c=False, uselist=uselist)
                c = self._reduce(depstr, use_c=True, uselist=uselist)
                ok, msg = _result_equal(c, py)
                self.assertTrue(ok, f"{depstr!r} uselist={uselist}: {msg}")

    def test_errors_inside_inactive_bodies_still_raise(self):
        for depstr, uselist in self.INVALID:
            with self.subTest(depstr=depstr, uselist=uselist):
                with self.assertRaises(InvalidDependString):
                    self._reduce(depstr, use_c=False, uselist=uselist)
                with self.assertRaises(InvalidDependString):
                    self._reduce(depstr, use_c=True, uselist=uselist)


class TestCAtomObjectProtocol(TestCase):
    """_parser.Atom's tp_repr/tp_str/tp_hash/tp_richcompare slots."""

    def setUp(self):
        self._parser = _c_parser()
        if self._parser is None:
            self.skipTest("_parser extension not available")

    def _atom(self, s):
        return self._parser.parse(s, matchall=True)[0]

    def test_str(self):
        self.assertEqual(
            str(self._atom(">=dev-libs/a-1:2/3=[x]")), ">=dev-libs/a-1:2/3=[x]"
        )

    def test_repr(self):
        self.assertEqual(repr(self._atom("dev-libs/a")), "Atom('dev-libs/a')")

    def test_hash_matches_string(self):
        self.assertEqual(hash(self._atom("dev-libs/a")), hash("dev-libs/a"))

    def test_hashable_in_containers(self):
        a, b = self._atom("dev-libs/a"), self._atom("dev-libs/a")
        self.assertEqual(len({a, b}), 1)
        self.assertEqual({a: 1}[b], 1)

    def test_equality(self):
        a, b = self._atom("dev-libs/a"), self._atom("dev-libs/a")
        c = self._atom("dev-libs/b")
        self.assertTrue(a == b)
        self.assertFalse(a != b)
        self.assertFalse(a == c)
        self.assertTrue(a != c)

    def test_equality_with_foreign_type(self):
        a = self._atom("dev-libs/a")
        for other in ("dev-libs/a", 1, None, Atom("dev-libs/a")):
            with self.subTest(other=other):
                self.assertFalse(a == other)
                self.assertTrue(a != other)

    def test_ordering_is_not_implemented(self):
        a, b = self._atom("dev-libs/a"), self._atom("dev-libs/b")
        for op in (operator.lt, operator.le, operator.gt, operator.ge):
            with self.subTest(op=op.__name__), self.assertRaises(TypeError):
                op(a, b)


class TestCParserEapiGuard(TestCase):
    """The C scanner implements the modern (EAPI 5+) atom grammar
    unconditionally. The use_reduce fast-path guard must therefore only take
    the C path for EAPIs whose grammar matches -- None (permissive) or
    slot_operator-capable (EAPI 5+) -- so it never accepts atoms that the
    pure-Python path rejects under an older EAPI."""

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _reduce(self, depstr, eapi, use_c):
        with _use_c_parser(use_c):
            return use_reduce(
                depstr, token_class=Atom, matchall=True, eapi=eapi, uselist=[]
            )

    def test_slot_operator_gate_matches_expectation(self):
        for eapi in ("0", "1", "4"):
            self.assertFalse(_get_eapi_attrs(eapi).slot_operator, eapi)
        for eapi in (None, "5", "6", "7", "8"):
            self.assertTrue(_get_eapi_attrs(eapi).slot_operator, eapi)

    def test_old_eapi_rejects_modern_syntax(self):
        # Each string is invalid under the given older EAPI. The Python path
        # rejects it; the C path is guard-skipped for these EAPIs, so it must
        # reject identically rather than silently accept.
        cases = [
            ("dev-libs/foo:=", "4"),  # slot operator: EAPI 5+
            ("dev-libs/foo:1/2", "4"),  # sub-slot: EAPI 5+
            ("dev-libs/foo[bar]", "1"),  # use dep: EAPI 4+
            ("dev-libs/foo:1", "0"),  # slot dep: EAPI 1+
        ]
        for depstr, eapi in cases:
            with self.subTest(depstr=depstr, eapi=eapi):
                with self.assertRaises(InvalidDependString):
                    self._reduce(depstr, eapi, use_c=False)
                with self.assertRaises(InvalidDependString):
                    self._reduce(depstr, eapi, use_c=True)

    def test_valid_across_eapis_parity(self):
        cases = [
            ("dev-libs/foo", None),
            ("dev-libs/foo", "0"),
            ("dev-libs/foo", "8"),
            ("dev-libs/foo:1", "1"),
            ("dev-libs/foo:1", "8"),
            ("dev-libs/foo[bar]", "4"),
            ("dev-libs/foo[bar]", "8"),
            ("dev-libs/foo:=", "5"),
            ("dev-libs/foo:1/2=", "8"),
        ]
        for depstr, eapi in cases:
            with self.subTest(depstr=depstr, eapi=eapi):
                py = self._reduce(depstr, eapi, use_c=False)
                c = self._reduce(depstr, eapi, use_c=True)
                ok, msg = _result_equal(c, py)
                self.assertTrue(ok, f"{depstr!r} eapi={eapi}: {msg}")


class TestKillSwitch(TestCase):
    """PORTAGE_NATIVE_DEP_PARSER=0 must disable the C path.  It is consulted
    when portage.dep is imported, so this has to run in a fresh process."""

    PROBE = "import portage.dep; print(portage.dep._c_dep_parser is None)"

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")

    def _probe(self, value):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path(portage.__file__).parent.parent), env.get("PYTHONPATH", "")]
        )
        if value is None:
            env.pop("PORTAGE_NATIVE_DEP_PARSER", None)
        else:
            env["PORTAGE_NATIVE_DEP_PARSER"] = value
        out = subprocess.run(
            [sys.executable, "-c", self.PROBE],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()

    def test_unset_uses_c_parser(self):
        self.assertEqual(self._probe(None), "False")

    def test_zero_disables_c_parser(self):
        self.assertEqual(self._probe("0"), "True")

    def test_other_values_do_not_disable(self):
        # Only the exact string "0" disables it.
        for value in ("1", "", "no"):
            with self.subTest(value=value):
                self.assertEqual(self._probe(value), "False")


class TestCParserAllocFailure(TestCase):
    """Every allocation the C parser makes can fail, and each failure has its
    own cleanup path that no ordinary test reaches.  _testcapi.set_nomemory(n,
    n + 1) makes the nth allocation fail, so sweeping n over a whole call
    exercises those paths one at a time.

    A failed allocation must surface as MemoryError, must not crash, and must
    not leave the parser unusable: the group-frame stack and the half-built
    Atom of the aborted call have to be released.

    set_nomemory() hooks CPython's own allocator, so these tests skip wherever
    it is unavailable: _testcapi is a test-support module that is not installed
    everywhere, and PyPy provides the module without the memory hooks."""

    # Large enough that the sweep runs past the last allocation of every case
    # here; _sweep() fails if a case ever outgrows it.
    SWEEP_LIMIT = 400

    PARSE_CASES = (
        ("dev-libs/a", (), False),
        ("=sys-apps/portage-2.1-r1:0/1=[doc,a=,!b=,c?,!d?,-e]", (), True),
        ("|| ( dev-libs/a dev-libs/b )", (), True),
        ("|| ( ( dev-libs/a dev-libs/b ) dev-libs/c )", (), True),
        ("foo? ( dev-libs/a dev-libs/b )", ("foo",), False),
        ("foo? ( dev-libs/a )", (), False),
        (
            "dev-libs/A >=dev-libs/B-2.0 || ( dev-libs/C dev-libs/D ) "
            "foo? ( =dev-libs/E-1.0:0[bar,baz?] )",
            ("foo",),
            False,
        ),
        # Long enough to miss the on-stack buffer in join_atom_string().
        ("=cat/" + "a" * 300 + "-1.0", (), True),
        # Deeper than PY_PARSE_INLINE_DEPTH, so the group-frame stack moves to
        # the heap (PyMem_New) and then grows again (PyMem_Realloc).
        ("( " * 40 + "dev-libs/a" + " )" * 40, (), True),
        ("( " * 70 + "dev-libs/a" + " )" * 70, (), True),
    )

    ATOM_CASES = (
        "sys-apps/portage",
        ">=dev-libs/foo-1.2.3-r1:0/1=[a,-b,c?,!d?,e=]",
        "!!media-libs/x:2",
        "=cat/pkg-1.2*",
    )

    USE_DEP_CASES = (
        ("foo",),
        ("foo", "-bar", "!baz?", "qux=", "quux(+)"),
        ("a", "b?", "!c?", "d=", "!e=", "-f", "g(+)", "h(-)"),
    )

    def setUp(self):
        if _orig_c_dep_parser is None:
            self.skipTest("_parser extension not available")
        if _testcapi is None:
            self.skipTest("_testcapi memory hooks not available")
        self._parser = _orig_c_dep_parser

    def _sweep(self, fn, *args, **kwargs):
        """Call fn(*args, **kwargs) once per allocation index, failing that
        allocation."""
        failed = []
        for n in range(self.SWEEP_LIMIT):
            _testcapi.set_nomemory(n, n + 1)
            try:
                fn(*args, **kwargs)
            except MemoryError:
                failed.append(n)
            finally:
                _testcapi.remove_mem_hooks()
        self.assertTrue(failed, "no allocation failure was injected")
        # A failure in the last stretch of the sweep means the call allocates
        # more than SWEEP_LIMIT times, so its deepest error paths were never
        # reached and the limit needs raising.
        self.assertLess(
            failed[-1],
            self.SWEEP_LIMIT - 50,
            f"SWEEP_LIMIT={self.SWEEP_LIMIT} too low for this case",
        )

    def test_parse(self):
        for depstr, uselist, matchall in self.PARSE_CASES:
            with self.subTest(depstr=depstr):
                kw = dict(uselist=uselist, matchall=matchall)
                expected = self._parser.parse(depstr, **kw)
                self._sweep(self._parser.parse, depstr, **kw)
                self.assertEqual(self._parser.parse(depstr, **kw), expected)

    def test_scan_atom(self):
        for s in self.ATOM_CASES:
            with self.subTest(s=s):
                expected = str(self._parser.scan_atom(s))
                self._sweep(self._parser.scan_atom, s)
                self.assertEqual(str(self._parser.scan_atom(s)), expected)

    def test_classify_use_deps(self):
        for tokens in self.USE_DEP_CASES:
            with self.subTest(tokens=tokens):
                expected = self._parser.classify_use_deps(tokens)
                self._sweep(self._parser.classify_use_deps, tokens)
                self.assertEqual(self._parser.classify_use_deps(tokens), expected)

    def test_bad_argument_types(self):
        """Argument conversion failures are error paths of their own, and no
        allocation sweep reaches them."""
        for arg in (42, None, b"dev-libs/a", ["dev-libs/a"]):
            with self.subTest(arg=arg):
                with self.assertRaises(TypeError):
                    self._parser.parse(arg)
                with self.assertRaises(TypeError):
                    self._parser.scan_atom(arg)
        # classify_use_deps() wants a sequence, and its items must be strings.
        for arg in (42, None):
            with self.subTest(arg=arg), self.assertRaises(TypeError):
                self._parser.classify_use_deps(arg)
        with self.assertRaises(TypeError):
            self._parser.classify_use_deps((42,))

    def test_atom_fast_path(self):
        """Atom() drives scan_atom() plus _c_fast_init(), so a failure here
        can also leave a partly initialized portage.dep.Atom behind."""
        for s in self.ATOM_CASES:
            with self.subTest(s=s):
                expected = Atom(s, eapi="8")
                self._sweep(Atom, s, eapi="8")
                ok, msg = _atoms_equal(Atom(s, eapi="8"), expected)
                self.assertTrue(ok, f"{s!r}: {msg}")
