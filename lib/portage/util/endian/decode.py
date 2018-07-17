# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import struct

def decode_uint16_be(data):
	"""
	Decode an unsigned 16-bit integer with big-endian encoding.

	@param data: string of bytes of length 2
	@type data: bytes
	@rtype: int
	@return: unsigned integer value of the decoded data
	"""
	return struct.unpack_from(">H", data)[0]

def decode_uint16_le(data):
	"""
	Decode an unsigned 16-bit integer with little-endian encoding.

	@param data: string of bytes of length 2
	@type data: bytes
	@rtype: int
	@return: unsigned integer value of the decoded data
	"""
	return struct.unpack_from("<H", data)[0]

def decode_uint32_be(data):
	"""
	Decode an unsigned 32-bit integer with big-endian encoding.

	@param data: string of bytes of length 4
	@type data: bytes
	@rtype: int
	@return: unsigned integer value of the decoded data
	"""
	return struct.unpack_from(">I", data)[0]

def decode_uint32_le(data):
	"""
	Decode an unsigned 32-bit integer with little-endian encoding.

	@param data: string of bytes of length 4
	@type data: bytes
	@rtype: int
	@return: unsigned integer value of the decoded data
	"""
	return struct.unpack_from("<I", data)[0]
