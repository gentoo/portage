# Copyright 2010-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os as _os
import re

from portage import _unicode_decode
from portage.exception import InvalidData

#########################################################
#	This an re-implementaion of dev-util/lafilefixer-0.5.
#	rewrite_lafile() takes the contents of an lafile as a string
#	It then parses the dependency_libs and inherited_linker_flags
#	entries.
#	We insist on dependency_libs being present. inherited_linker_flags
#	is optional.
#	There are strict rules about the syntax imposed by libtool's libltdl.
#	See 'parse_dotla_file' and 'trim' functions in libltdl/ltdl.c.
#	Note that duplicated entries of dependency_libs and inherited_linker_flags
#	are ignored by libtool (last one wins), but we treat it as error (like
#	lafilefixer does).
#	What it does:
#		* Replaces all .la files with absolut paths in dependency_libs with
#		  corresponding -l* and -L* entries
#		  (/usr/lib64/libfoo.la -> -L/usr/lib64 -lfoo)
#		* Moves various flags (see flag_re below) to inherited_linker_flags,
#		  if such an entry was present.
#		* Reorders dependency_libs such that all -R* entries precede -L* entries
#		  and these precede all other entries.
#		* Remove duplicated entries from dependency_libs
#		* Takes care that no entry to inherited_linker_flags is added that is
#		  already there.
#########################################################

#These regexes are used to parse the interesting entries in the la file
dep_libs_re = re.compile(b"dependency_libs='(?P<value>[^']*)'$")
inh_link_flags_re = re.compile(b"inherited_linker_flags='(?P<value>[^']*)'$")

#regexes for replacing stuff in -L entries.
#replace 'X11R6/lib' and 'local/lib' with 'lib', no idea what's this about.
X11_local_sub = re.compile(b"X11R6/lib|local/lib")
#get rid of the '..'
pkgconfig_sub1 = re.compile(br"usr/lib[^/]*/pkgconfig/\.\./\.\.")
pkgconfig_sub2 = re.compile(br"(?P<usrlib>usr/lib[^/]*)/pkgconfig/\.\.")

#detect flags that should go into inherited_linker_flags instead of dependency_libs
flag_re = re.compile(b"-mt|-mthreads|-kthread|-Kthread|-pthread|-pthreads|--thread-safe|-threads")

def _parse_lafile_contents(contents):
	"""
	Parses 'dependency_libs' and 'inherited_linker_flags' lines.
	"""

	dep_libs = None
	inh_link_flags = None

	for line in contents.split(b"\n"):
		m = dep_libs_re.match(line)
		if m:
			if dep_libs is not None:
				raise InvalidData("duplicated dependency_libs entry")
			dep_libs = m.group("value")
			continue

		m = inh_link_flags_re.match(line)
		if m:
			if inh_link_flags is not None:
				raise InvalidData("duplicated inherited_linker_flags entry")
			inh_link_flags = m.group("value")
			continue

	return dep_libs, inh_link_flags

def rewrite_lafile(contents):
	"""
	Given the contents of an .la file, parse and fix it.
	This operates with strings of raw bytes (assumed to contain some ascii
	characters), in order to avoid any potential character encoding issues.
	Raises 'InvalidData' if the .la file is invalid.
	@param contents: the contents of a libtool archive file
	@type contents: bytes
	@rtype: tuple
	@return: (True, fixed_contents) if something needed to be
		fixed, (False, None) otherwise.
	"""
	#Parse the 'dependency_libs' and 'inherited_linker_flags' lines.
	dep_libs, inh_link_flags = \
		_parse_lafile_contents(contents)

	if dep_libs is None:
		raise InvalidData("missing or invalid dependency_libs")

	new_dep_libs = []
	new_inh_link_flags = []
	librpath = []
	libladir = []

	if inh_link_flags is not None:
		new_inh_link_flags = inh_link_flags.split()

	#Check entries in 'dependency_libs'.
	for dep_libs_entry in dep_libs.split():
		if dep_libs_entry.startswith(b"-l"):
			#-lfoo, keep it
			if dep_libs_entry not in new_dep_libs:
				new_dep_libs.append(dep_libs_entry)

		elif dep_libs_entry.endswith(b".la"):
			#Two cases:
			#1) /usr/lib64/libfoo.la, turn it into -lfoo and append -L/usr/lib64 to libladir
			#2) libfoo.la, keep it
			dirname, basename = _os.path.split(dep_libs_entry)

			if not dirname or not basename.startswith(b"lib"):
				if dep_libs_entry not in new_dep_libs:
					new_dep_libs.append(dep_libs_entry)
			else:
				#/usr/lib64/libfoo.la -> -lfoo
				lib = b"-l" + basename[3:-3]
				if lib not in new_dep_libs:
					new_dep_libs.append(lib)
				#/usr/lib64/libfoo.la -> -L/usr/lib64
				ladir = b"-L" + dirname
				if ladir not in libladir:
					libladir.append(ladir)

		elif dep_libs_entry.startswith(b"-L"):
			#Do some replacement magic and store them in 'libladir'.
			#This allows us to place all -L entries at the beginning
			#of 'dependency_libs'.
			ladir = dep_libs_entry

			ladir = X11_local_sub.sub(b"lib", ladir)
			ladir = pkgconfig_sub1.sub(b"usr", ladir)
			ladir = pkgconfig_sub2.sub(br"\g<usrlib>", ladir)

			if ladir not in libladir:
				libladir.append(ladir)

		elif dep_libs_entry.startswith(b"-R"):
			if dep_libs_entry not in librpath:
				librpath.append(dep_libs_entry)

		elif flag_re.match(dep_libs_entry):
			#All this stuff goes into inh_link_flags, if the la file has such an entry.
			#If it doesn't, they stay in 'dependency_libs'.
			if inh_link_flags is not None:
				if dep_libs_entry not in new_inh_link_flags:
					new_inh_link_flags.append(dep_libs_entry)
			else:
				if dep_libs_entry not in new_dep_libs:
					new_dep_libs.append(dep_libs_entry)

		else:
			raise InvalidData("Error: Unexpected entry '%s' in 'dependency_libs'" \
				% _unicode_decode(dep_libs_entry))

	#What should 'dependency_libs' and 'inherited_linker_flags' look like?
	expected_dep_libs = b""
	for x in (librpath, libladir, new_dep_libs):
		if x:
			expected_dep_libs += b" " + b" ".join(x)

	expected_inh_link_flags = b""
	if new_inh_link_flags:
		expected_inh_link_flags += b" " + b" ".join(new_inh_link_flags)

	#Don't touch the file if we don't need to, otherwise put the expected values into
	#'contents' and write it into the la file.

	changed = False
	if dep_libs != expected_dep_libs:
		contents = contents.replace(b"dependency_libs='" + dep_libs + b"'", \
			b"dependency_libs='" + expected_dep_libs + b"'")
		changed = True

	if inh_link_flags is not None and expected_inh_link_flags != inh_link_flags:
		contents = contents.replace(b"inherited_linker_flags='" + inh_link_flags + b"'", \
			b"inherited_linker_flags='" + expected_inh_link_flags + b"'")
		changed = True

	if changed:
		return True, contents
	return False, None
