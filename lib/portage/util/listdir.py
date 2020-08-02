# Copyright 2010-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['cacheddir', 'listdir']

import errno
import stat


from portage import os
from portage.const import VCS_DIRS
from portage.exception import DirectoryNotFound, PermissionDenied, PortageException
from portage.util import normalize_path

# The global dircache is no longer supported, since it could
# be a memory leak for API consumers. Any cacheddir callers
# should use higher-level caches instead, when necessary.
# TODO: Remove dircache variable after stable portage does
# not use is (keep it for now, in case API consumers clear
# it manually).
dircache = {}

def cacheddir(my_original_path, ignorecvs, ignorelist, EmptyOnError, followSymlinks=True):
	mypath = normalize_path(my_original_path)
	try:
		pathstat = os.stat(mypath)
		if not stat.S_ISDIR(pathstat.st_mode):
			raise DirectoryNotFound(mypath)
	except EnvironmentError as e:
		if e.errno == PermissionDenied.errno:
			raise PermissionDenied(mypath)
		del e
		return [], []
	except PortageException:
		return [], []
	else:
		try:
			fpaths = os.listdir(mypath)
		except EnvironmentError as e:
			if e.errno != errno.EACCES:
				raise
			del e
			raise PermissionDenied(mypath)
		ftype = []
		for x in fpaths:
			try:
				if followSymlinks:
					pathstat = os.stat(mypath+"/"+x)
				else:
					pathstat = os.lstat(mypath+"/"+x)

				if stat.S_ISREG(pathstat[stat.ST_MODE]):
					ftype.append(0)
				elif stat.S_ISDIR(pathstat[stat.ST_MODE]):
					ftype.append(1)
				elif stat.S_ISLNK(pathstat[stat.ST_MODE]):
					ftype.append(2)
				else:
					ftype.append(3)
			except (IOError, OSError):
				ftype.append(3)

	if ignorelist or ignorecvs:
		ret_list = []
		ret_ftype = []
		for file_path, file_type in zip(fpaths, ftype):
			if file_path in ignorelist:
				pass
			elif ignorecvs:
				if file_path[:2] != ".#" and \
					not (file_type == 1 and file_path in VCS_DIRS):
					ret_list.append(file_path)
					ret_ftype.append(file_type)
	else:
		ret_list = fpaths
		ret_ftype = ftype

	return ret_list, ret_ftype

def listdir(mypath, recursive=False, filesonly=False, ignorecvs=False, ignorelist=[], followSymlinks=True,
	EmptyOnError=False, dirsonly=False):
	"""
	Portage-specific implementation of os.listdir

	@param mypath: Path whose contents you wish to list
	@type mypath: String
	@param recursive: Recursively scan directories contained within mypath
	@type recursive: Boolean
	@param filesonly; Only return files, not more directories
	@type filesonly: Boolean
	@param ignorecvs: Ignore VCS directories
	@type ignorecvs: Boolean
	@param ignorelist: List of filenames/directories to exclude
	@type ignorelist: List
	@param followSymlinks: Follow Symlink'd files and directories
	@type followSymlinks: Boolean
	@param EmptyOnError: Return [] if an error occurs (deprecated, always True)
	@type EmptyOnError: Boolean
	@param dirsonly: Only return directories.
	@type dirsonly: Boolean
	@rtype: List
	@return: A list of files and directories (or just files or just directories) or an empty list.
	"""

	fpaths, ftype = cacheddir(mypath, ignorecvs, ignorelist, EmptyOnError, followSymlinks)

	if fpaths is None:
		fpaths = []
	if ftype is None:
		ftype = []

	if not (filesonly or dirsonly or recursive):
		return fpaths

	if recursive:
		stack = list(zip(fpaths, ftype))
		fpaths = []
		ftype = []
		while stack:
			file_path, file_type = stack.pop()
			fpaths.append(file_path)
			ftype.append(file_type)
			if file_type == 1:
				subdir_list, subdir_types = cacheddir(
					os.path.join(mypath, file_path), ignorecvs,
					ignorelist, EmptyOnError, followSymlinks)
				stack.extend((os.path.join(file_path, x), x_type)
					for x, x_type in zip(subdir_list, subdir_types))

	if filesonly:
		fpaths = [x for x, x_type in zip(fpaths, ftype) if x_type == 0]

	elif dirsonly:
		fpaths = [x for x, x_type in zip(fpaths, ftype) if x_type == 1]

	return fpaths
