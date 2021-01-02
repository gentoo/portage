# Copyright 2004-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['apply_permissions', 'apply_recursive_permissions',
	'apply_secpass_permissions', 'apply_stat_permissions', 'atomic_ofstream',
	'cmp_sort_key', 'ConfigProtect', 'dump_traceback', 'ensure_dirs',
	'find_updated_config_files', 'getconfig', 'getlibpaths', 'grabdict',
	'grabdict_package', 'grabfile', 'grabfile_package', 'grablines',
	'initialize_logger', 'LazyItemsDict', 'map_dictlist_vals',
	'new_protect_filename', 'normalize_path', 'pickle_read', 'stack_dictlist',
	'stack_dicts', 'stack_lists', 'unique_array', 'unique_everseen', 'varexpand',
	'write_atomic', 'writedict', 'writemsg', 'writemsg_level', 'writemsg_stdout']

from contextlib import AbstractContextManager
from copy import deepcopy
import errno
import io
from itertools import chain, filterfalse
import logging
import re
import shlex
import stat
import string
import sys
import traceback
import glob

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'pickle',
	'portage.dep:Atom',
	'subprocess',
)

from portage import os
from portage import _encodings
from portage import _os_merge
from portage import _unicode_encode
from portage import _unicode_decode
from portage.const import VCS_DIRS
from portage.exception import InvalidAtom, PortageException, FileNotFound, \
	IsADirectory, OperationNotPermitted, ParseError, PermissionDenied, \
	ReadOnlyFileSystem
from portage.localization import _
from portage.proxy.objectproxy import ObjectProxy
from portage.cache.mappings import UserDict


noiselimit = 0

def initialize_logger(level=logging.WARNING):
	"""Sets up basic logging of portage activities
	Args:
		level: the level to emit messages at ('info', 'debug', 'warning' ...)
	Returns:
		None
	"""
	logging.basicConfig(level=level, format='[%(levelname)-4s] %(message)s')

def writemsg(mystr, noiselevel=0, fd=None):
	"""Prints out warning and debug messages based on the noiselimit setting"""
	global noiselimit
	if fd is None:
		fd = sys.stderr
	if noiselevel <= noiselimit:
		# avoid potential UnicodeEncodeError
		if isinstance(fd, io.StringIO):
			mystr = _unicode_decode(mystr,
				encoding=_encodings['content'], errors='replace')
		else:
			mystr = _unicode_encode(mystr,
				encoding=_encodings['stdio'], errors='backslashreplace')
			if fd in (sys.stdout, sys.stderr):
				fd = fd.buffer
		fd.write(mystr)
		fd.flush()

def writemsg_stdout(mystr, noiselevel=0):
	"""Prints messages stdout based on the noiselimit setting"""
	writemsg(mystr, noiselevel=noiselevel, fd=sys.stdout)

def writemsg_level(msg, level=0, noiselevel=0):
	"""
	Show a message for the given level as defined by the logging module
	(default is 0). When level >= logging.WARNING then the message is
	sent to stderr, otherwise it is sent to stdout. The noiselevel is
	passed directly to writemsg().

	@type msg: str
	@param msg: a message string, including newline if appropriate
	@type level: int
	@param level: a numeric logging level (see the logging module)
	@type noiselevel: int
	@param noiselevel: passed directly to writemsg
	"""
	if level >= logging.WARNING:
		fd = sys.stderr
	else:
		fd = sys.stdout
	writemsg(msg, noiselevel=noiselevel, fd=fd)

def normalize_path(mypath):
	"""
	os.path.normpath("//foo") returns "//foo" instead of "/foo"
	We dislike this behavior so we create our own normpath func
	to fix it.
	"""
	if isinstance(mypath, bytes):
		path_sep = os.path.sep.encode()
	else:
		path_sep = os.path.sep

	if mypath.startswith(path_sep):
		# posixpath.normpath collapses 3 or more leading slashes to just 1.
		return os.path.normpath(2*path_sep + mypath)
	return os.path.normpath(mypath)

def grabfile(myfilename, compat_level=0, recursive=0, remember_source_file=False):
	"""This function grabs the lines in a file, normalizes whitespace and returns lines in a list; if a line
	begins with a #, it is ignored, as are empty lines"""

	mylines = grablines(myfilename, recursive, remember_source_file=True)
	newlines = []

	for x, source_file in mylines:
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		myline = x.split()
		if x and x[0] != "#":
			mylinetemp = []
			for item in myline:
				if item[:1] != "#":
					mylinetemp.append(item)
				else:
					break
			myline = mylinetemp

		myline = " ".join(myline)
		if not myline:
			continue
		if myline[0] == "#":
			# Check if we have a compat-level string. BC-integration data.
			# '##COMPAT==>N<==' 'some string attached to it'
			mylinetest = myline.split("<==", 1)
			if len(mylinetest) == 2:
				myline_potential = mylinetest[1]
				mylinetest = mylinetest[0].split("##COMPAT==>")
				if len(mylinetest) == 2:
					if compat_level >= int(mylinetest[1]):
						# It's a compat line, and the key matches.
						newlines.append(myline_potential)
				continue
			else:
				continue
		if remember_source_file:
			newlines.append((myline, source_file))
		else:
			newlines.append(myline)
	return newlines

def map_dictlist_vals(func, myDict):
	"""Performs a function on each value of each key in a dictlist.
	Returns a new dictlist."""
	new_dl = {}
	for key in myDict:
		new_dl[key] = []
		new_dl[key] = [func(x) for x in myDict[key]]
	return new_dl

def stack_dictlist(original_dicts, incremental=0, incrementals=[], ignore_none=0):
	"""
	Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->list.
	Returns a single dict. Higher index in lists is preferenced.

	Example usage:
	   >>> from portage.util import stack_dictlist
		>>> print stack_dictlist( [{'a':'b'},{'x':'y'}])
		>>> {'a':'b','x':'y'}
		>>> print stack_dictlist( [{'a':'b'},{'a':'c'}], incremental = True )
		>>> {'a':['b','c'] }
		>>> a = {'KEYWORDS':['x86','alpha']}
		>>> b = {'KEYWORDS':['-x86']}
		>>> print stack_dictlist( [a,b] )
		>>> { 'KEYWORDS':['x86','alpha','-x86']}
		>>> print stack_dictlist( [a,b], incremental=True)
		>>> { 'KEYWORDS':['alpha'] }
		>>> print stack_dictlist( [a,b], incrementals=['KEYWORDS'])
		>>> { 'KEYWORDS':['alpha'] }

	@param original_dicts a list of (dictionary objects or None)
	@type list
	@param incremental True or false depending on whether new keys should overwrite
	   keys which already exist.
	@type boolean
	@param incrementals A list of items that should be incremental (-foo removes foo from
	   the returned dict).
	@type list
	@param ignore_none Appears to be ignored, but probably was used long long ago.
	@type boolean

	"""
	final_dict = {}
	for mydict in original_dicts:
		if mydict is None:
			continue
		for y in mydict:
			if not y in final_dict:
				final_dict[y] = []

			for thing in mydict[y]:
				if thing:
					if incremental or y in incrementals:
						if thing == "-*":
							final_dict[y] = []
							continue
						elif thing[:1] == '-':
							try:
								final_dict[y].remove(thing[1:])
							except ValueError:
								pass
							continue
					if thing not in final_dict[y]:
						final_dict[y].append(thing)
			if y in final_dict and not final_dict[y]:
				del final_dict[y]
	return final_dict

def stack_dicts(dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->string.
	Returns a single dict."""
	final_dict = {}
	for mydict in dicts:
		if not mydict:
			continue
		for k, v in mydict.items():
			if k in final_dict and (incremental or (k in incrementals)):
				final_dict[k] += " " + v
			else:
				final_dict[k]  = v
	return final_dict

def append_repo(atom_list, repo_name, remember_source_file=False):
	"""
	Takes a list of valid atoms without repo spec and appends ::repo_name.
	If an atom already has a repo part, then it is preserved (see bug #461948).
	"""
	if remember_source_file:
		return [(atom.repo is not None and atom or atom.with_repo(repo_name), source) \
			for atom, source in atom_list]

	return [atom.repo is not None and atom or atom.with_repo(repo_name) \
		for atom in atom_list]

def stack_lists(lists, incremental=1, remember_source_file=False,
	warn_for_unmatched_removal=False, strict_warn_for_unmatched_removal=False, ignore_repo=False):
	"""Stacks an array of list-types into one array. Optionally removing
	distinct values using '-value' notation. Higher index is preferenced.

	all elements must be hashable."""
	matched_removals = set()
	unmatched_removals = {}
	new_list = {}
	for sub_list in lists:
		for token in sub_list:
			token_key = token
			if remember_source_file:
				token, source_file = token
			else:
				source_file = False

			if token is None:
				continue

			if incremental:
				if token == "-*":
					new_list.clear()
				elif token[:1] == '-':
					matched = False
					if ignore_repo and not "::" in token:
						#Let -cat/pkg remove cat/pkg::repo.
						to_be_removed = []
						token_slice = token[1:]
						for atom in new_list:
							atom_without_repo = atom
							if atom.repo is not None:
								# Atom.without_repo instantiates a new Atom,
								# which is unnecessary here, so use string
								# replacement instead.
								atom_without_repo = \
									atom.replace("::" + atom.repo, "", 1)
							if atom_without_repo == token_slice:
								to_be_removed.append(atom)
						if to_be_removed:
							matched = True
							for atom in to_be_removed:
								new_list.pop(atom)
					else:
						try:
							new_list.pop(token[1:])
							matched = True
						except KeyError:
							pass

					if not matched:
						if source_file and \
							(strict_warn_for_unmatched_removal or \
							token_key not in matched_removals):
							unmatched_removals.setdefault(source_file, set()).add(token)
					else:
						matched_removals.add(token_key)
				else:
					new_list[token] = source_file
			else:
				new_list[token] = source_file

	if warn_for_unmatched_removal:
		for source_file, tokens in unmatched_removals.items():
			if len(tokens) > 3:
				selected = [tokens.pop(), tokens.pop(), tokens.pop()]
				writemsg(_("--- Unmatched removal atoms in %s: %s and %s more\n") % \
					(source_file, ", ".join(selected), len(tokens)),
					noiselevel=-1)
			else:
				writemsg(_("--- Unmatched removal atom(s) in %s: %s\n") % (source_file, ", ".join(tokens)),
					noiselevel=-1)

	if remember_source_file:
		return list(new_list.items())
	return list(new_list)

def grabdict(myfilename, juststrings=0, empty=0, recursive=0, incremental=1, newlines=0):
	"""
	This function grabs the lines in a file, normalizes whitespace and returns lines in a dictionary

	@param myfilename: file to process
	@type myfilename: string (path)
	@param juststrings: only return strings
	@type juststrings: Boolean (integer)
	@param empty: Ignore certain lines
	@type empty: Boolean (integer)
	@param recursive: Recursively grab ( support for /etc/portage/package.keywords/* and friends )
	@type recursive: Boolean (integer)
	@param incremental: Append to the return list, don't overwrite
	@type incremental: Boolean (integer)
	@param newlines: Append newlines
	@type newlines: Boolean (integer)
	@rtype: Dictionary
	@return:
	1.  Returns the lines in a file in a dictionary, for example:
		'sys-apps/portage x86 amd64 ppc'
		would return
		{"sys-apps/portage" : ['x86', 'amd64', 'ppc']}
	"""
	newdict = {}
	for x in grablines(myfilename, recursive):
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		if x[0] == "#":
			continue
		myline=x.split()
		mylinetemp = []
		for item in myline:
			if item[:1] != "#":
				mylinetemp.append(item)
			else:
				break
		myline = mylinetemp
		if len(myline) < 2 and empty == 0:
			continue
		if len(myline) < 1 and empty == 1:
			continue
		if newlines:
			myline.append("\n")
		if incremental:
			newdict.setdefault(myline[0], []).extend(myline[1:])
		else:
			newdict[myline[0]] = myline[1:]
	if juststrings:
		for k, v in newdict.items():
			newdict[k] = " ".join(v)
	return newdict

_eapi_cache = {}

def read_corresponding_eapi_file(filename, default="0"):
	"""
	Read the 'eapi' file from the directory 'filename' is in.
	Returns "0" if the file is not present or invalid.
	"""
	eapi_file = os.path.join(os.path.dirname(filename), "eapi")
	try:
		eapi = _eapi_cache[eapi_file]
	except KeyError:
		pass
	else:
		if eapi is None:
			return default
		return eapi

	eapi = None
	try:
		with io.open(_unicode_encode(eapi_file,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace') as f:
			lines = f.readlines()
		if len(lines) == 1:
			eapi = lines[0].rstrip("\n")
		else:
			writemsg(_("--- Invalid 'eapi' file (doesn't contain exactly one line): %s\n") % (eapi_file),
				noiselevel=-1)
	except IOError:
		pass

	_eapi_cache[eapi_file] = eapi
	if eapi is None:
		return default
	return eapi

def grabdict_package(myfilename, juststrings=0, recursive=0, newlines=0,
	allow_wildcard=False, allow_repo=False, allow_build_id=False, allow_use=True,
	verify_eapi=False, eapi=None, eapi_default="0"):
	""" Does the same thing as grabdict except it validates keys
		with isvalidatom()"""

	if recursive:
		file_list = _recursive_file_list(myfilename)
	else:
		file_list = [myfilename]

	atoms = {}
	for filename in file_list:
		d = grabdict(filename, juststrings=False,
			empty=True, recursive=False, incremental=True, newlines=newlines)
		if not d:
			continue
		if verify_eapi and eapi is None:
			eapi = read_corresponding_eapi_file(
				myfilename, default=eapi_default)

		for k, v in d.items():
			try:
				k = Atom(k, allow_wildcard=allow_wildcard,
					allow_repo=allow_repo,
					allow_build_id=allow_build_id, eapi=eapi)
			except InvalidAtom as e:
				writemsg(_("--- Invalid atom in %s: %s\n") % (filename, e),
					noiselevel=-1)
			else:
				if not allow_use and k.use:
					writemsg(_("--- Atom is not allowed to have USE flag(s) in %s: %s\n") % (filename, k),
						noiselevel=-1)
					continue
				atoms.setdefault(k, []).extend(v)

	if juststrings:
		for k, v in atoms.items():
			atoms[k] = " ".join(v)

	return atoms

def grabfile_package(myfilename, compatlevel=0, recursive=0,
	allow_wildcard=False, allow_repo=False, allow_build_id=False,
	remember_source_file=False, verify_eapi=False, eapi=None,
	eapi_default="0"):

	pkgs=grabfile(myfilename, compatlevel, recursive=recursive, remember_source_file=True)
	if not pkgs:
		return pkgs
	if verify_eapi and eapi is None:
		eapi = read_corresponding_eapi_file(
			myfilename, default=eapi_default)
	mybasename = os.path.basename(myfilename)
	is_packages_file = mybasename == 'packages'
	atoms = []
	for pkg, source_file in pkgs:
		pkg_orig = pkg
		# for packages and package.mask files
		if pkg[:1] == "-":
			if is_packages_file and pkg == '-*':
				if remember_source_file:
					atoms.append((pkg, source_file))
				else:
					atoms.append(pkg)
				continue
			pkg = pkg[1:]
		if pkg[:1] == '*' and is_packages_file:
			pkg = pkg[1:]
		try:
			pkg = Atom(pkg, allow_wildcard=allow_wildcard,
				allow_repo=allow_repo, allow_build_id=allow_build_id,
				eapi=eapi)
		except InvalidAtom as e:
			writemsg(_("--- Invalid atom in %s: %s\n") % (source_file, e),
				noiselevel=-1)
		else:
			if pkg_orig == str(pkg):
				# normal atom, so return as Atom instance
				if remember_source_file:
					atoms.append((pkg, source_file))
				else:
					atoms.append(pkg)
			else:
				# atom has special prefix, so return as string
				if remember_source_file:
					atoms.append((pkg_orig, source_file))
				else:
					atoms.append(pkg_orig)
	return atoms

def _recursive_basename_filter(f):
	return not f.startswith(".") and not f.endswith("~")

def _recursive_file_list(path):
	# path may be a regular file or a directory

	def onerror(e):
		if e.errno == PermissionDenied.errno:
			raise PermissionDenied(path)

	stack = [os.path.split(path)]

	while stack:
		parent, fname = stack.pop()
		fullpath = os.path.join(parent, fname)

		try:
			st = os.stat(fullpath)
		except OSError as e:
			onerror(e)
			continue

		if stat.S_ISDIR(st.st_mode):
			if fname in VCS_DIRS or not _recursive_basename_filter(fname):
				continue
			try:
				children = os.listdir(fullpath)
			except OSError as e:
				onerror(e)
				continue

			# Sort in reverse, since we pop from the end of the stack.
			# Include regular files in the stack, so files are sorted
			# together with directories.
			children.sort(reverse=True)
			stack.extend((fullpath, x) for x in children)

		elif stat.S_ISREG(st.st_mode):
			if _recursive_basename_filter(fname):
				yield fullpath

def grablines(myfilename, recursive=0, remember_source_file=False):
	mylines = []
	if recursive:
		for f in _recursive_file_list(myfilename):
			mylines.extend(grablines(f, recursive=False,
				remember_source_file=remember_source_file))

	else:
		try:
			with io.open(_unicode_encode(myfilename,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'], errors='replace') as myfile:
				if remember_source_file:
					mylines = [(line, myfilename) for line in myfile.readlines()]
				else:
					mylines = myfile.readlines()
		except IOError as e:
			if e.errno == PermissionDenied.errno:
				raise PermissionDenied(myfilename)
			elif e.errno in (errno.ENOENT, errno.ESTALE):
				pass
			else:
				raise
	return mylines

def writedict(mydict, myfilename, writekey=True):
	"""Writes out a dict to a file; writekey=0 mode doesn't write out
	the key and assumes all values are strings, not lists."""
	lines = []
	if not writekey:
		for v in mydict.values():
			lines.append(v + "\n")
	else:
		for k, v in mydict.items():
			lines.append("%s %s\n" % (k, " ".join(v)))
	write_atomic(myfilename, "".join(lines))


def shlex_split(s):
	"""
	This is equivalent to shlex.split, but if the current interpreter is
	python2, it temporarily encodes unicode strings to bytes since python2's
	shlex.split() doesn't handle unicode strings.
	"""
	return shlex.split(s)


class _getconfig_shlex(shlex.shlex):

	def __init__(self, portage_tolerant=False, **kwargs):
		shlex.shlex.__init__(self, **kwargs)
		self.__portage_tolerant = portage_tolerant

	def allow_sourcing(self, var_expand_map):
		self.source = portage._native_string("source")
		self.var_expand_map = var_expand_map

	def sourcehook(self, newfile):
		try:
			newfile = varexpand(newfile, self.var_expand_map)
			return shlex.shlex.sourcehook(self, newfile)
		except EnvironmentError as e:
			if e.errno == PermissionDenied.errno:
				raise PermissionDenied(newfile)
			if e.errno not in (errno.ENOENT, errno.ENOTDIR):
				writemsg("open('%s', 'r'): %s\n" % (newfile, e), noiselevel=-1)
				raise

			msg = self.error_leader()
			if e.errno == errno.ENOTDIR:
				msg += _("%s: Not a directory") % newfile
			else:
				msg += _("%s: No such file or directory") % newfile

			if self.__portage_tolerant:
				writemsg("%s\n" % msg, noiselevel=-1)
			else:
				raise ParseError(msg)
			return (newfile, io.StringIO())

_invalid_var_name_re = re.compile(r'^\d|\W')

def getconfig(mycfg, tolerant=False, allow_sourcing=False, expand=True,
	recursive=False):

	if isinstance(expand, dict):
		# Some existing variable definitions have been
		# passed in, for use in substitutions.
		expand_map = expand
		expand = True
	else:
		expand_map = {}
	mykeys = {}

	if recursive:
		# Emulate source commands so that syntax error messages
		# can display real file names and line numbers.
		if not expand:
			expand_map = False
		fname = None
		for fname in _recursive_file_list(mycfg):
			mykeys.update(getconfig(fname, tolerant=tolerant,
				allow_sourcing=allow_sourcing, expand=expand_map,
				recursive=False) or {})
		if fname is None:
			return None
		return mykeys

	f = None
	try:
		f = open(_unicode_encode(mycfg,
			encoding=_encodings['fs'], errors='strict'), mode='r',
			encoding=_encodings['content'], errors='replace')
		content = f.read()
	except IOError as e:
		if e.errno == PermissionDenied.errno:
			raise PermissionDenied(mycfg)
		if e.errno != errno.ENOENT:
			writemsg("open('%s', 'r'): %s\n" % (mycfg, e), noiselevel=-1)
			if e.errno not in (errno.EISDIR,):
				raise
		return None
	finally:
		if f is not None:
			f.close()

	# Since this file has unicode_literals enabled, and Python 2's
	# shlex implementation does not support unicode, the following code
	# uses _native_string() to encode unicode literals when necessary.

	# Workaround for avoiding a silent error in shlex that is
	# triggered by a source statement at the end of the file
	# without a trailing newline after the source statement.
	if content and content[-1] != portage._native_string('\n'):
		content += portage._native_string('\n')

	# Warn about dos-style line endings since that prevents
	# people from being able to source them with bash.
	if portage._native_string('\r') in content:
		writemsg(("!!! " + _("Please use dos2unix to convert line endings " + \
			"in config file: '%s'") + "\n") % mycfg, noiselevel=-1)

	lex = None
	try:
		# The default shlex.sourcehook() implementation
		# only joins relative paths when the infile
		# attribute is properly set.
		lex = _getconfig_shlex(instream=content, infile=mycfg, posix=True,
			portage_tolerant=tolerant)
		lex.wordchars = portage._native_string(string.digits +
			string.ascii_letters + r"~!@#$%*_\:;?,./-+{}")
		lex.quotes = portage._native_string("\"'")
		if allow_sourcing:
			lex.allow_sourcing(expand_map)

		while True:
			key = _unicode_decode(lex.get_token())
			if key == "export":
				key = _unicode_decode(lex.get_token())
			if key is None:
				#normal end of file
				break

			equ = _unicode_decode(lex.get_token())
			if not equ:
				msg = lex.error_leader() + _("Unexpected EOF")
				if not tolerant:
					raise ParseError(msg)
				else:
					writemsg("%s\n" % msg, noiselevel=-1)
					return mykeys

			elif equ != "=":
				msg = lex.error_leader() + \
					_("Invalid token '%s' (not '=')") % (equ,)
				if not tolerant:
					raise ParseError(msg)
				else:
					writemsg("%s\n" % msg, noiselevel=-1)
					return mykeys

			val = _unicode_decode(lex.get_token())
			if val is None:
				msg = lex.error_leader() + \
					_("Unexpected end of config file: variable '%s'") % (key,)
				if not tolerant:
					raise ParseError(msg)
				else:
					writemsg("%s\n" % msg, noiselevel=-1)
					return mykeys

			if _invalid_var_name_re.search(key) is not None:
				msg = lex.error_leader() + \
					_("Invalid variable name '%s'") % (key,)
				if not tolerant:
					raise ParseError(msg)
				writemsg("%s\n" % msg, noiselevel=-1)
				continue

			if expand:
				mykeys[key] = varexpand(val, mydict=expand_map,
					error_leader=lex.error_leader)
				expand_map[key] = mykeys[key]
			else:
				mykeys[key] = val
	except SystemExit as e:
		raise
	except Exception as e:
		if isinstance(e, ParseError) or lex is None:
			raise
		msg = "%s%s" % (lex.error_leader(), e)
		writemsg("%s\n" % msg, noiselevel=-1)
		raise

	return mykeys

_varexpand_word_chars = frozenset(string.ascii_letters + string.digits + "_")
_varexpand_unexpected_eof_msg = "unexpected EOF while looking for matching `}'"

def varexpand(mystring, mydict=None, error_leader=None):
	if mydict is None:
		mydict = {}

	"""
	new variable expansion code.  Preserves quotes, handles \n, etc.
	This code is used by the configfile code, as well as others (parser)
	This would be a good bunch of code to port to C.
	"""
	numvars = 0
	# in single, double quotes
	insing = 0
	indoub = 0
	pos = 0
	length = len(mystring)
	newstring = []
	while pos < length:
		current = mystring[pos]
		if current == "'":
			if indoub:
				newstring.append("'")
			else:
				newstring.append("'") # Quote removal is handled by shlex.
				insing=not insing
			pos += 1
			continue
		elif current == '"':
			if insing:
				newstring.append('"')
			else:
				newstring.append('"') # Quote removal is handled by shlex.
				indoub=not indoub
			pos += 1
			continue
		if not insing:
			#expansion time
			if current == "\n":
				#convert newlines to spaces
				newstring.append(" ")
				pos += 1
			elif current == "\\":
				# For backslash expansion, this function used to behave like
				# echo -e, but that's not needed for our purposes. We want to
				# behave like bash does when expanding a variable assignment
				# in a sourced file, in which case it performs backslash
				# removal for \\ and \$ but nothing more. It also removes
				# escaped newline characters. Note that we don't handle
				# escaped quotes here, since getconfig() uses shlex
				# to handle that earlier.
				if pos + 1 >= len(mystring):
					newstring.append(current)
					break
				else:
					current = mystring[pos + 1]
					pos += 2
					if current == "$":
						newstring.append(current)
					elif current == "\\":
						newstring.append(current)
						# BUG: This spot appears buggy, but it's intended to
						# be bug-for-bug compatible with existing behavior.
						if pos < length and \
							mystring[pos] in ("'", '"', "$"):
							newstring.append(mystring[pos])
							pos += 1
					elif current == "\n":
						pass
					else:
						newstring.append(mystring[pos - 2:pos])
					continue
			elif current == "$":
				pos += 1
				if pos == length:
					# shells handle this like \$
					newstring.append(current)
					continue

				if mystring[pos] == "{":
					pos += 1
					if pos == length:
						msg = _varexpand_unexpected_eof_msg
						if error_leader is not None:
							msg = error_leader() + msg
						writemsg(msg + "\n", noiselevel=-1)
						return ""

					braced = True
				else:
					braced = False
				myvstart = pos
				while mystring[pos] in _varexpand_word_chars:
					if pos + 1 >= len(mystring):
						if braced:
							msg = _varexpand_unexpected_eof_msg
							if error_leader is not None:
								msg = error_leader() + msg
							writemsg(msg + "\n", noiselevel=-1)
							return ""
						pos += 1
						break
					pos += 1
				myvarname = mystring[myvstart:pos]
				if braced:
					if mystring[pos] != "}":
						msg = _varexpand_unexpected_eof_msg
						if error_leader is not None:
							msg = error_leader() + msg
						writemsg(msg + "\n", noiselevel=-1)
						return ""
					pos += 1
				if len(myvarname) == 0:
					msg = "$"
					if braced:
						msg += "{}"
					msg += ": bad substitution"
					if error_leader is not None:
						msg = error_leader() + msg
					writemsg(msg + "\n", noiselevel=-1)
					return ""
				numvars += 1
				if myvarname in mydict:
					newstring.append(mydict[myvarname])
			else:
				newstring.append(current)
				pos += 1
		else:
			newstring.append(current)
			pos += 1

	return "".join(newstring)

# broken and removed, but can still be imported
pickle_write = None

def pickle_read(filename, default=None, debug=0):
	if not os.access(filename, os.R_OK):
		writemsg(_("pickle_read(): File not readable. '") + filename + "'\n", 1)
		return default
	data = None
	try:
		myf = open(_unicode_encode(filename,
			encoding=_encodings['fs'], errors='strict'), 'rb')
		mypickle = pickle.Unpickler(myf)
		data = mypickle.load()
		myf.close()
		del mypickle, myf
		writemsg(_("pickle_read(): Loaded pickle. '") + filename + "'\n", 1)
	except SystemExit as e:
		raise
	except Exception as e:
		writemsg(_("!!! Failed to load pickle: ") + str(e) + "\n", 1)
		data = default
	return data

def dump_traceback(msg, noiselevel=1):
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

class cmp_sort_key:
	"""
	In python-3.0 the list.sort() method no longer has a "cmp" keyword
	argument. This class acts as an adapter which converts a cmp function
	into one that's suitable for use as the "key" keyword argument to
	list.sort(), making it easier to port code for python-3.0 compatibility.
	It works by generating key objects which use the given cmp function to
	implement their __lt__ method.

	Beginning with Python 2.7 and 3.2, equivalent functionality is provided
	by functools.cmp_to_key().
	"""
	__slots__ = ("_cmp_func",)

	def __init__(self, cmp_func):
		"""
		@type cmp_func: callable which takes 2 positional arguments
		@param cmp_func: A cmp function.
		"""
		self._cmp_func = cmp_func

	def __call__(self, lhs):
		return self._cmp_key(self._cmp_func, lhs)

	class _cmp_key:
		__slots__ = ("_cmp_func", "_obj")

		def __init__(self, cmp_func, obj):
			self._cmp_func = cmp_func
			self._obj = obj

		def __lt__(self, other):
			if other.__class__ is not self.__class__:
				raise TypeError("Expected type %s, got %s" % \
					(self.__class__, other.__class__))
			return self._cmp_func(self._obj, other._obj) < 0

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

def unique_everseen(iterable, key=None):
	"""
	List unique elements, preserving order. Remember all elements ever seen.
	Taken from itertools documentation.
	"""
	# unique_everseen('AAAABBBCCDAABBB') --> A B C D
	# unique_everseen('ABBCcAD', str.lower) --> A B C D
	seen = set()
	seen_add = seen.add
	if key is None:
		for element in filterfalse(seen.__contains__, iterable):
			seen_add(element)
			yield element
	else:
		for element in iterable:
			k = key(element)
			if k not in seen:
				seen_add(k)
				yield element

def _do_stat(filename, follow_links=True):
	try:
		if follow_links:
			return os.stat(filename)
		return os.lstat(filename)
	except OSError as oe:
		func_call = "stat('%s')" % filename
		if oe.errno == errno.EPERM:
			raise OperationNotPermitted(func_call)
		if oe.errno == errno.EACCES:
			raise PermissionDenied(func_call)
		if oe.errno == errno.ENOENT:
			raise FileNotFound(filename)
		raise

def apply_permissions(filename, uid=-1, gid=-1, mode=-1, mask=-1,
	stat_cached=None, follow_links=True):
	"""Apply user, group, and mode bits to a file if the existing bits do not
	already match.  The default behavior is to force an exact match of mode
	bits.  When mask=0 is specified, mode bits on the target file are allowed
	to be a superset of the mode argument (via logical OR).  When mask>0, the
	mode bits that the target file is allowed to have are restricted via
	logical XOR.
	Returns True if the permissions were modified and False otherwise."""

	modified = False

	# Since Python 3.4, chown requires int type (no proxies).
	uid = int(uid)
	gid = int(gid)

	if stat_cached is None:
		stat_cached = _do_stat(filename, follow_links=follow_links)

	if	(uid != -1 and uid != stat_cached.st_uid) or \
		(gid != -1 and gid != stat_cached.st_gid):
		try:
			if follow_links:
				os.chown(filename, uid, gid)
			else:
				portage.data.lchown(filename, uid, gid)
			modified = True
		except OSError as oe:
			func_call = "chown('%s', %i, %i)" % (filename, uid, gid)
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EACCES:
				raise PermissionDenied(func_call)
			elif oe.errno == errno.EROFS:
				raise ReadOnlyFileSystem(func_call)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			else:
				raise

	new_mode = -1
	st_mode = stat_cached.st_mode & 0o7777 # protect from unwanted bits
	if mask >= 0:
		if mode == -1:
			mode = 0 # Don't add any mode bits when mode is unspecified.
		else:
			mode = mode & 0o7777
		if	(mode & st_mode != mode) or \
			((mask ^ st_mode) & st_mode != st_mode):
			new_mode = mode | st_mode
			new_mode = (mask ^ new_mode) & new_mode
	elif mode != -1:
		mode = mode & 0o7777 # protect from unwanted bits
		if mode != st_mode:
			new_mode = mode

	# The chown system call may clear S_ISUID and S_ISGID
	# bits, so those bits are restored if necessary.
	if modified and new_mode == -1 and \
		(st_mode & stat.S_ISUID or st_mode & stat.S_ISGID):
		if mode == -1:
			new_mode = st_mode
		else:
			mode = mode & 0o7777
			if mask >= 0:
				new_mode = mode | st_mode
				new_mode = (mask ^ new_mode) & new_mode
			else:
				new_mode = mode
			if not (new_mode & stat.S_ISUID or new_mode & stat.S_ISGID):
				new_mode = -1

	if not follow_links and stat.S_ISLNK(stat_cached.st_mode):
		# Mode doesn't matter for symlinks.
		new_mode = -1

	if new_mode != -1:
		try:
			os.chmod(filename, new_mode)
			modified = True
		except OSError as oe:
			func_call = "chmod('%s', %s)" % (filename, oct(new_mode))
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EACCES:
				raise PermissionDenied(func_call)
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

	# Avoid issues with circular symbolic links, as in bug #339670.
	follow_links = False

	if onerror is None:
		# Default behavior is to dump errors to stderr so they won't
		# go unnoticed.  Callers can pass in a quiet instance.
		def onerror(e):
			if isinstance(e, OperationNotPermitted):
				writemsg(_("Operation Not Permitted: %s\n") % str(e),
					noiselevel=-1)
			elif isinstance(e, FileNotFound):
				writemsg(_("File Not Found: '%s'\n") % str(e), noiselevel=-1)
			else:
				raise

	# For bug 554084, always apply permissions to a directory before
	# that directory is traversed.
	all_applied = True

	try:
		stat_cached = _do_stat(top, follow_links=follow_links)
	except FileNotFound:
		# backward compatibility
		return True

	if stat.S_ISDIR(stat_cached.st_mode):
		mode = dirmode
		mask = dirmask
	else:
		mode = filemode
		mask = filemask

	try:
		applied = apply_secpass_permissions(top,
			uid=uid, gid=gid, mode=mode, mask=mask,
			stat_cached=stat_cached, follow_links=follow_links)
		if not applied:
			all_applied = False
	except PortageException as e:
		all_applied = False
		onerror(e)

	for dirpath, dirnames, filenames in os.walk(top):
		for name, mode, mask in chain(
			((x, filemode, filemask) for x in filenames),
			((x, dirmode, dirmask) for x in dirnames)):
			try:
				applied = apply_secpass_permissions(os.path.join(dirpath, name),
					uid=uid, gid=gid, mode=mode, mask=mask,
					follow_links=follow_links)
				if not applied:
					all_applied = False
			except PortageException as e:
				# Ignore InvalidLocation exceptions such as FileNotFound
				# and DirectoryNotFound since sometimes things disappear,
				# like when adjusting permissions on DISTCC_DIR.
				if not isinstance(e, portage.exception.InvalidLocation):
					all_applied = False
					onerror(e)
	return all_applied

def apply_secpass_permissions(filename, uid=-1, gid=-1, mode=-1, mask=-1,
	stat_cached=None, follow_links=True):
	"""A wrapper around apply_permissions that uses secpass and simple
	logic to apply as much of the permissions as possible without
	generating an obviously avoidable permission exception. Despite
	attempts to avoid an exception, it's possible that one will be raised
	anyway, so be prepared.
	Returns True if all permissions are applied and False if some are left
	unapplied."""

	if stat_cached is None:
		stat_cached = _do_stat(filename, follow_links=follow_links)

	all_applied = True

	# Avoid accessing portage.data.secpass when possible, since
	# it triggers config loading (undesirable for chmod-lite).
	if (uid != -1 or gid != -1) and portage.data.secpass < 2:

		if uid != -1 and \
		uid != stat_cached.st_uid:
			all_applied = False
			uid = -1

		if gid != -1 and \
		gid != stat_cached.st_gid and \
		gid not in os.getgroups():
			all_applied = False
			gid = -1

	apply_permissions(filename, uid=uid, gid=gid, mode=mode, mask=mask,
		stat_cached=stat_cached, follow_links=follow_links)
	return all_applied

class atomic_ofstream(AbstractContextManager, ObjectProxy):
	"""Write a file atomically via os.rename().  Atomic replacement prevents
	interprocess interference and prevents corruption of the target
	file when the write is interrupted (for example, when an 'out of space'
	error occurs)."""

	def __init__(self, filename, mode='w', follow_links=True, **kargs):
		"""Opens a temporary filename.pid in the same directory as filename."""
		ObjectProxy.__init__(self)
		object.__setattr__(self, '_aborted', False)
		if 'b' in mode:
			open_func = open
		else:
			open_func = io.open
			kargs.setdefault('encoding', _encodings['content'])
			kargs.setdefault('errors', 'backslashreplace')

		if follow_links:
			canonical_path = os.path.realpath(filename)
			object.__setattr__(self, '_real_name', canonical_path)
			tmp_name = "%s.%i" % (canonical_path, portage.getpid())
			try:
				object.__setattr__(self, '_file',
					open_func(_unicode_encode(tmp_name,
						encoding=_encodings['fs'], errors='strict'),
						mode=mode, **kargs))
				return
			except IOError as e:
				if canonical_path == filename:
					raise
				# Ignore this error, since it's irrelevant
				# and the below open call will produce a
				# new error if necessary.

		object.__setattr__(self, '_real_name', filename)
		tmp_name = "%s.%i" % (filename, portage.getpid())
		object.__setattr__(self, '_file',
			open_func(_unicode_encode(tmp_name,
				encoding=_encodings['fs'], errors='strict'),
				mode=mode, **kargs))

	def __exit__(self, exc_type, exc_val, exc_tb):
		if exc_type is not None:
			self.abort()
		else:
			self.close()

	def _get_target(self):
		return object.__getattribute__(self, '_file')

	def __getattribute__(self, attr):
		if attr in ('close', 'abort', '__del__'):
			return object.__getattribute__(self, attr)
		return getattr(object.__getattribute__(self, '_file'), attr)

	def close(self):
		"""Closes the temporary file, copies permissions (if possible),
		and performs the atomic replacement via os.rename().  If the abort()
		method has been called, then the temp file is closed and removed."""
		f = object.__getattribute__(self, '_file')
		real_name = object.__getattribute__(self, '_real_name')
		if not f.closed:
			try:
				f.close()
				if not object.__getattribute__(self, '_aborted'):
					try:
						apply_stat_permissions(f.name, os.stat(real_name))
					except OperationNotPermitted:
						pass
					except FileNotFound:
						pass
					except OSError as oe: # from the above os.stat call
						if oe.errno in (errno.ENOENT, errno.EPERM):
							pass
						else:
							raise
					os.rename(f.name, real_name)
			finally:
				# Make sure we cleanup the temp file
				# even if an exception is raised.
				try:
					os.unlink(f.name)
				except OSError as oe:
					pass

	def abort(self):
		"""If an error occurs while writing the file, the user should
		call this method in order to leave the target file unchanged.
		This will call close() automatically."""
		if not object.__getattribute__(self, '_aborted'):
			object.__setattr__(self, '_aborted', True)
			self.close()

	def __del__(self):
		"""If the user does not explicitly call close(), it is
		assumed that an error has occurred, so we abort()."""
		try:
			f = object.__getattribute__(self, '_file')
		except AttributeError:
			pass
		else:
			if not f.closed:
				self.abort()
		# ensure destructor from the base class is called
		base_destructor = getattr(ObjectProxy, '__del__', None)
		if base_destructor is not None:
			base_destructor(self)

def write_atomic(file_path, content, **kwargs):
	f = None
	try:
		f = atomic_ofstream(file_path, **kwargs)
		f.write(content)
		f.close()
	except (IOError, OSError) as e:
		if f:
			f.abort()
		func_call = "write_atomic('%s')" % file_path
		if e.errno == errno.EPERM:
			raise OperationNotPermitted(func_call)
		elif e.errno == errno.EACCES:
			raise PermissionDenied(func_call)
		elif e.errno == errno.EROFS:
			raise ReadOnlyFileSystem(func_call)
		elif e.errno == errno.ENOENT:
			raise FileNotFound(file_path)
		else:
			raise

def ensure_dirs(dir_path, **kwargs):
	"""Create a directory and call apply_permissions.
	Returns True if a directory is created or the permissions needed to be
	modified, and False otherwise.

	This function's handling of EEXIST errors makes it useful for atomic
	directory creation, in which multiple processes may be competing to
	create the same directory.
	"""

	created_dir = False

	try:
		os.makedirs(dir_path)
		created_dir = True
	except OSError as oe:
		func_call = "makedirs('%s')" % dir_path
		if oe.errno in (errno.EEXIST,):
			pass
		else:
			if os.path.isdir(dir_path):
				# NOTE: DragonFly raises EPERM for makedir('/')
				# and that is supposed to be ignored here.
				# Also, sometimes mkdir raises EISDIR on FreeBSD
				# and we want to ignore that too (bug #187518).
				pass
			elif oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EACCES:
				raise PermissionDenied(func_call)
			elif oe.errno == errno.EROFS:
				raise ReadOnlyFileSystem(func_call)
			else:
				raise
	if kwargs:
		perms_modified = apply_permissions(dir_path, **kwargs)
	else:
		perms_modified = False
	return created_dir or perms_modified

class LazyItemsDict(UserDict):
	"""A mapping object that behaves like a standard dict except that it allows
	for lazy initialization of values via callable objects.  Lazy items can be
	overwritten and deleted just as normal items."""

	__slots__ = ('lazy_items',)

	def __init__(self, *args, **kwargs):

		self.lazy_items = {}
		UserDict.__init__(self, *args, **kwargs)

	def addLazyItem(self, item_key, value_callable, *pargs, **kwargs):
		"""Add a lazy item for the given key.  When the item is requested,
		value_callable will be called with *pargs and **kwargs arguments."""
		self.lazy_items[item_key] = \
			self._LazyItem(value_callable, pargs, kwargs, False)
		# make it show up in self.keys(), etc...
		UserDict.__setitem__(self, item_key, None)

	def addLazySingleton(self, item_key, value_callable, *pargs, **kwargs):
		"""This is like addLazyItem except value_callable will only be called
		a maximum of 1 time and the result will be cached for future requests."""
		self.lazy_items[item_key] = \
			self._LazyItem(value_callable, pargs, kwargs, True)
		# make it show up in self.keys(), etc...
		UserDict.__setitem__(self, item_key, None)

	def update(self, *args, **kwargs):
		if len(args) > 1:
			raise TypeError(
				"expected at most 1 positional argument, got " + \
				repr(len(args)))
		if args:
			map_obj = args[0]
		else:
			map_obj = None
		if map_obj is None:
			pass
		elif isinstance(map_obj, LazyItemsDict):
			for k in map_obj:
				if k in map_obj.lazy_items:
					UserDict.__setitem__(self, k, None)
				else:
					UserDict.__setitem__(self, k, map_obj[k])
			self.lazy_items.update(map_obj.lazy_items)
		else:
			UserDict.update(self, map_obj)
		if kwargs:
			UserDict.update(self, kwargs)

	def __getitem__(self, item_key):
		if item_key in self.lazy_items:
			lazy_item = self.lazy_items[item_key]
			pargs = lazy_item.pargs
			if pargs is None:
				pargs = ()
			kwargs = lazy_item.kwargs
			if kwargs is None:
				kwargs = {}
			result = lazy_item.func(*pargs, **kwargs)
			if lazy_item.singleton:
				self[item_key] = result
			return result

		return UserDict.__getitem__(self, item_key)

	def __setitem__(self, item_key, value):
		if item_key in self.lazy_items:
			del self.lazy_items[item_key]
		UserDict.__setitem__(self, item_key, value)

	def __delitem__(self, item_key):
		if item_key in self.lazy_items:
			del self.lazy_items[item_key]
		UserDict.__delitem__(self, item_key)

	def clear(self):
		self.lazy_items.clear()
		UserDict.clear(self)

	def copy(self):
		return self.__copy__()

	def __copy__(self):
		return self.__class__(self)

	def __deepcopy__(self, memo=None):
		"""
		This forces evaluation of each contained lazy item, and deepcopy of
		the result. A TypeError is raised if any contained lazy item is not
		a singleton, since it is not necessarily possible for the behavior
		of this type of item to be safely preserved.
		"""
		if memo is None:
			memo = {}
		result = self.__class__()
		memo[id(self)] = result
		for k in self:
			k_copy = deepcopy(k, memo)
			lazy_item = self.lazy_items.get(k)
			if lazy_item is not None:
				if not lazy_item.singleton:
					raise TypeError("LazyItemsDict " + \
						"deepcopy is unsafe with lazy items that are " + \
						"not singletons: key=%s value=%s" % (k, lazy_item,))
			UserDict.__setitem__(result, k_copy, deepcopy(self[k], memo))
		return result

	class _LazyItem:

		__slots__ = ('func', 'pargs', 'kwargs', 'singleton')

		def __init__(self, func, pargs, kwargs, singleton):

			if not pargs:
				pargs = None
			if not kwargs:
				kwargs = None

			self.func = func
			self.pargs = pargs
			self.kwargs = kwargs
			self.singleton = singleton

		def __copy__(self):
			return self.__class__(self.func, self.pargs,
				self.kwargs, self.singleton)

		def __deepcopy__(self, memo=None):
			"""
			Override this since the default implementation can fail silently,
			leaving some attributes unset.
			"""
			if memo is None:
				memo = {}
			result = self.__copy__()
			memo[id(self)] = result
			result.func = deepcopy(self.func, memo)
			result.pargs = deepcopy(self.pargs, memo)
			result.kwargs = deepcopy(self.kwargs, memo)
			result.singleton = deepcopy(self.singleton, memo)
			return result

class ConfigProtect:
	def __init__(self, myroot, protect_list, mask_list,
		case_insensitive=False):
		self.myroot = myroot
		self.protect_list = protect_list
		self.mask_list = mask_list
		self.case_insensitive = case_insensitive
		self.updateprotect()

	def updateprotect(self):
		"""Update internal state for isprotected() calls.  Nonexistent paths
		are ignored."""

		os = _os_merge

		self.protect = []
		self._dirs = set()
		for x in self.protect_list:
			ppath = normalize_path(
				os.path.join(self.myroot, x.lstrip(os.path.sep)))
			# Protect files that don't exist (bug #523684). If the
			# parent directory doesn't exist, we can safely skip it.
			if os.path.isdir(os.path.dirname(ppath)):
				self.protect.append(ppath)
			try:
				if stat.S_ISDIR(os.stat(ppath).st_mode):
					self._dirs.add(ppath)
			except OSError:
				pass

		self.protectmask = []
		for x in self.mask_list:
			ppath = normalize_path(
				os.path.join(self.myroot, x.lstrip(os.path.sep)))
			if self.case_insensitive:
				ppath = ppath.lower()
			try:
				"""Use lstat so that anything, even a broken symlink can be
				protected."""
				if stat.S_ISDIR(os.lstat(ppath).st_mode):
					self._dirs.add(ppath)
				self.protectmask.append(ppath)
				"""Now use stat in case this is a symlink to a directory."""
				if stat.S_ISDIR(os.stat(ppath).st_mode):
					self._dirs.add(ppath)
			except OSError:
				# If it doesn't exist, there's no need to mask it.
				pass

	def isprotected(self, obj):
		"""Returns True if obj is protected, False otherwise.  The caller must
		ensure that obj is normalized with a single leading slash.  A trailing
		slash is optional for directories."""
		masked = 0
		protected = 0
		sep = os.path.sep
		if self.case_insensitive:
			obj = obj.lower()
		for ppath in self.protect:
			if len(ppath) > masked and obj.startswith(ppath):
				if ppath in self._dirs:
					if obj != ppath and not obj.startswith(ppath + sep):
						# /etc/foo does not match /etc/foobaz
						continue
				elif obj != ppath:
					# force exact match when CONFIG_PROTECT lists a
					# non-directory
					continue
				protected = len(ppath)
				#config file management
				for pmpath in self.protectmask:
					if len(pmpath) >= protected and obj.startswith(pmpath):
						if pmpath in self._dirs:
							if obj != pmpath and \
								not obj.startswith(pmpath + sep):
								# /etc/foo does not match /etc/foobaz
								continue
						elif obj != pmpath:
							# force exact match when CONFIG_PROTECT_MASK lists
							# a non-directory
							continue
						#skip, it's in the mask
						masked = len(pmpath)
		return protected > masked

def new_protect_filename(mydest, newmd5=None, force=False):
	"""Resolves a config-protect filename for merging, optionally
	using the last filename if the md5 matches. If force is True,
	then a new filename will be generated even if mydest does not
	exist yet.
	(dest,md5) ==> 'string'            --- path_to_target_filename
	(dest)     ==> ('next', 'highest') --- next_target and most-recent_target
	"""

	# config protection filename format:
	# ._cfg0000_foo
	# 0123456789012

	os = _os_merge

	prot_num = -1
	last_pfile = ""

	if not force and \
		not os.path.exists(mydest):
		return mydest

	real_filename = os.path.basename(mydest)
	real_dirname  = os.path.dirname(mydest)
	for pfile in os.listdir(real_dirname):
		if pfile[0:5] != "._cfg":
			continue
		if pfile[10:] != real_filename:
			continue
		try:
			new_prot_num = int(pfile[5:9])
			if new_prot_num > prot_num:
				prot_num = new_prot_num
				last_pfile = pfile
		except ValueError:
			continue
	prot_num = prot_num + 1

	new_pfile = normalize_path(os.path.join(real_dirname,
		"._cfg" + str(prot_num).zfill(4) + "_" + real_filename))
	old_pfile = normalize_path(os.path.join(real_dirname, last_pfile))
	if last_pfile and newmd5:
		try:
			old_pfile_st = os.lstat(old_pfile)
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
		else:
			if stat.S_ISLNK(old_pfile_st.st_mode):
				try:
					# Read symlink target as bytes, in case the
					# target path has a bad encoding.
					pfile_link = os.readlink(_unicode_encode(old_pfile,
						encoding=_encodings['merge'], errors='strict'))
				except OSError:
					if e.errno != errno.ENOENT:
						raise
				else:
					pfile_link = _unicode_decode(pfile_link,
						encoding=_encodings['merge'], errors='replace')
					if pfile_link == newmd5:
						return old_pfile
			else:
				try:
					last_pfile_md5 = \
						portage.checksum._perform_md5_merge(old_pfile)
				except FileNotFound:
					# The file suddenly disappeared or it's a
					# broken symlink.
					pass
				else:
					if last_pfile_md5 == newmd5:
						return old_pfile
	return new_pfile

def find_updated_config_files(target_root, config_protect):
	"""
	Return a tuple of configuration files that needs to be updated.
	The tuple contains lists organized like this:
		[protected_dir, file_list]
	If the protected config isn't a protected_dir but a procted_file, list is:
		[protected_file, None]
	If no configuration files needs to be updated, None is returned
	"""

	encoding = _encodings['fs']

	if config_protect:
		# directories with some protect files in them
		for x in config_protect:
			files = []

			x = os.path.join(target_root, x.lstrip(os.path.sep))
			if not os.access(x, os.W_OK):
				continue
			try:
				mymode = os.lstat(x).st_mode
			except OSError:
				continue

			if stat.S_ISLNK(mymode):
				# We want to treat it like a directory if it
				# is a symlink to an existing directory.
				try:
					real_mode = os.stat(x).st_mode
					if stat.S_ISDIR(real_mode):
						mymode = real_mode
				except OSError:
					pass

			if stat.S_ISDIR(mymode):
				mycommand = \
					"find '%s' -name '.*' -type d -prune -o -name '._cfg????_*'" % x
			else:
				mycommand = "find '%s' -maxdepth 1 -name '._cfg????_%s'" % \
						os.path.split(x.rstrip(os.path.sep))
			mycommand += " ! -name '.*~' ! -iname '.*.bak' -print0"
			cmd = shlex_split(mycommand)

			cmd = [_unicode_encode(arg, encoding=encoding, errors='strict')
				for arg in cmd]
			proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT)
			output = _unicode_decode(proc.communicate()[0], encoding=encoding)
			status = proc.wait()
			if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
				files = output.split('\0')
				# split always produces an empty string as the last element
				if files and not files[-1]:
					del files[-1]
				if files:
					if stat.S_ISDIR(mymode):
						yield (x, files)
					else:
						yield (x, None)

_ld_so_include_re = re.compile(r'^include\s+(\S.*)')

def getlibpaths(root, env=None):
	def read_ld_so_conf(path):
		for l in grabfile(path):
			include_match = _ld_so_include_re.match(l)
			if include_match is not None:
				subpath = os.path.join(os.path.dirname(path),
					include_match.group(1))
				for p in glob.glob(subpath):
					for r in read_ld_so_conf(p):
						yield r
			else:
				yield l

	""" Return a list of paths that are used for library lookups """
	if env is None:
		env = os.environ
	# the following is based on the information from ld.so(8)
	rval = env.get("LD_LIBRARY_PATH", "").split(":")
	rval.extend(read_ld_so_conf(os.path.join(root, "etc", "ld.so.conf")))
	rval.append("/usr/lib")
	rval.append("/lib")

	return [normalize_path(x) for x in rval if x]
