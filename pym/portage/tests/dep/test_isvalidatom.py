# test_isvalidatom.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from unittest import TestCase
from portage.dep import isvalidatom
import portage.dep
portage.dep._dep_check_strict = True

class IsValidAtom(TestCase):
	""" A simple testcase for isvalidatom
	"""

	def testIsValidAtom(self):
		
		tests = [ ( "sys-apps/portage", True ),
			  ( "=sys-apps/portage-2.1", True ),
		 	  ( "=sys-apps/portage-2.1*", True ),
			  ( ">=sys-apps/portage-2.1", True ),
			  ( "<=sys-apps/portage-2.1", True ),
			  ( ">sys-apps/portage-2.1", True ),
			  ( "<sys-apps/portage-2.1", True ),
			  ( "~sys-apps/portage-2.1", True ),
			  ( "sys-apps/portage:foo", True ),
			  ( "sys-apps/portage-2.1:foo", False ),
			  ( "sys-apps/portage-2.1:", False ),
			  ( ">~cate-gory/foo-1.0", True ),
			  ( ">~category/foo-1.0", True ),
			  ( "<~category/foo-1.0", True ),
			  ( "###cat/foo-1.0", False ),
			  ( "~sys-apps/portage", False ),
			  ( "portage", False ) ]

		for test in tests:
			if test[1]:
				atom_type = "valid"
			else:
				atom_type = "invalid"
			self.assertEqual( bool(isvalidatom( test[0] )), test[1],
				msg="isvalidatom(%s) != %s" % ( test[0], test[1] ) )
