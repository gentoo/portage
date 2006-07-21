# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

import errno, os, re

from portage_util import write_atomic
from portage_exception import DirectoryNotFound
from portage_dep import isvalidatom, isjustname

ignored_dbentries = ("CONTENTS", "environment.bz2")

def update_dbentry(update_cmd, mycontent):
	if update_cmd[0] == "move":
		old_value, new_value = update_cmd[1], update_cmd[2]
		if mycontent.count(old_value):
			old_value = re.escape(old_value);
			mycontent = re.sub(old_value+"$", new_value, mycontent)
			mycontent = re.sub(old_value+"(\\s)", new_value+"\\1", mycontent)
			mycontent = re.sub(old_value+"(-[^a-zA-Z])", new_value+"\\1", mycontent)
			mycontent = re.sub(old_value+"([^a-zA-Z0-9-])", new_value+"\\1", mycontent)
	return mycontent

def update_dbentries(update_iter, mydata):
	"""Performs update commands and returns a
	dict containing only the updated items."""
	updated_items = {}
	for k, mycontent in mydata.iteritems():
		if k not in ignored_dbentries:
			orig_content = mycontent
			for update_cmd in update_iter:
				mycontent = update_dbentry(update_cmd, mycontent)
			if mycontent is not orig_content:
				updated_items[k] = mycontent
	return updated_items

def fixdbentries(update_iter, dbdir):
	"""Performs update commands which result in search and replace operations
	for each of the files in dbdir (excluding CONTENTS and environment.bz2).
	Returns True when actual modifications are necessary and False otherwise."""
	mydata = {}
	for myfile in [f for f in os.listdir(dbdir) if f not in ignored_dbentries]:
		file_path = os.path.join(dbdir, myfile)
		f = open(file_path, "r")
		mydata[myfile] = f.read()
		f.close()
	updated_items = update_dbentries(update_iter, mydata)
	for myfile, mycontent in updated_items.iteritems():
		file_path = os.path.join(dbdir, myfile)
		write_atomic(file_path, mycontent)
	return len(updated_items) > 0

def grab_updates(updpath, prev_mtimes=None):
	"""Returns all the updates from the given directory as a sorted list of
	tuples, each containing (file_path, statobj, content).  If prev_mtimes is
	given then only updates with differing mtimes are considered."""
	try:
		mylist = os.listdir(updpath)
	except OSError, oe:
		if oe.errno == errno.ENOENT:
			raise DirectoryNotFound(oe)
		else:
			raise oe
	if prev_mtimes is None:
		prev_mtimes = {}
	# validate the file name (filter out CVS directory, etc...)
	mylist = [myfile for myfile in mylist if len(myfile) == 7 and myfile[1:3] == "Q-"]
	if len(mylist) == 0:
		return []
	
	# update names are mangled to make them sort properly
	mylist = [myfile[3:]+"-"+myfile[:2] for myfile in mylist]
	mylist.sort()
	mylist = [myfile[5:]+"-"+myfile[:4] for myfile in mylist]

	update_data = []
	for myfile in mylist:
		file_path = os.path.join(updpath, myfile)
		mystat = os.stat(file_path)
		if file_path not in prev_mtimes or \
		prev_mtimes[file_path] != mystat.st_mtime:
			f = open(file_path)
			content = f.read()
			f.close()
			update_data.append((file_path, mystat, content))
	return update_data

def parse_updates(mycontent):
	"""Valid updates are returned as a list of split update commands."""
	myupd = []
	errors = []
	mylines = mycontent.splitlines()
	for myline in mylines:
		mysplit = myline.split()
		if len(mysplit) == 0:
			continue
		if mysplit[0] not in ("move", "slotmove"):
			errors.append("ERROR: Update type not recognized '%s'" % myline)
			continue
		if mysplit[0] == "move":
			if len(mysplit) != 3:
				errors.append("ERROR: Update command invalid '%s'" % myline)
				continue
			orig_value, new_value = mysplit[1], mysplit[2]
			for cp in (orig_value, new_value):
				if not (isvalidatom(cp) and isjustname(cp)):
					errors.append(
						"ERROR: Malformed update entry '%s'" % myline)
					continue
		if mysplit[0] == "slotmove":
			if len(mysplit)!=4:
				errors.append("ERROR: Update command invalid '%s'" % myline)
				continue
			pkg, origslot, newslot = mysplit[1], mysplit[2], mysplit[3]
			if not isvalidatom(pkg):
				errors.append("ERROR: Malformed update entry '%s'" % myline)
				continue
		
		# The list of valid updates is filtered by continue statements above.
		myupd.append(mysplit)
	return myupd, errors
