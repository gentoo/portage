# test_isvalidatom.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import isvalidatom

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
			  ( "sys-apps/portage-2.1:[foo]", False ),
			  ( "=sys-apps/portage-2.2*:foo[bar?,!baz?,!doc=,build=]", True ),
			  ( "=sys-apps/portage-2.2*:foo[doc?]", True ),
			  ( "=sys-apps/portage-2.2*:foo[!doc?]", True ),
			  ( "=sys-apps/portage-2.2*:foo[doc=]", True ),
			  ( "=sys-apps/portage-2.2*:foo[!doc=]", True ),
			  ( "=sys-apps/portage-2.2*:foo[!doc]", False ),
			  ( "=sys-apps/portage-2.2*:foo[!-doc]", False ),
			  ( "=sys-apps/portage-2.2*:foo[!-doc=]", False ),
			  ( "=sys-apps/portage-2.2*:foo[!-doc?]", False ),
			  ( "=sys-apps/portage-2.2*:foo[-doc?]", False ),
			  ( "=sys-apps/portage-2.2*:foo[-doc=]", False ),
			  ( "=sys-apps/portage-2.2*:foo[-doc!=]", False ),
			  ( "=sys-apps/portage-2.2*:foo[-doc=]", False ),
			  ( "=sys-apps/portage-2.2*:foo[bar][-baz][doc?][!build?]", False ),
			  ( "=sys-apps/portage-2.2*:foo[bar,-baz,doc?,!build?]", True ),
			  ( "=sys-apps/portage-2.2*:foo[bar,-baz,doc?,!build?,]", False ),
			  ( "=sys-apps/portage-2.2*:foo[,bar,-baz,doc?,!build?]", False ),
			  ( "=sys-apps/portage-2.2*:foo[bar,-baz][doc?,!build?]", False ),
			  ( "=sys-apps/portage-2.2*:foo[bar][doc,build]", False ),
			  ( ">~cate-gory/foo-1.0", False ),
			  ( ">~category/foo-1.0", False ),
			  ( "<~category/foo-1.0", False ),
			  ( "###cat/foo-1.0", False ),
			  ( "~sys-apps/portage", False ),
			  ( "portage", False ),
			  ( "=portage", False ),
			  ( ">=portage-2.1", False ),
			  ( "~portage-2.1", False ),
			  ( "=portage-2.1*", False ),
			  ( "null/portage", True ),
			  ( "null/portage*:0", False ),
			  ( ">=null/portage-2.1", True ),
			  ( ">=null/portage", False ),
			  ( ">null/portage", False ),
			  ( "=null/portage*", False ),
			  ( "=null/portage", False ),
			  ( "~null/portage", False ),
			  ( "<=null/portage", False ),
			  ( "<null/portage", False ),
			  ( "~null/portage-2.1", True ),
			  ( "=null/portage-2.1*", True ),
			  ( "null/portage-2.1*", False ),
			  ( "app-doc/php-docs-20071125", False),
			  ( "app-doc/php-docs-20071125-r2", False),
			  ( "=foo/bar-1-r1-1-r1", False ),
			  ( "foo/-z-1", False ),

			# These are invalid because pkg name must not end in hyphen
			# followed by numbers
			  ( "=foo/bar-1-r1-1-r1", False ),
			  ( "=foo/bar-123-1", False ),
			  ( "=foo/bar-123-1*", False ),
			  ( "foo/bar-123", False ),
			  ( "=foo/bar-123-1-r1", False ),
			  ( "=foo/bar-123-1-r1*", False ),
			  ( "foo/bar-123-r1", False ),
			  ( "foo/bar-1", False ),

			  ( "=foo/bar--baz-1-r1", True ),
			  ( "=foo/bar-baz--1-r1", True ),
			  ( "=foo/bar-baz---1-r1", True ),
			  ( "=foo/bar-baz---1", True ),
			  ( "=foo/bar-baz-1--r1", False ),
			  ( "games-strategy/ufo2000", True ),
			  ( "~games-strategy/ufo2000-0.1", True ),
			  ( "=media-libs/x264-20060810", True ),
			  ( "foo/b", True ),
			  ( "app-text/7plus", True ),
			  ( "foo/666", True ),
			  ( "=dev-libs/poppler-qt3-0.11*", True ),
		]

		for test in tests:
			if test[1]:
				atom_type = "valid"
			else:
				atom_type = "invalid"
			self.assertEqual( bool(isvalidatom( test[0] )), test[1],
				msg="isvalidatom(%s) != %s" % ( test[0], test[1] ) )
