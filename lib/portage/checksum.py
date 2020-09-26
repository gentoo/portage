# checksum.py -- core Portage functionality
# Copyright 1998-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# pylint: disable=ungrouped-imports

import errno
import functools
import hashlib
import portage
import stat
import subprocess
import tempfile

from portage import _encodings, _unicode_decode, _unicode_encode
from portage import os
from portage.const import HASHING_BLOCKSIZE, PRELINK_BINARY
from portage.localization import _


# Summary of all available hashes and their implementations,
# most preferred first. Please keep this in sync with logic below.
# ================================================================
#
# MD5: hashlib
# SHA1: hashlib
# SHA256: hashlib
# SHA512: hashlib
# RMD160: hashlib, pycrypto, mhash
# WHIRLPOOL: hashlib, mhash, bundled
# BLAKE2B (512): hashlib (3.6+), pyblake2, pycrypto
# BLAKE2S (512): hashlib (3.6+), pyblake2, pycrypto
# SHA3_256: hashlib (3.6+), pysha3, pycrypto
# SHA3_512: hashlib (3.6+), pysha3, pycrypto


# Dict of all available hash functions
hashfunc_map = {}
hashorigin_map = {}

def _open_file(filename):
	try:
		return open(_unicode_encode(filename,
			encoding=_encodings['fs'], errors='strict'), 'rb')
	except IOError as e:
		func_call = "open('%s')" % _unicode_decode(filename)
		if e.errno == errno.EPERM:
			raise portage.exception.OperationNotPermitted(func_call)
		elif e.errno == errno.EACCES:
			raise portage.exception.PermissionDenied(func_call)
		elif e.errno == errno.ENOENT:
			raise portage.exception.FileNotFound(filename)
		else:
			raise

class _generate_hash_function:

	__slots__ = ("_hashobject",)

	def __init__(self, hashtype, hashobject, origin="unknown"):
		self._hashobject = hashobject
		hashfunc_map[hashtype] = self
		hashorigin_map[hashtype] = origin

	def checksum_str(self, data):
		"""
		Obtain a checksum of a byte-string.

		@param data: Data to hash
		@type data: bytes
		@return: The hash of the data (hex-digest)
		"""
		checksum = self._hashobject()
		checksum.update(data)
		return checksum.hexdigest()

	def checksum_file(self, filename):
		"""
		Run a checksum against a file.

		@param filename: File to run the checksum against
		@type filename: String
		@return: The hash and size of the data
		"""
		with _open_file(filename) as f:
			blocksize = HASHING_BLOCKSIZE
			size = 0
			checksum = self._hashobject()
			data = f.read(blocksize)
			while data:
				checksum.update(data)
				size = size + len(data)
				data = f.read(blocksize)

		return (checksum.hexdigest(), size)


# Define hash functions, try to use the best module available. Preferred
# modules should go first, latter ones should check if the hashes aren't
# already defined.


# Use hashlib from python-2.5 if available and prefer it over pycrypto and internal fallbacks.
# Need special handling for RMD160/WHIRLPOOL as they may not always be provided by hashlib.
_generate_hash_function("MD5", hashlib.md5, origin="hashlib")
_generate_hash_function("SHA1", hashlib.sha1, origin="hashlib")
_generate_hash_function("SHA256", hashlib.sha256, origin="hashlib")
_generate_hash_function("SHA512", hashlib.sha512, origin="hashlib")
for local_name, hash_name in (
		("RMD160", "ripemd160"),
		("WHIRLPOOL", "whirlpool"),
		# available since Python 3.6
		("BLAKE2B", "blake2b"),
		("BLAKE2S", "blake2s"),
		("SHA3_256", "sha3_256"),
		("SHA3_512", "sha3_512"),
		):
	try:
		hashlib.new(hash_name)
	except ValueError:
		pass
	else:
		_generate_hash_function(local_name,
			functools.partial(hashlib.new, hash_name),
			origin='hashlib')


# Support using pyblake2 as fallback for python<3.6
if "BLAKE2B" not in hashfunc_map or "BLAKE2S" not in hashfunc_map:
	try:
		import pyblake2

		_generate_hash_function("BLAKE2B", pyblake2.blake2b, origin="pyblake2")
		_generate_hash_function("BLAKE2S", pyblake2.blake2s, origin="pyblake2")
	except ImportError:
		pass


# Support using pysha3 as fallback for python<3.6
if "SHA3_256" not in hashfunc_map or "SHA3_512" not in hashfunc_map:
	try:
		import sha3

		_generate_hash_function("SHA3_256", sha3.sha3_256, origin="pysha3")
		_generate_hash_function("SHA3_512", sha3.sha3_512, origin="pysha3")
	except ImportError:
		pass


# Support pygcrypt as fallback using optimized routines from libgcrypt
# (GnuPG).
gcrypt_algos = frozenset(('RMD160', 'WHIRLPOOL', 'SHA3_256', 'SHA3_512',
	'STREEBOG256', 'STREEBOG512'))
# Note: currently disabled due to resource exhaustion bugs in pygcrypt.
# Please do not reenable until upstream has a fix.
# https://bugs.gentoo.org/615620
if False:
#if gcrypt_algos.difference(hashfunc_map):
	try:
		import binascii
		import pygcrypt.hashcontext

		class GCryptHashWrapper:
			def __init__(self, algo):
				self._obj = pygcrypt.hashcontext.HashContext(algo=algo,
						secure=False)

			def update(self, data):
				self._obj.write(data)

			def hexdigest(self):
				return binascii.b2a_hex(self._obj.read()).decode()

		name_mapping = {
			'RMD160': 'ripemd160',
			'WHIRLPOOL': 'whirlpool',
			'SHA3_256': 'sha3-256',
			'SHA3_512': 'sha3-512',
			'STREEBOG256': 'stribog256',
			'STREEBOG512': 'stribog512',
		}

		for local_name, gcry_name in name_mapping.items():
			try:
				pygcrypt.hashcontext.HashContext(algo=gcry_name)
			except Exception: # yes, it throws Exception...
				pass
			else:
				_generate_hash_function(local_name,
						functools.partial(GCryptHashWrapper, gcry_name),
						origin="pygcrypt")
	except ImportError:
		pass


# Use pycrypto when available, prefer it over the internal fallbacks
# Check for 'new' attributes, since they can be missing if the module
# is broken somehow.
if 'RMD160' not in hashfunc_map:
	try:
		from Crypto.Hash import RIPEMD
		rmd160hash_ = getattr(RIPEMD, 'new', None)
		if rmd160hash_ is not None:
			_generate_hash_function("RMD160",
				rmd160hash_, origin="pycrypto")
	except ImportError:
		pass

# The following hashes were added in pycryptodome (pycrypto fork)
if 'BLAKE2B' not in hashfunc_map:
	try:
		from Crypto.Hash import BLAKE2b
		blake2bhash_ = getattr(BLAKE2b, 'new', None)
		if blake2bhash_ is not None:
			_generate_hash_function("BLAKE2B",
				functools.partial(blake2bhash_, digest_bytes=64), origin="pycrypto")
	except ImportError:
		pass

if 'BLAKE2S' not in hashfunc_map:
	try:
		from Crypto.Hash import BLAKE2s
		blake2shash_ = getattr(BLAKE2s, 'new', None)
		if blake2shash_ is not None:
			_generate_hash_function("BLAKE2S",
				functools.partial(blake2shash_, digest_bytes=32), origin="pycrypto")
	except ImportError:
		pass

if 'SHA3_256' not in hashfunc_map:
	try:
		from Crypto.Hash import SHA3_256
		sha3_256hash_ = getattr(SHA3_256, 'new', None)
		if sha3_256hash_ is not None:
			_generate_hash_function("SHA3_256",
				sha3_256hash_, origin="pycrypto")
	except ImportError:
		pass

if 'SHA3_512' not in hashfunc_map:
	try:
		from Crypto.Hash import SHA3_512
		sha3_512hash_ = getattr(SHA3_512, 'new', None)
		if sha3_512hash_ is not None:
			_generate_hash_function("SHA3_512",
				sha3_512hash_, origin="pycrypto")
	except ImportError:
		pass


# Try to use mhash if available
# mhash causes GIL presently, so it gets less priority than hashlib and
# pycrypto. However, it might be the only accelerated implementation of
# WHIRLPOOL available.
if 'RMD160' not in hashfunc_map or 'WHIRLPOOL' not in hashfunc_map:
	try:
		import mhash
		for local_name, hash_name in (("RMD160", "RIPEMD160"), ("WHIRLPOOL", "WHIRLPOOL")):
			if local_name not in hashfunc_map and hasattr(mhash, 'MHASH_%s' % hash_name):
				_generate_hash_function(local_name,
					functools.partial(mhash.MHASH, getattr(mhash, 'MHASH_%s' % hash_name)),
					origin='mhash')
	except ImportError:
		pass


# Support pygost as fallback streebog provider
# It's mostly provided as a reference implementation; it's pure Python,
# slow and reads all data to memory (i.e. doesn't hash on update()...)
if 'STREEBOG256' not in hashfunc_map or 'STREEBOG512' not in hashfunc_map:
	try:
		import pygost.gost34112012

		_generate_hash_function("STREEBOG256",
			functools.partial(pygost.gost34112012.GOST34112012, digest_size=32), origin="pygost")
		_generate_hash_function("STREEBOG512",
			functools.partial(pygost.gost34112012.GOST34112012, digest_size=64), origin="pygost")
	except ImportError:
		pass


_whirlpool_unaccelerated = False
if "WHIRLPOOL" not in hashfunc_map:
	# Bundled WHIRLPOOL implementation
	_whirlpool_unaccelerated = True
	from portage.util.whirlpool import new as _new_whirlpool
	_generate_hash_function("WHIRLPOOL", _new_whirlpool, origin="bundled")


# There is only one implementation for size
class SizeHash:
	def checksum_file(self, filename):
		size = os.stat(filename).st_size
		return (size, size)

hashfunc_map["size"] = SizeHash()

# cache all supported hash methods in a frozenset
hashfunc_keys = frozenset(hashfunc_map)

# end actual hash functions


prelink_capable = False
if os.path.exists(PRELINK_BINARY):
	cmd = [PRELINK_BINARY, "--version"]
	cmd = [_unicode_encode(x, encoding=_encodings['fs'], errors='strict')
		for x in cmd]
	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT)
	proc.communicate()
	status = proc.wait()
	if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
		prelink_capable = 1
	del cmd, proc, status

def is_prelinkable_elf(filename):
	f = _open_file(filename)
	try:
		magic = f.read(17)
	finally:
		f.close()
	return (len(magic) == 17 and magic.startswith(b'\x7fELF') and
		magic[16:17] in (b'\x02', b'\x03')) # 2=ET_EXEC, 3=ET_DYN

def perform_md5(x, calc_prelink=0):
	return perform_checksum(x, "MD5", calc_prelink)[0]

def _perform_md5_merge(x, **kwargs):
	return perform_md5(_unicode_encode(x,
		encoding=_encodings['merge'], errors='strict'), **kwargs)

def perform_all(x, calc_prelink=0):
	mydict = {}
	for k in hashfunc_keys:
		mydict[k] = perform_checksum(x, k, calc_prelink)[0]
	return mydict

def get_valid_checksum_keys():
	return hashfunc_keys

def get_hash_origin(hashtype):
	if hashtype not in hashfunc_keys:
		raise KeyError(hashtype)
	return hashorigin_map.get(hashtype, "unknown")

def _filter_unaccelarated_hashes(digests):
	"""
	If multiple digests are available and some are unaccelerated,
	then return a new dict that omits the unaccelerated ones. This
	allows extreme performance problems like bug #425046 to be
	avoided whenever practical, especially for cases like stage
	builds where acceleration may not be available for some hashes
	due to minimization of dependencies.
	"""
	if _whirlpool_unaccelerated and "WHIRLPOOL" in digests:
		verifiable_hash_types = set(digests).intersection(hashfunc_keys)
		verifiable_hash_types.discard("size")
		if len(verifiable_hash_types) > 1:
			digests = dict(digests)
			digests.pop("WHIRLPOOL")

	return digests

class _hash_filter:
	"""
	Implements filtering for PORTAGE_CHECKSUM_FILTER.
	"""

	__slots__ = ('transparent', '_tokens',)

	def __init__(self, filter_str):
		tokens = filter_str.upper().split()
		if not tokens or tokens[-1] == "*":
			del tokens[:]
		self.transparent = not tokens
		tokens.reverse()
		self._tokens = tuple(tokens)

	def __call__(self, hash_name):
		if self.transparent:
			return True
		matches = ("*", hash_name)
		for token in self._tokens:
			if token in matches:
				return True
			if token[:1] == "-":
				if token[1:] in matches:
					return False
		return False

def _apply_hash_filter(digests, hash_filter):
	"""
	Return a new dict containing the filtered digests, or the same
	dict if no changes are necessary. This will always preserve at
	at least one digest, in order to ensure that they are not all
	discarded.
	@param digests: dictionary of digests
	@type digests: dict
	@param hash_filter: A callable that takes a single hash name
		argument, and returns True if the hash is to be used or
		False otherwise
	@type hash_filter: callable
	"""

	verifiable_hash_types = set(digests).intersection(hashfunc_keys)
	verifiable_hash_types.discard("size")
	modified = False
	if len(verifiable_hash_types) > 1:
		for k in list(verifiable_hash_types):
			if not hash_filter(k):
				modified = True
				verifiable_hash_types.remove(k)
				if len(verifiable_hash_types) == 1:
					break

	if modified:
		digests = dict((k, v) for (k, v) in digests.items()
			if k == "size" or k in verifiable_hash_types)

	return digests

def verify_all(filename, mydict, calc_prelink=0, strict=0):
	"""
	Verify all checksums against a file.

	@param filename: File to run the checksums against
	@type filename: String
	@param calc_prelink: Whether or not to reverse prelink before running the checksum
	@type calc_prelink: Integer
	@param strict: Enable/Disable strict checking (which stops exactly at a checksum failure and throws an exception)
	@type strict: Integer
	@rtype: Tuple
	@return: Result of the checks and possible message:
		1) If size fails, False, and a tuple containing a message, the given size, and the actual size
		2) If there is an os error, False, and a tuple containing the system error followed by 2 nulls
		3) If a checksum fails, False and a tuple containing a message, the given hash, and the actual hash
		4) If all checks succeed, return True and a fake reason
	"""
	# Dict relates to single file only.
	# returns: (passed,reason)
	file_is_ok = True
	reason     = "Reason unknown"
	try:
		mysize = os.stat(filename)[stat.ST_SIZE]
		if mydict.get("size") is not None and mydict["size"] != mysize:
			return False,(_("Filesize does not match recorded size"), mysize, mydict["size"])
	except OSError as e:
		if e.errno == errno.ENOENT:
			raise portage.exception.FileNotFound(filename)
		return False, (str(e), None, None)

	verifiable_hash_types = set(mydict).intersection(hashfunc_keys)
	verifiable_hash_types.discard("size")
	if not verifiable_hash_types:
		expected = set(hashfunc_keys)
		expected.discard("size")
		expected = list(expected)
		expected.sort()
		expected = " ".join(expected)
		got = set(mydict)
		got.discard("size")
		got = list(got)
		got.sort()
		got = " ".join(got)
		return False, (_("Insufficient data for checksum verification"), got, expected)

	for x in sorted(mydict):
		if   x == "size":
			continue
		elif x in hashfunc_keys:
			myhash = perform_checksum(filename, x, calc_prelink=calc_prelink)[0]
			if mydict[x] != myhash:
				if strict:
					raise portage.exception.DigestException(
						("Failed to verify '$(file)s' on " + \
						"checksum type '%(type)s'") % \
						{"file" : filename, "type" : x})
				else:
					file_is_ok = False
					reason = (("Failed on %s verification" % x), myhash, mydict[x])
					break

	return file_is_ok, reason

def perform_checksum(filename, hashname="MD5", calc_prelink=0):
	"""
	Run a specific checksum against a file. The filename can
	be either unicode or an encoded byte string. If filename
	is unicode then a UnicodeDecodeError will be raised if
	necessary.

	@param filename: File to run the checksum against
	@type filename: String
	@param hashname: The type of hash function to run
	@type hashname: String
	@param calc_prelink: Whether or not to reverse prelink before running the checksum
	@type calc_prelink: Integer
	@rtype: Tuple
	@return: The hash and size of the data
	"""
	global prelink_capable
	# Make sure filename is encoded with the correct encoding before
	# it is passed to spawn (for prelink) and/or the hash function.
	filename = _unicode_encode(filename,
		encoding=_encodings['fs'], errors='strict')
	myfilename = filename
	prelink_tmpfile = None
	try:
		if (calc_prelink and prelink_capable and
		    is_prelinkable_elf(filename)):
			# Create non-prelinked temporary file to checksum.
			# Files rejected by prelink are summed in place.
			try:
				tmpfile_fd, prelink_tmpfile = tempfile.mkstemp()
				try:
					retval = portage.process.spawn([PRELINK_BINARY,
						"--verify", filename], fd_pipes={1:tmpfile_fd})
				finally:
					os.close(tmpfile_fd)
				if retval == os.EX_OK:
					myfilename = prelink_tmpfile
			except portage.exception.CommandNotFound:
				# This happens during uninstallation of prelink.
				prelink_capable = False
		try:
			if hashname not in hashfunc_keys:
				raise portage.exception.DigestException(hashname + \
					" hash function not available (needs dev-python/pycrypto)")
			myhash, mysize = hashfunc_map[hashname].checksum_file(myfilename)
		except (OSError, IOError) as e:
			if e.errno in (errno.ENOENT, errno.ESTALE):
				raise portage.exception.FileNotFound(myfilename)
			elif e.errno == portage.exception.PermissionDenied.errno:
				raise portage.exception.PermissionDenied(myfilename)
			raise
		return myhash, mysize
	finally:
		if prelink_tmpfile:
			try:
				os.unlink(prelink_tmpfile)
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e

def perform_multiple_checksums(filename, hashes=["MD5"], calc_prelink=0):
	"""
	Run a group of checksums against a file.

	@param filename: File to run the checksums against
	@type filename: String
	@param hashes: A list of checksum functions to run against the file
	@type hashname: List
	@param calc_prelink: Whether or not to reverse prelink before running the checksum
	@type calc_prelink: Integer
	@rtype: Tuple
	@return: A dictionary in the form:
		return_value[hash_name] = (hash_result,size)
		for each given checksum
	"""
	rVal = {}
	for x in hashes:
		if x not in hashfunc_keys:
			raise portage.exception.DigestException(x+" hash function not available (needs dev-python/pycrypto or >=dev-lang/python-2.5)")
		rVal[x] = perform_checksum(filename, x, calc_prelink)[0]
	return rVal


def checksum_str(data, hashname="MD5"):
	"""
	Run a specific checksum against a byte string.

	@param filename: Data to checksum
	@type filename: Bytes
	@param hashname: The type of hash function to run
	@type hashname: String
	@rtype: String
	@return: The hash (hex-digest) of the data
	"""
	if hashname not in hashfunc_keys:
		raise portage.exception.DigestException(hashname + \
			" hash function not available (needs dev-python/pycrypto)")
	return hashfunc_map[hashname].checksum_str(data)
