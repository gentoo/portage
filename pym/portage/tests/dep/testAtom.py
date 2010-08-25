# Copyright 2006, 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import Atom
from portage.exception import InvalidAtom

class TestAtom(TestCase):

	def testAtom(self):

		tests = (
			( "=sys-apps/portage-2.1-r1:0[doc,a=,!b=,c?,!d?,-e]",
				('=',  'sys-apps/portage', '2.1-r1', '0', '[doc,a=,!b=,c?,!d?,-e]'), False ),
			( "=sys-apps/portage-2.1-r1*:0[doc]",
				('=*',  'sys-apps/portage', '2.1-r1', '0', '[doc]'), False ),
			( "sys-apps/portage:0[doc]",
				(None,  'sys-apps/portage', None, '0', '[doc]'), False ),
			( "sys-apps/portage:0[doc]",
				(None,  'sys-apps/portage', None, '0', '[doc]'), False ),
			( "*/*",
				(None,  '*/*', None, None, None), True ),
			( "sys-apps/*",
				(None,  'sys-apps/*', None, None, None), True ),
			( "*/portage",
				(None,  '*/portage', None, None, None), True ),
			( "s*s-*/portage:1",
				(None,  's*s-*/portage', None, '1', None), True ),
			( "*/po*ge:2",
				(None,  '*/po*ge', None, '2', None), True ),
			( "!dev-libs/A",
				(None,  'dev-libs/A', None, None, None), True ),
			( "!!dev-libs/A",
				(None,  'dev-libs/A', None, None, None), True ),
			( "!!dev-libs/A",
				(None,  'dev-libs/A', None, None, None), True ),
			( "dev-libs/A[foo(+)]",
				(None,  'dev-libs/A', None, None, "[foo(+)]"), True ),
			( "dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]",
				(None,  'dev-libs/A', None, None, "[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]"), True ),
			( "dev-libs/A:2[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]",
				(None,  'dev-libs/A', None, "2", "[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]"), True ),
		)
		
		tests_xfail = (
			( Atom("sys-apps/portage"), False ),
			( "cat/pkg[a!]", False ),
			( "cat/pkg[!a]", False ),
			( "cat/pkg[!a!]", False ),
			( "cat/pkg[!a-]", False ),
			( "cat/pkg[-a=]", False ),
			( "cat/pkg[-a?]", False ),
			( "cat/pkg[-a!]", False ),
			( "cat/pkg[=a]", False ),
			( "cat/pkg[=a=]", False ),
			( "cat/pkg[=a?]", False ),
			( "cat/pkg[=a!]", False ),
			( "cat/pkg[=a-]", False ),
			( "cat/pkg[?a]", False ),
			( "cat/pkg[?a=]", False ),
			( "cat/pkg[?a?]", False ),
			( "cat/pkg[?a!]", False ),
			( "cat/pkg[?a-]", False ),
			( "sys-apps/portage[doc]:0", False ),
			( "*/*", False ),
			( "sys-apps/*", False ),
			( "*/portage", False ),
			( "*/**", True ),
			( "*/portage[use]", True ),
			( "cat/pkg[a()]", False ),
			( "cat/pkg[a(]", False ),
			( "cat/pkg[a)]", False ),
			( "cat/pkg[a(,b]", False ),
			( "cat/pkg[a),b]", False ),
			( "cat/pkg[a(*)]", False ),
			( "cat/pkg[a(*)]", True ),
			( "cat/pkg[a(+-)]", False ),
			( "cat/pkg[a()]", False ),
			( "cat/pkg[(+)a]", False ),
			( "cat/pkg[a=(+)]", False ),
			( "cat/pkg[!(+)a=]", False ),
			( "cat/pkg[!a=(+)]", False ),
			( "cat/pkg[a?(+)]", False ),
			( "cat/pkg[!a?(+)]", False ),
			( "cat/pkg[!(+)a?]", False ),
			( "cat/pkg[-(+)a]", False ),
			( "cat/pkg[a(+),-a]", False ),
			( "cat/pkg[a(-),-a]", False ),
			( "cat/pkg[-a,a(+)]", False ),
			( "cat/pkg[-a,a(-)]", False ),
			( "cat/pkg[-a(+),a(-)]", False ),
			( "cat/pkg[-a(-),a(+)]", False ),
		)

		for atom, parts, allow_wildcard in tests:
			a = Atom(atom, allow_wildcard=allow_wildcard)
			op, cp, ver, slot, use = parts
			self.assertEqual( op, a.operator,
				msg="Atom('%s').operator = %s == '%s'" % ( atom, a.operator, op ) )
			self.assertEqual( cp, a.cp,
				msg="Atom('%s').cp = %s == '%s'" % ( atom, a.cp, cp ) )
			if ver is not None:
				cpv = "%s-%s" % (cp, ver)
			else:
				cpv = cp
			self.assertEqual( cpv, a.cpv,
				msg="Atom('%s').cpv = %s == '%s'" % ( atom, a.cpv, cpv ) )
			self.assertEqual( slot, a.slot,
				msg="Atom('%s').slot = %s == '%s'" % ( atom, a.slot, slot ) )
			if a.use:
				returned_use = str(a.use)
			else:
				returned_use = None
			self.assertEqual( use, returned_use,
				msg="Atom('%s').use = %s == '%s'" % ( atom, returned_use, use ) )

		for atom, allow_wildcard in tests_xfail:
			self.assertRaisesMsg(atom, (InvalidAtom, TypeError), Atom, atom, allow_wildcard=allow_wildcard)

	def test_intersects(self):
		test_cases = (
			("dev-libs/A", "dev-libs/A", True),
			("dev-libs/A", "dev-libs/B", False),
			("dev-libs/A", "sci-libs/A", False),
			("dev-libs/A[foo]", "sci-libs/A[bar]", False),
			("dev-libs/A[foo(+)]", "sci-libs/A[foo(-)]", False),
			("=dev-libs/A-1", "=dev-libs/A-1-r1", False),
			("~dev-libs/A-1", "=dev-libs/A-1", False),
			("=dev-libs/A-1:1", "=dev-libs/A-1", True),
			("=dev-libs/A-1:1", "=dev-libs/A-1:1", True),
			("=dev-libs/A-1:1", "=dev-libs/A-1:2", False),
		)

		for atom, other, expected_result in test_cases:
			self.assertEqual(Atom(atom).intersects(Atom(other)), expected_result, \
				"%s and %s should intersect: %s" % (atom, other, expected_result))

	def test_violated_conditionals(self):
		test_cases = (
			("dev-libs/A", ["foo"], ["foo"], None, "dev-libs/A"),
			("dev-libs/A[foo]", [], ["foo"], None, "dev-libs/A[foo]"),
			("dev-libs/A[foo]", ["foo"], ["foo"], None, "dev-libs/A"),
			("dev-libs/A[foo]", [], ["foo"], [], "dev-libs/A[foo]"),
			("dev-libs/A[foo]", ["foo"], ["foo"], [], "dev-libs/A"),

			("dev-libs/A:0[foo]", ["foo"], ["foo"], [], "dev-libs/A:0"),

			("dev-libs/A[foo,-bar]", [], ["foo", "bar"], None, "dev-libs/A[foo]"),
			("dev-libs/A[-foo,bar]", [], ["foo", "bar"], None, "dev-libs/A[bar]"),

			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", [], ["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[a,!c=]"),

			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["a"], ["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["b"], ["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[a,b=,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["c"], ["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[a]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["d"], ["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["e"], ["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[a,!c=,!e?]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["f"], ["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[a,!c=,-f]"),

			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["a"], ["a", "b", "c", "d", "e", "f"], ["a"], "dev-libs/A[!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["b"], ["a", "b", "c", "d", "e", "f"], ["b"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["c"], ["a", "b", "c", "d", "e", "f"], ["c"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["d"], ["a", "b", "c", "d", "e", "f"], ["d"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["e"], ["a", "b", "c", "d", "e", "f"], ["e"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["f"], ["a", "b", "c", "d", "e", "f"], ["f"], "dev-libs/A[a,!c=,-f]"),

			("dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", ["a"], ["a", "b", "c", "d", "e", "f"], ["a"], "dev-libs/A[!c(+)=]"),
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", ["b"], ["a", "b", "c", "d", "e", "f"], ["b"], "dev-libs/A[a(-),!c(-)=]"),
			("dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", ["c"], ["a", "b", "c", "d", "e", "f"], ["c"], "dev-libs/A[a(+),!c(+)=]"),
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", ["d"], ["a", "b", "c", "d", "e", "f"], ["d"], "dev-libs/A[a(-),!c(-)=]"),
			("dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", ["e"], ["a", "b", "c", "d", "e", "f"], ["e"], "dev-libs/A[a(+),!c(+)=]"),
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", ["f"], ["a", "b", "c", "d", "e", "f"], ["f"], "dev-libs/A[a(-),!c(-)=,-f(+)]"),

			("dev-libs/A[a(+),b(+)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", ["a"], ["a"], ["a"], "dev-libs/A[b(+)=,!e(+)?]"),
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", ["b"], ["b"], ["b"], "dev-libs/A[a(-),!c(-)=,-f(+)]"),
			("dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", ["c"], ["c"], ["c"], "dev-libs/A[!c(+)=,!e(+)?]"),
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", ["d"], ["d"], ["d"], "dev-libs/A[a(-),b(+)=,!c(-)=,-f(+)]"),
			("dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", ["e"], ["e"], ["e"], "dev-libs/A"),
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", ["f"], ["f"], ["f"], "dev-libs/A[a(-),b(+)=,!c(-)=,-f(+)]"),

			#Some more test cases to trigger all remaining code paths
			("dev-libs/B[x?]", [], ["x"], ["x"], "dev-libs/B[x?]"),
			("dev-libs/B[x(+)?]", [], [], ["x"], "dev-libs/B"),
			("dev-libs/B[x(-)?]", [], [], ["x"], "dev-libs/B[x(-)?]"),

			("dev-libs/C[x=]", [], ["x"], ["x"], "dev-libs/C[x=]"),
			("dev-libs/C[x(+)=]", [], [], ["x"], "dev-libs/C"),
			("dev-libs/C[x(-)=]", [], [], ["x"], "dev-libs/C[x(-)=]"),

			("dev-libs/D[!x=]", [], ["x"], ["x"], "dev-libs/D"),
			("dev-libs/D[!x(+)=]", [], [], ["x"], "dev-libs/D[!x(+)=]"),
			("dev-libs/D[!x(-)=]", [], [], ["x"], "dev-libs/D"),

			#Missing IUSE test cases
			("dev-libs/B[x]", [], [], [], "dev-libs/B[x]"),
			("dev-libs/B[-x]", [], [], [], "dev-libs/B[-x]"),
			("dev-libs/B[x?]", [], [], [], "dev-libs/B[x?]"),
			("dev-libs/B[x=]", [], [], [], "dev-libs/B[x=]"),
			("dev-libs/B[!x=]", [], [], ["x"], "dev-libs/B[!x=]"),
			("dev-libs/B[!x?]", [], [], ["x"], "dev-libs/B[!x?]"),
		)
		
		test_cases_xfail = (
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", [], ["a", "b", "c", "d", "e", "f"], None),
		)

		class use_flag_validator(object):
			def __init__(self, iuse):
				self.iuse = iuse

			def is_valid_flag(self, flag):
				return flag in iuse

		for atom, other_use, iuse, parent_use, expected_violated_atom in test_cases:
			a = Atom(atom)
			validator = use_flag_validator(iuse)
			violated_atom = a.violated_conditionals(other_use, validator.is_valid_flag, parent_use)
			if parent_use is None:
				fail_msg = "Atom: %s, other_use: %s, iuse: %s, parent_use: %s, got: %s, expected: %s" % \
					(atom, " ".join(other_use), " ".join(iuse), "None", str(violated_atom), expected_violated_atom)
			else:
				fail_msg = "Atom: %s, other_use: %s, iuse: %s, parent_use: %s, got: %s, expected: %s" % \
					(atom, " ".join(other_use), " ".join(iuse), " ".join(parent_use), str(violated_atom), expected_violated_atom)
			self.assertEqual(str(violated_atom), expected_violated_atom, fail_msg)

		for atom, other_use, iuse, parent_use in test_cases_xfail:
			a = Atom(atom)
			validator = use_flag_validator(iuse)
			self.assertRaisesMsg(atom, InvalidAtom, \
				a.violated_conditionals, other_use, validator.is_valid_flag, parent_use)

	def test_evaluate_conditionals(self):
		test_cases = (
			("dev-libs/A[foo]", [], "dev-libs/A[foo]"),
			("dev-libs/A[foo]", ["foo"], "dev-libs/A[foo]"),

			("dev-libs/A:0[foo=]", ["foo"], "dev-libs/A:0[foo]"),

			("dev-libs/A[foo,-bar]", [], "dev-libs/A[foo,-bar]"),
			("dev-libs/A[-foo,bar]", [], "dev-libs/A[-foo,bar]"),

			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", [], "dev-libs/A[a,-b,c,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["a"], "dev-libs/A[a,-b,c,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["b"], "dev-libs/A[a,b,c,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["c"], "dev-libs/A[a,-b,-c,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["d"], "dev-libs/A[a,-b,c,d,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["e"], "dev-libs/A[a,-b,c,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["f"], "dev-libs/A[a,-b,c,-e,-f]"),
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", ["d"], "dev-libs/A[a(-),-b(+),c(-),d(+),-e(-),-f(+)]"),
			("dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", ["f"], "dev-libs/A[a(+),-b(-),c(+),-e(+),-f(-)]"),
		)

		for atom, use, expected_atom in test_cases:
			a = Atom(atom)
			b = a.evaluate_conditionals(use)
			self.assertEqual(str(b), expected_atom)
			self.assertEqual(str(b.unevaluated_atom), atom)

	def test__eval_qa_conditionals(self):
		test_cases = (
			("dev-libs/A[foo]", [], [], "dev-libs/A[foo]"),
			("dev-libs/A[foo]", ["foo"], [], "dev-libs/A[foo]"),
			("dev-libs/A[foo]", [], ["foo"], "dev-libs/A[foo]"),

			("dev-libs/A:0[foo]", [], [], "dev-libs/A:0[foo]"),
			("dev-libs/A:0[foo]", ["foo"], [], "dev-libs/A:0[foo]"),
			("dev-libs/A:0[foo]", [], ["foo"], "dev-libs/A:0[foo]"),
			("dev-libs/A:0[foo=]", [], ["foo"], "dev-libs/A:0[foo]"),

			("dev-libs/A[foo,-bar]", ["foo"], ["bar"], "dev-libs/A[foo,-bar]"),
			("dev-libs/A[-foo,bar]", ["foo", "bar"], [], "dev-libs/A[-foo,bar]"),

			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["a", "b", "c"], [], "dev-libs/A[a,-b,c,d,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", [], ["a", "b", "c"], "dev-libs/A[a,b,-c,d,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["d", "e", "f"], [], "dev-libs/A[a,b,-b,c,-c,-e,-f]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", [], ["d", "e", "f"], "dev-libs/A[a,b,-b,c,-c,d,-f]"),
			
			("dev-libs/A[a(-),b(+)=,!c(-)=,d(+)?,!e(-)?,-f(+)]", \
				["a", "b", "c", "d", "e", "f"], [], "dev-libs/A[a(-),-b(+),c(-),-e(-),-f(+)]"),
			("dev-libs/A[a(+),b(-)=,!c(+)=,d(-)?,!e(+)?,-f(-)]", \
				[], ["a", "b", "c", "d", "e", "f"], "dev-libs/A[a(+),b(-),-c(+),d(-),-f(-)]"),
		)

		for atom, use_mask, use_force, expected_atom in test_cases:
			a = Atom(atom)
			b = a._eval_qa_conditionals(use_mask, use_force)
			self.assertEqual(str(b), expected_atom)
			self.assertEqual(str(b.unevaluated_atom), atom)
