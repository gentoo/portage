#!/usr/bin/python -O
# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: emerge 5976 2007-02-17 09:14:53Z genone $

import sys
# This block ensures that ^C interrupts are handled quietly.
try:
	import signal

	def exithandler(signum,frame):
		signal.signal(signal.SIGINT, signal.SIG_IGN)
		signal.signal(signal.SIGTERM, signal.SIG_IGN)
		sys.exit(1)
	
	signal.signal(signal.SIGINT, exithandler)
	signal.signal(signal.SIGTERM, exithandler)
	signal.signal(signal.SIGPIPE, signal.SIG_DFL)

except KeyboardInterrupt:
	sys.exit(1)

import array
import fcntl
import select
import shlex
import urlparse
import weakref
import gc
import os, stat
import platform

os.environ["PORTAGE_LEGACY_GLOBALS"] = "false"
try:
	import portage
except ImportError:
	from os import path as osp
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), "pym"))
	import portage
del os.environ["PORTAGE_LEGACY_GLOBALS"]
from portage import digraph, portdbapi
from portage.const import NEWS_LIB_PATH, CACHE_PATH, PRIVATE_PATH, USER_CONFIG_PATH, GLOBAL_CONFIG_PATH

import _emerge.help
import portage.xpak, commands, errno, re, socket, time, types
from portage.output import blue, bold, colorize, darkblue, darkgreen, darkred, green, \
	havecolor, nc_len, nocolor, red, teal, turquoise, white, xtermTitle, \
	xtermTitleReset, yellow
from portage.output import create_color_func
good = create_color_func("GOOD")
bad = create_color_func("BAD")
# white looks bad on terminals with white background
from portage.output import bold as white

import portage.elog
import portage.dep
portage.dep._dep_check_strict = True
import portage.util
import portage.locks
import portage.exception
from portage.data import secpass
from portage.elog.messages import eerror
from portage.util import normalize_path as normpath
from portage.util import writemsg
from portage.sets import load_default_config, SETPREFIX
from portage.sets.base import InternalPackageSet

from itertools import chain, izip
from UserDict import DictMixin

try:
	import cPickle
except ImportError:
	import pickle as cPickle

class stdout_spinner(object):
	scroll_msgs = [
		"Gentoo Rocks ("+platform.system()+")",
		"Thank you for using Gentoo. :)",
		"Are you actually trying to read this?",
		"How many times have you stared at this?",
		"We are generating the cache right now",
		"You are paying too much attention.",
		"A theory is better than its explanation.",
		"Phasers locked on target, Captain.",
		"Thrashing is just virtual crashing.",
		"To be is to program.",
		"Real Users hate Real Programmers.",
		"When all else fails, read the instructions.",
		"Functionality breeds Contempt.",
		"The future lies ahead.",
		"3.1415926535897932384626433832795028841971694",
		"Sometimes insanity is the only alternative.",
		"Inaccuracy saves a world of explanation.",
	]

	twirl_sequence = "/-\\|/-\\|/-\\|/-\\|\\-/|\\-/|\\-/|\\-/|"

	def __init__(self):
		self.spinpos = 0
		self.update = self.update_twirl
		self.scroll_sequence = self.scroll_msgs[
			int(time.time() * 100) % len(self.scroll_msgs)]
		self.last_update = 0
		self.min_display_latency = 0.05

	def _return_early(self):
		"""
		Flushing ouput to the tty too frequently wastes cpu time. Therefore,
		each update* method should return without doing any output when this
		method returns True.
		"""
		cur_time = time.time()
		if cur_time - self.last_update < self.min_display_latency:
			return True
		self.last_update = cur_time
		return False

	def update_basic(self):
		self.spinpos = (self.spinpos + 1) % 500
		if self._return_early():
			return
		if (self.spinpos % 100) == 0:
			if self.spinpos == 0:
				sys.stdout.write(". ")
			else:
				sys.stdout.write(".")
		sys.stdout.flush()

	def update_scroll(self):
		if self._return_early():
			return
		if(self.spinpos >= len(self.scroll_sequence)):
			sys.stdout.write(darkgreen(" \b\b\b" + self.scroll_sequence[
				len(self.scroll_sequence) - 1 - (self.spinpos % len(self.scroll_sequence))]))
		else:
			sys.stdout.write(green("\b " + self.scroll_sequence[self.spinpos]))
		sys.stdout.flush()
		self.spinpos = (self.spinpos + 1) % (2 * len(self.scroll_sequence))

	def update_twirl(self):
		self.spinpos = (self.spinpos + 1) % len(self.twirl_sequence)
		if self._return_early():
			return
		sys.stdout.write("\b\b " + self.twirl_sequence[self.spinpos])
		sys.stdout.flush()

	def update_quiet(self):
		return

def userquery(prompt, responses=None, colours=None):
	"""Displays a prompt and a set of responses, then waits for a response
	which is checked against the responses and the first to match is
	returned.  An empty response will match the first value in responses.  The
	input buffer is *not* cleared prior to the prompt!

	prompt: a String.
	responses: a List of Strings.
	colours: a List of Functions taking and returning a String, used to
	process the responses for display. Typically these will be functions
	like red() but could be e.g. lambda x: "DisplayString".
	If responses is omitted, defaults to ["Yes", "No"], [green, red].
	If only colours is omitted, defaults to [bold, ...].

	Returns a member of the List responses. (If called without optional
	arguments, returns "Yes" or "No".)
	KeyboardInterrupt is converted to SystemExit to avoid tracebacks being
	printed."""
	if responses is None:
		responses = ["Yes", "No"]
		colours = [
			create_color_func("PROMPT_CHOICE_DEFAULT"),
			create_color_func("PROMPT_CHOICE_OTHER")
		]
	elif colours is None:
		colours=[bold]
	colours=(colours*len(responses))[:len(responses)]
	print bold(prompt),
	try:
		while True:
			response=raw_input("["+"/".join([colours[i](responses[i]) for i in range(len(responses))])+"] ")
			for key in responses:
				# An empty response will match the first value in responses.
				if response.upper()==key[:len(response)].upper():
					return key
			print "Sorry, response '%s' not understood." % response,
	except (EOFError, KeyboardInterrupt):
		print "Interrupted."
		sys.exit(1)

actions=[
"clean", "config", "depclean",
"info", "metadata",
"prune", "regen",  "search",
"sync",  "unmerge",
]
options=[
"--ask",          "--alphabetical",
"--buildpkg",     "--buildpkgonly",
"--changelog",    "--columns",
"--complete-graph",
"--debug",        "--deep",
"--digest",
"--emptytree",
"--fetchonly",    "--fetch-all-uri",
"--getbinpkg",    "--getbinpkgonly",
"--help",         "--ignore-default-opts",
"--keep-going",
"--noconfmem",
"--newuse",       "--nocolor",
"--nodeps",       "--noreplace",
"--nospinner",    "--oneshot",
"--onlydeps",     "--pretend",
"--quiet",        "--resume",
"--searchdesc",   "--selective",
"--skipfirst",
"--tree",
"--update",
"--usepkg",       "--usepkgonly",
"--verbose",      "--version"
]

shortmapping={
"1":"--oneshot",
"a":"--ask",
"b":"--buildpkg",  "B":"--buildpkgonly",
"c":"--clean",     "C":"--unmerge",
"d":"--debug",     "D":"--deep",
"e":"--emptytree",
"f":"--fetchonly", "F":"--fetch-all-uri",
"g":"--getbinpkg", "G":"--getbinpkgonly",
"h":"--help",
"k":"--usepkg",    "K":"--usepkgonly",
"l":"--changelog",
"n":"--noreplace", "N":"--newuse",
"o":"--onlydeps",  "O":"--nodeps",
"p":"--pretend",   "P":"--prune",
"q":"--quiet",
"s":"--search",    "S":"--searchdesc",
"t":"--tree",
"u":"--update",
"v":"--verbose",   "V":"--version"
}

def emergelog(xterm_titles, mystr, short_msg=None):
	if xterm_titles:
		if short_msg == None:
			short_msg = mystr
		if "HOSTNAME" in os.environ:
			short_msg = os.environ["HOSTNAME"]+": "+short_msg
		xtermTitle(short_msg)
	try:
		file_path = "/var/log/emerge.log"
		mylogfile = open(file_path, "a")
		portage.util.apply_secpass_permissions(file_path,
			uid=portage.portage_uid, gid=portage.portage_gid,
			mode=0660)
		mylock = None
		try:
			mylock = portage.locks.lockfile(mylogfile)
			# seek because we may have gotten held up by the lock.
			# if so, we may not be positioned at the end of the file.
			mylogfile.seek(0, 2)
			mylogfile.write(str(time.time())[:10]+": "+mystr+"\n")
			mylogfile.flush()
		finally:
			if mylock:
				portage.locks.unlockfile(mylock)
			mylogfile.close()
	except (IOError,OSError,portage.exception.PortageException), e:
		if secpass >= 1:
			print >> sys.stderr, "emergelog():",e

def countdown(secs=5, doing="Starting"):
	if secs:
		print ">>> Waiting",secs,"seconds before starting..."
		print ">>> (Control-C to abort)...\n"+doing+" in: ",
		ticks=range(secs)
		ticks.reverse()
		for sec in ticks:
			sys.stdout.write(colorize("UNMERGE_WARN", str(sec+1)+" "))
			sys.stdout.flush()
			time.sleep(1)
		print

# formats a size given in bytes nicely
def format_size(mysize):
	if type(mysize) not in [types.IntType,types.LongType]:
		return str(mysize)
	if 0 != mysize % 1024:
		# Always round up to the next kB so that it doesn't show 0 kB when
		# some small file still needs to be fetched.
		mysize += 1024 - mysize % 1024
	mystr=str(mysize/1024)
	mycount=len(mystr)
	while (mycount > 3):
		mycount-=3
		mystr=mystr[:mycount]+","+mystr[mycount:]
	return mystr+" kB"


def getgccversion(chost):
	"""
	rtype: C{str}
	return:  the current in-use gcc version
	"""

	gcc_ver_command = 'gcc -dumpversion'
	gcc_ver_prefix = 'gcc-'

	gcc_not_found_error = red(
	"!!! No gcc found. You probably need to 'source /etc/profile'\n" +
	"!!! to update the environment of this terminal and possibly\n" +
	"!!! other terminals also.\n"
	)

	mystatus, myoutput = commands.getstatusoutput("gcc-config -c")
	if mystatus == os.EX_OK and myoutput.startswith(chost + "-"):
		return myoutput.replace(chost + "-", gcc_ver_prefix, 1)

	mystatus, myoutput = commands.getstatusoutput(
		chost + "-" + gcc_ver_command)
	if mystatus == os.EX_OK:
		return gcc_ver_prefix + myoutput

	mystatus, myoutput = commands.getstatusoutput(gcc_ver_command)
	if mystatus == os.EX_OK:
		return gcc_ver_prefix + myoutput

	portage.writemsg(gcc_not_found_error, noiselevel=-1)
	return "[unavailable]"

def getportageversion(portdir, target_root, profile, chost, vardb):
	profilever = "unavailable"
	if profile:
		realpath = os.path.realpath(profile)
		basepath   = os.path.realpath(os.path.join(portdir, "profiles"))
		if realpath.startswith(basepath):
			profilever = realpath[1 + len(basepath):]
		else:
			try:
				profilever = "!" + os.readlink(profile)
			except (OSError):
				pass
		del realpath, basepath

	libcver=[]
	libclist  = vardb.match("virtual/libc")
	libclist += vardb.match("virtual/glibc")
	libclist  = portage.util.unique_array(libclist)
	for x in libclist:
		xs=portage.catpkgsplit(x)
		if libcver:
			libcver+=","+"-".join(xs[1:])
		else:
			libcver="-".join(xs[1:])
	if libcver==[]:
		libcver="unavailable"

	gccver = getgccversion(chost)
	unameout=platform.release()+" "+platform.machine()

	return "Portage " + portage.VERSION +" ("+profilever+", "+gccver+", "+libcver+", "+unameout+")"

def create_depgraph_params(myopts, myaction):
	#configure emerge engine parameters
	#
	# self:      include _this_ package regardless of if it is merged.
	# selective: exclude the package if it is merged
	# recurse:   go into the dependencies
	# deep:      go into the dependencies of already merged packages
	# empty:     pretend nothing is merged
	# complete:  completely account for all known dependencies
	myparams = set(["recurse"])
	if "--update" in myopts or \
		"--newuse" in myopts or \
		"--reinstall" in myopts or \
		"--noreplace" in myopts:
		myparams.add("selective")
	if "--emptytree" in myopts:
		myparams.add("empty")
		myparams.discard("selective")
	if "--nodeps" in myopts:
		myparams.discard("recurse")
	if "--deep" in myopts:
		myparams.add("deep")
	if "--complete-graph" in myopts:
		myparams.add("complete")
	return myparams

# search functionality
class search(object):

	#
	# class constants
	#
	VERSION_SHORT=1
	VERSION_RELEASE=2

	#
	# public interface
	#
	def __init__(self, root_config, spinner, searchdesc,
		verbose, usepkg, usepkgonly):
		"""Searches the available and installed packages for the supplied search key.
		The list of available and installed packages is created at object instantiation.
		This makes successive searches faster."""
		self.settings = root_config.settings
		self.vartree = root_config.trees["vartree"]
		self.spinner = spinner
		self.verbose = verbose
		self.searchdesc = searchdesc
		self.root_config = root_config
		self.setconfig = root_config.setconfig

		def fake_portdb():
			pass
		self.portdb = fake_portdb
		for attrib in ("aux_get", "cp_all",
			"xmatch", "findname", "getfetchlist"):
			setattr(fake_portdb, attrib, getattr(self, "_"+attrib))

		self._dbs = []

		portdb = root_config.trees["porttree"].dbapi
		bindb = root_config.trees["bintree"].dbapi
		vardb = root_config.trees["vartree"].dbapi

		if not usepkgonly and portdb._have_root_eclass_dir:
			self._dbs.append(portdb)

		if (usepkg or usepkgonly) and bindb.cp_all():
			self._dbs.append(bindb)

		self._dbs.append(vardb)
		self._portdb = portdb

	def _cp_all(self):
		cp_all = set()
		for db in self._dbs:
			cp_all.update(db.cp_all())
		return list(sorted(cp_all))

	def _aux_get(self, *args, **kwargs):
		for db in self._dbs:
			try:
				return db.aux_get(*args, **kwargs)
			except KeyError:
				pass
		raise

	def _findname(self, *args, **kwargs):
		for db in self._dbs:
			if db is not self._portdb:
				# We don't want findname to return anything
				# unless it's an ebuild in a portage tree.
				# Otherwise, it's already built and we don't
				# care about it.
				continue
			func = getattr(db, "findname", None)
			if func:
				value = func(*args, **kwargs)
				if value:
					return value
		return None

	def _getfetchlist(self, *args, **kwargs):
		for db in self._dbs:
			func = getattr(db, "getfetchlist", None)
			if func:
				value = func(*args, **kwargs)
				if value:
					return value
		return [], []

	def _visible(self, db, cpv, metadata):
		installed = db is self.vartree.dbapi
		built = installed or db is not self._portdb
		pkg_type = "ebuild"
		if installed:
			pkg_type = "installed"
		elif built:
			pkg_type = "binary"
		return visible(self.settings,
			Package(type_name=pkg_type, root_config=self.root_config,
			cpv=cpv, built=built, installed=installed, metadata=metadata))

	def _xmatch(self, level, atom):
		"""
		This method does not expand old-style virtuals because it
		is restricted to returning matches for a single ${CATEGORY}/${PN}
		and old-style virual matches unreliable for that when querying
		multiple package databases. If necessary, old-style virtuals
		can be performed on atoms prior to calling this method.
		"""
		cp = portage.dep_getkey(atom)
		if level == "match-all":
			matches = set()
			for db in self._dbs:
				if hasattr(db, "xmatch"):
					matches.update(db.xmatch(level, atom))
				else:
					matches.update(db.match(atom))
			result = list(x for x in matches if portage.cpv_getkey(x) == cp)
			db._cpv_sort_ascending(result)
		elif level == "match-visible":
			matches = set()
			for db in self._dbs:
				if hasattr(db, "xmatch"):
					matches.update(db.xmatch(level, atom))
				else:
					db_keys = list(db._aux_cache_keys)
					for cpv in db.match(atom):
						metadata = izip(db_keys,
							db.aux_get(cpv, db_keys))
						if not self._visible(db, cpv, metadata):
							continue
						matches.add(cpv)
			result = list(x for x in matches if portage.cpv_getkey(x) == cp)
			db._cpv_sort_ascending(result)
		elif level == "bestmatch-visible":
			result = None
			for db in self._dbs:
				if hasattr(db, "xmatch"):
					cpv = db.xmatch("bestmatch-visible", atom)
					if not cpv or portage.cpv_getkey(cpv) != cp:
						continue
					if not result or cpv == portage.best([cpv, result]):
						result = cpv
				else:
					db_keys = list(db._aux_cache_keys)
					# break out of this loop with highest visible
					# match, checked in descending order
					for cpv in reversed(db.match(atom)):
						if portage.cpv_getkey(cpv) != cp:
							continue
						metadata = izip(db_keys,
							db.aux_get(cpv, db_keys))
						if not self._visible(db, cpv, metadata):
							continue
						if not result or cpv == portage.best([cpv, result]):
							result = cpv
						break
		else:
			raise NotImplementedError(level)
		return result

	def execute(self,searchkey):
		"""Performs the search for the supplied search key"""
		match_category = 0
		self.searchkey=searchkey
		self.packagematches = []
		if self.searchdesc:
			self.searchdesc=1
			self.matches = {"pkg":[], "desc":[], "set":[]}
		else:
			self.searchdesc=0
			self.matches = {"pkg":[], "set":[]}
		print "Searching...   ",

		regexsearch = False
		if self.searchkey.startswith('%'):
			regexsearch = True
			self.searchkey = self.searchkey[1:]
		if self.searchkey.startswith('@'):
			match_category = 1
			self.searchkey = self.searchkey[1:]
		if regexsearch:
			self.searchre=re.compile(self.searchkey,re.I)
		else:
			self.searchre=re.compile(re.escape(self.searchkey), re.I)
		for package in self.portdb.cp_all():
			self.spinner.update()

			if match_category:
				match_string  = package[:]
			else:
				match_string  = package.split("/")[-1]

			masked=0
			if self.searchre.search(match_string):
				if not self.portdb.xmatch("match-visible", package):
					masked=1
				self.matches["pkg"].append([package,masked])
			elif self.searchdesc: # DESCRIPTION searching
				full_package = self.portdb.xmatch("bestmatch-visible", package)
				if not full_package:
					#no match found; we don't want to query description
					full_package = portage.best(
						self.portdb.xmatch("match-all", package))
					if not full_package:
						continue
					else:
						masked=1
				try:
					full_desc = self.portdb.aux_get(
						full_package, ["DESCRIPTION"])[0]
				except KeyError:
					print "emerge: search: aux_get() failed, skipping"
					continue
				if self.searchre.search(full_desc):
					self.matches["desc"].append([full_package,masked])

		self.sdict = self.setconfig.getSets()
		for setname in self.sdict:
			self.spinner.update()
			if match_category:
				match_string = setname
			else:
				match_string = setname.split("/")[-1]
			
			if self.searchre.search(match_string):
				self.matches["set"].append([setname, False])
			elif self.searchdesc:
				if self.searchre.search(
					self.sdict[setname].getMetadata("DESCRIPTION")):
					self.matches["set"].append([setname, False])
			
		self.mlen=0
		for mtype in self.matches:
			self.matches[mtype].sort()
			self.mlen += len(self.matches[mtype])

	def output(self):
		"""Outputs the results of the search."""
		print "\b\b  \n[ Results for search key : "+white(self.searchkey)+" ]"
		print "[ Applications found : "+white(str(self.mlen))+" ]"
		print " "
		vardb = self.vartree.dbapi
		for mtype in self.matches:
			for match,masked in self.matches[mtype]:
				full_package = None
				if mtype == "pkg":
					catpack = match
					full_package = self.portdb.xmatch(
						"bestmatch-visible", match)
					if not full_package:
						#no match found; we don't want to query description
						masked=1
						full_package = portage.best(
							self.portdb.xmatch("match-all",match))
				elif mtype == "desc":
					full_package = match
					match        = portage.cpv_getkey(match)
				elif mtype == "set":
					print green("*")+"  "+white(match)
					print "     ", darkgreen("Description:")+"  ", self.sdict[match].getMetadata("DESCRIPTION")
					print
				if full_package:
					try:
						desc, homepage, license = self.portdb.aux_get(
							full_package, ["DESCRIPTION","HOMEPAGE","LICENSE"])
					except KeyError:
						print "emerge: search: aux_get() failed, skipping"
						continue
					if masked:
						print green("*")+"  "+white(match)+" "+red("[ Masked ]")
					else:
						print green("*")+"  "+white(match)
					myversion = self.getVersion(full_package, search.VERSION_RELEASE)

					mysum = [0,0]
					file_size_str = None
					mycat = match.split("/")[0]
					mypkg = match.split("/")[1]
					mycpv = match + "-" + myversion
					myebuild = self.portdb.findname(mycpv)
					if myebuild:
						pkgdir = os.path.dirname(myebuild)
						from portage import manifest
						mf = manifest.Manifest(
							pkgdir, self.settings["DISTDIR"])
						fetchlist = self.portdb.getfetchlist(mycpv,
							mysettings=self.settings, all=True)[1]
						try:
							mysum[0] = mf.getDistfilesSize(fetchlist)
						except KeyError, e:
							file_size_str = "Unknown (missing digest for %s)" % \
								str(e)

					available = False
					for db in self._dbs:
						if db is not vardb and \
							db.cpv_exists(mycpv):
							available = True
							if not myebuild and hasattr(db, "bintree"):
								myebuild = db.bintree.getname(mycpv)
								try:
									mysum[0] = os.stat(myebuild).st_size
								except OSError:
									myebuild = None
							break

					if myebuild and file_size_str is None:
						mystr = str(mysum[0] / 1024)
						mycount = len(mystr)
						while (mycount > 3):
							mycount -= 3
							mystr = mystr[:mycount] + "," + mystr[mycount:]
						file_size_str = mystr + " kB"

					if self.verbose:
						if available:
							print "     ", darkgreen("Latest version available:"),myversion
						print "     ", self.getInstallationStatus(mycat+'/'+mypkg)
						if myebuild:
							print "      %s %s" % \
								(darkgreen("Size of files:"), file_size_str)
						print "     ", darkgreen("Homepage:")+"     ",homepage
						print "     ", darkgreen("Description:")+"  ",desc
						print "     ", darkgreen("License:")+"      ",license
						print
		print
	#
	# private interface
	#
	def getInstallationStatus(self,package):
		installed_package = self.vartree.dep_bestmatch(package)
		result = ""
		version = self.getVersion(installed_package,search.VERSION_RELEASE)
		if len(version) > 0:
			result = darkgreen("Latest version installed:")+" "+version
		else:
			result = darkgreen("Latest version installed:")+" [ Not Installed ]"
		return result

	def getVersion(self,full_package,detail):
		if len(full_package) > 1:
			package_parts = portage.catpkgsplit(full_package)
			if detail == search.VERSION_RELEASE and package_parts[3] != 'r0':
				result = package_parts[2]+ "-" + package_parts[3]
			else:
				result = package_parts[2]
		else:
			result = ""
		return result

class RootConfig(object):
	"""This is used internally by depgraph to track information about a
	particular $ROOT."""
	def __init__(self, settings, trees, setconfig):
		self.trees = trees
		self.settings = settings
		self.iuse_implicit = tuple(sorted(settings._get_implicit_iuse()))
		self.root = self.settings["ROOT"]
		self.setconfig = setconfig
		self.sets = self.setconfig.getSets()
		self.visible_pkgs = PackageVirtualDbapi(self.settings)

def create_world_atom(pkg, args_set, root_config):
	"""Create a new atom for the world file if one does not exist.  If the
	argument atom is precise enough to identify a specific slot then a slot
	atom will be returned. Atoms that are in the system set may also be stored
	in world since system atoms can only match one slot while world atoms can
	be greedy with respect to slots.  Unslotted system packages will not be
	stored in world."""

	arg_atom = args_set.findAtomForPackage(pkg)
	if not arg_atom:
		return None
	cp = portage.dep_getkey(arg_atom)
	new_world_atom = cp
	sets = root_config.sets
	portdb = root_config.trees["porttree"].dbapi
	vardb = root_config.trees["vartree"].dbapi
	available_slots = set(portdb.aux_get(cpv, ["SLOT"])[0] \
		for cpv in portdb.match(cp))
	slotted = len(available_slots) > 1 or \
		(len(available_slots) == 1 and "0" not in available_slots)
	if not slotted:
		# check the vdb in case this is multislot
		available_slots = set(vardb.aux_get(cpv, ["SLOT"])[0] \
			for cpv in vardb.match(cp))
		slotted = len(available_slots) > 1 or \
			(len(available_slots) == 1 and "0" not in available_slots)
	if slotted and arg_atom != cp:
		# If the user gave a specific atom, store it as a
		# slot atom in the world file.
		slot_atom = pkg.slot_atom

		# For USE=multislot, there are a couple of cases to
		# handle here:
		#
		# 1) SLOT="0", but the real SLOT spontaneously changed to some
		#    unknown value, so just record an unslotted atom.
		#
		# 2) SLOT comes from an installed package and there is no
		#    matching SLOT in the portage tree.
		#
		# Make sure that the slot atom is available in either the
		# portdb or the vardb, since otherwise the user certainly
		# doesn't want the SLOT atom recorded in the world file
		# (case 1 above).  If it's only available in the vardb,
		# the user may be trying to prevent a USE=multislot
		# package from being removed by --depclean (case 2 above).

		mydb = portdb
		if not portdb.match(slot_atom):
			# SLOT seems to come from an installed multislot package
			mydb = vardb
		# If there is no installed package matching the SLOT atom,
		# it probably changed SLOT spontaneously due to USE=multislot,
		# so just record an unslotted atom.
		if vardb.match(slot_atom):
			# Now verify that the argument is precise
			# enough to identify a specific slot.
			matches = mydb.match(arg_atom)
			matched_slots = set()
			for cpv in matches:
				matched_slots.add(mydb.aux_get(cpv, ["SLOT"])[0])
			if len(matched_slots) == 1:
				new_world_atom = slot_atom

	if new_world_atom == sets["world"].findAtomForPackage(pkg):
		# Both atoms would be identical, so there's nothing to add.
		return None
	if not slotted:
		# Unlike world atoms, system atoms are not greedy for slots, so they
		# can't be safely excluded from world if they are slotted.
		system_atom = sets["system"].findAtomForPackage(pkg)
		if system_atom:
			if not portage.dep_getkey(system_atom).startswith("virtual/"):
				return None
			# System virtuals aren't safe to exclude from world since they can
			# match multiple old-style virtuals but only one of them will be
			# pulled in by update or depclean.
			providers = portdb.mysettings.getvirtuals().get(
				portage.dep_getkey(system_atom))
			if providers and len(providers) == 1 and providers[0] == cp:
				return None
	return new_world_atom

def filter_iuse_defaults(iuse):
	for flag in iuse:
		if flag.startswith("+") or flag.startswith("-"):
			yield flag[1:]
		else:
			yield flag

class SlotObject(object):
	__slots__ = ("__weakref__",)

	def __init__(self, **kwargs):
		classes = [self.__class__]
		while classes:
			c = classes.pop()
			if c is SlotObject:
				continue
			classes.extend(c.__bases__)
			slots = getattr(c, "__slots__", None)
			if not slots:
				continue
			for myattr in slots:
				myvalue = kwargs.get(myattr, None)
				setattr(self, myattr, myvalue)

class AbstractDepPriority(SlotObject):
	__slots__ = ("buildtime", "runtime", "runtime_post")

	def __lt__(self, other):
		return self.__int__() < other

	def __le__(self, other):
		return self.__int__() <= other

	def __eq__(self, other):
		return self.__int__() == other

	def __ne__(self, other):
		return self.__int__() != other

	def __gt__(self, other):
		return self.__int__() > other

	def __ge__(self, other):
		return self.__int__() >= other

	def copy(self):
		import copy
		return copy.copy(self)

class DepPriority(AbstractDepPriority):
	"""
		This class generates an integer priority level based of various
		attributes of the dependency relationship.  Attributes can be assigned
		at any time and the new integer value will be generated on calls to the
		__int__() method.  Rich comparison operators are supported.

		The boolean attributes that affect the integer value are "satisfied",
		"buildtime", "runtime", and "system".  Various combinations of
		attributes lead to the following priority levels:

		Combination of properties           Priority  Category

		not satisfied and buildtime            0       HARD
		not satisfied and runtime             -1       MEDIUM
		not satisfied and runtime_post        -2       MEDIUM_SOFT
		satisfied and buildtime and rebuild   -3       SOFT
		satisfied and buildtime               -4       SOFT
		satisfied and runtime                 -5       SOFT
		satisfied and runtime_post            -6       SOFT
		(none of the above)                   -6       SOFT

		Several integer constants are defined for categorization of priority
		levels:

		MEDIUM   The upper boundary for medium dependencies.
		MEDIUM_SOFT   The upper boundary for medium-soft dependencies.
		SOFT     The upper boundary for soft dependencies.
		MIN      The lower boundary for soft dependencies.
	"""
	__slots__ = ("satisfied", "rebuild")
	MEDIUM = -1
	MEDIUM_SOFT = -2
	SOFT   = -3
	MIN    = -6

	def __int__(self):
		if not self.satisfied:
			if self.buildtime:
				return 0
			if self.runtime:
				return -1
			if self.runtime_post:
				return -2
		if self.buildtime:
			if self.rebuild:
				return -3
			return -4
		if self.runtime:
			return -5
		if self.runtime_post:
			return -6
		return -6

	def __str__(self):
		myvalue = self.__int__()
		if myvalue > self.MEDIUM:
			return "hard"
		if myvalue > self.MEDIUM_SOFT:
			return "medium"
		if myvalue > self.SOFT:
			return "medium-soft"
		return "soft"

class BlockerDepPriority(DepPriority):
	__slots__ = ()
	def __int__(self):
		return 0

BlockerDepPriority.instance = BlockerDepPriority()

class UnmergeDepPriority(AbstractDepPriority):
	__slots__ = ()
	"""
	Combination of properties           Priority  Category

	runtime                                0       HARD
	runtime_post                          -1       HARD
	buildtime                             -2       SOFT
	(none of the above)                   -2       SOFT
	"""

	MAX    =  0
	SOFT   = -2
	MIN    = -2

	def __int__(self):
		if self.runtime:
			return 0
		if self.runtime_post:
			return -1
		if self.buildtime:
			return -2
		return -2

	def __str__(self):
		myvalue = self.__int__()
		if myvalue > self.SOFT:
			return "hard"
		return "soft"

class FakeVartree(portage.vartree):
	"""This is implements an in-memory copy of a vartree instance that provides
	all the interfaces required for use by the depgraph.  The vardb is locked
	during the constructor call just long enough to read a copy of the
	installed package information.  This allows the depgraph to do it's
	dependency calculations without holding a lock on the vardb.  It also
	allows things like vardb global updates to be done in memory so that the
	user doesn't necessarily need write access to the vardb in cases where
	global updates are necessary (updates are performed when necessary if there
	is not a matching ebuild in the tree)."""
	def __init__(self, root_config, pkg_cache=None, acquire_lock=1):
		if pkg_cache is None:
			pkg_cache = {}
		real_vartree = root_config.trees["vartree"]
		portdb = root_config.trees["porttree"].dbapi
		self.root = real_vartree.root
		self.settings = real_vartree.settings
		mykeys = list(Package.metadata_keys)
		for required_key in ("COUNTER", "SLOT"):
			if required_key not in mykeys:
				mykeys.append(required_key)
		self._pkg_cache = pkg_cache
		self.dbapi = PackageVirtualDbapi(real_vartree.settings)
		vdb_path = os.path.join(self.root, portage.VDB_PATH)
		try:
			# At least the parent needs to exist for the lock file.
			portage.util.ensure_dirs(vdb_path)
		except portage.exception.PortageException:
			pass
		vdb_lock = None
		try:
			if acquire_lock and os.access(vdb_path, os.W_OK):
				vdb_lock = portage.locks.lockdir(vdb_path)
			real_dbapi = real_vartree.dbapi
			slot_counters = {}
			for cpv in real_dbapi.cpv_all():
				cache_key = ("installed", self.root, cpv, "nomerge")
				pkg = self._pkg_cache.get(cache_key)
				if pkg is not None:
					metadata = pkg.metadata
				else:
					metadata = dict(izip(mykeys, real_dbapi.aux_get(cpv, mykeys)))
				myslot = metadata["SLOT"]
				mycp = portage.dep_getkey(cpv)
				myslot_atom = "%s:%s" % (mycp, myslot)
				try:
					mycounter = long(metadata["COUNTER"])
				except ValueError:
					mycounter = 0
					metadata["COUNTER"] = str(mycounter)
				other_counter = slot_counters.get(myslot_atom, None)
				if other_counter is not None:
					if other_counter > mycounter:
						continue
				slot_counters[myslot_atom] = mycounter
				if pkg is None:
					pkg = Package(built=True, cpv=cpv,
						installed=True, metadata=metadata,
						root_config=root_config, type_name="installed")
				self._pkg_cache[pkg] = pkg
				self.dbapi.cpv_inject(pkg)
			real_dbapi.flush_cache()
		finally:
			if vdb_lock:
				portage.locks.unlockdir(vdb_lock)
		# Populate the old-style virtuals using the cached values.
		if not self.settings.treeVirtuals:
			self.settings.treeVirtuals = portage.util.map_dictlist_vals(
				portage.getCPFromCPV, self.get_all_provides())

		# Intialize variables needed for lazy cache pulls of the live ebuild
		# metadata.  This ensures that the vardb lock is released ASAP, without
		# being delayed in case cache generation is triggered.
		self._aux_get = self.dbapi.aux_get
		self.dbapi.aux_get = self._aux_get_wrapper
		self._match = self.dbapi.match
		self.dbapi.match = self._match_wrapper
		self._aux_get_history = set()
		self._portdb_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
		self._portdb = portdb
		self._global_updates = None

	def _match_wrapper(self, cpv, use_cache=1):
		"""
		Make sure the metadata in Package instances gets updated for any
		cpv that is returned from a match() call, since the metadata can
		be accessed directly from the Package instance instead of via
		aux_get().
		"""
		matches = self._match(cpv, use_cache=use_cache)
		for cpv in matches:
			if cpv in self._aux_get_history:
				continue
			self._aux_get_wrapper(cpv, [])
		return matches

	def _aux_get_wrapper(self, pkg, wants):
		if pkg in self._aux_get_history:
			return self._aux_get(pkg, wants)
		self._aux_get_history.add(pkg)
		try:
			# Use the live ebuild metadata if possible.
			live_metadata = dict(izip(self._portdb_keys,
				self._portdb.aux_get(pkg, self._portdb_keys)))
			self.dbapi.aux_update(pkg, live_metadata)
		except (KeyError, portage.exception.PortageException):
			if self._global_updates is None:
				self._global_updates = \
					grab_global_updates(self._portdb.porttree_root)
			perform_global_updates(
				pkg, self.dbapi, self._global_updates)
		return self._aux_get(pkg, wants)

def grab_global_updates(portdir):
	from portage.update import grab_updates, parse_updates
	updpath = os.path.join(portdir, "profiles", "updates")
	try:
		rawupdates = grab_updates(updpath)
	except portage.exception.DirectoryNotFound:
		rawupdates = []
	upd_commands = []
	for mykey, mystat, mycontent in rawupdates:
		commands, errors = parse_updates(mycontent)
		upd_commands.extend(commands)
	return upd_commands

def perform_global_updates(mycpv, mydb, mycommands):
	from portage.update import update_dbentries
	aux_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
	aux_dict = dict(izip(aux_keys, mydb.aux_get(mycpv, aux_keys)))
	updates = update_dbentries(mycommands, aux_dict)
	if updates:
		mydb.aux_update(mycpv, updates)

def visible(pkgsettings, pkg):
	"""
	Check if a package is visible. This can raise an InvalidDependString
	exception if LICENSE is invalid.
	TODO: optionally generate a list of masking reasons
	@rtype: Boolean
	@returns: True if the package is visible, False otherwise.
	"""
	if not pkg.metadata["SLOT"]:
		return False
	if pkg.built and not pkg.installed and "CHOST" in pkg.metadata:
		if not pkgsettings._accept_chost(pkg):
			return False
	if not portage.eapi_is_supported(pkg.metadata["EAPI"]):
		return False
	if not pkg.installed and \
		pkgsettings._getMissingKeywords(pkg.cpv, pkg.metadata):
		return False
	if pkgsettings._getMaskAtom(pkg.cpv, pkg.metadata):
		return False
	if pkgsettings._getProfileMaskAtom(pkg.cpv, pkg.metadata):
		return False
	try:
		if pkgsettings._getMissingLicenses(pkg.cpv, pkg.metadata):
			return False
	except portage.exception.InvalidDependString:
		return False
	return True

def get_masking_status(pkg, pkgsettings, root_config):

	mreasons = portage.getmaskingstatus(
		pkg, settings=pkgsettings,
		portdb=root_config.trees["porttree"].dbapi)

	if pkg.built and not pkg.installed and "CHOST" in pkg.metadata:
		if not pkgsettings._accept_chost(pkg):
			mreasons.append("CHOST: %s" % \
				pkg.metadata["CHOST"])

	if not pkg.metadata["SLOT"]:
		mreasons.append("invalid: SLOT is undefined")

	return mreasons

def get_mask_info(root_config, cpv, pkgsettings,
	db, pkg_type, built, installed, db_keys):
	eapi_masked = False
	try:
		metadata = dict(izip(db_keys,
			db.aux_get(cpv, db_keys)))
	except KeyError:
		metadata = None
	if metadata and not built:
		pkgsettings.setcpv(cpv, mydb=metadata)
		metadata["USE"] = pkgsettings["PORTAGE_USE"]
	if metadata is None:
		mreasons = ["corruption"]
	else:
		pkg = Package(type_name=pkg_type, root_config=root_config,
			cpv=cpv, built=built, installed=installed, metadata=metadata)
		mreasons = get_masking_status(pkg, pkgsettings, root_config)
	return metadata, mreasons

def show_masked_packages(masked_packages):
	shown_licenses = set()
	shown_comments = set()
	# Maybe there is both an ebuild and a binary. Only
	# show one of them to avoid redundant appearance.
	shown_cpvs = set()
	have_eapi_mask = False
	for (root_config, pkgsettings, cpv,
		metadata, mreasons) in masked_packages:
		if cpv in shown_cpvs:
			continue
		shown_cpvs.add(cpv)
		comment, filename = None, None
		if "package.mask" in mreasons:
			comment, filename = \
				portage.getmaskingreason(
				cpv, metadata=metadata,
				settings=pkgsettings,
				portdb=root_config.trees["porttree"].dbapi,
				return_location=True)
		missing_licenses = []
		if metadata:
			if not portage.eapi_is_supported(metadata["EAPI"]):
				have_eapi_mask = True
			try:
				missing_licenses = \
					pkgsettings._getMissingLicenses(
						cpv, metadata)
			except portage.exception.InvalidDependString:
				# This will have already been reported
				# above via mreasons.
				pass

		print "- "+cpv+" (masked by: "+", ".join(mreasons)+")"
		if comment and comment not in shown_comments:
			print filename+":"
			print comment
			shown_comments.add(comment)
		portdb = root_config.trees["porttree"].dbapi
		for l in missing_licenses:
			l_path = portdb.findLicensePath(l)
			if l in shown_licenses:
				continue
			msg = ("A copy of the '%s' license" + \
			" is located at '%s'.") % (l, l_path)
			print msg
			print
			shown_licenses.add(l)
	return have_eapi_mask

class Task(SlotObject):
	__slots__ = ("_hash_key", "_hash_value")

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			raise NotImplementedError(self)
		return hash_key

	def __eq__(self, other):
		return self._get_hash_key() == other

	def __ne__(self, other):
		return self._get_hash_key() != other

	def __hash__(self):
		hash_value = getattr(self, "_hash_value", None)
		if hash_value is None:
			self._hash_value = hash(self._get_hash_key())
		return self._hash_value

	def __len__(self):
		return len(self._get_hash_key())

	def __getitem__(self, key):
		return self._get_hash_key()[key]

	def __iter__(self):
		return iter(self._get_hash_key())

	def __contains__(self, key):
		return key in self._get_hash_key()

	def __str__(self):
		return str(self._get_hash_key())

class Blocker(Task):
	__slots__ = ("root", "atom", "cp", "satisfied")

	def __init__(self, **kwargs):
		Task.__init__(self, **kwargs)
		self.cp = portage.dep_getkey(self.atom)

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = \
				("blocks", self.root, self.atom)
		return self._hash_key

class Package(Task):
	__slots__ = ("built", "cpv", "depth",
		"installed", "metadata", "onlydeps", "operation",
		"root_config", "type_name",
		"category", "counter", "cp", "cpv_split",
		"inherited", "iuse", "mtime",
		"pf", "pv_split", "root", "slot", "slot_atom", "use")

	metadata_keys = [
		"CHOST", "COUNTER", "DEPEND", "EAPI", "IUSE", "KEYWORDS",
		"LICENSE", "PDEPEND", "PROVIDE", "RDEPEND",
		"repository", "RESTRICT", "SLOT", "USE", "_mtime_"]

	def __init__(self, **kwargs):
		Task.__init__(self, **kwargs)
		self.root = self.root_config.root
		self.metadata = _PackageMetadataWrapper(self, self.metadata)
		self.cp = portage.cpv_getkey(self.cpv)
		self.slot_atom = portage.dep.Atom("%s:%s" % (self.cp, self.slot))
		self.category, self.pf = portage.catsplit(self.cpv)
		self.cpv_split = portage.catpkgsplit(self.cpv)
		self.pv_split = self.cpv_split[1:]

	class _use(object):

		__slots__ = ("__weakref__", "enabled")

		def __init__(self, use):
			self.enabled = frozenset(use)

	class _iuse(object):

		__slots__ = ("__weakref__", "all", "enabled", "disabled", "iuse_implicit", "regex", "tokens")

		def __init__(self, tokens, iuse_implicit):
			self.tokens = tuple(tokens)
			self.iuse_implicit = iuse_implicit
			enabled = []
			disabled = []
			other = []
			for x in tokens:
				prefix = x[:1]
				if prefix == "+":
					enabled.append(x[1:])
				elif prefix == "-":
					disabled.append(x[1:])
				else:
					other.append(x)
			self.enabled = frozenset(enabled)
			self.disabled = frozenset(disabled)
			self.all = frozenset(chain(enabled, disabled, other))

		def __getattribute__(self, name):
			if name == "regex":
				try:
					return object.__getattribute__(self, "regex")
				except AttributeError:
					all = object.__getattribute__(self, "all")
					iuse_implicit = object.__getattribute__(self, "iuse_implicit")
					self.regex = re.compile("^(%s)$" % "|".join(
						chain((re.escape(x) for x in all), iuse_implicit)))
			return object.__getattribute__(self, name)

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			if self.operation is None:
				self.operation = "merge"
				if self.onlydeps or self.installed:
					self.operation = "nomerge"
			self._hash_key = \
				(self.type_name, self.root, self.cpv, self.operation)
		return self._hash_key

	def __lt__(self, other):
		if other.cp != self.cp:
			return False
		if portage.pkgcmp(self.pv_split, other.pv_split) < 0:
			return True
		return False

	def __le__(self, other):
		if other.cp != self.cp:
			return False
		if portage.pkgcmp(self.pv_split, other.pv_split) <= 0:
			return True
		return False

	def __gt__(self, other):
		if other.cp != self.cp:
			return False
		if portage.pkgcmp(self.pv_split, other.pv_split) > 0:
			return True
		return False

	def __ge__(self, other):
		if other.cp != self.cp:
			return False
		if portage.pkgcmp(self.pv_split, other.pv_split) >= 0:
			return True
		return False

_all_metadata_keys = set(x for x in portage.auxdbkeys \
	if not x.startswith("UNUSED_"))
_all_metadata_keys.discard("CDEPEND")
_all_metadata_keys.update(Package.metadata_keys)

from portage.cache.mappings import slot_dict_class
_PackageMetadataWrapperBase = slot_dict_class(_all_metadata_keys)

class _PackageMetadataWrapper(_PackageMetadataWrapperBase):
	"""
	Detect metadata updates and synchronize Package attributes.
	"""

	__slots__ = ("_pkg",)
	_wrapped_keys = frozenset(
		["COUNTER", "INHERITED", "IUSE", "SLOT", "USE", "_mtime_"])

	def __init__(self, pkg, metadata):
		_PackageMetadataWrapperBase.__init__(self)
		self._pkg = pkg
		self.update(metadata)

	def __setitem__(self, k, v):
		_PackageMetadataWrapperBase.__setitem__(self, k, v)
		if k in self._wrapped_keys:
			getattr(self, "_set_" + k.lower())(k, v)

	def _set_inherited(self, k, v):
		if isinstance(v, basestring):
			v = frozenset(v.split())
		self._pkg.inherited = v

	def _set_iuse(self, k, v):
		self._pkg.iuse = self._pkg._iuse(
			v.split(), self._pkg.root_config.iuse_implicit)

	def _set_slot(self, k, v):
		self._pkg.slot = v

	def _set_use(self, k, v):
		self._pkg.use = self._pkg._use(v.split())

	def _set_counter(self, k, v):
		if isinstance(v, basestring):
			try:
				v = int(v.strip())
			except ValueError:
				v = 0
		self._pkg.counter = v

	def _set__mtime_(self, k, v):
		if isinstance(v, basestring):
			try:
				v = float(v.strip())
			except ValueError:
				v = 0
		self._pkg.mtime = v

class EbuildFetcher(SlotObject):

	__slots__ = ("cancelled", "fetch_all", "pkg", "pretend", "settings")

	def execute(self):
		portdb = self.pkg.root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(self.pkg.cpv)
		debug = self.settings.get("PORTAGE_DEBUG") == "1"

		retval = portage.doebuild(ebuild_path, "fetch",
			self.settings["ROOT"], self.settings, debug=debug,
			listonly=self.pretend, fetchonly=1, fetchall=self.fetch_all,
			mydbapi=portdb, tree="porttree")
		return retval

class EbuildFetcherAsync(SlotObject):

	__slots__ = ("cancelled", "log_file", "fd_pipes", "pkg",
		"register", "unregister",
		"pid", "returncode", "files")

	_file_names = ("fetcher", "out")
	_files_dict = slot_dict_class(_file_names, prefix="")
	_bufsize = 4096

	def start(self):

		if self.cancelled:
			return

		# flush any pending output
		fd_pipes = self.fd_pipes
		if fd_pipes is None:
			fd_pipes = {
				0 : sys.stdin.fileno(),
				1 : sys.stdout.fileno(),
				2 : sys.stderr.fileno(),
			}

		log_file = self.log_file
		self.files = self._files_dict()
		files = self.files

		if log_file is not None:
			files.out = open(log_file, "a")
			portage.util.apply_secpass_permissions(log_file,
				uid=portage.portage_uid, gid=portage.portage_gid,
				mode=0660)
		else:
			for fd in fd_pipes.itervalues():
				if fd == sys.stdout.fileno():
					sys.stdout.flush()
				if fd == sys.stderr.fileno():
					sys.stderr.flush()

			files.out = os.fdopen(os.dup(fd_pipes[1]), 'w')

		master_fd, slave_fd = os.pipe()

		import fcntl
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		fd_pipes.setdefault(0, sys.stdin.fileno())
		fd_pipes_orig = fd_pipes.copy()
		fd_pipes[0] = fd_pipes_orig[0]
		fd_pipes[1] = slave_fd
		fd_pipes[2] = slave_fd

		root_config = self.pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(self.pkg.cpv)
		settings = root_config.settings

		fetch_env = dict((k, settings[k]) for k in settings)
		fetch_env["FEATURES"] = fetch_env.get("FEATURES", "") + " -cvs"
		fetch_env["PORTAGE_NICENESS"] = "0"
		fetch_env["PORTAGE_PARALLEL_FETCHONLY"] = "1"

		ebuild_binary = os.path.join(
			settings["EBUILD_BIN_PATH"], "ebuild")

		fetch_args = [ebuild_binary, ebuild_path, "fetch"]
		debug = settings.get("PORTAGE_DEBUG") == "1"
		if debug:
			fetch_args.append("--debug")

		retval = portage.process.spawn(fetch_args, env=fetch_env,
			fd_pipes=fd_pipes, returnpid=True)

		self.pid = retval[0]

		os.close(slave_fd)
		files.fetcher = os.fdopen(master_fd, 'r')
		self.register(files.fetcher.fileno(),
			select.POLLIN, self._output_handler)

	def _output_handler(self, fd, event):
		files = self.files
		buf = array.array('B')
		try:
			buf.fromfile(files.fetcher, self._bufsize)
		except EOFError:
			pass
		if buf:
			buf.tofile(files.out)
			files.out.flush()
		else:
			self.unregister(files.fetcher.fileno())
			for f in files.values():
				f.close()

	def poll(self):
		if self.returncode is not None:
			return self.returncode
		retval = os.waitpid(self.pid, os.WNOHANG)
		if retval == (0, 0):
			return None
		self._set_returncode(retval)
		return self.returncode

	def cancel(self):
		if self.isAlive():
			os.kill(self.pid, signal.SIGTERM)
		self.cancelled = True
		if self.pid is not None:
			self.wait()
		return self.returncode

	def isAlive(self):
		return self.pid is not None and \
			self.returncode is None

	def wait(self):
		if self.returncode is not None:
			return self.returncode
		self._set_returncode(os.waitpid(self.pid, 0))
		return self.returncode

	def _set_returncode(self, wait_retval):

		retval = wait_retval[1]
		portage.process.spawned_pids.remove(self.pid)
		if retval != os.EX_OK:
			if retval & 0xff:
				retval = (retval & 0xff) << 8
			else:
				retval = retval >> 8

		self.returncode = retval

class EbuildBuildDir(SlotObject):

	__slots__ = ("pkg", "settings",
		"locked", "_catdir", "_lock_obj")

	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self.locked = False

	def lock(self):
		"""
		This raises an AlreadyLocked exception if lock() is called
		while a lock is already held. In order to avoid this, call
		unlock() or check whether the "locked" attribute is True
		or False before calling lock().
		"""
		if self._lock_obj is not None:
			raise self.AlreadyLocked((self._lock_obj,))

		root_config = self.pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(self.pkg.cpv)
		settings = self.settings
		debug = settings.get("PORTAGE_DEBUG") == "1"
		use_cache = 1 # always true

		portage.doebuild_environment(ebuild_path, "setup", root_config.root,
			self.settings, debug, use_cache, portdb)
		catdir = os.path.dirname(settings["PORTAGE_BUILDDIR"])
		self._catdir = catdir
		portage.util.ensure_dirs(os.path.dirname(catdir),
			uid=portage.portage_uid, gid=portage.portage_gid,
			mode=070, mask=0)
		catdir_lock = None
		try:
			catdir_lock = portage.locks.lockdir(catdir)
			portage.util.ensure_dirs(catdir,
				gid=portage.portage_gid,
				mode=070, mask=0)
			self._lock_obj = portage.locks.lockdir(
				self.settings["PORTAGE_BUILDDIR"])
		finally:
			self.locked = self._lock_obj is not None
			if catdir_lock is not None:
				portage.locks.unlockdir(catdir_lock)

	def unlock(self):
		if self._lock_obj is None:
			return

		portage.locks.unlockdir(self._lock_obj)
		self._lock_obj = None
		self.locked = False

		catdir = self._catdir
		catdir_lock = None
		try:
			catdir_lock = portage.locks.lockdir(catdir)
		finally:
			if catdir_lock:
				try:
					os.rmdir(catdir)
				except OSError, e:
					if e.errno not in (errno.ENOENT,
						errno.ENOTEMPTY, errno.EEXIST):
						raise
					del e
				portage.locks.unlockdir(catdir_lock)

	class AlreadyLocked(portage.exception.PortageException):
		pass

class EbuildBuild(SlotObject):

	__slots__ = ("args_set", "find_blockers",
		"ldpath_mtimes", "logger", "opts",
		"pkg", "pkg_count", "scheduler",
		"settings")

	def execute(self):

		args_set = self.args_set
		find_blockers = self.find_blockers
		ldpath_mtimes = self.ldpath_mtimes
		logger = self.logger
		opts = self.opts
		pkg = self.pkg
		pkg_count = self.pkg_count
		scheduler = self.scheduler
		settings = self.settings
		root_config = pkg.root_config
		root = root_config.root
		system_set = root_config.sets["system"]
		world_set = root_config.sets["world"]
		vartree = root_config.trees["vartree"]
		portdb = root_config.trees["porttree"].dbapi
		debug = settings.get("PORTAGE_DEBUG") == "1"
		features = self.settings.features
		settings["EMERGE_FROM"] = pkg.type_name
		settings.backup_changes("EMERGE_FROM")
		settings.reset()
		ebuild_path = portdb.findname(self.pkg.cpv)

		#buildsyspkg: Check if we need to _force_ binary package creation
		issyspkg = "buildsyspkg" in features and \
				system_set.findAtomForPackage(pkg) and \
				not opts.buildpkg

		if opts.fetchonly:
			fetcher = EbuildFetcher(fetch_all=opts.fetch_all_uri,
				pkg=pkg, pretend=opts.pretend, settings=settings)
			retval = fetcher.execute()
			if retval != os.EX_OK:
				from portage.elog.messages import eerror
				eerror("!!! Fetch for %s failed, continuing..." % pkg.cpv,
					phase="unpack", key=pkg.cpv)
			return retval

		build_dir = EbuildBuildDir(pkg=pkg, settings=settings)
		try:
			build_dir.lock()
			# Cleaning is triggered before the setup
			# phase, in portage.doebuild().
			msg = " === (%s of %s) Cleaning (%s::%s)" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, ebuild_path)
			short_msg = "emerge: (%s of %s) %s Clean" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv)
			logger.log(msg, short_msg=short_msg)

			if opts.buildpkg or issyspkg:
				if issyspkg:
					portage.writemsg(">>> This is a system package, " + \
						"let's pack a rescue tarball.\n", noiselevel=-1)
				msg = " === (%s of %s) Compiling/Packaging (%s::%s)" % \
					(pkg_count.curval, pkg_count.maxval, pkg.cpv, ebuild_path)
				short_msg = "emerge: (%s of %s) %s Compile" % \
					(pkg_count.curval, pkg_count.maxval, pkg.cpv)
				logger.log(msg, short_msg=short_msg)

				build = EbuildExecuter(pkg=pkg, register=scheduler.register,
					schedule=scheduler.schedule, settings=settings,
					unregister=scheduler.unregister)
				retval = build.execute()
				if retval != os.EX_OK:
					return retval

				build = EbuildBinpkg(pkg=pkg, settings=settings)
				retval = build.execute()
				if retval != os.EX_OK:
					return retval

				if opts.buildpkgonly:
					msg = " === (%s of %s) Merging (%s::%s)" % \
						(pkg_count.curval, pkg_count.maxval,
						pkg.cpv, ebuild_path)
					short_msg = "emerge: (%s of %s) %s Merge" % \
						(pkg_count.curval, pkg_count.maxval, pkg.cpv)
					logger.log(msg, short_msg=short_msg)

					merge = EbuildMerge(
						find_blockers=find_blockers,
						ldpath_mtimes=ldpath_mtimes,
						pkg=pkg, settings=settings)
					retval = merge.execute()
					if retval != os.EX_OK:
						return retval
				elif "noclean" not in settings.features:
					portage.doebuild(ebuild_path, "clean", root,
						settings, debug=debug, mydbapi=portdb,
						tree="porttree")
			else:
				msg = " === (%s of %s) Compiling/Merging (%s::%s)" % \
					(pkg_count.curval, pkg_count.maxval, pkg.cpv, ebuild_path)
				short_msg = "emerge: (%s of %s) %s Compile" % \
					(pkg_count.curval, pkg_count.curval, pkg.cpv)
				logger.log(msg, short_msg=short_msg)

				build = EbuildExecuter(pkg=pkg, register=scheduler.register,
					schedule=scheduler.schedule, settings=settings,
					unregister=scheduler.unregister)
				retval = build.execute()
				if retval != os.EX_OK:
					return retval

				merge = EbuildMerge(
					find_blockers=self.find_blockers,
					ldpath_mtimes=ldpath_mtimes,
					pkg=pkg, settings=settings)
				retval = merge.execute()

				if retval != os.EX_OK:
					return retval
		finally:
			if build_dir.locked:
				portage.elog.elog_process(pkg.cpv, settings)
				build_dir.unlock()

class EbuildExecuter(SlotObject):

	__slots__ = ("pkg", "register", "schedule", "settings", "unregister")

	_phases = ("setup", "unpack", "compile", "test", "install")

	def execute(self):
		root_config = self.pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(self.pkg.cpv)
		settings = self.settings
		debug = settings.get("PORTAGE_DEBUG") == "1"
		cleanup = 1

		retval = portage.doebuild(ebuild_path, "clean",
			root_config.root, settings, debug, cleanup=cleanup,
			mydbapi=portdb, tree="porttree")
		if retval != os.EX_OK:
			return retval

		# This initializes PORTAGE_LOG_FILE.
		portage.prepare_build_dirs(root_config.root, settings, cleanup)

		fd_pipes = {
			0 : sys.stdin.fileno(),
			1 : sys.stdout.fileno(),
			2 : sys.stderr.fileno(),
		}

		for mydo in self._phases:
			ebuild_phase = EbuildPhase(fd_pipes=fd_pipes,
				pkg=self.pkg, phase=mydo, register=self.register,
				settings=settings, unregister=self.unregister)

			ebuild_phase.start()
			retval = None
			while retval is None:
				self.schedule()
				retval = ebuild_phase.poll()

			portage._post_phase_userpriv_perms(settings)
			if mydo == "install":
				portage._check_build_log(settings)
				if retval == os.EX_OK:
					retval = portage._post_src_install_checks(settings)

			if retval != os.EX_OK:
				return retval

		return os.EX_OK

class EbuildPhase(SlotObject):

	__slots__ = ("fd_pipes", "phase", "pkg",
		"register", "settings", "unregister",
		"pid", "returncode", "files")

	_file_names = ("log", "stdout", "ebuild")
	_files_dict = slot_dict_class(_file_names, prefix="")
	_bufsize = 4096

	def start(self):
		root_config = self.pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(self.pkg.cpv)
		settings = self.settings
		debug = settings.get("PORTAGE_DEBUG") == "1"
		logfile = settings.get("PORTAGE_LOG_FILE")
		master_fd = None
		slave_fd = None
		fd_pipes = self.fd_pipes.copy()

		# flush any pending output
		for fd in fd_pipes.itervalues():
			if fd == sys.stdout.fileno():
				sys.stdout.flush()
			if fd == sys.stderr.fileno():
				sys.stderr.flush()

		fd_pipes_orig = None
		self.files = self._files_dict()
		files = self.files
		got_pty = False

		portage._doebuild_exit_status_unlink(
			settings.get("EBUILD_EXIT_STATUS_FILE"))

		if logfile:
			if portage._disable_openpty:
				master_fd, slave_fd = os.pipe()
			else:
				from pty import openpty
				try:
					master_fd, slave_fd = openpty()
					got_pty = True
				except EnvironmentError, e:
					portage._disable_openpty = True
					portage.writemsg("openpty failed: '%s'\n" % str(e),
						noiselevel=-1)
					del e
					master_fd, slave_fd = os.pipe()

			if got_pty:
				# Disable post-processing of output since otherwise weird
				# things like \n -> \r\n transformations may occur.
				import termios
				mode = termios.tcgetattr(slave_fd)
				mode[1] &= ~termios.OPOST
				termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

			import fcntl
			fcntl.fcntl(master_fd, fcntl.F_SETFL,
				fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

			fd_pipes.setdefault(0, sys.stdin.fileno())
			fd_pipes_orig = fd_pipes.copy()
			if got_pty and os.isatty(fd_pipes_orig[1]):
				from portage.output import get_term_size, set_term_size
				rows, columns = get_term_size()
				set_term_size(rows, columns, slave_fd)
			fd_pipes[0] = fd_pipes_orig[0]
			fd_pipes[1] = slave_fd
			fd_pipes[2] = slave_fd

		retval = portage.doebuild(ebuild_path, self.phase,
			root_config.root, settings, debug,
			mydbapi=portdb, tree="porttree",
			fd_pipes=fd_pipes, returnpid=True)

		self.pid = retval[0]

		if logfile:
			os.close(slave_fd)
			files.log = open(logfile, 'a')
			files.stdout = os.fdopen(os.dup(fd_pipes_orig[1]), 'w')
			files.ebuild = os.fdopen(master_fd, 'r')
			self.register(files.ebuild.fileno(),
				select.POLLIN, self._output_handler)

	def _output_handler(self, fd, event):
		files = self.files
		buf = array.array('B')
		try:
			buf.fromfile(files.ebuild, self._bufsize)
		except EOFError:
			pass
		if buf:
			buf.tofile(files.stdout)
			files.stdout.flush()
			buf.tofile(files.log)
			files.log.flush()
		else:
			self.unregister(files.ebuild.fileno())
			for f in files.values():
				f.close()

	def poll(self):
		if self.returncode is not None:
			return self.returncode
		retval = os.waitpid(self.pid, os.WNOHANG)
		if retval == (0, 0):
			return None
		self._set_returncode(retval)
		return self.returncode

	def wait(self):
		if self.returncode is not None:
			return self.returncode
		self._set_returncode(os.waitpid(self.pid, 0))
		return self.returncode

	def _set_returncode(self, wait_retval):

		retval = wait_retval[1]
		portage.process.spawned_pids.remove(self.pid)
		if retval != os.EX_OK:
			if retval & 0xff:
				retval = (retval & 0xff) << 8
			else:
				retval = retval >> 8

		msg = portage._doebuild_exit_status_check(
			self.phase, self.settings)
		if msg:
			retval = 1
			from textwrap import wrap
			from portage.elog.messages import eerror
			for l in wrap(msg, 72):
				eerror(l, phase=self.phase, key=self.pkg.cpv)

		self.returncode = retval

class EbuildBinpkg(Task):
	"""
	This assumes that src_install() has successfully completed.
	"""
	__slots__ = ("pkg", "settings")

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = ("EbuildBinpkg", self.pkg._get_hash_key())
		return self._hash_key

	def execute(self):
		pkg = self.pkg
		root_config = pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		bintree = root_config.trees["bintree"]
		ebuild_path = portdb.findname(self.pkg.cpv)
		settings = self.settings
		debug = settings.get("PORTAGE_DEBUG") == "1"

		bintree.prevent_collision(pkg.cpv)
		binpkg_tmpfile = os.path.join(bintree.pkgdir,
			pkg.cpv + ".tbz2." + str(os.getpid()))
		settings["PORTAGE_BINPKG_TMPFILE"] = binpkg_tmpfile
		settings.backup_changes("PORTAGE_BINPKG_TMPFILE")

		# Earlier phases should already be done, so
		# use "noauto" to quietly skip them.
		settings.features.append("noauto")

		try:
			retval = portage.doebuild(ebuild_path,
				"package", root_config.root,
				settings, debug, mydbapi=portdb,
				tree="porttree")
		finally:
			settings.pop("PORTAGE_BINPKG_TMPFILE", None)
			try:
				settings.features.remove("noauto")
			except ValueError:
				pass

		if retval == os.EX_OK:
			bintree.inject(pkg.cpv, filename=binpkg_tmpfile)

		return retval

class EbuildMerge(Task):

	__slots__ = ("find_blockers", "ldpath_mtimes",
		"pkg", "pretend", "settings")

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = ("EbuildMerge", self.pkg._get_hash_key())
		return self._hash_key

	def execute(self):
		root_config = self.pkg.root_config
		settings = self.settings
		retval = portage.merge(settings["CATEGORY"],
			settings["PF"], settings["D"],
			os.path.join(settings["PORTAGE_BUILDDIR"],
			"build-info"), root_config.root, settings,
			myebuild=settings["EBUILD"],
			mytree="porttree", mydbapi=root_config.trees["porttree"].dbapi,
			vartree=root_config.trees["vartree"],
			prev_mtimes=self.ldpath_mtimes,
			blockers=self.find_blockers)
		return retval

class PackageUninstall(Task):

	__slots__ = ("ldpath_mtimes", "opts", "pkg", "settings")

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = ("PackageUninstall", self.pkg._get_hash_key())
		return self._hash_key

	def execute(self):
		try:
			unmerge(self.pkg.root_config, self.opts, "unmerge",
				[self.pkg.cpv], self.ldpath_mtimes, clean_world=0,
				raise_on_error=1)
		except UninstallFailure, e:
			return e.status
		return os.EX_OK

class BinpkgFetcher(Task):

	__slots__ = ("use_locks", "pkg", "pretend",
	"pkg_path", "remote")

	def __init__(self, **kwargs):
		Task.__init__(self, **kwargs)
		pkg = self.pkg
		self.pkg_path = pkg.root_config.trees["bintree"].getname(pkg.cpv)

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = ("BinpkgFetcher", self.pkg._get_hash_key())
		return self._hash_key

	def execute(self):
		tbz2_lock = None
		use_locks = self.use_locks
		pkg = self.pkg
		pretend = self.pretend
		bintree = pkg.root_config.trees["bintree"]
		pkgdir = bintree.pkgdir
		pkg_path = self.pkg_path
		rval = os.EX_OK

		try:
			try:
				if not pretend and use_locks and os.access(pkgdir, os.W_OK):
					portage.util.ensure_dirs(os.path.dirname(pkg_path))
					tbz2_lock = portage.locks.lockfile(pkg_path,
						wantnewlockfile=1)
				if bintree.isremote(pkg.cpv):
					self.remote = True
					if not pretend:
						bintree.gettbz2(pkg.cpv)
			finally:
				if tbz2_lock is not None:
					portage.locks.unlockfile(tbz2_lock)
		except portage.exception.FileNotFound:
			writemsg("!!! Fetching Binary failed " + \
				"for '%s'\n" % pkg.cpv, noiselevel=-1)
			rval = 1
		except portage.exception.DigestException, e:
			writemsg("\n!!! Digest verification failed:\n",
				noiselevel=-1)
			writemsg("!!! %s\n" % e.value[0],
				noiselevel=-1)
			writemsg("!!! Reason: %s\n" % e.value[1],
				noiselevel=-1)
			writemsg("!!! Got: %s\n" % e.value[2],
				noiselevel=-1)
			writemsg("!!! Expected: %s\n" % e.value[3],
				noiselevel=-1)
			if not pretend:
				os.unlink(pkg_path)
			rval = 1
		return rval

class BinpkgFetcherAsync(SlotObject):

	__slots__ = ("cancelled", "log_file", "fd_pipes", "pkg",
		"register", "unregister",
		"locked", "files", "pid", "pkg_path", "returncode", "_lock_obj")

	_file_names = ("fetcher", "out")
	_files_dict = slot_dict_class(_file_names, prefix="")
	_bufsize = 4096

	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		pkg = self.pkg
		self.pkg_path = pkg.root_config.trees["bintree"].getname(pkg.cpv)

	def start(self):

		if self.cancelled:
			return
		writemsg(">>> starting parallel binpkg fetcher\n")

		fd_pipes = self.fd_pipes
		if fd_pipes is None:
			fd_pipes = {
				0 : sys.stdin.fileno(),
				1 : sys.stdout.fileno(),
				2 : sys.stderr.fileno(),
			}

		log_file = self.log_file
		self.files = self._files_dict()
		files = self.files

		if log_file is not None:
			files.out = open(log_file, "a")
			portage.util.apply_secpass_permissions(log_file,
				uid=portage.portage_uid, gid=portage.portage_gid,
				mode=0660)
		else:
			# flush any pending output
			for fd in fd_pipes.itervalues():
				if fd == sys.stdout.fileno():
					sys.stdout.flush()
				if fd == sys.stderr.fileno():
					sys.stderr.flush()

			files.out = os.fdopen(os.dup(fd_pipes[1]), 'w')

		master_fd, slave_fd = os.pipe()
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		fd_pipes.setdefault(0, sys.stdin.fileno())
		fd_pipes_orig = fd_pipes.copy()
		fd_pipes[0] = fd_pipes_orig[0]
		fd_pipes[1] = slave_fd
		fd_pipes[2] = slave_fd

		pkg = self.pkg
		bintree = pkg.root_config.trees["bintree"]
		settings = bintree.settings
		use_locks = "distlocks" in settings.features
		pkg_path = self.pkg_path
		resume = os.path.exists(pkg_path)

		# urljoin doesn't work correctly with
		# unrecognized protocols like sftp
		if bintree._remote_has_index:
			rel_uri = bintree._remotepkgs[pkg.cpv].get("PATH")
			if not rel_uri:
				rel_uri = pkg.cpv + ".tbz2"
			uri = bintree._remote_base_uri.rstrip("/") + \
				"/" + rel_uri.lstrip("/")
		else:
			uri = settings["PORTAGE_BINHOST"].rstrip("/") + \
				"/" + pkg.pf + ".tbz2"

		protocol = urlparse.urlparse(uri)[0]
		fcmd_prefix = "FETCHCOMMAND"
		if resume:
			fcmd_prefix = "RESUMECOMMAND"
		fcmd = settings.get(fcmd_prefix + "_" + protocol.upper())
		if not fcmd:
			fcmd = settings.get(fcmd_prefix)

		fcmd_vars = {
			"DISTDIR" : os.path.dirname(pkg_path),
			"URI"     : uri,
			"FILE"    : os.path.basename(pkg_path)
		}

		fetch_env = dict((k, settings[k]) for k in settings)
		fetch_args = [portage.util.varexpand(x, mydict=fcmd_vars) \
			for x in shlex.split(fcmd)]

		portage.util.ensure_dirs(os.path.dirname(pkg_path))
		if use_locks:
			self.lock()

		retval = portage.process.spawn(fetch_args, env=fetch_env,
			fd_pipes=fd_pipes, returnpid=True)

		self.pid = retval[0]

		os.close(slave_fd)
		files.fetcher = os.fdopen(master_fd, 'r')
		self.register(files.fetcher.fileno(),
			select.POLLIN, self._output_handler)

	def _output_handler(self, fd, event):
		files = self.files
		buf = array.array('B')
		try:
			buf.fromfile(files.fetcher, self._bufsize)
		except EOFError:
			pass
		if buf:
			buf.tofile(files.out)
			files.out.flush()
		else:
			self.unregister(files.fetcher.fileno())
			for f in files.values():
				f.close()
			if self.locked:
				self.unlock()

	def lock(self):
		"""
		This raises an AlreadyLocked exception if lock() is called
		while a lock is already held. In order to avoid this, call
		unlock() or check whether the "locked" attribute is True
		or False before calling lock().
		"""
		if self._lock_obj is not None:
			raise self.AlreadyLocked((self._lock_obj,))

		self._lock_obj = portage.locks.lockfile(
			self.pkg_path, wantnewlockfile=1)
		self.locked = True

	class AlreadyLocked(portage.exception.PortageException):
		pass

	def unlock(self):
		if self._lock_obj is None:
			return
		portage.locks.unlockfile(self._lock_obj)
		self._lock_obj = None
		self.locked = False

	def poll(self):
		if self.returncode is not None:
			return self.returncode
		retval = os.waitpid(self.pid, os.WNOHANG)
		if retval == (0, 0):
			return None
		self._set_returncode(retval)
		return self.returncode

	def cancel(self):
		if self.isAlive():
			os.kill(self.pid, signal.SIGTERM)
		self.cancelled = True
		if self.pid is not None:
			self.wait()
		return self.returncode

	def isAlive(self):
		return self.pid is not None and \
			self.returncode is None

	def wait(self):
		if self.returncode is not None:
			return self.returncode
		self._set_returncode(os.waitpid(self.pid, 0))
		return self.returncode

	def _set_returncode(self, wait_retval):

		retval = wait_retval[1]
		portage.process.spawned_pids.remove(self.pid)
		if retval != os.EX_OK:
			if retval & 0xff:
				retval = (retval & 0xff) << 8
			else:
				retval = retval >> 8

		self.returncode = retval

class BinpkgMerge(Task):

	__slots__ = ("find_blockers", "ldpath_mtimes",
		"pkg", "pretend", "pkg_path", "settings")

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = ("BinpkgMerge", self.pkg._get_hash_key())
		return self._hash_key

	def execute(self):

		settings = self.settings
		settings["EMERGE_FROM"] = self.pkg.type_name
		settings.backup_changes("EMERGE_FROM")
		settings.reset()

		root_config = self.pkg.root_config
		retval = portage.pkgmerge(self.pkg_path, root_config.root,
			self.settings,
			mydbapi=root_config.trees["bintree"].dbapi,
			vartree=root_config.trees["vartree"],
			prev_mtimes=self.ldpath_mtimes,
			blockers=self.find_blockers)
		return retval

class DependencyArg(object):
	def __init__(self, arg=None, root_config=None):
		self.arg = arg
		self.root_config = root_config

	def __str__(self):
		return self.arg

class AtomArg(DependencyArg):
	def __init__(self, atom=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.atom = atom
		if not isinstance(self.atom, portage.dep.Atom):
			self.atom = portage.dep.Atom(self.atom)
		self.set = (self.atom, )

class PackageArg(DependencyArg):
	def __init__(self, package=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.package = package
		self.atom = portage.dep.Atom("=" + package.cpv)
		self.set = (self.atom, )

class SetArg(DependencyArg):
	def __init__(self, set=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.set = set
		self.name = self.arg[len(SETPREFIX):]

class Dependency(SlotObject):
	__slots__ = ("atom", "blocker", "depth",
		"parent", "onlydeps", "priority", "root")
	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		if self.priority is None:
			self.priority = DepPriority()
		if self.depth is None:
			self.depth = 0

class BlockerCache(DictMixin):
	"""This caches blockers of installed packages so that dep_check does not
	have to be done for every single installed package on every invocation of
	emerge.  The cache is invalidated whenever it is detected that something
	has changed that might alter the results of dep_check() calls:
		1) the set of installed packages (including COUNTER) has changed
		2) the old-style virtuals have changed
	"""

	# Number of uncached packages to trigger cache update, since
	# it's wasteful to update it for every vdb change.
	_cache_threshold = 5

	class BlockerData(object):

		__slots__ = ("__weakref__", "atoms", "counter")

		def __init__(self, counter, atoms):
			self.counter = counter
			self.atoms = atoms

	def __init__(self, myroot, vardb):
		self._vardb = vardb
		self._virtuals = vardb.settings.getvirtuals()
		self._cache_filename = os.path.join(myroot,
			portage.CACHE_PATH.lstrip(os.path.sep), "vdb_blockers.pickle")
		self._cache_version = "1"
		self._cache_data = None
		self._modified = set()
		self._load()

	def _load(self):
		try:
			f = open(self._cache_filename)
			mypickle = cPickle.Unpickler(f)
			mypickle.find_global = None
			self._cache_data = mypickle.load()
			f.close()
			del f
		except (IOError, OSError, EOFError, cPickle.UnpicklingError), e:
			if isinstance(e, cPickle.UnpicklingError):
				writemsg("!!! Error loading '%s': %s\n" % \
					(self._cache_filename, str(e)), noiselevel=-1)
			del e

		cache_valid = self._cache_data and \
			isinstance(self._cache_data, dict) and \
			self._cache_data.get("version") == self._cache_version and \
			isinstance(self._cache_data.get("blockers"), dict)
		if cache_valid:
			# Validate all the atoms and counters so that
			# corruption is detected as soon as possible.
			invalid_items = set()
			for k, v in self._cache_data["blockers"].iteritems():
				if not isinstance(k, basestring):
					invalid_items.add(k)
					continue
				try:
					if portage.catpkgsplit(k) is None:
						invalid_items.add(k)
						continue
				except portage.exception.InvalidData:
					invalid_items.add(k)
					continue
				if not isinstance(v, tuple) or \
					len(v) != 2:
					invalid_items.add(k)
					continue
				counter, atoms = v
				if not isinstance(counter, (int, long)):
					invalid_items.add(k)
					continue
				if not isinstance(atoms, (list, tuple)):
					invalid_items.add(k)
					continue
				invalid_atom = False
				for atom in atoms:
					if not isinstance(atom, basestring):
						invalid_atom = True
						break
					if atom[:1] != "!" or \
						not portage.isvalidatom(
						atom, allow_blockers=True):
						invalid_atom = True
						break
				if invalid_atom:
					invalid_items.add(k)
					continue

			for k in invalid_items:
				del self._cache_data["blockers"][k]
			if not self._cache_data["blockers"]:
				cache_valid = False

		if not cache_valid:
			self._cache_data = {"version":self._cache_version}
			self._cache_data["blockers"] = {}
			self._cache_data["virtuals"] = self._virtuals
		self._modified.clear()

	def flush(self):
		"""If the current user has permission and the internal blocker cache
		been updated, save it to disk and mark it unmodified.  This is called
		by emerge after it has proccessed blockers for all installed packages.
		Currently, the cache is only written if the user has superuser
		privileges (since that's required to obtain a lock), but all users
		have read access and benefit from faster blocker lookups (as long as
		the entire cache is still valid).  The cache is stored as a pickled
		dict object with the following format:

		{
			version : "1",
			"blockers" : {cpv1:(counter,(atom1, atom2...)), cpv2...},
			"virtuals" : vardb.settings.getvirtuals()
		}
		"""
		if len(self._modified) >= self._cache_threshold and \
			secpass >= 2:
			try:
				f = portage.util.atomic_ofstream(self._cache_filename)
				cPickle.dump(self._cache_data, f, -1)
				f.close()
				portage.util.apply_secpass_permissions(
					self._cache_filename, gid=portage.portage_gid, mode=0644)
			except (IOError, OSError), e:
				pass
			self._modified.clear()

	def __setitem__(self, cpv, blocker_data):
		"""
		Update the cache and mark it as modified for a future call to
		self.flush().

		@param cpv: Package for which to cache blockers.
		@type cpv: String
		@param blocker_data: An object with counter and atoms attributes.
		@type blocker_data: BlockerData
		"""
		self._cache_data["blockers"][cpv] = \
			(blocker_data.counter, tuple(str(x) for x in blocker_data.atoms))
		self._modified.add(cpv)

	def __iter__(self):
		return iter(self._cache_data["blockers"])

	def __delitem__(self, cpv):
		del self._cache_data["blockers"][cpv]

	def __getitem__(self, cpv):
		"""
		@rtype: BlockerData
		@returns: An object with counter and atoms attributes.
		"""
		return self.BlockerData(*self._cache_data["blockers"][cpv])

	def keys(self):
		"""This needs to be implemented so that self.__repr__() doesn't raise
		an AttributeError."""
		return list(self)

class BlockerDB(object):

	def __init__(self, root_config):
		self._root_config = root_config
		self._vartree = root_config.trees["vartree"]
		self._portdb = root_config.trees["porttree"].dbapi
			
		self._dep_check_trees = { self._vartree.root : {
			"porttree"    :  self._vartree,
			"vartree"     :  self._vartree,
		}}

	def findInstalledBlockers(self, new_pkg, acquire_lock=0):
		blocker_cache = BlockerCache(self._vartree.root, self._vartree.dbapi)
		dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
		dep_check_trees = self._dep_check_trees
		settings = self._vartree.settings
		stale_cache = set(blocker_cache)
		fake_vartree = \
			FakeVartree(self._root_config, acquire_lock=acquire_lock)
		vardb = fake_vartree.dbapi
		installed_pkgs = list(vardb)

		for inst_pkg in installed_pkgs:
			stale_cache.discard(inst_pkg.cpv)
			cached_blockers = blocker_cache.get(inst_pkg.cpv)
			if cached_blockers is not None and \
				cached_blockers.counter != long(inst_pkg.metadata["COUNTER"]):
				cached_blockers = None
			if cached_blockers is not None:
				blocker_atoms = cached_blockers.atoms
			else:
				# Use aux_get() to trigger FakeVartree global
				# updates on *DEPEND when appropriate.
				depstr = " ".join(vardb.aux_get(inst_pkg.cpv, dep_keys))
				try:
					portage.dep._dep_check_strict = False
					success, atoms = portage.dep_check(depstr,
						vardb, settings, myuse=inst_pkg.use.enabled,
						trees=dep_check_trees, myroot=inst_pkg.root)
				finally:
					portage.dep._dep_check_strict = True
				if not success:
					pkg_location = os.path.join(inst_pkg.root,
						portage.VDB_PATH, inst_pkg.category, inst_pkg.pf)
					portage.writemsg("!!! %s/*DEPEND: %s\n" % \
						(pkg_location, atoms), noiselevel=-1)
					continue

				blocker_atoms = [atom for atom in atoms \
					if atom.startswith("!")]
				blocker_atoms.sort()
				counter = long(inst_pkg.metadata["COUNTER"])
				blocker_cache[inst_pkg.cpv] = \
					blocker_cache.BlockerData(counter, blocker_atoms)
		for cpv in stale_cache:
			del blocker_cache[cpv]
		blocker_cache.flush()

		blocker_parents = digraph()
		blocker_atoms = []
		for pkg in installed_pkgs:
			for blocker_atom in blocker_cache[pkg.cpv].atoms:
				blocker_atom = blocker_atom[1:]
				blocker_atoms.append(blocker_atom)
				blocker_parents.add(blocker_atom, pkg)

		blocker_atoms = InternalPackageSet(initial_atoms=blocker_atoms)
		blocking_pkgs = set()
		for atom in blocker_atoms.iterAtomsForPackage(new_pkg):
			blocking_pkgs.update(blocker_parents.parent_nodes(atom))

		# Check for blockers in the other direction.
		depstr = " ".join(new_pkg.metadata[k] for k in dep_keys)
		try:
			portage.dep._dep_check_strict = False
			success, atoms = portage.dep_check(depstr,
				vardb, settings, myuse=new_pkg.use.enabled,
				trees=dep_check_trees, myroot=new_pkg.root)
		finally:
			portage.dep._dep_check_strict = True
		if not success:
			# We should never get this far with invalid deps.
			show_invalid_depstring_notice(new_pkg, depstr, atoms)
			assert False

		blocker_atoms = [atom[1:] for atom in atoms \
			if atom.startswith("!")]
		if blocker_atoms:
			blocker_atoms = InternalPackageSet(initial_atoms=blocker_atoms)
			for inst_pkg in installed_pkgs:
				try:
					blocker_atoms.iterAtomsForPackage(inst_pkg).next()
				except (portage.exception.InvalidDependString, StopIteration):
					continue
				blocking_pkgs.add(inst_pkg)

		return blocking_pkgs

def show_invalid_depstring_notice(parent_node, depstring, error_msg):

	from formatter import AbstractFormatter, DumbWriter
	f = AbstractFormatter(DumbWriter(maxcol=72))

	print "\n\n!!! Invalid or corrupt dependency specification: "
	print
	print error_msg
	print
	print parent_node
	print
	print depstring
	print
	p_type, p_root, p_key, p_status = parent_node
	msg = []
	if p_status == "nomerge":
		category, pf = portage.catsplit(p_key)
		pkg_location = os.path.join(p_root, portage.VDB_PATH, category, pf)
		msg.append("Portage is unable to process the dependencies of the ")
		msg.append("'%s' package. " % p_key)
		msg.append("In order to correct this problem, the package ")
		msg.append("should be uninstalled, reinstalled, or upgraded. ")
		msg.append("As a temporary workaround, the --nodeps option can ")
		msg.append("be used to ignore all dependencies.  For reference, ")
		msg.append("the problematic dependencies can be found in the ")
		msg.append("*DEPEND files located in '%s/'." % pkg_location)
	else:
		msg.append("This package can not be installed.  ")
		msg.append("Please notify the '%s' package maintainer " % p_key)
		msg.append("about this problem.")

	for x in msg:
		f.add_flowing_data(x)
	f.end_paragraph(1)

class PackageVirtualDbapi(portage.dbapi):
	"""
	A dbapi-like interface class that represents the state of the installed
	package database as new packages are installed, replacing any packages
	that previously existed in the same slot. The main difference between
	this class and fakedbapi is that this one uses Package instances
	internally (passed in via cpv_inject() and cpv_remove() calls).
	"""
	def __init__(self, settings):
		portage.dbapi.__init__(self)
		self.settings = settings
		self._match_cache = {}
		self._cp_map = {}
		self._cpv_map = {}

	def clear(self):
		"""
		Remove all packages.
		"""
		if self._cpv_map:
			self._clear_cache()
			self._cp_map.clear()
			self._cpv_map.clear()

	def copy(self):
		obj = PackageVirtualDbapi(self.settings)
		obj._match_cache = self._match_cache.copy()
		obj._cp_map = self._cp_map.copy()
		for k, v in obj._cp_map.iteritems():
			obj._cp_map[k] = v[:]
		obj._cpv_map = self._cpv_map.copy()
		return obj

	def __iter__(self):
		return self._cpv_map.itervalues()

	def __contains__(self, item):
		existing = self._cpv_map.get(item.cpv)
		if existing is not None and \
			existing == item:
			return True
		return False

	def match_pkgs(self, atom):
		return [self._cpv_map[cpv] for cpv in self.match(atom)]

	def _clear_cache(self):
		if self._categories is not None:
			self._categories = None
		if self._match_cache:
			self._match_cache = {}

	def match(self, origdep, use_cache=1):
		result = self._match_cache.get(origdep)
		if result is not None:
			return result[:]
		result = portage.dbapi.match(self, origdep, use_cache=use_cache)
		self._match_cache[origdep] = result
		return result[:]

	def cpv_exists(self, cpv):
		return cpv in self._cpv_map

	def cp_list(self, mycp, use_cache=1):
		cachelist = self._match_cache.get(mycp)
		# cp_list() doesn't expand old-style virtuals
		if cachelist and cachelist[0].startswith(mycp):
			return cachelist[:]
		cpv_list = self._cp_map.get(mycp)
		if cpv_list is None:
			cpv_list = []
		else:
			cpv_list = [pkg.cpv for pkg in cpv_list]
		self._cpv_sort_ascending(cpv_list)
		if not (not cpv_list and mycp.startswith("virtual/")):
			self._match_cache[mycp] = cpv_list
		return cpv_list[:]

	def cp_all(self):
		return list(self._cp_map)

	def cpv_all(self):
		return list(self._cpv_map)

	def cpv_inject(self, pkg):
		cp_list = self._cp_map.get(pkg.cp)
		if cp_list is None:
			cp_list = []
			self._cp_map[pkg.cp] = cp_list
		e_pkg = self._cpv_map.get(pkg.cpv)
		if e_pkg is not None:
			if e_pkg == pkg:
				return
			self.cpv_remove(e_pkg)
		for e_pkg in cp_list:
			if e_pkg.slot_atom == pkg.slot_atom:
				if e_pkg == pkg:
					return
				self.cpv_remove(e_pkg)
				break
		cp_list.append(pkg)
		self._cpv_map[pkg.cpv] = pkg
		self._clear_cache()

	def cpv_remove(self, pkg):
		old_pkg = self._cpv_map.get(pkg.cpv)
		if old_pkg != pkg:
			raise KeyError(pkg)
		self._cp_map[pkg.cp].remove(pkg)
		del self._cpv_map[pkg.cpv]
		self._clear_cache()

	def aux_get(self, cpv, wants):
		metadata = self._cpv_map[cpv].metadata
		return [metadata.get(x, "") for x in wants]

	def aux_update(self, cpv, values):
		self._cpv_map[cpv].metadata.update(values)
		self._clear_cache()

class depgraph(object):

	pkg_tree_map = {
		"ebuild":"porttree",
		"binary":"bintree",
		"installed":"vartree"}

	_mydbapi_keys = Package.metadata_keys

	_dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]

	# If dep calculation time exceeds this value then automatically
	# enable "complete" mode since any performance difference is
	# not as likely to be noticed by the user after this much time
	# has passed.
	_complete_threshold = 20

	def __init__(self, settings, trees, myopts, myparams, spinner):
		self._creation_time = time.time()
		self.settings = settings
		self.target_root = settings["ROOT"]
		self.myopts = myopts
		self.myparams = myparams
		self.edebug = 0
		if settings.get("PORTAGE_DEBUG", "") == "1":
			self.edebug = 1
		self.spinner = spinner
		self.pkgsettings = {}
		# Maps slot atom to package for each Package added to the graph.
		self._slot_pkg_map = {}
		# Maps nodes to the reasons they were selected for reinstallation.
		self._reinstall_nodes = {}
		self.mydbapi = {}
		self.trees = {}
		self._trees_orig = trees
		self.roots = {}
		# Contains a filtered view of preferred packages that are selected
		# from available repositories.
		self._filtered_trees = {}
		# Contains installed packages and new packages that have been added
		# to the graph.
		self._graph_trees = {}
		# All Package instances
		self._pkg_cache = self._package_cache(self)
		for myroot in trees:
			self.trees[myroot] = {}
			# Create a RootConfig instance that references
			# the FakeVartree instead of the real one.
			self.roots[myroot] = RootConfig(
				trees[myroot]["vartree"].settings,
				self.trees[myroot],
				trees[myroot]["root_config"].setconfig)
			for tree in ("porttree", "bintree"):
				self.trees[myroot][tree] = trees[myroot][tree]
			self.trees[myroot]["vartree"] = \
				FakeVartree(trees[myroot]["root_config"],
					pkg_cache=self._pkg_cache)
			self.pkgsettings[myroot] = portage.config(
				clone=self.trees[myroot]["vartree"].settings)
			self._slot_pkg_map[myroot] = {}
			vardb = self.trees[myroot]["vartree"].dbapi
			preload_installed_pkgs = "--nodeps" not in self.myopts and \
				"--buildpkgonly" not in self.myopts
			# This fakedbapi instance will model the state that the vdb will
			# have after new packages have been installed.
			fakedb = PackageVirtualDbapi(vardb.settings)
			if preload_installed_pkgs:
				for pkg in vardb:
					self.spinner.update()
					# This triggers metadata updates via FakeVartree.
					vardb.aux_get(pkg.cpv, [])
					fakedb.cpv_inject(pkg)

			# Now that the vardb state is cached in our FakeVartree,
			# we won't be needing the real vartree cache for awhile.
			# To make some room on the heap, clear the vardbapi
			# caches.
			trees[myroot]["vartree"].dbapi._clear_cache()
			gc.collect()

			self.mydbapi[myroot] = fakedb
			def graph_tree():
				pass
			graph_tree.dbapi = fakedb
			self._graph_trees[myroot] = {}
			self._filtered_trees[myroot] = {}
			# Substitute the graph tree for the vartree in dep_check() since we
			# want atom selections to be consistent with package selections
			# have already been made.
			self._graph_trees[myroot]["porttree"]   = graph_tree
			self._graph_trees[myroot]["vartree"]    = graph_tree
			def filtered_tree():
				pass
			filtered_tree.dbapi = self._dep_check_composite_db(self, myroot)
			self._filtered_trees[myroot]["porttree"] = filtered_tree

			# Passing in graph_tree as the vartree here could lead to better
			# atom selections in some cases by causing atoms for packages that
			# have been added to the graph to be preferred over other choices.
			# However, it can trigger atom selections that result in
			# unresolvable direct circular dependencies. For example, this
			# happens with gwydion-dylan which depends on either itself or
			# gwydion-dylan-bin. In case gwydion-dylan is not yet installed,
			# gwydion-dylan-bin needs to be selected in order to avoid a
			# an unresolvable direct circular dependency.
			#
			# To solve the problem described above, pass in "graph_db" so that
			# packages that have been added to the graph are distinguishable
			# from other available packages and installed packages. Also, pass
			# the parent package into self._select_atoms() calls so that
			# unresolvable direct circular dependencies can be detected and
			# avoided when possible.
			self._filtered_trees[myroot]["graph_db"] = graph_tree.dbapi
			self._filtered_trees[myroot]["vartree"] = self.trees[myroot]["vartree"]

			dbs = []
			portdb = self.trees[myroot]["porttree"].dbapi
			bindb  = self.trees[myroot]["bintree"].dbapi
			vardb  = self.trees[myroot]["vartree"].dbapi
			#               (db, pkg_type, built, installed, db_keys)
			if "--usepkgonly" not in self.myopts:
				db_keys = list(portdb._aux_cache_keys)
				dbs.append((portdb, "ebuild", False, False, db_keys))
			if "--usepkg" in self.myopts:
				db_keys = list(bindb._aux_cache_keys)
				dbs.append((bindb,  "binary", True, False, db_keys))
			db_keys = self._mydbapi_keys
			dbs.append((vardb, "installed", True, True, db_keys))
			self._filtered_trees[myroot]["dbs"] = dbs
			if "--usepkg" in self.myopts:
				self.trees[myroot]["bintree"].populate(
					"--getbinpkg" in self.myopts,
					"--getbinpkgonly" in self.myopts)
		del trees

		self.digraph=portage.digraph()
		# contains all sets added to the graph
		self._sets = {}
		# contains atoms given as arguments
		self._sets["args"] = InternalPackageSet()
		# contains all atoms from all sets added to the graph, including
		# atoms given as arguments
		self._set_atoms = InternalPackageSet()
		self._atom_arg_map = {}
		# contains all nodes pulled in by self._set_atoms
		self._set_nodes = set()
		# Contains only Blocker -> Uninstall edges
		self._blocker_uninstalls = digraph()
		# Contains only Package -> Blocker edges
		self._blocker_parents = digraph()
		# Contains only irrelevant Package -> Blocker edges
		self._irrelevant_blockers = digraph()
		# Contains only unsolvable Package -> Blocker edges
		self._unsolvable_blockers = digraph()
		self._slot_collision_info = set()
		# Slot collision nodes are not allowed to block other packages since
		# blocker validation is only able to account for one package per slot.
		self._slot_collision_nodes = set()
		self._serialized_tasks_cache = None
		self._displayed_list = None
		self._pprovided_args = []
		self._missing_args = []
		self._masked_installed = set()
		self._unsatisfied_deps_for_display = []
		self._unsatisfied_blockers_for_display = None
		self._circular_deps_for_display = None
		self._dep_stack = []
		self._unsatisfied_deps = []
		self._ignored_deps = []
		self._required_set_names = set(["system", "world"])
		self._select_atoms = self._select_atoms_highest_available
		self._select_package = self._select_pkg_highest_available
		self._highest_pkg_cache = {}

	def _show_slot_collision_notice(self):
		"""Show an informational message advising the user to mask one of the
		the packages. In some cases it may be possible to resolve this
		automatically, but support for backtracking (removal nodes that have
		already been selected) will be required in order to handle all possible
		cases."""

		if not self._slot_collision_info:
			return

		self._show_merge_list()

		msg = []
		msg.append("\n!!! Multiple versions within a single " + \
			"package slot have been pulled\n")
		msg.append("!!! into the dependency graph, resulting" + \
			" in a slot conflict:\n\n")
		indent = "  "
		# Max number of parents shown, to avoid flooding the display.
		max_parents = 3
		for slot_atom, root in self._slot_collision_info:
			msg.append(str(slot_atom))
			msg.append("\n\n")
			slot_nodes = []
			for node in self._slot_collision_nodes:
				if node.slot_atom == slot_atom:
					slot_nodes.append(node)
			slot_nodes.append(self._slot_pkg_map[root][slot_atom])
			for node in slot_nodes:
				msg.append(indent)
				msg.append(str(node))
				parents = self.digraph.parent_nodes(node)
				if parents:
					omitted_parents = 0
					if len(parents) > max_parents:
						pruned_list = []
						# When generating the pruned list, prefer instances
						# of DependencyArg over instances of Package.
						for parent in parents:
							if isinstance(parent, DependencyArg):
								pruned_list.append(parent)
						# Prefer Packages instances that themselves have been
						# pulled into collision slots.
						for parent in parents:
							if isinstance(parent, Package) and \
								(parent.slot_atom, parent.root) \
								in self._slot_collision_info:
								pruned_list.append(parent)
						for parent in parents:
							if len(pruned_list) >= max_parents:
								break
							if not isinstance(parent, DependencyArg) and \
								parent not in pruned_list:
								pruned_list.append(parent)
						omitted_parents = len(parents) - len(pruned_list)
						parents = pruned_list
					msg.append(" pulled in by\n")
					for parent in parents:
						msg.append(2*indent)
						msg.append(str(parent))
						msg.append("\n")
					if omitted_parents:
						msg.append(2*indent)
						msg.append("(and %d more)\n" % omitted_parents)
				else:
					msg.append(" (no parents)\n")
				msg.append("\n")
		msg.append("\n")
		sys.stderr.write("".join(msg))
		sys.stderr.flush()

		if "--quiet" in self.myopts:
			return

		msg = []
		msg.append("It may be possible to solve this problem ")
		msg.append("by using package.mask to prevent one of ")
		msg.append("those packages from being selected. ")
		msg.append("However, it is also possible that conflicting ")
		msg.append("dependencies exist such that they are impossible to ")
		msg.append("satisfy simultaneously.  If such a conflict exists in ")
		msg.append("the dependencies of two different packages, then those ")
		msg.append("packages can not be installed simultaneously.")

		from formatter import AbstractFormatter, DumbWriter
		f = AbstractFormatter(DumbWriter(sys.stderr, maxcol=72))
		for x in msg:
			f.add_flowing_data(x)
		f.end_paragraph(1)

		msg = []
		msg.append("For more information, see MASKED PACKAGES ")
		msg.append("section in the emerge man page or refer ")
		msg.append("to the Gentoo Handbook.")
		for x in msg:
			f.add_flowing_data(x)
		f.end_paragraph(1)
		f.writer.flush()

	def _reinstall_for_flags(self, forced_flags,
		orig_use, orig_iuse, cur_use, cur_iuse):
		"""Return a set of flags that trigger reinstallation, or None if there
		are no such flags."""
		if "--newuse" in self.myopts:
			flags = set(orig_iuse.symmetric_difference(
				cur_iuse).difference(forced_flags))
			flags.update(orig_iuse.intersection(orig_use).symmetric_difference(
				cur_iuse.intersection(cur_use)))
			if flags:
				return flags
		elif "changed-use" == self.myopts.get("--reinstall"):
			flags = orig_iuse.intersection(orig_use).symmetric_difference(
				cur_iuse.intersection(cur_use))
			if flags:
				return flags
		return None

	def _create_graph(self, allow_unsatisfied=False):
		dep_stack = self._dep_stack
		while dep_stack:
			self.spinner.update()
			dep = dep_stack.pop()
			if isinstance(dep, Package):
				if not self._add_pkg_deps(dep,
					allow_unsatisfied=allow_unsatisfied):
					return 0
				continue
			if not self._add_dep(dep, allow_unsatisfied=allow_unsatisfied):
				return 0
		return 1

	def _add_dep(self, dep, allow_unsatisfied=False):
		debug = "--debug" in self.myopts
		buildpkgonly = "--buildpkgonly" in self.myopts
		nodeps = "--nodeps" in self.myopts
		empty = "empty" in self.myparams
		deep = "deep" in self.myparams
		update = "--update" in self.myopts and dep.depth <= 1
		if dep.blocker:
			if not buildpkgonly and \
				not nodeps and \
				dep.parent not in self._slot_collision_nodes:
				if dep.parent.onlydeps:
					# It's safe to ignore blockers if the
					# parent is an --onlydeps node.
					return 1
				# The blocker applies to the root where
				# the parent is or will be installed.
				blocker = Blocker(atom=dep.atom, root=dep.parent.root)
				self._blocker_parents.add(blocker, dep.parent)
			return 1
		dep_pkg, existing_node = self._select_package(dep.root, dep.atom,
			onlydeps=dep.onlydeps)
		if not dep_pkg:
			if allow_unsatisfied:
				self._unsatisfied_deps.append(dep)
				return 1
			self._unsatisfied_deps_for_display.append(
				((dep.root, dep.atom), {"myparent":dep.parent}))
			return 0
		# In some cases, dep_check will return deps that shouldn't
		# be proccessed any further, so they are identified and
		# discarded here. Try to discard as few as possible since
		# discarded dependencies reduce the amount of information
		# available for optimization of merge order.
		if dep.priority.satisfied and \
			not (existing_node or empty or deep or update):
			myarg = None
			if dep.root == self.target_root:
				try:
					myarg = self._iter_atoms_for_pkg(dep_pkg).next()
				except StopIteration:
					pass
				except portage.exception.InvalidDependString:
					if not dep_pkg.installed:
						# This shouldn't happen since the package
						# should have been masked.
						raise
			if not myarg:
				self._ignored_deps.append(dep)
				return 1

		if not self._add_pkg(dep_pkg, dep.parent,
			priority=dep.priority, depth=dep.depth):
			return 0
		return 1

	def _add_pkg(self, pkg, myparent, priority=None, depth=0):
		if priority is None:
			priority = DepPriority()
		"""
		Fills the digraph with nodes comprised of packages to merge.
		mybigkey is the package spec of the package to merge.
		myparent is the package depending on mybigkey ( or None )
		addme = Should we add this package to the digraph or are we just looking at it's deps?
			Think --onlydeps, we need to ignore packages in that case.
		#stuff to add:
		#SLOT-aware emerge
		#IUSE-aware emerge -> USE DEP aware depgraph
		#"no downgrade" emerge
		"""

		# select the correct /var database that we'll be checking against
		vardbapi = self.trees[pkg.root]["vartree"].dbapi
		pkgsettings = self.pkgsettings[pkg.root]

		args = None
		arg_atoms = None
		if True:
			try:
				arg_atoms = list(self._iter_atoms_for_pkg(pkg))
			except portage.exception.InvalidDependString, e:
				if not pkg.installed:
					show_invalid_depstring_notice(
						pkg, pkg.metadata["PROVIDE"], str(e))
					return 0
				del e
			else:
				args = [arg for arg, atom in arg_atoms]

		if not pkg.onlydeps:
			if not pkg.installed and \
				"empty" not in self.myparams and \
				vardbapi.match(pkg.slot_atom):
				# Increase the priority of dependencies on packages that
				# are being rebuilt. This optimizes merge order so that
				# dependencies are rebuilt/updated as soon as possible,
				# which is needed especially when emerge is called by
				# revdep-rebuild since dependencies may be affected by ABI
				# breakage that has rendered them useless. Don't adjust
				# priority here when in "empty" mode since all packages
				# are being merged in that case.
				priority.rebuild = True

			existing_node = self._slot_pkg_map[pkg.root].get(pkg.slot_atom)
			slot_collision = False
			if existing_node:
				if pkg.cpv == existing_node.cpv:
					# The existing node can be reused.
					if args:
						for arg in args:
							self.digraph.add(existing_node, arg,
								priority=priority)
					# If a direct circular dependency is not an unsatisfied
					# buildtime dependency then drop it here since otherwise
					# it can skew the merge order calculation in an unwanted
					# way.
					if existing_node != myparent or \
						(priority.buildtime and not priority.satisfied):
						self.digraph.addnode(existing_node, myparent,
							priority=priority)
					return 1
				else:
					if pkg in self._slot_collision_nodes:
						return 1
					# A slot collision has occurred.  Sometimes this coincides
					# with unresolvable blockers, so the slot collision will be
					# shown later if there are no unresolvable blockers.
					self._slot_collision_info.add((pkg.slot_atom, pkg.root))
					self._slot_collision_nodes.add(pkg)
					slot_collision = True

			if slot_collision:
				# Now add this node to the graph so that self.display()
				# can show use flags and --tree portage.output.  This node is
				# only being partially added to the graph.  It must not be
				# allowed to interfere with the other nodes that have been
				# added.  Do not overwrite data for existing nodes in
				# self.mydbapi since that data will be used for blocker
				# validation.
				# Even though the graph is now invalid, continue to process
				# dependencies so that things like --fetchonly can still
				# function despite collisions.
				pass
			else:
				self._slot_pkg_map[pkg.root][pkg.slot_atom] = pkg
				self.mydbapi[pkg.root].cpv_inject(pkg)

			self.digraph.addnode(pkg, myparent, priority=priority)

			if not pkg.installed:
				# Allow this package to satisfy old-style virtuals in case it
				# doesn't already. Any pre-existing providers will be preferred
				# over this one.
				try:
					pkgsettings.setinst(pkg.cpv, pkg.metadata)
					# For consistency, also update the global virtuals.
					settings = self.roots[pkg.root].settings
					settings.unlock()
					settings.setinst(pkg.cpv, pkg.metadata)
					settings.lock()
				except portage.exception.InvalidDependString, e:
					show_invalid_depstring_notice(
						pkg, pkg.metadata["PROVIDE"], str(e))
					del e
					return 0

		if args:
			self._set_nodes.add(pkg)

		# Do this even when addme is False (--onlydeps) so that the
		# parent/child relationship is always known in case
		# self._show_slot_collision_notice() needs to be called later.
		if pkg.onlydeps:
			self.digraph.add(pkg, myparent, priority=priority)
		if args:
			for arg in args:
				self.digraph.add(pkg, arg, priority=priority)

		""" This section determines whether we go deeper into dependencies or not.
		    We want to go deeper on a few occasions:
		    Installing package A, we need to make sure package A's deps are met.
		    emerge --deep <pkgspec>; we need to recursively check dependencies of pkgspec
		    If we are in --nodeps (no recursion) mode, we obviously only check 1 level of dependencies.
		"""
		dep_stack = self._dep_stack
		if "recurse" not in self.myparams:
			return 1
		elif pkg.installed and \
			"deep" not in self.myparams:
			dep_stack = self._ignored_deps

		self.spinner.update()

		if args:
			depth = 0
		pkg.depth = depth
		dep_stack.append(pkg)
		return 1

	def _add_pkg_deps(self, pkg, allow_unsatisfied=False):

		mytype = pkg.type_name
		myroot = pkg.root
		mykey = pkg.cpv
		metadata = pkg.metadata
		myuse = pkg.use.enabled
		jbigkey = pkg
		depth = pkg.depth + 1

		edepend={}
		depkeys = ["DEPEND","RDEPEND","PDEPEND"]
		for k in depkeys:
			edepend[k] = metadata[k]

		if not pkg.built and \
			"--buildpkgonly" in self.myopts and \
			"deep" not in self.myparams and \
			"empty" not in self.myparams:
			edepend["RDEPEND"] = ""
			edepend["PDEPEND"] = ""
		bdeps_satisfied = False
		if mytype in ("installed", "binary"):
			if self.myopts.get("--with-bdeps", "n") == "y":
				# Pull in build time deps as requested, but marked them as
				# "satisfied" since they are not strictly required. This allows
				# more freedom in the merge order calculation for solving
				# circular dependencies. Don't convert to PDEPEND since that
				# could make --with-bdeps=y less effective if it is used to
				# adjust merge order to prevent built_with_use() calls from
				# failing.
				bdeps_satisfied = True
			else:
				# built packages do not have build time dependencies.
				edepend["DEPEND"] = ""

		deps = (
			("/", edepend["DEPEND"],
				DepPriority(buildtime=True, satisfied=bdeps_satisfied)),
			(myroot, edepend["RDEPEND"], DepPriority(runtime=True)),
			(myroot, edepend["PDEPEND"], DepPriority(runtime_post=True))
		)

		debug = "--debug" in self.myopts
		strict = mytype != "installed"
		try:
			for dep_root, dep_string, dep_priority in deps:
				if pkg.onlydeps:
					# Decrease priority so that --buildpkgonly
					# hasallzeros() works correctly.
					dep_priority = DepPriority()
				if not dep_string:
					continue
				if debug:
					print
					print "Parent:   ", jbigkey
					print "Depstring:", dep_string
					print "Priority:", dep_priority
				vardb = self.roots[dep_root].trees["vartree"].dbapi
				try:
					selected_atoms = self._select_atoms(dep_root,
						dep_string, myuse=myuse, parent=pkg, strict=strict)
				except portage.exception.InvalidDependString, e:
					show_invalid_depstring_notice(jbigkey, dep_string, str(e))
					return 0
				if debug:
					print "Candidates:", selected_atoms
				for atom in selected_atoms:
					if isinstance(atom, basestring) \
						and not portage.isvalidatom(atom):
						show_invalid_depstring_notice(
							pkg, dep_string, str(atom))
						if not pkg.installed:
							return 0
						continue
					blocker = atom.startswith("!")
					if blocker:
						atom = atom[1:]
					mypriority = dep_priority.copy()
					if not blocker and vardb.match(atom):
						mypriority.satisfied = True
					if not self._add_dep(Dependency(atom=atom,
						blocker=blocker, depth=depth, parent=pkg,
						priority=mypriority, root=dep_root),
						allow_unsatisfied=allow_unsatisfied):
						return 0
				if debug:
					print "Exiting...", jbigkey
		except ValueError, e:
			if not e.args or not isinstance(e.args[0], list) or \
				len(e.args[0]) < 2:
				raise
			pkgs = e.args[0]
			portage.writemsg("\n\n!!! An atom in the dependencies " + \
				"is not fully-qualified. Multiple matches:\n\n", noiselevel=-1)
			for cpv in pkgs:
				portage.writemsg("    %s\n" % cpv, noiselevel=-1)
			portage.writemsg("\n", noiselevel=-1)
			if mytype == "binary":
				portage.writemsg(
					"!!! This binary package cannot be installed: '%s'\n" % \
					mykey, noiselevel=-1)
			elif mytype == "ebuild":
				portdb = self.roots[myroot].trees["porttree"].dbapi
				myebuild, mylocation = portdb.findname2(mykey)
				portage.writemsg("!!! This ebuild cannot be installed: " + \
					"'%s'\n" % myebuild, noiselevel=-1)
			portage.writemsg("!!! Please notify the package maintainer " + \
				"that atoms must be fully-qualified.\n", noiselevel=-1)
			return 0
		return 1

	def _dep_expand(self, root_config, atom_without_category):
		"""
		@param root_config: a root config instance
		@type root_config: RootConfig
		@param atom_without_category: an atom without a category component
		@type atom_without_category: String
		@rtype: list
		@returns: a list of atoms containing categories (possibly empty)
		"""
		null_cp = portage.dep_getkey(insert_category_into_atom(
			atom_without_category, "null"))
		cat, atom_pn = portage.catsplit(null_cp)

		cp_set = set()
		for db, pkg_type, built, installed, db_keys in \
			self._filtered_trees[root_config.root]["dbs"]:
			cp_set.update(db.cp_all())
		for cp in list(cp_set):
			cat, pn = portage.catsplit(cp)
			if pn != atom_pn:
				cp_set.discard(cp)
		deps = []
		for cp in cp_set:
			cat, pn = portage.catsplit(cp)
			deps.append(insert_category_into_atom(
				atom_without_category, cat))
		return deps

	def _have_new_virt(self, root, atom_cp):
		ret = False
		for db, pkg_type, built, installed, db_keys in \
			self._filtered_trees[root]["dbs"]:
			if db.cp_list(atom_cp):
				ret = True
				break
		return ret

	def _iter_atoms_for_pkg(self, pkg):
		# TODO: add multiple $ROOT support
		if pkg.root != self.target_root:
			return
		atom_arg_map = self._atom_arg_map
		root_config = self.roots[pkg.root]
		for atom in self._set_atoms.iterAtomsForPackage(pkg):
			atom_cp = portage.dep_getkey(atom)
			if atom_cp != pkg.cp and \
				self._have_new_virt(pkg.root, atom_cp):
				continue
			visible_pkgs = root_config.visible_pkgs.match_pkgs(atom)
			visible_pkgs.reverse() # descending order
			higher_slot = None
			for visible_pkg in visible_pkgs:
				if visible_pkg.cp != atom_cp:
					continue
				if pkg >= visible_pkg:
					# This is descending order, and we're not
					# interested in any versions <= pkg given.
					break
				if pkg.slot_atom != visible_pkg.slot_atom:
					higher_slot = visible_pkg
					break
			if higher_slot is not None:
				continue
			for arg in atom_arg_map[(atom, pkg.root)]:
				if isinstance(arg, PackageArg) and \
					arg.package != pkg:
					continue
				yield arg, atom

	def select_files(self, myfiles):
		"""Given a list of .tbz2s, .ebuilds sets, and deps, create the
		appropriate depgraph and return a favorite list."""
		debug = "--debug" in self.myopts
		root_config = self.roots[self.target_root]
		sets = root_config.sets
		getSetAtoms = root_config.setconfig.getSetAtoms
		myfavorites=[]
		myroot = self.target_root
		dbs = self._filtered_trees[myroot]["dbs"]
		vardb = self.trees[myroot]["vartree"].dbapi
		real_vardb = self._trees_orig[myroot]["vartree"].dbapi
		portdb = self.trees[myroot]["porttree"].dbapi
		bindb = self.trees[myroot]["bintree"].dbapi
		pkgsettings = self.pkgsettings[myroot]
		args = []
		onlydeps = "--onlydeps" in self.myopts
		lookup_owners = []
		for x in myfiles:
			ext = os.path.splitext(x)[1]
			if ext==".tbz2":
				if not os.path.exists(x):
					if os.path.exists(
						os.path.join(pkgsettings["PKGDIR"], "All", x)):
						x = os.path.join(pkgsettings["PKGDIR"], "All", x)
					elif os.path.exists(
						os.path.join(pkgsettings["PKGDIR"], x)):
						x = os.path.join(pkgsettings["PKGDIR"], x)
					else:
						print "\n\n!!! Binary package '"+str(x)+"' does not exist."
						print "!!! Please ensure the tbz2 exists as specified.\n"
						return 0, myfavorites
				mytbz2=portage.xpak.tbz2(x)
				mykey=mytbz2.getelements("CATEGORY")[0]+"/"+os.path.splitext(os.path.basename(x))[0]
				if os.path.realpath(x) != \
					os.path.realpath(self.trees[myroot]["bintree"].getname(mykey)):
					print colorize("BAD", "\n*** You need to adjust PKGDIR to emerge this package.\n")
					return 0, myfavorites
				metadata = izip(self._mydbapi_keys,
					bindb.aux_get(mykey, self._mydbapi_keys))
				pkg = Package(type_name="binary", root_config=root_config,
					cpv=mykey, built=True, metadata=metadata,
					onlydeps=onlydeps)
				self._pkg_cache[pkg] = pkg
				args.append(PackageArg(arg=x, package=pkg,
					root_config=root_config))
			elif ext==".ebuild":
				ebuild_path = portage.util.normalize_path(os.path.abspath(x))
				pkgdir = os.path.dirname(ebuild_path)
				tree_root = os.path.dirname(os.path.dirname(pkgdir))
				cp = pkgdir[len(tree_root)+1:]
				e = portage.exception.PackageNotFound(
					("%s is not in a valid portage tree " + \
					"hierarchy or does not exist") % x)
				if not portage.isvalidatom(cp):
					raise e
				cat = portage.catsplit(cp)[0]
				mykey = cat + "/" + os.path.basename(ebuild_path[:-7])
				if not portage.isvalidatom("="+mykey):
					raise e
				ebuild_path = portdb.findname(mykey)
				if ebuild_path:
					if ebuild_path != os.path.join(os.path.realpath(tree_root),
						cp, os.path.basename(ebuild_path)):
						print colorize("BAD", "\n*** You need to adjust PORTDIR or PORTDIR_OVERLAY to emerge this package.\n")
						return 0, myfavorites
					if mykey not in portdb.xmatch(
						"match-visible", portage.dep_getkey(mykey)):
						print colorize("BAD", "\n*** You are emerging a masked package. It is MUCH better to use")
						print colorize("BAD", "*** /etc/portage/package.* to accomplish this. See portage(5) man")
						print colorize("BAD", "*** page for details.")
						countdown(int(self.settings["EMERGE_WARNING_DELAY"]),
							"Continuing...")
				else:
					raise portage.exception.PackageNotFound(
						"%s is not in a valid portage tree hierarchy or does not exist" % x)
				metadata = izip(self._mydbapi_keys,
					portdb.aux_get(mykey, self._mydbapi_keys))
				pkg = Package(type_name="ebuild", root_config=root_config,
					cpv=mykey, metadata=metadata, onlydeps=onlydeps)
				pkgsettings.setcpv(pkg)
				pkg.metadata["USE"] = pkgsettings["PORTAGE_USE"]
				self._pkg_cache[pkg] = pkg
				args.append(PackageArg(arg=x, package=pkg,
					root_config=root_config))
			elif x.startswith(os.path.sep):
				if not x.startswith(myroot):
					portage.writemsg(("\n\n!!! '%s' does not start with" + \
						" $ROOT.\n") % x, noiselevel=-1)
					return 0, []
				# Queue these up since it's most efficient to handle
				# multiple files in a single iter_owners() call.
				lookup_owners.append(x)
			else:
				if x in ("system", "world"):
					x = SETPREFIX + x
				if x.startswith(SETPREFIX):
					s = x[len(SETPREFIX):]
					if s not in sets:
						raise portage.exception.PackageNotFound(
							"emerge: there are no sets to satisfy '%s'." % s)
					if s in self._sets:
						continue
					# Recursively expand sets so that containment tests in
					# self._get_parent_sets() properly match atoms in nested
					# sets (like if world contains system).
					expanded_set = InternalPackageSet(
						initial_atoms=getSetAtoms(s))
					self._sets[s] = expanded_set
					args.append(SetArg(arg=x, set=expanded_set,
						root_config=root_config))
					myfavorites.append(x)
					continue
				if not is_valid_package_atom(x):
					portage.writemsg("\n\n!!! '%s' is not a valid package atom.\n" % x,
						noiselevel=-1)
					portage.writemsg("!!! Please check ebuild(5) for full details.\n")
					portage.writemsg("!!! (Did you specify a version but forget to prefix with '='?)\n")
					return (0,[])
				# Don't expand categories or old-style virtuals here unless
				# necessary. Expansion of old-style virtuals here causes at
				# least the following problems:
				#   1) It's more difficult to determine which set(s) an atom
				#      came from, if any.
				#   2) It takes away freedom from the resolver to choose other
				#      possible expansions when necessary.
				if "/" in x:
					args.append(AtomArg(arg=x, atom=x,
						root_config=root_config))
					continue
				expanded_atoms = self._dep_expand(root_config, x)
				installed_cp_set = set()
				for atom in expanded_atoms:
					atom_cp = portage.dep_getkey(atom)
					if vardb.cp_list(atom_cp):
						installed_cp_set.add(atom_cp)
				if len(expanded_atoms) > 1 and len(installed_cp_set) == 1:
					installed_cp = iter(installed_cp_set).next()
					expanded_atoms = [atom for atom in expanded_atoms \
						if portage.dep_getkey(atom) == installed_cp]

				if len(expanded_atoms) > 1:
					print "\n\n!!! The short ebuild name \"" + x + "\" is ambiguous.  Please specify"
					print "!!! one of the following fully-qualified ebuild names instead:\n"
					expanded_atoms = set(portage.dep_getkey(atom) \
						for atom in expanded_atoms)
					for i in sorted(expanded_atoms):
						print "    " + green(i)
					print
					return False, myfavorites
				if expanded_atoms:
					atom = expanded_atoms[0]
				else:
					null_atom = insert_category_into_atom(x, "null")
					null_cp = portage.dep_getkey(null_atom)
					cat, atom_pn = portage.catsplit(null_cp)
					virts_p = root_config.settings.get_virts_p().get(atom_pn)
					if virts_p:
						# Allow the depgraph to choose which virtual.
						atom = insert_category_into_atom(x, "virtual")
					else:
						atom = insert_category_into_atom(x, "null")

				args.append(AtomArg(arg=x, atom=atom,
					root_config=root_config))

		if lookup_owners:
			relative_paths = []
			search_for_multiple = False
			if len(lookup_owners) > 1:
				search_for_multiple = True

			for x in lookup_owners:
				if not search_for_multiple and os.path.isdir(x):
					search_for_multiple = True
				relative_paths.append(x[len(myroot):])

			owners = set()
			for pkg, relative_path in \
				real_vardb._owners.iter_owners(relative_paths):
				owners.add(pkg.mycpv)
				if not search_for_multiple:
					break

			if not owners:
				portage.writemsg(("\n\n!!! '%s' is not claimed " + \
					"by any package.\n") % lookup_owners[0], noiselevel=-1)
				return 0, []

			for cpv in owners:
				slot = vardb.aux_get(cpv, ["SLOT"])[0]
				if not slot:
					# portage now masks packages with missing slot, but it's
					# possible that one was installed by an older version
					atom = portage.cpv_getkey(cpv)
				else:
					atom = "%s:%s" % (portage.cpv_getkey(cpv), slot)
				args.append(AtomArg(arg=atom, atom=atom,
					root_config=root_config))

		if "--update" in self.myopts:
			# Enable greedy SLOT atoms for atoms given as arguments.
			# This is currently disabled for sets since greedy SLOT
			# atoms could be a property of the set itself.
			greedy_atoms = []
			for arg in args:
				# In addition to any installed slots, also try to pull
				# in the latest new slot that may be available.
				greedy_atoms.append(arg)
				if not isinstance(arg, (AtomArg, PackageArg)):
					continue
				atom_cp = portage.dep_getkey(arg.atom)
				slots = set()
				for cpv in vardb.match(arg.atom):
					slots.add(vardb.aux_get(cpv, ["SLOT"])[0])
				for slot in slots:
					greedy_atoms.append(
						AtomArg(arg=arg.arg, atom="%s:%s" % (atom_cp, slot),
							root_config=root_config))
			args = greedy_atoms
			del greedy_atoms

		# Create the "args" package set from atoms and
		# packages given as arguments.
		args_set = self._sets["args"]
		for arg in args:
			if not isinstance(arg, (AtomArg, PackageArg)):
				continue
			myatom = arg.atom
			if myatom in args_set:
				continue
			args_set.add(myatom)
			myfavorites.append(myatom)
		self._set_atoms.update(chain(*self._sets.itervalues()))
		atom_arg_map = self._atom_arg_map
		for arg in args:
			for atom in arg.set:
				atom_key = (atom, myroot)
				refs = atom_arg_map.get(atom_key)
				if refs is None:
					refs = []
					atom_arg_map[atom_key] = refs
					if arg not in refs:
						refs.append(arg)
		pprovideddict = pkgsettings.pprovideddict
		if debug:
			portage.writemsg("\n", noiselevel=-1)
		# Order needs to be preserved since a feature of --nodeps
		# is to allow the user to force a specific merge order.
		args.reverse()
		while args:
			arg = args.pop()
			for atom in arg.set:
				self.spinner.update()
				atom_cp = portage.dep_getkey(atom)
				try:
					pprovided = pprovideddict.get(portage.dep_getkey(atom))
					if pprovided and portage.match_from_list(atom, pprovided):
						# A provided package has been specified on the command line.
						self._pprovided_args.append((arg, atom))
						continue
					if isinstance(arg, PackageArg):
						if not self._add_pkg(arg.package, arg) or \
							not self._create_graph():
							sys.stderr.write(("\n\n!!! Problem resolving " + \
								"dependencies for %s\n") % arg.arg)
							return 0, myfavorites
						continue
					if debug:
						portage.writemsg("      Arg: %s\n     Atom: %s\n" % \
							(arg, atom), noiselevel=-1)
					pkg, existing_node = self._select_package(
						myroot, atom, onlydeps=onlydeps)
					if not pkg:
						if not (isinstance(arg, SetArg) and \
							arg.name in ("system", "world")):
							self._unsatisfied_deps_for_display.append(
								((myroot, atom), {}))
							return 0, myfavorites
						self._missing_args.append((arg, atom))
						continue
					if atom_cp != pkg.cp:
						# For old-style virtuals, we need to repeat the
						# package.provided check against the selected package.
						expanded_atom = atom.replace(atom_cp, pkg.cp)
						pprovided = pprovideddict.get(pkg.cp)
						if pprovided and \
							portage.match_from_list(expanded_atom, pprovided):
							# A provided package has been
							# specified on the command line.
							self._pprovided_args.append((arg, atom))
							continue
					if pkg.installed and "selective" not in self.myparams:
						self._unsatisfied_deps_for_display.append(
							((myroot, atom), {}))
						# Previous behavior was to bail out in this case, but
						# since the dep is satisfied by the installed package,
						# it's more friendly to continue building the graph
						# and just show a warning message. Therefore, only bail
						# out here if the atom is not from either the system or
						# world set.
						if not (isinstance(arg, SetArg) and \
							arg.name in ("system", "world")):
							return 0, myfavorites

					dep = Dependency(atom=atom, onlydeps=onlydeps,
						root=myroot, parent=arg)

					# Add the selected package to the graph as soon as possible
					# so that later dep_check() calls can use it as feedback
					# for making more consistent atom selections.
					if not self._add_pkg(pkg, dep.parent,
						priority=dep.priority, depth=dep.depth):
						if isinstance(arg, SetArg):
							sys.stderr.write(("\n\n!!! Problem resolving " + \
								"dependencies for %s from %s\n") % \
								(atom, arg.arg))
						else:
							sys.stderr.write(("\n\n!!! Problem resolving " + \
								"dependencies for %s\n") % atom)
						return 0, myfavorites

				except portage.exception.MissingSignature, e:
					portage.writemsg("\n\n!!! A missing gpg signature is preventing portage from calculating the\n")
					portage.writemsg("!!! required dependencies. This is a security feature enabled by the admin\n")
					portage.writemsg("!!! to aid in the detection of malicious intent.\n\n")
					portage.writemsg("!!! THIS IS A POSSIBLE INDICATION OF TAMPERED FILES -- CHECK CAREFULLY.\n")
					portage.writemsg("!!! Affected file: %s\n" % (e), noiselevel=-1)
					return 0, myfavorites
				except portage.exception.InvalidSignature, e:
					portage.writemsg("\n\n!!! An invalid gpg signature is preventing portage from calculating the\n")
					portage.writemsg("!!! required dependencies. This is a security feature enabled by the admin\n")
					portage.writemsg("!!! to aid in the detection of malicious intent.\n\n")
					portage.writemsg("!!! THIS IS A POSSIBLE INDICATION OF TAMPERED FILES -- CHECK CAREFULLY.\n")
					portage.writemsg("!!! Affected file: %s\n" % (e), noiselevel=-1)
					return 0, myfavorites
				except SystemExit, e:
					raise # Needed else can't exit
				except Exception, e:
					print >> sys.stderr, "\n\n!!! Problem in '%s' dependencies." % atom
					print >> sys.stderr, "!!!", str(e), getattr(e, "__module__", None)
					raise

		# Now that the root packages have been added to the graph,
		# process the dependencies.
		if not self._create_graph():
			return 0, myfavorites

		missing=0
		if "--usepkgonly" in self.myopts:
			for xs in self.digraph.all_nodes():
				if not isinstance(xs, Package):
					continue
				if len(xs) >= 4 and xs[0] != "binary" and xs[3] == "merge":
					if missing == 0:
						print
					missing += 1
					print "Missing binary for:",xs[2]

		try:
			self.altlist()
		except self._unknown_internal_error:
			return False, myfavorites

		# We're true here unless we are missing binaries.
		return (not missing,myfavorites)

	def _select_atoms_from_graph(self, *pargs, **kwargs):
		"""
		Prefer atoms matching packages that have already been
		added to the graph or those that are installed and have
		not been scheduled for replacement.
		"""
		kwargs["trees"] = self._graph_trees
		return self._select_atoms_highest_available(*pargs, **kwargs)

	def _select_atoms_highest_available(self, root, depstring,
		myuse=None, parent=None, strict=True, trees=None):
		"""This will raise InvalidDependString if necessary. If trees is
		None then self._filtered_trees is used."""
		pkgsettings = self.pkgsettings[root]
		if trees is None:
			trees = self._filtered_trees
		if True:
			try:
				if parent is not None:
					trees[root]["parent"] = parent
				if not strict:
					portage.dep._dep_check_strict = False
				mycheck = portage.dep_check(depstring, None,
					pkgsettings, myuse=myuse,
					myroot=root, trees=trees)
			finally:
				if parent is not None:
					trees[root].pop("parent")
				portage.dep._dep_check_strict = True
			if not mycheck[0]:
				raise portage.exception.InvalidDependString(mycheck[1])
			selected_atoms = mycheck[1]
		return selected_atoms

	def _show_unsatisfied_dep(self, root, atom, myparent=None, arg=None):
		atom = portage.dep.Atom(atom)
		atom_without_use = atom
		if atom.use:
			atom_without_use = portage.dep.remove_slot(atom)
			if atom.slot:
				atom_without_use += ":" + atom.slot
			atom_without_use = portage.dep.Atom(atom_without_use)
		xinfo = '"%s"' % atom
		if arg:
			xinfo='"%s"' % arg
		# Discard null/ from failed cpv_expand category expansion.
		xinfo = xinfo.replace("null/", "")
		if myparent:
			xfrom = '(dependency required by '+ \
				green('"%s"' % myparent[2]) + \
				red(' [%s]' % myparent[0]) + ')'
		masked_packages = []
		missing_use = []
		missing_licenses = []
		have_eapi_mask = False
		pkgsettings = self.pkgsettings[root]
		implicit_iuse = pkgsettings._get_implicit_iuse()
		root_config = self.roots[root]
		portdb = self.roots[root].trees["porttree"].dbapi
		dbs = self._filtered_trees[root]["dbs"]
		for db, pkg_type, built, installed, db_keys in dbs:
			if installed:
				continue
			match = db.match
			if hasattr(db, "xmatch"):
				cpv_list = db.xmatch("match-all", atom_without_use)
			else:
				cpv_list = db.match(atom_without_use)
			# descending order
			cpv_list.reverse()
			for cpv in cpv_list:
				metadata, mreasons  = get_mask_info(root_config, cpv,
					pkgsettings, db, pkg_type, built, installed, db_keys)
				if atom.use and not mreasons:
					missing_use.append(Package(built=built, cpv=cpv,
						installed=installed, metadata=metadata,
						root_config=root_config))
				else:
					masked_packages.append(
						(root_config, pkgsettings, cpv, metadata, mreasons))

		missing_use_reasons = []
		missing_iuse_reasons = []
		for pkg in missing_use:
			use = pkg.use.enabled
			iuse = implicit_iuse.union(re.escape(x) for x in pkg.iuse.all)
			iuse_re = re.compile("^(%s)$" % "|".join(iuse))
			missing_iuse = []
			for x in atom.use.required:
				if iuse_re.match(x) is None:
					missing_iuse.append(x)
			mreasons = []
			if missing_iuse:
				mreasons.append("Missing IUSE: %s" % " ".join(missing_iuse))
				missing_iuse_reasons.append((pkg, mreasons))
			else:
				need_enable = sorted(atom.use.enabled.difference(use))
				need_disable = sorted(atom.use.disabled.intersection(use))
				if need_enable or need_disable:
					changes = []
					changes.extend(colorize("red", "+" + x) \
						for x in need_enable)
					changes.extend(colorize("blue", "-" + x) \
						for x in need_disable)
					mreasons.append("Change USE: %s" % " ".join(changes))
					missing_use_reasons.append((pkg, mreasons))

		if missing_iuse_reasons and not missing_use_reasons:
			missing_use_reasons = missing_iuse_reasons
		elif missing_use_reasons:
			# Only show the latest version.
			del missing_use_reasons[1:]

		if missing_use_reasons:
			print "\nemerge: there are no ebuilds built with USE flags to satisfy "+green(xinfo)+"."
			print "!!! One of the following packages is required to complete your request:"
			for pkg, mreasons in missing_use_reasons:
				print "- "+pkg.cpv+" ("+", ".join(mreasons)+")"

		elif masked_packages:
			print "\n!!! "+red("All ebuilds that could satisfy ")+green(xinfo)+red(" have been masked.")
			print "!!! One of the following masked packages is required to complete your request:"
			have_eapi_mask = show_masked_packages(masked_packages)
			if have_eapi_mask:
				print
				msg = ("The current version of portage supports " + \
					"EAPI '%s'. You must upgrade to a newer version" + \
					" of portage before EAPI masked packages can" + \
					" be installed.") % portage.const.EAPI
				from textwrap import wrap
				for line in wrap(msg, 75):
					print line
			print
			show_mask_docs()
		else:
			print "\nemerge: there are no ebuilds to satisfy "+green(xinfo)+"."
		if myparent:
			print xfrom
		print

	def _select_pkg_highest_available(self, root, atom, onlydeps=False):
		cache_key = (root, atom, onlydeps)
		ret = self._highest_pkg_cache.get(cache_key)
		if ret is not None:
			pkg, existing = ret
			if pkg and not existing:
				existing = self._slot_pkg_map[root].get(pkg.slot_atom)
				if existing and existing == pkg:
					# Update the cache to reflect that the
					# package has been added to the graph.
					ret = pkg, pkg
					self._highest_pkg_cache[cache_key] = ret
			return ret
		ret = self._select_pkg_highest_available_imp(root, atom, onlydeps=onlydeps)
		self._highest_pkg_cache[cache_key] = ret
		return ret

	def _select_pkg_highest_available_imp(self, root, atom, onlydeps=False):
		root_config = self.roots[root]
		pkgsettings = self.pkgsettings[root]
		dbs = self._filtered_trees[root]["dbs"]
		vardb = self.roots[root].trees["vartree"].dbapi
		portdb = self.roots[root].trees["porttree"].dbapi
		# List of acceptable packages, ordered by type preference.
		matched_packages = []
		highest_version = None
		if not isinstance(atom, portage.dep.Atom):
			atom = portage.dep.Atom(atom)
		atom_cp = atom.cp
		existing_node = None
		myeb = None
		usepkgonly = "--usepkgonly" in self.myopts
		empty = "empty" in self.myparams
		selective = "selective" in self.myparams
		reinstall = False
		noreplace = "--noreplace" in self.myopts
		# Behavior of the "selective" parameter depends on
		# whether or not a package matches an argument atom.
		# If an installed package provides an old-style
		# virtual that is no longer provided by an available
		# package, the installed package may match an argument
		# atom even though none of the available packages do.
		# Therefore, "selective" logic does not consider
		# whether or not an installed package matches an
		# argument atom. It only considers whether or not
		# available packages match argument atoms, which is
		# represented by the found_available_arg flag.
		found_available_arg = False
		for find_existing_node in True, False:
			if existing_node:
				break
			for db, pkg_type, built, installed, db_keys in dbs:
				if existing_node:
					break
				if installed and not find_existing_node:
					want_reinstall = reinstall or empty or \
						(found_available_arg and not selective)
					if want_reinstall and matched_packages:
						continue
				if hasattr(db, "xmatch"):
					cpv_list = db.xmatch("match-all", atom)
				else:
					cpv_list = db.match(atom)

				# USE=multislot can make an installed package appear as if
				# it doesn't satisfy a slot dependency. Rebuilding the ebuild
				# won't do any good as long as USE=multislot is enabled since
				# the newly built package still won't have the expected slot.
				# Therefore, assume that such SLOT dependencies are already
				# satisfied rather than forcing a rebuild.
				if installed and not cpv_list and atom.slot:
					for cpv in db.match(atom.cp):
						slot_available = False
						for other_db, other_type, other_built, \
							other_installed, other_keys in dbs:
							try:
								if atom.slot == \
									other_db.aux_get(cpv, ["SLOT"])[0]:
									slot_available = True
									break
							except KeyError:
								pass
						if not slot_available:
							continue
						inst_pkg = self._pkg(cpv, "installed",
							root_config, installed=installed)
						# Remove the slot from the atom and verify that
						# the package matches the resulting atom.
						atom_without_slot = portage.dep.remove_slot(atom)
						if atom.use:
							atom_without_slot += str(atom.use)
						atom_without_slot = portage.dep.Atom(atom_without_slot)
						if portage.match_from_list(
							atom_without_slot, [inst_pkg]):
							cpv_list = [inst_pkg.cpv]
						break

				if not cpv_list:
					continue
				pkg_status = "merge"
				if installed or onlydeps:
					pkg_status = "nomerge"
				# descending order
				cpv_list.reverse()
				for cpv in cpv_list:
					# Make --noreplace take precedence over --newuse.
					if not installed and noreplace and \
						cpv in vardb.match(atom):
						# If the installed version is masked, it may
						# be necessary to look at lower versions,
						# in case there is a visible downgrade.
						continue
					reinstall_for_flags = None
					cache_key = (pkg_type, root, cpv, pkg_status)
					calculated_use = True
					pkg = self._pkg_cache.get(cache_key)
					if pkg is None:
						calculated_use = False
						try:
							metadata = izip(self._mydbapi_keys,
								db.aux_get(cpv, self._mydbapi_keys))
						except KeyError:
							continue
						pkg = Package(built=built, cpv=cpv,
							installed=installed, metadata=metadata,
							onlydeps=onlydeps, root_config=root_config,
							type_name=pkg_type)
						metadata = pkg.metadata
						if not built and ("?" in metadata["LICENSE"] or \
							"?" in metadata["PROVIDE"]):
							# This is avoided whenever possible because
							# it's expensive. It only needs to be done here
							# if it has an effect on visibility.
							pkgsettings.setcpv(pkg)
							metadata["USE"] = pkgsettings["PORTAGE_USE"]
							calculated_use = True
						self._pkg_cache[pkg] = pkg

					if not installed or (installed and matched_packages):
						# Only enforce visibility on installed packages
						# if there is at least one other visible package
						# available. By filtering installed masked packages
						# here, packages that have been masked since they
						# were installed can be automatically downgraded
						# to an unmasked version.
						try:
							if not visible(pkgsettings, pkg):
								continue
						except portage.exception.InvalidDependString:
							if not installed:
								continue

						# Enable upgrade or downgrade to a version
						# with visible KEYWORDS when the installed
						# version is masked by KEYWORDS, but never
						# reinstall the same exact version only due
						# to a KEYWORDS mask.
						if installed and matched_packages and \
							pkgsettings._getMissingKeywords(
							pkg.cpv, pkg.metadata):
							different_version = None
							for avail_pkg in matched_packages:
								if not portage.dep.cpvequal(
									pkg.cpv, avail_pkg.cpv):
									different_version = avail_pkg
									break
							if different_version is not None:
								# Only reinstall for KEYWORDS if
								# it's not the same version.
								continue

					if not pkg.built and not calculated_use:
						# This is avoided whenever possible because
						# it's expensive.
						pkgsettings.setcpv(pkg)
						pkg.metadata["USE"] = pkgsettings["PORTAGE_USE"]

					myarg = None
					if root == self.target_root:
						try:
							# Ebuild USE must have been calculated prior
							# to this point, in case atoms have USE deps.
							myarg = self._iter_atoms_for_pkg(pkg).next()
						except StopIteration:
							pass
						except portage.exception.InvalidDependString:
							if not installed:
								# masked by corruption
								continue
					if not installed and myarg:
						found_available_arg = True

					if atom.use and not pkg.built:
						use = pkg.use.enabled
						if atom.use.enabled.difference(use):
							continue
						if atom.use.disabled.intersection(use):
							continue
					if pkg.cp == atom_cp:
						if highest_version is None:
							highest_version = pkg
						elif pkg > highest_version:
							highest_version = pkg
					# At this point, we've found the highest visible
					# match from the current repo. Any lower versions
					# from this repo are ignored, so this so the loop
					# will always end with a break statement below
					# this point.
					if find_existing_node:
						e_pkg = self._slot_pkg_map[root].get(pkg.slot_atom)
						if not e_pkg:
							break
						if portage.dep.match_from_list(atom, [e_pkg]):
							if highest_version and \
								e_pkg.cp == atom_cp and \
								e_pkg < highest_version and \
								e_pkg.slot_atom != highest_version.slot_atom:
								# There is a higher version available in a
								# different slot, so this existing node is
								# irrelevant.
								pass
							else:
								matched_packages.append(e_pkg)
								existing_node = e_pkg
						break
					# Compare built package to current config and
					# reject the built package if necessary.
					if built and not installed and \
						("--newuse" in self.myopts or \
						"--reinstall" in self.myopts):
						iuses = pkg.iuse.all
						old_use = pkg.use.enabled
						if myeb:
							pkgsettings.setcpv(myeb)
						else:
							pkgsettings.setcpv(pkg)
						now_use = pkgsettings["PORTAGE_USE"].split()
						forced_flags = set()
						forced_flags.update(pkgsettings.useforce)
						forced_flags.update(pkgsettings.usemask)
						cur_iuse = iuses
						if myeb and not usepkgonly:
							cur_iuse = myeb.iuse.all
						if self._reinstall_for_flags(forced_flags,
							old_use, iuses,
							now_use, cur_iuse):
							break
					# Compare current config to installed package
					# and do not reinstall if possible.
					if not installed and \
						("--newuse" in self.myopts or \
						"--reinstall" in self.myopts) and \
						cpv in vardb.match(atom):
						pkgsettings.setcpv(pkg)
						forced_flags = set()
						forced_flags.update(pkgsettings.useforce)
						forced_flags.update(pkgsettings.usemask)
						old_use = vardb.aux_get(cpv, ["USE"])[0].split()
						old_iuse = set(filter_iuse_defaults(
							vardb.aux_get(cpv, ["IUSE"])[0].split()))
						cur_use = pkgsettings["PORTAGE_USE"].split()
						cur_iuse = pkg.iuse.all
						reinstall_for_flags = \
							self._reinstall_for_flags(
							forced_flags, old_use, old_iuse,
							cur_use, cur_iuse)
						if reinstall_for_flags:
							reinstall = True
					if not built:
						myeb = pkg
					matched_packages.append(pkg)
					if reinstall_for_flags:
						self._reinstall_nodes[pkg] = \
							reinstall_for_flags
					break

		if not matched_packages:
			return None, None

		if "--debug" in self.myopts:
			for pkg in matched_packages:
				portage.writemsg("%s %s\n" % \
					((pkg.type_name + ":").rjust(10), pkg.cpv), noiselevel=-1)

		# Filter out any old-style virtual matches if they are
		# mixed with new-style virtual matches.
		cp = portage.dep_getkey(atom)
		if len(matched_packages) > 1 and \
			"virtual" == portage.catsplit(cp)[0]:
			for pkg in matched_packages:
				if pkg.cp != cp:
					continue
				# Got a new-style virtual, so filter
				# out any old-style virtuals.
				matched_packages = [pkg for pkg in matched_packages \
					if pkg.cp == cp]
				break

		if len(matched_packages) > 1:
			bestmatch = portage.best(
				[pkg.cpv for pkg in matched_packages])
			matched_packages = [pkg for pkg in matched_packages \
				if portage.dep.cpvequal(pkg.cpv, bestmatch)]

		# ordered by type preference ("ebuild" type is the last resort)
		return  matched_packages[-1], existing_node

	def _select_pkg_from_graph(self, root, atom, onlydeps=False):
		"""
		Select packages that have already been added to the graph or
		those that are installed and have not been scheduled for
		replacement.
		"""
		graph_db = self._graph_trees[root]["porttree"].dbapi
		matches = graph_db.match(atom)
		if not matches:
			return None, None
		cpv = matches[-1] # highest match
		slot_atom = "%s:%s" % (portage.cpv_getkey(cpv),
			graph_db.aux_get(cpv, ["SLOT"])[0])
		e_pkg = self._slot_pkg_map[root].get(slot_atom)
		if e_pkg:
			return e_pkg, e_pkg
		# Since this cpv exists in the graph_db,
		# we must have a cached Package instance.
		cache_key = ("installed", root, cpv, "nomerge")
		return (self._pkg_cache[cache_key], None)

	def _complete_graph(self):
		"""
		Add any deep dependencies of required sets (args, system, world) that
		have not been pulled into the graph yet. This ensures that the graph
		is consistent such that initially satisfied deep dependencies are not
		broken in the new graph. Initially unsatisfied dependencies are
		irrelevant since we only want to avoid breaking dependencies that are
		intially satisfied.

		Since this method can consume enough time to disturb users, it is
		currently only enabled by the --complete-graph option, or when
		dep calculation time exceeds self._complete_threshold.
		"""
		if "--buildpkgonly" in self.myopts or \
			"recurse" not in self.myparams:
			return 1

		if "complete" not in self.myparams:
			if time.time() - self._creation_time > self._complete_threshold:
				self.myparams.add("complete")
			else:
				# Skip this to avoid consuming enough time to disturb users.
				return 1

		# Put the depgraph into a mode that causes it to only
		# select packages that have already been added to the
		# graph or those that are installed and have not been
		# scheduled for replacement. Also, toggle the "deep"
		# parameter so that all dependencies are traversed and
		# accounted for.
		self._select_atoms = self._select_atoms_from_graph
		self._select_package = self._select_pkg_from_graph
		already_deep = "deep" in self.myparams
		if not already_deep:
			self.myparams.add("deep")

		for root in self.roots:
			required_set_names = self._required_set_names.copy()
			if root == self.target_root and \
				(already_deep or "empty" in self.myparams):
				required_set_names.difference_update(self._sets)
			if not required_set_names and not self._ignored_deps:
				continue
			root_config = self.roots[root]
			setconfig = root_config.setconfig
			args = []
			# Reuse existing SetArg instances when available.
			for arg in self.digraph.root_nodes():
				if not isinstance(arg, SetArg):
					continue
				if arg.root_config != root_config:
					continue
				if arg.name in required_set_names:
					args.append(arg)
					required_set_names.remove(arg.name)
			# Create new SetArg instances only when necessary.
			for s in required_set_names:
				expanded_set = InternalPackageSet(
					initial_atoms=setconfig.getSetAtoms(s))
				atom = SETPREFIX + s
				args.append(SetArg(arg=atom, set=expanded_set,
					root_config=root_config))
			vardb = root_config.trees["vartree"].dbapi
			for arg in args:
				for atom in arg.set:
					self._dep_stack.append(
						Dependency(atom=atom, root=root, parent=arg))
			if self._ignored_deps:
				self._dep_stack.extend(self._ignored_deps)
				self._ignored_deps = []
			if not self._create_graph(allow_unsatisfied=True):
				return 0
			# Check the unsatisfied deps to see if any initially satisfied deps
			# will become unsatisfied due to an upgrade. Initially unsatisfied
			# deps are irrelevant since we only want to avoid breaking deps
			# that are initially satisfied.
			while self._unsatisfied_deps:
				dep = self._unsatisfied_deps.pop()
				matches = vardb.match_pkgs(dep.atom)
				if not matches:
					# Initially unsatisfied.
					continue
				# An scheduled installation broke a deep dependency.
				# Add the installed package to the graph so that it
				# will be appropriately reported as a slot collision
				# (possibly solvable via backtracking).
				pkg = matches[-1] # highest match
				if not self._add_pkg(pkg, dep.parent,
					priority=dep.priority, depth=dep.depth):
					return 0
				if not self._create_graph(allow_unsatisfied=True):
					return 0
		return 1

	def _pkg(self, cpv, type_name, root_config, installed=False):
		"""
		Get a package instance from the cache, or create a new
		one if necessary. Raises KeyError from aux_get if it
		failures for some reason (package does not exist or is
		corrupt).
		"""
		operation = "merge"
		if installed:
			operation = "nomerge"
		pkg = self._pkg_cache.get(
			(type_name, root_config.root, cpv, operation))
		if pkg is None:
			db = root_config.trees[
				self.pkg_tree_map[type_name]].dbapi
			metadata = izip(Package.metadata_keys,
				db.aux_get(cpv, Package.metadata_keys))
			pkg = Package(cpv=cpv, metadata=metadata,
				root_config=root_config, installed=installed)
			if type_name == "ebuild":
				settings = self.pkgsettings[root_config.root]
				settings.setcpv(pkg)
				pkg.metadata["USE"] = settings["PORTAGE_USE"]
			self._pkg_cache[pkg] = pkg
		return pkg

	def validate_blockers(self):
		"""Remove any blockers from the digraph that do not match any of the
		packages within the graph.  If necessary, create hard deps to ensure
		correct merge order such that mutually blocking packages are never
		installed simultaneously."""

		if "--buildpkgonly" in self.myopts or \
			"--nodeps" in self.myopts:
			return True

		#if "deep" in self.myparams:
		if True:
			# Pull in blockers from all installed packages that haven't already
			# been pulled into the depgraph.  This is not enabled by default
			# due to the performance penalty that is incurred by all the
			# additional dep_check calls that are required.

			dep_keys = ["DEPEND","RDEPEND","PDEPEND"]
			for myroot in self.trees:
				vardb = self.trees[myroot]["vartree"].dbapi
				portdb = self.trees[myroot]["porttree"].dbapi
				pkgsettings = self.pkgsettings[myroot]
				final_db = self.mydbapi[myroot]

				graph_complete_for_root = "complete" in self.myparams or \
					(myroot == self.target_root and \
					("deep" in self.myparams or "empty" in self.myparams) and \
					not self._required_set_names.difference(self._sets))

				blocker_cache = BlockerCache(myroot, vardb)
				stale_cache = set(blocker_cache)
				for pkg in vardb:
					cpv = pkg.cpv
					stale_cache.discard(cpv)
					pkg_in_graph = self.digraph.contains(pkg)

					# Check for masked installed packages. For keyword
					# mask there are a couple of common cases that are
					# likely to generate unwanted noise:
					#
					#  * Packages missing /var/db/pkg/*/*/KEYWORDS entries
					#    due to having been installed by an old version of
					#    portage.
					#
					#  * Packages installed by overriding ACCEPT_KEYWORDS
					#    via the environment.
					#
					# To avoid unwanted noise, only warn about keyword
					# masks if all of the following are true:
					#
					#  * KEYWORDS is not empty (not installed by old portage).
					#
					#  * The graph is complete and the package has not been
					#    pulled into the dependency graph. It's eligible for
					#    depclean, but depclean may fail to recognize it as
					#    such due to differences in visibility filtering which
					#    can lead to differences in || dep evaluation.
					#    TODO: Share visibility code to fix this inconsistency.

					if pkg in final_db:
						if pkg_in_graph and not visible(pkgsettings, pkg):
							self._masked_installed.add(pkg)
						elif graph_complete_for_root and \
							pkgsettings._getMissingKeywords(
							pkg.cpv, pkg.metadata) and \
							pkg.metadata["KEYWORDS"].split() and \
							not pkg_in_graph:
							try:
								ebuild = self._pkg(pkg.cpv,
									"ebuild", pkg.root_config)
							except KeyError:
								ebuild = None
							else:
								try:
									if not visible(pkgsettings, ebuild):
										ebuild = None
								except portage.exception.InvalidDependString:
									ebuild = None
							if ebuild is None:
								self._masked_installed.add(pkg)

					blocker_atoms = None
					blockers = None
					if pkg_in_graph:
						blockers = []
						try:
							blockers.extend(
								self._blocker_parents.child_nodes(pkg))
						except KeyError:
							pass
						try:
							blockers.extend(
								self._irrelevant_blockers.child_nodes(pkg))
						except KeyError:
							pass
					if blockers is not None:
						blockers = set("!" + blocker.atom \
							for blocker in blockers)

					# If this node has any blockers, create a "nomerge"
					# node for it so that they can be enforced.
					self.spinner.update()
					blocker_data = blocker_cache.get(cpv)
					if blocker_data is not None and \
						blocker_data.counter != long(pkg.metadata["COUNTER"]):
						blocker_data = None

					# If blocker data from the graph is available, use
					# it to validate the cache and update the cache if
					# it seems invalid.
					if blocker_data is not None and \
						blockers is not None:
						if not blockers.symmetric_difference(
							blocker_data.atoms):
							continue
						blocker_data = None

					if blocker_data is None and \
						blockers is not None:
						# Re-use the blockers from the graph.
						blocker_atoms = sorted(blockers)
						counter = long(pkg.metadata["COUNTER"])
						blocker_data = \
							blocker_cache.BlockerData(counter, blocker_atoms)
						blocker_cache[pkg.cpv] = blocker_data
						continue

					if blocker_data:
						blocker_atoms = blocker_data.atoms
					else:
						# Use aux_get() to trigger FakeVartree global
						# updates on *DEPEND when appropriate.
						depstr = " ".join(vardb.aux_get(pkg.cpv, dep_keys))
						# It is crucial to pass in final_db here in order to
						# optimize dep_check calls by eliminating atoms via
						# dep_wordreduce and dep_eval calls.
						try:
							portage.dep._dep_check_strict = False
							try:
								success, atoms = portage.dep_check(depstr,
									final_db, pkgsettings, myuse=pkg.use.enabled,
									trees=self._graph_trees, myroot=myroot)
							except Exception, e:
								if isinstance(e, SystemExit):
									raise
								# This is helpful, for example, if a ValueError
								# is thrown from cpv_expand due to multiple
								# matches (this can happen if an atom lacks a
								# category).
								show_invalid_depstring_notice(
									pkg, depstr, str(e))
								del e
								raise
						finally:
							portage.dep._dep_check_strict = True
						if not success:
							replacement_pkg = final_db.match_pkgs(pkg.slot_atom)
							if replacement_pkg and \
								replacement_pkg[0].operation == "merge":
								# This package is being replaced anyway, so
								# ignore invalid dependencies so as not to
								# annoy the user too much (otherwise they'd be
								# forced to manually unmerge it first).
								continue
							show_invalid_depstring_notice(pkg, depstr, atoms)
							return False
						blocker_atoms = [myatom for myatom in atoms \
							if myatom.startswith("!")]
						blocker_atoms.sort()
						counter = long(pkg.metadata["COUNTER"])
						blocker_cache[cpv] = \
							blocker_cache.BlockerData(counter, blocker_atoms)
					if blocker_atoms:
						for myatom in blocker_atoms:
							blocker = Blocker(atom=myatom[1:], root=myroot)
							self._blocker_parents.add(blocker, pkg)
				for cpv in stale_cache:
					del blocker_cache[cpv]
				blocker_cache.flush()
				del blocker_cache

		# Discard any "uninstall" tasks scheduled by previous calls
		# to this method, since those tasks may not make sense given
		# the current graph state.
		previous_uninstall_tasks = self._blocker_uninstalls.leaf_nodes()
		if previous_uninstall_tasks:
			self._blocker_uninstalls = digraph()
			self.digraph.difference_update(previous_uninstall_tasks)

		for blocker in self._blocker_parents.leaf_nodes():
			self.spinner.update()
			root_config = self.roots[blocker.root]
			virtuals = root_config.settings.getvirtuals()
			mytype, myroot, mydep = blocker
			initial_db = self.trees[myroot]["vartree"].dbapi
			final_db = self.mydbapi[myroot]
			
			provider_virtual = False
			if blocker.cp in virtuals and \
				not self._have_new_virt(blocker.root, blocker.cp):
				provider_virtual = True

			if provider_virtual:
				atoms = []
				for provider_entry in virtuals[blocker.cp]:
					provider_cp = \
						portage.dep_getkey(provider_entry)
					atoms.append(blocker.atom.replace(
						blocker.cp, provider_cp))
			else:
				atoms = [blocker.atom]

			blocked_initial = []
			for atom in atoms:
				blocked_initial.extend(initial_db.match_pkgs(atom))

			blocked_final = []
			for atom in atoms:
				blocked_final.extend(final_db.match_pkgs(atom))

			if not blocked_initial and not blocked_final:
				parent_pkgs = self._blocker_parents.parent_nodes(blocker)
				self._blocker_parents.remove(blocker)
				# Discard any parents that don't have any more blockers.
				for pkg in parent_pkgs:
					self._irrelevant_blockers.add(blocker, pkg)
					if not self._blocker_parents.child_nodes(pkg):
						self._blocker_parents.remove(pkg)
				continue
			for parent in self._blocker_parents.parent_nodes(blocker):
				unresolved_blocks = False
				depends_on_order = set()
				for pkg in blocked_initial:
					if pkg.slot_atom == parent.slot_atom:
						# TODO: Support blocks within slots in cases where it
						# might make sense.  For example, a new version might
						# require that the old version be uninstalled at build
						# time.
						continue
					if parent.installed:
						# Two currently installed packages conflict with
						# eachother. Ignore this case since the damage
						# is already done and this would be likely to
						# confuse users if displayed like a normal blocker.
						continue
					if parent.operation == "merge":
						# Maybe the blocked package can be replaced or simply
						# unmerged to resolve this block.
						depends_on_order.add((pkg, parent))
						continue
					# None of the above blocker resolutions techniques apply,
					# so apparently this one is unresolvable.
					unresolved_blocks = True
				for pkg in blocked_final:
					if pkg.slot_atom == parent.slot_atom:
						# TODO: Support blocks within slots.
						continue
					if parent.operation == "nomerge" and \
						pkg.operation == "nomerge":
						# This blocker will be handled the next time that a
						# merge of either package is triggered.
						continue

					# Maybe the blocking package can be
					# unmerged to resolve this block.
					if parent.operation == "merge" and pkg.installed:
						depends_on_order.add((pkg, parent))
						continue
					elif parent.operation == "nomerge":
						depends_on_order.add((parent, pkg))
						continue
					# None of the above blocker resolutions techniques apply,
					# so apparently this one is unresolvable.
					unresolved_blocks = True

				# Make sure we don't unmerge any package that have been pulled
				# into the graph.
				if not unresolved_blocks and depends_on_order:
					for inst_pkg, inst_task in depends_on_order:
						if self.digraph.contains(inst_pkg) and \
							self.digraph.parent_nodes(inst_pkg):
							unresolved_blocks = True
							break

				if not unresolved_blocks and depends_on_order:
					for inst_pkg, inst_task in depends_on_order:
						uninst_task = Package(built=inst_pkg.built,
							cpv=inst_pkg.cpv, installed=inst_pkg.installed,
							metadata=inst_pkg.metadata,
							operation="uninstall",
							root_config=inst_pkg.root_config,
							type_name=inst_pkg.type_name)
						self._pkg_cache[uninst_task] = uninst_task
						# Enforce correct merge order with a hard dep.
						self.digraph.addnode(uninst_task, inst_task,
							priority=BlockerDepPriority.instance)
						# Count references to this blocker so that it can be
						# invalidated after nodes referencing it have been
						# merged.
						self._blocker_uninstalls.addnode(uninst_task, blocker)
				if not unresolved_blocks and not depends_on_order:
					self._irrelevant_blockers.add(blocker, parent)
					self._blocker_parents.remove_edge(blocker, parent)
					if not self._blocker_parents.parent_nodes(blocker):
						self._blocker_parents.remove(blocker)
					if not self._blocker_parents.child_nodes(parent):
						self._blocker_parents.remove(parent)
				if unresolved_blocks:
					self._unsolvable_blockers.add(blocker, parent)

		return True

	def _accept_blocker_conflicts(self):
		acceptable = False
		for x in ("--buildpkgonly", "--fetchonly",
			"--fetch-all-uri", "--nodeps", "--pretend"):
			if x in self.myopts:
				acceptable = True
				break
		return acceptable

	def _merge_order_bias(self, mygraph):
		"""Order nodes from highest to lowest overall reference count for
		optimal leaf node selection."""
		node_info = {}
		for node in mygraph.order:
			node_info[node] = len(mygraph.parent_nodes(node))
		def cmp_merge_preference(node1, node2):
			return node_info[node2] - node_info[node1]
		mygraph.order.sort(cmp_merge_preference)

	def altlist(self, reversed=False):

		while self._serialized_tasks_cache is None:
			self._resolve_conflicts()
			try:
				self._serialized_tasks_cache = self._serialize_tasks()
			except self._serialize_tasks_retry:
				pass

		retlist = self._serialized_tasks_cache[:]
		if reversed:
			retlist.reverse()
		return retlist

	def break_refs(self, nodes):
		"""
		Take a mergelist like that returned from self.altlist() and
		break any references that lead back to the depgraph. This is
		useful if you want to hold references to packages without
		also holding the depgraph on the heap.
		"""
		for node in nodes:
			if hasattr(node, "root_config"):
				# The FakeVartree references the _package_cache which
				# references the depgraph. So that Package instances don't
				# hold the depgraph and FakeVartree on the heap, replace
				# the RootConfig that references the FakeVartree with the
				# original RootConfig instance which references the actual
				# vartree.
				node.root_config = \
					self._trees_orig[node.root_config.root]["root_config"]

	def _resolve_conflicts(self):
		if not self._complete_graph():
			raise self._unknown_internal_error()

		if not self.validate_blockers():
			raise self._unknown_internal_error()

	def _serialize_tasks(self):
		mygraph=self.digraph.copy()
		# Prune "nomerge" root nodes if nothing depends on them, since
		# otherwise they slow down merge order calculation. Don't remove
		# non-root nodes since they help optimize merge order in some cases
		# such as revdep-rebuild.
		removed_nodes = set()
		while True:
			for node in mygraph.root_nodes():
				if not isinstance(node, Package) or \
					node.installed or node.onlydeps:
					removed_nodes.add(node)
			if removed_nodes:
				self.spinner.update()
				mygraph.difference_update(removed_nodes)
			if not removed_nodes:
				break
			removed_nodes.clear()
		self._merge_order_bias(mygraph)
		def cmp_circular_bias(n1, n2):
			"""
			RDEPEND is stronger than PDEPEND and this function
			measures such a strength bias within a circular
			dependency relationship.
			"""
			n1_n2_medium = n2 in mygraph.child_nodes(n1,
				ignore_priority=DepPriority.MEDIUM_SOFT)
			n2_n1_medium = n1 in mygraph.child_nodes(n2,
				ignore_priority=DepPriority.MEDIUM_SOFT)
			if n1_n2_medium == n2_n1_medium:
				return 0
			elif n1_n2_medium:
				return 1
			return -1
		myblocker_uninstalls = self._blocker_uninstalls.copy()
		retlist=[]
		# Contains uninstall tasks that have been scheduled to
		# occur after overlapping blockers have been installed.
		scheduled_uninstalls = set()
		# Contains any Uninstall tasks that have been ignored
		# in order to avoid the circular deps code path. These
		# correspond to blocker conflicts that could not be
		# resolved.
		ignored_uninstall_tasks = set()
		have_uninstall_task = False
		complete = "complete" in self.myparams
		myblocker_parents = self._blocker_parents.copy()
		asap_nodes = []

		def get_nodes(**kwargs):
			"""
			Returns leaf nodes excluding Uninstall instances
			since those should be executed as late as possible.
			"""
			return [node for node in mygraph.leaf_nodes(**kwargs) \
				if isinstance(node, Package) and \
					(node.operation != "uninstall" or \
					node in scheduled_uninstalls)]

		# sys-apps/portage needs special treatment if ROOT="/"
		running_root = "/"
		from portage.const import PORTAGE_PACKAGE_ATOM
		runtime_deps = InternalPackageSet(
			initial_atoms=[PORTAGE_PACKAGE_ATOM])
		running_portage = self.trees[running_root]["vartree"].dbapi.match_pkgs(
			PORTAGE_PACKAGE_ATOM)
		replacement_portage = self.mydbapi[running_root].match_pkgs(
			PORTAGE_PACKAGE_ATOM)

		if running_portage:
			running_portage = running_portage[0]
		else:
			running_portage = None

		if replacement_portage:
			replacement_portage = replacement_portage[0]
		else:
			replacement_portage = None

		if replacement_portage == running_portage:
			replacement_portage = None

		if replacement_portage is not None:
			# update from running_portage to replacement_portage asap
			asap_nodes.append(replacement_portage)

		if running_portage is not None:
			try:
				portage_rdepend = self._select_atoms_highest_available(
					running_root, running_portage.metadata["RDEPEND"],
					myuse=running_portage.use.enabled,
					parent=running_portage, strict=False)
			except portage.exception.InvalidDependString, e:
				portage.writemsg("!!! Invalid RDEPEND in " + \
					"'%svar/db/pkg/%s/RDEPEND': %s\n" % \
					(running_root, running_portage.cpv, e), noiselevel=-1)
				del e
				portage_rdepend = []
			runtime_deps.update(atom for atom in portage_rdepend \
				if not atom.startswith("!"))

		ignore_priority_soft_range = [None]
		ignore_priority_soft_range.extend(
			xrange(DepPriority.MIN, DepPriority.MEDIUM_SOFT + 1))
		tree_mode = "--tree" in self.myopts
		# Tracks whether or not the current iteration should prefer asap_nodes
		# if available.  This is set to False when the previous iteration
		# failed to select any nodes.  It is reset whenever nodes are
		# successfully selected.
		prefer_asap = True

		# By default, try to avoid selecting root nodes whenever possible. This
		# helps ensure that the maximimum possible number of soft dependencies
		# have been removed from the graph before their parent nodes have
		# selected. This is especially important when those dependencies are
		# going to be rebuilt by revdep-rebuild or `emerge -e system` after the
		# CHOST has been changed (like when building a stage3 from a stage2).
		accept_root_node = False

		# State of prefer_asap and accept_root_node flags for successive
		# iterations that loosen the criteria for node selection.
		#
		# iteration   prefer_asap   accept_root_node
		# 1           True          False
		# 2           False         False
		# 3           False         True
		#
		# If no nodes are selected on the 3rd iteration, it is due to
		# unresolved blockers or circular dependencies.

		while not mygraph.empty():
			self.spinner.update()
			selected_nodes = None
			ignore_priority = None
			if prefer_asap and asap_nodes:
				"""ASAP nodes are merged before their soft deps."""
				asap_nodes = [node for node in asap_nodes \
					if mygraph.contains(node)]
				for node in asap_nodes:
					if not mygraph.child_nodes(node,
						ignore_priority=DepPriority.SOFT):
						selected_nodes = [node]
						asap_nodes.remove(node)
						break
			if not selected_nodes and \
				not (prefer_asap and asap_nodes):
				for ignore_priority in ignore_priority_soft_range:
					nodes = get_nodes(ignore_priority=ignore_priority)
					if nodes:
						break
				if nodes:
					if ignore_priority is None and not tree_mode:
						# Greedily pop all of these nodes since no relationship
						# has been ignored.  This optimization destroys --tree
						# output, so it's disabled in reversed mode. If there
						# is a mix of merge and uninstall nodes, save the
						# uninstall nodes from later since sometimes a merge
						# node will render an install node unnecessary, and
						# we want to avoid doing a separate uninstall task in
						# that case.
						merge_nodes = [node for node in nodes \
							if node.operation == "merge"]
						if merge_nodes:
							selected_nodes = merge_nodes
						else:
							selected_nodes = nodes
					else:
						# For optimal merge order:
						#  * Only pop one node.
						#  * Removing a root node (node without a parent)
						#    will not produce a leaf node, so avoid it.
						for node in nodes:
							if mygraph.parent_nodes(node):
								# found a non-root node
								selected_nodes = [node]
								break
						if not selected_nodes and \
							(accept_root_node or ignore_priority is None):
							# settle for a root node
							selected_nodes = [nodes[0]]

			if not selected_nodes:
				nodes = get_nodes(ignore_priority=DepPriority.MEDIUM)
				if nodes:
					"""Recursively gather a group of nodes that RDEPEND on
					eachother.  This ensures that they are merged as a group
					and get their RDEPENDs satisfied as soon as possible."""
					def gather_deps(ignore_priority,
						mergeable_nodes, selected_nodes, node):
						if node in selected_nodes:
							return True
						if node not in mergeable_nodes:
							return False
						if node == replacement_portage and \
							mygraph.child_nodes(node,
							ignore_priority=DepPriority.MEDIUM_SOFT):
							# Make sure that portage always has all of it's
							# RDEPENDs installed first.
							return False
						selected_nodes.add(node)
						for child in mygraph.child_nodes(node,
							ignore_priority=ignore_priority):
							if not gather_deps(ignore_priority,
								mergeable_nodes, selected_nodes, child):
								return False
						return True
					mergeable_nodes = set(nodes)
					if prefer_asap and asap_nodes:
						nodes = asap_nodes
					for ignore_priority in xrange(DepPriority.SOFT,
						DepPriority.MEDIUM_SOFT + 1):
						for node in nodes:
							if nodes is not asap_nodes and \
								not accept_root_node and \
								not mygraph.parent_nodes(node):
								continue
							selected_nodes = set()
							if gather_deps(ignore_priority,
								mergeable_nodes, selected_nodes, node):
								break
							else:
								selected_nodes = None
						if selected_nodes:
							break

					# If any nodes have been selected here, it's always
					# possible that anything up to a MEDIUM_SOFT priority
					# relationship has been ignored. This state is recorded
					# in ignore_priority so that relevant nodes will be
					# added to asap_nodes when appropriate.
					if selected_nodes:
						ignore_priority = DepPriority.MEDIUM_SOFT

					if prefer_asap and asap_nodes and not selected_nodes:
						# We failed to find any asap nodes to merge, so ignore
						# them for the next iteration.
						prefer_asap = False
						continue

					if not selected_nodes and not accept_root_node:
						# Maybe there are only root nodes left, so accept them
						# for the next iteration.
						accept_root_node = True
						continue

			if selected_nodes and ignore_priority > DepPriority.SOFT:
				# Try to merge ignored medium deps as soon as possible.
				for node in selected_nodes:
					children = set(mygraph.child_nodes(node))
					soft = children.difference(
						mygraph.child_nodes(node,
						ignore_priority=DepPriority.SOFT))
					medium_soft = children.difference(
						mygraph.child_nodes(node,
						ignore_priority=DepPriority.MEDIUM_SOFT))
					medium_soft.difference_update(soft)
					for child in medium_soft:
						if child in selected_nodes:
							continue
						if child in asap_nodes:
							continue
						asap_nodes.append(child)

			if selected_nodes and len(selected_nodes) > 1:
				if not isinstance(selected_nodes, list):
					selected_nodes = list(selected_nodes)
				selected_nodes.sort(cmp_circular_bias)

			if not selected_nodes and not myblocker_uninstalls.is_empty():
				# An Uninstall task needs to be executed in order to
				# avoid conflict if possible.
				min_parent_deps = None
				uninst_task = None
				for task in myblocker_uninstalls.leaf_nodes():
					# Do some sanity checks so that system or world packages
					# don't get uninstalled inappropriately here (only really
					# necessary when --complete-graph has not been enabled).

					if task in ignored_uninstall_tasks:
						continue

					if task in scheduled_uninstalls:
						# It's been scheduled but it hasn't
						# been executed yet due to dependence
						# on installation of blocking packages.
						continue

					root_config = self.roots[task.root]
					inst_pkg = self._pkg_cache[
						("installed", task.root, task.cpv, "nomerge")]

					if self.digraph.contains(inst_pkg):
						continue

					if running_root == task.root:
						# Never uninstall sys-apps/portage or it's essential
						# dependencies, except through replacement.
						try:
							runtime_dep_atoms = \
								list(runtime_deps.iterAtomsForPackage(task))
						except portage.exception.InvalidDependString, e:
							portage.writemsg("!!! Invalid PROVIDE in " + \
								"'%svar/db/pkg/%s/PROVIDE': %s\n" % \
								(task.root, task.cpv, e), noiselevel=-1)
							del e
							continue

						# Don't uninstall a runtime dep if it appears
						# to be the only suitable one installed.
						skip = False
						vardb = root_config.trees["vartree"].dbapi
						for atom in runtime_dep_atoms:
							other_version = None
							for pkg in vardb.match_pkgs(atom):
								if pkg.cpv == task.cpv and \
									pkg.metadata["COUNTER"] == \
									task.metadata["COUNTER"]:
									continue
								other_version = pkg
								break
							if other_version is None:
								skip = True
								break
						if skip:
							continue

						# For packages in the system set, don't take
						# any chances. If the conflict can't be resolved
						# by a normal replacement operation then abort.
						skip = False
						try:
							for atom in root_config.sets[
								"system"].iterAtomsForPackage(task):
								skip = True
								break
						except portage.exception.InvalidDependString, e:
							portage.writemsg("!!! Invalid PROVIDE in " + \
								"'%svar/db/pkg/%s/PROVIDE': %s\n" % \
								(task.root, task.cpv, e), noiselevel=-1)
							del e
							skip = True
						if skip:
							continue

					# Note that the world check isn't always
					# necessary since self._complete_graph() will
					# add all packages from the system and world sets to the
					# graph. This just allows unresolved conflicts to be
					# detected as early as possible, which makes it possible
					# to avoid calling self._complete_graph() when it is
					# unnecessary due to blockers triggering an abortion.
					if not complete:
						# For packages in the world set, go ahead an uninstall
						# when necessary, as long as the atom will be satisfied
						# in the final state.
						graph_db = self.mydbapi[task.root]
						skip = False
						try:
							for atom in root_config.sets[
								"world"].iterAtomsForPackage(task):
								satisfied = False
								for pkg in graph_db.match_pkgs(atom):
									if pkg == inst_pkg:
										continue
									satisfied = True
									break
								if not satisfied:
									skip = True
									break
						except portage.exception.InvalidDependString, e:
							portage.writemsg("!!! Invalid PROVIDE in " + \
								"'%svar/db/pkg/%s/PROVIDE': %s\n" % \
								(task.root, task.cpv, e), noiselevel=-1)
							del e
							skip = True
						if skip:
							continue

					# Check the deps of parent nodes to ensure that
					# the chosen task produces a leaf node. Maybe
					# this can be optimized some more to make the
					# best possible choice, but the current algorithm
					# is simple and should be near optimal for most
					# common cases.
					parent_deps = set()
					for parent in mygraph.parent_nodes(task):
						parent_deps.update(mygraph.child_nodes(parent,
							ignore_priority=DepPriority.MEDIUM_SOFT))
					parent_deps.remove(task)
					if min_parent_deps is None or \
						len(parent_deps) < min_parent_deps:
						min_parent_deps = len(parent_deps)
						uninst_task = task

				if uninst_task is not None:
					# The uninstall is performed only after blocking
					# packages have been merged on top of it. File
					# collisions between blocking packages are detected
					# and removed from the list of files to be uninstalled.
					scheduled_uninstalls.add(uninst_task)
					parent_nodes = mygraph.parent_nodes(uninst_task)

					# Reverse the parent -> uninstall edges since we want
					# to do the uninstall after blocking packages have
					# been merged on top of it.
					mygraph.remove(uninst_task)
					for blocked_pkg in parent_nodes:
						mygraph.add(blocked_pkg, uninst_task,
							priority=BlockerDepPriority.instance)
				else:
					# None of the Uninstall tasks are acceptable, so
					# the corresponding blockers are unresolvable.
					# We need to drop an Uninstall task here in order
					# to avoid the circular deps code path, but the
					# blocker will still be counted as an unresolved
					# conflict.
					for node in myblocker_uninstalls.leaf_nodes():
						try:
							mygraph.remove(node)
						except KeyError:
							pass
						else:
							ignored_uninstall_tasks.add(node)
							break

				# After dropping an Uninstall task, reset
				# the state variables for leaf node selection and
				# continue trying to select leaf nodes.
				prefer_asap = True
				accept_root_node = False
				continue

			if not selected_nodes:
				self._circular_deps_for_display = mygraph
				raise self._unknown_internal_error()

			# At this point, we've succeeded in selecting one or more nodes, so
			# it's now safe to reset the prefer_asap and accept_root_node flags
			# to their default states.
			prefer_asap = True
			accept_root_node = False

			mygraph.difference_update(selected_nodes)

			for node in selected_nodes:
				if isinstance(node, Package) and \
					node.operation == "nomerge":
					continue

				# Handle interactions between blockers
				# and uninstallation tasks.
				solved_blockers = set()
				uninst_task = None
				if isinstance(node, Package) and \
					"uninstall" == node.operation:
					have_uninstall_task = True
					uninst_task = node
				else:
					vardb = self.trees[node.root]["vartree"].dbapi
					previous_cpv = vardb.match(node.slot_atom)
					if previous_cpv:
						# The package will be replaced by this one, so remove
						# the corresponding Uninstall task if necessary.
						previous_cpv = previous_cpv[0]
						uninst_task = \
							("installed", node.root, previous_cpv, "uninstall")
						try:
							mygraph.remove(uninst_task)
						except KeyError:
							pass

				if uninst_task is not None and \
					uninst_task not in ignored_uninstall_tasks and \
					myblocker_uninstalls.contains(uninst_task):
					blocker_nodes = myblocker_uninstalls.parent_nodes(uninst_task)
					myblocker_uninstalls.remove(uninst_task)
					# Discard any blockers that this Uninstall solves.
					for blocker in blocker_nodes:
						if not myblocker_uninstalls.child_nodes(blocker):
							myblocker_uninstalls.remove(blocker)
							solved_blockers.add(blocker)

				retlist.append(node)

				if (isinstance(node, Package) and \
					"uninstall" == node.operation) or \
					(uninst_task is not None and \
					uninst_task in scheduled_uninstalls):
					# Include satisfied blockers in the merge list
					# since the user might be interested and also
					# it serves as an indicator that blocking packages
					# will be temporarily installed simultaneously.
					for blocker in solved_blockers:
						retlist.append(Blocker(atom=blocker.atom,
							root=blocker.root, satisfied=True))

		unsolvable_blockers = set(self._unsolvable_blockers.leaf_nodes())
		for node in myblocker_uninstalls.root_nodes():
			unsolvable_blockers.add(node)

		for blocker in unsolvable_blockers:
			retlist.append(blocker)

		# If any Uninstall tasks need to be executed in order
		# to avoid a conflict, complete the graph with any
		# dependencies that may have been initially
		# neglected (to ensure that unsafe Uninstall tasks
		# are properly identified and blocked from execution).
		if have_uninstall_task and \
			not complete and \
			not unsolvable_blockers:
			self.myparams.add("complete")
			raise self._serialize_tasks_retry("")

		if unsolvable_blockers and \
			not self._accept_blocker_conflicts():
			self._unsatisfied_blockers_for_display = unsolvable_blockers
			self._serialized_tasks_cache = retlist[:]
			raise self._unknown_internal_error()

		if self._slot_collision_info and \
			not self._accept_blocker_conflicts():
			self._serialized_tasks_cache = retlist[:]
			raise self._unknown_internal_error()

		return retlist

	def _show_circular_deps(self, mygraph):
		# No leaf nodes are available, so we have a circular
		# dependency panic situation.  Reduce the noise level to a
		# minimum via repeated elimination of root nodes since they
		# have no parents and thus can not be part of a cycle.
		while True:
			root_nodes = mygraph.root_nodes(
				ignore_priority=DepPriority.MEDIUM_SOFT)
			if not root_nodes:
				break
			mygraph.difference_update(root_nodes)
		# Display the USE flags that are enabled on nodes that are part
		# of dependency cycles in case that helps the user decide to
		# disable some of them.
		display_order = []
		tempgraph = mygraph.copy()
		while not tempgraph.empty():
			nodes = tempgraph.leaf_nodes()
			if not nodes:
				node = tempgraph.order[0]
			else:
				node = nodes[0]
			display_order.append(node)
			tempgraph.remove(node)
		display_order.reverse()
		self.myopts.pop("--quiet", None)
		self.myopts.pop("--verbose", None)
		self.myopts["--tree"] = True
		portage.writemsg("\n\n", noiselevel=-1)
		self.display(display_order)
		prefix = colorize("BAD", " * ")
		portage.writemsg("\n", noiselevel=-1)
		portage.writemsg(prefix + "Error: circular dependencies:\n",
			noiselevel=-1)
		portage.writemsg("\n", noiselevel=-1)
		mygraph.debug_print()
		portage.writemsg("\n", noiselevel=-1)
		portage.writemsg(prefix + "Note that circular dependencies " + \
			"can often be avoided by temporarily\n", noiselevel=-1)
		portage.writemsg(prefix + "disabling USE flags that trigger " + \
			"optional dependencies.\n", noiselevel=-1)

	def _show_merge_list(self):
		if self._serialized_tasks_cache is not None and \
			not (self._displayed_list and \
			(self._displayed_list == self._serialized_tasks_cache or \
			self._displayed_list == \
				list(reversed(self._serialized_tasks_cache)))):
			display_list = self._serialized_tasks_cache[:]
			if "--tree" in self.myopts:
				display_list.reverse()
			self.display(display_list)

	def _show_unsatisfied_blockers(self, blockers):
		self._show_merge_list()
		msg = "Error: The above package list contains " + \
			"packages which cannot be installed " + \
			"at the same time on the same system."
		prefix = colorize("BAD", " * ")
		from textwrap import wrap
		portage.writemsg("\n", noiselevel=-1)
		for line in wrap(msg, 70):
			portage.writemsg(prefix + line + "\n", noiselevel=-1)
		if "--quiet" not in self.myopts:
			show_blocker_docs_link()

	def display(self, mylist, favorites=[], verbosity=None):

		# This is used to prevent display_problems() from
		# redundantly displaying this exact same merge list
		# again via _show_merge_list().
		self._displayed_list = mylist

		if verbosity is None:
			verbosity = ("--quiet" in self.myopts and 1 or \
				"--verbose" in self.myopts and 3 or 2)
		favorites_set = InternalPackageSet(favorites)
		oneshot = "--oneshot" in self.myopts or \
			"--onlydeps" in self.myopts
		changelogs=[]
		p=[]
		blockers = []

		counters = PackageCounters()

		if verbosity == 1 and "--verbose" not in self.myopts:
			def create_use_string(*args):
				return ""
		else:
			def create_use_string(name, cur_iuse, iuse_forced, cur_use,
				old_iuse, old_use,
				is_new, reinst_flags,
				all_flags=(verbosity == 3 or "--quiet" in self.myopts),
				alphabetical=("--alphabetical" in self.myopts)):
				enabled = []
				if alphabetical:
					disabled = enabled
					removed = enabled
				else:
					disabled = []
					removed = []
				cur_iuse = set(cur_iuse)
				enabled_flags = cur_iuse.intersection(cur_use)
				removed_iuse = set(old_iuse).difference(cur_iuse)
				any_iuse = cur_iuse.union(old_iuse)
				any_iuse = list(any_iuse)
				any_iuse.sort()
				for flag in any_iuse:
					flag_str = None
					isEnabled = False
					reinst_flag = reinst_flags and flag in reinst_flags
					if flag in enabled_flags:
						isEnabled = True
						if is_new or flag in old_use and \
							(all_flags or reinst_flag):
							flag_str = red(flag)
						elif flag not in old_iuse:
							flag_str = yellow(flag) + "%*"
						elif flag not in old_use:
							flag_str = green(flag) + "*"
					elif flag in removed_iuse:
						if all_flags or reinst_flag:
							flag_str = yellow("-" + flag) + "%"
							if flag in old_use:
								flag_str += "*"
							flag_str = "(" + flag_str + ")"
							removed.append(flag_str)
						continue
					else:
						if is_new or flag in old_iuse and \
							flag not in old_use and \
							(all_flags or reinst_flag):
							flag_str = blue("-" + flag)
						elif flag not in old_iuse:
							flag_str = yellow("-" + flag)
							if flag not in iuse_forced:
								flag_str += "%"
						elif flag in old_use:
							flag_str = green("-" + flag) + "*"
					if flag_str:
						if flag in iuse_forced:
							flag_str = "(" + flag_str + ")"
						if isEnabled:
							enabled.append(flag_str)
						else:
							disabled.append(flag_str)

				if alphabetical:
					ret = " ".join(enabled)
				else:
					ret = " ".join(enabled + disabled + removed)
				if ret:
					ret = '%s="%s" ' % (name, ret)
				return ret

		repo_display = RepoDisplay(self.roots)
		show_repos = False

		tree_nodes = []
		display_list = []
		mygraph = self.digraph.copy()

		# If there are any Uninstall instances, add the corresponding
		# blockers to the digraph (useful for --tree display).

		executed_uninstalls = set(node for node in mylist \
			if isinstance(node, Package) and node.operation == "unmerge")

		for uninstall in self._blocker_uninstalls.leaf_nodes():
			uninstall_parents = \
				self._blocker_uninstalls.parent_nodes(uninstall)
			if not uninstall_parents:
				continue

			# Remove the corresponding "nomerge" node and substitute
			# the Uninstall node.
			inst_pkg = self._pkg_cache[
				("installed", uninstall.root, uninstall.cpv, "nomerge")]
			try:
				mygraph.remove(inst_pkg)
			except KeyError:
				pass

			try:
				inst_pkg_blockers = self._blocker_parents.child_nodes(inst_pkg)
			except KeyError:
				inst_pkg_blockers = []

			# Break the Package -> Uninstall edges.
			mygraph.remove(uninstall)

			# Resolution of a package's blockers
			# depend on it's own uninstallation.
			for blocker in inst_pkg_blockers:
				mygraph.add(uninstall, blocker)

			# Expand Package -> Uninstall edges into
			# Package -> Blocker -> Uninstall edges.
			for blocker in uninstall_parents:
				mygraph.add(uninstall, blocker)
				for parent in self._blocker_parents.parent_nodes(blocker):
					if parent != inst_pkg:
						mygraph.add(blocker, parent)

			# If the uninstall task did not need to be executed because
			# of an upgrade, display Blocker -> Upgrade edges since the
			# corresponding Blocker -> Uninstall edges will not be shown.
			upgrade_node = \
				self._slot_pkg_map[uninstall.root].get(uninstall.slot_atom)
			if upgrade_node is not None and \
				uninstall not in executed_uninstalls:
				for blocker in uninstall_parents:
					mygraph.add(upgrade_node, blocker)

		unsatisfied_blockers = []
		i = 0
		depth = 0
		shown_edges = set()
		for x in mylist:
			if isinstance(x, Blocker) and not x.satisfied:
				unsatisfied_blockers.append(x)
				continue
			graph_key = x
			if "--tree" in self.myopts:
				depth = len(tree_nodes)
				while depth and graph_key not in \
					mygraph.child_nodes(tree_nodes[depth-1]):
						depth -= 1
				if depth:
					tree_nodes = tree_nodes[:depth]
					tree_nodes.append(graph_key)
					display_list.append((x, depth, True))
					shown_edges.add((graph_key, tree_nodes[depth-1]))
				else:
					traversed_nodes = set() # prevent endless circles
					traversed_nodes.add(graph_key)
					def add_parents(current_node, ordered):
						parent_nodes = None
						# Do not traverse to parents if this node is an
						# an argument or a direct member of a set that has
						# been specified as an argument (system or world).
						if current_node not in self._set_nodes:
							parent_nodes = mygraph.parent_nodes(current_node)
						if parent_nodes:
							child_nodes = set(mygraph.child_nodes(current_node))
							selected_parent = None
							# First, try to avoid a direct cycle.
							for node in parent_nodes:
								if not isinstance(node, (Blocker, Package)):
									continue
								if node not in traversed_nodes and \
									node not in child_nodes:
									edge = (current_node, node)
									if edge in shown_edges:
										continue
									selected_parent = node
									break
							if not selected_parent:
								# A direct cycle is unavoidable.
								for node in parent_nodes:
									if not isinstance(node, (Blocker, Package)):
										continue
									if node not in traversed_nodes:
										edge = (current_node, node)
										if edge in shown_edges:
											continue
										selected_parent = node
										break
							if selected_parent:
								shown_edges.add((current_node, selected_parent))
								traversed_nodes.add(selected_parent)
								add_parents(selected_parent, False)
						display_list.append((current_node,
							len(tree_nodes), ordered))
						tree_nodes.append(current_node)
					tree_nodes = []
					add_parents(graph_key, True)
			else:
				display_list.append((x, depth, True))
		mylist = display_list
		for x in unsatisfied_blockers:
			mylist.append((x, 0, True))

		last_merge_depth = 0
		for i in xrange(len(mylist)-1,-1,-1):
			graph_key, depth, ordered = mylist[i]
			if not ordered and depth == 0 and i > 0 \
				and graph_key == mylist[i-1][0] and \
				mylist[i-1][1] == 0:
				# An ordered node got a consecutive duplicate when the tree was
				# being filled in.
				del mylist[i]
				continue
			if ordered and graph_key[-1] != "nomerge":
				last_merge_depth = depth
				continue
			if depth >= last_merge_depth or \
				i < len(mylist) - 1 and \
				depth >= mylist[i+1][1]:
					del mylist[i]

		from portage import flatten
		from portage.dep import use_reduce, paren_reduce
		# files to fetch list - avoids counting a same file twice
		# in size display (verbose mode)
		myfetchlist=[]

		for mylist_index in xrange(len(mylist)):
			x, depth, ordered = mylist[mylist_index]
			pkg_type = x[0]
			myroot = x[1]
			pkg_key = x[2]
			portdb = self.trees[myroot]["porttree"].dbapi
			bindb  = self.trees[myroot]["bintree"].dbapi
			vardb = self.trees[myroot]["vartree"].dbapi
			vartree = self.trees[myroot]["vartree"]
			pkgsettings = self.pkgsettings[myroot]

			fetch=" "
			indent = " " * depth

			if isinstance(x, Blocker):
				if x.satisfied:
					blocker_style = "PKG_BLOCKER_SATISFIED"
					addl = "%s  %s  " % (colorize(blocker_style, "b"), fetch)
				else:
					blocker_style = "PKG_BLOCKER"
					addl = "%s  %s  " % (colorize(blocker_style, "B"), fetch)
				if ordered:
					counters.blocks += 1
					if x.satisfied:
						counters.blocks_satisfied += 1
				resolved = portage.key_expand(
					pkg_key, mydb=vardb, settings=pkgsettings)
				if "--columns" in self.myopts and "--quiet" in self.myopts:
					addl += " " + colorize(blocker_style, resolved)
				else:
					addl = "[%s %s] %s%s" % \
						(colorize(blocker_style, "blocks"),
						addl, indent, colorize(blocker_style, resolved))
				block_parents = self._blocker_parents.parent_nodes(x)
				block_parents = set([pnode[2] for pnode in block_parents])
				block_parents = ", ".join(block_parents)
				if resolved!=x[2]:
					addl += colorize(blocker_style,
						" (\"%s\" is blocking %s)") % \
						(pkg_key, block_parents)
				else:
					addl += colorize(blocker_style,
						" (is blocking %s)") % block_parents
				if isinstance(x, Blocker) and x.satisfied:
					p.append(addl)
				else:
					blockers.append(addl)
			else:
				pkg_status = x[3]
				pkg_merge = ordered and pkg_status == "merge"
				if not pkg_merge and pkg_status == "merge":
					pkg_status = "nomerge"
				built = pkg_type != "ebuild"
				installed = pkg_type == "installed"
				pkg = x
				metadata = pkg.metadata
				ebuild_path = None
				repo_name = metadata["repository"]
				if pkg_type == "ebuild":
					ebuild_path = portdb.findname(pkg_key)
					if not ebuild_path: # shouldn't happen
						raise portage.exception.PackageNotFound(pkg_key)
					repo_path_real = os.path.dirname(os.path.dirname(
						os.path.dirname(ebuild_path)))
				else:
					repo_path_real = portdb.getRepositoryPath(repo_name)
				pkg_use = list(pkg.use.enabled)
				try:
					restrict = flatten(use_reduce(paren_reduce(
						pkg.metadata["RESTRICT"]), uselist=pkg_use))
				except portage.exception.InvalidDependString, e:
					if not pkg.installed:
						show_invalid_depstring_notice(x,
							pkg.metadata["RESTRICT"], str(e))
						del e
						return 1
					restrict = []
				if "ebuild" == pkg_type and x[3] != "nomerge" and \
					"fetch" in restrict:
					fetch = red("F")
					if ordered:
						counters.restrict_fetch += 1
					if portdb.fetch_check(pkg_key, pkg_use):
						fetch = green("f")
						if ordered:
							counters.restrict_fetch_satisfied += 1

				#we need to use "--emptrytree" testing here rather than "empty" param testing because "empty"
				#param is used for -u, where you still *do* want to see when something is being upgraded.
				myoldbest = []
				myinslotlist = None
				installed_versions = vardb.match(portage.cpv_getkey(pkg_key))
				if vardb.cpv_exists(pkg_key):
					addl="  "+yellow("R")+fetch+"  "
					if ordered:
						if pkg_merge:
							counters.reinst += 1
						elif pkg_status == "uninstall":
							counters.uninst += 1
				# filter out old-style virtual matches
				elif installed_versions and \
					portage.cpv_getkey(installed_versions[0]) == \
					portage.cpv_getkey(pkg_key):
					myinslotlist = vardb.match(pkg.slot_atom)
					# If this is the first install of a new-style virtual, we
					# need to filter out old-style virtual matches.
					if myinslotlist and \
						portage.cpv_getkey(myinslotlist[0]) != \
						portage.cpv_getkey(pkg_key):
						myinslotlist = None
					if myinslotlist:
						myoldbest = myinslotlist[:]
						addl = "   " + fetch
						if not portage.dep.cpvequal(pkg_key,
							portage.best([pkg_key] + myoldbest)):
							# Downgrade in slot
							addl += turquoise("U")+blue("D")
							if ordered:
								counters.downgrades += 1
						else:
							# Update in slot
							addl += turquoise("U") + " "
							if ordered:
								counters.upgrades += 1
					else:
						# New slot, mark it new.
						addl = " " + green("NS") + fetch + "  "
						myoldbest = vardb.match(portage.cpv_getkey(pkg_key))
						if ordered:
							counters.newslot += 1

					if "--changelog" in self.myopts:
						inst_matches = vardb.match(pkg.slot_atom)
						if inst_matches:
							changelogs.extend(self.calc_changelog(
								portdb.findname(pkg_key),
								inst_matches[0], pkg_key))
				else:
					addl = " " + green("N") + " " + fetch + "  "
					if ordered:
						counters.new += 1

				verboseadd = ""
				
				if True:
					# USE flag display
					forced_flags = set()
					pkgsettings.setcpv(pkg) # for package.use.{mask,force}
					forced_flags.update(pkgsettings.useforce)
					forced_flags.update(pkgsettings.usemask)

					cur_use = [flag for flag in pkg.use.enabled \
						if flag in pkg.iuse.all]
					cur_iuse = sorted(pkg.iuse.all)

					if myoldbest and myinslotlist:
						previous_cpv = myoldbest[0]
					else:
						previous_cpv = pkg.cpv
					if vardb.cpv_exists(previous_cpv):
						old_iuse, old_use = vardb.aux_get(
								previous_cpv, ["IUSE", "USE"])
						old_iuse = list(set(
							filter_iuse_defaults(old_iuse.split())))
						old_iuse.sort()
						old_use = old_use.split()
						is_new = False
					else:
						old_iuse = []
						old_use = []
						is_new = True

					old_use = [flag for flag in old_use if flag in old_iuse]

					use_expand = pkgsettings["USE_EXPAND"].lower().split()
					use_expand.sort()
					use_expand.reverse()
					use_expand_hidden = \
						pkgsettings["USE_EXPAND_HIDDEN"].lower().split()

					def map_to_use_expand(myvals, forcedFlags=False,
						removeHidden=True):
						ret = {}
						forced = {}
						for exp in use_expand:
							ret[exp] = []
							forced[exp] = set()
							for val in myvals[:]:
								if val.startswith(exp.lower()+"_"):
									if val in forced_flags:
										forced[exp].add(val[len(exp)+1:])
									ret[exp].append(val[len(exp)+1:])
									myvals.remove(val)
						ret["USE"] = myvals
						forced["USE"] = [val for val in myvals \
							if val in forced_flags]
						if removeHidden:
							for exp in use_expand_hidden:
								ret.pop(exp, None)
						if forcedFlags:
							return ret, forced
						return ret

					# Prevent USE_EXPAND_HIDDEN flags from being hidden if they
					# are the only thing that triggered reinstallation.
					reinst_flags_map = {}
					reinstall_for_flags = self._reinstall_nodes.get(pkg)
					reinst_expand_map = None
					if reinstall_for_flags:
						reinst_flags_map = map_to_use_expand(
							list(reinstall_for_flags), removeHidden=False)
						for k in list(reinst_flags_map):
							if not reinst_flags_map[k]:
								del reinst_flags_map[k]
						if not reinst_flags_map.get("USE"):
							reinst_expand_map = reinst_flags_map.copy()
							reinst_expand_map.pop("USE", None)
					if reinst_expand_map and \
						not set(reinst_expand_map).difference(
						use_expand_hidden):
						use_expand_hidden = \
							set(use_expand_hidden).difference(
							reinst_expand_map)

					cur_iuse_map, iuse_forced = \
						map_to_use_expand(cur_iuse, forcedFlags=True)
					cur_use_map = map_to_use_expand(cur_use)
					old_iuse_map = map_to_use_expand(old_iuse)
					old_use_map = map_to_use_expand(old_use)

					use_expand.sort()
					use_expand.insert(0, "USE")
					
					for key in use_expand:
						if key in use_expand_hidden:
							continue
						verboseadd += create_use_string(key.upper(),
							cur_iuse_map[key], iuse_forced[key],
							cur_use_map[key], old_iuse_map[key],
							old_use_map[key], is_new,
							reinst_flags_map.get(key))

				if verbosity == 3:
					# size verbose
					mysize=0
					if pkg_type == "ebuild" and pkg_merge:
						try:
							myfilesdict = portdb.getfetchsizes(pkg_key,
								useflags=pkg_use, debug=self.edebug)
						except portage.exception.InvalidDependString, e:
							src_uri = portdb.aux_get(pkg_key, ["SRC_URI"])[0]
							show_invalid_depstring_notice(x, src_uri, str(e))
							del e
							return 1
						if myfilesdict is None:
							myfilesdict="[empty/missing/bad digest]"
						else:
							for myfetchfile in myfilesdict:
								if myfetchfile not in myfetchlist:
									mysize+=myfilesdict[myfetchfile]
									myfetchlist.append(myfetchfile)
							if ordered:
								counters.totalsize += mysize
						verboseadd+=format_size(mysize)+" "

					# overlay verbose
					# assign index for a previous version in the same slot
					has_previous = False
					repo_name_prev = None
					slot_atom = "%s:%s" % (portage.dep_getkey(pkg_key),
						metadata["SLOT"])
					slot_matches = vardb.match(slot_atom)
					if slot_matches:
						has_previous = True
						repo_name_prev = vardb.aux_get(slot_matches[0],
							["repository"])[0]

					# now use the data to generate output
					repoadd = None
					if pkg.installed or not has_previous:
						repoadd = repo_display.repoStr(repo_path_real)
					else:
						repo_path_prev = None
						if repo_name_prev:
							repo_path_prev = portdb.getRepositoryPath(
								repo_name_prev)
						if repo_path_prev == repo_path_real:
							repoadd = repo_display.repoStr(repo_path_real)
						else:
							repoadd = "%s=>%s" % (
								repo_display.repoStr(repo_path_prev),
								repo_display.repoStr(repo_path_real))
					if repoadd and repoadd != "0":
						show_repos = True
						verboseadd += teal("[%s]" % repoadd)

				xs = [portage.cpv_getkey(pkg_key)] + \
					list(portage.catpkgsplit(pkg_key)[2:])
				if xs[2] == "r0":
					xs[2] = ""
				else:
					xs[2] = "-" + xs[2]

				mywidth = 130
				if "COLUMNWIDTH" in self.settings:
					try:
						mywidth = int(self.settings["COLUMNWIDTH"])
					except ValueError, e:
						portage.writemsg("!!! %s\n" % str(e), noiselevel=-1)
						portage.writemsg(
							"!!! Unable to parse COLUMNWIDTH='%s'\n" % \
							self.settings["COLUMNWIDTH"], noiselevel=-1)
						del e
				oldlp = mywidth - 30
				newlp = oldlp - 30

				# Convert myoldbest from a list to a string.
				if not myoldbest:
					myoldbest = ""
				else:
					for pos, key in enumerate(myoldbest):
						key = portage.catpkgsplit(key)[2] + \
							"-" + portage.catpkgsplit(key)[3]
						if key[-3:] == "-r0":
							key = key[:-3]
						myoldbest[pos] = key
					myoldbest = blue("["+", ".join(myoldbest)+"]")

				pkg_cp = xs[0]
				root_config = self.roots[myroot]
				system_set = root_config.sets["system"]
				world_set  = root_config.sets["world"]

				pkg_system = False
				pkg_world = False
				try:
					pkg_system = system_set.findAtomForPackage(pkg)
					pkg_world  = world_set.findAtomForPackage(pkg)
					if not (oneshot or pkg_world) and \
						myroot == self.target_root and \
						favorites_set.findAtomForPackage(pkg):
						# Maybe it will be added to world now.
						if create_world_atom(pkg, favorites_set, root_config):
							pkg_world = True
				except portage.exception.InvalidDependString:
					# This is reported elsewhere if relevant.
					pass

				def pkgprint(pkg_str):
					if pkg_merge:
						if pkg_system:
							return colorize("PKG_MERGE_SYSTEM", pkg_str)
						elif pkg_world:
							return colorize("PKG_MERGE_WORLD", pkg_str)
						else:
							return colorize("PKG_MERGE", pkg_str)
					elif pkg_status == "uninstall":
						return colorize("PKG_UNINSTALL", pkg_str)
					else:
						if pkg_system:
							return colorize("PKG_NOMERGE_SYSTEM", pkg_str)
						elif pkg_world:
							return colorize("PKG_NOMERGE_WORLD", pkg_str)
						else:
							return colorize("PKG_NOMERGE", pkg_str)

				if x[1]!="/":
					if myoldbest:
						myoldbest +=" "
					if "--columns" in self.myopts:
						if "--quiet" in self.myopts:
							myprint=addl+" "+indent+pkgprint(pkg_cp)
							myprint=myprint+darkblue(" "+xs[1]+xs[2])+" "
							myprint=myprint+myoldbest
							myprint=myprint+darkgreen("to "+x[1])
						else:
							if not pkg_merge:
								myprint = "[%s] %s%s" % \
									(pkgprint(pkg_status.ljust(13)),
									indent, pkgprint(pkg.cp))
							else:
								myprint = "[%s %s] %s%s" % \
									(pkgprint(pkg.type_name), addl,
									indent, pkgprint(pkg.cp))
							if (newlp-nc_len(myprint)) > 0:
								myprint=myprint+(" "*(newlp-nc_len(myprint)))
							myprint=myprint+"["+darkblue(xs[1]+xs[2])+"] "
							if (oldlp-nc_len(myprint)) > 0:
								myprint=myprint+" "*(oldlp-nc_len(myprint))
							myprint=myprint+myoldbest
							myprint=myprint+darkgreen("to "+x[1])+" "+verboseadd
					else:
						if not pkg_merge:
							myprint = "[%s] " % pkgprint(pkg_status.ljust(13))
						else:
							myprint = "[" + pkg_type + " " + addl + "] "
						myprint += indent + pkgprint(pkg_key) + " " + \
							myoldbest + darkgreen("to " + myroot) + " " + \
							verboseadd
				else:
					if "--columns" in self.myopts:
						if "--quiet" in self.myopts:
							myprint=addl+" "+indent+pkgprint(pkg_cp)
							myprint=myprint+" "+green(xs[1]+xs[2])+" "
							myprint=myprint+myoldbest
						else:
							if not pkg_merge:
								myprint = "[%s] %s%s" % \
									(pkgprint(pkg_status.ljust(13)),
									indent, pkgprint(pkg.cp))
							else:
								myprint = "[%s %s] %s%s" % \
									(pkgprint(pkg.type_name), addl,
									indent, pkgprint(pkg.cp))
							if (newlp-nc_len(myprint)) > 0:
								myprint=myprint+(" "*(newlp-nc_len(myprint)))
							myprint=myprint+green(" ["+xs[1]+xs[2]+"] ")
							if (oldlp-nc_len(myprint)) > 0:
								myprint=myprint+(" "*(oldlp-nc_len(myprint)))
							myprint=myprint+myoldbest+"  "+verboseadd
					else:
						if not pkg_merge:
							myprint = "[%s] %s%s %s %s" % \
								(pkgprint(pkg_status.ljust(13)),
								indent, pkgprint(pkg.cpv),
								myoldbest, verboseadd)
						else:
							myprint="["+pkgprint(pkg_type)+" "+addl+"] "+indent+pkgprint(pkg_key)+" "+myoldbest+" "+verboseadd
				p.append(myprint)

				mysplit = [portage.cpv_getkey(pkg_key)] + \
					list(portage.catpkgsplit(pkg_key)[2:])
				if "--tree" not in self.myopts and mysplit and \
					len(mysplit) == 3 and mysplit[0] == "sys-apps/portage" and \
					x[1] == "/":
	
					if mysplit[2] == "r0":
						myversion = mysplit[1]
					else:
						myversion = "%s-%s" % (mysplit[1], mysplit[2])
	
					if myversion != portage.VERSION and "--quiet" not in self.myopts:
						if mylist_index < len(mylist) - 1:
							p.append(colorize("WARN", "*** Portage will stop merging at this point and reload itself,"))
							p.append(colorize("WARN", "    then resume the merge."))
							print
				del mysplit

		for x in p:
			print x
		for x in blockers:
			print x

		if verbosity == 3:
			print
			print counters
			if show_repos:
				sys.stdout.write(str(repo_display))

		if "--changelog" in self.myopts:
			print
			for revision,text in changelogs:
				print bold('*'+revision)
				sys.stdout.write(text)

		sys.stdout.flush()
		return os.EX_OK

	def display_problems(self):
		"""
		Display problems with the dependency graph such as slot collisions.
		This is called internally by display() to show the problems _after_
		the merge list where it is most likely to be seen, but if display()
		is not going to be called then this method should be called explicitly
		to ensure that the user is notified of problems with the graph.
		"""

		if self._circular_deps_for_display is not None:
			self._show_circular_deps(
				self._circular_deps_for_display)

		# The user is only notified of a slot conflict if
		# there are no unresolvable blocker conflicts.
		if self._unsatisfied_blockers_for_display is not None:
			self._show_unsatisfied_blockers(
				self._unsatisfied_blockers_for_display)
		else:
			self._show_slot_collision_notice()

		# TODO: Add generic support for "set problem" handlers so that
		# the below warnings aren't special cases for world only.

		if self._missing_args:
			world_problems = False
			if "world" in self._sets:
				for arg, atom in self._missing_args:
					if arg.name == "world":
						world_problems = True
						break

			if world_problems:
				sys.stderr.write("\n!!! Problems have been " + \
					"detected with your world file\n")
				sys.stderr.write("!!! Please run " + \
					green("emaint --check world")+"\n\n")

		if self._missing_args:
			sys.stderr.write("\n" + colorize("BAD", "!!!") + \
				" Ebuilds for the following packages are either all\n")
			sys.stderr.write(colorize("BAD", "!!!") + \
				" masked or don't exist:\n")
			sys.stderr.write(" ".join(str(atom) for arg, atom in \
				self._missing_args) + "\n")

		if self._pprovided_args:
			arg_refs = {}
			for arg, atom in self._pprovided_args:
				if isinstance(arg, SetArg):
					parent = arg.name
					arg_atom = (atom, atom)
				else:
					parent = "args"
					arg_atom = (arg.arg, atom)
				refs = arg_refs.setdefault(arg_atom, [])
				if parent not in refs:
					refs.append(parent)
			msg = []
			msg.append(bad("\nWARNING: "))
			if len(self._pprovided_args) > 1:
				msg.append("Requested packages will not be " + \
					"merged because they are listed in\n")
			else:
				msg.append("A requested package will not be " + \
					"merged because it is listed in\n")
			msg.append("package.provided:\n\n")
			problems_sets = set()
			for (arg, atom), refs in arg_refs.iteritems():
				ref_string = ""
				if refs:
					problems_sets.update(refs)
					refs.sort()
					ref_string = ", ".join(["'%s'" % name for name in refs])
					ref_string = " pulled in by " + ref_string
				msg.append("  %s%s\n" % (colorize("INFORM", str(arg)), ref_string))
			msg.append("\n")
			if "world" in problems_sets:
				msg.append("This problem can be solved in one of the following ways:\n\n")
				msg.append("  A) Use emaint to clean offending packages from world (if not installed).\n")
				msg.append("  B) Uninstall offending packages (cleans them from world).\n")
				msg.append("  C) Remove offending entries from package.provided.\n\n")
				msg.append("The best course of action depends on the reason that an offending\n")
				msg.append("package.provided entry exists.\n\n")
			sys.stderr.write("".join(msg))

		masked_packages = []
		for pkg in self._masked_installed:
			root_config = pkg.root_config
			pkgsettings = self.pkgsettings[pkg.root]
			mreasons = get_masking_status(pkg, pkgsettings, root_config)
			masked_packages.append((root_config, pkgsettings,
				pkg.cpv, pkg.metadata, mreasons))
		if masked_packages:
			sys.stderr.write("\n" + colorize("BAD", "!!!") + \
				" The following installed packages are masked:\n")
			show_masked_packages(masked_packages)
			show_mask_docs()
			print

		for pargs, kwargs in self._unsatisfied_deps_for_display:
			self._show_unsatisfied_dep(*pargs, **kwargs)

	def calc_changelog(self,ebuildpath,current,next):
		if ebuildpath == None or not os.path.exists(ebuildpath):
			return []
		current = '-'.join(portage.catpkgsplit(current)[1:])
		if current.endswith('-r0'):
			current = current[:-3]
		next = '-'.join(portage.catpkgsplit(next)[1:])
		if next.endswith('-r0'):
			next = next[:-3]
		changelogpath = os.path.join(os.path.split(ebuildpath)[0],'ChangeLog')
		try:
			changelog = open(changelogpath).read()
		except SystemExit, e:
			raise # Needed else can't exit
		except:
			return []
		divisions = self.find_changelog_tags(changelog)
		#print 'XX from',current,'to',next
		#for div,text in divisions: print 'XX',div
		# skip entries for all revisions above the one we are about to emerge
		for i in range(len(divisions)):
			if divisions[i][0]==next:
				divisions = divisions[i:]
				break
		# find out how many entries we are going to display
		for i in range(len(divisions)):
			if divisions[i][0]==current:
				divisions = divisions[:i]
				break
		else:
		    # couldnt find the current revision in the list. display nothing
			return []
		return divisions

	def find_changelog_tags(self,changelog):
		divs = []
		release = None
		while 1:
			match = re.search(r'^\*\ ?([-a-zA-Z0-9_.+]*)(?:\ .*)?\n',changelog,re.M)
			if match is None:
				if release is not None:
					divs.append((release,changelog))
				return divs
			if release is not None:
				divs.append((release,changelog[:match.start()]))
			changelog = changelog[match.end():]
			release = match.group(1)
			if release.endswith('.ebuild'):
				release = release[:-7]
			if release.endswith('-r0'):
				release = release[:-3]

	def saveNomergeFavorites(self):
		"""Find atoms in favorites that are not in the mergelist and add them
		to the world file if necessary."""
		for x in ("--buildpkgonly", "--fetchonly", "--fetch-all-uri",
			"--oneshot", "--onlydeps", "--pretend"):
			if x in self.myopts:
				return
		root_config = self.roots[self.target_root]
		world_set = root_config.sets["world"]
		world_set.lock()
		world_set.load() # maybe it's changed on disk
		args_set = self._sets["args"]
		portdb = self.trees[self.target_root]["porttree"].dbapi
		added_favorites = set()
		for x in self._set_nodes:
			pkg_type, root, pkg_key, pkg_status = x
			if pkg_status != "nomerge":
				continue

			try:
				myfavkey = create_world_atom(x, args_set, root_config)
				if myfavkey:
					if myfavkey in added_favorites:
						continue
					added_favorites.add(myfavkey)
			except portage.exception.InvalidDependString, e:
				writemsg("\n\n!!! '%s' has invalid PROVIDE: %s\n" % \
					(pkg_key, str(e)), noiselevel=-1)
				writemsg("!!! see '%s'\n\n" % os.path.join(
					root, portage.VDB_PATH, pkg_key, "PROVIDE"), noiselevel=-1)
				del e
		all_added = []
		for k in self._sets:
			if k in ("args", "world") or not root_config.sets[k].world_candidate:
				continue
			s = SETPREFIX + k
			if s in world_set:
				continue
			all_added.append(SETPREFIX + k)
		all_added.extend(added_favorites)
		all_added.sort()
		for a in all_added:
			print ">>> Recording %s in \"world\" favorites file..." % \
				colorize("INFORM", str(a))
		if all_added:
			world_set.update(all_added)
		world_set.unlock()

	def loadResumeCommand(self, resume_data, skip_masked=False):
		"""
		Add a resume command to the graph and validate it in the process.  This
		will raise a PackageNotFound exception if a package is not available.
		"""

		if not isinstance(resume_data, dict):
			return False

		mergelist = resume_data.get("mergelist")
		if not isinstance(mergelist, list):
			mergelist = []

		fakedb = self.mydbapi
		trees = self.trees
		serialized_tasks = []
		masked_tasks = []
		for x in mergelist:
			if not (isinstance(x, list) and len(x) == 4):
				continue
			pkg_type, myroot, pkg_key, action = x
			if pkg_type not in self.pkg_tree_map:
				continue
			if action != "merge":
				continue
			mydb = trees[myroot][self.pkg_tree_map[pkg_type]].dbapi
			try:
				metadata = izip(self._mydbapi_keys,
					mydb.aux_get(pkg_key, self._mydbapi_keys))
			except KeyError:
				# It does no exist or it is corrupt.
				if action == "uninstall":
					continue
				raise portage.exception.PackageNotFound(pkg_key)
			installed = action == "uninstall"
			built = pkg_type != "ebuild"
			root_config = self.roots[myroot]
			pkg = Package(built=built, cpv=pkg_key,
				installed=installed, metadata=metadata,
				operation=action, root_config=root_config,
				type_name=pkg_type)
			if pkg_type == "ebuild":
				pkgsettings = self.pkgsettings[myroot]
				pkgsettings.setcpv(pkg)
				pkg.metadata["USE"] = pkgsettings["PORTAGE_USE"]
			self._pkg_cache[pkg] = pkg

			root_config = self.roots[pkg.root]
			if "merge" == pkg.operation and \
				not visible(root_config.settings, pkg):
				if skip_masked:
					masked_tasks.append(Dependency(root=pkg.root, parent=pkg))
				else:
					self._unsatisfied_deps_for_display.append(
						((pkg.root, "="+pkg.cpv), {"myparent":None}))

			fakedb[myroot].cpv_inject(pkg)
			serialized_tasks.append(pkg)
			self.spinner.update()

		if self._unsatisfied_deps_for_display:
			return False

		if not serialized_tasks or "--nodeps" in self.myopts:
			self._serialized_tasks_cache = serialized_tasks
		else:
			self._select_package = self._select_pkg_from_graph
			self.myparams.add("selective")

			favorites = resume_data.get("favorites")
			args_set = self._sets["args"]
			if isinstance(favorites, list):
				args = self._load_favorites(favorites)
			else:
				args = []

			for task in serialized_tasks:
				if isinstance(task, Package) and \
					task.operation == "merge":
					if not self._add_pkg(task, None):
						return False

			# Packages for argument atoms need to be explicitly
			# added via _add_pkg() so that they are included in the
			# digraph (needed at least for --tree display).
			for arg in args:
				for atom in arg.set:
					pkg, existing_node = self._select_package(
						arg.root_config.root, atom)
					if existing_node is None and \
						pkg is not None:
						if not self._add_pkg(pkg, arg):
							return False

			# Allow unsatisfied deps here to avoid showing a masking
			# message for an unsatisfied dep that isn't necessarily
			# masked.
			if not self._create_graph(allow_unsatisfied=True):
				return False
			if masked_tasks or self._unsatisfied_deps:
				# This probably means that a required package
				# was dropped via --skipfirst. It makes the
				# resume list invalid, so convert it to a
				# UnsatisfiedResumeDep exception.
				raise self.UnsatisfiedResumeDep(self,
					masked_tasks + self._unsatisfied_deps)
			self._serialized_tasks_cache = None
			try:
				self.altlist()
			except self._unknown_internal_error:
				return False

		return True

	def _load_favorites(self, favorites):
		"""
		Use a list of favorites to resume state from a
		previous select_files() call. This creates similar
		DependencyArg instances to those that would have
		been created by the original select_files() call.
		This allows Package instances to be matched with
		DependencyArg instances during graph creation.
		"""
		root_config = self.roots[self.target_root]
		getSetAtoms = root_config.setconfig.getSetAtoms
		sets = root_config.sets
		args = []
		for x in favorites:
			if not isinstance(x, basestring):
				continue
			if x in ("system", "world"):
				x = SETPREFIX + x
			if x.startswith(SETPREFIX):
				s = x[len(SETPREFIX):]
				if s not in sets:
					continue
				if s in self._sets:
					continue
				# Recursively expand sets so that containment tests in
				# self._get_parent_sets() properly match atoms in nested
				# sets (like if world contains system).
				expanded_set = InternalPackageSet(
					initial_atoms=getSetAtoms(s))
				self._sets[s] = expanded_set
				args.append(SetArg(arg=x, set=expanded_set,
					root_config=root_config))
			else:
				if not portage.isvalidatom(x):
					continue
				args.append(AtomArg(arg=x, atom=x,
					root_config=root_config))

		# Create the "args" package set from atoms and
		# packages given as arguments.
		args_set = self._sets["args"]
		for arg in args:
			if not isinstance(arg, (AtomArg, PackageArg)):
				continue
			myatom = arg.atom
			if myatom in args_set:
				continue
			args_set.add(myatom)
		self._set_atoms.update(chain(*self._sets.itervalues()))
		atom_arg_map = self._atom_arg_map
		for arg in args:
			for atom in arg.set:
				atom_key = (atom, arg.root_config.root)
				refs = atom_arg_map.get(atom_key)
				if refs is None:
					refs = []
					atom_arg_map[atom_key] = refs
					if arg not in refs:
						refs.append(arg)
		return args

	class UnsatisfiedResumeDep(portage.exception.PortageException):
		"""
		A dependency of a resume list is not installed. This
		can occur when a required package is dropped from the
		merge list via --skipfirst.
		"""
		def __init__(self, depgraph, value):
			portage.exception.PortageException.__init__(self, value)
			self.depgraph = depgraph

	class _internal_exception(portage.exception.PortageException):
		def __init__(self, value=""):
			portage.exception.PortageException.__init__(self, value)

	class _unknown_internal_error(_internal_exception):
		"""
		Used by the depgraph internally to terminate graph creation.
		The specific reason for the failure should have been dumped
		to stderr, unfortunately, the exact reason for the failure
		may not be known.
		"""

	class _serialize_tasks_retry(_internal_exception):
		"""
		This is raised by the _serialize_tasks() method when it needs to
		be called again for some reason. The only case that it's currently
		used for is when neglected dependencies need to be added to the
		graph in order to avoid making a potentially unsafe decision.
		"""

	class _dep_check_composite_db(portage.dbapi):
		"""
		A dbapi-like interface that is optimized for use in dep_check() calls.
		This is built on top of the existing depgraph package selection logic.
		Some packages that have been added to the graph may be masked from this
		view in order to influence the atom preference selection that occurs
		via dep_check().
		"""
		def __init__(self, depgraph, root):
			portage.dbapi.__init__(self)
			self._depgraph = depgraph
			self._root = root
			self._match_cache = {}
			self._cpv_pkg_map = {}

		def match(self, atom):
			ret = self._match_cache.get(atom)
			if ret is not None:
				return ret[:]
			orig_atom = atom
			if "/" not in atom:
				atom = self._dep_expand(atom)
			pkg, existing = self._depgraph._select_package(self._root, atom)
			if not pkg:
				ret = []
			else:
				# Return the highest available from select_package() as well as
				# any matching slots in the graph db.
				slots = set()
				slots.add(pkg.metadata["SLOT"])
				atom_cp = portage.dep_getkey(atom)
				if pkg.cp.startswith("virtual/"):
					# For new-style virtual lookahead that occurs inside
					# dep_check(), examine all slots. This is needed
					# so that newer slots will not unnecessarily be pulled in
					# when a satisfying lower slot is already installed. For
					# example, if virtual/jdk-1.4 is satisfied via kaffe then
					# there's no need to pull in a newer slot to satisfy a
					# virtual/jdk dependency.
					for db, pkg_type, built, installed, db_keys in \
						self._depgraph._filtered_trees[self._root]["dbs"]:
						for cpv in db.match(atom):
							if portage.cpv_getkey(cpv) != pkg.cp:
								continue
							slots.add(db.aux_get(cpv, ["SLOT"])[0])
				ret = []
				if self._visible(pkg):
					self._cpv_pkg_map[pkg.cpv] = pkg
					ret.append(pkg.cpv)
				slots.remove(pkg.metadata["SLOT"])
				while slots:
					slot_atom = "%s:%s" % (atom_cp, slots.pop())
					pkg, existing = self._depgraph._select_package(
						self._root, slot_atom)
					if not pkg:
						continue
					if not self._visible(pkg):
						continue
					self._cpv_pkg_map[pkg.cpv] = pkg
					ret.append(pkg.cpv)
				if ret:
					self._cpv_sort_ascending(ret)
			self._match_cache[orig_atom] = ret
			return ret[:]

		def _visible(self, pkg):
			if pkg.installed and "selective" not in self._depgraph.myparams:
				try:
					arg = self._depgraph._iter_atoms_for_pkg(pkg).next()
				except (StopIteration, portage.exception.InvalidDependString):
					arg = None
				if arg:
					return False
				if pkg.installed:
					try:
						if not visible(
							self._depgraph.pkgsettings[pkg.root], pkg):
							return False
					except portage.exception.InvalidDependString:
						pass
			return True

		def _dep_expand(self, atom):
			"""
			This is only needed for old installed packages that may
			contain atoms that are not fully qualified with a specific
			category. Emulate the cpv_expand() function that's used by
			dbapi.match() in cases like this. If there are multiple
			matches, it's often due to a new-style virtual that has
			been added, so try to filter those out to avoid raising
			a ValueError.
			"""
			root_config = self._depgraph.roots[self._root]
			orig_atom = atom
			expanded_atoms = self._depgraph._dep_expand(root_config, atom)
			if len(expanded_atoms) > 1:
				non_virtual_atoms = []
				for x in expanded_atoms:
					if not portage.dep_getkey(x).startswith("virtual/"):
						non_virtual_atoms.append(x)
				if len(non_virtual_atoms) == 1:
					expanded_atoms = non_virtual_atoms
			if len(expanded_atoms) > 1:
				# compatible with portage.cpv_expand()
				raise ValueError([portage.dep_getkey(x) \
					for x in expanded_atoms])
			if expanded_atoms:
				atom = expanded_atoms[0]
			else:
				null_atom = insert_category_into_atom(atom, "null")
				null_cp = portage.dep_getkey(null_atom)
				cat, atom_pn = portage.catsplit(null_cp)
				virts_p = root_config.settings.get_virts_p().get(atom_pn)
				if virts_p:
					# Allow the resolver to choose which virtual.
					atom = insert_category_into_atom(atom, "virtual")
				else:
					atom = insert_category_into_atom(atom, "null")
			return atom

		def aux_get(self, cpv, wants):
			metadata = self._cpv_pkg_map[cpv].metadata
			return [metadata.get(x, "") for x in wants]

	class _package_cache(dict):
		def __init__(self, depgraph):
			dict.__init__(self)
			self._depgraph = depgraph

		def __setitem__(self, k, v):
			dict.__setitem__(self, k, v)
			root_config = self._depgraph.roots[v.root]
			try:
				if visible(root_config.settings, v) and \
					not (v.installed and \
					v.root_config.settings._getMissingKeywords(v.cpv, v.metadata)):
					root_config.visible_pkgs.cpv_inject(v)
			except portage.exception.InvalidDependString:
				pass

class RepoDisplay(object):
	def __init__(self, roots):
		self._shown_repos = {}
		self._unknown_repo = False
		repo_paths = set()
		for root_config in roots.itervalues():
			portdir = root_config.settings.get("PORTDIR")
			if portdir:
				repo_paths.add(portdir)
			overlays = root_config.settings.get("PORTDIR_OVERLAY")
			if overlays:
				repo_paths.update(overlays.split())
		repo_paths = list(repo_paths)
		self._repo_paths = repo_paths
		self._repo_paths_real = [ os.path.realpath(repo_path) \
			for repo_path in repo_paths ]

		# pre-allocate index for PORTDIR so that it always has index 0.
		for root_config in roots.itervalues():
			portdb = root_config.trees["porttree"].dbapi
			portdir = portdb.porttree_root
			if portdir:
				self.repoStr(portdir)

	def repoStr(self, repo_path_real):
		real_index = -1
		if repo_path_real:
			real_index = self._repo_paths_real.index(repo_path_real)
		if real_index == -1:
			s = "?"
			self._unknown_repo = True
		else:
			shown_repos = self._shown_repos
			repo_paths = self._repo_paths
			repo_path = repo_paths[real_index]
			index = shown_repos.get(repo_path)
			if index is None:
				index = len(shown_repos)
				shown_repos[repo_path] = index
			s = str(index)
		return s

	def __str__(self):
		output = []
		shown_repos = self._shown_repos
		unknown_repo = self._unknown_repo
		if shown_repos or self._unknown_repo:
			output.append("Portage tree and overlays:\n")
		show_repo_paths = list(shown_repos)
		for repo_path, repo_index in shown_repos.iteritems():
			show_repo_paths[repo_index] = repo_path
		if show_repo_paths:
			for index, repo_path in enumerate(show_repo_paths):
				output.append(" "+teal("["+str(index)+"]")+" %s\n" % repo_path)
		if unknown_repo:
			output.append(" "+teal("[?]") + \
				" indicates that the source repository could not be determined\n")
		return "".join(output)

class PackageCounters(object):

	def __init__(self):
		self.upgrades   = 0
		self.downgrades = 0
		self.new        = 0
		self.newslot    = 0
		self.reinst     = 0
		self.uninst     = 0
		self.blocks     = 0
		self.blocks_satisfied         = 0
		self.totalsize  = 0
		self.restrict_fetch           = 0
		self.restrict_fetch_satisfied = 0

	def __str__(self):
		total_installs = self.upgrades + self.downgrades + self.newslot + self.new + self.reinst
		myoutput = []
		details = []
		myoutput.append("Total: %s package" % total_installs)
		if total_installs != 1:
			myoutput.append("s")
		if total_installs != 0:
			myoutput.append(" (")
		if self.upgrades > 0:
			details.append("%s upgrade" % self.upgrades)
			if self.upgrades > 1:
				details[-1] += "s"
		if self.downgrades > 0:
			details.append("%s downgrade" % self.downgrades)
			if self.downgrades > 1:
				details[-1] += "s"
		if self.new > 0:
			details.append("%s new" % self.new)
		if self.newslot > 0:
			details.append("%s in new slot" % self.newslot)
			if self.newslot > 1:
				details[-1] += "s"
		if self.reinst > 0:
			details.append("%s reinstall" % self.reinst)
			if self.reinst > 1:
				details[-1] += "s"
		if self.uninst > 0:
			details.append("%s uninstall" % self.uninst)
			if self.uninst > 1:
				details[-1] += "s"
		myoutput.append(", ".join(details))
		if total_installs != 0:
			myoutput.append(")")
		myoutput.append(", Size of downloads: %s" % format_size(self.totalsize))
		if self.restrict_fetch:
			myoutput.append("\nFetch Restriction: %s package" % \
				self.restrict_fetch)
			if self.restrict_fetch > 1:
				myoutput.append("s")
		if self.restrict_fetch_satisfied < self.restrict_fetch:
			myoutput.append(bad(" (%s unsatisfied)") % \
				(self.restrict_fetch - self.restrict_fetch_satisfied))
		if self.blocks > 0:
			myoutput.append("\nConflict: %s block" % \
				self.blocks)
			if self.blocks > 1:
				myoutput.append("s")
			if self.blocks_satisfied < self.blocks:
				myoutput.append(bad(" (%s unsatisfied)") % \
					(self.blocks - self.blocks_satisfied))
		return "".join(myoutput)

class Scheduler(object):

	_opts_ignore_blockers = \
		frozenset(["--buildpkgonly",
		"--fetchonly", "--fetch-all-uri",
		"--nodeps", "--pretend"])

	_fetch_log = "/var/log/emerge-fetch.log"

	class _iface_class(SlotObject):
		__slots__ = ("register", "schedule", "unregister")

	class _build_opts_class(SlotObject):
		__slots__ = ("buildpkg", "buildpkgonly",
			"fetch_all_uri", "fetchonly", "pretend")

	class _pkg_count_class(SlotObject):
		__slots__ = ("curval", "maxval")

	class _emerge_log_class(SlotObject):
		__slots__ = ("xterm_titles",)

		def log(self, *pargs, **kwargs):
			emergelog(self.xterm_titles, *pargs, **kwargs)

	def __init__(self, settings, trees, mtimedb, myopts,
		spinner, mergelist, favorites, digraph):
		self.settings = settings
		self.target_root = settings["ROOT"]
		self.trees = trees
		self.myopts = myopts
		self._spinner = spinner
		self._mtimedb = mtimedb
		self._mergelist = mergelist
		self._favorites = favorites
		self._args_set = InternalPackageSet(favorites)
		self._build_opts = self._build_opts_class()
		for k in self._build_opts.__slots__:
			setattr(self._build_opts, k, "--" + k.replace("_", "-") in myopts)
		self.edebug = 0
		if settings.get("PORTAGE_DEBUG", "") == "1":
			self.edebug = 1
		self.pkgsettings = {}
		for root in trees:
			self.pkgsettings[root] = portage.config(
				clone=trees[root]["vartree"].settings)
		self.curval = 0
		self._logger = self._emerge_log_class(
			xterm_titles=("notitles" not in settings.features))
		self._sched_iface = self._iface_class(
			register=self._register, schedule=self._schedule,
				unregister=self._unregister)
		self._poll_event_handlers = {}
		self._poll = select.poll()
		from collections import deque
		self._task_queue = deque()
		self._running_tasks = set()
		self._max_jobs = 1
		self._parallel_fetch = False
		features = self.settings.features
		if "parallel-fetch" in features and \
			not ("--pretend" in self.myopts or \
			"--fetch-all-uri" in self.myopts or \
			"--fetchonly" in self.myopts):
			if "distlocks" not in features:
				portage.writemsg(red("!!!")+"\n", noiselevel=-1)
				portage.writemsg(red("!!!")+" parallel-fetching " + \
					"requires the distlocks feature enabled"+"\n",
					noiselevel=-1)
				portage.writemsg(red("!!!")+" you have it disabled, " + \
					"thus parallel-fetching is being disabled"+"\n",
					noiselevel=-1)
				portage.writemsg(red("!!!")+"\n", noiselevel=-1)
			elif len(mergelist) > 1:
				self._parallel_fetch = True

				# clear out existing fetch log if it exists
				try:
					open(self._fetch_log, 'w')
				except EnvironmentError:
					pass

	def _add_task(self, task):
		self._task_queue.append(task)

	class _pkg_failure(portage.exception.PortageException):
		"""
		An instance of this class is raised by unmerge() when
		an uninstallation fails.
		"""
		status = 1
		def __init__(self, *pargs):
			portage.exception.PortageException.__init__(self, pargs)
			if pargs:
				self.status = pargs[0]

	def _find_blockers(self, new_pkg):
		"""
		Returns a callable which should be called only when
		the vdb lock has been acquired.
		"""
		def get_blockers():
			return self._find_blockers_with_lock(new_pkg, acquire_lock=0)
		return get_blockers

	def _find_blockers_with_lock(self, new_pkg, acquire_lock=0):
		if self._opts_ignore_blockers.intersection(self.myopts):
			return None

		# Call gc.collect() here to avoid heap overflow that
		# triggers 'Cannot allocate memory' errors (reported
		# with python-2.5).
		import gc
		gc.collect()

		blocker_db = BlockerDB(self.trees[new_pkg.root]["root_config"])

		blocker_dblinks = []
		for blocking_pkg in blocker_db.findInstalledBlockers(
			new_pkg, acquire_lock=acquire_lock):
			if new_pkg.slot_atom == blocking_pkg.slot_atom:
				continue
			if new_pkg.cpv == blocking_pkg.cpv:
				continue
			blocker_dblinks.append(portage.dblink(
				blocking_pkg.category, blocking_pkg.pf, blocking_pkg.root,
				self.pkgsettings[blocking_pkg.root], treetype="vartree",
				vartree=self.trees[blocking_pkg.root]["vartree"]))

		gc.collect()

		return blocker_dblinks

	def merge(self):

		keep_going = "--keep-going" in self.myopts
		running_tasks = self._running_tasks

		while True:
			try:
				rval = self._merge()
			finally:
				# clean up child process if necessary
				self._task_queue.clear()
				while running_tasks:
					task = running_tasks.pop()
					task.cancel()

			if rval == os.EX_OK or not keep_going:
				break
			mtimedb = self._mtimedb
			if "resume" not in mtimedb:
				break
			mergelist = self._mtimedb["resume"].get("mergelist")
			if not mergelist:
				break
			if mergelist[0][-1] != "merge":
				break

			# Skip the first one because it failed to build or install.
			pkg_key = tuple(mergelist[0])
			del mergelist[0]
			failed_pkg = None
			for task in self._mergelist:
				if task == pkg_key:
					failed_pkg = task
					break
			if failed_pkg is None:
				break
			if not mergelist:
				break

			mylist, dropped_tasks = self._calc_resume_list()
			clear_caches(self.trees)
			if not mylist:
				break

			if dropped_tasks:

				def _eerror(lines):
					for l in lines:
						eerror(l, phase="other", key=failed_pkg.cpv)

				msg = []
				msg.append("One or more packages have been " + \
					"dropped due to unsatisfied dependencies:")
				msg.append("")
				msg.extend("  " + str(task) for task in dropped_tasks)
				msg.append("")
				_eerror(msg)
				del _eerror, msg
			del dropped_tasks
			self._mergelist = mylist

		return rval

	def _calc_resume_list(self):
		"""
		Use the current resume list to calculate a new one,
		dropping any packages with unsatisfied deps.
		"""
		print colorize("GOOD", "*** Resuming merge...")

		show_spinner = "--quiet" not in self.myopts and \
			"--nodeps" not in self.myopts

		if show_spinner:
			print "Calculating dependencies  ",

		myparams = create_depgraph_params(self.myopts, None)
		success, mydepgraph, dropped_tasks = resume_depgraph(
			self.settings, self.trees, self._mtimedb, self.myopts,
			myparams, self._spinner, skip_unsatisfied=True)

		if show_spinner:
			print "\b\b... done!"

		if not success:
			mydepgraph.display_problems()
			return (None, None)

		mylist = mydepgraph.altlist()
		mydepgraph.break_refs(mylist)
		mydepgraph.break_refs(dropped_tasks)
		return (mylist, dropped_tasks)

	def _register(self, f, eventmask, handler):
		self._poll_event_handlers[f] = handler
		self._poll.register(f, eventmask)

	def _unregister(self, f):
		self._poll.unregister(f)
		del self._poll_event_handlers[f]
		self._schedule_tasks()

	def _schedule(self):
		event_handlers = self._poll_event_handlers
		running_tasks = self._running_tasks
		poll = self._poll.poll

		self._schedule_tasks()

		while event_handlers:
			for f, event in poll():
				event_handlers[f](f, event)

			if len(event_handlers) <= len(running_tasks):
				# Assuming one handler per task, this
				# means the caller has unregistered it's
				# handler, so it's time to yield.
				break

	def _schedule_tasks(self):
		task_queue = self._task_queue
		running_tasks = self._running_tasks
		max_jobs = self._max_jobs
		state_changed = False

		for task in list(running_tasks):
			if task.poll() is not None:
				running_tasks.remove(task)
				state_changed = True

		while task_queue and (len(running_tasks) < max_jobs):
			task = task_queue.popleft()
			cancelled = getattr(task, "cancelled", None)
			if not cancelled:
				task.start()
				running_tasks.add(task)
			state_changed = True

		return state_changed

	def _merge(self):
		mylist = self._mergelist
		favorites = self._favorites
		mtimedb = self._mtimedb
		buildpkgonly = "--buildpkgonly" in self.myopts
		failed_fetches = []
		fetchonly = "--fetchonly" in self.myopts or \
			"--fetch-all-uri" in self.myopts
		oneshot = "--oneshot" in self.myopts or \
			"--onlydeps" in self.myopts
		pretend = "--pretend" in self.myopts
		ldpath_mtimes = mtimedb["ldpath"]
		logger = self._logger

		if "--resume" in self.myopts:
			# We're resuming.
			print colorize("GOOD", "*** Resuming merge...")
			self._logger.log(" *** Resuming merge...")

		# Do this before verifying the ebuild Manifests since it might
		# be possible for the user to use --resume --skipfirst get past
		# a non-essential package with a broken digest.
		mtimedb["resume"]["mergelist"] = [list(x) for x in mylist \
			if isinstance(x, Package) and x.operation == "merge"]
		mtimedb.commit()

		prefetchers = weakref.WeakValueDictionary()
		getbinpkg = "--getbinpkg" in self.myopts

		if self._parallel_fetch:
			portage.writemsg(">>> starting parallel fetch\n")
			for pkg in mylist:
				if not isinstance(pkg, Package):
					continue
				if pkg.type_name == "ebuild":
					self._add_task(EbuildFetcherAsync(
						log_file=self._fetch_log,
						pkg=pkg, register=self._register,
						unregister=self._unregister))
				elif pkg.type_name == "binary" and getbinpkg and \
					pkg.root_config.trees["bintree"].isremote(pkg.cpv):
					prefetcher = BinpkgFetcherAsync(
						log_file=self._fetch_log,
						pkg=pkg, register=self._register,
						unregister=self._unregister)
					prefetchers[pkg] = prefetcher
					self._add_task(prefetcher)
					del prefetcher

		# Verify all the manifests now so that the user is notified of failure
		# as soon as possible.
		if "--fetchonly" not in self.myopts and \
			"--fetch-all-uri" not in self.myopts and \
			"strict" in self.settings.features:
			shown_verifying_msg = False
			quiet_settings = {}
			for myroot, pkgsettings in self.pkgsettings.iteritems():
				quiet_config = portage.config(clone=pkgsettings)
				quiet_config["PORTAGE_QUIET"] = "1"
				quiet_config.backup_changes("PORTAGE_QUIET")
				quiet_settings[myroot] = quiet_config
				del quiet_config
			for x in mylist:
				if x[0] != "ebuild" or x[-1] == "nomerge":
					continue
				if not shown_verifying_msg:
					shown_verifying_msg = True
					print ">>> Verifying ebuild Manifests..."
				mytype, myroot, mycpv, mystatus = x
				portdb = self.trees[myroot]["porttree"].dbapi
				quiet_config = quiet_settings[myroot]
				quiet_config["O"] = os.path.dirname(portdb.findname(mycpv))
				if not portage.digestcheck([], quiet_config, strict=True):
					return 1
				del x, mytype, myroot, mycpv, mystatus, quiet_config
			del shown_verifying_msg, quiet_settings

		root_config = self.trees[self.target_root]["root_config"]
		mymergelist = mylist
		myfeat = self.settings.features[:]
		bad_resume_opts = set(["--ask", "--changelog", "--skipfirst",
			"--resume"])
		metadata_keys = [k for k in portage.auxdbkeys \
			if not k.startswith("UNUSED_")] + ["USE"]

		task_list = mymergelist
		# Filter mymergelist so that all the len(mymergelist) calls
		# below (for display) do not count Uninstall instances.
		mymergelist = [x for x in mymergelist if x[-1] == "merge"]
		pkg_count = self._pkg_count_class(
			curval=0, maxval=len(mymergelist))
		for x in task_list:
			if x[0] == "blocks":
				continue
			pkg_type, myroot, pkg_key, operation = x
			built = pkg_type != "ebuild"
			installed = pkg_type == "installed"
			portdb = self.trees[myroot]["porttree"].dbapi
			bindb  = self.trees[myroot]["bintree"].dbapi
			vartree = self.trees[myroot]["vartree"]
			vardb = vartree.dbapi
			root_config = self.trees[myroot]["root_config"]
			if pkg_type == "blocks":
				pass
			elif pkg_type == "ebuild":
				mydbapi = portdb
			else:
				if pkg_type == "binary":
					mydbapi = bindb
				elif pkg_type == "installed":
					mydbapi = vardb
				else:
					raise AssertionError("Package type: '%s'" % pkg_type)
			if not x.installed:
				pkg_count.curval += 1
			try:
				self._execute_task(bad_resume_opts,
					failed_fetches,
					mydbapi, pkg_count,
					myfeat, mymergelist, x,
					prefetchers)
			except self._pkg_failure, e:
				return e.status
		return self._post_merge(mtimedb,
			self._logger.xterm_titles, failed_fetches)

	def _execute_task(self, bad_resume_opts,
		failed_fetches, mydbapi, pkg_count, myfeat,
		mymergelist, pkg, prefetchers):
			favorites = self._favorites
			mtimedb = self._mtimedb
			mergecount = pkg_count.curval
			pkgsettings = self.pkgsettings[pkg.root]
			buildpkgonly = "--buildpkgonly" in self.myopts
			fetch_all = "--fetch-all-uri" in self.myopts
			fetchonly = fetch_all or "--fetchonly" in self.myopts
			
			oneshot = "--oneshot" in self.myopts or \
				"--onlydeps" in self.myopts
			pretend = "--pretend" in self.myopts
			ldpath_mtimes = mtimedb["ldpath"]
			xterm_titles = "notitles" not in self.settings.features

			x = pkg
			y = None
			root_config = pkg.root_config
			system_set = root_config.sets["system"]
			args_set = InternalPackageSet(favorites)
			world_set = root_config.sets["world"]
			vartree = self.trees[pkg.root]["vartree"]
			portdb = root_config.trees["porttree"].dbapi
			bindb = root_config.trees["bintree"].dbapi
			pkg_type, myroot, pkg_key, operation = x
			pkgindex = 2
			metadata = pkg.metadata
			if pkg.installed:
				if not (buildpkgonly or fetchonly or pretend):
					uninstall = PackageUninstall(ldpath_mtimes=ldpath_mtimes,
						opts=self.myopts, pkg=pkg, settings=pkgsettings)
					retval = uninstall.execute()
					if retval != os.EX_OK:
						raise self._pkg_failure(retval)
				return

			if x[0]=="blocks":
				pkgindex=3

			if "--pretend" not in self.myopts:
				print "\n>>> Emerging (" + \
					colorize("MERGE_LIST_PROGRESS", str(mergecount)) + " of " + \
					colorize("MERGE_LIST_PROGRESS", str(len(mymergelist))) + ") " + \
					colorize("GOOD", x[pkgindex]) + " to " + x[1]
				emergelog(xterm_titles, " >>> emerge ("+\
					str(mergecount)+" of "+str(len(mymergelist))+\
					") "+x[pkgindex]+" to "+x[1])

			self._schedule()

			if x.type_name == "ebuild":
				y = portdb.findname(pkg.cpv)
				build = EbuildBuild(args_set=self._args_set,
					find_blockers=self._find_blockers(pkg),
					ldpath_mtimes=ldpath_mtimes, logger=self._logger,
					opts=self._build_opts, pkg=pkg, pkg_count=pkg_count,
					settings=pkgsettings, scheduler=self._sched_iface)
				retval = build.execute()
				if retval != os.EX_OK:
					raise self._pkg_failure(retval)

			elif x.type_name == "binary":
				# The prefetcher have already completed or it
				# could be running now. If it's running now,
				# wait for it to complete since it holds
				# a lock on the file being fetched. The
				# portage.locks functions are only designed
				# to work between separate processes. Since
				# the lock is held by the current process,
				# use the scheduler and fetcher methods to
				# synchronize with the fetcher.
				prefetcher = prefetchers.get(pkg)
				if prefetcher is not None:
					if not prefetcher.isAlive():
						writemsg(">>> prefetcher not alive, cancelling\n")
						prefetcher.cancel()
					else:
						writemsg(">>> prefetcher alive, waiting\n")
						retval = None
						while retval is None:
							self._schedule()
							retval = prefetcher.poll()
					del prefetcher
				else:
					writemsg(">>> prefetcher does not exist\n")

				fetcher = BinpkgFetcher(pkg=pkg, pretend=pretend,
					use_locks=("distlocks" in pkgsettings.features))
				mytbz2 = fetcher.pkg_path
				y = mytbz2
				if "--getbinpkg" in self.myopts:
					retval = fetcher.execute()
					if fetcher.remote:
						msg = " --- (%s of %s) Fetching Binary (%s::%s)" %\
							(mergecount, len(mymergelist), pkg_key, mytbz2)
						short_msg = "emerge: (%s of %s) %s Fetch" % \
							(mergecount, len(mymergelist), pkg_key)
						emergelog(xterm_titles, msg, short_msg=short_msg)

					if retval != os.EX_OK:
						failed_fetches.append(pkg.cpv)
						if not fetchonly:
							raise self._pkg_failure()

				if "--fetchonly" in self.myopts or \
					"--fetch-all-uri" in self.myopts:
					self.curval += 1
					return

				short_msg = "emerge: ("+str(mergecount)+" of "+str(len(mymergelist))+") "+x[pkgindex]+" Merge Binary"
				emergelog(xterm_titles, " === ("+str(mergecount)+\
					" of "+str(len(mymergelist))+") Merging Binary ("+\
					x[pkgindex]+"::"+mytbz2+")", short_msg=short_msg)
				merge = BinpkgMerge(find_blockers=self._find_blockers(pkg),
					ldpath_mtimes=ldpath_mtimes, pkg=pkg, pretend=pretend,
					pkg_path=fetcher.pkg_path, settings=pkgsettings)
				retval = merge.execute()
				if retval != os.EX_OK:
					raise self._pkg_failure(retval)
				#need to check for errors
			if not buildpkgonly:
				if not (fetchonly or oneshot or pretend) and \
					args_set.findAtomForPackage(pkg):
					world_set.lock()
					world_set.load() # maybe it's changed on disk
					myfavkey = create_world_atom(pkg, args_set, root_config)
					if myfavkey:
						print ">>> Recording",myfavkey,"in \"world\" favorites file..."
						emergelog(xterm_titles, " === ("+\
							str(mergecount)+" of "+\
							str(len(mymergelist))+\
							") Updating world file ("+x[pkgindex]+")")
						world_set.add(myfavkey)
					world_set.unlock()

				if "--pretend" not in self.myopts and \
					"--fetchonly" not in self.myopts and \
					"--fetch-all-uri" not in self.myopts:

					# Figure out if we need a restart.
					if myroot == "/" and pkg.cp == "sys-apps/portage":
						if len(mymergelist) > mergecount:
							emergelog(xterm_titles,
								" ::: completed emerge ("+ \
								str(mergecount)+" of "+ \
								str(len(mymergelist))+") "+ \
								x[2]+" to "+x[1])
							emergelog(xterm_titles, " *** RESTARTING " + \
								"emerge via exec() after change of " + \
								"portage version.")
							del mtimedb["resume"]["mergelist"][0]
							mtimedb.commit()
							portage.run_exitfuncs()
							mynewargv=[sys.argv[0],"--resume"]
							resume_opts = self.myopts.copy()
							# For automatic resume, we need to prevent
							# any of bad_resume_opts from leaking in
							# via EMERGE_DEFAULT_OPTS.
							resume_opts["--ignore-default-opts"] = True
							for myopt, myarg in resume_opts.iteritems():
								if myopt not in bad_resume_opts:
									if myarg is True:
										mynewargv.append(myopt)
									else:
										mynewargv.append(myopt +"="+ myarg)
							# priority only needs to be adjusted on the first run
							os.environ["PORTAGE_NICENESS"] = "0"
							os.execv(mynewargv[0], mynewargv)

			if "--pretend" not in self.myopts and \
				"--fetchonly" not in self.myopts and \
				"--fetch-all-uri" not in self.myopts:
				if "noclean" not in self.settings.features:
					short_msg = "emerge: (%s of %s) %s Clean Post" % \
						(mergecount, len(mymergelist), x[pkgindex])
					emergelog(xterm_titles, (" === (%s of %s) " + \
						"Post-Build Cleaning (%s::%s)") % \
						(mergecount, len(mymergelist), pkg.cpv, y),
						short_msg=short_msg)
				emergelog(xterm_titles, " ::: completed emerge ("+\
					str(mergecount)+" of "+str(len(mymergelist))+") "+\
					x[2]+" to "+x[1])

			# Unsafe for parallel merges
			del mtimedb["resume"]["mergelist"][0]
			# Commit after each merge so that --resume may still work in
			# in the event that portage is not allowed to exit normally
			# due to power failure, SIGKILL, etc...
			mtimedb.commit()
			self.curval += 1

	def _post_merge(self, mtimedb, xterm_titles, failed_fetches):
		if "--pretend" not in self.myopts:
			emergelog(xterm_titles, " *** Finished. Cleaning up...")

		# We're out of the loop... We're done. Delete the resume data.
		if "resume" in mtimedb:
			del mtimedb["resume"]
		mtimedb.commit()

		#by doing an exit this way, --fetchonly can continue to try to
		#fetch everything even if a particular download fails.
		if "--fetchonly" in self.myopts or "--fetch-all-uri" in self.myopts:
			if failed_fetches:
				sys.stderr.write("\n\n!!! Some fetch errors were " + \
					"encountered.  Please see above for details.\n\n")
				for cpv in failed_fetches:
					sys.stderr.write("   ")
					sys.stderr.write(cpv)
					sys.stderr.write("\n")
				sys.stderr.write("\n")
				sys.exit(1)
			else:
				sys.exit(0)
		return os.EX_OK

class UninstallFailure(portage.exception.PortageException):
	"""
	An instance of this class is raised by unmerge() when
	an uninstallation fails.
	"""
	status = 1
	def __init__(self, *pargs):
		portage.exception.PortageException.__init__(self, pargs)
		if pargs:
			self.status = pargs[0]

def unmerge(root_config, myopts, unmerge_action,
	unmerge_files, ldpath_mtimes, autoclean=0,
	clean_world=1, ordered=0, raise_on_error=0):
	settings = root_config.settings
	sets = root_config.sets
	vartree = root_config.trees["vartree"]
	candidate_catpkgs=[]
	global_unmerge=0
	xterm_titles = "notitles" not in settings.features

	pkg_cache = {}

	def _pkg(cpv):
		pkg = pkg_cache.get(cpv)
		if pkg is None:
			pkg = Package(cpv=cpv, installed=True,
				metadata=izip(Package.metadata_keys,
					vartree.dbapi.aux_get(cpv, Package.metadata_keys)),
				root_config=root_config,
				type_name="installed")
			pkg_cache[cpv] = pkg
		return pkg

	vdb_path = os.path.join(settings["ROOT"], portage.VDB_PATH)
	try:
		# At least the parent needs to exist for the lock file.
		portage.util.ensure_dirs(vdb_path)
	except portage.exception.PortageException:
		pass
	vdb_lock = None
	try:
		if os.access(vdb_path, os.W_OK):
			vdb_lock = portage.locks.lockdir(vdb_path)
		realsyslist = sets["system"].getAtoms()
		syslist = []
		for x in realsyslist:
			mycp = portage.dep_getkey(x)
			if mycp in settings.getvirtuals():
				providers = []
				for provider in settings.getvirtuals()[mycp]:
					if vartree.dbapi.match(provider):
						providers.append(provider)
				if len(providers) == 1:
					syslist.extend(providers)
			else:
				syslist.append(mycp)
	
		mysettings = portage.config(clone=settings)
	
		if not unmerge_files:
			if unmerge_action == "unmerge":
				print
				print bold("emerge unmerge") + " can only be used with specific package names"
				print
				return 0
			else:
				global_unmerge = 1
	
		localtree = vartree
		# process all arguments and add all
		# valid db entries to candidate_catpkgs
		if global_unmerge:
			if not unmerge_files:
				candidate_catpkgs.extend(vartree.dbapi.cp_all())
		else:
			#we've got command-line arguments
			if not unmerge_files:
				print "\nNo packages to unmerge have been provided.\n"
				return 0
			for x in unmerge_files:
				arg_parts = x.split('/')
				if x[0] not in [".","/"] and \
					arg_parts[-1][-7:] != ".ebuild":
					#possible cat/pkg or dep; treat as such
					candidate_catpkgs.append(x)
				elif unmerge_action in ["prune","clean"]:
					print "\n!!! Prune and clean do not accept individual" + \
						" ebuilds as arguments;\n    skipping.\n"
					continue
				else:
					# it appears that the user is specifying an installed
					# ebuild and we're in "unmerge" mode, so it's ok.
					if not os.path.exists(x):
						print "\n!!! The path '"+x+"' doesn't exist.\n"
						return 0
	
					absx   = os.path.abspath(x)
					sp_absx = absx.split("/")
					if sp_absx[-1][-7:] == ".ebuild":
						del sp_absx[-1]
						absx = "/".join(sp_absx)
	
					sp_absx_len = len(sp_absx)
	
					vdb_path = os.path.join(settings["ROOT"], portage.VDB_PATH)
					vdb_len  = len(vdb_path)
	
					sp_vdb     = vdb_path.split("/")
					sp_vdb_len = len(sp_vdb)
	
					if not os.path.exists(absx+"/CONTENTS"):
						print "!!! Not a valid db dir: "+str(absx)
						return 0
	
					if sp_absx_len <= sp_vdb_len:
						# The Path is shorter... so it can't be inside the vdb.
						print sp_absx
						print absx
						print "\n!!!",x,"cannot be inside "+ \
							vdb_path+"; aborting.\n"
						return 0
	
					for idx in range(0,sp_vdb_len):
						if idx >= sp_absx_len or sp_vdb[idx] != sp_absx[idx]:
							print sp_absx
							print absx
							print "\n!!!", x, "is not inside "+\
								vdb_path+"; aborting.\n"
							return 0
	
					print "="+"/".join(sp_absx[sp_vdb_len:])
					candidate_catpkgs.append(
						"="+"/".join(sp_absx[sp_vdb_len:]))
	
		newline=""
		if (not "--quiet" in myopts):
			newline="\n"
		if settings["ROOT"] != "/":
			print darkgreen(newline+ \
				">>> Using system located in ROOT tree "+settings["ROOT"])
		if (("--pretend" in myopts) or ("--ask" in myopts)) and \
			not ("--quiet" in myopts):
			print darkgreen(newline+\
				">>> These are the packages that would be unmerged:")

		# Preservation of order is required for --depclean and --prune so
		# that dependencies are respected. Use all_selected to eliminate
		# duplicate packages since the same package may be selected by
		# multiple atoms.
		pkgmap = []
		all_selected = set()
		for x in candidate_catpkgs:
			# cycle through all our candidate deps and determine
			# what will and will not get unmerged
			try:
				mymatch=localtree.dep_match(x)
			except KeyError:
				mymatch=None
			except ValueError, errpkgs:
				print "\n\n!!! The short ebuild name \"" + \
					x + "\" is ambiguous.  Please specify"
				print "!!! one of the following fully-qualified " + \
					"ebuild names instead:\n"
				for i in errpkgs[0]:
					print "    " + green(i)
				print
				sys.exit(1)
	
			if not mymatch and x[0] not in "<>=~":
				mymatch = localtree.dep_match(x)
			if not mymatch:
				portage.writemsg("\n--- Couldn't find '%s' to %s.\n" % \
					(x, unmerge_action), noiselevel=-1)
				continue

			pkgmap.append(
				{"protected": set(), "selected": set(), "omitted": set()})
			mykey = len(pkgmap) - 1
			if unmerge_action=="unmerge":
					for y in mymatch:
						if y not in all_selected:
							pkgmap[mykey]["selected"].add(y)
							all_selected.add(y)
			elif unmerge_action == "prune":
				if len(mymatch) == 1:
					continue
				best_version = mymatch[0]
				best_slot = vartree.getslot(best_version)
				best_counter = vartree.dbapi.cpv_counter(best_version)
				for mypkg in mymatch[1:]:
					myslot = vartree.getslot(mypkg)
					mycounter = vartree.dbapi.cpv_counter(mypkg)
					if (myslot == best_slot and mycounter > best_counter) or \
						mypkg == portage.best([mypkg, best_version]):
						if myslot == best_slot:
							if mycounter < best_counter:
								# On slot collision, keep the one with the
								# highest counter since it is the most
								# recently installed.
								continue
						best_version = mypkg
						best_slot = myslot
						best_counter = mycounter
				pkgmap[mykey]["protected"].add(best_version)
				pkgmap[mykey]["selected"].update(mypkg for mypkg in mymatch \
					if mypkg != best_version and mypkg not in all_selected)
				all_selected.update(pkgmap[mykey]["selected"])
			else:
				# unmerge_action == "clean"
				slotmap={}
				for mypkg in mymatch:
					if unmerge_action == "clean":
						myslot = localtree.getslot(mypkg)
					else:
						# since we're pruning, we don't care about slots
						# and put all the pkgs in together
						myslot = 0
					if myslot not in slotmap:
						slotmap[myslot] = {}
					slotmap[myslot][localtree.dbapi.cpv_counter(mypkg)] = mypkg
				
				for myslot in slotmap:
					counterkeys = slotmap[myslot].keys()
					if not counterkeys:
						continue
					counterkeys.sort()
					pkgmap[mykey]["protected"].add(
						slotmap[myslot][counterkeys[-1]])
					del counterkeys[-1]
					#be pretty and get them in order of merge:
					for ckey in counterkeys:
						mypkg = slotmap[myslot][ckey]
						if mypkg not in all_selected:
							pkgmap[mykey]["selected"].add(mypkg)
							all_selected.add(mypkg)
					# ok, now the last-merged package
					# is protected, and the rest are selected
		numselected = len(all_selected)
		if global_unmerge and not numselected:
			portage.writemsg_stdout("\n>>> No outdated packages were found on your system.\n")
			return 0
	
		if not numselected:
			portage.writemsg_stdout(
				"\n>>> No packages selected for removal by " + \
				unmerge_action + "\n")
			return 0
	finally:
		if vdb_lock:
			vartree.dbapi.flush_cache()
			portage.locks.unlockdir(vdb_lock)
	
	from portage.sets.base import EditablePackageSet
	
	# generate a list of package sets that are directly or indirectly listed in "world",
	# as there is no persistent list of "installed" sets
	installed_sets = ["world"]
	stop = False
	pos = 0
	while not stop:
		stop = True
		pos = len(installed_sets)
		for s in installed_sets[pos - 1:]:
			candidates = [x[len(SETPREFIX):] for x in sets[s].getNonAtoms() if x.startswith(SETPREFIX)]
			if candidates:
				stop = False
				installed_sets += candidates
	installed_sets = [x for x in installed_sets if x not in root_config.setconfig.active]
	del stop, pos

	# we don't want to unmerge packages that are still listed in user-editable package sets
	# listed in "world" as they would be remerged on the next update of "world" or the 
	# relevant package sets.
	for cp in xrange(len(pkgmap)):
		for cpv in pkgmap[cp]["selected"].copy():
			try:
				pkg = _pkg(cpv)
			except KeyError:
				# It could have been uninstalled
				# by a concurrent process.
				continue
			parents = []
			for s in installed_sets:
				# skip sets that the user requested to unmerge, and skip world 
				# unless we're unmerging a package set (as the package would be 
				# removed from "world" later on)
				if s in root_config.setconfig.active or (s == "world" and not root_config.setconfig.active):
					continue
				# only check instances of EditablePackageSet as other classes are generally used for
				# special purposes and can be ignored here (and are usually generated dynamically, so the
				# user can't do much about them anyway)
				if isinstance(sets[s], EditablePackageSet):

					# This is derived from a snippet of code in the
					# depgraph._iter_atoms_for_pkg() method.
					for atom in sets[s].iterAtomsForPackage(pkg):
						inst_matches = vartree.dbapi.match(atom)
						inst_matches.reverse() # descending order
						higher_slot = None
						for inst_cpv in inst_matches:
							try:
								inst_pkg = _pkg(inst_cpv)
							except KeyError:
								# It could have been uninstalled
								# by a concurrent process.
								continue

							if inst_pkg.cp != atom.cp:
								continue
							if pkg >= inst_pkg:
								# This is descending order, and we're not
								# interested in any versions <= pkg given.
								break
							if pkg.slot_atom != inst_pkg.slot_atom:
								higher_slot = inst_pkg
								break
						if higher_slot is None:
							parents.append(s)
							break
			if parents:
				#print colorize("WARN", "Package %s is going to be unmerged," % cpv)
				#print colorize("WARN", "but still listed in the following package sets:")
				#print "    %s\n" % ", ".join(parents)
				print colorize("WARN", "Not unmerging package %s as it is" % cpv)
				print colorize("WARN", "still referenced by the following package sets:")
				print "    %s\n" % ", ".join(parents)
				# adjust pkgmap so the display output is correct
				pkgmap[cp]["selected"].remove(cpv)
				pkgmap[cp]["protected"].add(cpv)
	
	del installed_sets

	# Unmerge order only matters in some cases
	if not ordered:
		unordered = {}
		for d in pkgmap:
			selected = d["selected"]
			if not selected:
				continue
			cp = portage.cpv_getkey(iter(selected).next())
			cp_dict = unordered.get(cp)
			if cp_dict is None:
				cp_dict = {}
				unordered[cp] = cp_dict
				for k in d:
					cp_dict[k] = set()
			for k, v in d.iteritems():
				cp_dict[k].update(v)
		pkgmap = [unordered[cp] for cp in sorted(unordered)]

	for x in xrange(len(pkgmap)):
		selected = pkgmap[x]["selected"]
		if not selected:
			continue
		for mytype, mylist in pkgmap[x].iteritems():
			if mytype == "selected":
				continue
			mylist.difference_update(all_selected)
		cp = portage.cpv_getkey(iter(selected).next())
		for y in localtree.dep_match(cp):
			if y not in pkgmap[x]["omitted"] and \
				y not in pkgmap[x]["selected"] and \
				y not in pkgmap[x]["protected"] and \
				y not in all_selected:
				pkgmap[x]["omitted"].add(y)
		if global_unmerge and not pkgmap[x]["selected"]:
			#avoid cluttering the preview printout with stuff that isn't getting unmerged
			continue
		if not (pkgmap[x]["protected"] or pkgmap[x]["omitted"]) and cp in syslist:
			print colorize("BAD","\a\n\n!!! '%s' is part of your system profile." % cp)
			print colorize("WARN","\a!!! Unmerging it may be damaging to your system.\n")
			if "--pretend" not in myopts and "--ask" not in myopts:
				countdown(int(settings["EMERGE_WARNING_DELAY"]),
					colorize("UNMERGE_WARN", "Press Ctrl-C to Stop"))
		if "--quiet" not in myopts:
			print "\n "+bold(cp)
		else:
			print bold(cp)+": ",
		for mytype in ["selected","protected","omitted"]:
			if "--quiet" not in myopts:
				portage.writemsg_stdout((mytype + ": ").rjust(14), noiselevel=-1)
			if pkgmap[x][mytype]:
				sorted_pkgs = [portage.catpkgsplit(mypkg)[1:] for mypkg in pkgmap[x][mytype]]
				sorted_pkgs.sort(portage.pkgcmp)
				for pn, ver, rev in sorted_pkgs:
					if rev == "r0":
						myversion = ver
					else:
						myversion = ver + "-" + rev
					if mytype == "selected":
						portage.writemsg_stdout(
							colorize("UNMERGE_WARN", myversion + " "), noiselevel=-1)
					else:
						portage.writemsg_stdout(
							colorize("GOOD", myversion + " "), noiselevel=-1)
			else:
				portage.writemsg_stdout("none ", noiselevel=-1)
			if "--quiet" not in myopts:
				portage.writemsg_stdout("\n", noiselevel=-1)
		if "--quiet" in myopts:
			portage.writemsg_stdout("\n", noiselevel=-1)

	portage.writemsg_stdout("\n>>> " + colorize("UNMERGE_WARN", "'Selected'") + \
		" packages are slated for removal.\n")
	portage.writemsg_stdout(">>> " + colorize("GOOD", "'Protected'") + \
			" and " + colorize("GOOD", "'omitted'") + \
			" packages will not be removed.\n\n")

	if "--pretend" in myopts:
		#we're done... return
		return 0
	if "--ask" in myopts:
		if userquery("Would you like to unmerge these packages?")=="No":
			# enter pretend mode for correct formatting of results
			myopts["--pretend"] = True
			print
			print "Quitting."
			print
			return 0
	#the real unmerging begins, after a short delay....
	if not autoclean:
		countdown(int(settings["CLEAN_DELAY"]), ">>> Unmerging")

	for x in xrange(len(pkgmap)):
		for y in pkgmap[x]["selected"]:
			print ">>> Unmerging "+y+"..."
			emergelog(xterm_titles, "=== Unmerging... ("+y+")")
			mysplit = y.split("/")
			#unmerge...
			retval = portage.unmerge(mysplit[0], mysplit[1], settings["ROOT"],
				mysettings, unmerge_action not in ["clean","prune"],
				vartree=vartree, ldpath_mtimes=ldpath_mtimes)
			if retval != os.EX_OK:
				emergelog(xterm_titles, " !!! unmerge FAILURE: "+y)
				if raise_on_error:
					raise UninstallFailure(retval)
				sys.exit(retval)
			else:
				if clean_world:
					sets["world"].cleanPackage(vartree.dbapi, y)
				emergelog(xterm_titles, " >>> unmerge success: "+y)
	if clean_world:
		for s in root_config.setconfig.active:
			sets["world"].remove(SETPREFIX+s)
	return 1

def chk_updated_info_files(root, infodirs, prev_mtimes, retval):

	if os.path.exists("/usr/bin/install-info"):
		regen_infodirs=[]
		for z in infodirs:
			if z=='':
				continue
			inforoot=normpath(root+z)
			if os.path.isdir(inforoot):
				infomtime = long(os.stat(inforoot).st_mtime)
				if inforoot not in prev_mtimes or \
					prev_mtimes[inforoot] != infomtime:
						regen_infodirs.append(inforoot)

		if not regen_infodirs:
			portage.writemsg_stdout("\n "+green("*")+" GNU info directory index is up-to-date.\n")
		else:
			portage.writemsg_stdout("\n "+green("*")+" Regenerating GNU info directory index...\n")

			dir_extensions = ("", ".gz", ".bz2")
			icount=0
			badcount=0
			for inforoot in regen_infodirs:
				if inforoot=='':
					continue

				if not os.path.isdir(inforoot) or \
					not os.access(inforoot, os.W_OK):
					continue
				errmsg = ""
				file_list = os.listdir(inforoot)
				file_list.sort()
				dir_file = os.path.join(inforoot, "dir")
				moved_old_dir = False
				processed_count = 0
				for x in file_list:
					if x.startswith(".") or \
						os.path.isdir(os.path.join(inforoot, x)):
						continue
					if x.startswith("dir"):
						skip = False
						for ext in dir_extensions:
							if x == "dir" + ext or \
								x == "dir" + ext + ".old":
								skip = True
								break
						if skip:
							continue
					if processed_count == 0:
						for ext in dir_extensions:
							try:
								os.rename(dir_file + ext, dir_file + ext + ".old")
								moved_old_dir = True
							except EnvironmentError, e:
								if e.errno != errno.ENOENT:
									raise
								del e
					processed_count += 1
					myso=commands.getstatusoutput("LANG=C LANGUAGE=C /usr/bin/install-info --dir-file="+inforoot+"/dir "+inforoot+"/"+x)[1]
					existsstr="already exists, for file `"
					if myso!="":
						if re.search(existsstr,myso):
							# Already exists... Don't increment the count for this.
							pass
						elif myso[:44]=="install-info: warning: no info dir entry in ":
							# This info file doesn't contain a DIR-header: install-info produces this
							# (harmless) warning (the --quiet switch doesn't seem to work).
							# Don't increment the count for this.
							pass
						else:
							badcount=badcount+1
							errmsg += myso + "\n"
					icount=icount+1

				if moved_old_dir and not os.path.exists(dir_file):
					# We didn't generate a new dir file, so put the old file
					# back where it was originally found.
					for ext in dir_extensions:
						try:
							os.rename(dir_file + ext + ".old", dir_file + ext)
						except EnvironmentError, e:
							if e.errno != errno.ENOENT:
								raise
							del e

				# Clean dir.old cruft so that they don't prevent
				# unmerge of otherwise empty directories.
				for ext in dir_extensions:
					try:
						os.unlink(dir_file + ext + ".old")
					except EnvironmentError, e:
						if e.errno != errno.ENOENT:
							raise
						del e

				#update mtime so we can potentially avoid regenerating.
				prev_mtimes[inforoot] = long(os.stat(inforoot).st_mtime)

			if badcount:
				print " "+yellow("*")+" Processed",icount,"info files;",badcount,"errors."
				print errmsg
			else:
				if icount > 0:
					print " "+green("*")+" Processed",icount,"info files."


def display_news_notification(trees):
	for target_root in trees:
		if len(trees) > 1 and target_root != "/":
			break
	settings = trees[target_root]["vartree"].settings
	portdb = trees[target_root]["porttree"].dbapi
	vardb = trees[target_root]["vartree"].dbapi
	NEWS_PATH = os.path.join("metadata", "news")
	UNREAD_PATH = os.path.join(target_root, NEWS_LIB_PATH, "news")
	newsReaderDisplay = False

	for repo in portdb.getRepositories():
		unreadItems = checkUpdatedNewsItems(
			portdb, vardb, NEWS_PATH, UNREAD_PATH, repo)
		if unreadItems:
			if not newsReaderDisplay:
				newsReaderDisplay = True
				print
			print colorize("WARN", " * IMPORTANT:"),
			print "%s news items need reading for repository '%s'." % (unreadItems, repo)
			
	
	if newsReaderDisplay:
		print colorize("WARN", " *"),
		print "Use " + colorize("GOOD", "eselect news") + " to read news items."
		print

def post_emerge(trees, mtimedb, retval):
	"""
	Misc. things to run at the end of a merge session.
	
	Update Info Files
	Update Config Files
	Update News Items
	Commit mtimeDB
	Display preserved libs warnings
	Exit Emerge

	@param trees: A dictionary mapping each ROOT to it's package databases
	@type trees: dict
	@param mtimedb: The mtimeDB to store data needed across merge invocations
	@type mtimedb: MtimeDB class instance
	@param retval: Emerge's return value
	@type retval: Int
	@rype: None
	@returns:
	1.  Calls sys.exit(retval)
	"""
	for target_root in trees:
		if len(trees) > 1 and target_root != "/":
			break
	vardbapi = trees[target_root]["vartree"].dbapi
	settings = vardbapi.settings
	info_mtimes = mtimedb["info"]

	# Load the most current variables from ${ROOT}/etc/profile.env
	settings.unlock()
	settings.reload()
	settings.regenerate()
	settings.lock()

	config_protect = settings.get("CONFIG_PROTECT","").split()
	infodirs = settings.get("INFOPATH","").split(":") + \
		settings.get("INFODIR","").split(":")

	os.chdir("/")

	if retval == os.EX_OK:
		exit_msg = " *** exiting successfully."
	else:
		exit_msg = " *** exiting unsuccessfully with status '%s'." % retval
	emergelog("notitles" not in settings.features, exit_msg)

	# Dump the mod_echo output now so that our other notifications are shown
	# last.
	try:
		from portage.elog import mod_echo
	except ImportError:
		pass # happens during downgrade to a version without the module
	else:
		mod_echo.finalize()

	vdb_path = os.path.join(target_root, portage.VDB_PATH)
	portage.util.ensure_dirs(vdb_path)
	vdb_lock = None
	if os.access(vdb_path, os.W_OK):
		vdb_lock = portage.locks.lockdir(vdb_path)

	if vdb_lock:
		try:
			if "noinfo" not in settings.features:
				chk_updated_info_files(target_root,
					infodirs, info_mtimes, retval)
			mtimedb.commit()
		finally:
			if vdb_lock:
				portage.locks.unlockdir(vdb_lock)

	chk_updated_cfg_files(target_root, config_protect)
	
	display_news_notification(trees)
	
	if vardbapi.plib_registry.hasEntries():
		print
		print colorize("WARN", "!!!") + " existing preserved libs:"
		plibdata = vardbapi.plib_registry.getPreservedLibs()
		for cpv in plibdata:
			print colorize("WARN", ">>>") + " package: %s" % cpv
			for f in plibdata[cpv]:
				print colorize("WARN", " * ") + " - %s" % f
		print "Use " + colorize("GOOD", "emerge @preserved-rebuild") + " to rebuild packages using these libraries"

	sys.exit(retval)


def chk_updated_cfg_files(target_root, config_protect):
	if config_protect:
		#number of directories with some protect files in them
		procount=0
		for x in config_protect:
			x = os.path.join(target_root, x.lstrip(os.path.sep))
			if not os.access(x, os.W_OK):
				# Avoid Permission denied errors generated
				# later by `find`.
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
				mycommand = "find '%s' -iname '._cfg????_*'" % x
			else:
				mycommand = "find '%s' -maxdepth 1 -iname '._cfg????_%s'" % \
					os.path.split(x.rstrip(os.path.sep))
			mycommand += " ! -iname '.*~' ! -iname '.*.bak' -print0"
			a = commands.getstatusoutput(mycommand)
			if a[0] != 0:
				sys.stderr.write(" %s error scanning '%s': " % (bad("*"), x))
				sys.stderr.flush()
				# Show the error message alone, sending stdout to /dev/null.
				os.system(mycommand + " 1>/dev/null")
			else:
				files = a[1].split('\0')
				# split always produces an empty string as the last element
				if files and not files[-1]:
					del files[-1]
				if files:
					procount += 1
					print "\n"+colorize("WARN", " * IMPORTANT:"),
					if stat.S_ISDIR(mymode):
						 print "%d config files in '%s' need updating." % \
							(len(files), x)
					else:
						 print "config file '%s' needs updating." % x

		if procount:
			print " "+yellow("*")+" See the "+colorize("INFORM","CONFIGURATION FILES")+ \
				" section of the " + bold("emerge")
			print " "+yellow("*")+" man page to learn how to update config files."

def checkUpdatedNewsItems(portdb, vardb, NEWS_PATH, UNREAD_PATH, repo_id):
	"""
	Examines news items in repodir + '/' + NEWS_PATH and attempts to find unread items
	Returns the number of unread (yet relevent) items.
	
	@param portdb: a portage tree database
	@type portdb: pordbapi
	@param vardb: an installed package database
	@type vardb: vardbapi
	@param NEWS_PATH:
	@type NEWS_PATH:
	@param UNREAD_PATH:
	@type UNREAD_PATH:
	@param repo_id:
	@type repo_id:
	@rtype: Integer
	@returns:
	1.  The number of unread but relevant news items.
	
	"""
	from portage.news import NewsManager
	manager = NewsManager(portdb, vardb, NEWS_PATH, UNREAD_PATH)
	return manager.getUnreadItems( repo_id, update=True )

def insert_category_into_atom(atom, category):
	alphanum = re.search(r'\w', atom)
	if alphanum:
		ret = atom[:alphanum.start()] + "%s/" % category + \
			atom[alphanum.start():]
	else:
		ret = None
	return ret

def is_valid_package_atom(x):
	if "/" not in x:
		alphanum = re.search(r'\w', x)
		if alphanum:
			x = x[:alphanum.start()] + "cat/" + x[alphanum.start():]
	return portage.isvalidatom(x)

def show_blocker_docs_link():
	print
	print "For more information about " + bad("Blocked Packages") + ", please refer to the following"
	print "section of the Gentoo Linux x86 Handbook (architecture is irrelevant):"
	print
	print "http://www.gentoo.org/doc/en/handbook/handbook-x86.xml?full=1#blocked"
	print

def show_mask_docs():
	print "For more information, see the MASKED PACKAGES section in the emerge"
	print "man page or refer to the Gentoo Handbook."

def action_sync(settings, trees, mtimedb, myopts, myaction):
	xterm_titles = "notitles" not in settings.features
	emergelog(xterm_titles, " === sync")
	myportdir = settings.get("PORTDIR", None)
	if not myportdir:
		sys.stderr.write("!!! PORTDIR is undefined.  Is /etc/make.globals missing?\n")
		sys.exit(1)
	if myportdir[-1]=="/":
		myportdir=myportdir[:-1]
	if not os.path.exists(myportdir):
		print ">>>",myportdir,"not found, creating it."
		os.makedirs(myportdir,0755)
	syncuri=settings["SYNC"].rstrip()
	os.umask(0022)
	updatecache_flg = False
	if myaction == "metadata":
		print "skipping sync"
		updatecache_flg = True
	elif syncuri[:8]=="rsync://":
		if not os.path.exists("/usr/bin/rsync"):
			print "!!! /usr/bin/rsync does not exist, so rsync support is disabled."
			print "!!! Type \"emerge net-misc/rsync\" to enable rsync support."
			sys.exit(1)
		mytimeout=180

		rsync_opts = []
		import shlex, StringIO
		if settings["PORTAGE_RSYNC_OPTS"] == "":
			portage.writemsg("PORTAGE_RSYNC_OPTS empty or unset, using hardcoded defaults\n")
			rsync_opts.extend([
				"--recursive",    # Recurse directories
				"--links",        # Consider symlinks
				"--safe-links",   # Ignore links outside of tree
				"--perms",        # Preserve permissions
				"--times",        # Preserive mod times
				"--compress",     # Compress the data transmitted
				"--force",        # Force deletion on non-empty dirs
				"--whole-file",   # Don't do block transfers, only entire files
				"--delete",       # Delete files that aren't in the master tree
				"--stats",        # Show final statistics about what was transfered
				"--timeout="+str(mytimeout), # IO timeout if not done in X seconds
				"--exclude=/distfiles",   # Exclude distfiles from consideration
				"--exclude=/local",       # Exclude local     from consideration
				"--exclude=/packages",    # Exclude packages  from consideration
			])

		else:
			# The below validation is not needed when using the above hardcoded
			# defaults.

			portage.writemsg("Using PORTAGE_RSYNC_OPTS instead of hardcoded defaults\n", 1)
			lexer = shlex.shlex(StringIO.StringIO(
				settings.get("PORTAGE_RSYNC_OPTS","")), posix=True)
			lexer.whitespace_split = True
			rsync_opts.extend(lexer)
			del lexer

			for opt in ("--recursive", "--times"):
				if opt not in rsync_opts:
					portage.writemsg(yellow("WARNING:") + " adding required option " + \
					"%s not included in PORTAGE_RSYNC_OPTS\n" % opt)
					rsync_opts.append(opt)
	
			for exclude in ("distfiles", "local", "packages"):
				opt = "--exclude=/%s" % exclude
				if opt not in rsync_opts:
					portage.writemsg(yellow("WARNING:") + \
					" adding required option %s not included in "  % opt + \
					"PORTAGE_RSYNC_OPTS (can be overridden with --exclude='!')\n")
					rsync_opts.append(opt)
	
			if settings["RSYNC_TIMEOUT"] != "":
				portage.writemsg("WARNING: usage of RSYNC_TIMEOUT is deprecated, " + \
				"use PORTAGE_RSYNC_EXTRA_OPTS instead\n")
				try:
					mytimeout = int(settings["RSYNC_TIMEOUT"])
					rsync_opts.append("--timeout=%d" % mytimeout)
				except ValueError, e:
					portage.writemsg("!!! %s\n" % str(e))
	
			# TODO: determine options required for official servers
			if syncuri.rstrip("/").endswith(".gentoo.org/gentoo-portage"):

				def rsync_opt_startswith(opt_prefix):
					for x in rsync_opts:
						if x.startswith(opt_prefix):
							return True
					return False

				if not rsync_opt_startswith("--timeout="):
					rsync_opts.append("--timeout=%d" % mytimeout)

				for opt in ("--compress", "--whole-file"):
					if opt not in rsync_opts:
						portage.writemsg(yellow("WARNING:") + " adding required option " + \
						"%s not included in PORTAGE_RSYNC_OPTS\n" % opt)
						rsync_opts.append(opt)

		if "--quiet" in myopts:
			rsync_opts.append("--quiet")    # Shut up a lot
		else:
			rsync_opts.append("--verbose")	# Print filelist

		if "--verbose" in myopts:
			rsync_opts.append("--progress")  # Progress meter for each file

		if "--debug" in myopts:
			rsync_opts.append("--checksum") # Force checksum on all files

		if settings["RSYNC_EXCLUDEFROM"] != "":
			portage.writemsg(yellow("WARNING:") + \
			" usage of RSYNC_EXCLUDEFROM is deprecated, use " + \
			"PORTAGE_RSYNC_EXTRA_OPTS instead\n")
			if os.path.exists(settings["RSYNC_EXCLUDEFROM"]):
				rsync_opts.append("--exclude-from=%s" % \
				settings["RSYNC_EXCLUDEFROM"])
			else:
				portage.writemsg("!!! RSYNC_EXCLUDEFROM specified," + \
				" but file does not exist.\n")

		if settings["RSYNC_RATELIMIT"] != "":
			portage.writemsg(yellow("WARNING:") + \
			" usage of RSYNC_RATELIMIT is deprecated, use " + \
			"PORTAGE_RSYNC_EXTRA_OPTS instead")
			rsync_opts.append("--bwlimit=%s" % \
			settings["RSYNC_RATELIMIT"])

		# Real local timestamp file.
		servertimestampfile = os.path.join(
			myportdir, "metadata", "timestamp.chk")

		content = portage.util.grabfile(servertimestampfile)
		mytimestamp = 0
		if content:
			try:
				mytimestamp = time.mktime(time.strptime(content[0],
					"%a, %d %b %Y %H:%M:%S +0000"))
			except (OverflowError, ValueError):
				pass
		del content

		try:
			rsync_initial_timeout = \
				int(settings.get("PORTAGE_RSYNC_INITIAL_TIMEOUT", "15"))
		except ValueError:
			rsync_initial_timeout = 15

		try:
			if "RSYNC_RETRIES" in settings:
				print yellow("WARNING:")+" usage of RSYNC_RETRIES is deprecated, use PORTAGE_RSYNC_RETRIES instead"
				maxretries=int(settings["RSYNC_RETRIES"])				
			else:
				maxretries=int(settings["PORTAGE_RSYNC_RETRIES"])
		except SystemExit, e:
			raise # Needed else can't exit
		except:
			maxretries=3 #default number of retries

		retries=0
		user_name, hostname, port = re.split(
			"rsync://([^:/]+@)?([^:/]*)(:[0-9]+)?", syncuri, maxsplit=3)[1:4]
		if port is None:
			port=""
		if user_name is None:
			user_name=""
		updatecache_flg=True
		all_rsync_opts = set(rsync_opts)
		lexer = shlex.shlex(StringIO.StringIO(
			settings.get("PORTAGE_RSYNC_EXTRA_OPTS","")), posix=True)
		lexer.whitespace_split = True
		extra_rsync_opts = list(lexer)
		del lexer
		all_rsync_opts.update(extra_rsync_opts)
		family = socket.AF_INET
		if "-4" in all_rsync_opts or "--ipv4" in all_rsync_opts:
			family = socket.AF_INET
		elif socket.has_ipv6 and \
			("-6" in all_rsync_opts or "--ipv6" in all_rsync_opts):
			family = socket.AF_INET6
		ips=[]
		SERVER_OUT_OF_DATE = -1
		EXCEEDED_MAX_RETRIES = -2
		while (1):
			if ips:
				del ips[0]
			if ips==[]:
				try:
					for addrinfo in socket.getaddrinfo(
						hostname, None, family, socket.SOCK_STREAM):
						if addrinfo[0] == socket.AF_INET6:
							# IPv6 addresses need to be enclosed in square brackets
							ips.append("[%s]" % addrinfo[4][0])
						else:
							ips.append(addrinfo[4][0])
					from random import shuffle
					shuffle(ips)
				except SystemExit, e:
					raise # Needed else can't exit
				except Exception, e:
					print "Notice:",str(e)
					dosyncuri=syncuri

			if ips:
				try:
					dosyncuri = syncuri.replace(
						"//" + user_name + hostname + port + "/",
						"//" + user_name + ips[0] + port + "/", 1)
				except SystemExit, e:
					raise # Needed else can't exit
				except Exception, e:
					print "Notice:",str(e)
					dosyncuri=syncuri

			if (retries==0):
				if "--ask" in myopts:
					if userquery("Do you want to sync your Portage tree with the mirror at\n" + blue(dosyncuri) + bold("?"))=="No":
						print
						print "Quitting."
						print
						sys.exit(0)
				emergelog(xterm_titles, ">>> Starting rsync with " + dosyncuri)
				if "--quiet" not in myopts:
					print ">>> Starting rsync with "+dosyncuri+"..."
			else:
				emergelog(xterm_titles,
					">>> Starting retry %d of %d with %s" % \
						(retries,maxretries,dosyncuri))
				print "\n\n>>> Starting retry %d of %d with %s" % (retries,maxretries,dosyncuri)

			if mytimestamp != 0 and "--quiet" not in myopts:
				print ">>> Checking server timestamp ..."

			rsynccommand = ["/usr/bin/rsync"] + rsync_opts + extra_rsync_opts

			if "--debug" in myopts:
				print rsynccommand

			exitcode = os.EX_OK
			servertimestamp = 0
			# Even if there's no timestamp available locally, fetch the
			# timestamp anyway as an initial probe to verify that the server is
			# responsive.  This protects us from hanging indefinitely on a
			# connection attempt to an unresponsive server which rsync's
			# --timeout option does not prevent.
			if True:
				# Temporary file for remote server timestamp comparison.
				from tempfile import mkstemp
				fd, tmpservertimestampfile = mkstemp()
				os.close(fd)
				mycommand = rsynccommand[:]
				mycommand.append(dosyncuri.rstrip("/") + \
					"/metadata/timestamp.chk")
				mycommand.append(tmpservertimestampfile)
				content = None
				mypids = []
				try:
					def timeout_handler(signum, frame):
						raise portage.exception.PortageException("timed out")
					signal.signal(signal.SIGALRM, timeout_handler)
					# Timeout here in case the server is unresponsive.  The
					# --timeout rsync option doesn't apply to the initial
					# connection attempt.
					if rsync_initial_timeout:
						signal.alarm(rsync_initial_timeout)
					try:
						mypids.extend(portage.process.spawn(
							mycommand, env=settings.environ(), returnpid=True))
						exitcode = os.waitpid(mypids[0], 0)[1]
						content = portage.grabfile(tmpservertimestampfile)
					finally:
						if rsync_initial_timeout:
							signal.alarm(0)
						try:
							os.unlink(tmpservertimestampfile)
						except OSError:
							pass
				except portage.exception.PortageException, e:
					# timed out
					print e
					del e
					if mypids and os.waitpid(mypids[0], os.WNOHANG) == (0,0):
						os.kill(mypids[0], signal.SIGTERM)
						os.waitpid(mypids[0], 0)
					# This is the same code rsync uses for timeout.
					exitcode = 30
				else:
					if exitcode != os.EX_OK:
						if exitcode & 0xff:
							exitcode = (exitcode & 0xff) << 8
						else:
							exitcode = exitcode >> 8
				if mypids:
					portage.process.spawned_pids.remove(mypids[0])
				if content:
					try:
						servertimestamp = time.mktime(time.strptime(
							content[0], "%a, %d %b %Y %H:%M:%S +0000"))
					except (OverflowError, ValueError):
						pass
				del mycommand, mypids, content
			if exitcode == os.EX_OK:
				if (servertimestamp != 0) and (servertimestamp == mytimestamp):
					emergelog(xterm_titles,
						">>> Cancelling sync -- Already current.")
					print
					print ">>>"
					print ">>> Timestamps on the server and in the local repository are the same."
					print ">>> Cancelling all further sync action. You are already up to date."
					print ">>>"
					print ">>> In order to force sync, remove '%s'." % servertimestampfile
					print ">>>"
					print
					sys.exit(0)
				elif (servertimestamp != 0) and (servertimestamp < mytimestamp):
					emergelog(xterm_titles,
						">>> Server out of date: %s" % dosyncuri)
					print
					print ">>>"
					print ">>> SERVER OUT OF DATE: %s" % dosyncuri
					print ">>>"
					print ">>> In order to force sync, remove '%s'." % servertimestampfile
					print ">>>"
					print
					exitcode = SERVER_OUT_OF_DATE
				elif (servertimestamp == 0) or (servertimestamp > mytimestamp):
					# actual sync
					mycommand = rsynccommand + [dosyncuri+"/", myportdir]
					exitcode = portage.process.spawn(mycommand,
						env=settings.environ())
					if exitcode in [0,1,3,4,11,14,20,21]:
						break
			elif exitcode in [1,3,4,11,14,20,21]:
				break
			else:
				# Code 2 indicates protocol incompatibility, which is expected
				# for servers with protocol < 29 that don't support
				# --prune-empty-directories.  Retry for a server that supports
				# at least rsync protocol version 29 (>=rsync-2.6.4).
				pass

			retries=retries+1

			if retries<=maxretries:
				print ">>> Retrying..."
				time.sleep(11)
			else:
				# over retries
				# exit loop
				updatecache_flg=False
				exitcode = EXCEEDED_MAX_RETRIES
				break

		if (exitcode==0):
			emergelog(xterm_titles, "=== Sync completed with %s" % dosyncuri)
		elif exitcode == SERVER_OUT_OF_DATE:
			sys.exit(1)
		elif exitcode == EXCEEDED_MAX_RETRIES:
			sys.stderr.write(
				">>> Exceeded PORTAGE_RSYNC_RETRIES: %s\n" % maxretries)
			sys.exit(1)
		elif (exitcode>0):
			print
			if exitcode==1:
				print darkred("!!!")+green(" Rsync has reported that there is a syntax error. Please ensure")
				print darkred("!!!")+green(" that your SYNC statement is proper.")
				print darkred("!!!")+green(" SYNC="+settings["SYNC"])
			elif exitcode==11:
				print darkred("!!!")+green(" Rsync has reported that there is a File IO error. Normally")
				print darkred("!!!")+green(" this means your disk is full, but can be caused by corruption")
				print darkred("!!!")+green(" on the filesystem that contains PORTDIR. Please investigate")
				print darkred("!!!")+green(" and try again after the problem has been fixed.")
				print darkred("!!!")+green(" PORTDIR="+settings["PORTDIR"])
			elif exitcode==20:
				print darkred("!!!")+green(" Rsync was killed before it finished.")
			else:
				print darkred("!!!")+green(" Rsync has not successfully finished. It is recommended that you keep")
				print darkred("!!!")+green(" trying or that you use the 'emerge-webrsync' option if you are unable")
				print darkred("!!!")+green(" to use rsync due to firewall or other restrictions. This should be a")
				print darkred("!!!")+green(" temporary problem unless complications exist with your network")
				print darkred("!!!")+green(" (and possibly your system's filesystem) configuration.")
			print
			sys.exit(exitcode)
	elif syncuri[:6]=="cvs://":
		if not os.path.exists("/usr/bin/cvs"):
			print "!!! /usr/bin/cvs does not exist, so CVS support is disabled."
			print "!!! Type \"emerge dev-util/cvs\" to enable CVS support."
			sys.exit(1)
		cvsroot=syncuri[6:]
		cvsdir=os.path.dirname(myportdir)
		if not os.path.exists(myportdir+"/CVS"):
			#initial checkout
			print ">>> Starting initial cvs checkout with "+syncuri+"..."
			if os.path.exists(cvsdir+"/gentoo-x86"):
				print "!!! existing",cvsdir+"/gentoo-x86 directory; exiting."
				sys.exit(1)
			try:
				os.rmdir(myportdir)
			except OSError, e:
				if e.errno != errno.ENOENT:
					sys.stderr.write(
						"!!! existing '%s' directory; exiting.\n" % myportdir)
					sys.exit(1)
				del e
			if portage.spawn("cd "+cvsdir+"; cvs -z0 -d "+cvsroot+" co -P gentoo-x86",settings,free=1):
				print "!!! cvs checkout error; exiting."
				sys.exit(1)
			os.rename(os.path.join(cvsdir, "gentoo-x86"), myportdir)
		else:
			#cvs update
			print ">>> Starting cvs update with "+syncuri+"..."
			retval = portage.spawn("cd '%s'; cvs -z0 -q update -dP" % \
				myportdir, settings, free=1)
			if retval != os.EX_OK:
				sys.exit(retval)
		dosyncuri = syncuri
	else:
		print "!!! rsync setting: ",syncuri,"not recognized; exiting."
		sys.exit(1)

	if updatecache_flg and  \
		myaction != "metadata" and \
		"metadata-transfer" not in settings.features:
		updatecache_flg = False

	# Reload the whole config from scratch.
	settings, trees, mtimedb = load_emerge_config(trees=trees)
	portdb = trees[settings["ROOT"]]["porttree"].dbapi

	if os.path.exists(myportdir+"/metadata/cache") and updatecache_flg:
		action_metadata(settings, portdb, myopts)

	if portage._global_updates(trees, mtimedb["updates"]):
		mtimedb.commit()
		# Reload the whole config from scratch.
		settings, trees, mtimedb = load_emerge_config(trees=trees)
		portdb = trees[settings["ROOT"]]["porttree"].dbapi

	mybestpv = portdb.xmatch("bestmatch-visible", "sys-apps/portage")
	mypvs = portage.best(
		trees[settings["ROOT"]]["vartree"].dbapi.match("sys-apps/portage"))

	chk_updated_cfg_files("/", settings.get("CONFIG_PROTECT","").split())

	if myaction != "metadata":
		if os.access(portage.USER_CONFIG_PATH + "/bin/post_sync", os.X_OK):
			retval = portage.process.spawn(
				[os.path.join(portage.USER_CONFIG_PATH, "bin", "post_sync"),
				dosyncuri], env=settings.environ())
			if retval != os.EX_OK:
				print red(" * ")+bold("spawn failed of "+ portage.USER_CONFIG_PATH + "/bin/post_sync")

	if(mybestpv != mypvs) and not "--quiet" in myopts:
		print
		print red(" * ")+bold("An update to portage is available.")+" It is _highly_ recommended"
		print red(" * ")+"that you update portage now, before any other packages are updated."
		print
		print red(" * ")+"To update portage, run 'emerge portage' now."
		print
	
	display_news_notification(trees)

def action_metadata(settings, portdb, myopts):
	portage.writemsg_stdout("\n>>> Updating Portage cache:      ")
	old_umask = os.umask(0002)
	cachedir = os.path.normpath(settings.depcachedir)
	if cachedir in ["/",    "/bin", "/dev",  "/etc",  "/home",
					"/lib", "/opt", "/proc", "/root", "/sbin",
					"/sys", "/tmp", "/usr",  "/var"]:
		print >> sys.stderr, "!!! PORTAGE_DEPCACHEDIR IS SET TO A PRIMARY " + \
			"ROOT DIRECTORY ON YOUR SYSTEM."
		print >> sys.stderr, \
			"!!! This is ALMOST CERTAINLY NOT what you want: '%s'" % cachedir
		sys.exit(73)
	if not os.path.exists(cachedir):
		os.mkdir(cachedir)

	ec = portage.eclass_cache.cache(portdb.porttree_root)
	myportdir = os.path.realpath(settings["PORTDIR"])
	cm = settings.load_best_module("portdbapi.metadbmodule")(
		myportdir, "metadata/cache", portage.auxdbkeys[:], readonly=True)

	from portage.cache import util

	class percentage_noise_maker(util.quiet_mirroring):
		def __init__(self, dbapi):
			self.dbapi = dbapi
			self.cp_all = dbapi.cp_all()
			l = len(self.cp_all)
			self.call_update_min = 100000000
			self.min_cp_all = l/100.0
			self.count = 1
			self.pstr = ''

		def __iter__(self):
			for x in self.cp_all:
				self.count += 1
				if self.count > self.min_cp_all:
					self.call_update_min = 0
					self.count = 0
				for y in self.dbapi.cp_list(x):
					yield y
			self.call_update_mine = 0

		def update(self, *arg):
			try:				self.pstr = int(self.pstr) + 1
			except ValueError:	self.pstr = 1
			sys.stdout.write("%s%i%%" % \
				("\b" * (len(str(self.pstr))+1), self.pstr))
			sys.stdout.flush()
			self.call_update_min = 10000000

		def finish(self, *arg):
			sys.stdout.write("\b\b\b\b100%\n")
			sys.stdout.flush()

	if "--quiet" in myopts:
		def quicky_cpv_generator(cp_all_list):
			for x in cp_all_list:
				for y in portdb.cp_list(x):
					yield y
		source = quicky_cpv_generator(portdb.cp_all())
		noise_maker = portage.cache.util.quiet_mirroring()
	else:
		noise_maker = source = percentage_noise_maker(portdb)
	portage.cache.util.mirror_cache(source, cm, portdb.auxdb[myportdir],
		eclass_cache=ec, verbose_instance=noise_maker)

	sys.stdout.flush()
	os.umask(old_umask)

def action_regen(settings, portdb):
	xterm_titles = "notitles" not in settings.features
	emergelog(xterm_titles, " === regen")
	#regenerate cache entries
	portage.writemsg_stdout("Regenerating cache entries...\n")
	try:
		os.close(sys.stdin.fileno())
	except SystemExit, e:
		raise # Needed else can't exit
	except:
		pass
	sys.stdout.flush()
	mynodes = portdb.cp_all()
	from portage.cache.cache_errors import CacheError
	dead_nodes = {}
	for mytree in portdb.porttrees:
		try:
			dead_nodes[mytree] = set(portdb.auxdb[mytree].iterkeys())
		except CacheError, e:
			portage.writemsg("Error listing cache entries for " + \
				"'%s': %s, continuing...\n" % (mytree, e), noiselevel=-1)
			del e
			dead_nodes = None
			break
	for x in mynodes:
		mymatches = portdb.cp_list(x)
		portage.writemsg_stdout("Processing %s\n" % x)
		for y in mymatches:
			try:
				foo = portdb.aux_get(y,["DEPEND"])
			except (KeyError, portage.exception.PortageException), e:
				portage.writemsg(
					"Error processing %(cpv)s, continuing... (%(e)s)\n" % \
					{"cpv":y,"e":str(e)}, noiselevel=-1)
			if dead_nodes:
				for mytree in portdb.porttrees:
					if portdb.findname2(y, mytree=mytree)[0]:
						dead_nodes[mytree].discard(y)
	if dead_nodes:
		for mytree, nodes in dead_nodes.iteritems():
			auxdb = portdb.auxdb[mytree]
			for y in nodes:
				try:
					del auxdb[y]
				except (KeyError, CacheError):
					pass
	portage.writemsg_stdout("done!\n")

def action_config(settings, trees, myopts, myfiles):
	if len(myfiles) != 1:
		print red("!!! config can only take a single package atom at this time\n")
		sys.exit(1)
	if not is_valid_package_atom(myfiles[0]):
		portage.writemsg("!!! '%s' is not a valid package atom.\n" % myfiles[0],
			noiselevel=-1)
		portage.writemsg("!!! Please check ebuild(5) for full details.\n")
		portage.writemsg("!!! (Did you specify a version but forget to prefix with '='?)\n")
		sys.exit(1)
	print
	try:
		pkgs = trees[settings["ROOT"]]["vartree"].dbapi.match(myfiles[0])
	except ValueError, e:
		# Multiple matches thrown from cpv_expand
		pkgs = e.args[0]
	if len(pkgs) == 0:
		print "No packages found.\n"
		sys.exit(0)
	elif len(pkgs) > 1:
		if "--ask" in myopts:
			options = []
			print "Please select a package to configure:"
			idx = 0
			for pkg in pkgs:
				idx += 1
				options.append(str(idx))
				print options[-1]+") "+pkg
			print "X) Cancel"
			options.append("X")
			idx = userquery("Selection?", options)
			if idx == "X":
				sys.exit(0)
			pkg = pkgs[int(idx)-1]
		else:
			print "The following packages available:"
			for pkg in pkgs:
				print "* "+pkg
			print "\nPlease use a specific atom or the --ask option."
			sys.exit(1)
	else:
		pkg = pkgs[0]

	print
	if "--ask" in myopts:
		if userquery("Ready to configure "+pkg+"?") == "No":
			sys.exit(0)
	else:
		print "Configuring pkg..."
	print
	ebuildpath = trees[settings["ROOT"]]["vartree"].dbapi.findname(pkg)
	mysettings = portage.config(clone=settings)
	vardb = trees[mysettings["ROOT"]]["vartree"].dbapi
	debug = mysettings.get("PORTAGE_DEBUG") == "1"
	retval = portage.doebuild(ebuildpath, "config", mysettings["ROOT"],
		mysettings,
		debug=(settings.get("PORTAGE_DEBUG", "") == 1), cleanup=True,
		mydbapi=trees[settings["ROOT"]]["vartree"].dbapi, tree="vartree")
	if retval == os.EX_OK:
		portage.doebuild(ebuildpath, "clean", mysettings["ROOT"],
			mysettings, debug=debug, mydbapi=vardb, tree="vartree")
	print

def action_info(settings, trees, myopts, myfiles):
	print getportageversion(settings["PORTDIR"], settings["ROOT"],
		settings.profile_path, settings["CHOST"],
		trees[settings["ROOT"]]["vartree"].dbapi)
	header_width = 65
	header_title = "System Settings"
	if myfiles:
		print header_width * "="
		print header_title.rjust(int(header_width/2 + len(header_title)/2))
	print header_width * "="
	print "System uname: "+platform.platform(aliased=1)

	lastSync = portage.grabfile(os.path.join(
		settings["PORTDIR"], "metadata", "timestamp.chk"))
	print "Timestamp of tree:",
	if lastSync:
		print lastSync[0]
	else:
		print "Unknown"

	output=commands.getstatusoutput("distcc --version")
	if not output[0]:
		print str(output[1].split("\n",1)[0]),
		if "distcc" in settings.features:
			print "[enabled]"
		else:
			print "[disabled]"

	output=commands.getstatusoutput("ccache -V")
	if not output[0]:
		print str(output[1].split("\n",1)[0]),
		if "ccache" in settings.features:
			print "[enabled]"
		else:
			print "[disabled]"

	myvars  = ["sys-devel/autoconf", "sys-devel/automake", "virtual/os-headers",
	           "sys-devel/binutils", "sys-devel/libtool",  "dev-lang/python"]
	myvars += portage.util.grabfile(settings["PORTDIR"]+"/profiles/info_pkgs")
	myvars  = portage.util.unique_array(myvars)
	myvars.sort()

	for x in myvars:
		if portage.isvalidatom(x):
			pkg_matches = trees["/"]["vartree"].dbapi.match(x)
			pkg_matches = [portage.catpkgsplit(cpv)[1:] for cpv in pkg_matches]
			pkg_matches.sort(portage.pkgcmp)
			pkgs = []
			for pn, ver, rev in pkg_matches:
				if rev != "r0":
					pkgs.append(ver + "-" + rev)
				else:
					pkgs.append(ver)
			if pkgs:
				pkgs = ", ".join(pkgs)
				print "%-20s %s" % (x+":", pkgs)
		else:
			print "%-20s %s" % (x+":", "[NOT VALID]")

	libtool_vers = ",".join(trees["/"]["vartree"].dbapi.match("sys-devel/libtool"))

	if "--verbose" in myopts:
		myvars=settings.keys()
	else:
		myvars = ['GENTOO_MIRRORS', 'CONFIG_PROTECT', 'CONFIG_PROTECT_MASK',
		          'PORTDIR', 'DISTDIR', 'PKGDIR', 'PORTAGE_TMPDIR',
		          'PORTDIR_OVERLAY', 'USE', 'CHOST', 'CFLAGS', 'CXXFLAGS',
		          'ACCEPT_KEYWORDS', 'SYNC', 'FEATURES', 'EMERGE_DEFAULT_OPTS']

		myvars.extend(portage.util.grabfile(settings["PORTDIR"]+"/profiles/info_vars"))

	myvars = portage.util.unique_array(myvars)
	unset_vars = []
	myvars.sort()
	for x in myvars:
		if x in settings:
			if x != "USE":
				print '%s="%s"' % (x, settings[x])
			else:
				use = set(settings["USE"].split())
				use_expand = settings["USE_EXPAND"].split()
				use_expand.sort()
				for varname in use_expand:
					flag_prefix = varname.lower() + "_"
					for f in list(use):
						if f.startswith(flag_prefix):
							use.remove(f)
				use = list(use)
				use.sort()
				print 'USE="%s"' % " ".join(use),
				for varname in use_expand:
					myval = settings.get(varname)
					if myval:
						print '%s="%s"' % (varname, myval),
				print
		else:
			unset_vars.append(x)
	if unset_vars:
		print "Unset:  "+", ".join(unset_vars)
	print

	if "--debug" in myopts:
		for x in dir(portage):
			module = getattr(portage, x)
			if "cvs_id_string" in dir(module):
				print "%s: %s" % (str(x), str(module.cvs_id_string))

	# See if we can find any packages installed matching the strings
	# passed on the command line
	mypkgs = []
	vardb = trees[settings["ROOT"]]["vartree"].dbapi
	portdb = trees[settings["ROOT"]]["porttree"].dbapi
	for x in myfiles:
		mypkgs.extend(vardb.match(x))

	# If some packages were found...
	if mypkgs:
		# Get our global settings (we only print stuff if it varies from
		# the current config)
		mydesiredvars = [ 'CHOST', 'CFLAGS', 'CXXFLAGS' ]
		auxkeys = mydesiredvars + [ "USE", "IUSE"]
		global_vals = {}
		pkgsettings = portage.config(clone=settings)

		for myvar in mydesiredvars:
			global_vals[myvar] = set(settings.get(myvar, "").split())

		# Loop through each package
		# Only print settings if they differ from global settings
		header_title = "Package Settings"
		print header_width * "="
		print header_title.rjust(int(header_width/2 + len(header_title)/2))
		print header_width * "="
		from portage.output import EOutput
		out = EOutput()
		for pkg in mypkgs:
			# Get all package specific variables
			auxvalues = vardb.aux_get(pkg, auxkeys)
			valuesmap = {}
			for i in xrange(len(auxkeys)):
				valuesmap[auxkeys[i]] = set(auxvalues[i].split())
			diff_values = {}
			for myvar in mydesiredvars:
				# If the package variable doesn't match the
				# current global variable, something has changed
				# so set diff_found so we know to print
				if valuesmap[myvar] != global_vals[myvar]:
					diff_values[myvar] = valuesmap[myvar]
			valuesmap["IUSE"] = set(filter_iuse_defaults(valuesmap["IUSE"]))
			valuesmap["USE"] = valuesmap["USE"].intersection(valuesmap["IUSE"])
			pkgsettings.reset()
			# If a matching ebuild is no longer available in the tree, maybe it
			# would make sense to compare against the flags for the best
			# available version with the same slot?
			mydb = None
			if portdb.cpv_exists(pkg):
				mydb = portdb
			pkgsettings.setcpv(pkg, mydb=mydb)
			if valuesmap["IUSE"].intersection(
				pkgsettings["PORTAGE_USE"].split()) != valuesmap["USE"]:
				diff_values["USE"] = valuesmap["USE"]
			# If a difference was found, print the info for
			# this package.
			if diff_values:
				# Print package info
				print "%s was built with the following:" % pkg
				for myvar in mydesiredvars + ["USE"]:
					if myvar in diff_values:
						mylist = list(diff_values[myvar])
						mylist.sort()
						print "%s=\"%s\"" % (myvar, " ".join(mylist))
				print
			print ">>> Attempting to run pkg_info() for '%s'" % pkg
			ebuildpath = vardb.findname(pkg)
			if not ebuildpath or not os.path.exists(ebuildpath):
				out.ewarn("No ebuild found for '%s'" % pkg)
				continue
			portage.doebuild(ebuildpath, "info", pkgsettings["ROOT"],
				pkgsettings, debug=(settings.get("PORTAGE_DEBUG", "") == 1),
				mydbapi=trees[settings["ROOT"]]["vartree"].dbapi,
				tree="vartree")

def action_search(root_config, myopts, myfiles, spinner):
	if not myfiles:
		print "emerge: no search terms provided."
	else:
		searchinstance = search(root_config,
			spinner, "--searchdesc" in myopts,
			"--quiet" not in myopts, "--usepkg" in myopts,
			"--usepkgonly" in myopts)
		for mysearch in myfiles:
			try:
				searchinstance.execute(mysearch)
			except re.error, comment:
				print "\n!!! Regular expression error in \"%s\": %s" % ( mysearch, comment )
				sys.exit(1)
			searchinstance.output()

def action_depclean(settings, trees, ldpath_mtimes,
	myopts, action, myfiles, spinner):
	# Kill packages that aren't explicitly merged or are required as a
	# dependency of another package. World file is explicit.

	# Global depclean or prune operations are not very safe when there are
	# missing dependencies since it's unknown how badly incomplete
	# the dependency graph is, and we might accidentally remove packages
	# that should have been pulled into the graph. On the other hand, it's
	# relatively safe to ignore missing deps when only asked to remove
	# specific packages.
	allow_missing_deps = len(myfiles) > 0

	msg = []
	msg.append("Depclean may break link level dependencies.  Thus, it is\n")
	msg.append("recommended to use a tool such as " + good("`revdep-rebuild`") + " (from\n")
	msg.append("app-portage/gentoolkit) in order to detect such breakage.\n")
	msg.append("\n")
	msg.append("Also study the list of packages to be cleaned for any obvious\n")
	msg.append("mistakes. Packages that are part of the world set will always\n")
	msg.append("be kept.  They can be manually added to this set with\n")
	msg.append(good("`emerge --noreplace <atom>`") + ".  Packages that are listed in\n")
	msg.append("package.provided (see portage(5)) will be removed by\n")
	msg.append("depclean, even if they are part of the world set.\n")
	msg.append("\n")
	msg.append("As a safety measure, depclean will not remove any packages\n")
	msg.append("unless *all* required dependencies have been resolved.  As a\n")
	msg.append("consequence, it is often necessary to run\n")
	msg.append(good("`emerge --update --newuse --deep world`") + " prior to depclean.\n")

	if action == "depclean" and "--quiet" not in myopts and not myfiles:
		portage.writemsg_stdout("\n")
		for x in msg:
			portage.writemsg_stdout(colorize("BAD", "*** WARNING ***  ") + x)

	xterm_titles = "notitles" not in settings.features
	myroot = settings["ROOT"]
	portdb = trees[myroot]["porttree"].dbapi
	pkg_cache = {}
	dep_check_trees = {}
	dep_check_trees[myroot] = {}
	dep_check_trees[myroot]["vartree"] = \
		FakeVartree(trees[myroot]["root_config"], pkg_cache=pkg_cache)
	vardb = dep_check_trees[myroot]["vartree"].dbapi
	# Constrain dependency selection to the installed packages.
	dep_check_trees[myroot]["porttree"] = dep_check_trees[myroot]["vartree"]
	root_config = trees[myroot]["root_config"]
	setconfig = root_config.setconfig
	syslist = setconfig.getSetAtoms("system")
	worldlist = setconfig.getSetAtoms("world")
	args_set = InternalPackageSet()
	fakedb = portage.fakedbapi(settings=settings)
	myvarlist = vardb.cpv_all()

	if not syslist:
		print "\n!!! You have no system list.",
	if not worldlist:
		print "\n!!! You have no world file.",
	if not myvarlist:
		print "\n!!! You have no installed package database (%s)." % portage.VDB_PATH,

	if not (syslist and worldlist and myvarlist):
		print "\n!!! Proceeding "+(syslist and myvarlist and "may" or "will")
		print " break your installation.\n"
		if "--pretend" not in myopts:
			countdown(int(settings["EMERGE_WARNING_DELAY"]), ">>> Depclean")

	if action == "depclean":
		emergelog(xterm_titles, " >>> depclean")
	if myfiles:
		for x in myfiles:
			if not is_valid_package_atom(x):
				portage.writemsg("!!! '%s' is not a valid package atom.\n" % x,
					noiselevel=-1)
				portage.writemsg("!!! Please check ebuild(5) for full details.\n")
				return
			try:
				atom = portage.dep_expand(x, mydb=vardb, settings=settings)
			except ValueError, e:
				print "!!! The short ebuild name \"" + x + "\" is ambiguous.  Please specify"
				print "!!! one of the following fully-qualified ebuild names instead:\n"
				for i in e[0]:
					print "    " + colorize("INFORM", i)
				print
				return
			args_set.add(atom)
		matched_packages = False
		for x in args_set:
			if vardb.match(x):
				matched_packages = True
				break
		if not matched_packages:
			portage.writemsg_stdout(
				">>> No packages selected for removal by %s\n" % action)
			return

	if "--quiet" not in myopts:
		print "\nCalculating dependencies  ",

	runtime = UnmergeDepPriority(runtime=True)
	runtime_post = UnmergeDepPriority(runtime_post=True)
	buildtime = UnmergeDepPriority(buildtime=True)

	priority_map = {
		"RDEPEND": runtime,
		"PDEPEND": runtime_post,
		"DEPEND": buildtime,
	}

	remaining_atoms = []
	if action == "depclean":
		for atom in syslist:
			if vardb.match(atom):
				remaining_atoms.append((atom, 'system', runtime))
		if myfiles:
			# Pull in everything that's installed since we don't want
			# to clean any package if something depends on it.
			remaining_atoms.extend(
				("="+cpv, 'world', runtime) for cpv in vardb.cpv_all())
		else:
			for atom in worldlist:
				if vardb.match(atom):
					remaining_atoms.append((atom, 'world', runtime))
	elif action == "prune":
		for atom in syslist:
			if vardb.match(atom):
				remaining_atoms.append((atom, 'system', runtime))
		# Pull in everything that's installed since we don't want to prune a
		# package if something depends on it.
		remaining_atoms.extend(
			(atom, 'world', runtime) for atom in vardb.cp_all())
		if not myfiles:
			# Try to prune everything that's slotted.
			for cp in vardb.cp_all():
				if len(vardb.cp_list(cp)) > 1:
					args_set.add(cp)

	unresolveable = {}
	aux_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
	metadata_keys = depgraph._mydbapi_keys
	graph = digraph()
	with_bdeps = myopts.get("--with-bdeps", "y") == "y"

	while remaining_atoms:
		atom, parent, priority = remaining_atoms.pop()
		pkgs = vardb.match(atom)
		if not pkgs:
			if priority > UnmergeDepPriority.SOFT:
				unresolveable.setdefault(atom, []).append(parent)
			continue
		if action == "depclean" and parent == "world" and myfiles:
			# Filter out packages given as arguments since the user wants
			# to remove those.
			filtered_pkgs = []
			for pkg in pkgs:
				arg_atom = None
				try:
					arg_atom = args_set.findAtomForPackage(
						pkg_cache[("installed", myroot, pkg, "nomerge")])
				except portage.exception.InvalidDependString, e:
					file_path = os.path.join(
						myroot, portage.VDB_PATH, pkg, "PROVIDE")
					portage.writemsg("\n\nInvalid PROVIDE: %s\n" % str(e),
						noiselevel=-1)
					portage.writemsg("See '%s'\n" % file_path,
						noiselevel=-1)
					del e
				if not arg_atom:
					filtered_pkgs.append(pkg)
			pkgs = filtered_pkgs
		if len(pkgs) > 1:
			# For consistency with the update algorithm, keep the highest
			# visible version and prune any versions that are old or masked.
			for cpv in reversed(pkgs):
				if visible(settings,
					pkg_cache[("installed", myroot, cpv, "nomerge")]):
					pkgs = [cpv]
					break
			if len(pkgs) > 1:
				# They're all masked, so just keep the highest version.
				pkgs = [pkgs[-1]]
		for pkg in pkgs:
			graph.add(pkg, parent, priority=priority)
			if fakedb.cpv_exists(pkg):
				continue
			spinner.update()
			fakedb.cpv_inject(pkg)
			myaux = izip(aux_keys, vardb.aux_get(pkg, aux_keys))
			mydeps = []

			usedef = vardb.aux_get(pkg, ["USE"])[0].split()
			for dep_type, depstr in myaux:

				if not depstr:
					continue

				if not with_bdeps and dep_type == "DEPEND":
					continue

				priority = priority_map[dep_type]
				if "--debug" in myopts:
					print
					print "Parent:   ", pkg
					print "Depstring:", depstr
					print "Priority:", priority

				try:
					portage.dep._dep_check_strict = False
					success, atoms = portage.dep_check(depstr, None, settings,
						myuse=usedef, trees=dep_check_trees, myroot=myroot)
				finally:
					portage.dep._dep_check_strict = True
				if not success:
					show_invalid_depstring_notice(
						("installed", myroot, pkg, "nomerge"),
						depstr, atoms)
					return

				if "--debug" in myopts:
					print "Candidates:", atoms

				for atom in atoms:
					if atom.startswith("!"):
						continue
					remaining_atoms.append((atom, pkg, priority))

	if "--quiet" not in myopts:
		print "\b\b... done!\n"

	if unresolveable and not allow_missing_deps:
		print "Dependencies could not be completely resolved due to"
		print "the following required packages not being installed:"
		print
		for atom in unresolveable:
			print atom, "required by", " ".join(unresolveable[atom])
	if unresolveable and not allow_missing_deps:
		print
		print "Have you forgotten to run " + good("`emerge --update --newuse --deep world`") + " prior to"
		print "%s?  It may be necessary to manually uninstall packages that no longer" % action
		print "exist in the portage tree since it may not be possible to satisfy their"
		print "dependencies.  Also, be aware of the --with-bdeps option that is documented"
		print "in " + good("`man emerge`") + "."
		print
		if action == "prune":
			print "If you would like to ignore dependencies then use %s." % \
				good("--nodeps")
		return

	def show_parents(child_node):
		parent_nodes = graph.parent_nodes(child_node)
		if not parent_nodes:
			# With --prune, the highest version can be pulled in without any
			# real parent since all installed packages are pulled in.  In that
			# case there's nothing to show here.
			return
		parent_nodes.sort()
		msg = []
		msg.append("  %s pulled in by:\n" % str(child_node))
		for parent_node in parent_nodes:
			msg.append("    %s\n" % str(parent_node))
		msg.append("\n")
		portage.writemsg_stdout("".join(msg), noiselevel=-1)

	cleanlist = []
	if action == "depclean":
		if myfiles:
			for pkg in vardb.cpv_all():
				arg_atom = None
				try:
					arg_atom = args_set.findAtomForPackage(
						pkg_cache[("installed", myroot, pkg, "nomerge")])
				except portage.exception.InvalidDependString:
					# this error has already been displayed by now
					continue
				if arg_atom:
					if not fakedb.cpv_exists(pkg):
						cleanlist.append(pkg)
					elif "--verbose" in myopts:
						show_parents(pkg)
		else:
			for pkg in vardb.cpv_all():
				if not fakedb.cpv_exists(pkg):
					cleanlist.append(pkg)
				elif "--verbose" in myopts:
					show_parents(pkg)
	elif action == "prune":
		# Prune really uses all installed instead of world.  It's not a real
		# reverse dependency so don't display it as such.
		if graph.contains("world"):
			graph.remove("world")
		for atom in args_set:
			for pkg in vardb.match(atom):
				if not fakedb.cpv_exists(pkg):
					cleanlist.append(pkg)
				elif "--verbose" in myopts:
					show_parents(pkg)

	if not cleanlist:
		portage.writemsg_stdout(
			">>> No packages selected for removal by %s\n" % action)
		if "--verbose" not in myopts:
			portage.writemsg_stdout(
				">>> To see reverse dependencies, use %s\n" % \
					good("--verbose"))
		if action == "prune":
			portage.writemsg_stdout(
				">>> To ignore dependencies, use %s\n" % \
					good("--nodeps"))

	if len(cleanlist):
		# Use a topological sort to create an unmerge order such that
		# each package is unmerged before it's dependencies. This is
		# necessary to avoid breaking things that may need to run
		# during pkg_prerm or pkg_postrm phases.

		# Create a new graph to account for dependencies between the
		# packages being unmerged.
		graph = digraph()
		clean_set = set(cleanlist)
		del cleanlist[:]
		for node in clean_set:
			graph.add(node, None)
			myaux = izip(aux_keys, vardb.aux_get(node, aux_keys))
			mydeps = []
			usedef = vardb.aux_get(node, ["USE"])[0].split()
			for dep_type, depstr in myaux:
				if not depstr:
					continue
				try:
					portage.dep._dep_check_strict = False
					success, atoms = portage.dep_check(depstr, None, settings,
						myuse=usedef, trees=dep_check_trees, myroot=myroot)
				finally:
					portage.dep._dep_check_strict = True
				if not success:
					show_invalid_depstring_notice(
						("installed", myroot, node, "nomerge"),
						depstr, atoms)
					return

				priority = priority_map[dep_type]
				for atom in atoms:
					if atom.startswith("!"):
						continue
					matches = vardb.match(atom)
					if not matches:
						continue
					for cpv in matches:
						if cpv in clean_set:
							graph.add(cpv, node, priority=priority)

		ordered = True
		if len(graph.order) == len(graph.root_nodes()):
			# If there are no dependencies between packages
			# let unmerge() group them by cat/pn.
			ordered = False
			cleanlist = graph.all_nodes()
		else:
			# Order nodes from lowest to highest overall reference count for
			# optimal root node selection.
			node_refcounts = {}
			for node in graph.order:
				node_refcounts[node] = len(graph.parent_nodes(node))
			def cmp_reference_count(node1, node2):
				return node_refcounts[node1] - node_refcounts[node2]
			graph.order.sort(cmp_reference_count)
	
			ignore_priority_range = [None]
			ignore_priority_range.extend(
				xrange(UnmergeDepPriority.MIN, UnmergeDepPriority.MAX + 1))
			while not graph.empty():
				for ignore_priority in ignore_priority_range:
					nodes = graph.root_nodes(ignore_priority=ignore_priority)
					if nodes:
						break
				if not nodes:
					raise AssertionError("no root nodes")
				if ignore_priority is not None:
					# Some deps have been dropped due to circular dependencies,
					# so only pop one node in order do minimize the number that
					# are dropped.
					del nodes[1:]
				for node in nodes:
					graph.remove(node)
					cleanlist.append(node)

		unmerge(root_config, myopts, "unmerge", cleanlist,
			ldpath_mtimes, ordered=ordered)

	if action == "prune":
		return

	if not cleanlist and "--quiet" in myopts:
		return

	print "Packages installed:   "+str(len(myvarlist))
	print "Packages in world:    "+str(len(worldlist))
	print "Packages in system:   "+str(len(syslist))
	print "Unique package names: "+str(len(myvarlist))
	print "Required packages:    "+str(len(fakedb.cpv_all()))
	if "--pretend" in myopts:
		print "Number to remove:     "+str(len(cleanlist))
	else:
		print "Number removed:       "+str(len(cleanlist))

def resume_depgraph(settings, trees, mtimedb, myopts, myparams, spinner,
	skip_masked=False, skip_unsatisfied=False):
	"""
	Construct a depgraph for the given resume list. This will raise
	PackageNotFound or depgraph.UnsatisfiedResumeDep when necessary.
	@rtype: tuple
	@returns: (success, depgraph, dropped_tasks)
	"""
	mergelist = mtimedb["resume"]["mergelist"]
	dropped_tasks = set()
	while True:
		mydepgraph = depgraph(settings, trees,
			myopts, myparams, spinner)
		try:
			success = mydepgraph.loadResumeCommand(mtimedb["resume"],
				skip_masked=skip_masked)
		except depgraph.UnsatisfiedResumeDep, e:
			if not skip_unsatisfied:
				raise

			graph = mydepgraph.digraph
			unsatisfied_parents = dict((dep.parent, dep.parent) \
				for dep in e.value)
			traversed_nodes = set()
			unsatisfied_stack = list(unsatisfied_parents)
			while unsatisfied_stack:
				pkg = unsatisfied_stack.pop()
				if pkg in traversed_nodes:
					continue
				traversed_nodes.add(pkg)

				# If this package was pulled in by a parent
				# package scheduled for merge, removing this
				# package may cause the the parent package's
				# dependency to become unsatisfied.
				for parent_node in graph.parent_nodes(pkg):
					if not isinstance(parent_node, Package) \
						or parent_node.operation != "merge":
						continue
					unsatisfied = \
						graph.child_nodes(parent_node,
						ignore_priority=DepPriority.SOFT)
					if pkg in unsatisfied:
						unsatisfied_parents[parent_node] = parent_node
						unsatisfied_stack.append(parent_node)

			pruned_mergelist = [x for x in mergelist \
				if isinstance(x, list) and \
				tuple(x) not in unsatisfied_parents]

			# It shouldn't happen, but if the size of mergelist
			# does not decrease for some reason then the loop
			# will be infinite. Therefore, if that case ever
			# occurs for some reason, raise the exception to
			# break out of the loop.
			if not pruned_mergelist or \
				len(pruned_mergelist) == len(mergelist):
				raise
			mergelist[:] = pruned_mergelist
			dropped_tasks.update(unsatisfied_parents)
			del e, graph, traversed_nodes, \
				unsatisfied_parents, unsatisfied_stack
			continue
		else:
			break
	return (success, mydepgraph, dropped_tasks)

def action_build(settings, trees, mtimedb,
	myopts, myaction, myfiles, spinner):

	# validate the state of the resume data
	# so that we can make assumptions later.
	for k in ("resume", "resume_backup"):
		if k not in mtimedb:
			continue
		resume_data = mtimedb[k]
		if not isinstance(resume_data, dict):
			del mtimedb[k]
			continue
		mergelist = resume_data.get("mergelist")
		if not isinstance(mergelist, list):
			del mtimedb[k]
			continue
		resume_opts = resume_data.get("myopts")
		if not isinstance(resume_opts, (dict, list)):
			del mtimedb[k]
			continue
		favorites = resume_data.get("favorites")
		if not isinstance(favorites, list):
			del mtimedb[k]
			continue

	resume = False
	if "--resume" in myopts and \
		("resume" in mtimedb or
		"resume_backup" in mtimedb):
		resume = True
		if "resume" not in mtimedb:
			mtimedb["resume"] = mtimedb["resume_backup"]
			del mtimedb["resume_backup"]
			mtimedb.commit()
		# "myopts" is a list for backward compatibility.
		resume_opts = mtimedb["resume"].get("myopts", [])
		if isinstance(resume_opts, list):
			resume_opts = dict((k,True) for k in resume_opts)
		for opt in ("--skipfirst", "--ask", "--tree"):
			resume_opts.pop(opt, None)
		myopts.update(resume_opts)
		# Adjust config according to options of the command being resumed.
		for myroot in trees:
			mysettings =  trees[myroot]["vartree"].settings
			mysettings.unlock()
			adjust_config(myopts, mysettings)
			mysettings.lock()
			del myroot, mysettings

	ldpath_mtimes = mtimedb["ldpath"]
	favorites=[]
	merge_count = 0
	buildpkgonly = "--buildpkgonly" in myopts
	pretend = "--pretend" in myopts
	fetchonly = "--fetchonly" in myopts or "--fetch-all-uri" in myopts
	ask = "--ask" in myopts
	nodeps = "--nodeps" in myopts
	oneshot = "--oneshot" in myopts or "--onlydeps" in myopts
	tree = "--tree" in myopts
	if nodeps and tree:
		tree = False
		del myopts["--tree"]
		portage.writemsg(colorize("WARN", " * ") + \
			"--tree is broken with --nodeps. Disabling...\n")
	debug = "--debug" in myopts
	verbose = "--verbose" in myopts
	quiet = "--quiet" in myopts
	if pretend or fetchonly:
		# make the mtimedb readonly
		mtimedb.filename = None
	if "--digest" in myopts:
		msg = "The --digest option can prevent corruption from being" + \
			" noticed. The `repoman manifest` command is the preferred" + \
			" way to generate manifests and it is capable of doing an" + \
			" entire repository or category at once."
		prefix = bad(" * ")
		writemsg(prefix + "\n")
		from textwrap import wrap
		for line in wrap(msg, 72):
			writemsg("%s%s\n" % (prefix, line))
		writemsg(prefix + "\n")

	if "--quiet" not in myopts and \
		("--pretend" in myopts or "--ask" in myopts or \
		"--tree" in myopts or "--verbose" in myopts):
		action = ""
		if "--fetchonly" in myopts or "--fetch-all-uri" in myopts:
			action = "fetched"
		elif "--buildpkgonly" in myopts:
			action = "built"
		else:
			action = "merged"
		if "--tree" in myopts and action != "fetched": # Tree doesn't work with fetching
			print
			print darkgreen("These are the packages that would be %s, in reverse order:") % action
			print
		else:
			print
			print darkgreen("These are the packages that would be %s, in order:") % action
			print

	show_spinner = "--quiet" not in myopts and "--nodeps" not in myopts
	if not show_spinner:
		spinner.update = spinner.update_quiet

	if resume:
		favorites = mtimedb["resume"].get("favorites")
		if not isinstance(favorites, list):
			favorites = []

		if show_spinner:
			print "Calculating dependencies  ",
		myparams = create_depgraph_params(myopts, myaction)

		resume_data = mtimedb["resume"]
		mergelist = resume_data["mergelist"]
		if mergelist and "--skipfirst" in myopts:
			for i, task in enumerate(mergelist):
				if isinstance(task, list) and \
					task and task[-1] == "merge":
					del mergelist[i]
					break

		skip_masked      = "--skipfirst" in myopts
		skip_unsatisfied = "--skipfirst" in myopts
		success = False
		mydepgraph = None
		try:
			success, mydepgraph, dropped_tasks = resume_depgraph(
				settings, trees, mtimedb, myopts, myparams, spinner,
				skip_masked=skip_masked, skip_unsatisfied=skip_unsatisfied)
		except (portage.exception.PackageNotFound,
			depgraph.UnsatisfiedResumeDep), e:
			if isinstance(e, depgraph.UnsatisfiedResumeDep):
				mydepgraph = e.depgraph
			if show_spinner:
				print
			from textwrap import wrap
			from portage.output import EOutput
			out = EOutput()

			resume_data = mtimedb["resume"]
			mergelist = resume_data.get("mergelist")
			if not isinstance(mergelist, list):
				mergelist = []
			if mergelist and debug or (verbose and not quiet):
				out.eerror("Invalid resume list:")
				out.eerror("")
				indent = "  "
				for task in mergelist:
					if isinstance(task, list):
						out.eerror(indent + str(tuple(task)))
				out.eerror("")

			if isinstance(e, depgraph.UnsatisfiedResumeDep):
				out.eerror("One or packages are either masked or " + \
					"have missing dependencies:")
				out.eerror("")
				indent = "  "
				for dep in e.value:
					if dep.atom is None:
						out.eerror(indent + "Masked package:")
						out.eerror(2 * indent + str(dep.parent))
						out.eerror("")
					else:
						out.eerror(indent + str(dep.atom) + " pulled in by:")
						out.eerror(2 * indent + str(dep.parent))
						out.eerror("")
				msg = "The resume list contains packages " + \
					"that are either masked or have " + \
					"unsatisfied dependencies. " + \
					"Please restart/continue " + \
					"the operation manually, or use --skipfirst " + \
					"to skip the first package in the list and " + \
					"any other packages that may be " + \
					"masked or have missing dependencies."
				for line in wrap(msg, 72):
					out.eerror(line)
			elif isinstance(e, portage.exception.PackageNotFound):
				out.eerror("An expected package is " + \
					"not available: %s" % str(e))
				out.eerror("")
				msg = "The resume list contains one or more " + \
					"packages that are no longer " + \
					"available. Please restart/continue " + \
					"the operation manually."
				for line in wrap(msg, 72):
					out.eerror(line)
		else:
			if show_spinner:
				print "\b\b... done!"

		if success:
			if dropped_tasks:
				portage.writemsg("!!! One or more packages have been " + \
					"dropped due to\n" + \
					"!!! masking or unsatisfied dependencies:\n\n",
					noiselevel=-1)
				for task in dropped_tasks:
					portage.writemsg("  " + str(task) + "\n", noiselevel=-1)
				portage.writemsg("\n", noiselevel=-1)
			del dropped_tasks
		else:
			if mydepgraph is not None:
				mydepgraph.display_problems()
			if not (ask or pretend):
				# delete the current list and also the backup
				# since it's probably stale too.
				for k in ("resume", "resume_backup"):
					mtimedb.pop(k, None)
				mtimedb.commit()

			return 1
	else:
		if ("--resume" in myopts):
			print darkgreen("emerge: It seems we have nothing to resume...")
			return os.EX_OK

		myparams = create_depgraph_params(myopts, myaction)
		if "--quiet" not in myopts and "--nodeps" not in myopts:
			print "Calculating dependencies  ",
			sys.stdout.flush()
		mydepgraph = depgraph(settings, trees, myopts, myparams, spinner)
		try:
			retval, favorites = mydepgraph.select_files(myfiles)
		except portage.exception.PackageNotFound, e:
			portage.writemsg("\n!!! %s\n" % str(e), noiselevel=-1)
			return 1
		if show_spinner:
			print "\b\b... done!"
		if not retval:
			mydepgraph.display_problems()
			return 1

	if "--pretend" not in myopts and \
		("--ask" in myopts or "--tree" in myopts or \
		"--verbose" in myopts) and \
		not ("--quiet" in myopts and "--ask" not in myopts):
		if "--resume" in myopts:
			mymergelist = mydepgraph.altlist()
			if len(mymergelist) == 0:
				print colorize("INFORM", "emerge: It seems we have nothing to resume...")
				return os.EX_OK
			favorites = mtimedb["resume"]["favorites"]
			retval = mydepgraph.display(
				mydepgraph.altlist(reversed=tree),
				favorites=favorites)
			mydepgraph.display_problems()
			if retval != os.EX_OK:
				return retval
			prompt="Would you like to resume merging these packages?"
		else:
			retval = mydepgraph.display(
				mydepgraph.altlist(reversed=("--tree" in myopts)),
				favorites=favorites)
			mydepgraph.display_problems()
			if retval != os.EX_OK:
				return retval
			mergecount=0
			for x in mydepgraph.altlist():
				if isinstance(x, Package) and x.operation == "merge":
					mergecount += 1

			if mergecount==0:
				sets = trees[settings["ROOT"]]["root_config"].sets
				world_candidates = None
				if "--noreplace" in myopts and \
					not oneshot and favorites:
					# Sets that are not world candidates are filtered
					# out here since the favorites list needs to be
					# complete for depgraph.loadResumeCommand() to
					# operate correctly.
					world_candidates = [x for x in favorites \
						if not (x.startswith(SETPREFIX) and \
						not sets[x[1:]].world_candidate)]
				if "--noreplace" in myopts and \
					not oneshot and world_candidates:
					print
					for x in world_candidates:
						print " %s %s" % (good("*"), x)
					prompt="Would you like to add these packages to your world favorites?"
				elif settings["AUTOCLEAN"] and "yes"==settings["AUTOCLEAN"]:
					prompt="Nothing to merge; would you like to auto-clean packages?"
				else:
					print
					print "Nothing to merge; quitting."
					print
					return os.EX_OK
			elif "--fetchonly" in myopts or "--fetch-all-uri" in myopts:
				prompt="Would you like to fetch the source files for these packages?"
			else:
				prompt="Would you like to merge these packages?"
		print
		if "--ask" in myopts and userquery(prompt) == "No":
			print
			print "Quitting."
			print
			return os.EX_OK
		# Don't ask again (e.g. when auto-cleaning packages after merge)
		myopts.pop("--ask", None)

	if ("--pretend" in myopts) and not ("--fetchonly" in myopts or "--fetch-all-uri" in myopts):
		if ("--resume" in myopts):
			mymergelist = mydepgraph.altlist()
			if len(mymergelist) == 0:
				print colorize("INFORM", "emerge: It seems we have nothing to resume...")
				return os.EX_OK
			favorites = mtimedb["resume"]["favorites"]
			retval = mydepgraph.display(
				mydepgraph.altlist(reversed=tree),
				favorites=favorites)
			mydepgraph.display_problems()
			if retval != os.EX_OK:
				return retval
		else:
			retval = mydepgraph.display(
				mydepgraph.altlist(reversed=("--tree" in myopts)),
				favorites=favorites)
			mydepgraph.display_problems()
			if retval != os.EX_OK:
				return retval
			if "--buildpkgonly" in myopts:
				graph_copy = mydepgraph.digraph.clone()
				for node in list(graph_copy.order):
					if not isinstance(node, Package):
						graph_copy.remove(node)
				if not graph_copy.hasallzeros(ignore_priority=DepPriority.MEDIUM):
					print "\n!!! --buildpkgonly requires all dependencies to be merged."
					print "!!! You have to merge the dependencies before you can build this package.\n"
					return 1
	else:
		if "--buildpkgonly" in myopts:
			graph_copy = mydepgraph.digraph.clone()
			for node in list(graph_copy.order):
				if not isinstance(node, Package):
					graph_copy.remove(node)
			if not graph_copy.hasallzeros(ignore_priority=DepPriority.MEDIUM):
				print "\n!!! --buildpkgonly requires all dependencies to be merged."
				print "!!! Cannot merge requested packages. Merge deps and try again.\n"
				return 1

		if ("--resume" in myopts):
			favorites=mtimedb["resume"]["favorites"]
			if "PORTAGE_PARALLEL_FETCHONLY" in settings:
				""" parallel-fetch uses --resume --fetchonly and we don't want
				it to write the mtimedb"""
				mtimedb.filename = None
				time.sleep(3) # allow the parent to have first fetch
			mymergelist = mydepgraph.altlist()
			mydepgraph.break_refs(mymergelist)
			mydepgraph.break_refs(mydepgraph.digraph.order)
			mergetask = Scheduler(settings, trees, mtimedb, myopts,
				spinner, mymergelist, favorites, mydepgraph.digraph)
			del mydepgraph
			clear_caches(trees)

			retval = mergetask.merge()
			merge_count = mergetask.curval
		else:
			if "resume" in mtimedb and \
			"mergelist" in mtimedb["resume"] and \
			len(mtimedb["resume"]["mergelist"]) > 1:
				mtimedb["resume_backup"] = mtimedb["resume"]
				del mtimedb["resume"]
				mtimedb.commit()
			mtimedb["resume"]={}
			# XXX: Stored as a list for backward compatibility.
			mtimedb["resume"]["myopts"] = \
				[k for k in myopts if myopts[k] is True]

			# Convert Atom instances to plain str since the mtimedb loader
			# sets unpickler.find_global = None which causes unpickler.load()
			# to raise the following exception:
			#
			# cPickle.UnpicklingError: Global and instance pickles are not supported.
			#
			# TODO: Maybe stop setting find_global = None, or find some other
			# way to avoid accidental triggering of the above UnpicklingError.
			mtimedb["resume"]["favorites"] = [str(x) for x in favorites]

			if ("--digest" in myopts) and not ("--fetchonly" in myopts or "--fetch-all-uri" in myopts):
				for pkgline in mydepgraph.altlist():
					if pkgline[0]=="ebuild" and pkgline[3]=="merge":
						y = trees[pkgline[1]]["porttree"].dbapi.findname(pkgline[2])
						tmpsettings = portage.config(clone=settings)
						edebug = 0
						if settings.get("PORTAGE_DEBUG", "") == "1":
							edebug = 1
						retval = portage.doebuild(
							y, "digest", settings["ROOT"], tmpsettings, edebug,
							("--pretend" in myopts),
							mydbapi=trees[pkgline[1]]["porttree"].dbapi,
							tree="porttree")

			pkglist = mydepgraph.altlist()
			mydepgraph.saveNomergeFavorites()
			mydepgraph.break_refs(pkglist)
			mydepgraph.break_refs(mydepgraph.digraph.order)
			mergetask = Scheduler(settings, trees, mtimedb, myopts,
				spinner, pkglist, favorites, mydepgraph.digraph)
			del mydepgraph
			clear_caches(trees)

			retval = mergetask.merge()
			merge_count = mergetask.curval

		if retval == os.EX_OK and not (buildpkgonly or fetchonly or pretend):
			if "yes" == settings.get("AUTOCLEAN"):
				portage.writemsg_stdout(">>> Auto-cleaning packages...\n")
				unmerge(trees[settings["ROOT"]]["root_config"],
					myopts, "clean", [],
					ldpath_mtimes, autoclean=1)
			else:
				portage.writemsg_stdout(colorize("WARN", "WARNING:")
					+ " AUTOCLEAN is disabled.  This can cause serious"
					+ " problems due to overlapping packages.\n")
			trees[settings["ROOT"]]["vartree"].dbapi.plib_registry.pruneNonExisting()

		if merge_count and not (buildpkgonly or fetchonly or pretend):
			post_emerge(trees, mtimedb, retval)
		return retval

def multiple_actions(action1, action2):
	sys.stderr.write("\n!!! Multiple actions requested... Please choose one only.\n")
	sys.stderr.write("!!! '%s' or '%s'\n\n" % (action1, action2))
	sys.exit(1)

def parse_opts(tmpcmdline, silent=False):
	myaction=None
	myopts = {}
	myfiles=[]

	global actions, options, shortmapping

	longopt_aliases = {"--cols":"--columns", "--skip-first":"--skipfirst"}
	argument_options = {
		"--config-root": {
			"help":"specify the location for portage configuration files",
			"action":"store"
		},
		"--color": {
			"help":"enable or disable color output",
			"type":"choice",
			"choices":("y", "n")
		},
		"--with-bdeps": {
			"help":"include unnecessary build time dependencies",
			"type":"choice",
			"choices":("y", "n")
		},
		"--reinstall": {
			"help":"specify conditions to trigger package reinstallation",
			"type":"choice",
			"choices":["changed-use"]
		}
	}

	from optparse import OptionParser
	parser = OptionParser()
	if parser.has_option("--help"):
		parser.remove_option("--help")

	for action_opt in actions:
		parser.add_option("--" + action_opt, action="store_true",
			dest=action_opt.replace("-", "_"), default=False)
	for myopt in options:
		parser.add_option(myopt, action="store_true",
			dest=myopt.lstrip("--").replace("-", "_"), default=False)
	for shortopt, longopt in shortmapping.iteritems():
		parser.add_option("-" + shortopt, action="store_true",
			dest=longopt.lstrip("--").replace("-", "_"), default=False)
	for myalias, myopt in longopt_aliases.iteritems():
		parser.add_option(myalias, action="store_true",
			dest=myopt.lstrip("--").replace("-", "_"), default=False)

	for myopt, kwargs in argument_options.iteritems():
		parser.add_option(myopt,
			dest=myopt.lstrip("--").replace("-", "_"), **kwargs)

	myoptions, myargs = parser.parse_args(args=tmpcmdline)

	for myopt in options:
		v = getattr(myoptions, myopt.lstrip("--").replace("-", "_"))
		if v:
			myopts[myopt] = True

	for myopt in argument_options:
		v = getattr(myoptions, myopt.lstrip("--").replace("-", "_"), None)
		if v is not None:
			myopts[myopt] = v

	for action_opt in actions:
		v = getattr(myoptions, action_opt.replace("-", "_"))
		if v:
			if myaction:
				multiple_actions(myaction, action_opt)
				sys.exit(1)
			myaction = action_opt

	for x in myargs:
		if x in actions and myaction != "search":
			if not silent:
				print red("*** Deprecated use of action '%s', use '--%s' instead" % (x,x))
			# special case "search" so people can search for action terms, e.g. emerge -s sync
			if myaction:
				multiple_actions(myaction, x)
				sys.exit(1)
			myaction = x
		else:
			myfiles.append(x)

	if "--nocolor" in myopts:
		if not silent:
			sys.stderr.write("*** Deprecated use of '--nocolor', " + \
				"use '--color=n' instead.\n")
		del myopts["--nocolor"]
		myopts["--color"] = "n"

	return myaction, myopts, myfiles

def validate_ebuild_environment(trees):
	for myroot in trees:
		settings = trees[myroot]["vartree"].settings
		settings.validate()

def clear_caches(trees):
	for d in trees.itervalues():
		d["porttree"].dbapi.melt()
		d["porttree"].dbapi._aux_cache.clear()
		d["bintree"].dbapi._aux_cache.clear()
		d["bintree"].dbapi._clear_cache()
	portage.dircache.clear()
	gc.collect()

def load_emerge_config(trees=None):
	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		v = os.environ.get(envvar, None)
		if v and v.strip():
			kwargs[k] = v
	trees = portage.create_trees(trees=trees, **kwargs)

	for root, root_trees in trees.iteritems():
		settings = root_trees["vartree"].settings
		setconfig = load_default_config(settings, root_trees)
		root_trees["root_config"] = RootConfig(settings, root_trees, setconfig)

	settings = trees["/"]["vartree"].settings

	for myroot in trees:
		if myroot != "/":
			settings = trees[myroot]["vartree"].settings
			break

	mtimedbfile = os.path.join("/", portage.CACHE_PATH.lstrip(os.path.sep), "mtimedb")
	mtimedb = portage.MtimeDB(mtimedbfile)
	
	return settings, trees, mtimedb

def adjust_config(myopts, settings):
	"""Make emerge specific adjustments to the config."""

	# To enhance usability, make some vars case insensitive by forcing them to
	# lower case.
	for myvar in ("AUTOCLEAN", "NOCOLOR"):
		if myvar in settings:
			settings[myvar] = settings[myvar].lower()
			settings.backup_changes(myvar)
	del myvar

	# Kill noauto as it will break merges otherwise.
	if "noauto" in settings.features:
		while "noauto" in settings.features:
			settings.features.remove("noauto")
		settings["FEATURES"] = " ".join(settings.features)
		settings.backup_changes("FEATURES")

	CLEAN_DELAY = 5
	try:
		CLEAN_DELAY = int(settings.get("CLEAN_DELAY", str(CLEAN_DELAY)))
	except ValueError, e:
		portage.writemsg("!!! %s\n" % str(e), noiselevel=-1)
		portage.writemsg("!!! Unable to parse integer: CLEAN_DELAY='%s'\n" % \
			settings["CLEAN_DELAY"], noiselevel=-1)
	settings["CLEAN_DELAY"] = str(CLEAN_DELAY)
	settings.backup_changes("CLEAN_DELAY")

	EMERGE_WARNING_DELAY = 10
	try:
		EMERGE_WARNING_DELAY = int(settings.get(
			"EMERGE_WARNING_DELAY", str(EMERGE_WARNING_DELAY)))
	except ValueError, e:
		portage.writemsg("!!! %s\n" % str(e), noiselevel=-1)
		portage.writemsg("!!! Unable to parse integer: EMERGE_WARNING_DELAY='%s'\n" % \
			settings["EMERGE_WARNING_DELAY"], noiselevel=-1)
	settings["EMERGE_WARNING_DELAY"] = str(EMERGE_WARNING_DELAY)
	settings.backup_changes("EMERGE_WARNING_DELAY")

	if "--quiet" in myopts:
		settings["PORTAGE_QUIET"]="1"
		settings.backup_changes("PORTAGE_QUIET")

	# Set so that configs will be merged regardless of remembered status
	if ("--noconfmem" in myopts):
		settings["NOCONFMEM"]="1"
		settings.backup_changes("NOCONFMEM")

	# Set various debug markers... They should be merged somehow.
	PORTAGE_DEBUG = 0
	try:
		PORTAGE_DEBUG = int(settings.get("PORTAGE_DEBUG", str(PORTAGE_DEBUG)))
		if PORTAGE_DEBUG not in (0, 1):
			portage.writemsg("!!! Invalid value: PORTAGE_DEBUG='%i'\n" % \
				PORTAGE_DEBUG, noiselevel=-1)
			portage.writemsg("!!! PORTAGE_DEBUG must be either 0 or 1\n",
				noiselevel=-1)
			PORTAGE_DEBUG = 0
	except ValueError, e:
		portage.writemsg("!!! %s\n" % str(e), noiselevel=-1)
		portage.writemsg("!!! Unable to parse integer: PORTAGE_DEBUG='%s'\n" %\
			settings["PORTAGE_DEBUG"], noiselevel=-1)
		del e
	if "--debug" in myopts:
		PORTAGE_DEBUG = 1
	settings["PORTAGE_DEBUG"] = str(PORTAGE_DEBUG)
	settings.backup_changes("PORTAGE_DEBUG")

	if settings.get("NOCOLOR") not in ("yes","true"):
		portage.output.havecolor = 1

	"""The explicit --color < y | n > option overrides the NOCOLOR environment
	variable and stdout auto-detection."""
	if "--color" in myopts:
		if "y" == myopts["--color"]:
			portage.output.havecolor = 1
			settings["NOCOLOR"] = "false"
		else:
			portage.output.havecolor = 0
			settings["NOCOLOR"] = "true"
		settings.backup_changes("NOCOLOR")
	elif not sys.stdout.isatty() and settings.get("NOCOLOR") != "no":
		portage.output.havecolor = 0
		settings["NOCOLOR"] = "true"
		settings.backup_changes("NOCOLOR")

def emerge_main():
	global portage	# NFC why this is necessary now - genone
	# Disable color until we're sure that it should be enabled (after
	# EMERGE_DEFAULT_OPTS has been parsed).
	portage.output.havecolor = 0
	# This first pass is just for options that need to be known as early as
	# possible, such as --config-root.  They will be parsed again later,
	# together with EMERGE_DEFAULT_OPTS (which may vary depending on the
	# the value of --config-root).
	myaction, myopts, myfiles = parse_opts(sys.argv[1:], silent=True)
	if "--debug" in myopts:
		os.environ["PORTAGE_DEBUG"] = "1"
	if "--config-root" in myopts:
		os.environ["PORTAGE_CONFIGROOT"] = myopts["--config-root"]

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(022)
	settings, trees, mtimedb = load_emerge_config()
	portdb = trees[settings["ROOT"]]["porttree"].dbapi

	try:
		os.nice(int(settings.get("PORTAGE_NICENESS", "0")))
	except (OSError, ValueError), e:
		portage.writemsg("!!! Failed to change nice value to '%s'\n" % \
			settings["PORTAGE_NICENESS"])
		portage.writemsg("!!! %s\n" % str(e))
		del e

	if portage._global_updates(trees, mtimedb["updates"]):
		mtimedb.commit()
		# Reload the whole config from scratch.
		settings, trees, mtimedb = load_emerge_config(trees=trees)
		portdb = trees[settings["ROOT"]]["porttree"].dbapi

	xterm_titles = "notitles" not in settings.features

	tmpcmdline = []
	if "--ignore-default-opts" not in myopts:
		tmpcmdline.extend(settings["EMERGE_DEFAULT_OPTS"].split())
	tmpcmdline.extend(sys.argv[1:])
	myaction, myopts, myfiles = parse_opts(tmpcmdline)

	if "--digest" in myopts:
		os.environ["FEATURES"] = os.environ.get("FEATURES","") + " digest"
		# Reload the whole config from scratch so that the portdbapi internal
		# config is updated with new FEATURES.
		settings, trees, mtimedb = load_emerge_config(trees=trees)
		portdb = trees[settings["ROOT"]]["porttree"].dbapi

	for myroot in trees:
		mysettings =  trees[myroot]["vartree"].settings
		mysettings.unlock()
		adjust_config(myopts, mysettings)
		mysettings.lock()
		del myroot, mysettings

	spinner = stdout_spinner()
	if "candy" in settings.features:
		spinner.update = spinner.update_scroll

	if "--quiet" not in myopts:
		portage.deprecated_profile_check()
		for root in trees:
			if "porttree" in trees[root]:
				db = trees[root]["porttree"].dbapi
				paths = (db.mysettings["PORTDIR"]+" "+db.mysettings["PORTDIR_OVERLAY"]).split()
				paths = [os.path.realpath(p) for p in paths]
				repos = db.getRepositories()
				for r in repos:
					p = db.getRepositoryPath(r)
					try:
						paths.remove(p)
					except ValueError:
						pass
				for p in paths:
					writemsg("WARNING: repository at %s is missing a repo_name entry\n" % p)
					

	eclasses_overridden = {}
	for mytrees in trees.itervalues():
		mydb = mytrees["porttree"].dbapi
		# Freeze the portdbapi for performance (memoize all xmatch results).
		mydb.freeze()
		eclasses_overridden.update(mydb.eclassdb._master_eclasses_overridden)
	del mytrees, mydb

	if eclasses_overridden and \
		settings.get("PORTAGE_ECLASS_WARNING_ENABLE") != "0":
		prefix = bad(" * ")
		if len(eclasses_overridden) == 1:
			writemsg(prefix + "Overlay eclass overrides " + \
				"eclass from PORTDIR:\n", noiselevel=-1)
		else:
			writemsg(prefix + "Overlay eclasses override " + \
				"eclasses from PORTDIR:\n", noiselevel=-1)
		writemsg(prefix + "\n", noiselevel=-1)
		for eclass_name in sorted(eclasses_overridden):
			writemsg(prefix + "  '%s/%s.eclass'\n" % \
				(eclasses_overridden[eclass_name], eclass_name),
				noiselevel=-1)
		writemsg(prefix + "\n", noiselevel=-1)
		msg = "It is best to avoid overridding eclasses from PORTDIR " + \
		"because it will trigger invalidation of cached ebuild metadata " + \
		"that is distributed with the portage tree. If you must " + \
		"override eclasses from PORTDIR then you are advised to add " + \
		"FEATURES=\"metadata-transfer\" to /etc/make.conf and to run " + \
		"`emerge --regen` after each time that you run `emerge --sync`. " + \
		"Set PORTAGE_ECLASS_WARNING_ENABLE=\"0\" in /etc/make.conf if " + \
		"you would like to disable this warning."
		from textwrap import wrap
		for line in wrap(msg, 72):
			writemsg("%s%s\n" % (prefix, line), noiselevel=-1)

	if "moo" in myfiles:
		print """

  Larry loves Gentoo (""" + platform.system() + """)

 _______________________
< Have you mooed today? >
 -----------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\ 
                ||----w |
                ||     ||

"""

	for x in myfiles:
		ext = os.path.splitext(x)[1]
		if (ext == ".ebuild" or ext == ".tbz2") and os.path.exists(os.path.abspath(x)):
			print colorize("BAD", "\n*** emerging by path is broken and may not always work!!!\n")
			break

	# only expand sets for actions taking package arguments
	oldargs = myfiles[:]
	if myaction in ("clean", "config", "depclean", "info", "prune", "unmerge", None):
		root_config = trees[settings["ROOT"]]["root_config"]
		setconfig = root_config.setconfig
		# display errors that occured while loading the SetConfig instance
		for e in setconfig.errors:
			print colorize("BAD", "Error during set creation: %s" % e)
		
		sets = setconfig.getSets()
		# emerge relies on the existance of sets with names "world" and "system"
		required_sets = ("world", "system")
		for s in required_sets:
			if s not in sets:
				msg = ["emerge: incomplete set configuration, " + \
					"no \"%s\" set defined" % s]
				msg.append("        sets defined: %s" % ", ".join(sets))
				for line in msg:
					sys.stderr.write(line + "\n")
				return 1
		unmerge_actions = ("unmerge", "prune", "clean", "depclean")
		
		# In order to know exactly which atoms/sets should be added to the
		# world file, the depgraph performs set expansion later. It will get
		# confused about where the atoms came from if it's not allowed to
		# expand them itself.
		do_not_expand = (None, )
		newargs = []
		for a in myfiles:
			if a in ("system", "world"):
				newargs.append(SETPREFIX+a)
			else:
				newargs.append(a)
		myfiles = newargs
		del newargs
		newargs = []
		for a in myfiles:
			if a.startswith(SETPREFIX):
				s = a[len(SETPREFIX):]
				if s not in sets:
					print "emerge: there are no sets to satisfy %s." % \
						colorize("INFORM", s)
					return 1
				setconfig.active.append(s)
				if myaction in unmerge_actions and \
						not sets[s].supportsOperation("unmerge"):
					sys.stderr.write("emerge: the given set '%s' does " % s + \
						"not support unmerge operations\n")
					return 1
				if not setconfig.getSetAtoms(s):
					print "emerge: '%s' is an empty set" % s
				elif myaction not in do_not_expand:
					newargs.extend(setconfig.getSetAtoms(s))
				else:
					newargs.append(SETPREFIX+s)
				for e in sets[s].errors:
					print e
			else:
				newargs.append(a)
		myfiles = newargs
		del newargs
		# Need to handle empty sets specially, otherwise emerge will react 
		# with the help message for empty argument lists
		if oldargs and not myfiles:
			print "emerge: no targets left after set expansion"
			return 0

	if ("--tree" in myopts) and ("--columns" in myopts):
		print "emerge: can't specify both of \"--tree\" and \"--columns\"."
		return 1

	if ("--quiet" in myopts):
		spinner.update = spinner.update_quiet
		portage.util.noiselimit = -1

	# Always create packages if FEATURES=buildpkg
	# Imply --buildpkg if --buildpkgonly
	if ("buildpkg" in settings.features) or ("--buildpkgonly" in myopts):
		if "--buildpkg" not in myopts:
			myopts["--buildpkg"] = True

	# Also allow -S to invoke search action (-sS)
	if ("--searchdesc" in myopts):
		if myaction and myaction != "search":
			myfiles.append(myaction)
		if "--search" not in myopts:
			myopts["--search"] = True
		myaction = "search"

	# Always try and fetch binary packages if FEATURES=getbinpkg
	if ("getbinpkg" in settings.features):
		myopts["--getbinpkg"] = True

	if "--buildpkgonly" in myopts:
		# --buildpkgonly will not merge anything, so
		# it cancels all binary package options.
		for opt in ("--getbinpkg", "--getbinpkgonly",
			"--usepkg", "--usepkgonly"):
			myopts.pop(opt, None)

	if "--skipfirst" in myopts and "--resume" not in myopts:
		myopts["--resume"] = True

	if ("--getbinpkgonly" in myopts) and not ("--usepkgonly" in myopts):
		myopts["--usepkgonly"] = True

	if ("--getbinpkgonly" in myopts) and not ("--getbinpkg" in myopts):
		myopts["--getbinpkg"] = True

	if ("--getbinpkg" in myopts) and not ("--usepkg" in myopts):
		myopts["--usepkg"] = True

	# Also allow -K to apply --usepkg/-k
	if ("--usepkgonly" in myopts) and not ("--usepkg" in myopts):
		myopts["--usepkg"] = True

	# Allow -p to remove --ask
	if ("--pretend" in myopts) and ("--ask" in myopts):
		print ">>> --pretend disables --ask... removing --ask from options."
		del myopts["--ask"]

	# forbid --ask when not in a terminal
	# note: this breaks `emerge --ask | tee logfile`, but that doesn't work anyway.
	if ("--ask" in myopts) and (not sys.stdin.isatty()):
		portage.writemsg("!!! \"--ask\" should only be used in a terminal. Exiting.\n",
			noiselevel=-1)
		return 1

	if settings.get("PORTAGE_DEBUG", "") == "1":
		spinner.update = spinner.update_quiet
		portage.debug=1
		if "python-trace" in settings.features:
			import portage.debug
			portage.debug.set_trace(True)

	if not ("--quiet" in myopts):
		if not sys.stdout.isatty() or ("--nospinner" in myopts):
			spinner.update = spinner.update_basic

	if "--version" in myopts:
		print getportageversion(settings["PORTDIR"], settings["ROOT"],
			settings.profile_path, settings["CHOST"],
			trees[settings["ROOT"]]["vartree"].dbapi)
		return 0
	elif "--help" in myopts:
		_emerge.help.help(myaction, myopts, portage.output.havecolor)
		return 0

	if "--debug" in myopts:
		print "myaction", myaction
		print "myopts", myopts

	if not myaction and not myfiles and "--resume" not in myopts:
		_emerge.help.help(myaction, myopts, portage.output.havecolor)
		return 1

	pretend = "--pretend" in myopts
	fetchonly = "--fetchonly" in myopts or "--fetch-all-uri" in myopts
	buildpkgonly = "--buildpkgonly" in myopts

	# check if root user is the current user for the actions where emerge needs this
	if portage.secpass < 2:
		# We've already allowed "--version" and "--help" above.
		if "--pretend" not in myopts and myaction not in ("search","info"):
			need_superuser = not \
				(fetchonly or \
				(buildpkgonly and secpass >= 1) or \
				myaction in ("metadata", "regen") or \
				(myaction == "sync" and os.access(settings["PORTDIR"], os.W_OK)))
			if portage.secpass < 1 or \
				need_superuser:
				if need_superuser:
					access_desc = "superuser"
				else:
					access_desc = "portage group"
				# Always show portage_group_warning() when only portage group
				# access is required but the user is not in the portage group.
				from portage.data import portage_group_warning
				if "--ask" in myopts:
					myopts["--pretend"] = True
					del myopts["--ask"]
					print ("%s access is required... " + \
						"adding --pretend to options.\n") % access_desc
					if portage.secpass < 1 and not need_superuser:
						portage_group_warning()
				else:
					sys.stderr.write(("emerge: %s access is " + \
						"required.\n\n") % access_desc)
					if portage.secpass < 1 and not need_superuser:
						portage_group_warning()
					return 1

	disable_emergelog = False
	for x in ("--pretend", "--fetchonly", "--fetch-all-uri"):
		if x in myopts:
			disable_emergelog = True
			break
	if myaction in ("search", "info"):
		disable_emergelog = True
	if disable_emergelog:
		""" Disable emergelog for everything except build or unmerge
		operations.  This helps minimize parallel emerge.log entries that can
		confuse log parsers.  We especially want it disabled during
		parallel-fetch, which uses --resume --fetchonly."""
		global emergelog
		def emergelog(*pargs, **kargs):
			pass

	if not "--pretend" in myopts:
		emergelog(xterm_titles, "Started emerge on: "+\
			time.strftime("%b %d, %Y %H:%M:%S", time.localtime()))
		myelogstr=""
		if myopts:
			myelogstr=" ".join(myopts)
		if myaction:
			myelogstr+=" "+myaction
		if myfiles:
			myelogstr += " " + " ".join(oldargs)
		emergelog(xterm_titles, " *** emerge " + myelogstr)
	del oldargs

	def emergeexitsig(signum, frame):
		signal.signal(signal.SIGINT, signal.SIG_IGN)
		signal.signal(signal.SIGTERM, signal.SIG_IGN)
		portage.util.writemsg("\n\nExiting on signal %(signal)s\n" % {"signal":signum})
		sys.exit(100+signum)
	signal.signal(signal.SIGINT, emergeexitsig)
	signal.signal(signal.SIGTERM, emergeexitsig)

	def emergeexit():
		"""This gets out final log message in before we quit."""
		if "--pretend" not in myopts:
			emergelog(xterm_titles, " *** terminating.")
		if "notitles" not in settings.features:
			xtermTitleReset()
	portage.atexit_register(emergeexit)

	if myaction in ("config", "metadata", "regen", "sync"):
		if "--pretend" in myopts:
			sys.stderr.write(("emerge: The '%s' action does " + \
				"not support '--pretend'.\n") % myaction)
			return 1
	if "sync" == myaction:
		action_sync(settings, trees, mtimedb, myopts, myaction)
	elif "metadata" == myaction:
		action_metadata(settings, portdb, myopts)
	elif myaction=="regen":
		validate_ebuild_environment(trees)
		action_regen(settings, portdb)
	# HELP action
	elif "config"==myaction:
		validate_ebuild_environment(trees)
		action_config(settings, trees, myopts, myfiles)
	
	# INFO action
	elif "info"==myaction:
		action_info(settings, trees, myopts, myfiles)

	# SEARCH action
	elif "search"==myaction:
		validate_ebuild_environment(trees)
		action_search(trees[settings["ROOT"]]["root_config"],
			myopts, myfiles, spinner)
	elif myaction in ("clean", "unmerge") or \
		(myaction == "prune" and "--nodeps" in myopts):
		validate_ebuild_environment(trees)
		root_config = trees[settings["ROOT"]]["root_config"]
		# When given a list of atoms, unmerge
		# them in the order given.
		ordered = myaction == "unmerge"
		if 1 == unmerge(root_config, myopts, myaction, myfiles,
			mtimedb["ldpath"], ordered=ordered):
			if not (buildpkgonly or fetchonly or pretend):
				post_emerge(trees, mtimedb, os.EX_OK)

	elif myaction in ("depclean", "prune"):
		validate_ebuild_environment(trees)
		action_depclean(settings, trees, mtimedb["ldpath"],
			myopts, myaction, myfiles, spinner)
		if not (buildpkgonly or fetchonly or pretend):
			post_emerge(trees, mtimedb, os.EX_OK)
	# "update", "system", or just process files:
	else:
		validate_ebuild_environment(trees)
		if "--pretend" not in myopts:
			display_news_notification(trees)
		retval = action_build(settings, trees, mtimedb,
			myopts, myaction, myfiles, spinner)
		# if --pretend was not enabled then display_news_notification 
		# was already called by post_emerge
		if "--pretend" in myopts:
			display_news_notification(trees)
		return retval
