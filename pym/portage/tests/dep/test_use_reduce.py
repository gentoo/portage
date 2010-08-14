# Copyright 2009-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.exception import InvalidDependString
from portage.dep import use_reduce

class UseReduceTestCase(object):
	def __init__(self, deparray, uselist=[], masklist=[], \
		matchall=0, excludeall=[], is_src_uri=False, \
		allow_src_uri_file_renames=False, opconvert=False, expected_result=None):
		self.deparray = deparray
		self.uselist = uselist
		self.masklist = masklist
		self.matchall = matchall
		self.excludeall = excludeall
		self.is_src_uri = is_src_uri
		self.allow_src_uri_file_renames = allow_src_uri_file_renames
		self.opconvert = opconvert
		self.expected_result = expected_result

	def run(self):
		return use_reduce(self.deparray, self.uselist, self.masklist, \
			self.matchall, self.excludeall, self.is_src_uri, self.allow_src_uri_file_renames, self.opconvert)
				
class UseReduce(TestCase):

	def testUseReduce(self):

		test_cases = (
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist = ["a", "b", "c", "d"],
				expected_result = ["A", "B"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist = ["a", "b", "c"],
				expected_result = ["A", "B", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist = ["b", "c"],
				expected_result = ["B", "D"]
				),

			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall = True,
				expected_result = ["A", "B", "C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				masklist = ["a", "c"],
				expected_result = ["C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall = True,
				masklist = ["a", "c"],
				expected_result = ["B", "C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist = ["a", "b"],
				masklist = ["a", "c"],
				expected_result = ["B", "C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				excludeall = ["a", "c"],
				expected_result = ["D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist = ["b"],
				excludeall = ["a", "c"],
				expected_result = ["B", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall = True,
				excludeall = ["a", "c"],
				expected_result = ["A", "B", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall = True,
				excludeall = ["a", "c"],
				masklist = ["b"],
				expected_result = ["A", "D"]
				),

			
			UseReduceTestCase(
				"a? ( b? ( AB ) )",
				uselist = ["a", "b"],
				expected_result = ["AB"]
				),
			UseReduceTestCase(
				"a? ( b? ( AB ) C )",
				uselist = ["a"],
				expected_result = ["C"]
				),
			UseReduceTestCase(
				"a? ( b? ( || ( AB CD ) ) )",
				uselist = ["a", "b"],
				expected_result = ["||", ["AB", "CD"]]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( A ) b? ( B ) ) )",
				uselist = ["a", "b"],
				expected_result = ["||", ["A", "B"]]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( A ) b? ( B ) ) )",
				uselist = ["a"],
				expected_result = ["A"]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( A ) b? ( B ) ) )",
				uselist = [],
				expected_result = []
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist = [],
				expected_result = []
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist = ["a"],
				expected_result = ["A"]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist = ["b"],
				expected_result = ["B"]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist = ["c"],
				expected_result = []
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist = ["a", "c"],
				expected_result = ["||", [ "A", "C"]]
				),
			
			#paren_reduce tests
			UseReduceTestCase(
				"A",
				expected_result = ["A"]),
			UseReduceTestCase(
				"( A )",
				expected_result = ["A"]),
			UseReduceTestCase(
				"|| ( A B )",
				expected_result = [ "||", ["A", "B"] ]),
			UseReduceTestCase(
				"|| ( A || ( B C ) )",
				expected_result = [ "||", ["A", "||", ["B", "C"]]]),
			UseReduceTestCase(
				"|| ( A || ( B C D ) )",
				expected_result = [ "||", ["A", "||", ["B", "C", "D"]] ]),
			UseReduceTestCase(
				"|| ( A || ( B || ( C D ) E ) )",
				expected_result = [ "||", ["A", "||", ["B", "||", ["C", "D"], "E"]] ]),
			UseReduceTestCase(
				"( || ( ( ( A ) B ) ) )",
				expected_result = [ "||", ["A", "B"] ] ),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				expected_result = [ "||", ["A", "B"] ]),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				expected_result = [ "||", ["A", "B"] ]),
			UseReduceTestCase(
				"|| ( A )",
				expected_result = ["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				expected_result = ["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				uselist = ["foo"],
				expected_result = [ "||", ["A", "B"] ]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				expected_result = []),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				uselist = ["foo", "bar"],
				expected_result = [ "||", [ "A", "B" ] ]),
			UseReduceTestCase(
				"A || ( ) foo? ( ) B",
				expected_result = ["A", "B"]),
			UseReduceTestCase(
				"|| ( A ) || ( B )",
				expected_result = ["A", "B"]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				expected_result = []),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				uselist = ["foo"],
				expected_result = ["A", "B"]),
			
			#SRC_URI stuff
			UseReduceTestCase(
				"http://foo/bar -> blah.tbz2",
				is_src_uri = True,
				allow_src_uri_file_renames = True,
				expected_result = ["http://foo/bar", "->", "blah.tbz2"]),
			UseReduceTestCase(
				"foo? ( http://foo/bar -> blah.tbz2 )",
				uselist = [],
				is_src_uri = True,
				allow_src_uri_file_renames = True,
				expected_result = []),
			UseReduceTestCase(
				"foo? ( http://foo/bar -> blah.tbz2 )",
				uselist = ["foo"],
				is_src_uri = True,
				allow_src_uri_file_renames = True,
				expected_result = ["http://foo/bar", "->", "blah.tbz2"]),
			UseReduceTestCase(
				"http://foo/bar -> bar.tbz2 foo? ( ftp://foo/a )",
				uselist = [],
				is_src_uri = True,
				allow_src_uri_file_renames = True,
				expected_result = ["http://foo/bar", "->", "bar.tbz2"]),
			UseReduceTestCase(
				"http://foo/bar -> bar.tbz2 foo? ( ftp://foo/a )",
				uselist = ["foo"],
				is_src_uri = True,
				allow_src_uri_file_renames = True,
				expected_result = ["http://foo/bar", "->", "bar.tbz2", "ftp://foo/a"]),
			UseReduceTestCase(
				"http://foo.com/foo http://foo/bar -> blah.tbz2",
				uselist = ["foo"],
				is_src_uri = True,
				allow_src_uri_file_renames = True,
				expected_result = ["http://foo.com/foo", "http://foo/bar", "->", "blah.tbz2"]),

			#opconvert tests
			UseReduceTestCase(
				"A",
				opconvert = True,
				expected_result = ["A"]),
			UseReduceTestCase(
				"( A )",
				opconvert = True,
				expected_result = ["A"]),
			UseReduceTestCase(
				"|| ( A B )",
				opconvert = True,
				expected_result = [ ["||", "A", "B"] ]),
			UseReduceTestCase(
				"|| ( A || ( B C ) )",
				opconvert = True,
				expected_result = [ ["||", "A", ["||", "B", "C"]] ]),
			UseReduceTestCase(
				"|| ( A || ( B C D ) )",
				opconvert = True,
				expected_result = [ ["||", "A", ["||", "B", "C", "D"]] ]),
			UseReduceTestCase(
				"|| ( A || ( B || ( C D ) E ) )",
				expected_result = [ "||", ["A", "||", ["B", "||", ["C", "D"], "E"]] ]),
			UseReduceTestCase(
				"( || ( ( ( A ) B ) ) )",
				opconvert = True,
				expected_result = [ ["||", "A", "B"] ] ),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				opconvert = True,
				expected_result = [ ["||", "A", "B"] ]),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				opconvert = True,
				expected_result = [ ["||", "A", "B"] ]),
			UseReduceTestCase(
				"|| ( A )",
				opconvert = True,
				expected_result = ["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				expected_result = ["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				uselist = ["foo"],
				opconvert = True,
				expected_result = [ ["||", "A", "B"] ]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				opconvert = True,
				expected_result = []),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				uselist = ["foo", "bar"],
				opconvert = True,
				expected_result = [ ["||", "A", "B"] ]),
			UseReduceTestCase(
				"A || ( ) foo? ( ) B",
				opconvert = True,
				expected_result = ["A", "B"]),
			UseReduceTestCase(
				"|| ( A ) || ( B )",
				opconvert = True,
				expected_result = ["A", "B"]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				opconvert = True,
				expected_result = []),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				uselist = ["foo"],
				opconvert = True,
				expected_result = ["A", "B"]),
		)
		
		test_cases_xfail = (
			UseReduceTestCase("? ( A )"),
			UseReduceTestCase("!? ( A )"),
			UseReduceTestCase("( A"),
			UseReduceTestCase("A )"),
			UseReduceTestCase("||( A B )"),
			UseReduceTestCase("|| (A B )"),
			UseReduceTestCase("|| ( A B)"),
			UseReduceTestCase("|| ( A B"),
			UseReduceTestCase("|| A B )"),
			UseReduceTestCase("|| A B"),
			UseReduceTestCase("|| ( A B ) )"),
			UseReduceTestCase("|| || B C"),
			UseReduceTestCase("|| ( A B || )"),
			UseReduceTestCase("a? A"),
			UseReduceTestCase("( || ( || || ( A ) foo? ( B ) ) )"),
			UseReduceTestCase("( || ( || bar? ( A ) foo? ( B ) ) )"),
			
			#SRC_URI stuff
			UseReduceTestCase("http://foo/bar -> blah.tbz2", is_src_uri = True, allow_src_uri_file_renames = False),
			UseReduceTestCase("|| ( http://foo/bar -> blah.tbz2 )", is_src_uri = True, allow_src_uri_file_renames = True),
			UseReduceTestCase("http://foo/bar -> foo? ( ftp://foo/a )", is_src_uri = True, allow_src_uri_file_renames = True),
			UseReduceTestCase("http://foo/bar blah.tbz2 ->", is_src_uri = True, allow_src_uri_file_renames = True),
			UseReduceTestCase("-> http://foo/bar blah.tbz2 )", is_src_uri = True, allow_src_uri_file_renames = True),
			UseReduceTestCase("http://foo/bar ->", is_src_uri = True, allow_src_uri_file_renames = True),
			UseReduceTestCase("http://foo/bar -> foo? ( http://foo.com/foo )", is_src_uri = True, allow_src_uri_file_renames = True),
			UseReduceTestCase("foo? ( http://foo/bar -> ) blah.tbz2", is_src_uri = True, allow_src_uri_file_renames = True),
			UseReduceTestCase("http://foo/bar -> foo/blah.tbz2", is_src_uri = True, allow_src_uri_file_renames = True),
		)

		for test_case in test_cases:
			self.assertEqual(test_case.run(), test_case.expected_result)

		for test_case in test_cases_xfail:
			self.assertRaisesMsg(test_case.deparray, InvalidDependString, test_case.run)
