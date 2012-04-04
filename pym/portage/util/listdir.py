# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['cacheddir', 'listdir']

import errno
import stat
import time

from portage import os
from portage.exception import DirectoryNotFound, PermissionDenied, PortageException
from portage.util import normalize_path, writemsg

_ignorecvs_dirs = ('CVS', 'RCS', 'SCCS', '.svn', '.git')
dircache = {}
cacheHit = 0
cacheMiss = 0
cacheStale = 0

def cacheddir(my_original_path, ignorecvs, ignorelist, EmptyOnError, followSymlinks=True):
	global cacheHit,cacheMiss,cacheStale
	mypath = normalize_path(my_original_path)
	if mypath in dircache:
		cacheHit += 1
		cached_mtime, list, ftype = dircache[mypath]
	else:
		cacheMiss += 1
		cached_mtime, list, ftype = -1, [], []
	try:
		pathstat = os.stat(mypath)
		if stat.S_ISDIR(pathstat[stat.ST_MODE]):
			mtime = pathstat.st_mtime
		else:
			raise DirectoryNotFound(mypath)
	except EnvironmentError as e:
		if e.errno == PermissionDenied.errno:
			raise PermissionDenied(mypath)
		del e
		return [], []
	except PortageException:
		return [], []
	# Python retuns mtime in seconds, so if it was changed in the last few seconds, it could be invalid
	if mtime != cached_mtime or time.time() - mtime < 4:
		if mypath in dircache:
			cacheStale += 1
		try:
			list = os.listdir(mypath)
		except EnvironmentError as e:
			if e.errno != errno.EACCES:
				raise
			del e
			raise PermissionDenied(mypath)
		ftype = []
		for x in list:
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
		dircache[mypath] = mtime, list, ftype

	ret_list = []
	ret_ftype = []
	for x in range(0, len(list)):
		if list[x] in ignorelist:
			pass
		elif ignorecvs:
			if list[x][:2] != ".#" and \
				not (ftype[x] == 1 and list[x] in _ignorecvs_dirs):
				ret_list.append(list[x])
				ret_ftype.append(ftype[x])
		else:
			ret_list.append(list[x])
			ret_ftype.append(ftype[x])

	writemsg("cacheddirStats: H:%d/M:%d/S:%d\n" % (cacheHit, cacheMiss, cacheStale),10)
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
	@param ignorecvs: Ignore CVS directories ('CVS','SCCS','.svn','.git')
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

	list, ftype = cacheddir(mypath, ignorecvs, ignorelist, EmptyOnError, followSymlinks)

	if list is None:
		list=[]
	if ftype is None:
		ftype=[]

	if not (filesonly or dirsonly or recursive):
		return list

	if recursive:
		x=0
		while x<len(ftype):
			if ftype[x] == 1:
				l,f = cacheddir(mypath+"/"+list[x], ignorecvs, ignorelist, EmptyOnError,
					followSymlinks)

				l=l[:]
				for y in range(0,len(l)):
					l[y]=list[x]+"/"+l[y]
				list=list+l
				ftype=ftype+f
			x+=1
	if filesonly:
		rlist=[]
		for x in range(0,len(ftype)):
			if ftype[x]==0:
				rlist=rlist+[list[x]]
	elif dirsonly:
		rlist = []
		for x in range(0, len(ftype)):
			if ftype[x] == 1:
				rlist = rlist + [list[x]]	
	else:
		rlist=list

	return rlist
