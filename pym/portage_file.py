# portage_data.py -- Calculated/Discovered Data Values
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/portage_file.py,v 1.3.2.1 2005/01/16 02:35:33 carpaski Exp $


import os
import portage_data
import portage_exception
from portage_localization import _

def normpath(mypath):
	newpath = os.path.normpath(mypath)
	if len(newpath) > 1:
		if newpath[:2] == "//":
			newpath = newpath[1:]
	return newpath
								

def makedirs(path, perms=0755, uid=None, gid=None, must_chown=False):
	old_umask = os.umask(0)
	if(uid == None):
		uid = portage_data.portage_uid
	if(gid == None):
		gid = portage_data.portage_gid
	if not path:
		raise portage_exception.InvalidParameter, _("Invalid path: type: '%(type)s' value: '%(path)s'") % {"path": path, "type": type(path)}
	if(perm > 1535) or (perm == 0):
		raise portage_exception.InvalidParameter, _("Invalid permissions passed. Value is octal and no higher than 02777.")

	mypath = normpath(path)
	dirs = string.split(path, "/")
	
	mypath = ""
	if dirs and dirs[0] == "":
		mypath = "/"
		dirs = dirs[1:]
	for x in dirs:
		mypath += x+"/"
		if not os.path.exists(mypath):
			os.mkdir(mypath, perm)
			try:
				os.chown(mypath, uid, gid)
			except SystemExit, e:
				raise
			except:
				if must_chown:
					os.umask(old_umask)
					raise
				portage_util.writemsg(_("Failed to chown: %(path)s to %(uid)s:%(gid)s\n") % {"path":mypath,"uid":uid,"gid":gid})

	os.umask(old_umask)
	
	
	
	
	
	
	
	
	
	
