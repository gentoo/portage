# checksum.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.const import PRIVATE_PATH,PRELINK_BINARY,HASHING_BLOCKSIZE
import os
import errno
import stat
import tempfile
import portage.exception
import portage.process
import commands

#dict of all available hash functions
hashfunc_map = {}
hashorigin_map = {}

def _generate_hash_function(hashtype, hashobject, origin="unknown"):
	def pyhash(filename):
		"""
		Run a checksum against a file.
	
		@param filename: File to run the checksum against
		@type filename: String
		@return: The hash and size of the data
		"""
		f = open(filename, 'rb')
		blocksize = HASHING_BLOCKSIZE
		data = f.read(blocksize)
		size = 0L
		checksum = hashobject()
		while data:
			checksum.update(data)
			size = size + len(data)
			data = f.read(blocksize)
		f.close()

		return (checksum.hexdigest(), size)
	hashfunc_map[hashtype] = pyhash
	hashorigin_map[hashtype] = origin
	return pyhash

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

# Use pycrypto when available, prefer it over the internal fallbacks
try:
	from Crypto.Hash import MD5, SHA, SHA256, RIPEMD
	
	md5hash = _generate_hash_function("MD5", MD5.new, origin="pycrypto")
	sha1hash = _generate_hash_function("SHA1", SHA.new, origin="pycrypto")
	sha256hash = _generate_hash_function("SHA256", SHA256.new, origin="pycrypto")
	rmd160hash = _generate_hash_function("RMD160", RIPEMD.new, origin="pycrypto")
except ImportError, e:
	pass

# Use hashlib from python-2.5 if available and prefer it over pycrypto and internal fallbacks.
# Need special handling for RMD160 as it may not always be provided by hashlib.
try:
	import hashlib
	
	md5hash = _generate_hash_function("MD5", hashlib.md5, origin="hashlib")
	sha1hash = _generate_hash_function("SHA1", hashlib.sha1, origin="hashlib")
	sha256hash = _generate_hash_function("SHA256", hashlib.sha256, origin="hashlib")
	try:
		hashlib.new('ripemd160')
	except ValueError:
		pass
	else:
		def rmd160():
			return hashlib.new('ripemd160')
		rmd160hash = _generate_hash_function("RMD160", rmd160, origin="hashlib")
except ImportError, e:
	pass
	

# Use python-fchksum if available, prefer it over all other MD5 implementations
try:
	import fchksum
	
	def md5hash(filename):
		return fchksum.fmd5t(filename)
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
	results = commands.getstatusoutput(PRELINK_BINARY+" --version > /dev/null 2>&1")
	if (results[0] >> 8) == 0:
		prelink_capable=1
	del results

def perform_md5(x, calc_prelink=0):
	return perform_checksum(x, "MD5", calc_prelink)[0]

def perform_all(x, calc_prelink=0):
	mydict = {}
	for k in hashfunc_map:
		mydict[k] = perform_checksum(x, hashfunc_map[k], calc_prelink)[0]
	return mydict

def get_valid_checksum_keys():
	return hashfunc_map.keys()

def get_hash_origin(hashtype):
	if hashtype not in hashfunc_map:
		raise KeyError(hashtype)
	return hashorigin_map.get(hashtype, "unknown")

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
			return False,("Filesize does not match recorded size", mysize, mydict["size"])
	except OSError, e:
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
		return False, ("Insufficient data for checksum verification", got, expected)

	for x in mydict:
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
	Run a specific checksum against a file.

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
	myfilename      = filename[:]
	prelink_tmpfile = None
	try:
		if calc_prelink and prelink_capable:
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
		except (OSError, IOError), e:
			if e.errno == errno.ENOENT:
				raise portage.exception.FileNotFound(myfilename)
			raise
		return myhash, mysize
	finally:
		if prelink_tmpfile:
			try:
				os.unlink(prelink_tmpfile)
			except OSError, e:
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
			raise portage.exception.DigestException, x+" hash function not available (needs dev-python/pycrypto or >=dev-lang/python-2.5)"
		rVal[x] = perform_checksum(filename, x, calc_prelink)[0]
	return rVal
