# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/portage_util.py,v 1.11.2.6 2005/04/23 07:26:04 jstubbs Exp $

from portage_exception import PortageException, FileNotFound, OperationNotPermitted, ReadOnlyFileSystem

import sys,string,shlex,os,errno
try:
	import cPickle
except ImportError:
	import pickle as cPickle

if not hasattr(__builtins__, "set"):
	from sets import Set as set

noiselimit = 0

def writemsg(mystr,noiselevel=0,fd=None):
	"""Prints out warning and debug messages based on the noiselimit setting"""
	global noiselimit
	if fd is None:
		fd = sys.stderr
	if noiselevel <= noiselimit:
		fd.write(mystr)
		fd.flush()

def writemsg_stdout(mystr,noiselevel=0):
	"""Prints messages stdout based on the noiselimit setting"""
	writemsg(mystr, noiselevel=noiselevel, fd=sys.stdout)

def grabfile(myfilename, compat_level=0, recursive=0):
	"""This function grabs the lines in a file, normalizes whitespace and returns lines in a list; if a line
	begins with a #, it is ignored, as are empty lines"""

	mylines=grablines(myfilename, recursive)
	newlines=[]
	for x in mylines:
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		myline=string.join(string.split(x))
		if not len(myline):
			continue
		if myline[0]=="#":
			# Check if we have a compat-level string. BC-integration data.
			# '##COMPAT==>N<==' 'some string attached to it'
			mylinetest = string.split(myline, "<==", 1)
			if len(mylinetest) == 2:
				myline_potential = mylinetest[1]
				mylinetest = string.split(mylinetest[0],"##COMPAT==>")
				if len(mylinetest) == 2:
					if compat_level >= int(mylinetest[1]):
						# It's a compat line, and the key matches.
						newlines.append(myline_potential)
				continue
			else:
				continue
		newlines.append(myline)
	return newlines

def map_dictlist_vals(func,myDict):
	"""Performs a function on each value of each key in a dictlist.
	Returns a new dictlist."""
	new_dl = {}
	for key in myDict.keys():
		new_dl[key] = []
		new_dl[key] = map(func,myDict[key])
	return new_dl

def stack_dictlist(original_dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->list.
	Returns a single dict. Higher index in lists is preferenced."""
	final_dict = None
	kill_list = {}
	for mydict in original_dicts:
		if mydict is None:
			continue
		if final_dict is None:
			final_dict = {}
		for y in mydict.keys():
			if not final_dict.has_key(y):
				final_dict[y] = []
			if not kill_list.has_key(y):
				kill_list[y] = []
			
			mydict[y].reverse()
			for thing in mydict[y]:
				if thing and (thing not in kill_list[y]) and ("*" not in kill_list[y]):
					if (incremental or (y in incrementals)) and thing[0] == '-':
						if thing[1:] not in kill_list[y]:
							kill_list[y] += [thing[1:]]
					else:
						if thing not in final_dict[y]:
							final_dict[y].append(thing[:])
			mydict[y].reverse()
			if final_dict.has_key(y) and not final_dict[y]:
				del final_dict[y]
	return final_dict

def stack_dicts(dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->string.
	Returns a single dict."""
	final_dict = None
	for mydict in dicts:
		if mydict is None:
			if ignore_none:
				continue
			else:
				return None
		if final_dict is None:
			final_dict = {}
		for y in mydict.keys():
			if mydict[y]:
				if final_dict.has_key(y) and (incremental or (y in incrementals)):
					final_dict[y] += " "+mydict[y][:]
				else:
					final_dict[y]  = mydict[y][:]
			mydict[y] = string.join(mydict[y].split()) # Remove extra spaces.
	return final_dict

def stack_lists(lists, incremental=1):
	"""Stacks an array of list-types into one array. Optionally removing
	distinct values using '-value' notation. Higher index is preferenced.

	all elements must be hashable."""

	new_list = {}
	for x in lists:
		for y in filter(None, x):
			if incremental and y.startswith("-"):
				if y[1:] in new_list:
					del new_list[y[1:]]
			else:
				new_list[y] = True
	return new_list.keys()

def grabdict(myfilename, juststrings=0, empty=0, recursive=0):
	"""This function grabs the lines in a file, normalizes whitespace and returns lines in a dictionary"""
	newdict={}
	for x in grablines(myfilename, recursive):
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		if x[0] == "#":
			continue
		myline=string.split(x)
		if len(myline) < 2 and empty == 0:
			continue
		if len(myline) < 1 and empty == 1:
			continue
		if juststrings:
			newdict[myline[0]]=string.join(myline[1:])
		else:
			newdict[myline[0]]=myline[1:]
	return newdict

def grabdict_package(myfilename, juststrings=0, recursive=0):
	pkgs=grabdict(myfilename, juststrings, empty=1, recursive=recursive)
	for x in pkgs:
		if not isvalidatom(x):
			del(pkgs[x])
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, x))
	return pkgs

def grabfile_package(myfilename, compatlevel=0, recursive=0):
	pkgs=grabfile(myfilename, compatlevel, recursive=recursive)
	for x in range(len(pkgs)-1, -1, -1):
		pkg = pkgs[x]
		if pkg[0] == "-":
			pkg = pkg[1:]
		if pkg[0] == "*": # Kill this so we can deal the "packages" file too
			pkg = pkg[1:]
		if not isvalidatom(pkg):
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, pkgs[x]))
			del(pkgs[x])
	return pkgs

def grablines(myfilename,recursive=0):
	mylines=[]
	if recursive and os.path.isdir(myfilename):
		myfiles = [myfilename+os.path.sep+x for x in os.listdir(myfilename)]
		myfiles.sort()
		for f in myfiles:
			mylines.extend(grablines(f, recursive))
	else:
		try:
			myfile = open(myfilename, "r")
			mylines = myfile.readlines()
			myfile.close()
		except IOError:
			pass
	return mylines

def writedict(mydict,myfilename,writekey=True):
	"""Writes out a dict to a file; writekey=0 mode doesn't write out
	the key and assumes all values are strings, not lists."""
	myfile = None
	try:
		myfile = atomic_ofstream(myfilename)
		if not writekey:
			for x in mydict.values():
				myfile.write(x+"\n")
		else:
			for x in mydict.keys():
				myfile.write("%s %s\n" % (x, " ".join(mydict[x])))
		myfile.close()
	except IOError:
		if myfile is not None:
			myfile.abort()
		return 0
	return 1

def getconfig(mycfg,tolerant=0,allow_sourcing=False):
	mykeys={}
	try:
		f=open(mycfg,'r')
	except IOError:
		return None
	try:
		lex=shlex.shlex(f)
		lex.wordchars=string.digits+string.letters+"~!@#$%*_\:;?,./-+{}"     
		lex.quotes="\"'"
		if allow_sourcing:
			lex.source="source"
		while 1:
			key=lex.get_token()
			if (key==''):
				#normal end of file
				break;
			equ=lex.get_token()
			if (equ==''):
				#unexpected end of file
				#lex.error_leader(self.filename,lex.lineno)
				if not tolerant:
					writemsg("!!! Unexpected end of config file: variable "+str(key)+"\n")
					raise Exception("ParseError: Unexpected EOF: "+str(mycfg)+": on/before line "+str(lex.lineno))
				else:
					return mykeys
			elif (equ!='='):
				#invalid token
				#lex.error_leader(self.filename,lex.lineno)
				if not tolerant:
					writemsg("!!! Invalid token (not \"=\") "+str(equ)+"\n")
					raise Exception("ParseError: Invalid token (not '='): "+str(mycfg)+": line "+str(lex.lineno))
				else:
					return mykeys
			val=lex.get_token()
			if (val==''):
				#unexpected end of file
				#lex.error_leader(self.filename,lex.lineno)
				if not tolerant:
					writemsg("!!! Unexpected end of config file: variable "+str(key)+"\n")
					raise portage_exception.CorruptionError("ParseError: Unexpected EOF: "+str(mycfg)+": line "+str(lex.lineno))
				else:
					return mykeys
			mykeys[key]=varexpand(val,mykeys)
	except SystemExit, e:
		raise
	except Exception, e:
		raise e.__class__, str(e)+" in "+mycfg
	return mykeys
	
#cache expansions of constant strings
cexpand={}
def varexpand(mystring,mydict={}):
	try:
		return cexpand[" "+mystring]
	except KeyError:
		pass
	"""
	new variable expansion code.  Removes quotes, handles \n, etc.
	This code is used by the configfile code, as well as others (parser)
	This would be a good bunch of code to port to C.
	"""
	numvars=0
	mystring=" "+mystring
	#in single, double quotes
	insing=0
	indoub=0
	pos=1
	newstring=" "
	while (pos<len(mystring)):
		if (mystring[pos]=="'") and (mystring[pos-1]!="\\"):
			if (indoub):
				newstring=newstring+"'"
			else:
				insing=not insing
			pos=pos+1
			continue
		elif (mystring[pos]=='"') and (mystring[pos-1]!="\\"):
			if (insing):
				newstring=newstring+'"'
			else:
				indoub=not indoub
			pos=pos+1
			continue
		if (not insing): 
			#expansion time
			if (mystring[pos]=="\n"):
				#convert newlines to spaces
				newstring=newstring+" "
				pos=pos+1
			elif (mystring[pos]=="\\"):
				#backslash expansion time
				if (pos+1>=len(mystring)):
					newstring=newstring+mystring[pos]
					break
				else:
					a=mystring[pos+1]
					pos=pos+2
					if a=='a':
						newstring=newstring+chr(007)
					elif a=='b':
						newstring=newstring+chr(010)
					elif a=='e':
						newstring=newstring+chr(033)
					elif (a=='f') or (a=='n'):
						newstring=newstring+chr(012)
					elif a=='r':
						newstring=newstring+chr(015)
					elif a=='t':
						newstring=newstring+chr(011)
					elif a=='v':
						newstring=newstring+chr(013)
					elif a!='\n':
						#remove backslash only, as bash does: this takes care of \\ and \' and \" as well
						newstring=newstring+mystring[pos-1:pos]
						continue
			elif (mystring[pos]=="$") and (mystring[pos-1]!="\\"):
				pos=pos+1
				if mystring[pos]=="{":
					pos=pos+1
					braced=True
				else:
					braced=False
				myvstart=pos
				validchars=string.ascii_letters+string.digits+"_"
				while mystring[pos] in validchars:
					if (pos+1)>=len(mystring):
						if braced:
							cexpand[mystring]=""
							return ""
						else:
							pos=pos+1
							break
					pos=pos+1
				myvarname=mystring[myvstart:pos]
				if braced:
					if mystring[pos]!="}":
						cexpand[mystring]=""
						return ""
					else:
						pos=pos+1
				if len(myvarname)==0:
					cexpand[mystring]=""
					return ""
				numvars=numvars+1
				if mydict.has_key(myvarname):
					newstring=newstring+mydict[myvarname] 
			else:
				newstring=newstring+mystring[pos]
				pos=pos+1
		else:
			newstring=newstring+mystring[pos]
			pos=pos+1
	if numvars==0:
		cexpand[mystring]=newstring[1:]
	return newstring[1:]	

def pickle_write(data,filename,debug=0):
	import os
	try:
		myf=open(filename,"w")
		cPickle.dump(data,myf,-1)
		myf.flush()
		myf.close()
		writemsg("Wrote pickle: "+str(filename)+"\n",1)
		os.chown(myefn,uid,portage_gid)
		os.chmod(myefn,0664)
	except SystemExit, e:
		raise
	except Exception, e:
		return 0
	return 1

def pickle_read(filename,default=None,debug=0):
	import os
	if not os.access(filename, os.R_OK):
		writemsg("pickle_read(): File not readable. '"+filename+"'\n",1)
		return default
	data = None
	try:
		myf = open(filename)
		mypickle = cPickle.Unpickler(myf)
		mypickle.find_global = None
		data = mypickle.load()
		myf.close()
		del mypickle,myf
		writemsg("pickle_read(): Loaded pickle. '"+filename+"'\n",1)
	except SystemExit, e:
		raise
	except Exception, e:
		writemsg("!!! Failed to load pickle: "+str(e)+"\n",1)
		data = default
	return data

def dump_traceback(msg, noiselevel=1):
	import sys, traceback
	info = sys.exc_info()
	if not info[2]:
		stack = traceback.extract_stack()[:-1]
		error = None
	else:
		stack = traceback.extract_tb(info[2])
		error = str(info[1])
	writemsg("\n====================================\n", noiselevel=noiselevel)
	writemsg("%s\n\n" % msg, noiselevel=noiselevel)
	for line in traceback.format_list(stack):
		writemsg(line, noiselevel=noiselevel)
	if error:
		writemsg(error+"\n", noiselevel=noiselevel)
	writemsg("====================================\n\n", noiselevel=noiselevel)

def unique_array(s):
	"""lifted from python cookbook, credit: Tim Peters
	Return a list of the elements in s in arbitrary order, sans duplicates"""
	n = len(s)
	# assume all elements are hashable, if so, it's linear
	try:
		return list(set(s))
	except TypeError:
		pass

	# so much for linear.  abuse sort.
	try:
		t = list(s)
		t.sort()
	except TypeError:
		pass
	else:
		assert n > 0
		last = t[0]
		lasti = i = 1
		while i < n:
			if t[i] != last:
				t[lasti] = last = t[i]
				lasti += 1
			i += 1
		return t[:lasti]

	# blah.	 back to original portage.unique_array
	u = []
	for x in s:
		if x not in u:
			u.append(x)
	return u

def apply_permissions(filename, uid=-1, gid=-1, mode=-1, mask=-1,
	stat_cached=None):
	"""Apply user, group, and mode bits to a file if the existing bits do not
	already match.  The default behavior is to force an exact match of mode
	bits.  When mask=0 is specified, mode bits on the target file are allowed
	to be a superset of the mode argument (via logical OR).  When mask>0, the
	mode bits that the target file is allowed to have are restricted via
	logical XOR.
	Returns True if the permissions were modified and False otherwise."""

	modified = False

	if stat_cached is None:
		try:
			stat_cached = os.stat(filename)
		except OSError, oe:
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted("stat('%s')" % filename)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			else:
				raise

	if	(uid != -1 and uid != stat_cached.st_uid) or \
		(gid != -1 and gid != stat_cached.st_gid):
		try:
			os.chown(filename, uid, gid)
			modified = True
		except OSError, oe:
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted("chown('%s', %i, %i)" % (filename, uid, gid))
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			else:
				raise

	new_mode = -1
	st_mode = stat_cached.st_mode & 07777 # protect from unwanted bits
	if mask >= 0:
		if mode == -1:
			mode = 0 # Don't add any mode bits when mode is unspecified.
		else:
			mode = mode & 07777
		if	(mode & st_mode != mode) or \
			((mask ^ st_mode) & st_mode != st_mode):
			new_mode = mode | st_mode
			new_mode = (mask ^ new_mode) & new_mode
	elif mode != -1:
		mode = mode & 07777 # protect from unwanted bits
		if mode != st_mode:
			new_mode = mode

	if new_mode != -1:
		try:
			os.chmod(filename, new_mode)
			modified = True
		except OSError, oe:
			func_call = "chmod('%s', %s)" % (filename, oct(new_mode))
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EROFS:
				raise ReadOnlyFileSystem(func_call)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			raise
	return modified

def apply_stat_permissions(filename, newstat, **kwargs):
	"""A wrapper around apply_secpass_permissions that gets
	uid, gid, and mode from a stat object"""
	return apply_secpass_permissions(filename, uid=newstat.st_uid, gid=newstat.st_gid,
	mode=newstat.st_mode, **kwargs)

def apply_recursive_permissions(top, uid=-1, gid=-1,
	dirmode=-1, dirmask=-1, filemode=-1, filemask=-1, onerror=None):
	"""A wrapper around apply_secpass_permissions that applies permissions
	recursively.  If optional argument onerror is specified, it should be a
	function; it will be called with one argument, a PortageException instance.
	Returns True if all permissions are applied and False if some are left
	unapplied."""

	if onerror is None:
		# Default behavior is to dump errors to stderr so they won't
		# go unnoticed.  Callers can pass in a quiet instance.
		def onerror(e):
			if isinstance(e, OperationNotPermitted):
				writemsg("Operation Not Permitted: %s\n" % str(e))
			elif isinstance(e, FileNotFound):
				writemsg("File Not Found: '%s'\n" % str(e))
			else:
				raise

	all_applied = True
	for dirpath, dirnames, filenames in os.walk(top):
		try:
			applied = apply_secpass_permissions(dirpath,
				uid=uid, gid=gid, mode=dirmode, mask=dirmask)
			if not applied:
				all_applied = False
		except PortageException, e:
			all_applied = False
			onerror(e)

		for name in filenames:
			try:
				applied = apply_secpass_permissions(os.path.join(dirpath, name),
					uid=uid, gid=gid, mode=filemode, mask=filemask)
				if not applied:
					all_applied = False
			except PortageException, e:
				all_applied = False
				onerror(e)
	return all_applied

def apply_secpass_permissions(filename, uid=-1, gid=-1, mode=-1, mask=-1,
	stat_cached=None):
	"""A wrapper around apply_permissions that uses secpass and simple
	logic to apply as much of the permissions as possible without
	generating an obviously avoidable permission exception. Despite
	attempts to avoid an exception, it's possible that one will be raised
	anyway, so be prepared.
	Returns True if all permissions are applied and False if some are left
	unapplied."""

	if stat_cached is None:
		try:
			stat_cached = os.stat(filename)
		except OSError, oe:
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted("stat('%s')" % filename)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			else:
				raise

	all_applied = True

	import portage_data # not imported globally because of circular dep
	if portage_data.secpass < 2:

		if uid != -1 and \
		uid != stat_cached.st_uid:
			all_applied = False
			uid = -1

		if gid != -1 and \
		gid != stat_cached.st_gid and \
		gid not in os.getgroups():
			all_applied = False
			gid = -1

	apply_permissions(filename, uid=uid, gid=gid, mode=mode, mask=mask, stat_cached=stat_cached)
	return all_applied

class atomic_ofstream(file):
	"""Write a file atomically via os.rename().  Atomic replacement prevents
	interprocess interference and prevents corruption of the target
	file when the write is interrupted (for example, when an 'out of space'
	error occurs)."""

	def __init__(self, filename, mode='w', follow_links=True, **kargs):
		"""Opens a temporary filename.pid in the same directory as filename."""
		self._aborted = False

		if follow_links:
			canonical_path = os.path.realpath(filename)
			self._real_name = canonical_path
			tmp_name = "%s.%i" % (canonical_path, os.getpid())
			try:
				super(atomic_ofstream, self).__init__(tmp_name, mode=mode, **kargs)
				return
			except (OSError, IOError), e:
				if canonical_path == filename:
					raise
				writemsg("!!! Failed to open file: '%s'\n" % tmp_name)
				writemsg("!!! %s\n" % str(e))

		self._real_name = filename
		tmp_name = "%s.%i" % (filename, os.getpid())
		super(atomic_ofstream, self).__init__(tmp_name, mode=mode, **kargs)

	def close(self):
		"""Closes the temporary file, copies permissions (if possible),
		and performs the atomic replacement via os.rename().  If the abort()
		method has been called, then the temp file is closed and removed."""
		if not self.closed:
			try:
				super(atomic_ofstream, self).close()
				if not self._aborted:
					try:
						apply_stat_permissions(self.name, os.stat(self._real_name))
					except OperationNotPermitted:
						pass
					except FileNotFound:
						pass
					except OSError, oe: # from the above os.stat call
						if oe.errno in (errno.ENOENT, errno.EPERM):
							pass
						else:
							raise
					os.rename(self.name, self._real_name)
			finally:
				# Make sure we cleanup the temp file
				# even if an exception is raised.
				try:
					os.unlink(self.name)
				except OSError, oe:
					pass

	def abort(self):
		"""If an error occurs while writing the file, the user should
		call this method in order to leave the target file unchanged.
		This will call close() automatically."""
		if not self._aborted:
			self._aborted = True
			self.close()

	def __del__(self):
		"""If the user does not explicitely call close(), it is
		assumed that an error has occurred, so we abort()."""
		if not self.closed:
			self.abort()
		# ensure destructor from the base class is called
		base_destructor = getattr(super(atomic_ofstream, self), '__del__', None)
		if base_destructor is not None:
			base_destructor()

def write_atomic(file_path, content):
	f = atomic_ofstream(file_path)
	try:
		f.write(content)
		f.close()
	except IOError, ioe:
		f.abort()
		raise ioe

def ensure_dirs(dir_path, *args, **kwargs):
	"""Create a directory and call apply_permissions.
	Returns True if a directory is created or the permissions needed to be
	modified, and False otherwise."""

	created_dir = False

	try:
		os.makedirs(dir_path)
		created_dir = True
	except OSError, oe:
		if errno.EEXIST == oe.errno:
			pass
		elif  oe.errno in (errno.EPERM, errno.EROFS):
			raise portage_exception.OperationNotPermitted(str(oe))
		else:
			raise
	perms_modified = apply_permissions(dir_path, *args, **kwargs)
	return created_dir or perms_modified

class LazyItemsDict(dict):
	"""A mapping object that behaves like a standard dict except that it allows
	for lazy initialization of values via callable objects.  Lazy items can be
	overwritten and deleted just as normal items."""
	def __init__(self, initial_items=None):
		dict.__init__(self)
		self.lazy_items = {}
		if initial_items is not None:
			self.update(initial_items)
			if isinstance(initial_items, LazyItemsDict):
				self.lazy_items.update(initial_items.lazy_items)
	def addLazyItem(self, item_key, value_callable):
		"""Add a lazy item for the given key.  When the item is requested,
		value_callable will be called with no arguments."""
		self.lazy_items[item_key] = value_callable
		# make it show up in self.keys(), etc...
		dict.__setitem__(self, item_key, None)
	def __getitem__(self, item_key):
		if item_key in self.lazy_items:
			return self.lazy_items[item_key]()
		else:
			return dict.__getitem__(self, item_key)
	def __setitem__(self, item_key, value):
		if item_key in self.lazy_items:
			del self.lazy_items[item_key]
		dict.__setitem__(self, item_key, value)
	def __delitem__(self, item_key):
		if item_key in self.lazy_items:
			del self.lazy_items[item_key]
		dict.__delitem__(self, item_key)
