#!/usr/bin/python
# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import array
import optparse
import os
import re
import sys

if hasattr(os, "getxattr"):

	class xattr(object):
		get = os.getxattr
		set = os.setxattr
		list = os.listxattr

else:
	import xattr

_unquote_re = re.compile(br'\\[0-7]{3}')
_fs_encoding = sys.getfilesystemencoding()

if sys.hexversion < 0x3000000:

	def octal_quote_byte(b):
		return b'\\%03o' % ord(b)

	def unicode_encode(s):
		if isinstance(s, unicode):
			s = s.encode(_fs_encoding)
		return s
else:

	def octal_quote_byte(b):
		return ('\\%03o' % ord(b)).encode('ascii')

	def unicode_encode(s):
		if isinstance(s, str):
			s = s.encode(_fs_encoding)
		return s

def quote(s, quote_chars):

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

	return b"".join(result)

def unquote(s):

	result = []
	pos = 0
	s_len = len(s)

	while pos < s_len:
		m = _unquote_re.search(s, pos=pos)
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

	return b"".join(result)

def dump_xattrs(file_in, file_out):

	for pathname in file_in.read().split(b'\0'):
		if not pathname:
			continue

		attrs = xattr.list(pathname)
		if not attrs:
			continue

		# NOTE: Always quote backslashes, in order to ensure that they are
		# not interpreted as quotes when they are processed by unquote.
		file_out.write(b'# file: ' + quote(pathname, b'\n\r\\\\') + b'\n')
		for attr in attrs:
			attr = unicode_encode(attr)
			file_out.write(quote(attr, b'=\n\r\\\\') + b'="' +
				quote(xattr.get(pathname, attr), b'\0\n\r"\\\\') + b'"\n')

def restore_xattrs(file_in):

	pathname = None
	for i, line in enumerate(file_in):
		if line.startswith(b'# file: '):
			pathname = unquote(line.rstrip(b'\n')[8:])
		else:
			parts = line.split(b'=', 1)
			if len(parts) == 2:
				if pathname is None:
					raise AssertionError('line %d: missing pathname' % (i + 1,))
				attr = unquote(parts[0])
				# strip trailing newline and quotes 
				value = unquote(parts[1].rstrip(b'\n')[1:-1])
				xattr.set(pathname, attr, value)
			elif line.strip():
				raise AssertionError("line %d: malformed entry" % (i + 1,))

def main(argv):

	description = "Dump and restore extended attributes," \
		" using format like that used by getfattr --dump."
	usage = "usage: %s [--dump | --restore]\n" % \
		os.path.basename(argv[0])

	parser = optparse.OptionParser(description=description, usage=usage)

	actions = optparse.OptionGroup(parser, 'Actions')
	actions.add_option("--dump",
		action="store_true",
		help="Dump the values of all extended "
			"attributes associated with null-separated"
			" paths read from stdin.")
	actions.add_option("--restore",
		action="store_true",
		help="Restore extended attributes using"
			" a dump read from stdin.")
	parser.add_option_group(actions)

	options, args = parser.parse_args(argv[1:])

	if len(args) != 0:
		parser.error("expected zero arguments, "
			"got %s" % len(args))

	if sys.hexversion >= 0x3000000:
		file_in = sys.stdin.buffer.raw
	else:
		file_in = sys.stdin

	if options.dump:

		if sys.hexversion >= 0x3000000:
			file_out = sys.stdout.buffer
		else:
			file_out = sys.stdout

		dump_xattrs(file_in, file_out)

	elif options.restore:

		restore_xattrs(file_in)

	else:
		parser.error("available actions: --dump, --restore")

	return os.EX_OK

if __name__ == "__main__":
	rval = main(sys.argv[:])
	sys.exit(rval)
