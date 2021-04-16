# Copyright 2005-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os, _unicode_encode
from portage.const import MERGING_IDENTIFIER, EPREFIX, PRIVATE_PATH, VDB_PATH
from portage.dep import isvalidatom

import shutil
import subprocess
import sys
import time

class TrackingFile:
	"""File for keeping track of failed merges."""


	def __init__(self, tracking_path):
		"""
		Create a TrackingFile object.

		@param tracking_path: file path used to keep track of failed merges
		@type tracking_path: String
		"""
		self._tracking_path = _unicode_encode(tracking_path)


	def save(self, failed_pkgs):
		"""
		Save the specified packages that failed to merge.

		@param failed_pkgs: dictionary of failed packages
		@type failed_pkgs: dict
		"""
		tracking_path = self._tracking_path
		lines = ['%s %s' % (pkg, mtime) for pkg, mtime in failed_pkgs.items()]
		portage.util.write_atomic(tracking_path, '\n'.join(lines))


	def load(self):
		"""
		Load previously failed merges.

		@rtype: dict
		@return: dictionary of packages that failed to merge
		"""
		tracking_path = self._tracking_path
		if not self.exists():
			return {}
		failed_pkgs = {}
		with open(tracking_path, 'r') as tracking_file:
			for failed_merge in tracking_file:
				pkg, mtime = failed_merge.strip().split()
				failed_pkgs[pkg] = mtime
		return failed_pkgs


	def exists(self):
		"""
		Check if tracking file exists.

		@rtype: bool
		@return: true if tracking file exists, false otherwise
		"""
		return os.path.exists(self._tracking_path)


	def purge(self):
		"""Delete previously saved tracking file if one exists."""
		if self.exists():
			os.remove(self._tracking_path)


	def __iter__(self):
		"""
		Provide an interator over failed merges.

		@return: iterator of packages that failed to merge
		"""
		return self.load().items().__iter__()


class MergesHandler:
	"""Handle failed package merges."""

	short_desc = "Remove failed merges"

	@staticmethod
	def name():
		return "merges"


	def __init__(self):
		"""Create MergesHandler object."""
		eroot = portage.settings['EROOT']
		tracking_path = os.path.join(eroot, PRIVATE_PATH, 'failed-merges')
		self._tracking_file = TrackingFile(tracking_path)
		self._vardb_path = os.path.join(eroot, VDB_PATH)


	def can_progressbar(self, func):
		return func == 'check'


	def _scan(self, onProgress=None):
		"""
		Scan the file system for failed merges and return any found.

		@param onProgress: function to call for updating progress
		@type onProgress: Function
		@rtype: dict
		@return: dictionary of packages that failed to merges
		"""
		failed_pkgs = {}
		for cat in os.listdir(self._vardb_path):
			pkgs_path = os.path.join(self._vardb_path, cat)
			if not os.path.isdir(pkgs_path):
				continue
			pkgs = os.listdir(pkgs_path)
			maxval = len(pkgs)
			for i, pkg in enumerate(pkgs):
				if onProgress:
					onProgress(maxval, i+1)
				if MERGING_IDENTIFIER in pkg:
					mtime = int(os.stat(os.path.join(pkgs_path, pkg)).st_mtime)
					pkg = os.path.join(cat, pkg)
					failed_pkgs[pkg] = mtime
		return failed_pkgs


	def _failed_pkgs(self, onProgress=None):
		"""
		Return failed packages from both the file system and tracking file.

		@rtype: dict
		@return: dictionary of packages that failed to merges
		"""
		failed_pkgs = self._scan(onProgress)
		for pkg, mtime in self._tracking_file:
			if pkg not in failed_pkgs:
				failed_pkgs[pkg] = mtime
		return failed_pkgs


	def _remove_failed_dirs(self, failed_pkgs):
		"""
		Remove the directories of packages that failed to merge.

		@param failed_pkgs: failed packages whose directories to remove
		@type failed_pkg: dict
		"""
		for failed_pkg in failed_pkgs:
			pkg_path = os.path.join(self._vardb_path, failed_pkg)
			# delete failed merge directory if it exists (it might not exist
			# if loaded from tracking file)
			if os.path.exists(pkg_path):
				shutil.rmtree(pkg_path)
			# TODO: try removing package CONTENTS to prevent orphaned
			# files


	def _get_pkg_atoms(self, failed_pkgs, pkg_atoms, pkg_invalid_entries):
		"""
		Get the package atoms for the specified failed packages.

		@param failed_pkgs: failed packages to iterate
		@type failed_pkgs: dict
		@param pkg_atoms: add package atoms to this set
		@type pkg_atoms: set
		@param pkg_invalid_entries: add any packages that are invalid to this set
		@type pkg_invalid_entries: set
		"""

		portdb = portage.db[portage.root]['porttree'].dbapi
		for failed_pkg in failed_pkgs:
			# validate pkg name
			pkg_name = '%s' % failed_pkg.replace(MERGING_IDENTIFIER, '')
			pkg_atom = '=%s' % pkg_name

			if not isvalidatom(pkg_atom):
				pkg_invalid_entries.add("'%s' is an invalid package atom."
					% pkg_atom)
			if not portdb.cpv_exists(pkg_name):
				pkg_invalid_entries.add(
					"'%s' does not exist in the ebuild repository." % pkg_name)
			pkg_atoms.add(pkg_atom)


	def _emerge_pkg_atoms(self, module_output, pkg_atoms, yes=False):
		"""
		Emerge the specified packages atoms.

		@param module_output: output will be written to
		@type module_output: Class
		@param pkg_atoms: packages atoms to emerge
		@type pkg_atoms: set
		@param yes: do not prompt for emerge invocations
		@type yes: bool
		@rtype: list
		@return: List of results
		"""
		# TODO: rewrite code to use portage's APIs instead of a subprocess
		env = {
			"FEATURES" : "-collision-protect -protect-owned",
			"PATH" : os.environ["PATH"]
		}
		emerge_cmd = (
			portage._python_interpreter,
			'-b',
			os.path.join(EPREFIX or '/', 'usr', 'bin', 'emerge'),
			'--ask=n' if yes else '--ask',
			'--quiet',
			'--oneshot',
			'--complete-graph=y'
		)
		results = []
		msg = 'Re-Emerging packages that failed to merge...\n'
		if module_output:
			module_output.write(msg)
		else:
			module_output = subprocess.PIPE
			results.append(msg)
		proc = subprocess.Popen(emerge_cmd + tuple(pkg_atoms), env=env,
			stdout=module_output, stderr=sys.stderr)
		output = proc.communicate()[0]
		if output:
			results.append(output)
		if proc.returncode != os.EX_OK:
			emerge_status = "Failed to emerge '%s'" % (' '.join(pkg_atoms))
		else:
			emerge_status = "Successfully emerged '%s'" % (' '.join(pkg_atoms))
		results.append(emerge_status)
		return results


	def check(self, **kwargs):
		"""Check for failed merges."""
		onProgress = kwargs.get('onProgress', None)
		failed_pkgs = self._failed_pkgs(onProgress)
		errors = []
		for pkg, mtime in failed_pkgs.items():
			mtime_str = time.ctime(int(mtime))
			errors.append("'%s' failed to merge on '%s'" % (pkg, mtime_str))
		if errors:
			return (False, errors)
		return (True, None)


	def fix(self, **kwargs):
		"""Attempt to fix any failed merges."""
		module_output = kwargs.get('module_output', None)
		failed_pkgs = self._failed_pkgs()
		if not failed_pkgs:
			return (True, ['No failed merges found.'])

		pkg_invalid_entries = set()
		pkg_atoms = set()
		self._get_pkg_atoms(failed_pkgs, pkg_atoms, pkg_invalid_entries)
		if pkg_invalid_entries:
			return (False, pkg_invalid_entries)

		try:
			self._tracking_file.save(failed_pkgs)
		except IOError as ex:
			errors = ['Unable to save failed merges to tracking file: %s\n'
				% str(ex)]
			errors.append(', '.join(sorted(failed_pkgs)))
			return (False, errors)
		self._remove_failed_dirs(failed_pkgs)
		results = self._emerge_pkg_atoms(module_output, pkg_atoms,
			yes=kwargs.get('options', {}).get("yes", False))
		# list any new failed merges
		for pkg in sorted(self._scan()):
			results.append("'%s' still found as a failed merge." % pkg)
		# reload config and remove successful packages from tracking file
		portage._reset_legacy_globals()
		vardb = portage.db[portage.root]['vartree'].dbapi
		still_failed_pkgs = {}
		for pkg, mtime in failed_pkgs.items():
			pkg_name = '%s' % pkg.replace(MERGING_IDENTIFIER, '')
			if not vardb.cpv_exists(pkg_name):
				still_failed_pkgs[pkg] = mtime
		self._tracking_file.save(still_failed_pkgs)
		if still_failed_pkgs:
			return (False, results)
		return (True, results)


	def purge(self, **kwargs):
		"""Attempt to remove previously saved tracking file."""
		if not self._tracking_file.exists():
			return (True, ['Tracking file not found.'])
		self._tracking_file.purge()
		return (True, ['Removed tracking file.'])
