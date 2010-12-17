# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['digestcheck']

import warnings

from portage import os, _encodings, _unicode_decode
from portage.exception import DigestException, FileNotFound
from portage.localization import _
from portage.manifest import Manifest
from portage.output import EOutput
from portage.util import writemsg

def digestcheck(myfiles, mysettings, strict=False, justmanifest=None):
	"""
	Verifies checksums. Assumes all files have been downloaded.
	@rtype: int
	@returns: 1 on success and 0 on failure
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
	manifest_path = os.path.join(pkgdir, "Manifest")
	if not os.path.exists(manifest_path):
		writemsg(_("!!! Manifest file not found: '%s'\n") % manifest_path,
			noiselevel=-1)
		if strict:
			return 0
		else:
			return 1
	mf = Manifest(pkgdir, mysettings["DISTDIR"])
	manifest_empty = True
	for d in mf.fhashdict.values():
		if d:
			manifest_empty = False
			break
	if manifest_empty:
		writemsg(_("!!! Manifest is empty: '%s'\n") % manifest_path,
			noiselevel=-1)
		if strict:
			return 0
		else:
			return 1
	eout = EOutput()
	eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
	try:
		if strict and "PORTAGE_PARALLEL_FETCHONLY" not in mysettings:
			eout.ebegin(_("checking ebuild checksums ;-)"))
			mf.checkTypeHashes("EBUILD")
			eout.eend(0)
			eout.ebegin(_("checking auxfile checksums ;-)"))
			mf.checkTypeHashes("AUX")
			eout.eend(0)
			eout.ebegin(_("checking miscfile checksums ;-)"))
			mf.checkTypeHashes("MISC", ignoreMissingFiles=True)
			eout.eend(0)
		for f in myfiles:
			eout.ebegin(_("checking %s ;-)") % f)
			ftype = mf.findFile(f)
			if ftype is None:
				eout.eend(1)
				writemsg(_("\n!!! Missing digest for '%s'\n") % (f,),
					noiselevel=-1)
				return 0
			mf.checkFileHashes(ftype, f)
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
	""" epatch will just grab all the patches out of a directory, so we have to
	make sure there aren't any foreign files that it might grab."""
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
