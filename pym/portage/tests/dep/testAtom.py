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
			  ( "=sys-apps/portage-2.1-r1:0[doc]",
				('=',  'sys-apps/portage', '2.1-r1', '0', '[doc]') ),
			  ( "=sys-apps/portage-2.1-r1*:0[doc]",
				('=*',  'sys-apps/portage', '2.1-r1', '0', '[doc]') ),
			  ( "sys-apps/portage:0[doc]",
				(None,  'sys-apps/portage', None, '0', '[doc]') ),
		]

		for atom, parts in tests:
			a = Atom(atom)
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
			self.assertEqual( use, str(a.use),
				msg="Atom('%s').use == '%s'" % ( atom, a.use ) )
