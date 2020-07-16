#!/usr/bin/python -b
# Copyright 2012-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Dump and restore extended attributes.

We use formats like that used by getfattr --dump.  This is meant for shell
helpers to save/restore.  If you're looking for a python/portage API, see
portage.util.movefile._copyxattr instead.

https://en.wikipedia.org/wiki/Extended_file_attributes
"""
__doc__ = doc


import argparse
import array
import os
import re
import sys

from portage.util._xattr import xattr


_UNQUOTE_RE = re.compile(br'\\[0-7]{3}')
_FS_ENCODING = sys.getfilesystemencoding()


def octal_quote_byte(b):
	return ('\\%03o' % ord(b)).encode('ascii')


def unicode_encode(s):
	if isinstance(s, str):
		s = s.encode(_FS_ENCODING, 'surrogateescape')
	return s


def quote(s, quote_chars):
	"""Convert all |quote_chars| in |s| to escape sequences

	This is normally used to escape any embedded quotation marks.
	"""
	quote_re = re.compile(b'[' + quote_chars + b']')
	result = []
	pos = 0
	s_len = len(s)

	while pos < s_len:
		m = quote_re.search(s, pos=pos)
		if m is None:
			result.append(s[pos:])
			pos = s_len
		else:
			start = m.start()
			result.append(s[pos:start])
			result.append(octal_quote_byte(s[start:start+1]))
			pos = start + 1

	return b''.join(result)


def unquote(s):
	"""Process all escape sequences in |s|"""
	result = []
	pos = 0
	s_len = len(s)

	while pos < s_len:
		m = _UNQUOTE_RE.search(s, pos=pos)
		if m is None:
			result.append(s[pos:])
			pos = s_len
		else:
			start = m.start()
			result.append(s[pos:start])
			pos = start + 4
			a = array.array('B')
			a.append(int(s[start + 1:pos], 8))
			try:
				# Python >= 3.2
				result.append(a.tobytes())
			except AttributeError:
				result.append(a.tostring())

	return b''.join(result)


def dump_xattrs(pathnames, file_out):
	"""Dump the xattr data for |pathnames| to |file_out|"""
	# NOTE: Always quote backslashes, in order to ensure that they are
	# not interpreted as quotes when they are processed by unquote.
	quote_chars = b'\n\r\\\\'

	for pathname in pathnames:
		attrs = xattr.list(pathname)
		if not attrs:
			continue

		file_out.write(b'# file: %s\n' % quote(pathname, quote_chars))
		for attr in attrs:
			attr = unicode_encode(attr)
			value = xattr.get(pathname, attr)
			file_out.write(b'%s="%s"\n' % (
				quote(attr, b'=' + quote_chars),
				quote(value, b'\0"' + quote_chars)))


def restore_xattrs(file_in):
	"""Read |file_in| and restore xattrs content from it

	This expects textual data in the format written by dump_xattrs.
	"""
	pathname = None
	for i, line in enumerate(file_in):
		if line.startswith(b'# file: '):
			pathname = unquote(line.rstrip(b'\n')[8:])
		else:
			parts = line.split(b'=', 1)
			if len(parts) == 2:
				if pathname is None:
					raise ValueError('line %d: missing pathname' % (i + 1,))
				attr = unquote(parts[0])
				# strip trailing newline and quotes
				value = unquote(parts[1].rstrip(b'\n')[1:-1])
				xattr.set(pathname, attr, value)
			elif line.strip():
				raise ValueError('line %d: malformed entry' % (i + 1,))


def main(argv):

	parser = argparse.ArgumentParser(description=doc)
	parser.add_argument('paths', nargs='*', default=[])

	actions = parser.add_argument_group('Actions')
	actions.add_argument('--dump',
		action='store_true',
		help='Dump the values of all extended '
			'attributes associated with paths '
			'passed as arguments or null-separated '
			'paths read from stdin.')
	actions.add_argument('--restore',
		action='store_true',
		help='Restore extended attributes using '
			'a dump read from stdin.')

	options = parser.parse_args(argv)

	file_in = sys.stdin.buffer.raw

	if options.dump:
		if options.paths:
			options.paths = [unicode_encode(x) for x in options.paths]
		else:
			options.paths = [x for x in file_in.read().split(b'\0') if x]
		file_out = sys.stdout.buffer
		dump_xattrs(options.paths, file_out)

	elif options.restore:
		restore_xattrs(file_in)

	else:
		parser.error('missing action!')

	return os.EX_OK


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
