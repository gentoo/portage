# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import errno
import shutil
import warnings

import portage
from portage import os, _encodings, _unicode_decode, _unicode_encode
from portage.data import portage_gid, portage_uid
from portage.dep import dep_getkey
from portage.localization import _
from portage.manifest import Manifest
from portage.util import writemsg, writemsg_stdout

def commit_mtimedb(mydict=None, filename=None):
	warnings.warn("portage.commit_mtimedb() is deprecated, " + \
		"use portage.mtimedb.commit() instead",
		DeprecationWarning, stacklevel=2)

def digestParseFile(myfilename, mysettings=None):
	"""(filename) -- Parses a given file for entries matching:
	<checksumkey> <checksum_hex_string> <filename> <filesize>
	Ignores lines that don't start with a valid checksum identifier
	and returns a dict with the filenames as keys and {checksumkey:checksum}
	as the values.
	DEPRECATED: this function is now only a compability wrapper for
	            portage.manifest.Manifest()."""

	warnings.warn("portage.digestParseFile() is deprecated",
		DeprecationWarning, stacklevel=2)

	mysplit = myfilename.split(os.sep)
	if mysplit[-2] == "files" and mysplit[-1].startswith("digest-"):
		pkgdir = os.sep + os.sep.join(mysplit[:-2]).strip(os.sep)
	elif mysplit[-1] == "Manifest":
		pkgdir = os.sep + os.sep.join(mysplit[:-1]).strip(os.sep)

	return Manifest(pkgdir, None).getDigests()

def dep_virtual(mysplit, mysettings):
	"Does virtual dependency conversion"
	warnings.warn("portage.dep_virtual() is deprecated",
		DeprecationWarning, stacklevel=2)
	newsplit=[]
	myvirtuals = mysettings.getvirtuals()
	for x in mysplit:
		if isinstance(x, list):
			newsplit.append(dep_virtual(x, mysettings))
		else:
			mykey=dep_getkey(x)
			mychoices = myvirtuals.get(mykey, None)
			if mychoices:
				if len(mychoices) == 1:
					a = x.replace(mykey, dep_getkey(mychoices[0]), 1)
				else:
					if x[0]=="!":
						# blocker needs "and" not "or(||)".
						a=[]
					else:
						a=['||']
					for y in mychoices:
						a.append(x.replace(mykey, dep_getkey(y), 1))
				newsplit.append(a)
			else:
				newsplit.append(x)
	return newsplit

def getvirtuals(myroot):
	"""
	Calls portage.settings.getvirtuals().
	@deprecated: Use portage.settings.getvirtuals().
	"""
	warnings.warn("portage.getvirtuals() is deprecated",
		DeprecationWarning, stacklevel=2)
	return portage.settings.getvirtuals()

def pkgmerge(mytbz2, myroot, mysettings, mydbapi=None,
	vartree=None, prev_mtimes=None, blockers=None):
	"""will merge a .tbz2 file, returning a list of runtime dependencies
		that must be satisfied, or None if there was a merge error.	This
		code assumes the package exists."""

	warnings.warn("portage.pkgmerge() is deprecated",
		DeprecationWarning, stacklevel=2)

	if mydbapi is None:
		mydbapi = portage.db[myroot]["bintree"].dbapi
	if vartree is None:
		vartree = portage.db[myroot]["vartree"]
	if mytbz2[-5:]!=".tbz2":
		print(_("!!! Not a .tbz2 file"))
		return 1

	tbz2_lock = None
	mycat = None
	mypkg = None
	did_merge_phase = False
	success = False
	try:
		""" Don't lock the tbz2 file because the filesytem could be readonly or
		shared by a cluster."""
		#tbz2_lock = portage.locks.lockfile(mytbz2, wantnewlockfile=1)

		mypkg = os.path.basename(mytbz2)[:-5]
		xptbz2 = portage.xpak.tbz2(mytbz2)
		mycat = xptbz2.getfile(_unicode_encode("CATEGORY",
			encoding=_encodings['repo.content']))
		if not mycat:
			writemsg(_("!!! CATEGORY info missing from info chunk, aborting...\n"),
				noiselevel=-1)
			return 1
		mycat = _unicode_decode(mycat,
			encoding=_encodings['repo.content'], errors='replace')
		mycat = mycat.strip()

		# These are the same directories that would be used at build time.
		builddir = os.path.join(
			mysettings["PORTAGE_TMPDIR"], "portage", mycat, mypkg)
		catdir = os.path.dirname(builddir)
		pkgloc = os.path.join(builddir, "image")
		infloc = os.path.join(builddir, "build-info")
		myebuild = os.path.join(
			infloc, os.path.basename(mytbz2)[:-4] + "ebuild")
		portage.util.ensure_dirs(os.path.dirname(catdir),
			uid=portage_uid, gid=portage_gid, mode=0o70, mask=0)
		portage.util.ensure_dirs(catdir,
			uid=portage_uid, gid=portage_gid, mode=0o70, mask=0)
		try:
			shutil.rmtree(builddir)
		except (IOError, OSError) as e:
			if e.errno != errno.ENOENT:
				raise
			del e
		for mydir in (builddir, pkgloc, infloc):
			portage.util.ensure_dirs(mydir, uid=portage_uid,
				gid=portage_gid, mode=0o755)
		writemsg_stdout(_(">>> Extracting info\n"))
		xptbz2.unpackinfo(infloc)
		mysettings.setcpv(mycat + "/" + mypkg, mydb=mydbapi)
		# Store the md5sum in the vdb.
		fp = open(_unicode_encode(os.path.join(infloc, 'BINPKGMD5')), 'w')
		fp.write(str(portage.checksum.perform_md5(mytbz2))+"\n")
		fp.close()

		# This gives bashrc users an opportunity to do various things
		# such as remove binary packages after they're installed.
		mysettings["PORTAGE_BINPKG_FILE"] = mytbz2
		mysettings.backup_changes("PORTAGE_BINPKG_FILE")
		debug = mysettings.get("PORTAGE_DEBUG", "") == "1"

		# Eventually we'd like to pass in the saved ebuild env here.
		retval = portage.doebuild(myebuild, "setup", myroot, mysettings, debug=debug,
			tree="bintree", mydbapi=mydbapi, vartree=vartree)
		if retval != os.EX_OK:
			writemsg(_("!!! Setup failed: %s\n") % retval, noiselevel=-1)
			return retval

		writemsg_stdout(_(">>> Extracting %s\n") % mypkg)
		retval = portage.process.spawn_bash(
			"bzip2 -dqc -- '%s' | tar -xp -C '%s' -f -" % (mytbz2, pkgloc),
			env=mysettings.environ())
		if retval != os.EX_OK:
			writemsg(_("!!! Error Extracting '%s'\n") % mytbz2, noiselevel=-1)
			return retval
		#portage.locks.unlockfile(tbz2_lock)
		#tbz2_lock = None

		mylink = portage.dblink(mycat, mypkg, myroot, mysettings, vartree=vartree,
			treetype="bintree", blockers=blockers)
		retval = mylink.merge(pkgloc, infloc, myroot, myebuild, cleanup=0,
			mydbapi=mydbapi, prev_mtimes=prev_mtimes)
		did_merge_phase = True
		success = retval == os.EX_OK
		return retval
	finally:
		mysettings.pop("PORTAGE_BINPKG_FILE", None)
		if tbz2_lock:
			portage.locks.unlockfile(tbz2_lock)
		if True:
			if not did_merge_phase:
				# The merge phase handles this already.  Callers don't know how
				# far this function got, so we have to call elog_process() here
				# so that it's only called once.
				from portage.elog import elog_process
				elog_process(mycat + "/" + mypkg, mysettings)
			try:
				if success:
					shutil.rmtree(builddir)
			except (IOError, OSError) as e:
				if e.errno != errno.ENOENT:
					raise
				del e
