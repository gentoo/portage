# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import re
import subprocess
import sys

try:
	from configparser import Error as ConfigParserError, RawConfigParser
except ImportError:
	from ConfigParser import Error as ConfigParserError, RawConfigParser

from portage import _encodings, _unicode_encode, _unicode_decode
from portage.util import writemsg

def parse_desktop_entry(path):
	"""
	Parse the given file with RawConfigParser and return the
	result. This may raise an IOError from io.open(), or a
	ParsingError from RawConfigParser.
	"""
	parser = RawConfigParser()

	# use read_file/readfp in order to control decoding of unicode
	try:
		# Python >=3.2
		read_file = parser.read_file
	except AttributeError:
		read_file = parser.readfp

	with io.open(_unicode_encode(path,
		encoding=_encodings['fs'], errors='strict'),
		mode='r', encoding=_encodings['repo.content'],
		errors='replace') as f:
		content = f.read()

	# In Python 3.2, read_file does not support bytes in file names
	# (see bug #429544), so use StringIO to hide the file name.
	read_file(io.StringIO(content))

	return parser

_trivial_warnings = re.compile(r' looks redundant with value ')
_ignore_kde_key_re = re.compile(r'^\s*(configurationType\s*=|Type\s*=\s*Service)')
_ignore_kde_types = frozenset(
	["AkonadiAgent", "AkonadiResource", "Service", "ServiceType"])

# kdebase-data installs files with [Currency Code] sections
# in /usr/share/locale/currency
# kdepim-runtime installs files with [Plugin] and [Wizard]
# sections in /usr/share/apps/akonadi/{plugins,accountwizard}
_ignore_kde_sections = ("Currency Code", "Plugin", "Wizard")

def validate_desktop_entry(path):
	args = ["desktop-file-validate", path]
	if sys.hexversion < 0x3000000 or sys.hexversion >= 0x3020000:
		# Python 3.1 does not support bytes in Popen args.
		args = [_unicode_encode(x, errors='strict') for x in args]
	proc = subprocess.Popen(args,
		stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	output_lines = _unicode_decode(proc.communicate()[0]).splitlines()
	proc.wait()

	if output_lines:
		# Ignore kde extensions for bug #414125 and bug #432862.
		try:
			desktop_entry = parse_desktop_entry(path)
		except ConfigParserError:
			with io.open(_unicode_encode(path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace') as f:
				for line in f:
					if _ignore_kde_key_re.match(line):
						# Ignore kde extensions for bug #432862.
						del output_lines[:]
						break
		else:
			if desktop_entry.has_section("Desktop Entry"):
				try:
					entry_type = desktop_entry.get("Desktop Entry", "Type")
				except ConfigParserError:
					pass
				else:
					if entry_type in _ignore_kde_types:
						del output_lines[:]
				try:
					desktop_entry.get("Desktop Entry", "Hidden")
				except ConfigParserError:
					pass
				else:
					# The "Hidden" key appears to be unique to special kde
					# service files (which don't validate well), installed
					# in /usr/share/kde4/services/ by packages like
					# nepomuk-core and kurifilter-plugins.
					del output_lines[:]
			for section in _ignore_kde_sections:
				if desktop_entry.has_section(section):
					del output_lines[:]

	if output_lines:
		output_lines = [line for line in output_lines
			if _trivial_warnings.search(line) is None]

	return output_lines

if __name__ == "__main__":
	for arg in sys.argv[1:]:
		for line in validate_desktop_entry(arg):
			writemsg(line + "\n", noiselevel=-1)
