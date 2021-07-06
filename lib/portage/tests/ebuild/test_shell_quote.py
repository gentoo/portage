# Copyright 2021 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import _shell_quote
from portage.tests import TestCase

class ShellQuoteTestCase(TestCase):

	def testShellQuote(self):
		test_data = [

			# String contains no special characters, should be preserved.
			("abc","abc"),

			# String contains whitespace, should be double-quoted to prevent word splitting.
			("abc xyz","\"abc xyz\""),
			("abc  xyz","\"abc  xyz\""),
			(" abcxyz ","\" abcxyz \""),
			("abc\txyz","\"abc\txyz\""),
			("abc\t\txyz","\"abc\t\txyz\""),
			("\tabcxyz\t","\"\tabcxyz\t\""),
			("abc\nxyz","\"abc\nxyz\""),
			("abc\n\nxyz","\"abc\n\nxyz\""),
			("\nabcxyz\n","\"\nabcxyz\n\""),

			# String contains > or <, should be double-quoted to prevent redirection.
			("abc>xyz","\"abc>xyz\""),
			("abc>>xyz","\"abc>>xyz\""),
			(">abcxyz>","\">abcxyz>\""),
			("abc<xyz","\"abc<xyz\""),
			("abc<<xyz","\"abc<<xyz\""),
			("<abcxyz<","\"<abcxyz<\""),

			# String contains =, should be double-quoted to prevent assignment.
			("abc=xyz","\"abc=xyz\""),
			("abc==xyz","\"abc==xyz\""),
			("=abcxyz=","\"=abcxyz=\""),

			# String contains *, should be double-quoted to prevent globbing.
			("abc*xyz","\"abc*xyz\""),
			("abc**xyz","\"abc**xyz\""),
			("*abcxyz*","\"*abcxyz*\""),

			# String contains $, should be escaped to prevent parameter expansion.
			# Also double-quoted, though not strictly needed.
			("abc$xyz","\"abc\\$xyz\""),
			("abc$$xyz","\"abc\\$\\$xyz\""),
			("$abcxyz$","\"\\$abcxyz\\$\""),

			# String contains `, should be escaped to prevent command substitution.
			# Also double-quoted, though not strictly needed.
			("abc`xyz","\"abc\\`xyz\""),
			("abc``xyz","\"abc\\`\\`xyz\""),
			("`abc`","\"\\`abc\\`\""),

			# String contains \, should be escaped to prevent it from escaping
			# the next character. Also double-quoted, though not strictly needed.
			("abc\\xyz", "\"abc\\\\xyz\""),
			("abc\\\\xyz", "\"abc\\\\\\\\xyz\""),
			("\\abcxyz\\", "\"\\\\abcxyz\\\\\""),

			# String contains ", should be escaped to prevent it from unexpectedly
			# ending a previous double-quote or starting a new double-quote. Also
			# double-quoted, though not strictly needed.
			("abc\"xyz","\"abc\\\"xyz\""),
			("abc\"\"xyz","\"abc\\\"\\\"xyz\""),
			("\"abcxyz\"","\"\\\"abcxyz\\\"\""),

			# String contains ', should be double-quoted to prevent it from unexpectedly
			# ending a previous single-quote or starting a new single-quote.
			("abc'xyz","\"abc'xyz\""),
			("abc''xyz","\"abc''xyz\""),
			("'abcxyz'","\"'abcxyz'\""),

			# String contains ;, should be double-quoted to prevent command separation.
			("abc;xyz","\"abc;xyz\""),
			("abc;;xyz","\"abc;;xyz\""),
			(";abcxyz;","\";abcxyz;\""),

			# String contains &, should be double-quoted to prevent job control.
			("abc&xyz","\"abc&xyz\""),
			("abc&&xyz","\"abc&&xyz\""),
			("&abcxyz&","\"&abcxyz&\""),

			# String contains |, should be double-quoted to prevent piping.
			("abc|xyz","\"abc|xyz\""),
			("abc||xyz","\"abc||xyz\""),
			("|abcxyz|","\"|abcxyz|\""),

			# String contains (), should be double-quoted to prevent
			# command group / array initialization.
			("abc()xyz","\"abc()xyz\""),
			("abc(())xyz","\"abc(())xyz\""),
			("((abcxyz))","\"((abcxyz))\""),

			# String contains {}. Parameter expansion of the form ${} is already
			# rendered safe by escaping the $, but {} could also occur on its own,
			# for example in a brace expansion such as filename.{ext1,ext2},
			# so the string should be double-quoted.
			("abc{}xyz","\"abc{}xyz\""),
			("abc{{}}xyz","\"abc{{}}xyz\""),
			("{{abcxyz}}","\"{{abcxyz}}\""),

			# String contains [], should be double-quoted to prevent testing
			("abc[]xyz","\"abc[]xyz\""),
			("abc[[]]xyz","\"abc[[]]xyz\""),
			("[[abcxyz]]","\"[[abcxyz]]\""),

			# String contains #, should be double-quoted to prevent comment.
			("#abc","\"#abc\""),

			# String contains !, should be double-quoted to prevent e.g. history substitution.
			("!abc","\"!abc\""),

			# String contains ~, should be double-quoted to prevent home directory expansion.
			("~abc","\"~abc\""),

			# String contains ?, should be double-quoted to prevent globbing.
			("abc?xyz","\"abc?xyz\""),
			("abc??xyz","\"abc??xyz\""),
			("?abcxyz?","\"?abcxyz?\""),
		]

		for (data,expected_result) in test_data:
			result = _shell_quote(data)
			self.assertEqual(result, expected_result)
