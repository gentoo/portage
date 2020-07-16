# -*- coding:utf-8 -*-

from __future__ import print_function

import collections
import logging
from itertools import chain

from portage import os


_vcs_type = collections.namedtuple('_vcs_type', 'name dir_name file_name')

_FindVCS_data = (
	_vcs_type(
		name='git',
		dir_name='.git',
		file_name='.git'
	),
	_vcs_type(
		name='bzr',
		dir_name='.bzr',
		file_name=''
	),
	_vcs_type(
		name='hg',
		dir_name='.hg',
		file_name=''
	),
	_vcs_type(
		name='svn',
		dir_name='.svn',
		file_name=''
	)
)


def FindVCS(cwd=None):
	"""
	Try to figure out in what VCS' working tree we are.

	@param cwd: working directory (default is os.getcwd())
	@type cwd: str
	@return: list of strings describing the discovered vcs types
	@rtype: list
	"""

	if cwd is None:
		cwd = os.getcwd()

	outvcs = []

	def seek(depth=None):
		'''Seek for VCSes that have a top-level data directory only.

		@param depth: integer
		@returns: list of strings
		'''
		retvcs = []
		pathprep = cwd

		while depth is None or depth > 0:
			for vcs_type in _FindVCS_data:
				vcs_dir = os.path.join(pathprep, vcs_type.dir_name)
				if os.path.isdir(vcs_dir):
					logging.debug(
						'FindVCS: found %(name)s dir: %(vcs_dir)s' % {
							'name': vcs_type.name,
							'vcs_dir': os.path.abspath(vcs_dir)})
					retvcs.append(vcs_type.name)
				elif vcs_type.file_name:
					vcs_file = os.path.join(pathprep, vcs_type.file_name)
					if os.path.exists(vcs_file):
						logging.debug(
							'FindVCS: found %(name)s file: %(vcs_file)s' % {
								'name': vcs_type.name,
								'vcs_file': os.path.abspath(vcs_file)})
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
	if os.path.isdir(os.path.join(cwd, 'CVS')):
		outvcs.append('cvs')
	if os.path.isdir('.svn'):  # <1.7
		outvcs.append(os.path.join(cwd, 'svn'))

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


def vcs_files_to_cps(vcs_file_iter, repodir, repolevel, reposplit, categories):
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

	# Exclude packages that have been removed, since calling
	# code assumes that the packages exist.
	return frozenset(x for x in frozenset(modified_cps)
		if os.path.exists(os.path.join(repodir, x)))


def vcs_new_changed(relative_path, mychanged, mynew):
	'''Check if any vcs tracked file have been modified

	@param relative_path:
	@param mychanged: iterable of changed files
	@param mynew: iterable of new files
	@returns boolean
	'''
	for x in chain(mychanged, mynew):
		if x == relative_path:
			return True
	return False


