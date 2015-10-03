# -*- coding:utf-8 -*-

from __future__ import print_function, unicode_literals

import collections
import logging
import re
import subprocess
import sys
from itertools import chain

from portage import os
from portage.const import BASH_BINARY
from portage.output import red, green
from portage import _unicode_encode, _unicode_decode

from repoman._subprocess import repoman_getstatusoutput


_vcs_type = collections.namedtuple('_vcs_type', 'name dir_name')

_FindVCS_data = (
	_vcs_type(
		name='git',
		dir_name='.git'
	),
	_vcs_type(
		name='bzr',
		dir_name='.bzr'
	),
	_vcs_type(
		name='hg',
		dir_name='.hg'
	),
	_vcs_type(
		name='svn',
		dir_name='.svn'
	)
)


def FindVCS():
	""" Try to figure out in what VCS' working tree we are. """

	outvcs = []

	def seek(depth=None):
		""" Seek for VCSes that have a top-level data directory only. """
		retvcs = []
		pathprep = ''

		while depth is None or depth > 0:
			for vcs_type in _FindVCS_data:
				vcs_dir = os.path.join(pathprep, vcs_type.dir_name)
				if os.path.isdir(vcs_dir):
					logging.debug(
						'FindVCS: found %(name)s dir: %(vcs_dir)s' % {
							'name': vcs_type.name,
							'vcs_dir': os.path.abspath(vcs_dir)})
					retvcs.append(vcs_type.name)

			if retvcs:
				break
			pathprep = os.path.join(pathprep, '..')
			if os.path.realpath(pathprep).strip('/') == '':
				break
			if depth is not None:
				depth = depth - 1

		return retvcs

	# Level zero VCS-es.
	if os.path.isdir('CVS'):
		outvcs.append('cvs')
	if os.path.isdir('.svn'):  # <1.7
		outvcs.append('svn')

	# If we already found one of 'level zeros', just take a quick look
	# at the current directory. Otherwise, seek parents till we get
	# something or reach root.
	if outvcs:
		outvcs.extend(seek(1))
	else:
		outvcs = seek()

	if len(outvcs) > 1:
		# eliminate duplicates, like for svn in bug #391199
		outvcs = list(set(outvcs))

	return outvcs


def vcs_files_to_cps(vcs_file_iter, repolevel, reposplit, categories):
	"""
	Iterate over the given modified file paths returned from the vcs,
	and return a frozenset containing category/pn strings for each
	modified package.
	"""

	modified_cps = []

	if repolevel == 3:
		if reposplit[-2] in categories and \
			next(vcs_file_iter, None) is not None:
			modified_cps.append("/".join(reposplit[-2:]))

	elif repolevel == 2:
		category = reposplit[-1]
		if category in categories:
			for filename in vcs_file_iter:
				f_split = filename.split(os.sep)
				# ['.', pn, ...]
				if len(f_split) > 2:
					modified_cps.append(category + "/" + f_split[1])

	else:
		# repolevel == 1
		for filename in vcs_file_iter:
			f_split = filename.split(os.sep)
			# ['.', category, pn, ...]
			if len(f_split) > 3 and f_split[1] in categories:
				modified_cps.append("/".join(f_split[1:3]))

	return frozenset(modified_cps)


def vcs_new_changed(relative_path, mychanged, mynew):
	for x in chain(mychanged, mynew):
		if x == relative_path:
			return True
	return False


def git_supports_gpg_sign():
	status, cmd_output = \
		repoman_getstatusoutput("git --version")
	cmd_output = cmd_output.split()
	if cmd_output:
		version = re.match(r'^(\d+)\.(\d+)\.(\d+)', cmd_output[-1])
		if version is not None:
			version = [int(x) for x in version.groups()]
			if version[0] > 1 or \
				(version[0] == 1 and version[1] > 7) or \
				(version[0] == 1 and version[1] == 7 and version[2] >= 9):
				return True
	return False


def detect_vcs_conflicts(options, vcs):
	"""Determine if the checkout has problems like cvs conflicts.

	If you want more vcs support here just keep adding if blocks...
	This could be better.

	TODO(antarus): Also this should probably not call sys.exit() as
	repoman is run on >1 packages and one failure should not cause
	subsequent packages to fail.

	Args:
		vcs - A string identifying the version control system in use
	Returns:
		None (calls sys.exit on fatal problems)
	"""

	cmd = None
	if vcs == 'cvs':
		logging.info(
			"Performing a %s with a little magic grep to check for updates." %
			green("cvs -n up"))
		cmd = (
			"cvs -n up 2>/dev/null | "
			"egrep '^[^\?] .*' | "
			"egrep -v '^. .*/digest-[^/]+|^cvs server: .* -- ignored$'")
	if vcs == 'svn':
		logging.info(
			"Performing a %s with a little magic grep to check for updates." %
			green("svn status -u"))
		cmd = (
			"svn status -u 2>&1 | "
			"egrep -v '^.  +.*/digest-[^/]+' | "
			"head -n-1")

	if cmd is not None:
		# Use Popen instead of getstatusoutput(), in order to avoid
		# unicode handling problems (see bug #310789).
		args = [BASH_BINARY, "-c", cmd]
		args = [_unicode_encode(x) for x in args]
		proc = subprocess.Popen(
			args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		out = _unicode_decode(proc.communicate()[0])
		proc.wait()
		mylines = out.splitlines()
		myupdates = []
		for line in mylines:
			if not line:
				continue

			# [ ] Unmodified (SVN)	[U] Updates		[P] Patches
			# [M] Modified			[A] Added		[R] Removed / Replaced
			# [D] Deleted
			if line[0] not in " UPMARD":
				# Stray Manifest is fine, we will readd it anyway.
				if line[0] == '?' and line[1:].lstrip() == 'Manifest':
					continue
				logging.error(red(
					"!!! Please fix the following issues reported "
					"from cvs: %s" % green("(U,P,M,A,R,D are ok)")))
				logging.error(red(
					"!!! Note: This is a pretend/no-modify pass..."))
				logging.error(out)
				sys.exit(1)
			elif vcs == 'cvs' and line[0] in "UP":
				myupdates.append(line[2:])
			elif vcs == 'svn' and line[8] == '*':
				myupdates.append(line[9:].lstrip(" 1234567890"))

		if myupdates:
			logging.info(green("Fetching trivial updates..."))
			if options.pretend:
				logging.info("(" + vcs + " update " + " ".join(myupdates) + ")")
				retval = os.EX_OK
			else:
				retval = os.system(vcs + " update " + " ".join(myupdates))
			if retval != os.EX_OK:
				logging.fatal("!!! " + vcs + " exited with an error. Terminating.")
				sys.exit(retval)


class VCSSettings(object):
	'''Holds various VCS settings'''

	def __init__(self, options=None, repoman_settings=None):
		if options.vcs:
			if options.vcs in ('cvs', 'svn', 'git', 'bzr', 'hg'):
				self.vcs = options.vcs
			else:
				self.vcs = None
		else:
			vcses = FindVCS()
			if len(vcses) > 1:
				print(red(
					'*** Ambiguous workdir -- more than one VCS found'
					' at the same depth: %s.' % ', '.join(vcses)))
				print(red(
					'*** Please either clean up your workdir'
					' or specify --vcs option.'))
				sys.exit(1)
			elif vcses:
				self.vcs = vcses[0]
			else:
				self.vcs = None

		if options.if_modified == "y" and self.vcs is None:
			logging.info(
				"Not in a version controlled repository; "
				"disabling --if-modified.")
			options.if_modified = "n"

		# Disable copyright/mtime check if vcs does not preserve mtime (bug #324075).
		self.vcs_preserves_mtime = self.vcs in ('cvs',)

		self.vcs_local_opts = repoman_settings.get(
			"REPOMAN_VCS_LOCAL_OPTS", "").split()
		self.vcs_global_opts = repoman_settings.get(
			"REPOMAN_VCS_GLOBAL_OPTS")
		if self.vcs_global_opts is None:
			if self.vcs in ('cvs', 'svn'):
				self.vcs_global_opts = "-q"
			else:
				self.vcs_global_opts = ""
		self.vcs_global_opts = self.vcs_global_opts.split()

		if options.mode == 'commit' and not options.pretend and not self.vcs:
			logging.info(
				"Not in a version controlled repository; "
				"enabling pretend mode.")
			options.pretend = True
