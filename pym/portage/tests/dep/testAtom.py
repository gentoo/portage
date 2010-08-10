# test_isvalidatom.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import Atom
from portage.exception import InvalidAtom

class TestAtom(TestCase):
	""" A simple testcase for isvalidatom
	"""

	def testAtom(self):

		tests = [
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
		]
		
		tests_xfail = [
			( "cat/pkg[a!]", False ),
			( "cat/pkg[a-]", False ),
			( "cat/pkg[!a]", False ),
			( "cat/pkg[!a!]", False ),
			( "cat/pkg[!a-]", False ),
			( "cat/pkg[-a=]", False ),
			( "cat/pkg[-a?]", False ),
			( "cat/pkg[-a!]", False ),
			( "cat/pkg[-a-]", False ),
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
			( "*/portage:slot", True )
		]

		for atom, parts, allow_wildcard in tests:
			a = Atom(atom, allow_wildcard=allow_wildcard)
			op, cp, ver, slot, use = parts
			self.assertEqual( op, a.operator,
				msg="Atom('%s').operator == '%s'" % ( atom, a.operator ) )
			self.assertEqual( cp, a.cp,
				msg="Atom('%s').cp == '%s'" % ( atom, a.cp ) )
			if ver is not None:
				cpv = "%s-%s" % (cp, ver)
			else:
				cpv = cp
			self.assertEqual( cpv, a.cpv,
				msg="Atom('%s').cpv == '%s'" % ( atom, a.cpv ) )
			self.assertEqual( slot, a.slot,
				msg="Atom('%s').slot == '%s'" % ( atom, a.slot ) )
			if a.use:
				expected_use = str(a.use)
			else:
				expected_use = None
			self.assertEqual( use, expected_use,
				msg="Atom('%s').use == '%s'" % ( atom, a.use ) )

		for atom, allow_wildcard in tests_xfail:
			self.assertRaisesMsg(atom, InvalidAtom, Atom, atom)

	def test_violated_conditionals(self):
		test_cases = (
			("dev-libs/A", ["foo"], None, "dev-libs/A"),
			("dev-libs/A[foo]", [], None, "dev-libs/A[foo]"),
			("dev-libs/A[foo]", ["foo"], None, "dev-libs/A"),
			("dev-libs/A[foo]", [], [], "dev-libs/A[foo]"),
			("dev-libs/A[foo]", ["foo"], [], "dev-libs/A"),

			("dev-libs/A:0[foo]", ["foo"], [], "dev-libs/A:0"),

			("dev-libs/A[foo,-bar]", [], None, "dev-libs/A[foo]"),
			("dev-libs/A[-foo,bar]", [], None, "dev-libs/A[bar]"),

			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", [], [], "dev-libs/A[a,!c=]"),
			
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["a"], [], "dev-libs/A[!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["b"], [], "dev-libs/A[a,b=,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["c"], [], "dev-libs/A[a]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["d"], [], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["e"], [], "dev-libs/A[a,!e?,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["f"], [], "dev-libs/A[a,-f,!c=]"),
			
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["a"], ["a"], "dev-libs/A[!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["b"], ["b"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["c"], ["c"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["d"], ["d"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["e"], ["e"], "dev-libs/A[a,!c=]"),
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", ["f"], ["f"], "dev-libs/A[a,-f,!c=]"),
		)
		
		test_cases_xfail = (
			("dev-libs/A[a,b=,!c=,d?,!e?,-f]", [], None),
		)
		
		for atom, other_use, parent_use, expected_violated_atom in test_cases:
			a = Atom(atom)
			violated_atom = a.violated_conditionals(other_use, parent_use)
			if parent_use is None:
				fail_msg = "Atom: %s, other_use: %s, parent_use: %s, got: %s, expected: %s" % \
					(atom, " ".join(other_use), "None", str(violated_atom), expected_violated_atom)
			else:
				fail_msg = "Atom: %s, other_use: %s, parent_use: %s, got: %s, expected: %s" % \
					(atom, " ".join(other_use), " ".join(parent_use), str(violated_atom), expected_violated_atom)
			self.assertEqual(str(violated_atom), expected_violated_atom, fail_msg)

		for atom, other_use, parent_use in test_cases_xfail:
			a = Atom(atom)
			self.assertRaisesMsg(atom, InvalidAtom, \
				a.violated_conditionals, other_use, parent_use)
