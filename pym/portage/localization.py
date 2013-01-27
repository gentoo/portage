# localization.py -- Code to manage/help portage localization.
# Copyright 2004-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import _unicode_decode

# We define this to make the transition easier for us.
def _(mystr):
	"""
	Always returns unicode, regardless of the input type. This is
	helpful for avoiding UnicodeDecodeError from __str__() with
	Python 2, by ensuring that string format operations invoke
	__unicode__() instead of __str__().
	"""
	return _unicode_decode(mystr)

def localization_example():
	# Dict references allow translators to rearrange word order.
	print(_("You can use this string for translating."))
	print(_("Strings can be formatted with %(mystr)s like this.") % {"mystr": "VALUES"})

	a_value = "value.of.a"
	b_value = 123
	c_value = [1,2,3,4]
	print(_("A: %(a)s -- B: %(b)s -- C: %(c)s") % {"a":a_value,"b":b_value,"c":c_value})

