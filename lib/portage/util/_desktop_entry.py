# Copyright 2012-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import re
import subprocess
import sys

from portage import _unicode_encode, _unicode_decode
from portage.util import writemsg
from portage.util.configparser import (RawConfigParser,	read_configs)

def parse_desktop_entry(path):
	"""
	Parse the given file with RawConfigParser and return the
	result. This may raise an IOError from io.open(), or a
	ParsingError from RawConfigParser.
	"""
	parser = RawConfigParser()

	read_configs(parser, [path])

	return parser

_trivial_warnings = re.compile(r' looks '
	# >=desktop-file-utils-0.25
	r'(?:the same as that of key|'

	# <desktop-file-utils-0.25
	r'redundant with value) ')

_ignored_errors = (
		# Ignore error for emacs.desktop:
		# https://bugs.freedesktop.org/show_bug.cgi?id=35844#c6
		'error: (will be fatal in the future): value "TextEditor" in key "Categories" in group "Desktop Entry" requires another category to be present among the following categories: Utility',
		'warning: key "Encoding" in group "Desktop Entry" is deprecated'
)

_ShowIn_exemptions = (
	# See bug #480586.
	'contains an unregistered value "Pantheon"',
)

def validate_desktop_entry(path):
	args = ["desktop-file-validate", path]

	args = [_unicode_encode(x, errors='strict') for x in args]
	proc = subprocess.Popen(args,
		stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	output_lines = _unicode_decode(proc.communicate()[0]).splitlines()
	proc.wait()

	if output_lines:
		filtered_output = []
		for line in output_lines:
			msg = line[len(path)+2:]
			# "hint:" output is new in desktop-file-utils-0.21
			if msg.startswith('hint: ') or msg in _ignored_errors:
				continue
			if 'for key "NotShowIn" in group "Desktop Entry"' in msg or \
				'for key "OnlyShowIn" in group "Desktop Entry"' in msg:
				exempt = False
				for s in _ShowIn_exemptions:
					if s in msg:
						exempt = True
						break
				if exempt:
					continue
			filtered_output.append(line)
		output_lines = filtered_output

	if output_lines:
		output_lines = [line for line in output_lines
			if _trivial_warnings.search(line) is None]

	return output_lines

if __name__ == "__main__":
	for arg in sys.argv[1:]:
		for line in validate_desktop_entry(arg):
			writemsg(line + "\n", noiselevel=-1)
