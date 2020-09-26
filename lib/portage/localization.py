# localization.py -- Code to manage/help portage localization.
# Copyright 2004-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import locale
import math

from portage import _encodings, _unicode_decode

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
	c_value = [1, 2, 3, 4]
	print(_("A: %(a)s -- B: %(b)s -- C: %(c)s") %
	      {"a": a_value, "b": b_value, "c": c_value})

def localized_size(num_bytes):
	"""
	Return pretty localized size string for num_bytes size
	(given in bytes). The output will be in kibibytes.
	"""

	# always round up, so that small files don't end up as '0 KiB'
	num_kib = math.ceil(num_bytes / 1024)
	try:
		formatted_num = locale.format_string('%d', num_kib, grouping=True)
	except UnicodeDecodeError:
		# failure to decode locale data
		formatted_num = str(num_kib)
	return _unicode_decode(formatted_num, encoding=_encodings['stdio']) + ' KiB'
