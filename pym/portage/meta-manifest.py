
from __future__ import unicode_literals

import argparse
import errno
import io
import logging
import re
import stat
import subprocess
import sys
import warnings

import portage
portage.proxy.lazyimport.lazyimport(globals(),
        'portage.checksum:hashfunc_map,perform_multiple_checksums,' + \
                'verify_all,_apply_hash_filter,_filter_unaccelarated_hashes',
        'portage.repository.config:_find_invalid_path_char',
        'portage.util:write_atomic,writemsg_level',
)

from gkeys.gkeysinterface import GkeysInterface
from gkeys.config import GKeysConfig
from pyGPG.gpg import GPG
from gkeys.lib import GkeysGPG

from portage import manifest
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.manifest import guessManifestFileType
from portage.exception import DigestException, FileNotFound, \
        InvalidDataType, MissingParameter, PermissionDenied, \
        PortageException, PortagePackageException
from portage.const import (MANIFEST1_HASH_FUNCTIONS, MANIFEST2_HASH_DEFAULTS,
        MANIFEST2_HASH_FUNCTIONS, MANIFEST2_IDENTIFIERS, MANIFEST2_REQUIRED_HASH)
from portage.localization import _

if sys.hexversion >= 0x3000000:
	# pylint: disable=W0622
	_unicode = str
	basestring = str
else:
	_unicode = unicode


class MetaManifest(manifest.Manifest):
	'''Subclass of the Manifest class for Manifest files outside the packages'''

	def sign(self):
		'''Signs MetaManifest file with the default PORTAGE_GPG_KEY''' 
		filename = self.getFullname()
		portage_settings = portage.config(clone=portage.settings)
		portage_portdbapi = portage.portdbapi(portage_settings)
		gpgcmd = portage_settings.get("PORTAGE_GPG_SIGNING_COMMAND")
		if gpgcmd in [None, '']:
			raise portage.exception.MissingParameter(
				"PORTAGE_GPG_SIGNING_COMMAND is unset! Is make.globals missing?")
		if "${PORTAGE_GPG_KEY}" in gpgcmd and "PORTAGE_GPG_KEY" not in portage_settings:
			raise portage.exception.MissingParameter("PORTAGE_GPG_KEY is unset!")
		if "${PORTAGE_GPG_DIR}" in gpgcmd:
			if "PORTAGE_GPG_DIR" not in portage_settings:
				portage_settings["PORTAGE_GPG_DIR"] = os.path.expanduser("~/.gnupg")
			else:
				portage_settings["PORTAGE_GPG_DIR"] = os.path.expanduser(portage_settings["PORTAGE_GPG_DIR"])
			if not os.access(portage_settings["PORTAGE_GPG_DIR"], os.X_OK):
				raise portage.exception.InvalidLocation(
					"Unable to access directory: PORTAGE_GPG_DIR='%s'" %
					portage_settings["PORTAGE_GPG_DIR"])
		gpgvars = {"FILE": filename}
		for setting in ("PORTAGE_GPG_DIR", "PORTAGE_GPG_KEY"):
			keyvar = portage_settings.get(setting)
			if keyvar is not None:
				gpgvars[setting] = keyvar
		gpgcmd = portage.util.varexpand(gpgcmd, mydict=gpgvars)
		gpgcmd = portage.util.shlex_split(gpgcmd)
		gpgcmd = [portage._unicode_encode(arg, encoding=portage._encodings['fs'], errors='strict') for arg in gpgcmd]
		return_code = subprocess.call(gpgcmd)
		if return_code == os.EX_OK:
			os.rename(filename + ".asc", filename)
		else:
			raise portage.exception.PortageException("!!! gpg exited with '" + str(return_code) + "' status")

	def find_reporoot(self):
		'''Finds reporoot'''
		repodir = self.pkgdir
		while len(set(['metadata', 'eclass', 'profiles']).intersection(os.listdir(repodir))) == 0:
			myrepo = repodir.split(os.path.sep)[1:-1]
			if myrepo[-1] not in myrepo[:-1]:
				repodir = repodir.replace(("/" +  myrepo[-1]), "")
			else:
				raise("Invalid path")
		self.reporoot = repodir

	def find_repolevel(self, path):
		'''Finds repolevel'''
		self.find_reporoot()
		path = path.replace(self.reporoot, "")
		myrepo = path.split(os.path.sep)
		repolevel = len(myrepo)
		return repolevel

	def find_repotype(self, path):
		'''Finds the type of the repo directory'''
		if len(set(['metadata', 'eclass', 'profiles']).intersection(os.listdir(path))) > 0:
			return 'root'
		elif path.endswith("eclass/"):
			return 'eclass'
		elif path.endswith("profiles/"):
			return 'profile'
		else:
			if self.find_repolevel(path) == 2:
				return 'category'
			else:
				return 'package'

	def create(self):
		'''Creates a MetaManifest file'''
		repodir = self.pkgdir
		repotype = self.find_repotype(repodir)
		if repotype == 'profile':
			self.create_profile()
		elif repotype == 'eclass':
			self.create_eclass()
		elif repotype == 'root':
			self.create_master()
		else:
			self.create_cat()

	def create_master(self):
		'''Creates a MetaManifest file from all the MetaManifest files of the repository'''
		self.find_reporoot()
		myrepodir = self.reporoot
		self.pkgdir = self.reporoot
		self.fhashdict = {}
		for ftype in MANIFEST2_IDENTIFIERS:
			self.fhashdict[ftype] = {}
		for file in os.listdir(myrepodir):
			fpath = os.path.join(myrepodir, file)
			if os.path.isfile(fpath):
				if not fpath.endswith('Manifest'):
					ftype = guessManifestFileType(fpath, is_pkg=False)
					self.fhashdict[ftype][f] = perform_multiple_checksums(fpath, self.hashes)
			else:
				for mf in os.listdir(fpath):
					mfpath = os.path.join(fpath, mf)
					if mfpath.endswith('Manifest'):
						f = mfpath.replace(self.reporoot, "")
						self.fhashdict["MANIFEST"][f] = perform_multiple_checksums(mfpath, self.hashes) 

	def create_eclass(self):
		'''Creates a MetaManifest file in the eclass directory'''
		eclass_dir = self.pkgdir
		self.fhashdict = {}
		for ftype in MANIFEST2_IDENTIFIERS:
			self.fhashdict[ftype] = {}

		for eclass_dir, eclassdir_dir, files in os.walk(eclass_dir):
			for f in files:
				try:
                                        f = _unicode_decode(f,encoding=_encodings['fs'], errors='strict')
                                        eclass_dir = _unicode_decode(eclass_dir,encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
                        	        continue
				fpath = os.path.join(eclass_dir, f)
				ftype = guessManifestFileType(fpath, is_pkg=False)
				f = fpath.replace(self.pkgdir, "")
				if not f.endswith("Manifest"):
					self.fhashdict[ftype][f] = perform_multiple_checksums(fpath, self.hashes)

	def create_cat(self):
		'''Creates a MetaManifest file in the selected category'''
		catdir = self.pkgdir
		for ftype in MANIFEST2_IDENTIFIERS:
                        self.fhashdict[ftype] = {}
		for pkg_dir in os.listdir(catdir):
			pkg_dir = os.path.join(catdir, pkg_dir)
			if os.path.isdir(pkg_dir):
				for file in os.listdir(pkg_dir):
					fpath = os.path.join(pkg_dir, file)
					if os.path.isfile(fpath) and fpath.endswith('Manifest'):
						new_mf = MetaManifest(fpath.replace('Manifest', ""))
						new_mf.verify_manifest()
						f = fpath.replace(self.pkgdir, "")
						self.fhashdict["MANIFEST"][f] = perform_multiple_checksums(fpath, self.hashes)

	def create_profile(self):
		'''Creates a MetaManifest file in the profiles directory'''
		profiledir = self.pkgdir
		for ftype in MANIFEST2_IDENTIFIERS:
                        self.fhashdict[ftype] = {}
		for profiledir, profiledir_dir, files in os.walk(profiledir):
			for f in files:
				try:
					f = _unicode_decode(f,encoding=_encodings['fs'], errors='strict')
					profiledir = _unicode_decode(profiledir,encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					continue
				fpath = os.path.join(profiledir, f)
				ftype = guessManifestFileType(fpath, is_pkg=False)
				if ftype == "OTHER":
					ftype = "DATA"
				f = fpath.replace(self.pkgdir, "")
				if not f.endswith("Manifest"):
					self.fhashdict[ftype][f] = perform_multiple_checksums(fpath, self.hashes)

	def checkFileHashes(self, ftype, fname, ignoreMissing=False, hash_filter=None):
                digests = _filter_unaccelarated_hashes(self.fhashdict[ftype][fname])
                if hash_filter is not None:
                        digests = _apply_hash_filter(digests, hash_filter)
                try:
                        if ftype not in ('DIST'):
                                ok, reason = verify_all(self._getAbsname(ftype, fname), digests)
                                if not ok:
                                        raise DigestException(tuple([self._getAbsname(ftype, fname)]+list(reason)))
                                return ok, reason
                except FileNotFound as e:
                        if not ignoreMissing:
                                raise
                        return False, _("File Not Found: '%s'") % str(e)


	def validate_signature(self):
		'''Validate the Manifest's file signature.'''
		self.gkeys = GkeysInterface('portage', '/')
		is_good, has_sig = self.gkeys.verify_file(self.getFullname())
		return (is_good, has_sig)

	def verify_manifest(self, verify_pkgs = True):
		'''Verifies the manifest's validity'''
		mfdir = self.pkgdir
		mftype = self.find_repotype(mfdir)
		if mftype == 'root':
			for ftype in MANIFEST2_IDENTIFIERS:
				for f in self.fhashdict[ftype]:
					if ftype != 'MANIFEST':
						self.checkFileHashes(ftype, f, ignoreMissing=False)
					else:
						mfpath = os.path.join(mfdir, f.replace("Manifest", ""))
						missing = False
						if not os.path.exists(mfpath) and self.find_repotype(f) is 'category':
							missing = true
						self.checkFileHashes('MANIFEST', f, ignoreMissing=missing)
						new_mf = MetaManifest(mfpath)
						new_mf.verify_manifest(verify_pkgs=verify_pkgs)
		elif mftype == 'category':
			for f in self.fhashdict['MANIFEST']:
				mfpath = os.path.join(mfdir, f.replace("Manifest", ""))
				if not os.path.exists(mfpath) and self.find_repotype(f) is 'package':
					self.checkFileHashes('MANIFEST', f, ignoreMissing=True)
				else:
					self.checkFileHashes('MANIFEST', f, ignoreMissing=False)
				if verify_pkgs:
					new_mfpath = os.path.join(mfdir, f.replace("Manifest", ""))
					new_mf = MetaManifest(new_mfpath)
					new_mf.verify_manifest(verify_pkgs=verify_pkgs)
		else:
			self.checkAllHashes(ignoreMissingFiles=False)

if __name__ == '__main__':
	try:

		parser = argparse.ArgumentParser(description='Process some integers.')
		parser.add_argument('directory', metavar='d', type=str,
			help='the selected directory')
		args = parser.parse_args()
		meta_manifest = MetaManifest(args.directory)
		meta_manifest.create()
		meta_manifest.write(sign=True)
		#meta_manifest.verify_manifest(verify_pkgs=True)
	except KeyboardInterrupt:
		print('interrupted ...', file=sys.stderr)
		exit(1)


