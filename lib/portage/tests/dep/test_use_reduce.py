# Copyright 2009-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.exception import InvalidDependString
from portage.dep import Atom, use_reduce

class UseReduceTestCase:
	def __init__(self, deparray, uselist=[], masklist=[],
	             matchall=0, excludeall=[], is_src_uri=False,
	             eapi='0', opconvert=False, flat=False, expected_result=None,
	             is_valid_flag=None, token_class=None, subset=None):
		self.deparray = deparray
		self.uselist = uselist
		self.masklist = masklist
		self.matchall = matchall
		self.excludeall = excludeall
		self.is_src_uri = is_src_uri
		self.eapi = eapi
		self.opconvert = opconvert
		self.flat = flat
		self.is_valid_flag = is_valid_flag
		self.token_class = token_class
		self.subset = subset
		self.expected_result = expected_result

	def run(self):
		try:
			return use_reduce(self.deparray, self.uselist, self.masklist,
				self.matchall, self.excludeall, self.is_src_uri, self.eapi,
				self.opconvert, self.flat, self.is_valid_flag, self.token_class,
				subset=self.subset)
		except InvalidDependString as e:
			raise InvalidDependString("%s: %s" % (e, self.deparray))

class UseReduce(TestCase):

	def always_true(self, ununsed_parameter):
		return True

	def always_false(self, ununsed_parameter):
		return False

	def testUseReduce(self):

		EAPI_WITH_SRC_URI_ARROWS = "2"
		EAPI_WITHOUT_SRC_URI_ARROWS = "0"

		test_cases = (
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist=["a", "b", "c", "d"],
				expected_result=["A", "B"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist=["a", "b", "c", "d"],
				subset=["b"],
				expected_result=["B"]
				),
			UseReduceTestCase(
				"bar? ( || ( foo bar? ( baz ) ) )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=['||', ['foo', 'baz']]
				),
			UseReduceTestCase(
				"bar? ( foo bar? ( baz ) foo )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=['foo', 'baz', 'foo']
				),
			UseReduceTestCase(
				"|| ( ( a b ) ( c d ) )",
				uselist=[],
				subset=["bar"],
				expected_result=[]
				),
			UseReduceTestCase(
				"|| ( ( a b ) ( bar? ( c d ) e f ) )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=['c', 'd']
				),
			UseReduceTestCase(
				"( a b ) ( c d bar? ( e f baz? ( g h ) ) )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=['e', 'f']
				),
			UseReduceTestCase(
				"( a b ) ( c d bar? ( e f baz? ( g h ) ) )",
				uselist=["bar", "baz"],
				subset=["bar"],
				expected_result=['e', 'f', 'g', 'h']
				),
			UseReduceTestCase(
				"( bar? ( a b ) ( bar? ( c d ) ) ) ( e f )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=['a', 'b', 'c', 'd']
				),
			UseReduceTestCase(
				"|| ( foo bar? ( baz ) )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=["baz"]
				),
			UseReduceTestCase(
				"|| ( || ( bar? ( a || ( b c || ( d e ) ) ) ) )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=['a', '||', ['b', 'c', 'd', 'e']]
				),
			UseReduceTestCase(
				"|| ( || ( bar? ( a || ( ( b c ) ( d e ) ) ) ) )",
				uselist=["bar"],
				subset=["bar"],
				expected_result=['a', '||', [['b', 'c'], ['d', 'e']]]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist=["a", "b", "c"],
				expected_result=["A", "B", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist=["b", "c"],
				expected_result=["B", "D"]
				),

			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall=True,
				expected_result=["A", "B", "C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				masklist=["a", "c"],
				expected_result=["C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall=True,
				masklist=["a", "c"],
				expected_result=["B", "C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist=["a", "b"],
				masklist=["a", "c"],
				expected_result=["B", "C", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				excludeall=["a", "c"],
				expected_result=["D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				uselist=["b"],
				excludeall=["a", "c"],
				expected_result=["B", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall=True,
				excludeall=["a", "c"],
				expected_result=["A", "B", "D"]
				),
			UseReduceTestCase(
				"a? ( A ) b? ( B ) !c? ( C ) !d? ( D )",
				matchall=True,
				excludeall=["a", "c"],
				masklist=["b"],
				expected_result=["A", "D"]
				),

			UseReduceTestCase(
				"a? ( b? ( AB ) )",
				uselist=["a", "b"],
				expected_result=["AB"]
				),
			UseReduceTestCase(
				"a? ( b? ( AB ) C )",
				uselist=["a"],
				expected_result=["C"]
				),
			UseReduceTestCase(
				"a? ( b? ( || ( AB CD ) ) )",
				uselist=["a", "b"],
				expected_result=["||", ["AB", "CD"]]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( A ) b? ( B ) ) )",
				uselist=["a", "b"],
				expected_result=["||", ["A", "B"]]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( A ) b? ( B ) ) )",
				uselist=["a"],
				expected_result=["A"]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( A ) b? ( B ) ) )",
				uselist=[],
				expected_result=[]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist=[],
				expected_result=[]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist=["a"],
				expected_result=["A"]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist=["b"],
				expected_result=["B"]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist=["c"],
				expected_result=[]
				),
			UseReduceTestCase(
				"|| ( || ( a? ( || ( A c? ( C ) ) ) b? ( B ) ) )",
				uselist=["a", "c"],
				expected_result=["||", ["A", "C"]]
				),

			# paren_reduce tests
			UseReduceTestCase(
				"A",
				expected_result=["A"]),
			UseReduceTestCase(
				"( A )",
				expected_result=["A"]),
			UseReduceTestCase(
				"|| ( A B )",
				expected_result=["||", ["A", "B"]]),
			UseReduceTestCase(
				"|| ( ( A B ) C )",
				expected_result=["||", [["A", "B"], "C"]]),
			UseReduceTestCase(
				"|| ( ( A B ) ( C ) )",
				expected_result=["||", [["A", "B"], "C"]]),
			UseReduceTestCase(
				"|| ( A || ( B C ) )",
				expected_result=["||", ["A", "B", "C"]]),
			UseReduceTestCase(
				"|| ( A || ( B C D ) )",
				expected_result=["||", ["A", "B", "C", "D"]]),
			UseReduceTestCase(
				"|| ( A || ( B || ( C D ) E ) )",
				expected_result=["||", ["A", "B", "C", "D", "E"]]),
			UseReduceTestCase(
				"( || ( ( ( A ) B ) ) )",
				expected_result=["A", "B"]),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				expected_result=["||", ["A", "B"]]),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				expected_result=["||", ["A", "B"]]),
			UseReduceTestCase(
				"|| ( A )",
				expected_result=["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				expected_result=["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				uselist=["foo"],
				expected_result=["||", ["A", "B"]]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				expected_result=[]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				uselist=["foo", "bar"],
				expected_result=["||", ["A", "B"]]),
			UseReduceTestCase(
				"A || ( bar? ( C ) ) foo? ( bar? ( C ) ) B",
				expected_result=["A", "B"]),
			UseReduceTestCase(
				"|| ( A ) || ( B )",
				expected_result=["A", "B"]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				expected_result=[]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				uselist=["foo"],
				expected_result=["A", "B"]),
			UseReduceTestCase(
				"|| ( A B ) C",
				expected_result=['||', ['A', 'B'], 'C']),
			UseReduceTestCase(
				"A || ( B C )",
				expected_result=['A', '||', ['B', 'C']]),

			# SRC_URI stuff
			UseReduceTestCase(
				"http://foo/bar -> blah.tbz2",
				is_src_uri=True,
				eapi=EAPI_WITH_SRC_URI_ARROWS,
				expected_result=["http://foo/bar", "->", "blah.tbz2"]),
			UseReduceTestCase(
				"foo? ( http://foo/bar -> blah.tbz2 )",
				uselist=[],
				is_src_uri=True,
				eapi=EAPI_WITH_SRC_URI_ARROWS,
				expected_result=[]),
			UseReduceTestCase(
				"foo? ( http://foo/bar -> blah.tbz2 )",
				uselist=["foo"],
				is_src_uri=True,
				eapi=EAPI_WITH_SRC_URI_ARROWS,
				expected_result=["http://foo/bar", "->", "blah.tbz2"]),
			UseReduceTestCase(
				"http://foo/bar -> bar.tbz2 foo? ( ftp://foo/a )",
				uselist=[],
				is_src_uri=True,
				eapi=EAPI_WITH_SRC_URI_ARROWS,
				expected_result=["http://foo/bar", "->", "bar.tbz2"]),
			UseReduceTestCase(
				"http://foo/bar -> bar.tbz2 foo? ( ftp://foo/a )",
				uselist=["foo"],
				is_src_uri=True,
				eapi=EAPI_WITH_SRC_URI_ARROWS,
				expected_result=["http://foo/bar", "->", "bar.tbz2", "ftp://foo/a"]),
			UseReduceTestCase(
				"http://foo.com/foo http://foo/bar -> blah.tbz2",
				uselist=["foo"],
				is_src_uri=True,
				eapi=EAPI_WITH_SRC_URI_ARROWS,
				expected_result=["http://foo.com/foo", "http://foo/bar", "->", "blah.tbz2"]),

			# opconvert tests
			UseReduceTestCase(
				"A",
				opconvert=True,
				expected_result=["A"]),
			UseReduceTestCase(
				"( A )",
				opconvert=True,
				expected_result=["A"]),
			UseReduceTestCase(
				"|| ( A B )",
				opconvert=True,
				expected_result=[['||', 'A', 'B']]),
			UseReduceTestCase(
				"|| ( ( A B ) C )",
				opconvert=True,
				expected_result=[['||', ['A', 'B'], 'C']]),
			UseReduceTestCase(
				"|| ( A || ( B C ) )",
				opconvert=True,
				expected_result=[['||', 'A', 'B', 'C']]),
			UseReduceTestCase(
				"|| ( A || ( B C D ) )",
				opconvert=True,
				expected_result=[['||', 'A', 'B', 'C', 'D']]),
			UseReduceTestCase(
				"|| ( A || ( B || ( C D ) E ) )",
				expected_result=["||", ["A", "B", "C", "D", "E"]]),
			UseReduceTestCase(
				"( || ( ( ( A ) B ) ) )",
				opconvert=True,
				expected_result=['A', 'B']),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				opconvert=True,
				expected_result=[['||', 'A', 'B']]),
			UseReduceTestCase(
				"|| ( A B ) C",
				opconvert=True,
				expected_result=[['||', 'A', 'B'], 'C']),
			UseReduceTestCase(
				"A || ( B C )",
				opconvert=True,
				expected_result=['A', ['||', 'B', 'C']]),
			UseReduceTestCase(
				"A foo? ( || ( B || ( bar? ( || ( C D E ) ) !bar? ( F ) ) ) ) G",
				uselist=["foo", "bar"],
				opconvert=True,
				expected_result=['A', ['||', 'B', 'C', 'D', 'E'], 'G']),
			UseReduceTestCase(
				"A foo? ( || ( B || ( bar? ( || ( C D E ) ) !bar? ( F ) ) ) ) G",
				uselist=["foo", "bar"],
				opconvert=False,
				expected_result=['A', '||', ['B', 'C', 'D', 'E'], 'G']),

			UseReduceTestCase(
				"|| ( A )",
				opconvert=True,
				expected_result=["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				expected_result=["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				uselist=["foo"],
				opconvert=True,
				expected_result=[['||', 'A', 'B']]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				opconvert=True,
				expected_result=[]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				uselist=["foo", "bar"],
				opconvert=True,
				expected_result=[['||', 'A', 'B']]),
			UseReduceTestCase(
				"A || ( bar? ( C ) ) foo? ( bar? ( C ) ) B",
				opconvert=True,
				expected_result=["A", "B"]),
			UseReduceTestCase(
				"|| ( A ) || ( B )",
				opconvert=True,
				expected_result=["A", "B"]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				opconvert=True,
				expected_result=[]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				uselist=["foo"],
				opconvert=True,
				expected_result=["A", "B"]),
			UseReduceTestCase(
				"|| ( foo? ( || ( A B ) ) )",
				uselist=["foo"],
				opconvert=True,
				expected_result=[['||', 'A', 'B']]),

			UseReduceTestCase(
				"|| ( ( A B ) foo? ( || ( C D ) ) )",
				uselist=["foo"],
				opconvert=True,
				expected_result=[['||', ['A', 'B'], 'C', 'D']]),

			UseReduceTestCase(
				"|| ( ( A B ) foo? ( || ( C D ) ) )",
				uselist=["foo"],
				opconvert=False,
				expected_result=['||', [['A', 'B'], 'C', 'D']]),

			UseReduceTestCase(
				"|| ( ( A B ) || ( C D ) )",
				expected_result=['||', [['A', 'B'], 'C', 'D']]),

			UseReduceTestCase(
				"|| ( ( A B ) || ( C D || ( E ( F G ) || ( H ) ) ) )",
				expected_result=['||', [['A', 'B'], 'C', 'D', 'E', ['F', 'G'], 'H']]),

			UseReduceTestCase(
				"|| ( ( A B ) || ( C D || ( E ( F G ) || ( H ) ) ) )",
				opconvert=True,
				expected_result=[['||', ['A', 'B'], 'C', 'D', 'E', ['F', 'G'], 'H']]),

			UseReduceTestCase(
				"|| ( foo? ( A B ) )",
				uselist=["foo"],
				expected_result=['A', 'B']),

			UseReduceTestCase(
				"|| ( || ( foo? ( A B ) ) )",
				uselist=["foo"],
				expected_result=['A', 'B']),

			UseReduceTestCase(
				"|| ( || ( || ( a? ( b? ( c? ( || ( || ( || ( d? ( e? ( f? ( A B ) ) ) ) ) ) ) ) ) ) ) )",
				uselist=["a", "b", "c", "d", "e", "f"],
				expected_result=['A', 'B']),

			UseReduceTestCase(
				"|| ( || ( ( || ( a? ( ( b? ( c? ( || ( || ( || ( ( d? ( e? ( f? ( A B ) ) ) ) ) ) ) ) ) ) ) ) ) ) )",
				uselist=["a", "b", "c", "d", "e", "f"],
				expected_result=['A', 'B']),

			UseReduceTestCase(
				"|| ( ( A ( || ( B ) ) ) )",
				expected_result=['A', 'B']),

			UseReduceTestCase(
				"|| ( ( A B ) || ( foo? ( bar? ( ( C D || ( baz? ( E ) ( F G ) || ( H ) ) ) ) ) ) )",
				uselist=["foo", "bar", "baz"],
				expected_result=['||', [['A', 'B'], ['C', 'D', '||', ['E', ['F', 'G'], 'H']]]]),

			UseReduceTestCase(
				"|| ( ( A B ) || ( foo? ( bar? ( ( C D || ( baz? ( E ) ( F G ) || ( H ) ) ) ) ) ) )",
				uselist=["foo", "bar", "baz"],
				opconvert=True,
				expected_result=[['||', ['A', 'B'], ['C', 'D', ['||', 'E', ['F', 'G'], 'H']]]]),

			UseReduceTestCase(
				"|| ( foo? ( A B ) )",
				uselist=["foo"],
				opconvert=True,
				expected_result=['A', 'B']),

			UseReduceTestCase(
				"|| ( || ( foo? ( A B ) ) )",
				uselist=["foo"],
				opconvert=True,
				expected_result=['A', 'B']),

			UseReduceTestCase(
				"|| ( || ( || ( a? ( b? ( c? ( || ( || ( || ( d? ( e? ( f? ( A B ) ) ) ) ) ) ) ) ) ) ) )",
				uselist=["a", "b", "c", "d", "e", "f"],
				opconvert=True,
				expected_result=['A', 'B']),

			# flat test
			UseReduceTestCase(
				"A",
				flat=True,
				expected_result=["A"]),
			UseReduceTestCase(
				"( A )",
				flat=True,
				expected_result=["A"]),
			UseReduceTestCase(
				"|| ( A B )",
				flat=True,
				expected_result=["||", "A", "B"]),
			UseReduceTestCase(
				"|| ( A || ( B C ) )",
				flat=True,
				expected_result=["||", "A", "||", "B", "C"]),
			UseReduceTestCase(
				"|| ( A || ( B C D ) )",
				flat=True,
				expected_result=["||", "A", "||", "B", "C", "D"]),
			UseReduceTestCase(
				"|| ( A || ( B || ( C D ) E ) )",
				flat=True,
				expected_result=["||", "A", "||", "B", "||", "C", "D", "E"]),
			UseReduceTestCase(
				"( || ( ( ( A ) B ) ) )",
				flat=True,
				expected_result=["||", "A", "B"]),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				flat=True,
				expected_result=["||", "||", "A", "B"]),
			UseReduceTestCase(
				"( || ( || ( ( A ) B ) ) )",
				flat=True,
				expected_result=["||", "||", "A", "B"]),
			UseReduceTestCase(
				"|| ( A )",
				flat=True,
				expected_result=["||", "A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				expected_result=["A"]),
			UseReduceTestCase(
				"( || ( || ( || ( A ) foo? ( B ) ) ) )",
				uselist=["foo"],
				flat=True,
				expected_result=["||", "||", "||", "A", "B"]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				flat=True,
				expected_result=["||", "||", "||"]),
			UseReduceTestCase(
				"( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )",
				uselist=["foo", "bar"],
				flat=True,
				expected_result=["||", "||", "A", "||", "B"]),
			UseReduceTestCase(
				"A || ( bar? ( C ) ) foo? ( bar? ( C ) ) B",
				flat=True,
				expected_result=["A", "||", "B"]),
			UseReduceTestCase(
				"|| ( A ) || ( B )",
				flat=True,
				expected_result=["||", "A", "||", "B"]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				flat=True,
				expected_result=[]),
			UseReduceTestCase(
				"foo? ( A ) foo? ( B )",
				uselist=["foo"],
				flat=True,
				expected_result=["A", "B"]),

			# use flag validation
			UseReduceTestCase(
				"foo? ( A )",
				uselist=["foo"],
				is_valid_flag=self.always_true,
				expected_result=["A"]),
			UseReduceTestCase(
				"foo? ( A )",
				is_valid_flag=self.always_true,
				expected_result=[]),

			# token_class
			UseReduceTestCase(
				"foo? ( dev-libs/A )",
				uselist=["foo"],
				token_class=Atom,
				expected_result=["dev-libs/A"]),
			UseReduceTestCase(
				"foo? ( dev-libs/A )",
				token_class=Atom,
				expected_result=[]),
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
			UseReduceTestCase("foo?"),
			UseReduceTestCase("foo? || ( A )"),
			UseReduceTestCase("|| ( )"),
			UseReduceTestCase("foo? ( )"),

			# SRC_URI stuff
			UseReduceTestCase("http://foo/bar -> blah.tbz2", is_src_uri=True, eapi=EAPI_WITHOUT_SRC_URI_ARROWS),
			UseReduceTestCase("|| ( http://foo/bar -> blah.tbz2 )", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("http://foo/bar -> foo? ( ftp://foo/a )", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("http://foo/bar blah.tbz2 ->", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("-> http://foo/bar blah.tbz2 )", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("http://foo/bar ->", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("http://foo/bar -> foo? ( http://foo.com/foo )", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("foo? ( http://foo/bar -> ) blah.tbz2", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("http://foo/bar -> foo/blah.tbz2", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),
			UseReduceTestCase("http://foo/bar -> -> bar.tbz2 foo? ( ftp://foo/a )", is_src_uri=True, eapi=EAPI_WITH_SRC_URI_ARROWS),

			UseReduceTestCase("http://foo/bar -> bar.tbz2 foo? ( ftp://foo/a )", is_src_uri=False, eapi=EAPI_WITH_SRC_URI_ARROWS),

			UseReduceTestCase(
				"A",
				opconvert=True,
				flat=True),

			# use flag validation
			UseReduceTestCase("1.0? ( A )"),
			UseReduceTestCase("!1.0? ( A )"),
			UseReduceTestCase("!? ( A )"),
			UseReduceTestCase("!?? ( A )"),
			UseReduceTestCase(
				"foo? ( A )",
				is_valid_flag=self.always_false,
				),
			UseReduceTestCase(
				"foo? ( A )",
				uselist=["foo"],
				is_valid_flag=self.always_false,
				),

			# token_class
			UseReduceTestCase(
				"foo? ( A )",
				uselist=["foo"],
				token_class=Atom),
			UseReduceTestCase(
				"A(B",
				token_class=Atom),
		)

		for test_case in test_cases:
			# If it fails then show the input, since lots of our
			# test cases have the same output but different input,
			# making it difficult deduce which test has failed.
			self.assertEqual(test_case.run(), test_case.expected_result,
				"input: '%s' result: %s != %s" % (test_case.deparray,
				test_case.run(), test_case.expected_result))

		for test_case in test_cases_xfail:
			self.assertRaisesMsg(test_case.deparray, (InvalidDependString, ValueError), test_case.run)
