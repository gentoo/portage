# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import logging
import re
import stat
import warnings

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.checksum:get_valid_checksum_keys,perform_multiple_checksums,' + \
		'verify_all,_apply_hash_filter,_filter_unaccelarated_hashes',
	'portage.repository.config:_find_invalid_path_char',
	'portage.util:write_atomic,writemsg_level',
)

from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.exception import DigestException, FileNotFound, \
	InvalidDataType, MissingParameter, PermissionDenied, \
	PortageException, PortagePackageException
from portage.const import (MANIFEST2_HASH_DEFAULTS, MANIFEST2_IDENTIFIERS)
from portage.localization import _

_manifest_re = re.compile(
	r'^(' + '|'.join(MANIFEST2_IDENTIFIERS) + r') (\S+)( \d+( \S+ \S+)+)$',
	re.UNICODE)


class FileNotInManifestException(PortageException):
	pass

def manifest2AuxfileFilter(filename):
	filename = filename.strip(os.sep)
	mysplit = filename.split(os.path.sep)
	if "CVS" in mysplit:
		return False
	for x in mysplit:
		if x[:1] == '.':
			return False
	return not filename[:7] == 'digest-'

def manifest2MiscfileFilter(filename):
	return not (filename == "Manifest" or filename.endswith(".ebuild"))

def guessManifestFileType(filename):
	""" Perform a best effort guess of which type the given filename is, avoid using this if possible """
	if filename.startswith("files" + os.sep + "digest-"):
		return None
	if filename.startswith("files" + os.sep):
		return "AUX"
	if filename.endswith(".ebuild"):
		return "EBUILD"
	if filename in ["ChangeLog", "metadata.xml"]:
		return "MISC"
	return "DIST"

def guessThinManifestFileType(filename):
	filetype = guessManifestFileType(filename)
	if filetype != "DIST":
		return None
	return "DIST"

def parseManifest2(line):
	if not isinstance(line, str):
		line = ' '.join(line)
	myentry = None
	match = _manifest_re.match(line)
	if match is not None:
		tokens = match.group(3).split()
		hashes = dict(zip(tokens[1::2], tokens[2::2]))
		hashes["size"] = int(tokens[0])
		myentry = Manifest2Entry(type=match.group(1),
			name=match.group(2), hashes=hashes)
	return myentry

class ManifestEntry:
	__slots__ = ("type", "name", "hashes")
	def __init__(self, **kwargs):
		for k, v in kwargs.items():
			setattr(self, k, v)

class Manifest2Entry(ManifestEntry):
	def __str__(self):
		myline = " ".join([self.type, self.name, str(self.hashes["size"])])
		myhashkeys = list(self.hashes)
		myhashkeys.remove("size")
		myhashkeys.sort()
		for h in myhashkeys:
			myline += " " + h + " " + str(self.hashes[h])
		return myline

	def __eq__(self, other):
		if not isinstance(other, Manifest2Entry) or \
			self.type != other.type or \
			self.name != other.name or \
			self.hashes != other.hashes:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)


class Manifest:
	parsers = (parseManifest2,)
	def __init__(self, pkgdir, distdir=None, fetchlist_dict=None,
		manifest1_compat=DeprecationWarning, from_scratch=False, thin=False,
		allow_missing=False, allow_create=True, hashes=None, required_hashes=None,
		find_invalid_path_char=None, strict_misc_digests=True):
		""" Create new Manifest instance for package in pkgdir.
		    Do not parse Manifest file if from_scratch == True (only for internal use)
			The fetchlist_dict parameter is required only for generation of
			a Manifest (not needed for parsing and checking sums).
			If thin is specified, then the manifest carries only info for
			distfiles."""

		if manifest1_compat is not DeprecationWarning:
			warnings.warn("The manifest1_compat parameter of the "
				"portage.manifest.Manifest constructor is deprecated.",
				DeprecationWarning, stacklevel=2)

		if find_invalid_path_char is None:
			find_invalid_path_char = _find_invalid_path_char
		self._find_invalid_path_char = find_invalid_path_char
		self.pkgdir = _unicode_decode(pkgdir).rstrip(os.sep) + os.sep
		self.fhashdict = {}
		self.hashes = set()
		self.required_hashes = set()

		if hashes is None:
			hashes = MANIFEST2_HASH_DEFAULTS
		if required_hashes is None:
			required_hashes = hashes

		self.hashes.update(hashes)
		self.hashes.difference_update(hashname for hashname in \
			list(self.hashes) if hashname not in get_valid_checksum_keys())
		self.hashes.add("size")

		self.required_hashes.update(required_hashes)
		self.required_hashes.intersection_update(self.hashes)

		for t in MANIFEST2_IDENTIFIERS:
			self.fhashdict[t] = {}
		if not from_scratch:
			self._read()
		if fetchlist_dict != None:
			self.fetchlist_dict = fetchlist_dict
		else:
			self.fetchlist_dict = {}
		self.distdir = distdir
		self.thin = thin
		if thin:
			self.guessType = guessThinManifestFileType
		else:
			self.guessType = guessManifestFileType
		self.allow_missing = allow_missing
		self.allow_create = allow_create
		self.strict_misc_digests = strict_misc_digests

	def getFullname(self):
		""" Returns the absolute path to the Manifest file for this instance """
		return os.path.join(self.pkgdir, "Manifest")

	def getDigests(self):
		""" Compability function for old digest/manifest code, returns dict of filename:{hashfunction:hashvalue} """
		rval = {}
		for t in MANIFEST2_IDENTIFIERS:
			rval.update(self.fhashdict[t])
		return rval

	def getTypeDigests(self, ftype):
		""" Similar to getDigests(), but restricted to files of the given type. """
		return self.fhashdict[ftype]

	def _readManifest(self, file_path, myhashdict=None, **kwargs):
		"""Parse a manifest.  If myhashdict is given then data will be added too it.
		   Otherwise, a new dict will be created and returned."""
		try:
			with io.open(_unicode_encode(file_path,
				encoding=_encodings['fs'], errors='strict'), mode='r',
				encoding=_encodings['repo.content'], errors='replace') as f:
				if myhashdict is None:
					myhashdict = {}
				self._parseDigests(f, myhashdict=myhashdict, **kwargs)
			return myhashdict
		except (OSError, IOError) as e:
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

	def _parseManifestLines(self, mylines):
		"""Parse manifest lines and return a list of manifest entries."""
		for myline in mylines:
			myentry = None
			for parser in self.parsers:
				myentry = parser(myline)
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

	def _createManifestEntries(self):
		valid_hashes = set(get_valid_checksum_keys())
		valid_hashes.add('size')
		mytypes = list(self.fhashdict)
		mytypes.sort()
		for t in mytypes:
			myfiles = list(self.fhashdict[t])
			myfiles.sort()
			for f in myfiles:
				myentry = Manifest2Entry(
					type=t, name=f, hashes=self.fhashdict[t][f].copy())
				for h in list(myentry.hashes):
					if h not in valid_hashes:
						del myentry.hashes[h]
				yield myentry

	def checkIntegrity(self):
		for t in self.fhashdict:
			for f in self.fhashdict[t]:
				diff = self.required_hashes.difference(
						set(self.fhashdict[t][f]))
				if diff:
					raise MissingParameter(_("Missing %s checksum(s): %s %s") %
						(' '.join(diff), t, f))

	def write(self, sign=False, force=False):
		""" Write Manifest instance to disk, optionally signing it. Returns
		True if the Manifest is actually written, and False if the write
		is skipped due to existing Manifest being identical."""
		rval = False
		if not self.allow_create:
			return rval
		self.checkIntegrity()
		try:
			myentries = list(self._createManifestEntries())
			update_manifest = True
			preserved_stats = {}
			preserved_stats[self.pkgdir.rstrip(os.sep)] = os.stat(self.pkgdir)
			if myentries and not force:
				try:
					f = io.open(_unicode_encode(self.getFullname(),
						encoding=_encodings['fs'], errors='strict'),
						mode='r', encoding=_encodings['repo.content'],
						errors='replace')
					oldentries = list(self._parseManifestLines(f))
					preserved_stats[self.getFullname()] = os.fstat(f.fileno())
					f.close()
					if len(oldentries) == len(myentries):
						update_manifest = False
						for i in range(len(oldentries)):
							if oldentries[i] != myentries[i]:
								update_manifest = True
								break
				except (IOError, OSError) as e:
					if e.errno == errno.ENOENT:
						pass
					else:
						raise

			if update_manifest:
				if myentries or not (self.thin or self.allow_missing):
					# If myentries is empty, don't write an empty manifest
					# when thin or allow_missing is enabled. Except for
					# thin manifests with no DIST entries, myentries is
					# non-empty for all currently known use cases.
					write_atomic(self.getFullname(), "".join("%s\n" %
						str(myentry) for myentry in myentries))
					self._apply_max_mtime(preserved_stats, myentries)
					rval = True
				else:
					# With thin manifest, there's no need to have
					# a Manifest file if there are no DIST entries.
					try:
						os.unlink(self.getFullname())
					except OSError as e:
						if e.errno != errno.ENOENT:
							raise
					rval = True

			if sign:
				self.sign()
		except (IOError, OSError) as e:
			if e.errno == errno.EACCES:
				raise PermissionDenied(str(e))
			raise
		return rval

	def _apply_max_mtime(self, preserved_stats, entries):
		"""
		Set the Manifest mtime to the max mtime of all relevant files
		and directories. Directory mtimes account for file renames and
		removals. The existing Manifest mtime accounts for eclass
		modifications that change DIST entries. This results in a
		stable/predictable mtime, which is useful when converting thin
		manifests to thick manifests for distribution via rsync. For
		portability, the mtime is set with 1 second resolution.

		@param preserved_stats: maps paths to preserved stat results
			that should be used instead of os.stat() calls
		@type preserved_stats: dict
		@param entries: list of current Manifest2Entry instances
		@type entries: list
		"""
		# Use stat_result[stat.ST_MTIME] for 1 second resolution, since
		# it always rounds down. Note that stat_result.st_mtime will round
		# up from 0.999999999 to 1.0 when precision is lost during conversion
		# from nanosecond resolution to float.
		max_mtime = None
		_update_max = (lambda st: max_mtime if max_mtime is not None
			and max_mtime > st[stat.ST_MTIME] else st[stat.ST_MTIME])
		_stat = (lambda path: preserved_stats[path] if path in preserved_stats
			else os.stat(path))

		for stat_result in preserved_stats.values():
			max_mtime = _update_max(stat_result)

		for entry in entries:
			if entry.type == 'DIST':
				continue
			abs_path = (os.path.join(self.pkgdir, 'files', entry.name) if
				entry.type == 'AUX' else os.path.join(self.pkgdir, entry.name))
			max_mtime = _update_max(_stat(abs_path))

		if not self.thin:
			# Account for changes to all relevant nested directories.
			# This is not necessary for thin manifests because
			# self.pkgdir is already included via preserved_stats.
			for parent_dir, dirs, files in os.walk(self.pkgdir.rstrip(os.sep)):
				try:
					parent_dir = _unicode_decode(parent_dir,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					# If an absolute path cannot be decoded, then it is
					# always excluded from the manifest (repoman will
					# report such problems).
					pass
				else:
					max_mtime = _update_max(_stat(parent_dir))

		if max_mtime is not None:
			for path in preserved_stats:
				try:
					os.utime(path, (max_mtime, max_mtime))
				except OSError as e:
					# Even though we have write permission, utime fails
					# with EPERM if path is owned by a different user.
					# Only warn in this case, since it's not a problem
					# unless this repo is being prepared for distribution
					# via rsync.
					writemsg_level('!!! utime(\'%s\', (%s, %s)): %s\n' %
						(path, max_mtime, max_mtime, e),
						level=logging.WARNING, noiselevel=-1)

	def sign(self):
		""" Sign the Manifest """
		raise NotImplementedError()

	def validateSignature(self):
		""" Validate signature on Manifest """
		raise NotImplementedError()

	def addFile(self, ftype, fname, hashdict=None, ignoreMissing=False):
		""" Add entry to Manifest optionally using hashdict to avoid recalculation of hashes """
		if ftype == "AUX" and not fname.startswith("files/"):
			fname = os.path.join("files", fname)
		if not os.path.exists(self.pkgdir+fname) and not ignoreMissing:
			raise FileNotFound(fname)
		if not ftype in MANIFEST2_IDENTIFIERS:
			raise InvalidDataType(ftype)
		if ftype == "AUX" and fname.startswith("files"):
			fname = fname[6:]
		self.fhashdict[ftype][fname] = {}
		if hashdict != None:
			self.fhashdict[ftype][fname].update(hashdict)
		if self.required_hashes.difference(set(self.fhashdict[ftype][fname])):
			self.updateFileHashes(ftype, fname, checkExisting=False, ignoreMissing=ignoreMissing)

	def removeFile(self, ftype, fname):
		""" Remove given entry from Manifest """
		del self.fhashdict[ftype][fname]

	def hasFile(self, ftype, fname):
		""" Return whether the Manifest contains an entry for the given type,filename pair """
		return fname in self.fhashdict[ftype]

	def findFile(self, fname):
		""" Return entrytype of the given file if present in Manifest or None if not present """
		for t in MANIFEST2_IDENTIFIERS:
			if fname in self.fhashdict[t]:
				return t
		return None

	def create(self, checkExisting=False, assumeDistHashesSometimes=False,
		assumeDistHashesAlways=False, requiredDistfiles=[]):
		""" Recreate this Manifest from scratch.  This will not use any
		existing checksums unless assumeDistHashesSometimes or
		assumeDistHashesAlways is true (assumeDistHashesSometimes will only
		cause DIST checksums to be reused if the file doesn't exist in
		DISTDIR).  The requiredDistfiles parameter specifies a list of
		distfiles to raise a FileNotFound exception for (if no file or existing
		checksums are available), and defaults to all distfiles when not
		specified."""
		if not self.allow_create:
			return
		if checkExisting:
			self.checkAllHashes()
		if assumeDistHashesSometimes or assumeDistHashesAlways:
			distfilehashes = self.fhashdict["DIST"]
		else:
			distfilehashes = {}
		self.__init__(self.pkgdir, distdir=self.distdir,
			fetchlist_dict=self.fetchlist_dict, from_scratch=True,
			thin=self.thin, allow_missing=self.allow_missing,
			allow_create=self.allow_create, hashes=self.hashes,
			required_hashes=self.required_hashes,
			find_invalid_path_char=self._find_invalid_path_char,
			strict_misc_digests=self.strict_misc_digests)
		pn = os.path.basename(self.pkgdir.rstrip(os.path.sep))
		cat = self._pkgdir_category()

		pkgdir = self.pkgdir
		if self.thin:
			cpvlist = self._update_thin_pkgdir(cat, pn, pkgdir)
		else:
			cpvlist = self._update_thick_pkgdir(cat, pn, pkgdir)

		distlist = set()
		for cpv in cpvlist:
			distlist.update(self._getCpvDistfiles(cpv))

		if requiredDistfiles is None:
			# This allows us to force removal of stale digests for the
			# ebuild --force digest option (no distfiles are required).
			requiredDistfiles = set()
		elif len(requiredDistfiles) == 0:
			# repoman passes in an empty list, which implies that all distfiles
			# are required.
			requiredDistfiles = distlist.copy()
		required_hash_types = set()
		required_hash_types.add("size")
		required_hash_types.update(self.required_hashes)
		for f in distlist:
			fname = os.path.join(self.distdir, f)
			mystat = None
			try:
				mystat = os.stat(fname)
			except OSError:
				pass
			if f in distfilehashes and \
				not required_hash_types.difference(distfilehashes[f]) and \
				((assumeDistHashesSometimes and mystat is None) or \
				(assumeDistHashesAlways and mystat is None) or \
				(assumeDistHashesAlways and mystat is not None and \
				set(distfilehashes[f]) == set(self.hashes) and \
				distfilehashes[f]["size"] == mystat.st_size)):
				self.fhashdict["DIST"][f] = distfilehashes[f]
			else:
				try:
					self.fhashdict["DIST"][f] = perform_multiple_checksums(fname, self.hashes)
				except FileNotFound:
					if f in requiredDistfiles:
						raise

	def _is_cpv(self, cat, pn, filename):
		if not filename.endswith(".ebuild"):
			return None
		pf = filename[:-7]
		ps = portage.versions._pkgsplit(pf)
		cpv = "%s/%s" % (cat, pf)
		if not ps:
			raise PortagePackageException(
				_("Invalid package name: '%s'") % cpv)
		if ps[0] != pn:
			raise PortagePackageException(
				_("Package name does not "
				"match directory name: '%s'") % cpv)
		return cpv

	def _update_thin_pkgdir(self, cat, pn, pkgdir):
		for pkgdir, pkgdir_dirs, pkgdir_files in os.walk(pkgdir):
			break
		cpvlist = []
		for f in pkgdir_files:
			try:
				f = _unicode_decode(f,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				continue
			if f[:1] == '.':
				continue
			pf = self._is_cpv(cat, pn, f)
			if pf is not None:
				cpvlist.append(pf)
		return cpvlist

	def _update_thick_pkgdir(self, cat, pn, pkgdir):
		cpvlist = []
		for pkgdir, pkgdir_dirs, pkgdir_files in os.walk(pkgdir):
			break
		for f in pkgdir_files:
			try:
				f = _unicode_decode(f,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				continue
			if f[:1] == ".":
				continue
			pf = self._is_cpv(cat, pn, f)
			if pf is not None:
				mytype = "EBUILD"
				cpvlist.append(pf)
			elif self._find_invalid_path_char(f) == -1 and \
				manifest2MiscfileFilter(f):
				mytype = "MISC"
			else:
				continue
			self.fhashdict[mytype][f] = perform_multiple_checksums(self.pkgdir+f, self.hashes)
		recursive_files = []

		pkgdir = self.pkgdir
		cut_len = len(os.path.join(pkgdir, "files") + os.sep)
		for parentdir, dirs, files in os.walk(os.path.join(pkgdir, "files")):
			for f in files:
				try:
					f = _unicode_decode(f,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					continue
				full_path = os.path.join(parentdir, f)
				recursive_files.append(full_path[cut_len:])
		for f in recursive_files:
			if self._find_invalid_path_char(f) != -1 or \
				not manifest2AuxfileFilter(f):
				continue
			self.fhashdict["AUX"][f] = perform_multiple_checksums(
				os.path.join(self.pkgdir, "files", f.lstrip(os.sep)), self.hashes)
		return cpvlist

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
		for t in MANIFEST2_IDENTIFIERS:
			self.checkTypeHashes(t, ignoreMissingFiles=ignoreMissingFiles)

	def checkTypeHashes(self, idtype, ignoreMissingFiles=False, hash_filter=None):
		for f in self.fhashdict[idtype]:
			self.checkFileHashes(idtype, f, ignoreMissing=ignoreMissingFiles,
				hash_filter=hash_filter)

	def checkFileHashes(self, ftype, fname, ignoreMissing=False, hash_filter=None):
		digests = _filter_unaccelarated_hashes(self.fhashdict[ftype][fname])
		if hash_filter is not None:
			digests = _apply_hash_filter(digests, hash_filter)
		try:
			ok, reason = verify_all(self._getAbsname(ftype, fname), digests)
			if not ok:
				raise DigestException(tuple([self._getAbsname(ftype, fname)]+list(reason)))
			return ok, reason
		except FileNotFound as e:
			if not ignoreMissing:
				raise
			return False, _("File Not Found: '%s'") % str(e)

	def checkCpvHashes(self, cpv, checkDistfiles=True, onlyDistfiles=False, checkMiscfiles=False):
		""" check the hashes for all files associated to the given cpv, include all
		AUX files and optionally all MISC files. """
		if not onlyDistfiles:
			self.checkTypeHashes("AUX", ignoreMissingFiles=False)
			if checkMiscfiles:
				self.checkTypeHashes("MISC", ignoreMissingFiles=False)
			ebuildname = "%s.ebuild" % self._catsplit(cpv)[1]
			self.checkFileHashes("EBUILD", ebuildname, ignoreMissing=False)
		if checkDistfiles or onlyDistfiles:
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
		if not ignoreMissing and fname not in self.fhashdict[ftype]:
			raise FileNotInManifestException(fname)
		if fname not in self.fhashdict[ftype]:
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
		for idtype in MANIFEST2_IDENTIFIERS:
			self.updateTypeHashes(idtype, checkExisting=checkExisting,
				ignoreMissingFiles=ignoreMissingFiles)

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
		myfile = io.open(_unicode_encode(mfname,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace')
		lines = myfile.readlines()
		myfile.close()
		for l in lines:
			mysplit = l.split()
			if len(mysplit) > 4 and mysplit[0] in MANIFEST2_IDENTIFIERS \
				and ((len(mysplit) - 3) % 2) == 0 and not 2 in rVal:
				rVal.append(2)
		return rVal

	def _catsplit(self, pkg_key):
		"""Split a category and package, returning a list of [cat, pkg].
		This is compatible with portage.catsplit()"""
		return pkg_key.split("/", 1)
