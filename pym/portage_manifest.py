# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

import errno, os, sets
if not hasattr(__builtins__, "set"):
	from sets import Set as set

import portage_exception, portage_versions, portage_const
from portage_checksum import *
from portage_exception import *
from portage_util import write_atomic

class FileNotInManifestException(PortageException):
	pass

def manifest2AuxfileFilter(filename):
	filename = filename.strip(os.sep)
	for ignored_dir in ("CVS", ".bzr",".git",".svn"):
		if filename == ignored_dir or \
		ignored_dir in filename.split(os.sep):
			return False
	return not filename.startswith("digest-")

def manifest2MiscfileFilter(filename):
	filename = filename.strip(os.sep)
	return not (filename in ["CVS", ".svn", "files", "Manifest"] or filename.endswith(".ebuild"))

def guessManifestFileType(filename):
	""" Perform a best effort guess of which type the given filename is, avoid using this if possible """
	if filename.startswith("files" + os.sep + "digest-"):
		return None
	if filename.startswith("files" + os.sep):
		return "AUX"
	elif filename.endswith(".ebuild"):
		return "EBUILD"
	elif filename in ["ChangeLog", "metadata.xml"]:
		return "MISC"
	else:
		return "DIST"

def parseManifest2(mysplit):
	myentry = None
	if len(mysplit) > 4 and mysplit[0] in portage_const.MANIFEST2_IDENTIFIERS:
		mytype = mysplit[0]
		myname = mysplit[1]
		mysize = int(mysplit[2])
		myhashes = dict(zip(mysplit[3::2], mysplit[4::2]))
		myhashes["size"] = mysize
		myentry = Manifest2Entry(type=mytype, name=myname, hashes=myhashes)
	return myentry

def parseManifest1(mysplit):
	myentry = None
	if len(mysplit) == 4 and mysplit[0] in ["size"] + portage_const.MANIFEST1_HASH_FUNCTIONS:
		myname = mysplit[2]
		mytype = None
		mytype = guessManifestFileType(myname)
		if mytype == "AUX":
			if myname.startswith("files" + os.path.sep):
				myname = myname[6:]
		mysize = int(mysplit[3])
		myhashes = {mysplit[0]: mysplit[1]}
		myhashes["size"] = mysize
		myentry = Manifest1Entry(type=mytype, name=myname, hashes=myhashes)
	return myentry

class ManifestEntry(object):
	__slots__ = ("type", "name", "hashes")
	def __init__(self, **kwargs):
		for k, v in kwargs.iteritems():
			setattr(self, k, v)
	def __cmp__(self, other):
		if str(self) == str(other):
			return 0
		return 1

class Manifest1Entry(ManifestEntry):
	def __str__(self):
		myhashkeys = self.hashes.keys()
		for hashkey in myhashkeys:
			if hashkey != "size":
				break
		hashvalue = self.hashes[hashkey]
		myname = self.name
		if self.type == "AUX" and not myname.startswith("files" + os.sep):
			myname = os.path.join("files", myname)
		return " ".join([hashkey, str(hashvalue), myname, str(self.hashes["size"])])

class Manifest2Entry(ManifestEntry):
	def __str__(self):
		myline = " ".join([self.type, self.name, str(self.hashes["size"])])
		myhashkeys = self.hashes.keys()
		myhashkeys.remove("size")
		myhashkeys.sort()
		for h in myhashkeys:
			myline += " " + h + " " + str(self.hashes[h])
		return myline

class Manifest(object):
	parsers = (parseManifest2, parseManifest1)
	def __init__(self, pkgdir, distdir, fetchlist_dict=None,
		manifest1_compat=True, from_scratch=False):
		""" create new Manifest instance for package in pkgdir
		    and add compability entries for old portage versions if manifest1_compat == True.
		    Do not parse Manifest file if from_scratch == True (only for internal use)
			The fetchlist_dict parameter is required only for generation of
			a Manifest (not needed for parsing and checking sums)."""
		self.pkgdir = pkgdir.rstrip(os.sep) + os.sep
		self.fhashdict = {}
		self.hashes = portage_const.MANIFEST2_HASH_FUNCTIONS[:]
		self.hashes.append("size")
		if manifest1_compat:
			self.hashes.extend(portage_const.MANIFEST1_HASH_FUNCTIONS)
		self.hashes = sets.Set(self.hashes)
		for t in portage_const.MANIFEST2_IDENTIFIERS:
			self.fhashdict[t] = {}
		if not from_scratch:
			self._read()
		self.compat = manifest1_compat
		self.fetchlist_dict = fetchlist_dict
		self.distdir = distdir
		self.guessType = guessManifestFileType

	def getFullname(self):
		""" Returns the absolute path to the Manifest file for this instance """
		return os.path.join(self.pkgdir, "Manifest")
	
	def getDigests(self):
		""" Compability function for old digest/manifest code, returns dict of filename:{hashfunction:hashvalue} """
		rval = {}
		for t in portage_const.MANIFEST2_IDENTIFIERS:
			rval.update(self.fhashdict[t])
		return rval
	
	def getTypeDigests(self, ftype):
		""" Similar to getDigests(), but restricted to files of the given type. """
		return self.fhashdict[ftype]

	def _readDigests(self, myhashdict=None):
		""" Parse old style digest files for this Manifest instance """
		if myhashdict is None:
			myhashdict = {}
		try:
			for d in os.listdir(os.path.join(self.pkgdir, "files")):
				if d.startswith("digest-"):
					self._readManifest(os.path.join(self.pkgdir, "files", d), mytype="DIST",
						myhashdict=myhashdict)
		except (IOError, OSError), e:
			if e.errno == errno.ENOENT:
				pass
			else:
				raise
		return myhashdict

	def _readManifest(self, file_path, myhashdict=None, **kwargs):
		"""Parse a manifest or an old style digest.  If myhashdict is given
		then data will be added too it.  Otherwise, a new dict will be created
		and returned."""
		try:
			fd = open(file_path, "r")
			if myhashdict is None:
				myhashdict = {}
			self._parseDigests(fd, myhashdict=myhashdict, **kwargs)
			fd.close()
			return myhashdict
		except (OSError, IOError), e:
			if e.errno == errno.ENOENT:
				raise FileNotFound(file_path)
			else:
				raise

	def _read(self):
		""" Parse Manifest file for this instance """
		try:
			self._readManifest(self.getFullname(), myhashdict=self.fhashdict)
		except FileNotFound:
			pass
		self._readDigests(myhashdict=self.fhashdict)
		

	def _parseManifestLines(self, mylines):
		"""Parse manifest lines and return a list of manifest entries."""
		for myline in mylines:
			myentry = None
			mysplit = myline.split()
			for parser in self.parsers:
				myentry = parser(mysplit)
				if myentry is not None:
					yield myentry
					break # go to the next line

	def _parseDigests(self, mylines, myhashdict=None, mytype=None):
		"""Parse manifest entries and store the data in myhashdict.  If mytype
		is specified, it will override the type for all parsed entries."""
		if myhashdict is None:
			myhashdict = {}
		for myentry in self._parseManifestLines(mylines):
			if mytype is None:
				myentry_type = myentry.type
			else:
				myentry_type = mytype
			myhashdict.setdefault(myentry_type, {})
			myhashdict[myentry_type].setdefault(myentry.name, {})
			myhashdict[myentry_type][myentry.name].update(myentry.hashes)
		return myhashdict

	def _writeDigests(self, force=False):
		""" Create old style digest files for this Manifest instance """
		cpvlist = [os.path.join(self._pkgdir_category(), x[:-7]) for x in os.listdir(self.pkgdir) if x.endswith(".ebuild")]
		rval = []
		try:
			os.makedirs(os.path.join(self.pkgdir, "files"))
		except OSError, oe:
			if oe.errno == errno.EEXIST:
				pass
			else:
				raise
		for cpv in cpvlist:
			dname = os.path.join(self.pkgdir, "files", "digest-%s" % self._catsplit(cpv)[1])
			distlist = self._getCpvDistfiles(cpv)
			have_all_checksums = True
			for f in distlist:
				if f not in self.fhashdict["DIST"] or len(self.fhashdict["DIST"][f]) == 0:
					have_all_checksums = False
					break
			if not have_all_checksums:
				# We don't have all the required checksums to generate a proper
				# digest, so we have to skip this cpv.
				continue
			update_digest = True
			if not force:
				try:
					f = open(dname, "r")
					old_data = self._parseDigests(f)
					f.close()
					if len(old_data) == 1 and "DIST" in old_data:
						new_data = self._getDigestData(distlist)
						for myfile in new_data["DIST"]:
							for hashname in new_data["DIST"][myfile].keys():
								if hashname != "size" and \
								hashname not in portage_const.MANIFEST1_HASH_FUNCTIONS:
									del new_data["DIST"][myfile][hashname]
						if new_data["DIST"] == old_data["DIST"]:
							update_digest = False
				except (IOError, OSError), e:
					if errno.ENOENT == e.errno:
						pass
					else:
						raise
			if update_digest:
				write_atomic(dname,
				"\n".join(self._createDigestLines1(distlist, self.fhashdict))+"\n")
			rval.append(dname)
		return rval

	def _getDigestData(self, distlist):
		"""create a hash dict for a specific list of files"""
		myhashdict = {}
		for myname in distlist:
			for mytype in self.fhashdict:
				if myname in self.fhashdict[mytype]:
					myhashdict.setdefault(mytype, {})
					myhashdict[mytype].setdefault(myname, {})
					myhashdict[mytype][myname].update(self.fhashdict[mytype][myname])
		return myhashdict

	def _createDigestLines1(self, distlist, myhashdict):
		""" Create an old style digest file."""
		mylines = []
		myfiles = myhashdict["DIST"].keys()
		myfiles.sort()
		for f in myfiles:
			if f in distlist:
				myhashkeys = myhashdict["DIST"][f].keys()
				myhashkeys.sort()
				for h in myhashkeys:
					if h not in portage_const.MANIFEST1_HASH_FUNCTIONS:
						continue
					myline = " ".join([h, str(myhashdict["DIST"][f][h]), f, str(myhashdict["DIST"][f]["size"])])
					mylines.append(myline)
		return mylines
	
	def _addDigestsToManifest(self, digests, fd):
		""" Add entries for old style digest files to Manifest file """
		mylines = []
		for dname in digests:
			myhashes = perform_multiple_checksums(dname, portage_const.MANIFEST1_HASH_FUNCTIONS+["size"])
			for h in myhashes:
				mylines.append((" ".join([h, str(myhashes[h]), os.path.join("files", os.path.basename(dname)), str(myhashes["size"])])))
		fd.write("\n".join(mylines))
		fd.write("\n")

	def _createManifestEntries(self):
		mytypes = self.fhashdict.keys()
		mytypes.sort()
		for t in mytypes:
			myfiles = self.fhashdict[t].keys()
			myfiles.sort()
			for f in myfiles:
				myentry = Manifest2Entry(
					type=t, name=f, hashes=self.fhashdict[t][f].copy())
				myhashkeys = myentry.hashes.keys()
				for h in myhashkeys:
					if h not in ["size"] + portage_const.MANIFEST2_HASH_FUNCTIONS:
						del myentry.hashes[h]
				yield myentry
				if self.compat and t != "DIST":
					mysize = self.fhashdict[t][f]["size"]
					myhashes = self.fhashdict[t][f]
					for h in myhashkeys:
						if h not in portage_const.MANIFEST1_HASH_FUNCTIONS:
							continue
						yield Manifest1Entry(
							type=t, name=f, hashes={"size":mysize, h:myhashes[h]})

		if self.compat:
			cvp_list = self.fetchlist_dict.keys()
			cvp_list.sort()
			for cpv in cvp_list:
				digest_path = os.path.join("files", "digest-%s" % self._catsplit(cpv)[1])
				dname = os.path.join(self.pkgdir, digest_path)
				try:
					myhashes = perform_multiple_checksums(dname, portage_const.MANIFEST1_HASH_FUNCTIONS+["size"])
					myhashkeys = myhashes.keys()
					myhashkeys.sort()
					for h in myhashkeys:
						if h in portage_const.MANIFEST1_HASH_FUNCTIONS:
							yield Manifest1Entry(type="AUX", name=digest_path,
								hashes={"size":myhashes["size"], h:myhashes[h]})
				except FileNotFound:
					pass

	def write(self, sign=False, force=False):
		""" Write Manifest instance to disk, optionally signing it """
		try:
			if self.compat:
				self._writeDigests()
			myentries = list(self._createManifestEntries())
			update_manifest = True
			if not force:
				try:
					f = open(self.getFullname(), "r")
					oldentries = list(self._parseManifestLines(f))
					f.close()
					if len(oldentries) == len(myentries):
						update_manifest = False
						for i in xrange(len(oldentries)):
							if oldentries[i] != myentries[i]:
								update_manifest = True
								break
				except (IOError, OSError), e:
					if e.errno == errno.ENOENT:
						pass
					else:
						raise
			if update_manifest:
				fd = open(self.getFullname(), "w")
				for myentry in myentries:
					fd.write("%s\n" % str(myentry))
				fd.close()
			if sign:
				self.sign()
		except (IOError, OSError), e:
			if e.errno == errno.EACCES:
				raise PermissionDenied(str(e))
			raise

	def sign(self):
		""" Sign the Manifest """
		raise NotImplementedError()
	
	def validateSignature(self):
		""" Validate signature on Manifest """
		raise NotImplementedError()
	
	def addFile(self, ftype, fname, hashdict=None):
		""" Add entry to Manifest optionally using hashdict to avoid recalculation of hashes """
		if not os.path.exists(self.pkgdir+fname):
			raise FileNotFound(fname)
		if not ftype in portage_const.MANIFEST2_IDENTIFIERS:
			raise InvalidDataType(ftype)
		self.fhashdict[ftype][fname] = {}
		if hashdict != None:
			self.fhashdict[ftype][fname].update(hashdict)
		if not portage_const.MANIFEST2_REQUIRED_HASH in self.fhashdict[ftype][fname]:
			self.updateFileHashes(ftype, fname)
	
	def removeFile(self, ftype, fname):
		""" Remove given entry from Manifest """
		del self.fhashdict[ftype][fname]
	
	def hasFile(self, ftype, fname):
		""" Return wether the Manifest contains an entry for the given type,filename pair """
		return (fname in self.fhashdict[ftype])
	
	def findFile(self, fname):
		""" Return entrytype of the given file if present in Manifest or None if not present """
		for t in portage_const.MANIFEST2_IDENTIFIERS:
			if fname in self.fhashdict[t]:
				return t
		return None
	
	def create(self, checkExisting=False, assumeDistHashesSometimes=False,
		assumeDistHashesAlways=False, requiredDistfiles=None):
		""" Recreate this Manifest from scratch.  This will not use any
		existing checksums unless assumeDistHashesSometimes or
		assumeDistHashesAlways is true (assumeDistHashesSometimes will only
		cause DIST checksums to be reused if the file doesn't exist in
		DISTDIR).  The requiredDistfiles parameter specifies a list of
		distfiles to raise a FileNotFound exception for (if no file or existing
		checksums are available), and defaults to all distfiles when not
		specified."""
		if checkExisting:
			self.checkAllHashes()
		if assumeDistHashesSometimes or assumeDistHashesAlways:
			distfilehashes = self.fhashdict["DIST"]
		else:
			distfilehashes = {}
		self.__init__(self.pkgdir, self.distdir,
			fetchlist_dict=self.fetchlist_dict, from_scratch=True)
		for pkgdir, pkgdir_dirs, pkgdir_files in os.walk(self.pkgdir):
			break
		for f in pkgdir_files:
			if f.endswith(".ebuild"):
				mytype = "EBUILD"
			elif manifest2MiscfileFilter(f):
				mytype = "MISC"
			else:
				continue
			self.fhashdict[mytype][f] = perform_multiple_checksums(self.pkgdir+f, self.hashes)
		recursive_files = []
		cut_len = len(os.path.join(self.pkgdir, "files") + os.sep)
		for parentdir, dirs, files in os.walk(os.path.join(self.pkgdir, "files")):
			for f in files:
				full_path = os.path.join(parentdir, f)
				recursive_files.append(full_path[cut_len:])
		for f in recursive_files:
			if not manifest2AuxfileFilter(f):
				continue
			self.fhashdict["AUX"][f] = perform_multiple_checksums(
				os.path.join(self.pkgdir, "files", f.lstrip(os.sep)), self.hashes)
		cpvlist = [os.path.join(self._pkgdir_category(), x[:-7]) for x in os.listdir(self.pkgdir) if x.endswith(".ebuild")]
		distlist = set()
		for cpv in cpvlist:
			distlist.update(self._getCpvDistfiles(cpv))
		if requiredDistfiles is None or len(requiredDistfiles) == 0:
			# repoman passes in an empty list, which implies that all distfiles
			# are required.
			requiredDistfiles = distlist.copy()
		for f in distlist:
			fname = os.path.join(self.distdir, f)
			mystat = None
			try:
				mystat = os.stat(fname)
			except OSError:
				pass
			if f in distfilehashes and \
				((assumeDistHashesSometimes and mystat is None) or \
				(assumeDistHashesAlways and mystat is None) or \
				(assumeDistHashesAlways and mystat is not None and \
				len(distfilehashes[f]) == len(self.hashes) and \
				distfilehashes[f]["size"] == mystat.st_size)):
				self.fhashdict["DIST"][f] = distfilehashes[f]
			else:
				try:
					self.fhashdict["DIST"][f] = perform_multiple_checksums(fname, self.hashes)
				except FileNotFound:
					if f in requiredDistfiles:
						raise

	def _pkgdir_category(self):
		return self.pkgdir.rstrip(os.sep).split(os.sep)[-2]

	def _getAbsname(self, ftype, fname):
		if ftype == "DIST":
			absname = os.path.join(self.distdir, fname)
		elif ftype == "AUX":
			absname = os.path.join(self.pkgdir, "files", fname)
		else:
			absname = os.path.join(self.pkgdir, fname)
		return absname	
	
	def checkAllHashes(self, ignoreMissingFiles=False):
		for t in portage_const.MANIFEST2_IDENTIFIERS:
			self.checkTypeHashes(t, ignoreMissingFiles=ignoreMissingFiles)
	
	def checkTypeHashes(self, idtype, ignoreMissingFiles=False):
		for f in self.fhashdict[idtype]:
			self.checkFileHashes(idtype, f, ignoreMissing=ignoreMissingFiles)
	
	def checkFileHashes(self, ftype, fname, ignoreMissing=False):
		myhashes = self.fhashdict[ftype][fname]
		try:
			ok,reason = verify_all(self._getAbsname(ftype, fname), self.fhashdict[ftype][fname])
			if not ok:
				raise DigestException(tuple([self._getAbsname(ftype, fname)]+list(reason)))
			return ok, reason
		except FileNotFound, e:
			if not ignoreMissing:
				raise
			return False, "File Not Found: '%s'" % str(e)

	def checkCpvHashes(self, cpv, checkDistfiles=True, onlyDistfiles=False, checkMiscfiles=False):
		""" check the hashes for all files associated to the given cpv, include all
		AUX files and optionally all MISC files. """
		if not onlyDistfiles:
			self.checkTypeHashes("AUX", ignoreMissingFiles=False)
			if checkMiscfiles:
				self.checkTypeHashes("MISC", ignoreMissingFiles=False)
			ebuildname = "%s.ebuild" % self._catsplit(cpv)[1]
			self.checkFileHashes("EBUILD", ebuildname, ignoreMissing=False)
		if checkDistfiles:
			if onlyDistfiles:
				for f in self._getCpvDistfiles(cpv):
					self.checkFileHashes("DIST", f, ignoreMissing=False)
	
	def _getCpvDistfiles(self, cpv):
		""" Get a list of all DIST files associated to the given cpv """
		return self.fetchlist_dict[cpv]

	def getDistfilesSize(self, fetchlist):
		total_bytes = 0
		for f in fetchlist:
			total_bytes += int(self.fhashdict["DIST"][f]["size"])
		return total_bytes

	def updateFileHashes(self, ftype, fname, checkExisting=True, ignoreMissing=True, reuseExisting=False):
		""" Regenerate hashes for the given file """
		if checkExisting:
			self.checkFileHashes(ftype, fname, ignoreMissing=ignoreMissing)
		if not ignoreMissing and not self.fhashdict[ftype].has_key(fname):
			raise FileNotInManifestException(fname)
		if not self.fhashdict[ftype].has_key(fname):
			self.fhashdict[ftype][fname] = {}
		myhashkeys = list(self.hashes)
		if reuseExisting:
			for k in [h for h in self.fhashdict[ftype][fname] if h in myhashkeys]:
				myhashkeys.remove(k)
		myhashes = perform_multiple_checksums(self._getAbsname(ftype, fname), myhashkeys)
		self.fhashdict[ftype][fname].update(myhashes)
	
	def updateTypeHashes(self, idtype, checkExisting=False, ignoreMissingFiles=True):
		""" Regenerate all hashes for all files of the given type """
		for fname in self.fhashdict[idtype]:
			self.updateFileHashes(idtype, fname, checkExisting)
	
	def updateAllHashes(self, checkExisting=False, ignoreMissingFiles=True):
		""" Regenerate all hashes for all files in this Manifest. """
		for ftype in portage_const.MANIFEST2_IDENTIFIERS:
			self.updateTypeHashes(idtype, fname, checkExisting)

	def updateCpvHashes(self, cpv, ignoreMissingFiles=True):
		""" Regenerate all hashes associated to the given cpv (includes all AUX and MISC
		files)."""
		self.updateTypeHashes("AUX", ignoreMissingFiles=ignoreMissingFiles)
		self.updateTypeHashes("MISC", ignoreMissingFiles=ignoreMissingFiles)
		ebuildname = "%s.ebuild" % self._catsplit(cpv)[1]
		self.updateFileHashes("EBUILD", ebuildname, ignoreMissingFiles=ignoreMissingFiles)
		for f in self._getCpvDistfiles(cpv):
			self.updateFileHashes("DIST", f, ignoreMissingFiles=ignoreMissingFiles)

	def updateHashesGuessType(self, fname, *args, **kwargs):
		""" Regenerate hashes for the given file (guesses the type and then
		calls updateFileHashes)."""
		mytype = self.guessType(fname)
		if mytype == "AUX":
			fname = fname[len("files" + os.sep):]
		elif mytype is None:
			return
		myrealtype = self.findFile(fname)
		if myrealtype is not None:
			mytype = myrealtype
		return self.updateFileHashes(mytype, fname, *args, **kwargs)

	def getFileData(self, ftype, fname, key):
		""" Return the value of a specific (type,filename,key) triple, mainly useful
		to get the size for distfiles."""
		return self.fhashdict[ftype][fname][key]

	def getVersions(self):
		""" Returns a list of manifest versions present in the manifest file. """
		rVal = []
		mfname = self.getFullname()
		if not os.path.exists(mfname):
			return rVal
		myfile = open(mfname, "r")
		lines = myfile.readlines()
		myfile.close()
		for l in lines:
			mysplit = l.split()
			if len(mysplit) == 4 and mysplit[0] in portage_const.MANIFEST1_HASH_FUNCTIONS and not 1 in rVal:
				rVal.append(1)
			elif len(mysplit) > 4 and mysplit[0] in portage_const.MANIFEST2_IDENTIFIERS and ((len(mysplit) - 3) % 2) == 0 and not 2 in rVal:
				rVal.append(2)
		return rVal

	def _catsplit(self, pkg_key):
		"""Split a category and package, returning a list of [cat, pkg].
		This is compatible with portage.catsplit()"""
		return pkg_key.split("/", 1)
