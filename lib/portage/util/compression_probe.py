# Copyright 2015-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import ctypes
import errno
import re


from portage import _encodings, _unicode_encode
from portage.exception import FileNotFound, PermissionDenied

_compressors = {
	"bzip2": {
		"compress": "${PORTAGE_BZIP2_COMMAND} ${BINPKG_COMPRESS_FLAGS}",
		"decompress": "${PORTAGE_BUNZIP2_COMMAND}",
		"decompress_alt": "${PORTAGE_BZIP2_COMMAND} -d",
		"package": "app-arch/bzip2",
	},
	"gzip": {
		"compress": "gzip ${BINPKG_COMPRESS_FLAGS}",
		"decompress": "gzip -d",
		"package": "app-arch/gzip",
	},
	"lz4": {
		"compress": "lz4 ${BINPKG_COMPRESS_FLAGS}",
		"decompress": "lz4 -d",
		"package": "app-arch/lz4",
	},
	"lzip": {
		"compress": "lzip ${BINPKG_COMPRESS_FLAGS}",
		"decompress": "lzip -d",
		"package": "app-arch/lzip",
	},
	"lzop": {
		"compress": "lzop ${BINPKG_COMPRESS_FLAGS}",
		"decompress": "lzop -d",
		"package": "app-arch/lzop",
	},
	"xz": {
		"compress": "xz ${BINPKG_COMPRESS_FLAGS}",
		"decompress": "xz -d",
		"package": "app-arch/xz-utils",
	},
	"zstd": {
		"compress": "zstd ${BINPKG_COMPRESS_FLAGS}",
		# If the compression windowLog was larger than the default of 27,
		# then --long=windowLog needs to be passed to the decompressor.
		# Therefore, pass a larger --long=31 value to the decompressor
		# if the current architecture can support it, which is true when
		# sizeof(long) is at least 8 bytes.
		"decompress": "zstd -d" + (" --long=31" if ctypes.sizeof(ctypes.c_long) >= 8 else ""),
		"package": "app-arch/zstd",
	},
}

_compression_re = re.compile(b'^(' +
	b'(?P<bzip2>\x42\x5a\x68\x39)|' +
	b'(?P<gzip>\x1f\x8b)|' +
	b'(?P<lz4>(?:\x04\x22\x4d\x18|\x02\x21\x4c\x18))|' +
	b'(?P<lzip>LZIP)|' +
	b'(?P<lzop>\x89LZO\x00\x0d\x0a\x1a\x0a)|' +
	b'(?P<xz>\xfd\x37\x7a\x58\x5a\x00)|' +
	b'(?P<zstd>([\x22-\x28]\xb5\x2f\xfd)))')

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
		zstd

	@param f: a file path, or file-like object
	@type f: str or file
	@return: a string identifying the compression type, or None if the
		compression type is unrecognized
	@rtype str or None
	"""

	open_file = isinstance(f, str)
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
