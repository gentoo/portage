# portage_contents.py -- (Persistent) Contents File Management
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: /var/cvsroot/gentoo-src/portage/pym/portage_contents.py,v 1.3.2.1 2005/01/16 02:35:33 carpaski Exp $
cvs_id_string="$Id: portage_contents.py,v 1.3.2.1 2005/01/16 02:35:33 carpaski Exp $"[5:-2]

import os,string,types,sys,copy
import portage_exception
import portage_const

#import gettext
#gettext_t = gettext.translation('portage.contents', portage_const.LOCALE_DATA_PATH)
#_ = gettext_t.ugettext
def _(mystr):
	return mystr


FILES_KEY = "\0FILES\0"
OWNER_KEY = "\0OWNER\0"


def ContentsHandler(filename):
	infile = open(filename)
	myfiles = []
	mydirs  = []
	
	mylines = infile.readlines()
	infile.close()
	for line in mylines:
		if line[-1] == '\n':
			line   = line[:-1]
		parts  = string.split(line)

		mytype   = parts[0]
		mytarget = None

		if   mytype in ["dir","dev","fif"]:
			mypath = string.join(parts[1:])
		elif mytype == "obj":
			mypath = string.join(parts[1:-2])
		elif mytype == "sym":
			sl = string.join(parts[1:-1])
			sl = string.split(sl, " -> ")

			mypath   = sl[0]
			mytarget = sl[1]
		else:
			print _("Unknown type:"),mytype
		
		if mytype in ["dir"]:
			mydirs.append(mypath)
		else:
			myfiles.append(mypath)
	
	mydirs.sort()
	myfiles.sort()
	return myfiles,mydirs

class PathLookupTable:
	"""Creates a temporary lookup table for paths from files."""
	def __init__(self,dbname):
		#if not self.validLocation(dbname):
		#	raise portage_exception.InvalidLocation, dbname
		#self.base = copy.deepcopy(dbname)
		
		self.files = []
		self.pathtree = {}
	
	def addFromFile(self, filename, handler):
		if type(handler) != types.FunctionType:
			raise portage_exception.IncorrectParameter, _("Handler of type '%(type)s' not 'function'") % {"type": type(handler)}
	
		filelist,dirlist = handler(filename)
		filestat = os.stat(filename)

		if type(filelist) != types.ListType:
			raise portage_exception.InvalidDataType, _("%(handler)s returned an invalid file list") % {"handler": handler.__name__}
		if type(dirlist) != types.ListType:
			raise portage_exception.InvalidDataType, _("%(handler)s returned an invalid directory list") % {"handler": handler.__name__}

		for x in filelist:
			if not x:
				continue
			x = os.path.normpath(x)
			if len(x) > 1:
				if x[:2] == "//":
					x = x[1:]
			if type(x) != types.StringType:
				raise portage_exception.InvalidDataType, _("%(handler)s returned an invalid subelement in dataset") % {"handler": handler.__name__}
			xs = string.split(x, "/")
			self.addFilePath(xs,filename)
			
		for x in dirlist:
			if not x:
				continue
			x = os.path.normpath(x)
			if len(x) > 1:
				if x[:2] == "//":
					x = x[1:]
			if type(x) != types.StringType:
				raise portage_exception.InvalidDataType, _("%(handler)s returned an invalid subelement in dataset") % {"handler": handler.__name__}
			xs = string.split(x, "/")
			self.addDirectoryPath(xs,filename)
			
	def addDirectoryPath(self,split_path, owner):
		pt = self.pathtree
		for x in split_path:
			if x not in pt.keys():
				pt[x] = {FILES_KEY:{},OWNER_KEY:[]}
			if owner not in pt[x][OWNER_KEY]:
				pt[x][OWNER_KEY].append(owner[:])
			pt = pt[x]
		return pt

	def addFilePath(self,split_path, owner):
		pt = self.addDirectoryPath(split_path[:-1], owner)
		if split_path[-1] not in pt[FILES_KEY]:
			pt[FILES_KEY][split_path[-1][:]] = []
		if owner not in pt[FILES_KEY][split_path[-1][:]]:
			pt[FILES_KEY][split_path[-1][:]].append(owner[:])
		
	def whoProvides(self,path):
		if type(path) != types.StringType:
			raise portage_exception.InvalidData, _("Path passed is not a string: %(path)s") % {"path": path}
		x = os.path.normpath(path)
		if x[0:2] == '//':
			x = x[1:]
		
		xs = x.split("/")
		pt = self.pathtree
		final_dir = xs.pop(-1)
		for subpath in xs:
			if subpath in pt.keys():
				pt = pt[subpath]

		owners = []
		if final_dir in pt[FILES_KEY]:
			for x in pt[FILES_KEY][final_dir]:
				if x not in owners:
					owners.append(x[:])
		if final_dir in pt:
			for x in pt[final_dir][OWNER_KEY]:
				if x not in owners:
					owners.append(x[:])

		return owners



def test():
	import os
	plt = PathLookupTable("spork")
	for x in os.listdir("/var/db/pkg"):
		for y in os.listdir("/var/db/pkg/"+x):
			c_path = "/var/db/pkg/"+x+"/"+y+"/CONTENTS"
			if os.path.exists(c_path):
				plt.addFromFile(c_path, ContentsHandler)
	print "/bin/bash:",    plt.whoProvides("/bin/bash")
	print "/var/spool:",   plt.whoProvides("/var/spool")
	print "/etc/init.d",   plt.whoProvides("/etc/init.d")
	return plt
