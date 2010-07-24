# test_isvalidatom.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import Atom
import portage.dep
portage.dep._dep_check_strict = True

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
			self.assertRaisesMsg(atom, portage.exception.InvalidAtom, Atom, atom)
