# Copyright 2009-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.exception import InvalidDependString
from portage.dep import use_reduce

class UseReduceTestCase(object):
	def __init__(self, deparray, uselist=[], masklist=[], \
		matchall=0, excludeall=[], expected_result=None):
		self.deparray = deparray
		self.uselist = uselist
		self.masklist = masklist
		self.matchall = matchall
		self.excludeall = excludeall
		self.expected_result = expected_result

	def run(self):
		return use_reduce(self.deparray, self.uselist, self.masklist, \
			self.matchall, self.excludeall)
				
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
		)

		for test_case in test_cases:
			self.assertEqual(test_case.run(), test_case.expected_result)

		for test_case in test_cases_xfail:
			self.assertRaisesMsg(test_case.deparray, InvalidDependString, test_case.run)
