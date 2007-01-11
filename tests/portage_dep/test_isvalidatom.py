# test_isvalidatom.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_atoms.py 5525 2007-01-10 13:35:03Z antarus $

from unittest import TestCase
from portage_dep import isvalidatom

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
			  ( ">~cate-gory/foo-1.0", False ),
			  ( ">~category/foo-1.0", False ),
			  ( "<~category/foo-1.0", False ),
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
