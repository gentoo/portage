# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

import errno, os, re, sys

from portage_util import ConfigProtect, grabfile, new_protect_filename, \
	normalize_path, write_atomic, writemsg
from portage_exception import DirectoryNotFound, PortageException
from portage_dep import dep_getkey, isvalidatom, isjustname
from portage_const import USER_CONFIG_PATH, WORLD_FILE

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
		long(prev_mtimes[file_path]) != long(mystat.st_mtime):
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

def update_config_files(config_root, protect, protect_mask, update_iter):
	"""Perform global updates on /etc/portage/package.* and the world file.
	config_root - location of files to update
	protect - list of paths from CONFIG_PROTECT
	protect_mask - list of paths from CONFIG_PROTECT_MASK
	update_iter - list of update commands as returned from parse_updates()"""
	config_root = normalize_path(config_root)
	update_files = {}
	file_contents = {}
	myxfiles = ["package.mask", "package.unmask", \
		"package.keywords", "package.use"]
	myxfiles += [os.path.join("profile", x) for x in myxfiles]
	abs_user_config = os.path.join(config_root,
		USER_CONFIG_PATH.lstrip(os.path.sep))
	recursivefiles = []
	for x in myxfiles:
		config_file = os.path.join(abs_user_config, x)
		if os.path.isdir(config_file):
			for parent, dirs, files in os.walk(config_file):
				for y in dirs:
					if y.startswith("."):
						dirs.remove(y)
				for y in files:
					if y.startswith("."):
						continue
					recursivefiles.append(
						os.path.join(parent, y)[len(abs_user_config) + 1:])
		else:
			recursivefiles.append(x)
	myxfiles = recursivefiles
	for x in myxfiles:
		try:
			myfile = open(os.path.join(abs_user_config, x),"r")
			file_contents[x] = myfile.readlines()
			myfile.close()
		except IOError:
			if file_contents.has_key(x):
				del file_contents[x]
			continue
	worldlist = grabfile(os.path.join(config_root, WORLD_FILE))

	for update_cmd in update_iter:
		if update_cmd[0] == "move":
			old_value, new_value = update_cmd[1], update_cmd[2]
			#update world entries:
			for x in range(0,len(worldlist)):
				#update world entries, if any.
				worldlist[x] = \
					dep_transform(worldlist[x], old_value, new_value)

			#update /etc/portage/packages.*
			for x in file_contents:
				for mypos in range(0,len(file_contents[x])):
					line = file_contents[x][mypos]
					if line[0] == "#" or not line.strip():
						continue
					key = dep_getkey(line.split()[0])
					if key == old_value:
						file_contents[x][mypos] = \
							line.replace(old_value, new_value)
						update_files[x] = 1
						sys.stdout.write("p")
						sys.stdout.flush()

	write_atomic(os.path.join(config_root, WORLD_FILE), "\n".join(worldlist))

	protect_obj = ConfigProtect(
		config_root, protect, protect_mask)
	for x in update_files:
		updating_file = os.path.join(abs_user_config, x)
		if protect_obj.isprotected(updating_file):
			updating_file = new_protect_filename(updating_file)
		try:
			write_atomic(updating_file, "".join(file_contents[x]))
		except PortageException, e:
			writemsg("\n!!! %s\n" % str(e), noiselevel=-1)
			writemsg("!!! An error occured while updating a config file:" + \
				" '%s'\n" % updating_file, noiselevel=-1)
			continue

def dep_transform(mydep, oldkey, newkey):
	return mydep.replace(oldkey, newkey, 1)
