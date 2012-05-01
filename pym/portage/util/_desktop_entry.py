# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import subprocess
import sys

try:
	from configparser import Error as ConfigParserError, RawConfigParser
except ImportError:
	from ConfigParser import Error as ConfigParserError, RawConfigParser

from portage import _encodings, _unicode_encode, _unicode_decode

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
		read_file(f)

	return parser

_ignored_service_errors = (
	'error: required key "Name" in group "Desktop Entry" is not present',
	'error: key "Actions" is present in group "Desktop Entry", but the type is "Service" while this key is only valid for type "Application"',
	'error: key "MimeType" is present in group "Desktop Entry", but the type is "Service" while this key is only valid for type "Application"',
)

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
		try:
			desktop_entry = parse_desktop_entry(path)
		except ConfigParserError:
			pass
		else:
			if desktop_entry.has_section("Desktop Entry"):
				try:
					entry_type = desktop_entry.get("Desktop Entry", "Type")
				except ConfigParserError:
					pass
				else:
					if entry_type == "Service":
						# Filter false errors for Type=Service (bug #414125).
						filtered_output = []
						for line in output_lines:
							if line[len(path)+2:] in _ignored_service_errors:
								continue
							filtered_output.append(line)
						output_lines = filtered_output

	return output_lines
