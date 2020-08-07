# cvstree.py -- cvs tree utilities
# Copyright 1998-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import re
import stat
import time

from portage import os
from portage import _encodings
from portage import _unicode_encode


# [D]/Name/Version/Date/Flags/Tags

def pathdata(entries, path):
	"""Returns the data(dict) for a specific file/dir at the path specified."""
	mysplit = path.split("/")
	myentries = entries
	mytarget = mysplit[-1]
	mysplit = mysplit[:-1]
	for mys in mysplit:
		if mys in myentries["dirs"]:
			myentries = myentries["dirs"][mys]
		else:
			return None
	if mytarget in myentries["dirs"]:
		return myentries["dirs"][mytarget]
	if mytarget in myentries["files"]:
		return myentries["files"][mytarget]
	return None

def fileat(entries, path):
	return pathdata(entries, path)

def isadded(entries, path):
	"""Returns True if the path exists and is added to the cvs tree."""
	mytarget = pathdata(entries, path)
	if mytarget:
		if "cvs" in mytarget["status"]:
			return 1

	basedir = os.path.dirname(path)
	filename = os.path.basename(path)

	try:
		myfile = io.open(
			_unicode_encode(os.path.join(basedir, 'CVS', 'Entries'),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['content'], errors='strict')
	except IOError:
		return 0
	mylines = myfile.readlines()
	myfile.close()

	rep = re.compile(r"^\/%s\/" % re.escape(filename))
	for x in mylines:
		if rep.search(x):
			return 1

	return 0

def findnew(entries, recursive=0, basedir=""):
	"""Recurses the entries tree to find all elements that have been added but
	have not yet been committed. Returns a list of paths, optionally prepended
	with a basedir.
	"""
	if basedir and basedir[-1] != "/":
		basedir += "/"

	mylist = []
	for myfile in entries["files"]:
		if "cvs" in entries["files"][myfile]["status"]:
			if "0" == entries["files"][myfile]["revision"]:
				mylist.append(basedir + myfile)

	if recursive:
		for mydir in entries["dirs"]:
			mylist += findnew(entries["dirs"][mydir], recursive, basedir + mydir)

	return mylist

def findoption(entries, pattern, recursive=0, basedir=""):
	"""Iterate over paths of cvs entries for which the pattern.search() method
	finds a match. Returns a list of paths, optionally prepended with a
	basedir.
	"""
	if not basedir.endswith("/"):
		basedir += "/"

	for myfile, mydata in entries["files"].items():
		if "cvs" in mydata["status"]:
			if pattern.search(mydata["flags"]):
				yield basedir + myfile

	if recursive:
		for mydir, mydata in entries["dirs"].items():
			for x in findoption(mydata, pattern,
			                    recursive, basedir + mydir):
				yield x

def findchanged(entries, recursive=0, basedir=""):
	"""Recurses the entries tree to find all elements that exist in the cvs tree
	and differ from the committed version. Returns a list of paths, optionally
	prepended with a basedir.
	"""
	if basedir and basedir[-1] != "/":
		basedir += "/"

	mylist = []
	for myfile in entries["files"]:
		if "cvs" in entries["files"][myfile]["status"]:
			if "current" not in entries["files"][myfile]["status"]:
				if "exists" in entries["files"][myfile]["status"]:
					if entries["files"][myfile]["revision"] != "0":
						mylist.append(basedir + myfile)

	if recursive:
		for mydir in entries["dirs"]:
			mylist += findchanged(entries["dirs"][mydir], recursive, basedir + mydir)

	return mylist

def findmissing(entries, recursive=0, basedir=""):
	"""Recurses the entries tree to find all elements that are listed in the cvs
	tree but do not exist on the filesystem. Returns a list of paths,
	optionally prepended with a basedir.
	"""
	if basedir and basedir[-1] != "/":
		basedir += "/"

	mylist = []
	for myfile in entries["files"]:
		if "cvs" in entries["files"][myfile]["status"]:
			if "exists" not in entries["files"][myfile]["status"]:
				if "removed" not in entries["files"][myfile]["status"]:
					mylist.append(basedir + myfile)

	if recursive:
		for mydir in entries["dirs"]:
			mylist += findmissing(entries["dirs"][mydir], recursive, basedir + mydir)

	return mylist

def findunadded(entries, recursive=0, basedir=""):
	"""Recurses the entries tree to find all elements that are in valid cvs
	directories but are not part of the cvs tree. Returns a list of paths,
	optionally prepended with a basedir.
	"""
	if basedir and basedir[-1] != "/":
		basedir += "/"

	# Ignore what cvs ignores.
	mylist = []
	for myfile in entries["files"]:
		if "cvs" not in entries["files"][myfile]["status"]:
			mylist.append(basedir + myfile)

	if recursive:
		for mydir in entries["dirs"]:
			mylist += findunadded(entries["dirs"][mydir], recursive, basedir + mydir)

	return mylist

def findremoved(entries, recursive=0, basedir=""):
	"""Recurses the entries tree to find all elements that are in flagged for cvs
	deletions. Returns a list of paths,	optionally prepended with a basedir.
	"""
	if basedir and basedir[-1] != "/":
		basedir += "/"

	mylist = []
	for myfile in entries["files"]:
		if "removed" in entries["files"][myfile]["status"]:
			mylist.append(basedir + myfile)

	if recursive:
		for mydir in entries["dirs"]:
			mylist += findremoved(entries["dirs"][mydir], recursive, basedir + mydir)

	return mylist

def findall(entries, recursive=0, basedir=""):
	"""Recurses the entries tree to find all new, changed, missing, and unadded
	entities. Returns a 4 element list of lists as returned from each find*().
	"""
	if basedir and basedir[-1] != "/":
		basedir += "/"
	mynew     = findnew(entries, recursive, basedir)
	mychanged = findchanged(entries, recursive, basedir)
	mymissing = findmissing(entries, recursive, basedir)
	myunadded = findunadded(entries, recursive, basedir)
	myremoved = findremoved(entries, recursive, basedir)
	return [mynew, mychanged, mymissing, myunadded, myremoved]

ignore_list = re.compile(r"(^|/)(RCS(|LOG)|SCCS|CVS(|\.adm)|cvslog\..*|tags|TAGS|\.(make\.state|nse_depinfo)|.*~|(\.|)#.*|,.*|_$.*|.*\$|\.del-.*|.*\.(old|BAK|bak|orig|rej|a|olb|o|obj|so|exe|Z|elc|ln)|core)$")
def apply_cvsignore_filter(files):
	x = 0
	while x < len(files):
		if ignore_list.match(files[x].split("/")[-1]):
			files.pop(x)
		else:
			x += 1
	return files

def getentries(mydir, recursive=0):
	"""Scans the given directory and returns a datadict of all the entries in
	the directory separated as a dirs dict and a files dict.
	"""
	myfn = mydir + "/CVS/Entries"
	# entries=[dirs, files]
	entries = {"dirs":{}, "files":{}}
	if not os.path.exists(mydir):
		return entries
	try:
		myfile = io.open(_unicode_encode(myfn,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['content'], errors='strict')
		mylines = myfile.readlines()
		myfile.close()
	except SystemExit as e:
		raise
	except:
		mylines = []

	for line in mylines:
		if line and line[-1] == "\n":
			line = line[:-1]
		if not line:
			continue
		if line == "D": # End of entries file
			break
		mysplit = line.split("/")
		if len(mysplit) != 6:
			print("Confused:", mysplit)
			continue
		if mysplit[0] == "D":
			entries["dirs"][mysplit[1]] = {"dirs":{}, "files":{}, "status":[]}
			entries["dirs"][mysplit[1]]["status"] = ["cvs"]
			if os.path.isdir(mydir+"/"+mysplit[1]):
				entries["dirs"][mysplit[1]]["status"] += ["exists"]
				entries["dirs"][mysplit[1]]["flags"] = mysplit[2:]
				if recursive:
					rentries = getentries(mydir + "/" + mysplit[1], recursive)
					entries["dirs"][mysplit[1]]["dirs"] = rentries["dirs"]
					entries["dirs"][mysplit[1]]["files"] = rentries["files"]
		else:
			# [D]/Name/revision/Date/Flags/Tags
			entries["files"][mysplit[1]] = {}
			entries["files"][mysplit[1]]["revision"] = mysplit[2]
			entries["files"][mysplit[1]]["date"] = mysplit[3]
			entries["files"][mysplit[1]]["flags"] = mysplit[4]
			entries["files"][mysplit[1]]["tags"] = mysplit[5]
			entries["files"][mysplit[1]]["status"] = ["cvs"]
			if entries["files"][mysplit[1]]["revision"][0] == "-":
				entries["files"][mysplit[1]]["status"] += ["removed"]

	for file in os.listdir(mydir):
		if file == "CVS":
			continue
		if os.path.isdir(mydir + "/" + file):
			if file not in entries["dirs"]:
				if ignore_list.match(file) is not None:
					continue
				entries["dirs"][file] = {"dirs":{}, "files":{}}
				# It's normal for a directory to be unlisted in Entries
				# when checked out without -P (see bug #257660).
				rentries = getentries(mydir + "/" + file, recursive)
				entries["dirs"][file]["dirs"] = rentries["dirs"]
				entries["dirs"][file]["files"] = rentries["files"]
			if "status" in entries["dirs"][file]:
				if "exists" not in entries["dirs"][file]["status"]:
					entries["dirs"][file]["status"] += ["exists"]
			else:
				entries["dirs"][file]["status"] = ["exists"]
		elif os.path.isfile(mydir + "/" + file):
			if file not in entries["files"]:
				if ignore_list.match(file) is not None:
					continue
				entries["files"][file] = {"revision":"", "date":"", "flags":"", "tags":""}
			if "status" in entries["files"][file]:
				if "exists" not in entries["files"][file]["status"]:
					entries["files"][file]["status"] += ["exists"]
			else:
				entries["files"][file]["status"] = ["exists"]
			try:
				mystat = os.stat(mydir + "/" + file)
				mytime = time.asctime(time.gmtime(mystat[stat.ST_MTIME]))
				if "status" not in entries["files"][file]:
					entries["files"][file]["status"] = []
				if mytime == entries["files"][file]["date"]:
					entries["files"][file]["status"] += ["current"]
			except SystemExit as e:
				raise
			except Exception as e:
				print("failed to stat", file)
				print(e)
				return

		elif ignore_list.match(file) is not None:
			pass
		else:
			print()
			print("File of unknown type:", mydir + "/" + file)
			print()

	return entries
