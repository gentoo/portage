# -*- coding:utf-8 -*-


import difflib
import io
from tempfile import mkstemp

from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage import os
from portage import shutil
from portage import util

def update_copyright_year(year, line):
	"""
	Updates the copyright year range for any copyright owner

	@param year: current year
	@type str
	@param line: copyright line
	@type str
	@return: str
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

	# used for backward compatibility in UpdateChangelog
	line = line.replace(b'Gentoo Foundation', b'Gentoo Authors')

	parts = line.split(b' ', 3)
	if parts[2] != year:
		# Update the years range
		parts[2] = b'-'.join([parts[2].split(b'-')[0], year])
	# re-assemble the line
	line = b' '.join(parts)
	if not is_bytes:
		line = _unicode_decode(line)
	return line


def add_owner(owner, line):
	"""
	Updates the copyright for any copyright owner

	@param year: new owner
	@type str
	@param line: copyright line
	@type str
	@return: str
	"""
	is_bytes = isinstance(line, bytes)
	if is_bytes:
		if not line.startswith(b'# Copyright '):
			return line
	else:
		if not line.startswith('# Copyright '):
			return line

	# ensure is unicode and strip the newline
	line = _unicode_encode(line).rstrip(b'\n')

	parts = line.split(b' ', 3)
	if parts[3].endswith(b' and others'):
		owners = parts[3].split(b' and others')
		owners[0].rstrip(b',')
		parts[3] = b', '.join([owners[0], owner]) + b' and others'
	else:
		parts[3] = b', '.join([parts[3].rstrip(b','), owner])
	line = b' '.join(parts) + b'\n'
	if not is_bytes:
		line = _unicode_decode(line)
	return line


def update_copyright(fn_path, year, pretend=False,
			owner=None, update_owner=False,
			add_copyright=False):
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

	owner = _unicode_encode(owner) or b'Gentoo Authors'

	orig_header = []
	new_header = []
	has_copyright = False

	for line in fn_hdl:
		line_strip = line.strip()
		orig_header.append(line)
		if not line_strip or line_strip[:1] != b'#':
			new_header.append(line)
			break
		has_copyright = max(has_copyright, line.startswith(b'# Copyright '))
		# update date range
		line = update_copyright_year(year, line)
		# now check for and add COPYRIGHT_OWNER
		if update_owner and owner not in line:
			line = add_owner(owner, line)
		new_header.append(line)
	if not has_copyright and add_copyright:
		new_copyright = b' '.join([b'# Copyright', _unicode_encode(year), owner]) + b'\n'
		new_header.insert(0, new_copyright)

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
