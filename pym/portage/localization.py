# localization.py -- Code to manage/help portage localization.
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2


# We define this to make the transition easier for us.
def _(mystr):
	return mystr


def localization_example():
	# Dict references allow translators to rearrange word order.
	print(_("You can use this string for translating."))
	print(_("Strings can be formatted with %(mystr)s like this.") % {"mystr": "VALUES"})

	a_value = "value.of.a"
	b_value = 123
	c_value = [1,2,3,4]
	print(_("A: %(a)s -- B: %(b)s -- C: %(c)s") % {"a":a_value,"b":b_value,"c":c_value})

