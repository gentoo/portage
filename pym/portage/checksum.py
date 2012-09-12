# checksum.py -- core Portage functionality
# Copyright 1998-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage.const import PRELINK_BINARY,HASHING_BLOCKSIZE
from portage.localization import _
from portage import os
from portage import _encodings
from portage import _unicode_encode
import errno
import stat
import sys
import subprocess
import tempfile

#dict of all available hash functions
hashfunc_map = {}
hashorigin_map = {}

def _open_file(filename):
	try:
		return open(_unicode_encode(filename,
			encoding=_encodings['fs'], errors='strict'), 'rb')
	except IOError as e:
		func_call = "open('%s')" % filename
		if e.errno == errno.EPERM:
			raise portage.exception.OperationNotPermitted(func_call)
		elif e.errno == errno.EACCES:
			raise portage.exception.PermissionDenied(func_call)
		elif e.errno == errno.ENOENT:
			raise portage.exception.FileNotFound(filename)
		else:
			raise

class _generate_hash_function(object):

	__slots__ = ("_hashobject",)

	def __init__(self, hashtype, hashobject, origin="unknown"):
		self._hashobject = hashobject
		hashfunc_map[hashtype] = self
		hashorigin_map[hashtype] = origin

	def __call__(self, filename):
		"""
		Run a checksum against a file.
	
		@param filename: File to run the checksum against
		@type filename: String
		@return: The hash and size of the data
		"""
		f = _open_file(filename)
		blocksize = HASHING_BLOCKSIZE
		data = f.read(blocksize)
		size = 0
		checksum = self._hashobject()
		while data:
			checksum.update(data)
			size = size + len(data)
			data = f.read(blocksize)
		f.close()

		return (checksum.hexdigest(), size)

# Define hash functions, try to use the best module available. Later definitions
# override earlier ones

# Use the internal modules as last fallback
try:
	from hashlib import md5 as _new_md5
except ImportError:
	from md5 import new as _new_md5

md5hash = _generate_hash_function("MD5", _new_md5, origin="internal")

try:
	from hashlib import sha1 as _new_sha1
except ImportError:
	from sha import new as _new_sha1

sha1hash = _generate_hash_function("SHA1", _new_sha1, origin="internal")

# Try to use mhash if available
# mhash causes GIL presently, so it gets less priority than hashlib and
# pycrypto. However, it might be the only accelerated implementation of
# WHIRLPOOL available.
try:
	import mhash, functools
	md5hash = _generate_hash_function("MD5", functools.partial(mhash.MHASH, mhash.MHASH_MD5), origin="mhash")
	sha1hash = _generate_hash_function("SHA1", functools.partial(mhash.MHASH, mhash.MHASH_SHA1), origin="mhash")
	sha256hash = _generate_hash_function("SHA256", functools.partial(mhash.MHASH, mhash.MHASH_SHA256), origin="mhash")
	sha512hash = _generate_hash_function("SHA512", functools.partial(mhash.MHASH, mhash.MHASH_SHA512), origin="mhash")
	for local_name, hash_name in (("rmd160", "ripemd160"), ("whirlpool", "whirlpool")):
		if hasattr(mhash, 'MHASH_%s' % local_name.upper()):
			globals()['%shash' % local_name] = \
				_generate_hash_function(local_name.upper(), \
				functools.partial(mhash.MHASH, getattr(mhash, 'MHASH_%s' % hash_name.upper())), \
				origin='mhash')
except ImportError:
	pass

# Use pycrypto when available, prefer it over the internal fallbacks
# Check for 'new' attributes, since they can be missing if the module
# is broken somehow.
try:
	from Crypto.Hash import SHA256, RIPEMD
	sha256hash = getattr(SHA256, 'new', None)
	if sha256hash is not None:
		sha256hash = _generate_hash_function("SHA256",
			sha256hash, origin="pycrypto")
	rmd160hash = getattr(RIPEMD, 'new', None)
	if rmd160hash is not None:
		rmd160hash = _generate_hash_function("RMD160",
			rmd160hash, origin="pycrypto")
except ImportError:
	pass

# Use hashlib from python-2.5 if available and prefer it over pycrypto and internal fallbacks.
# Need special handling for RMD160/WHIRLPOOL as they may not always be provided by hashlib.
try:
	import hashlib, functools
	
	md5hash = _generate_hash_function("MD5", hashlib.md5, origin="hashlib")
	sha1hash = _generate_hash_function("SHA1", hashlib.sha1, origin="hashlib")
	sha256hash = _generate_hash_function("SHA256", hashlib.sha256, origin="hashlib")
	sha512hash = _generate_hash_function("SHA512", hashlib.sha512, origin="hashlib")
	for local_name, hash_name in (("rmd160", "ripemd160"), ("whirlpool", "whirlpool")):
		try:
			hashlib.new(hash_name)
		except ValueError:
			pass
		else:
			globals()['%shash' % local_name] = \
				_generate_hash_function(local_name.upper(), \
				functools.partial(hashlib.new, hash_name), \
				origin='hashlib')

except ImportError:
	pass

_whirlpool_unaccelerated = False
if "WHIRLPOOL" not in hashfunc_map:
	# Bundled WHIRLPOOL implementation
	_whirlpool_unaccelerated = True
	from portage.util.whirlpool import new as _new_whirlpool
	whirlpoolhash = _generate_hash_function("WHIRLPOOL", _new_whirlpool, origin="bundled")

# Use python-fchksum if available, prefer it over all other MD5 implementations
try:
	from fchksum import fmd5t as md5hash
	hashfunc_map["MD5"] = md5hash
	hashorigin_map["MD5"] = "python-fchksum"

except ImportError:
	pass

# There is only one implementation for size
def getsize(filename):
	size = os.stat(filename).st_size
	return (size, size)
hashfunc_map["size"] = getsize

# end actual hash functions

prelink_capable = False
if os.path.exists(PRELINK_BINARY):
	cmd = [PRELINK_BINARY, "--version"]
	if sys.hexversion < 0x3000000 or sys.hexversion >= 0x3020000:
		# Python 3.1 does not support bytes in Popen args.
		cmd = [_unicode_encode(x, encoding=_encodings['fs'], errors='strict')
			for x in cmd]
	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT)
	proc.communicate()
	status = proc.wait()
	if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
		prelink_capable=1
	del cmd, proc, status

def is_prelinkable_elf(filename):
	f = _open_file(filename)
	try:
		magic = f.read(17)
	finally:
		f.close()
	return (len(magic) == 17 and magic.startswith(b'\x7fELF') and
		magic[16] in (b'\x02', b'\x03')) # 2=ET_EXEC, 3=ET_DYN

def perform_md5(x, calc_prelink=0):
	return perform_checksum(x, "MD5", calc_prelink)[0]

def _perform_md5_merge(x, **kwargs):
	return perform_md5(_unicode_encode(x,
		encoding=_encodings['merge'], errors='strict'), **kwargs)

def perform_all(x, calc_prelink=0):
	mydict = {}
	for k in hashfunc_map:
		mydict[k] = perform_checksum(x, k, calc_prelink)[0]
	return mydict

def get_valid_checksum_keys():
	return list(hashfunc_map)

def get_hash_origin(hashtype):
	if hashtype not in hashfunc_map:
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
		verifiable_hash_types = set(digests).intersection(hashfunc_map)
		verifiable_hash_types.discard("size")
		if len(verifiable_hash_types) > 1:
			digests = dict(digests)
			digests.pop("WHIRLPOOL")

	return digests

class _hash_filter(object):
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
			elif token[:1] == "-":
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

	verifiable_hash_types = set(digests).intersection(hashfunc_map)
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
		if mydict["size"] != mysize:
			return False,(_("Filesize does not match recorded size"), mysize, mydict["size"])
	except OSError as e:
		if e.errno == errno.ENOENT:
			raise portage.exception.FileNotFound(filename)
		return False, (str(e), None, None)

	verifiable_hash_types = set(mydict).intersection(hashfunc_map)
	verifiable_hash_types.discard("size")
	if not verifiable_hash_types:
		expected = set(hashfunc_map)
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
		elif x in hashfunc_map:
			myhash = perform_checksum(filename, x, calc_prelink=calc_prelink)[0]
			if mydict[x] != myhash:
				if strict:
					raise portage.exception.DigestException(
						("Failed to verify '$(file)s' on " + \
						"checksum type '%(type)s'") % \
						{"file" : filename, "type" : x})
				else:
					file_is_ok = False
					reason     = (("Failed on %s verification" % x), myhash,mydict[x])
					break
	return file_is_ok,reason

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
			if hashname not in hashfunc_map:
				raise portage.exception.DigestException(hashname + \
					" hash function not available (needs dev-python/pycrypto)")
			myhash, mysize = hashfunc_map[hashname](myfilename)
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
		if x not in hashfunc_map:
			raise portage.exception.DigestException(x+" hash function not available (needs dev-python/pycrypto or >=dev-lang/python-2.5)")
		rVal[x] = perform_checksum(filename, x, calc_prelink)[0]
	return rVal
