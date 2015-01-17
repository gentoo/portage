# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import re
import sys

if sys.hexversion >= 0x3000000:
	basestring = str

from portage import _encodings, _unicode_encode
from portage.exception import FileNotFound, PermissionDenied

_decompressors = {
	"bzip2": "${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d}",
	"gzip": "gzip -d",
	"lz4": "lz4 -d",
	"lzip": "lzip -d",
	"lzop": "lzop -d",
	"xz": "xz -d",
}

_compression_re = re.compile(b'^(' +
	b'(?P<bzip2>\x42\x5a\x68\x39)|' +
	b'(?P<gzip>\x1f\x8b)|' +
	b'(?P<lz4>(?:\x04\x22\x4d\x18|\x02\x21\x4c\x18))|' +
	b'(?P<lzip>LZIP)|' +
	b'(?P<lzop>\x89LZO\x00\x0d\x0a\x1a\x0a)|' +
	b'(?P<xz>\xfd\x37\x7a\x58\x5a\x00))')

_max_compression_re_len = 9

def compression_probe(f):
	"""
	Identify the compression type of a file. Returns one of the
	following identifier strings:

		bzip2
		gzip
		lz4
		lzip
		lzop
		xz

	@param f: a file path, or file-like object
	@type f: str or file
	@return: a string identifying the compression type, or None if the
		compression type is unrecognized
	@rtype str or None
	"""

	open_file = isinstance(f, basestring)
	if open_file:
		try:
			f = open(_unicode_encode(f,
				encoding=_encodings['fs'], errors='strict'), mode='rb')
		except IOError as e:
			if e.errno == PermissionDenied.errno:
				raise PermissionDenied(f)
			elif e.errno in (errno.ENOENT, errno.ESTALE):
				raise FileNotFound(f)
			else:
				raise

	try:
		return _compression_probe_file(f)
	finally:
		if open_file:
			f.close()

def _compression_probe_file(f):

	m = _compression_re.match(f.read(_max_compression_re_len))
	if m is not None:
		for k, v in m.groupdict().items():
			if v is not None:
				return k

	return None
