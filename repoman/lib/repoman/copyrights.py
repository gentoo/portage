# -*- coding:utf-8 -*-


import difflib
import io
import re
from tempfile import mkstemp

from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage import os
from portage import shutil
from portage import util


_copyright_re1 = \
	re.compile(br'^(# Copyright \d\d\d\d)-\d\d\d\d( Gentoo (Foundation|Authors))\b')
_copyright_re2 = \
	re.compile(br'^(# Copyright )(\d\d\d\d)( Gentoo (Foundation|Authors))\b')


class _copyright_repl:
	__slots__ = ('year',)

	def __init__(self, year):
		self.year = year

	def __call__(self, matchobj):
		if matchobj.group(2) == self.year:
			return matchobj.group(0)
		else:
			return matchobj.group(1) + matchobj.group(2) + \
				b'-' + self.year + b' Gentoo Authors'


def update_copyright_year(year, line):
	"""
	These two regexes are taken from echangelog
	update_copyright(), except that we don't hardcode
	1999 here (in order to be more generic).
	"""
	is_bytes = isinstance(line, bytes)
	if is_bytes:
		if not line.startswith(b'# Copyright '):
			return line
	else:
		if not line.startswith('# Copyright '):
			return line

	year = _unicode_encode(year)
	line = _unicode_encode(line)

	line = _copyright_re1.sub(br'\1-' + year + b' Gentoo Authors', line)
	line = _copyright_re2.sub(_copyright_repl(year), line)
	if not is_bytes:
		line = _unicode_decode(line)
	return line


def update_copyright(fn_path, year, pretend=False):
	"""
	Check file for a Copyright statement, and update its year.  The
	patterns used for replacing copyrights are taken from echangelog.
	Only the first lines of each file that start with a hash ('#') are
	considered, until a line is found that doesn't start with a hash.
	Files are read and written in binary mode, so that this function
	will work correctly with files encoded in any character set, as
	long as the copyright statements consist of plain ASCII.

	@param fn_path: file path
	@type str
	@param year: current year
	@type str
	@param pretend: pretend mode
	@type bool
	@rtype: bool
	@return: True if copyright update was needed, False otherwise
	"""

	try:
		fn_hdl = io.open(_unicode_encode(
			fn_path, encoding=_encodings['fs'], errors='strict'),
			mode='rb')
	except EnvironmentError:
		return

	orig_header = []
	new_header = []

	for line in fn_hdl:
		line_strip = line.strip()
		orig_header.append(line)
		if not line_strip or line_strip[:1] != b'#':
			new_header.append(line)
			break

		line = update_copyright_year(year, line)
		new_header.append(line)

	difflines = 0
	for diffline in difflib.unified_diff(
		[_unicode_decode(diffline) for diffline in orig_header],
		[_unicode_decode(diffline) for diffline in new_header],
		fromfile=fn_path, tofile=fn_path, n=0):
		util.writemsg_stdout(diffline, noiselevel=-1)
		difflines += 1
	util.writemsg_stdout("\n", noiselevel=-1)

	# unified diff has three lines to start with
	if difflines > 3 and not pretend:
		# write new file with changed header
		f, fnnew_path = mkstemp()
		f = io.open(f, mode='wb')
		for line in new_header:
			f.write(line)
		for line in fn_hdl:
			f.write(line)
		f.close()
		try:
			fn_stat = os.stat(fn_path)
		except OSError:
			fn_stat = None

		shutil.move(fnnew_path, fn_path)

		if fn_stat is None:
			util.apply_permissions(fn_path, mode=0o644)
		else:
			util.apply_stat_permissions(fn_path, fn_stat)
	fn_hdl.close()
	return difflines > 3
