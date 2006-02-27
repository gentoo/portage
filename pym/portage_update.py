
import os, re

from portage_util import write_atomic

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
