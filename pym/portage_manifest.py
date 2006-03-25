import os, sets

import portage, portage_exception, portage_versions, portage_const
from portage_checksum import *
from portage_exception import *

class FileNotInManifestException(PortageException):
	pass

def manifest2AuxfileFilter(filename):
	filename = filename.strip(os.sep)
	return not (filename in ["CVS", ".svn"] or filename.startswith("digest-"))

def manifest2MiscfileFilter(filename):
	filename = filename.strip(os.sep)
	return not (filename in ["CVS", ".svn", "files", "Manifest"] or filename.endswith(".ebuild"))

class Manifest(object):
	def __init__(self, pkgdir, db, mysettings, manifest1_compat=True, from_scratch=False):
		""" create new Manifest instance for package in pkgdir, using db and mysettings for metadata lookups,
		    and add compability entries for old portage versions if manifest1_compat == True.
		    Do not parse Manifest file if from_scratch == True (only for internal use) """
		self.pkgdir = pkgdir+os.sep
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
		self.db = db
		self.mysettings = mysettings
		if mysettings.has_key("PORTAGE_ACTUAL_DISTDIR"):
			self.distdir = mysettings["PORTAGE_ACTUAL_DISTDIR"]
		else:
			self.distdir = mysettings["DISTDIR"]
		
	def guessType(self, filename):
		""" Perform a best effort guess of which type the given filename is, avoid using this if possible """
		if filename.startswith("files"+os.sep+"digest-"):
			return None
		if filename.startswith("files"+os.sep):
			return "AUX"
		elif filename.endswith(".ebuild"):
			return "EBUILD"
		elif filename in ["ChangeLog", "metadata.xml"]:
			return "MISC"
		else:
			return "DIST"
	
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

	def _readDigests(self):
		""" Parse old style digest files for this Manifest instance """
		mycontent = ""
		for d in portage.listdir(os.path.join(self.pkgdir, "files"), filesonly=True, recursive=False):
			if d.startswith("digest-"):
				mycontent += open(os.path.join(self.pkgdir, "files", d), "r").read()
		return mycontent
		
	def _read(self):
		""" Parse Manifest file for this instance """
		if not os.path.exists(self.getFullname()):
			return
		fd = open(self.getFullname(), "r")
		mylines = fd.readlines()
		fd.close()
		mylines.extend(self._readDigests().split("\n"))
		for l in mylines:
			myname = ""
			mysplit = l.split()
			if len(mysplit) == 4 and mysplit[0] in portage_const.MANIFEST1_HASH_FUNCTIONS:
				myname = mysplit[2]
				mytype = self.guessType(myname)
				if mytype == "AUX" and myname.startswith("files"+os.sep):
					myname = myname[6:]
				if mytype == None:
					continue
				mysize = int(mysplit[3])
				myhashes = {mysplit[0]: mysplit[1]}
			if len(mysplit) > 4 and mysplit[0] in portage_const.MANIFEST2_IDENTIFIERS:
				mytype = mysplit[0]
				myname = mysplit[1]
				mysize = int(mysplit[2])
				myhashes = dict(zip(mysplit[3::2], mysplit[4::2]))
			if len(myname) == 0:
				continue
			if not self.fhashdict[mytype].has_key(myname):
				self.fhashdict[mytype][myname] = {} 
			self.fhashdict[mytype][myname].update(myhashes)
			self.fhashdict[mytype][myname]["size"] = mysize
	
	def _writeDigests(self):
		""" Create old style digest files for this Manifest instance """
		cpvlist = [os.path.join(self.pkgdir.rstrip(os.sep).split(os.sep)[-2], x[:-7]) for x in portage.listdir(self.pkgdir) if x.endswith(".ebuild")]
		rval = []
		for cpv in cpvlist:
			dname = os.path.join(self.pkgdir, "files", "digest-"+portage.catsplit(cpv)[1])
			mylines = []
			distlist = self._getCpvDistfiles(cpv)
			for f in self.fhashdict["DIST"].keys():
				if f in distlist:
					for h in self.fhashdict["DIST"][f].keys():
						if h not in portage_const.MANIFEST1_HASH_FUNCTIONS:
							continue
						myline = " ".join([h, str(self.fhashdict["DIST"][f][h]), f, str(self.fhashdict["DIST"][f]["size"])])
						mylines.append(myline)
			fd = open(dname, "w")
			fd.write("\n".join(mylines))
			fd.write("\n")
			fd.close()
			rval.append(dname)
		return rval
	
	def _addDigestsToManifest(self, digests, fd):
		""" Add entries for old style digest files to Manifest file """
		mylines = []
		for dname in digests:
			myhashes = perform_multiple_checksums(dname, portage_const.MANIFEST1_HASH_FUNCTIONS+["size"])
			for h in myhashes.keys():
				mylines.append((" ".join([h, str(myhashes[h]), os.path.join("files", os.path.basename(dname)), str(myhashes["size"])])))
		fd.write("\n".join(mylines))
		fd.write("\n")
	
	def _write(self, fd):
		""" Actual Manifest file generator """
		mylines = []
		for t in self.fhashdict.keys():
			for f in self.fhashdict[t].keys():
				# compat hack for v1 manifests
				if t == "AUX":
					f2 = os.path.join("files", f)
				else:
					f2 = f
				myline = " ".join([t, f, str(self.fhashdict[t][f]["size"])])
				myhashes = self.fhashdict[t][f]
				for h in myhashes.keys():
					if h not in portage_const.MANIFEST2_HASH_FUNCTIONS:
						continue
					myline += " "+h+" "+str(myhashes[h])
				mylines.append(myline)
				if self.compat and t != "DIST":
					for h in myhashes.keys():
						if h not in portage_const.MANIFEST1_HASH_FUNCTIONS:
							continue
						mylines.append((" ".join([h, str(myhashes[h]), f2, str(myhashes["size"])])))
		fd.write("\n".join(mylines))
		fd.write("\n")

	def write(self, sign=False):
		""" Write Manifest instance to disk, optionally signing it """
		fd = open(self.getFullname(), "w")
		self._write(fd)
		if self.compat:
			digests = self._writeDigests()
			self._addDigestsToManifest(digests, fd)
		fd.close()
		if sign:
			self.sign()
	
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
		if not portage_const.MANIFEST2_REQUIRED_HASH in self.fhashdict[ftype][fname].keys():
			self.updateFileHashes(ftype, fname)
	
	def removeFile(self, ftype, fname):
		""" Remove given entry from Manifest """
		del self.fhashdict[ftype][fname]
	
	def hasFile(self, ftype, fname):
		""" Return wether the Manifest contains an entry for the given type,filename pair """
		return (fname in self.fhashdict[ftype].keys())
	
	def findFile(self, fname):
		""" Return entrytype of the given file if present in Manifest or None if not present """
		for t in portage_const.MANIFEST2_IDENTIFIERS:
			if fname in self.fhashdict[t]:
				return t
		return None
	
	def create(self, checkExisting=False, assumeDistfileHashes=True):
		""" Recreate this Manifest from scratch, not using any existing checksums
		(exception: if assumeDistfileHashes is true then existing DIST checksums are
		reused if the file doesn't exist in DISTDIR."""
		if checkExisting:
			self.checkAllHashes()
		if assumeDistfileHashes:
			distfilehashes = self.fhashdict["DIST"]
		else:
			distfilehashes = {}
		self.__init__(self.pkgdir, self.db, self.mysettings, from_scratch=True)
		for f in portage.listdir(self.pkgdir, filesonly=True, recursive=False):
			if f.endswith(".ebuild"):
				mytype = "EBUILD"
			elif manifest2MiscfileFilter(f):
				mytype = "MISC"
			else:
				continue
			self.fhashdict[mytype][f] = perform_multiple_checksums(self.pkgdir+f, self.hashes)
		for f in portage.listdir(self.pkgdir+"files", filesonly=True, recursive=True):
			if not manifest2AuxfileFilter(f):
				continue
			self.fhashdict["AUX"][f] = perform_multiple_checksums(self.pkgdir+"files"+os.sep+f, self.hashes)
		cpvlist = [os.path.join(self.pkgdir.rstrip(os.sep).split(os.sep)[-2], x[:-7]) for x in portage.listdir(self.pkgdir) if x.endswith(".ebuild")]
		distlist = []
		for cpv in cpvlist:
			distlist.extend(self._getCpvDistfiles(cpv))
		for f in distlist:
			fname = os.path.join(self.distdir, f)
			if os.path.exists(fname):
				self.fhashdict["DIST"][f] = perform_multiple_checksums(fname, self.hashes)
			elif assumeDistfileHashes and f in distfilehashes.keys():
				self.fhashdict["DIST"][f] = distfilehashes[f]
			else:
				raise FileNotFound(fname)			
	
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
		for f in self.fhashdict[idtype].keys():
			self.checkFileHashes(idtype, f, ignoreMissing=ignoreMissingFiles)
	
	def checkFileHashes(self, ftype, fname, ignoreMissing=False):
		myhashes = self.fhashdict[ftype][fname]
		ok,reason = verify_all(self._getAbsname(ftype, fname), self.fhashdict[ftype][fname])
		if not ok:
			raise DigestException(tuple([self._getAbsname(ftype, fname)]+list(reason)))
		return ok, reason

	def checkCpvHashes(self, cpv, checkDistfiles=True, onlyDistfiles=False, checkMiscfiles=False):
		""" check the hashes for all files associated to the given cpv, include all
		AUX files and optionally all MISC files. """
		if not onlyDistfiles:
			self.checkTypeHashes("AUX", ignoreMissingFiles=False)
			if checkMiscfiles:
				self.checkTypeHashes("MISC", ignoreMissingFiles=False)
			ebuildname = portage.catsplit(cpv)[1]+".ebuild"
			self.checkFileHashes("EBUILD", ebuildname, ignoreMissing=False)
		if checkDistfiles:
			if onlyDistfiles:
				for f in self._getCpvDistfiles(cpv):
					self.checkFileHashes("DIST", f, ignoreMissing=False)
	
	def _getCpvDistfiles(self, cpv):
		""" Get a list of all DIST files associated to the given cpv """
		return self.db.getfetchlist(cpv, mysettings=self.mysettings, all=True)[1]
	
	def updateFileHashes(self, ftype, fname, checkExisting=True, ignoreMissing=True, reuseExisting=False):
		""" Regenerate hashes for the given file """
		if checkExisting:
			self.checkFileHashes(fname)
		if not ignoreMissing and not self.fhashdict[ftype].has_key(fname):
			raise FileNotInManifestException(fname)
		if not self.fhashdict[ftype].has_key(fname):
			self.fhashdict[ftype][fname] = {}
		myhashkeys = list(self.hashes)
		if reuseExisting:
			for k in [h for h in self.fhashdict[ftype][fname].keys() if h in myhashkeys]:
				myhashkeys.remove(k)
		myhashes = perform_multiple_checksums(self._getAbsname(ftype, fname), myhashkeys)
		self.fhashdict[ftype][fname].update(myhashes)
	
	def updateTypeHashes(self, idtype, checkExisting=False, ignoreMissingFiles=True):
		""" Regenerate all hashes for all files of the given type """
		for fname in self.fhashdict[idtype].keys():
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
		ebuildname = portage.catsplit(cpv)[1]+".ebuild"
		self.updateFileHashes("EBUILD", ebuildname, ignoreMissingFiles=ignoreMissingFiles)
		for f in self._getCpvDistfiles(cpv):
			self.updateFileHashes("DIST", f, ignoreMissingFiles=ignoreMissingFiles)

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
