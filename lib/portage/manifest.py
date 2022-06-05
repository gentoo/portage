# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import itertools
import logging
import re
import stat
import warnings

import portage

portage.proxy.lazyimport.lazyimport(
    globals(),
    "portage.checksum:get_valid_checksum_keys,perform_multiple_checksums,"
    + "verify_all,_apply_hash_filter,_filter_unaccelarated_hashes",
    "portage.repository.config:_find_invalid_path_char",
    "portage.util:write_atomic,writemsg_level",
)

from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.exception import (
    DigestException,
    FileNotFound,
    InvalidDataType,
    MissingParameter,
    PermissionDenied,
    PortageException,
    PortagePackageException,
)
from portage.const import MANIFEST2_HASH_DEFAULTS, MANIFEST2_IDENTIFIERS
from portage.localization import _

_manifest_re = re.compile(
    r"^(" + "|".join(MANIFEST2_IDENTIFIERS) + r") (\S+)( \d+( \S+ \S+)+)$", re.UNICODE
)


class FileNotInManifestException(PortageException):
    pass


def manifest2AuxfileFilter(filename):
    filename = filename.strip(os.sep)
    mysplit = filename.split(os.path.sep)
    if "CVS" in mysplit:
        return False
    for x in mysplit:
        if x[:1] == ".":
            return False
    return not filename[:7] == "digest-"


def manifest2MiscfileFilter(filename):
    return not (filename == "Manifest" or filename.endswith(".ebuild"))


def guessManifestFileType(filename):
    """Perform a best effort guess of which type the given filename is, avoid using this if possible"""
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
        line = " ".join(line)
    myentry = None
    matched = _manifest_re.match(line)
    if matched:
        tokens = matched.group(3).split()
        hashes = dict(zip(tokens[1::2], tokens[2::2]))
        hashes["size"] = int(tokens[0])
        myentry = Manifest2Entry(
            type=matched.group(1), name=matched.group(2), hashes=hashes
        )
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
        with_hashes = " ".join(f"{h} {self.hashes[h]}" for h in myhashkeys)
        return f"{myline} {with_hashes}"

    def __eq__(self, other):
        return (
            isinstance(other, Manifest2Entry)
            and self.type == other.type
            and self.name == other.name
            and self.hashes == other.hashes
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class Manifest:
    parsers = (parseManifest2,)

    def __init__(
        self,
        pkgdir,
        distdir=None,
        fetchlist_dict=None,
        manifest1_compat=DeprecationWarning,
        from_scratch=False,
        thin=False,
        allow_missing=False,
        allow_create=True,
        hashes=None,
        required_hashes=None,
        find_invalid_path_char=None,
        strict_misc_digests=True,
    ):
        """Create new Manifest instance for package in pkgdir.
        Do not parse Manifest file if from_scratch == True (only for internal use)
            The fetchlist_dict parameter is required only for generation of
            a Manifest (not needed for parsing and checking sums).
            If thin is specified, then the manifest carries only info for
            distfiles."""

        if manifest1_compat is not DeprecationWarning:
            warnings.warn(
                "The manifest1_compat parameter of the "
                "portage.manifest.Manifest constructor is deprecated.",
                DeprecationWarning,
                stacklevel=2,
            )

        if find_invalid_path_char is None:
            find_invalid_path_char = _find_invalid_path_char
        self._find_invalid_path_char = find_invalid_path_char
        self.pkgdir = _unicode_decode(pkgdir).rstrip(os.sep) + os.sep
        self.hashes = set()
        self.required_hashes = set()

        if hashes is None:
            hashes = MANIFEST2_HASH_DEFAULTS
        if required_hashes is None:
            required_hashes = hashes

        self.hashes.update(hashes)
        self.hashes.difference_update(
            hashname
            for hashname in list(self.hashes)
            if hashname not in get_valid_checksum_keys()
        )
        self.hashes.add("size")

        self.required_hashes.update(required_hashes)
        self.required_hashes.intersection_update(self.hashes)

        self.fhashdict = {t: {} for t in MANIFEST2_IDENTIFIERS}

        if not from_scratch:
            # Parse Manifest file for this instance
            try:
                self._readManifest(self.getFullname(), myhashdict=self.fhashdict)
            except FileNotFound:
                pass

        self.fetchlist_dict = {}
        if fetchlist_dict:
            self.fetchlist_dict.update(fetchlist_dict)

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
        """Returns the absolute path to the Manifest file for this instance"""
        return os.path.join(self.pkgdir, "Manifest")

    def getDigests(self):
        """Compability function for old digest/manifest code, returns dict of filename:{hashfunction:hashvalue}"""
        rval = {
            k: v for t in MANIFEST2_IDENTIFIERS for k, v in self.fhashdict[t].items()
        }
        return rval

    def getTypeDigests(self, ftype):
        """Similar to getDigests(), but restricted to files of the given type."""
        return self.fhashdict[ftype]

    def _readManifest(self, file_path, myhashdict=None, **kwargs):
        """Parse a manifest.  If myhashdict is given then data will be added too it.
        Otherwise, a new dict will be created and returned."""
        try:
            with io.open(
                _unicode_encode(file_path, encoding=_encodings["fs"], errors="strict"),
                mode="r",
                encoding=_encodings["repo.content"],
                errors="replace",
            ) as f:
                if myhashdict is None:
                    myhashdict = {}
                self._parseDigests(f, myhashdict=myhashdict, **kwargs)
            return myhashdict
        except (OSError, IOError) as e:
            if e.errno == errno.ENOENT:
                raise FileNotFound(file_path)
            else:
                raise

    def _parseManifestLines(self, mylines):
        """Parse manifest lines and return a list of manifest entries."""
        for myline in mylines:
            myentry = None
            for parser in self.parsers:
                myentry = parser(myline)
                if myentry is not None:
                    yield myentry
                    break  # go to the next line

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
        myhashdict = {
            mytype: {myname: self.fhashdict[mytype][myname]}
            for myname in distlist
            for mytype in self.fhashdict
            if myname in self.fhashdict[mytype]
        }
        return myhashdict

    def _createManifestEntries(self):
        valid_hashes = set(itertools.chain(get_valid_checksum_keys(), ("size",)))
        mytypes = sorted(self.fhashdict)
        for mytype in mytypes:
            myfiles = sorted(self.fhashdict[mytype])
            for myfile in myfiles:
                remainings = set(self.fhashdict[mytype][myfile]).intersection(
                    valid_hashes
                )
                yield Manifest2Entry(
                    type=mytype,
                    name=myfile,
                    hashes={
                        remaining: self.fhashdict[mytype][myfile][remaining]
                        for remaining in remainings
                    },
                )

    def checkIntegrity(self):
        manifest_data = (
            (
                self.required_hashes.difference(set(self.fhashdict[mytype][myfile])),
                mytype,
                myfile,
            )
            for mytype in self.fhashdict
            for myfile in self.fhashdict[mytype]
        )
        for needed_hashes, its_type, its_file in manifest_data:
            if needed_hashes:
                raise MissingParameter(
                    _(
                        f"Missing {' '.join(needed_hashes)} checksum(s): {its_type} {its_file}"
                    )
                )

    def write(self, sign=False, force=False):
        """Write Manifest instance to disk, optionally signing it. Returns
        True if the Manifest is actually written, and False if the write
        is skipped due to existing Manifest being identical."""
        rval = False
        if not self.allow_create:
            return rval
        self.checkIntegrity()
        try:
            myentries = list(self._createManifestEntries())
            update_manifest = True
            preserved_stats = {self.pkgdir.rstrip(os.sep): os.stat(self.pkgdir)}
            if myentries and not force:
                try:
                    with io.open(
                        _unicode_encode(
                            self.getFullname(),
                            encoding=_encodings["fs"],
                            errors="strict",
                        ),
                        mode="r",
                        encoding=_encodings["repo.content"],
                        errors="replace",
                    ) as f:
                        oldentries = list(self._parseManifestLines(f))
                        preserved_stats[self.getFullname()] = os.fstat(f.fileno())
                        if len(oldentries) == len(myentries):
                            update_manifest = False
                            for oldentry, myentry in zip(oldentries, myentries):
                                if oldentry != myentry:
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
                    write_atomic(
                        self.getFullname(),
                        "".join(f"{myentry}\n" for myentry in myentries),
                    )
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

        def _update_max(max_mtime, st):
            stat_mtime = st[stat.ST_MTIME]
            if max_mtime:
                return max(max_mtime, stat_mtime)

        def _stat(path):
            if path in preserved_stats:
                return preserved_stats[path]
            else:
                return os.stat(path)

        max_mtime = None
        for stat_result in preserved_stats.values():
            max_mtime = _update_max(max_mtime, stat_result)

        for entry in entries:
            if entry.type == "DIST":
                continue
            files = ""
            if entry.type == "AUX":
                files = "files"
            abs_path = os.path.join(self.pkgdir, files, entry.name)
            max_mtime = _update_max(max_mtime, _stat(abs_path))

        if not self.thin:
            # Account for changes to all relevant nested directories.
            # This is not necessary for thin manifests because
            # self.pkgdir is already included via preserved_stats.
            for parent_dir, dirs, files in os.walk(self.pkgdir.rstrip(os.sep)):
                try:
                    parent_dir = _unicode_decode(
                        parent_dir, encoding=_encodings["fs"], errors="strict"
                    )
                except UnicodeDecodeError:
                    # If an absolute path cannot be decoded, then it is
                    # always excluded from the manifest (repoman will
                    # report such problems).
                    pass
                else:
                    max_mtime = _update_max(max_mtime, _stat(parent_dir))

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
                    writemsg_level(
                        f"!!! utime('{path}', ({max_mtime}, {max_mtime})): {e}\n",
                        level=logging.WARNING,
                        noiselevel=-1,
                    )

    def sign(self):
        """Sign the Manifest"""
        raise NotImplementedError()

    def validateSignature(self):
        """Validate signature on Manifest"""
        raise NotImplementedError()

    def addFile(self, ftype, fname, hashdict=None, ignoreMissing=False):
        """Add entry to Manifest optionally using hashdict to avoid recalculation of hashes"""
        if ftype == "AUX":
            if not fname.startswith("files/"):
                fname = os.path.join("files", fname)
            if fname.startswith("files"):
                fname = fname[6:]
        if not os.path.exists(f"{self.pkgdir}{fname}") and not ignoreMissing:
            raise FileNotFound(fname)
        if ftype not in MANIFEST2_IDENTIFIERS:
            raise InvalidDataType(ftype)
        self.fhashdict[ftype][fname] = {}
        if hashdict is not None:
            self.fhashdict[ftype][fname].update(hashdict)
        if self.required_hashes.difference(set(self.fhashdict[ftype][fname])):
            self.updateFileHashes(
                ftype, fname, checkExisting=False, ignoreMissing=ignoreMissing
            )

    def removeFile(self, ftype, fname):
        """Remove given entry from Manifest"""
        del self.fhashdict[ftype][fname]

    def hasFile(self, ftype, fname):
        """Return whether the Manifest contains an entry for the given type,filename pair"""
        return fname in self.fhashdict[ftype]

    def findFile(self, fname):
        """Return entrytype of the given file if present in Manifest or None if not present"""
        found_entries = (t for t in MANIFEST2_IDENTIFIERS if fname in self.fhashdict[t])
        return next(found_entries, None)

    def create(
        self,
        checkExisting=False,
        assumeDistHashesSometimes=False,
        assumeDistHashesAlways=False,
        requiredDistfiles=None,
    ):
        """Recreate this Manifest from scratch.  This will not use any
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
        distfilehashes = {}
        if assumeDistHashesSometimes or assumeDistHashesAlways:
            distfilehashes.update(self.fhashdict["DIST"])
        self.__init__(
            self.pkgdir,
            distdir=self.distdir,
            fetchlist_dict=self.fetchlist_dict,
            from_scratch=True,
            thin=self.thin,
            allow_missing=self.allow_missing,
            allow_create=self.allow_create,
            hashes=self.hashes,
            required_hashes=self.required_hashes,
            find_invalid_path_char=self._find_invalid_path_char,
            strict_misc_digests=self.strict_misc_digests,
        )

        update_pkgdir = self._update_thick_pkgdir
        if self.thin:
            update_pkgdir = self._update_thin_pkgdir

        cpvlist = update_pkgdir(
            self._pkgdir_category(),
            os.path.basename(self.pkgdir.rstrip(os.path.sep)),
            self.pkgdir,
        )
        distlist = set(
            distfile for cpv in cpvlist for distfile in self._getCpvDistfiles(cpv)
        )

        if requiredDistfiles is None:
            # This allows us to force removal of stale digests for the
            # ebuild --force digest option (no distfiles are required).
            requiredDistfiles = set()
        elif len(requiredDistfiles) == 0:
            # repoman passes in an empty list, which implies that all distfiles
            # are required.
            requiredDistfiles = distlist.copy()
        required_hash_types = set(itertools.chain(self.required_hashes, ("size",)))
        for f in distlist:
            fname = os.path.join(self.distdir, f)
            mystat = None
            try:
                mystat = os.stat(fname)
            except OSError:
                pass
            if (
                f in distfilehashes
                and not required_hash_types.difference(distfilehashes[f])
                and (
                    (assumeDistHashesSometimes and mystat is None)
                    or (assumeDistHashesAlways and mystat is None)
                    or (
                        assumeDistHashesAlways
                        and mystat is not None
                        and set(distfilehashes[f]) == set(self.hashes)
                        and distfilehashes[f]["size"] == mystat.st_size
                    )
                )
            ):
                self.fhashdict["DIST"][f] = distfilehashes[f]
            else:
                try:
                    self.fhashdict["DIST"][f] = perform_multiple_checksums(
                        fname, self.hashes
                    )
                except FileNotFound:
                    if f in requiredDistfiles:
                        raise

    def _is_cpv(self, cat, pn, filename):
        if not filename.endswith(".ebuild"):
            return None
        pf = filename[:-7]
        ps = portage.versions._pkgsplit(pf)
        cpv = f"{cat}/{pf}"
        if not ps:
            raise PortagePackageException(_(f"Invalid package name: '{cpv}'"))
        if ps[0] != pn:
            raise PortagePackageException(
                _(f"Package name does not match directory name: '{cpv}'")
            )
        return cpv

    def _update_thin_pkgdir(self, cat, pn, pkgdir):
        _, _, pkgdir_files = next(os.walk(pkgdir), (None, None, None))

        def _process_for_cpv(filename):
            try:
                filename = _unicode_decode(
                    filename, encoding=_encodings["fs"], errors="strict"
                )
            except UnicodeDecodeError:
                return None
            if filename.startswith("."):
                return None
            pf = self._is_cpv(cat, pn, filename)
            if pf is not None:
                return pf

        processed = (_process_for_cpv(filename) for filename in pkgdir_files)
        cpvlist = [pf for pf in processed if pf]
        return cpvlist

    def _update_thick_pkgdir(self, cat, pn, pkgdir):
        _, _, pkgdir_files = next(os.walk(pkgdir), (None, None, None))
        cpvlist = []
        for f in pkgdir_files:
            try:
                f = _unicode_decode(f, encoding=_encodings["fs"], errors="strict")
            except UnicodeDecodeError:
                continue
            if f.startswith("."):
                continue
            pf = self._is_cpv(cat, pn, f)
            if pf is not None:
                mytype = "EBUILD"
                cpvlist.append(pf)
            elif self._find_invalid_path_char(f) == -1 and manifest2MiscfileFilter(f):
                mytype = "MISC"
            else:
                continue
            self.fhashdict[mytype][f] = perform_multiple_checksums(
                f"{self.pkgdir}{f}", self.hashes
            )
        recursive_files = []

        pkgdir = self.pkgdir
        cut_len = len(os.path.join(pkgdir, f"files{os.sep}"))
        for parentdir, dirs, files in os.walk(os.path.join(pkgdir, "files")):
            for f in files:
                try:
                    f = _unicode_decode(f, encoding=_encodings["fs"], errors="strict")
                except UnicodeDecodeError:
                    continue
                full_path = os.path.join(parentdir, f)
                recursive_files.append(full_path[cut_len:])
        for f in recursive_files:
            if self._find_invalid_path_char(f) != -1 or not manifest2AuxfileFilter(f):
                continue
            self.fhashdict["AUX"][f] = perform_multiple_checksums(
                os.path.join(self.pkgdir, "files", f.lstrip(os.sep)), self.hashes
            )
        return cpvlist

    def _pkgdir_category(self):
        return self.pkgdir.rstrip(os.sep).split(os.sep)[-2]

    def _getAbsname(self, ftype, fname):
        if ftype == "DIST":
            abspath = (self.distdir, fname)
        elif ftype == "AUX":
            abspath = (self.pkgdir, "files", fname)
        else:
            abspath = (self.pkgdir, fname)
        return os.path.join(*abspath)

    def checkAllHashes(self, ignoreMissingFiles=False):
        for t in MANIFEST2_IDENTIFIERS:
            self.checkTypeHashes(t, ignoreMissingFiles=ignoreMissingFiles)

    def checkTypeHashes(self, idtype, ignoreMissingFiles=False, hash_filter=None):
        for f in self.fhashdict[idtype]:
            self.checkFileHashes(
                idtype, f, ignoreMissing=ignoreMissingFiles, hash_filter=hash_filter
            )

    def checkFileHashes(self, ftype, fname, ignoreMissing=False, hash_filter=None):
        digests = _filter_unaccelarated_hashes(self.fhashdict[ftype][fname])
        if hash_filter is not None:
            digests = _apply_hash_filter(digests, hash_filter)
        try:
            ok, reason = verify_all(self._getAbsname(ftype, fname), digests)
            if not ok:
                raise DigestException(
                    tuple([self._getAbsname(ftype, fname)] + list(reason))
                )
            return ok, reason
        except FileNotFound as e:
            if not ignoreMissing:
                raise
            return False, _(f"File Not Found: '{e}'")

    def checkCpvHashes(
        self, cpv, checkDistfiles=True, onlyDistfiles=False, checkMiscfiles=False
    ):
        """check the hashes for all files associated to the given cpv, include all
        AUX files and optionally all MISC files."""
        if not onlyDistfiles:
            self.checkTypeHashes("AUX", ignoreMissingFiles=False)
            if checkMiscfiles:
                self.checkTypeHashes("MISC", ignoreMissingFiles=False)
            ebuildname = f"{self._catsplit(cpv)[1]}.ebuild"
            self.checkFileHashes("EBUILD", ebuildname, ignoreMissing=False)
        if checkDistfiles or onlyDistfiles:
            for f in self._getCpvDistfiles(cpv):
                self.checkFileHashes("DIST", f, ignoreMissing=False)

    def _getCpvDistfiles(self, cpv):
        """Get a list of all DIST files associated to the given cpv"""
        return self.fetchlist_dict[cpv]

    def getDistfilesSize(self, fetchlist):
        total_bytes = sum(int(self.fhashdict["DIST"][f]["size"]) for f in fetchlist)
        return total_bytes

    def updateAllFileHashes(
        self, ftype, fnames, checkExisting=True, ignoreMissing=True, reuseExisting=False
    ):
        """Regenerate hashes from a list of files"""
        for fname in fnames:
            if checkExisting:
                self.checkFileHashes(ftype, fname, ignoreMissing=ignoreMissing)
            if not ignoreMissing and fname not in self.fhashdict[ftype]:
                raise FileNotInManifestException(fname)
            if fname not in self.fhashdict[ftype]:
                self.fhashdict[ftype][fname] = {}
            myhashkeys = self.hashes
            if reuseExisting:
                myhashkeys = myhashkeys.difference(self.fhashdict[ftype][fname])
            myhashes = perform_multiple_checksums(
                self._getAbsname(ftype, fname), myhashkeys
            )
            self.fhashdict[ftype][fname].update(myhashes)

    def updateAllTypeHashes(
        self, idtypes, checkExisting=False, ignoreMissingFiles=True
    ):
        """Regenerate all hashes for all files from a list of types"""
        for idtype in idtypes:
            self.updateAllFileHashes(
                ftype=idtype, fnames=self.fhashdict[idtype], checkExisting=checkExisting
            )

    def updateAllHashes(self, checkExisting=False, ignoreMissingFiles=True):
        """Regenerate all hashes for all files in this Manifest."""
        self.updateTypeHashes(
            idtypes=MANIFEST2_IDENTIFIERS,
            checkExisting=checkExisting,
            ignoreMissingFiles=ignoreMissingFiles,
        )

    def updateCpvHashes(self, cpv, ignoreMissingFiles=True):
        """Regenerate all hashes associated to the given cpv (includes all AUX and MISC
        files)."""
        self.updateAllTypeHashes(
            idtypes=("AUX", "MISC"),
            ignoreMissingFiles=ignoreMissingFiles,
        )
        self.updateAllFileHashes(
            ftype="EBUILD",
            fnames=(f"{self._catsplit(cpv)[1]}.ebuild",),
            ignoreMissingFiles=ignoreMissingFiles,
        )
        self.updateAllFileHashes(
            ftype="DIST",
            fnames=self._getCpvDistfiles(cpv),
            ignoreMissingFiles=ignoreMissingFiles,
        )

    def updateHashesGuessType(self, fname, *args, **kwargs):
        """Regenerate hashes for the given file (guesses the type and then
        calls updateFileHashes)."""
        mytype = self.guessType(fname)
        if mytype is None:
            return
        elif mytype == "AUX":
            fname = fname[len(f"files{os.sep}") :]
        myrealtype = self.findFile(fname)
        if myrealtype is not None:
            mytype = myrealtype
        return self.updateAllFileHashes(ftype=mytype, fnames=(fname,), *args, **kwargs)

    def getFileData(self, ftype, fname, key):
        """Return the value of a specific (type,filename,key) triple, mainly useful
        to get the size for distfiles."""
        return self.fhashdict[ftype][fname][key]

    def getVersions(self):
        """Returns a list of manifest versions present in the manifest file."""
        mfname = self.getFullname()
        if not os.path.exists(mfname):
            return []
        with io.open(
            _unicode_encode(mfname, encoding=_encodings["fs"], errors="strict"),
            mode="r",
            encoding=_encodings["repo.content"],
            errors="replace",
        ) as myfile:
            line_splits = (line.split() for line in myfile.readlines())
            validation = (
                True
                for line_split in line_splits
                if len(line_split) > 4
                and line_split[0] in MANIFEST2_IDENTIFIERS
                and (len(line_split) - 3) % 2 == 0
            )
            if any(validation):
                return [2]
        return []

    def _catsplit(self, pkg_key):
        """Split a category and package, returning a list of [cat, pkg].
        This is compatible with portage.catsplit()"""
        return pkg_key.split("/", 1)
