# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import codecs

_codec_map = None

def _setup_encodings(default_encoding, filesystem_encoding, missing_encodings):
	"""
	The <python-2.6.4 that's inside stage 1 or 2 is built with a minimal
	configuration which does not include the /usr/lib/pythonX.Y/encodings
	directory. This results in error like the following:

	  LookupError: no codec search functions registered: can't find encoding

	In order to solve this problem, detect it early and manually register
	a search function for the ascii and utf_8 codecs. Starting with python-3.0
	this problem is more noticeable because of stricter handling of encoding
	and decoding between strings of characters and bytes.
	"""

	global _codec_map
	_codec_map = _gen_missing_encodings(missing_encodings)

	default_fallback = 'utf_8'

	if default_encoding in missing_encodings and \
		default_encoding not in _codec_map:
		# Make the fallback codec correspond to whatever name happens
		# to be returned by sys.getfilesystemencoding().

		try:
			_codec_map[default_encoding] = codecs.lookup(default_fallback)
		except LookupError:
			_codec_map[default_encoding] = _codec_map[default_fallback]

	if filesystem_encoding in missing_encodings and \
		filesystem_encoding not in _codec_map:
		# Make the fallback codec correspond to whatever name happens
		# to be returned by sys.getdefaultencoding().

		try:
			_codec_map[filesystem_encoding] = codecs.lookup(default_fallback)
		except LookupError:
			_codec_map[filesystem_encoding] = _codec_map[default_fallback]

	codecs.register(_search_function)

def _gen_missing_encodings(missing_encodings):

	codec_map = {}

	if 'ascii' in missing_encodings:

		class AsciiIncrementalEncoder(codecs.IncrementalEncoder):
			def encode(self, input, final=False):
				return codecs.ascii_encode(input, self.errors)[0]

		class AsciiIncrementalDecoder(codecs.IncrementalDecoder):
			def decode(self, input, final=False):
				return codecs.ascii_decode(input, self.errors)[0]

		class AsciiStreamWriter(codecs.StreamWriter):
			encode = codecs.ascii_encode

		class AsciiStreamReader(codecs.StreamReader):
			decode = codecs.ascii_decode

		codec_info =  codecs.CodecInfo(
			name='ascii',
			encode=codecs.ascii_encode,
			decode=codecs.ascii_decode,
			incrementalencoder=AsciiIncrementalEncoder,
			incrementaldecoder=AsciiIncrementalDecoder,
			streamwriter=AsciiStreamWriter,
			streamreader=AsciiStreamReader,
		)

		for alias in ('ascii', '646', 'ansi_x3.4_1968', 'ansi_x3_4_1968',
			'ansi_x3.4_1986', 'cp367', 'csascii', 'ibm367', 'iso646_us',
			'iso_646.irv_1991', 'iso_ir_6', 'us', 'us_ascii'):
			codec_map[alias] = codec_info

	if 'utf_8' in missing_encodings:

		def utf8decode(input, errors='strict'):
			return codecs.utf_8_decode(input, errors, True)

		class Utf8IncrementalEncoder(codecs.IncrementalEncoder):
			def encode(self, input, final=False):
				return codecs.utf_8_encode(input, self.errors)[0]

		class Utf8IncrementalDecoder(codecs.BufferedIncrementalDecoder):
			_buffer_decode = codecs.utf_8_decode

		class Utf8StreamWriter(codecs.StreamWriter):
			encode = codecs.utf_8_encode

		class Utf8StreamReader(codecs.StreamReader):
			decode = codecs.utf_8_decode

		codec_info = codecs.CodecInfo(
			name='utf-8',
			encode=codecs.utf_8_encode,
			decode=utf8decode,
			incrementalencoder=Utf8IncrementalEncoder,
			incrementaldecoder=Utf8IncrementalDecoder,
			streamreader=Utf8StreamReader,
			streamwriter=Utf8StreamWriter,
		)

		for alias in ('utf_8', 'u8', 'utf', 'utf8', 'utf8_ucs2', 'utf8_ucs4'):
			codec_map[alias] = codec_info

	return codec_map

def _search_function(name):
	global _codec_map
	name = name.lower()
	name = name.replace('-', '_')
	codec_info = _codec_map.get(name)
	if codec_info is not None:
		return codecs.CodecInfo(
			name=codec_info.name,
			encode=codec_info.encode,
			decode=codec_info.decode,
			incrementalencoder=codec_info.incrementalencoder,
			incrementaldecoder=codec_info.incrementaldecoder,
			streamreader=codec_info.streamreader,
			streamwriter=codec_info.streamwriter,
		)
	return None
