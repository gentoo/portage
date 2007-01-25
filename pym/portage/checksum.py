# portage_checksum.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


from portage_const import PRIVATE_PATH,PRELINK_BINARY,HASHING_BLOCKSIZE
import os
import errno
import shutil
import stat
import portage_exception
import portage_exec
import portage_util
import portage_locks
import commands
import sha


# actual hash functions first

#dict of all available hash functions
hashfunc_map = {}

# We _try_ to load this module. If it fails we do the slightly slower fallback.
try:
	import fchksum
	
	def md5hash(filename):
		return fchksum.fmd5t(filename)

except ImportError:
	import md5
	def md5hash(filename):
		return pyhash(filename, md5)
hashfunc_map["MD5"] = md5hash

def sha1hash(filename):
	return pyhash(filename, sha)
hashfunc_map["SHA1"] = sha1hash
	
# Keep pycrypto optional for now, there are no internal fallbacks for these
try:
	import Crypto.Hash.SHA256
	
	def sha256hash(filename):
		return pyhash(filename, Crypto.Hash.SHA256)
	hashfunc_map["SHA256"] = sha256hash
except ImportError:
	pass

try:
	import Crypto.Hash.RIPEMD
	
	def rmd160hash(filename):
		return pyhash(filename, Crypto.Hash.RIPEMD)
	hashfunc_map["RMD160"] = rmd160hash
except ImportError:
	pass

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
	for k in hashfunc_map.keys():
		mydict[k] = perform_checksum(x, hashfunc_map[k], calc_prelink)[0]
	return mydict

def get_valid_checksum_keys():
	return hashfunc_map.keys()

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
			raise portage_exception.FileNotFound(filename)
		return False, (str(e), None, None)
	for x in mydict.keys():
		if   x == "size":
			continue
		elif x in hashfunc_map.keys():
			myhash = perform_checksum(filename, x, calc_prelink=calc_prelink)[0]
			if mydict[x] != myhash:
				if strict:
					raise portage_exception.DigestException, "Failed to verify '$(file)s' on checksum type '%(type)s'" % {"file":filename, "type":x}
				else:
					file_is_ok = False
					reason     = (("Failed on %s verification" % x), myhash,mydict[x])
					break
	return file_is_ok,reason

def pyhash(filename, hashobject):
	"""
	Run a checksum against a file.

	@param filename: File to run the checksum against
	@type filename: String
	@param hashname: The hash object that will execute the checksum on the file
	@type hashname: Object
	@return: The hash and size of the data
	"""
	f = open(filename, 'rb')
	blocksize = HASHING_BLOCKSIZE
	data = f.read(blocksize)
	size = 0L
	sum = hashobject.new()
	while data:
		sum.update(data)
		size = size + len(data)
		data = f.read(blocksize)
	f.close()

	return (sum.hexdigest(), size)

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
	myfilename      = filename[:]
	prelink_tmpfile = os.path.join("/", PRIVATE_PATH, "prelink-checksum.tmp." + str(os.getpid()))
	mylock          = None
	try:
		if calc_prelink and prelink_capable:
			mylock = portage_locks.lockfile(prelink_tmpfile, wantnewlockfile=1)
			# Create non-prelinked temporary file to checksum.
			# Files rejected by prelink are summed in place.
			retval = portage_exec.spawn([PRELINK_BINARY, "--undo", "-o",
				prelink_tmpfile, filename], fd_pipes={})
			if retval == os.EX_OK:
				myfilename = prelink_tmpfile
		try:
			if hashname not in hashfunc_map:
				raise portage_exception.DigestException(hashname + \
					" hash function not available (needs dev-python/pycrypto)")
			myhash, mysize = hashfunc_map[hashname](myfilename)
		except (OSError, IOError), e:
			if e.errno == errno.ENOENT:
				raise portage_exception.FileNotFound(myfilename)
			raise
		if calc_prelink and prelink_capable:
			try:
				os.unlink(prelink_tmpfile)
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
		return myhash, mysize
	finally:
		if mylock:
			portage_locks.unlockfile(mylock)

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
			raise portage_exception.DigestException, x+" hash function not available (needs dev-python/pycrypto)"
		rVal[x] = perform_checksum(filename, x, calc_prelink)[0]
	return rVal
