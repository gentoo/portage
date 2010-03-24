# Copyright 2008 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import paren_reduce
from portage.dbapi.porttree import _src_uri_validate
from portage.exception import InvalidDependString

class SrcUri(TestCase):

	def testSrcUri(self):

		tests = [
			( "0", "http://foo/bar -> blah.tbz2"                     , False ),
			( "1", "http://foo/bar -> blah.tbz2"                     , False ),
			( "2", "|| ( http://foo/bar -> blah.tbz2 )"              , False ),
			( "2", "http://foo/bar -> blah.tbz2"                     , True  ),
			( "2", "foo? ( http://foo/bar -> blah.tbz2 )"            , True  ),
			( "2", "http://foo/bar -> foo? ( ftp://foo/a )"          , False ),
			( "2", "http://foo/bar -> bar.tbz2 foo? ( ftp://foo/a )" , True  ),
			( "2", "http://foo/bar blah.tbz2 ->"                     , False ),
			( "2", "-> http://foo/bar blah.tbz2 )"                   , False ),
			( "2", "http://foo/bar ->"                               , False ),
			( "2", "http://foo/bar -> foo? ( http://foo.com/foo )"   , False ),
			( "2", "foo? ( http://foo/bar -> ) blah.tbz2"            , False ),
			( "2", "http://foo/bar -> foo/blah.tbz2"                 , False ),
			( "2", "http://foo.com/foo http://foo/bar -> blah.tbz2"  , True  ),
		]

		for eapi, src_uri, valid in tests:
			try:
				_src_uri_validate("cat/pkg-1", eapi, paren_reduce(src_uri))
			except InvalidDependString:
				self.assertEqual(valid, False)
			else:
				self.assertEqual(valid, True)
