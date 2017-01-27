# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['digestcheck']

import warnings

from portage import os, _encodings, _unicode_decode
from portage.checksum import _hash_filter
from portage.exception import DigestException, FileNotFound
from portage.localization import _
from portage.output import EOutput
from portage.util import writemsg

def digestcheck(myfiles, mysettings, strict=False, justmanifest=None, mf=None):
	"""
	Verifies checksums. Assumes all files have been downloaded.
	@rtype: int
	@return: 1 on success and 0 on failure
	"""

	if justmanifest is not None:
		warnings.warn("The justmanifest parameter of the " + \
			"portage.package.ebuild.digestcheck.digestcheck()" + \
			" function is now unused.",
			DeprecationWarning, stacklevel=2)
		justmanifest = None

	if mysettings.get("EBUILD_SKIP_MANIFEST") == "1":
		return 1
	pkgdir = mysettings["O"]
	hash_filter = _hash_filter(mysettings.get("PORTAGE_CHECKSUM_FILTER", ""))
	if hash_filter.transparent:
		hash_filter = None
	if mf is None:
		mf = mysettings.repositories.get_repo_for_location(
			os.path.dirname(os.path.dirname(pkgdir)))
		mf = mf.load_manifest(pkgdir, mysettings["DISTDIR"])
	eout = EOutput()
	eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
	try:
		if not mf.thin and strict and "PORTAGE_PARALLEL_FETCHONLY" not in mysettings:
			if mf.fhashdict.get("EBUILD"):
				eout.ebegin(_("checking ebuild checksums ;-)"))
				mf.checkTypeHashes("EBUILD", hash_filter=hash_filter)
				eout.eend(0)
			if mf.fhashdict.get("AUX"):
				eout.ebegin(_("checking auxfile checksums ;-)"))
				mf.checkTypeHashes("AUX", hash_filter=hash_filter)
				eout.eend(0)
			if mf.strict_misc_digests and mf.fhashdict.get("MISC"):
				eout.ebegin(_("checking miscfile checksums ;-)"))
				mf.checkTypeHashes("MISC", ignoreMissingFiles=True,
					hash_filter=hash_filter)
				eout.eend(0)
		for f in myfiles:
			eout.ebegin(_("checking %s ;-)") % f)
			ftype = mf.findFile(f)
			if ftype is None:
				if mf.allow_missing:
					continue
				eout.eend(1)
				writemsg(_("\n!!! Missing digest for '%s'\n") % (f,),
					noiselevel=-1)
				return 0
			mf.checkFileHashes(ftype, f, hash_filter=hash_filter)
			eout.eend(0)
	except FileNotFound as e:
		eout.eend(1)
		writemsg(_("\n!!! A file listed in the Manifest could not be found: %s\n") % str(e),
			noiselevel=-1)
		return 0
	except DigestException as e:
		eout.eend(1)
		writemsg(_("\n!!! Digest verification failed:\n"), noiselevel=-1)
		writemsg("!!! %s\n" % e.value[0], noiselevel=-1)
		writemsg(_("!!! Reason: %s\n") % e.value[1], noiselevel=-1)
		writemsg(_("!!! Got: %s\n") % e.value[2], noiselevel=-1)
		writemsg(_("!!! Expected: %s\n") % e.value[3], noiselevel=-1)
		return 0
	if mf.thin or mf.allow_missing:
		# In this case we ignore any missing digests that
		# would otherwise be detected below.
		return 1
	# Make sure that all of the ebuilds are actually listed in the Manifest.
	for f in os.listdir(pkgdir):
		pf = None
		if f[-7:] == '.ebuild':
			pf = f[:-7]
		if pf is not None and not mf.hasFile("EBUILD", f):
			writemsg(_("!!! A file is not listed in the Manifest: '%s'\n") % \
				os.path.join(pkgdir, f), noiselevel=-1)
			if strict:
				return 0
	# epatch will just grab all the patches out of a directory, so we have to
	# make sure there aren't any foreign files that it might grab.
	filesdir = os.path.join(pkgdir, "files")

	for parent, dirs, files in os.walk(filesdir):
		try:
			parent = _unicode_decode(parent,
				encoding=_encodings['fs'], errors='strict')
		except UnicodeDecodeError:
			parent = _unicode_decode(parent,
				encoding=_encodings['fs'], errors='replace')
			writemsg(_("!!! Path contains invalid "
				"character(s) for encoding '%s': '%s'") \
				% (_encodings['fs'], parent), noiselevel=-1)
			if strict:
				return 0
			continue
		for d in dirs:
			d_bytes = d
			try:
				d = _unicode_decode(d,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				d = _unicode_decode(d,
					encoding=_encodings['fs'], errors='replace')
				writemsg(_("!!! Path contains invalid "
					"character(s) for encoding '%s': '%s'") \
					% (_encodings['fs'], os.path.join(parent, d)),
					noiselevel=-1)
				if strict:
					return 0
				dirs.remove(d_bytes)
				continue
			if d.startswith(".") or d == "CVS":
				dirs.remove(d_bytes)
		for f in files:
			try:
				f = _unicode_decode(f,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				f = _unicode_decode(f,
					encoding=_encodings['fs'], errors='replace')
				if f.startswith("."):
					continue
				f = os.path.join(parent, f)[len(filesdir) + 1:]
				writemsg(_("!!! File name contains invalid "
					"character(s) for encoding '%s': '%s'") \
					% (_encodings['fs'], f), noiselevel=-1)
				if strict:
					return 0
				continue
			if f.startswith("."):
				continue
			f = os.path.join(parent, f)[len(filesdir) + 1:]
			file_type = mf.findFile(f)
			if file_type != "AUX" and not f.startswith("digest-"):
				writemsg(_("!!! A file is not listed in the Manifest: '%s'\n") % \
					os.path.join(filesdir, f), noiselevel=-1)
				if strict:
					return 0
	return 1
