# portage_checksum.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/portage_checksum.py,v 1.10.2.2 2005/08/10 05:42:03 ferringb Exp $
cvs_id_string="$Id: portage_checksum.py,v 1.10.2.2 2005/08/10 05:42:03 ferringb Exp $"[5:-2]

from portage_const import PRIVATE_PATH,PRELINK_BINARY
import os
import shutil
import stat
import portage_exec
import portage_util
import portage_locks
import commands
import sha

prelink_capable = False
if os.path.exists(PRELINK_BINARY):
	results = commands.getstatusoutput(PRELINK_BINARY+" --version > /dev/null 2>&1")
	if (results[0] >> 8) == 0:
		prelink_capable=1
	del results

def perform_md5(x, calc_prelink=0):
	return perform_checksum(x, md5hash, calc_prelink)[0]

def perform_sha1(x, calc_prelink=0):
	return perform_checksum(x, sha1hash, calc_prelink)[0]

def perform_all(x, calc_prelink=0):
	mydict = {}
	mydict["SHA1"] = perform_sha1(x, calc_prelink)
	mydict["MD5"] = perform_md5(x, calc_prelink)
	return mydict

def get_valid_checksum_keys():
	return ["SHA1", "MD5"]

def verify_all(filename, mydict, calc_prelink=0, strict=0):
	# Dict relates to single file only.
	# returns: (passed,reason)
	file_is_ok = True
	reason     = "Reason unknown"
	try:
		if mydict["size"] != os.stat(filename)[stat.ST_SIZE]:
			return False,"Filesize does not match recorded size"
	except OSError, e:
		return False, str(e)
	for x in mydict.keys():
		if   x == "size":
			continue
		elif x == "SHA1":
			if mydict[x] != perform_sha1(filename, calc_prelink=calc_prelink):
				if strict:
					raise portage_exception.DigestException, "Failed to verify '$(file)s' on checksum type '%(type)s'" % {"file":filename, "type":x}
				else:
					file_is_ok = False
					reason     = "Failed on %s verification" % (x,)
					break
		elif x == "MD5":
			if mydict[x] != perform_md5(filename, calc_prelink=calc_prelink):
				if strict:
					raise portage_exception.DigestException, "Failed to verify '$(file)s' on checksum type '%(type)s'" % {"file":filename, "type":x}
				else:
					file_is_ok = False
					reason     = "Failed on %s verification" % (x,)
					break
	return file_is_ok,reason

# We _try_ to load this module. If it fails we do the slow fallback.
try:
	import fchksum
	
	def md5hash(filename):
		return fchksum.fmd5t(filename)

except ImportError:
	import md5
	def md5hash(filename):
		f = open(filename, 'rb')
		blocksize=32768
		data = f.read(blocksize)
		size = 0L
		sum = md5.new()
		while data:
			sum.update(data)
			size = size + len(data)
			data = f.read(blocksize)
		f.close()

		return (sum.hexdigest(),size)

def sha1hash(filename):
	f = open(filename, 'rb')
	blocksize=32768
	data = f.read(blocksize)
	size = 0L
	sum = sha.new()
	while data:
		sum.update(data)
		size = size + len(data)
		data = f.read(blocksize)
	f.close()

	return (sum.hexdigest(),size)

def perform_checksum(filename, hash_function=md5hash, calc_prelink=0):
	myfilename      = filename[:]
	prelink_tmpfile = PRIVATE_PATH+"/prelink-checksum.tmp."+str(os.getpid())
	mylock          = None
	
	if calc_prelink and prelink_capable:
		mylock = portage_locks.lockfile(prelink_tmpfile, wantnewlockfile=1)
		# Create non-prelinked temporary file to md5sum.
		# Raw data is returned on stdout, errors on stderr.
		# Non-prelinks are just returned.
		try:
			shutil.copy2(filename,prelink_tmpfile)
		except SystemExit, e:
			raise
		except Exception,e:
			portage_util.writemsg("!!! Unable to copy file '"+str(filename)+"'.\n")
			portage_util.writemsg("!!! "+str(e)+"\n")
			raise
		portage_exec.spawn(PRELINK_BINARY+" --undo "+prelink_tmpfile,fd_pipes={})
		myfilename=prelink_tmpfile

	myhash, mysize = hash_function(myfilename)

	if calc_prelink and prelink_capable:
		os.unlink(prelink_tmpfile)
		portage_locks.unlockfile(mylock)

	return (myhash,mysize)
