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

import os, stat

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

import portage.dep
portage.dep._dep_check_strict = True
import portage.util
import portage.locks
import portage.exception
from portage.data import secpass
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
		"Gentoo Rocks ("+os.uname()[0]+")",
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

	mystatus, myoutput = commands.getstatusoutput("eselect compiler show")
	if mystatus == os.EX_OK and len(myoutput.split("/")) == 2:
		part1, part2 = myoutput.split("/")
		if part1.startswith(chost + "-"):
			return myoutput.replace(chost + "-", gcc_ver_prefix, 1)

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
	unameout=os.uname()[2]+" "+os.uname()[4]

	return "Portage " + portage.VERSION +" ("+profilever+", "+gccver+", "+libcver+", "+unameout+")"

def create_depgraph_params(myopts, myaction):
	#configure emerge engine parameters
	#
	# self:      include _this_ package regardless of if it is merged.
	# selective: exclude the package if it is merged
	# recurse:   go into the dependencies
	# deep:      go into the dependencies of already merged packages
	# empty:     pretend nothing is merged
	# consistent: ensure that installation of new packages does not break
	#            any deep dependencies of required sets (args, system, or
	#            world).
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
		myparams.add("consistent")
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
			Package(type_name=pkg_type, root=self.settings["ROOT"],
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
						metadata = dict(izip(db_keys,
							db.aux_get(cpv, db_keys)))
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
						metadata = dict(izip(db_keys,
							db.aux_get(cpv, db_keys)))
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
	def __init__(self, trees, setconfig):
		self.trees = trees
		self.settings = trees["vartree"].settings
		self.root = self.settings["ROOT"]
		self.setconfig = setconfig
		self.sets = self.setconfig.getSets()

def create_world_atom(pkg_key, metadata, args_set, root_config):
	"""Create a new atom for the world file if one does not exist.  If the
	argument atom is precise enough to identify a specific slot then a slot
	atom will be returned. Atoms that are in the system set may also be stored
	in world since system atoms can only match one slot while world atoms can
	be greedy with respect to slots.  Unslotted system packages will not be
	stored in world."""
	arg_atom = args_set.findAtomForPackage(pkg_key, metadata)
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
		slot_atom = "%s:%s" % (cp, metadata["SLOT"])

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

	if new_world_atom == sets["world"].findAtomForPackage(pkg_key, metadata):
		# Both atoms would be identical, so there's nothing to add.
		return None
	if not slotted:
		# Unlike world atoms, system atoms are not greedy for slots, so they
		# can't be safely excluded from world if they are slotted.
		system_atom = sets["system"].findAtomForPackage(pkg_key, metadata)
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

class AbstractDepPriority(object):
	__slots__ = ("__weakref__", "buildtime", "runtime", "runtime_post")
	def __init__(self, **kwargs):
		for myattr in chain(self.__slots__, AbstractDepPriority.__slots__):
			if myattr == "__weakref__":
				continue
			myvalue = kwargs.get(myattr, False)
			setattr(self, myattr, myvalue)

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

class UnmergeDepPriority(AbstractDepPriority):
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
	def __init__(self, real_vartree, portdb, db_keys, pkg_cache):
		self.root = real_vartree.root
		self.settings = real_vartree.settings
		mykeys = db_keys[:]
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
			if os.access(vdb_path, os.W_OK):
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
						root=self.root, type_name="installed")
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
	if pkg.built and not pkg.installed:
		pkg_chost = pkg.metadata.get("CHOST")
		if pkg_chost and pkg_chost != pkgsettings["CHOST"]:
			return False
	if not portage.eapi_is_supported(pkg.metadata["EAPI"]):
		return False
	if not pkg.installed and \
		pkgsettings.getMissingKeywords(pkg.cpv, pkg.metadata):
		return False
	if pkgsettings.getMaskAtom(pkg.cpv, pkg.metadata):
		return False
	if pkgsettings.getProfileMaskAtom(pkg.cpv, pkg.metadata):
		return False
	try:
		if pkgsettings.getMissingLicenses(pkg.cpv, pkg.metadata):
			return False
	except portage.exception.InvalidDependString:
		return False
	return True

def get_masking_status(pkg, pkgsettings, root_config):

	mreasons = portage.getmaskingstatus(
		pkg, settings=pkgsettings,
		portdb=root_config.trees["porttree"].dbapi)

	if pkg.built and not pkg.installed:
		pkg_chost = pkg.metadata.get("CHOST")
		if pkg_chost and pkg_chost != pkgsettings["CHOST"]:
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
		pkg = Package(type_name=pkg_type, root=root_config.root,
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
					pkgsettings.getMissingLicenses(
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

class Package(object):
	__slots__ = ("__weakref__", "built", "cpv", "depth",
		"installed", "metadata", "root", "onlydeps", "type_name",
		"cp", "cpv_slot", "slot_atom", "_digraph_node")
	def __init__(self, **kwargs):
		for myattr in self.__slots__:
			if myattr == "__weakref__":
				continue
			myvalue = kwargs.get(myattr, None)
			setattr(self, myattr, myvalue)

		self.cp = portage.cpv_getkey(self.cpv)
		self.slot_atom = "%s:%s" % (self.cp, self.metadata["SLOT"])
		self.cpv_slot = "%s:%s" % (self.cpv, self.metadata["SLOT"])

		status = "merge"
		if self.onlydeps or self.installed:
			status = "nomerge"
		self._digraph_node = (self.type_name, self.root, self.cpv, status)

	def __lt__(self, other):
		other_split = portage.catpkgsplit(other.cpv)
		self_split = portage.catpkgsplit(self.cpv)
		if other_split[:2] != self_split[:2]:
			return False
		if portage.pkgcmp(self_split[1:], other_split[1:]) < 0:
			return True
		return False

	def __gt__(self, other):
		other_split = portage.catpkgsplit(other.cpv)
		self_split = portage.catpkgsplit(self.cpv)
		if other_split[:2] != self_split[:2]:
			return False
		if portage.pkgcmp(self_split[1:], other_split[1:]) > 0:
			return True
		return False

	def __eq__(self, other):
		return self._digraph_node == other
	def __ne__(self, other):
		return self._digraph_node != other
	def __hash__(self):
		return hash(self._digraph_node)
	def __len__(self):
		return len(self._digraph_node)
	def __getitem__(self, key):
		return self._digraph_node[key]
	def __iter__(self):
		return iter(self._digraph_node)
	def __contains__(self, key):
		return key in self._digraph_node
	def __str__(self):
		return str(self._digraph_node)

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
		self.set = (self.atom, )

class PackageArg(DependencyArg):
	def __init__(self, package=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.package = package
		self.atom = "=" + package.cpv
		self.set = (self.atom, )

class SetArg(DependencyArg):
	def __init__(self, set=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.set = set
		self.name = self.arg[len(SETPREFIX):]

class Dependency(object):
	__slots__ = ("__weakref__", "atom", "blocker", "depth",
		"parent", "onlydeps", "priority", "root")
	def __init__(self, **kwargs):
		for myattr in self.__slots__:
			if myattr == "__weakref__":
				continue
			myvalue = kwargs.get(myattr, None)
			setattr(self, myattr, myvalue)

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
	class BlockerData(object):
		def __init__(self, counter, atoms):
			self.counter = counter
			self.atoms = atoms

	def __init__(self, myroot, vardb):
		self._vardb = vardb
		self._installed_pkgs = set(vardb.cpv_all())
		self._virtuals = vardb.settings.getvirtuals()
		self._cache_filename = os.path.join(myroot,
			portage.CACHE_PATH.lstrip(os.path.sep), "vdb_blockers.pickle")
		self._cache_version = "1"
		self._cache_data = None
		self._modified = False
		self._load()

	def _load(self):
		try:
			f = open(self._cache_filename)
			mypickle = cPickle.Unpickler(f)
			mypickle.find_global = None
			self._cache_data = mypickle.load()
			f.close()
			del f
		except (IOError, OSError, EOFError, cPickle.UnpicklingError):
			pass
		cache_valid = self._cache_data and \
			isinstance(self._cache_data, dict) and \
			self._cache_data.get("version") == self._cache_version and \
			self._cache_data.get("virtuals") == self._virtuals and \
			set(self._cache_data.get("blockers", [])) == self._installed_pkgs
		if cache_valid:
			for pkg in self._installed_pkgs:
				if long(self._vardb.aux_get(pkg, ["COUNTER"])[0]) != \
					self[pkg].counter:
					cache_valid = False
					break
		if not cache_valid:
			self._cache_data = {"version":self._cache_version}
			self._cache_data["blockers"] = {}
			self._cache_data["virtuals"] = self._virtuals
		self._modified = False

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
		if self._modified and \
			secpass >= 2:
			try:
				f = portage.util.atomic_ofstream(self._cache_filename)
				cPickle.dump(self._cache_data, f, -1)
				f.close()
				portage.util.apply_secpass_permissions(
					self._cache_filename, gid=portage.portage_gid, mode=0644)
			except (IOError, OSError), e:
				pass
			self._modified = False

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
			(blocker_data.counter, blocker_data.atoms)
		self._modified = True

	def __getitem__(self, cpv):
		"""
		@rtype: BlockerData
		@returns: An object with counter and atoms attributes.
		"""
		return self.BlockerData(*self._cache_data["blockers"][cpv])

	def keys(self):
		"""This needs to be implemented so that self.__repr__() doesn't raise
		an AttributeError."""
		if self._cache_data and "blockers" in self._cache_data:
			return self._cache_data["blockers"].keys()
		return []

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
		for e_pkg in cp_list:
			if e_pkg.slot_atom == pkg.slot_atom:
				if e_pkg == pkg:
					return
				self.cpv_remove(e_pkg)
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

	_mydbapi_keys = [
		"CHOST", "COUNTER", "DEPEND", "EAPI", "IUSE", "KEYWORDS",
		"LICENSE", "PDEPEND", "PROVIDE", "RDEPEND",
		"repository", "RESTRICT", "SLOT", "USE"]

	_dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]

	def __init__(self, settings, trees, myopts, myparams, spinner):
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
		self._pkg_cache = {}
		for myroot in trees:
			self.trees[myroot] = {}
			for tree in ("porttree", "bintree"):
				self.trees[myroot][tree] = trees[myroot][tree]
			self.trees[myroot]["vartree"] = \
				FakeVartree(trees[myroot]["vartree"],
					trees[myroot]["porttree"].dbapi,
					self._mydbapi_keys, self._pkg_cache)
			self.pkgsettings[myroot] = portage.config(
				clone=self.trees[myroot]["vartree"].settings)
			self._slot_pkg_map[myroot] = {}
			vardb = self.trees[myroot]["vartree"].dbapi
			# Create a RootConfig instance that references
			# the FakeVartree instead of the real one.
			self.roots[myroot] = RootConfig(self.trees[myroot],
				trees[myroot]["root_config"].setconfig)
			preload_installed_pkgs = "--nodeps" not in self.myopts and \
				"--buildpkgonly" not in self.myopts
			# This fakedbapi instance will model the state that the vdb will
			# have after new packages have been installed.
			fakedb = PackageVirtualDbapi(vardb.settings)
			if preload_installed_pkgs:
				for cpv in vardb.cpv_all():
					self.spinner.update()
					metadata = dict(izip(self._mydbapi_keys,
						vardb.aux_get(cpv, self._mydbapi_keys)))
					pkg = Package(built=True, cpv=cpv,
						installed=True, metadata=metadata,
						root=myroot, type_name="installed")
					self._pkg_cache[pkg] = pkg
					fakedb.cpv_inject(pkg)
			self.mydbapi[myroot] = fakedb
			def graph_tree():
				pass
			graph_tree.dbapi = fakedb
			self._graph_trees[myroot] = {}
			self._graph_trees[myroot]["porttree"] = graph_tree
			self._graph_trees[myroot]["vartree"] = self.trees[myroot]["vartree"]
			del vardb, fakedb
			self._filtered_trees[myroot] = {}
			self._filtered_trees[myroot]["vartree"] = self.trees[myroot]["vartree"]
			def filtered_tree():
				pass
			filtered_tree.dbapi = self._dep_check_composite_db(self, myroot)
			self._filtered_trees[myroot]["porttree"] = filtered_tree
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
		self.blocker_digraph = digraph()
		self.blocker_parents = {}
		self._unresolved_blocker_parents = {}
		self._slot_collision_info = set()
		# Slot collision nodes are not allowed to block other packages since
		# blocker validation is only able to account for one package per slot.
		self._slot_collision_nodes = set()
		self._altlist_cache = {}
		self._pprovided_args = []
		self._missing_args = []
		self._masked_installed = []
		self._unsatisfied_deps_for_display = []
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

		msg = []
		msg.append("\n!!! Multiple versions within a single " + \
			"package slot have been \n")
		msg.append("!!! pulled into the dependency graph:\n\n")
		indent = "  "
		# Max number of parents shown, to avoid flooding the display.
		max_parents = 3
		for slot_atom, root in self._slot_collision_info:
			msg.append(slot_atom)
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
			flags = orig_iuse.symmetric_difference(
				cur_iuse).difference(forced_flags)
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
		debug = "--debug" in self.myopts
		buildpkgonly = "--buildpkgonly" in self.myopts
		nodeps = "--nodeps" in self.myopts
		empty = "empty" in self.myparams
		deep = "deep" in self.myparams
		consistent = "consistent" in self.myparams
		dep_stack = self._dep_stack
		while dep_stack:
			dep = dep_stack.pop()
			if isinstance(dep, Package):
				if not self._add_pkg_deps(dep):
					return 0
				continue
			update = "--update" in self.myopts and dep.depth <= 1
			if dep.blocker:
				if not buildpkgonly and \
					not nodeps and \
					dep.parent not in self._slot_collision_nodes:
					if dep.parent.onlydeps:
						# It's safe to ignore blockers if the
						# parent is an --onlydeps node.
						continue
					# The blocker applies to the root where
					# the parent is or will be installed.
					self.blocker_parents.setdefault(
						("blocks", dep.parent.root, dep.atom), set()).add(
							dep.parent)
				continue
			dep_pkg, existing_node = self._select_package(dep.root, dep.atom,
				onlydeps=dep.onlydeps)
			if not dep_pkg:
				if allow_unsatisfied:
					self._unsatisfied_deps.append(dep)
					continue
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
					if consistent:
						self._ignored_deps.append(dep)
					continue

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

		if pkg.installed:
			# Warn if an installed package is masked and it
			# is pulled into the graph.
			if not visible(pkgsettings, pkg):
				self._masked_installed.append((pkg, pkgsettings))

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
			if "consistent" not in self.myparams:
				return 1
			dep_stack = self._ignored_deps

		self.spinner.update()

		if args:
			depth = 0
		pkg.depth = depth
		dep_stack.append(pkg)
		return 1

	def _add_pkg_deps(self, pkg):

		mytype = pkg.type_name
		myroot = pkg.root
		mykey = pkg.cpv
		metadata = pkg.metadata
		myuse = metadata["USE"].split()
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
						dep_string, myuse=myuse, strict=strict)
				except portage.exception.InvalidDependString, e:
					show_invalid_depstring_notice(jbigkey, dep_string, str(e))
					return 0
				if debug:
					print "Candidates:", selected_atoms
				for atom in selected_atoms:
					blocker = atom.startswith("!")
					if blocker:
						atom = atom[1:]
					mypriority = dep_priority.copy()
					if not blocker and vardb.match(atom):
						mypriority.satisfied = True
					self._dep_stack.append(
						Dependency(atom=atom,
							blocker=blocker, depth=depth, parent=pkg,
							priority=mypriority, root=dep_root))
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
		for atom in self._set_atoms.iterAtomsForPackage(pkg):
			atom_cp = portage.dep_getkey(atom)
			if atom_cp != pkg.cp and \
				self._have_new_virt(pkg.root, atom_cp):
				continue
			for arg in atom_arg_map[(atom, pkg.root)]:
				if isinstance(arg, PackageArg) and \
					arg.package != pkg:
					continue
				yield arg, atom

	def select_files(self, myfiles):
		"""Given a list of .tbz2s, .ebuilds sets, and deps, create the
		appropriate depgraph and return a favorite list."""
		root_config = self.roots[self.target_root]
		sets = root_config.sets
		getSetAtoms = root_config.setconfig.getSetAtoms
		oneshot = "--oneshot" in self.myopts or \
			"--onlydeps" in self.myopts
		myfavorites=[]
		myroot = self.target_root
		dbs = self._filtered_trees[myroot]["dbs"]
		vardb = self.trees[myroot]["vartree"].dbapi
		portdb = self.trees[myroot]["porttree"].dbapi
		bindb = self.trees[myroot]["bintree"].dbapi
		pkgsettings = self.pkgsettings[myroot]
		args = []
		onlydeps = "--onlydeps" in self.myopts
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
				metadata = dict(izip(self._mydbapi_keys,
					bindb.aux_get(mykey, self._mydbapi_keys)))
				pkg = Package(type_name="binary", root=myroot,
					cpv=mykey, built=True, metadata=metadata,
					onlydeps=onlydeps)
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
				metadata = dict(izip(self._mydbapi_keys,
					portdb.aux_get(mykey, self._mydbapi_keys)))
				pkgsettings.setcpv(mykey, mydb=metadata)
				metadata["USE"] = pkgsettings["PORTAGE_USE"]
				pkg = Package(type_name="ebuild", root=myroot,
					cpv=mykey, metadata=metadata, onlydeps=onlydeps)
				args.append(PackageArg(arg=x, package=pkg,
					root_config=root_config))
			elif x.startswith(os.path.sep):
				if not x.startswith(myroot):
					portage.writemsg(("\n\n!!! '%s' does not start with" + \
						" $ROOT.\n") % x, noiselevel=-1)
					return 0, []
				relative_path = x[len(myroot):]
				vartree = self._trees_orig[myroot]["vartree"]
				owner_cpv = None
				for cpv in vardb.cpv_all():
					self.spinner.update()
					cat, pf = portage.catsplit(cpv)
					if portage.dblink(cat, pf, myroot,
						pkgsettings, vartree=vartree).isowner(
						relative_path, myroot):
						owner_cpv = cpv
						break
				if owner_cpv is None:
					portage.writemsg(("\n\n!!! '%s' is not claimed " + \
						"by any package.\n") % x, noiselevel=-1)
					return 0, []
				slot = vardb.aux_get(owner_cpv, ["SLOT"])[0]
				if not slot:
					# portage now masks packages with missing slot, but it's
					# possible that one was installed by an older version
					atom = portage.cpv_getkey(owner_cpv)
				else:
					atom = "%s:%s" % (portage.cpv_getkey(owner_cpv), slot)
				args.append(AtomArg(arg=atom, atom=atom,
					root_config=root_config))
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
					if not oneshot:
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
			if not oneshot:
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
		# Order needs to be preserved since a feature of --nodeps
		# is to allow the user to force a specific merge order.
		args.reverse()
		while args:
			arg = args.pop()
			for atom in arg.set:
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

					self._dep_stack.append(
						Dependency(atom=atom, onlydeps=onlydeps, root=myroot, parent=arg))
					if not self._create_graph():
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
					sys.exit(1)
				except portage.exception.InvalidSignature, e:
					portage.writemsg("\n\n!!! An invalid gpg signature is preventing portage from calculating the\n")
					portage.writemsg("!!! required dependencies. This is a security feature enabled by the admin\n")
					portage.writemsg("!!! to aid in the detection of malicious intent.\n\n")
					portage.writemsg("!!! THIS IS A POSSIBLE INDICATION OF TAMPERED FILES -- CHECK CAREFULLY.\n")
					portage.writemsg("!!! Affected file: %s\n" % (e), noiselevel=-1)
					sys.exit(1)
				except SystemExit, e:
					raise # Needed else can't exit
				except Exception, e:
					print >> sys.stderr, "\n\n!!! Problem in '%s' dependencies." % atom
					print >> sys.stderr, "!!!", str(e), getattr(e, "__module__", None)
					raise

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

		if not self._complete_graph():
			return False, myfavorites

		if not self.validate_blockers():
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
		myuse=None, strict=True, trees=None):
		"""This will raise InvalidDependString if necessary. If trees is
		None then self._filtered_trees is used."""
		pkgsettings = self.pkgsettings[root]
		if trees is None:
			trees = self._filtered_trees
		if True:
			try:
				if not strict:
					portage.dep._dep_check_strict = False
				mycheck = portage.dep_check(depstring, None,
					pkgsettings, myuse=myuse,
					myroot=root, trees=trees)
			finally:
				portage.dep._dep_check_strict = True
			if not mycheck[0]:
				raise portage.exception.InvalidDependString(mycheck[1])
			selected_atoms = mycheck[1]
		return selected_atoms

	def _show_unsatisfied_dep(self, root, atom, myparent=None, arg=None):
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
		missing_licenses = []
		have_eapi_mask = False
		pkgsettings = self.pkgsettings[root]
		root_config = self.roots[root]
		portdb = self.roots[root].trees["porttree"].dbapi
		dbs = self._filtered_trees[root]["dbs"]
		for db, pkg_type, built, installed, db_keys in dbs:
			if installed:
				continue
			match = db.match
			if hasattr(db, "xmatch"):
				cpv_list = db.xmatch("match-all", atom)
			else:
				cpv_list = db.match(atom)
			# descending order
			cpv_list.reverse()
			for cpv in cpv_list:
				metadata, mreasons  = get_mask_info(root_config, cpv,
					pkgsettings, db, pkg_type, built, installed, db_keys)
				masked_packages.append(
					(root_config, pkgsettings, cpv, metadata, mreasons))

		if masked_packages:
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
		pkgsettings = self.pkgsettings[root]
		dbs = self._filtered_trees[root]["dbs"]
		vardb = self.roots[root].trees["vartree"].dbapi
		portdb = self.roots[root].trees["porttree"].dbapi
		# List of acceptable packages, ordered by type preference.
		matched_packages = []
		highest_version = None
		atom_cp = portage.dep_getkey(atom)
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
						break
					reinstall_for_flags = None
					cache_key = (pkg_type, root, cpv, pkg_status)
					calculated_use = True
					pkg = self._pkg_cache.get(cache_key)
					if pkg is None:
						calculated_use = False
						try:
							metadata = dict(izip(self._mydbapi_keys,
								db.aux_get(cpv, self._mydbapi_keys)))
						except KeyError:
							continue
						if not built and ("?" in metadata["LICENSE"] or \
							"?" in metadata["PROVIDE"]):
							# This is avoided whenever possible because
							# it's expensive. It only needs to be done here
							# if it has an effect on visibility.
							pkgsettings.setcpv(cpv, mydb=metadata)
							metadata["USE"] = pkgsettings["PORTAGE_USE"]
							calculated_use = True
						pkg = Package(built=built, cpv=cpv,
							installed=installed, metadata=metadata,
							onlydeps=onlydeps, root=root, type_name=pkg_type)
						self._pkg_cache[pkg] = pkg
					myarg = None
					if root == self.target_root:
						try:
							myarg = self._iter_atoms_for_pkg(pkg).next()
						except StopIteration:
							pass
						except portage.exception.InvalidDependString:
							if not installed:
								# masked by corruption
								continue
					if not installed and myarg:
						found_available_arg = True
					if not installed or (installed and matched_packages):
						# Only enforce visibility on installed packages
						# if there is at least one other visible package
						# available. By filtering installed masked packages
						# here, packages that have been masked since they
						# were installed can be automatically downgraded
						# to an unmasked version.
						if not visible(pkgsettings, pkg):
							continue
					if not built and not calculated_use:
						# This is avoided whenever possible because
						# it's expensive.
						pkgsettings.setcpv(cpv, mydb=pkg.metadata)
						pkg.metadata["USE"] = pkgsettings["PORTAGE_USE"]
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
						cpv_slot = "%s:%s" % \
							(e_pkg.cpv, e_pkg.metadata["SLOT"])
						if portage.dep.match_from_list(atom, [cpv_slot]):
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
						iuses = set(filter_iuse_defaults(
							pkg.metadata["IUSE"].split()))
						old_use = pkg.metadata["USE"].split()
						mydb = pkg.metadata
						if myeb and not usepkgonly:
							mydb = portdb
						if myeb:
							pkgsettings.setcpv(myeb, mydb=mydb)
						else:
							pkgsettings.setcpv(cpv, mydb=mydb)
						now_use = pkgsettings["PORTAGE_USE"].split()
						forced_flags = set()
						forced_flags.update(pkgsettings.useforce)
						forced_flags.update(pkgsettings.usemask)
						cur_iuse = iuses
						if myeb and not usepkgonly:
							cur_iuse = set(filter_iuse_defaults(
								portdb.aux_get(myeb,
								["IUSE"])[0].split()))
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
						pkgsettings.setcpv(cpv, mydb=pkg.metadata)
						forced_flags = set()
						forced_flags.update(pkgsettings.useforce)
						forced_flags.update(pkgsettings.usemask)
						old_use = vardb.aux_get(cpv, ["USE"])[0].split()
						old_iuse = set(filter_iuse_defaults(
							vardb.aux_get(cpv, ["IUSE"])[0].split()))
						cur_use = pkgsettings["PORTAGE_USE"].split()
						cur_iuse = set(filter_iuse_defaults(
							pkg.metadata["IUSE"].split()))
						reinstall_for_flags = \
							self._reinstall_for_flags(
							forced_flags, old_use, old_iuse,
							cur_use, cur_iuse)
						if reinstall_for_flags:
							reinstall = True
					if not installed:
						must_reinstall = empty or \
							(myarg and not selective)
						if not reinstall_for_flags and \
							not must_reinstall and \
							cpv in vardb.match(atom):
							break
					if not built:
						myeb = cpv
					matched_packages.append(pkg)
					if reinstall_for_flags:
						self._reinstall_nodes[pkg] = \
							reinstall_for_flags
					break

		if not matched_packages:
			return None, None

		if "--debug" in self.myopts:
			for pkg in matched_packages:
				print (pkg.type_name + ":").rjust(10), pkg.cpv

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
		currently only enabled by the --complete-graph option.
		"""
		if "consistent" not in self.myparams:
			# Skip this to avoid consuming enough time to disturb users.
			return 1

		if "--buildpkgonly" in self.myopts or \
			"recurse" not in self.myparams:
			return 1

		# Put the depgraph into a mode that causes it to only
		# select packages that have already been added to the
		# graph or those that are installed and have not been
		# scheduled for replacement. Also, toggle the "deep"
		# parameter so that all dependencies are traversed and
		# accounted for.
		self._select_atoms = self._select_atoms_from_graph
		self._select_package = self._select_pkg_from_graph
		self.myparams.add("deep")

		for root in self.roots:
			required_set_names = self._required_set_names.copy()
			if root == self.target_root and \
				("deep" in self.myparams or "empty" in self.myparams):
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
				matches = vardb.match(dep.atom)
				if not matches:
					# Initially unsatisfied.
					continue
				# An scheduled installation broke a deep dependency.
				# Add the installed package to the graph so that it
				# will be appropriately reported as a slot collision
				# (possibly solvable via backtracking).
				cpv = matches[-1] # highest match
				metadata = dict(izip(self._mydbapi_keys,
					vardb.aux_get(cpv, self._mydbapi_keys)))
				pkg = Package(type_name="installed", root=root,
					cpv=cpv, metadata=metadata, built=True,
					installed=True)
				if not self._add_pkg(pkg, dep.parent,
					priority=dep.priority, depth=dep.depth):
					return 0
				if not self._create_graph(allow_unsatisfied=True):
					return 0
		return 1

	def validate_blockers(self):
		"""Remove any blockers from the digraph that do not match any of the
		packages within the graph.  If necessary, create hard deps to ensure
		correct merge order such that mutually blocking packages are never
		installed simultaneously."""

		if "--buildpkgonly" in self.myopts or \
			"--nodeps" in self.myopts:
			return True

		modified_slots = {}
		for myroot in self.trees:
			myslots = {}
			modified_slots[myroot] = myslots
			final_db = self.mydbapi[myroot]
			for pkg in self._slot_pkg_map[myroot].itervalues():
				if not (pkg.installed or pkg.onlydeps):
					myslots[pkg.slot_atom] = pkg.cpv

		#if "deep" in self.myparams:
		if True:
			# Pull in blockers from all installed packages that haven't already
			# been pulled into the depgraph.  This is not enabled by default
			# due to the performance penalty that is incurred by all the
			# additional dep_check calls that are required.

			# Optimization hack for dep_check calls that minimizes the
			# available matches by replacing the portdb with a fakedbapi
			# instance.
			class FakePortageTree(object):
				def __init__(self, mydb):
					self.dbapi = mydb
			dep_check_trees = {}
			for myroot in self.trees:
				dep_check_trees[myroot] = self.trees[myroot].copy()
				dep_check_trees[myroot]["porttree"] = \
					FakePortageTree(self.mydbapi[myroot])

			dep_keys = ["DEPEND","RDEPEND","PDEPEND"]
			for myroot in self.trees:
				vardb = self.trees[myroot]["vartree"].dbapi
				portdb = self.trees[myroot]["porttree"].dbapi
				pkgsettings = self.pkgsettings[myroot]
				final_db = self.mydbapi[myroot]
				cpv_all_installed = self.trees[myroot]["vartree"].dbapi.cpv_all()
				blocker_cache = BlockerCache(myroot, vardb)
				for pkg in cpv_all_installed:
					blocker_atoms = None
					metadata = dict(izip(self._mydbapi_keys,
						vardb.aux_get(pkg, self._mydbapi_keys)))
					node = Package(cpv=pkg, built=True,
						installed=True, metadata=metadata,
						type_name="installed", root=myroot)
					if self.digraph.contains(node):
						continue
					# If this node has any blockers, create a "nomerge"
					# node for it so that they can be enforced.
					self.spinner.update()
					blocker_data = blocker_cache.get(pkg)
					if blocker_data:
						blocker_atoms = blocker_data.atoms
					else:
						dep_vals = vardb.aux_get(pkg, dep_keys)
						myuse = vardb.aux_get(pkg, ["USE"])[0].split()
						depstr = " ".join(dep_vals)
						# It is crucial to pass in final_db here in order to
						# optimize dep_check calls by eliminating atoms via
						# dep_wordreduce and dep_eval calls.
						try:
							portage.dep._dep_check_strict = False
							try:
								success, atoms = portage.dep_check(depstr,
									final_db, pkgsettings, myuse=myuse,
									trees=dep_check_trees, myroot=myroot)
							except Exception, e:
								if isinstance(e, SystemExit):
									raise
								# This is helpful, for example, if a ValueError
								# is thrown from cpv_expand due to multiple
								# matches (this can happen if an atom lacks a
								# category).
								show_invalid_depstring_notice(
									node, depstr, str(e))
								del e
								raise
						finally:
							portage.dep._dep_check_strict = True
						if not success:
							slot_atom = "%s:%s" % (portage.dep_getkey(pkg),
								vardb.aux_get(pkg, ["SLOT"])[0])
							if slot_atom in modified_slots[myroot]:
								# This package is being replaced anyway, so
								# ignore invalid dependencies so as not to
								# annoy the user too much (otherwise they'd be
								# forced to manually unmerge it first).
								continue
							show_invalid_depstring_notice(node, depstr, atoms)
							return False
						blocker_atoms = [myatom for myatom in atoms \
							if myatom.startswith("!")]
						counter = long(vardb.aux_get(pkg, ["COUNTER"])[0])
						blocker_cache[pkg] = \
							blocker_cache.BlockerData(counter, blocker_atoms)
					if blocker_atoms:
						for myatom in blocker_atoms:
							blocker = ("blocks", myroot, myatom[1:])
							myparents = \
								self.blocker_parents.get(blocker, None)
							if not myparents:
								myparents = set()
								self.blocker_parents[blocker] = myparents
							myparents.add(node)
				blocker_cache.flush()
				del blocker_cache

		for blocker in self.blocker_parents.keys():
			mytype, myroot, mydep = blocker
			initial_db = self.trees[myroot]["vartree"].dbapi
			final_db = self.mydbapi[myroot]
			blocked_initial = initial_db.match(mydep)
			blocked_final = final_db.match(mydep)
			if not blocked_initial and not blocked_final:
				del self.blocker_parents[blocker]
				continue
			blocked_slots_initial = {}
			blocked_slots_final = {}
			for cpv in blocked_initial:
				blocked_slots_initial[cpv] = \
					"%s:%s" % (portage.dep_getkey(cpv),
						initial_db.aux_get(cpv, ["SLOT"])[0])
			for cpv in blocked_final:
				blocked_slots_final[cpv] = \
					"%s:%s" % (portage.dep_getkey(cpv),
						final_db.aux_get(cpv, ["SLOT"])[0])
			for parent in list(self.blocker_parents[blocker]):
				ptype, proot, pcpv, pstatus = parent
				pdbapi = self.trees[proot][self.pkg_tree_map[ptype]].dbapi
				pslot = pdbapi.aux_get(pcpv, ["SLOT"])[0]
				pslot_atom = "%s:%s" % (portage.dep_getkey(pcpv), pslot)
				parent_static = pslot_atom not in modified_slots[proot]
				unresolved_blocks = False
				depends_on_order = set()
				for cpv in blocked_initial:
					slot_atom = blocked_slots_initial[cpv]
					if slot_atom == pslot_atom:
						# TODO: Support blocks within slots in cases where it
						# might make sense.  For example, a new version might
						# require that the old version be uninstalled at build
						# time.
						continue
					if parent_static and \
						slot_atom not in modified_slots[myroot]:
						# This blocker will be handled the next time that a
						# merge of either package is triggered.
						continue
					if pstatus == "merge" and \
						slot_atom in modified_slots[myroot]:
						replacement = self._slot_pkg_map[myroot][slot_atom]
						if not portage.match_from_list(
							mydep, [replacement.cpv_slot]):
							# Apparently a replacement may be able to
							# invalidate this block.
							depends_on_order.add((replacement, parent))
							continue
					# None of the above blocker resolutions techniques apply,
					# so apparently this one is unresolvable.
					unresolved_blocks = True
				for cpv in blocked_final:
					slot_atom = blocked_slots_final[cpv]
					if slot_atom == pslot_atom:
						# TODO: Support blocks within slots.
						continue
					if parent_static and \
						slot_atom not in modified_slots[myroot]:
						# This blocker will be handled the next time that a
						# merge of either package is triggered.
						continue
					if not parent_static and pstatus == "nomerge" and \
						slot_atom in modified_slots[myroot]:
						replacement = self._slot_pkg_map[myroot][pslot_atom]
						if replacement not in \
							self.blocker_parents[blocker]:
							# Apparently a replacement may be able to
							# invalidate this block.
							blocked_node = \
								self._slot_pkg_map[myroot][slot_atom]
							depends_on_order.add(
								(replacement, blocked_node))
							continue
					# None of the above blocker resolutions techniques apply,
					# so apparently this one is unresolvable.
					unresolved_blocks = True
				if not unresolved_blocks and depends_on_order:
					for node, pnode in depends_on_order:
						# Enforce correct merge order with a hard dep.
						self.digraph.addnode(node, pnode,
							priority=DepPriority(buildtime=True))
						# Count references to this blocker so that it can be
						# invalidated after nodes referencing it have been
						# merged.
						self.blocker_digraph.addnode(node, blocker)
				if not unresolved_blocks and not depends_on_order:
					self.blocker_parents[blocker].remove(parent)
				if unresolved_blocks:
					self._unresolved_blocker_parents.setdefault(
						blocker, set()).add(parent)
			if not self.blocker_parents[blocker]:
				del self.blocker_parents[blocker]
		# Validate blockers that depend on merge order.
		if not self.blocker_digraph.empty():
			self.altlist()
		if self._slot_collision_info:
			# The user is only notified of a slot collision if there are no
			# unresolvable blocks.
			for x in self.altlist():
				if x[0] == "blocks":
					self._slot_collision_info.clear()
					return True
			if not self._accept_collisions():
				return False
		return True

	def _accept_collisions(self):
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
		if reversed in self._altlist_cache:
			return self._altlist_cache[reversed][:]
		if reversed:
			retlist = self.altlist()
			retlist.reverse()
			self._altlist_cache[reversed] = retlist[:]
			return retlist
		mygraph=self.digraph.copy()
		# Prune "nomerge" root nodes if nothing depends on them, since
		# otherwise they slow down merge order calculation. Don't remove
		# non-root nodes since they help optimize merge order in some cases
		# such as revdep-rebuild.
		while True:
			removed_something = False
			for node in mygraph.root_nodes():
				if not isinstance(node, Package) or \
					node.installed or node.onlydeps:
					mygraph.remove(node)
					removed_something = True
			if not removed_something:
				break
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
		myblockers = self.blocker_digraph.copy()
		retlist=[]
		circular_blocks = False
		blocker_deps = None
		asap_nodes = []
		portage_node = None
		if reversed:
			get_nodes = mygraph.root_nodes
		else:
			get_nodes = mygraph.leaf_nodes
			for node in mygraph.order:
				if node.root == "/" and \
					"sys-apps/portage" == portage.cpv_getkey(node.cpv):
					portage_node = node
					asap_nodes.append(node)
					break
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
						# output, so it's disabled in reversed mode.
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
						if node == portage_node and mygraph.child_nodes(node,
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

			if not selected_nodes:
				if not myblockers.is_empty():
					"""A blocker couldn't be circumnavigated while keeping all
					dependencies satisfied.  The user will have to resolve this
					manually.  This is a panic condition and thus the order
					doesn't really matter, so just pop a random node in order
					to avoid a circular dependency panic if possible."""
					if not circular_blocks:
						circular_blocks = True
						blocker_deps = myblockers.leaf_nodes()
					while blocker_deps:
						# Some of these nodes might have already been selected
						# by the normal node selection process after the
						# circular_blocks flag has been set.  Therefore, we
						# have to verify that they're still in the graph so
						# that they're not selected more than once.
						node = blocker_deps.pop()
						if mygraph.contains(node):
							selected_nodes = [node]
							break

			if not selected_nodes:
				# No leaf nodes are available, so we have a circular
				# dependency panic situation.  Reduce the noise level to a
				# minimum via repeated elimination of root nodes since they
				# have no parents and thus can not be part of a cycle.
				while True:
					root_nodes = mygraph.root_nodes(
						ignore_priority=DepPriority.MEDIUM_SOFT)
					if not root_nodes:
						break
					for node in root_nodes:
						mygraph.remove(node)
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
					display_order.append(list(node))
					tempgraph.remove(node)
				display_order.reverse()
				self.myopts.pop("--quiet", None)
				self.myopts.pop("--verbose", None)
				self.myopts["--tree"] = True
				self.display(display_order)
				print "!!! Error: circular dependencies:"
				print
				mygraph.debug_print()
				print
				print "!!! Note that circular dependencies can often be avoided by temporarily"
				print "!!! disabling USE flags that trigger optional dependencies."
				sys.exit(1)

			# At this point, we've succeeded in selecting one or more nodes, so
			# it's now safe to reset the prefer_asap and accept_root_node flags
			# to their default states.
			prefer_asap = True
			accept_root_node = False

			for node in selected_nodes:
				if node[-1] != "nomerge":
					retlist.append(list(node))
				mygraph.remove(node)
				if not reversed and not circular_blocks and myblockers.contains(node):
					"""This node may have invalidated one or more blockers."""
					myblockers.remove(node)
					for blocker in myblockers.root_nodes():
						if not myblockers.child_nodes(blocker):
							myblockers.remove(blocker)
							unresolved = \
								self._unresolved_blocker_parents.get(blocker)
							if unresolved:
								self.blocker_parents[blocker] = unresolved
							else:
								del self.blocker_parents[blocker]

		if not reversed:
			"""Blocker validation does not work with reverse mode,
			so self.altlist() should first be called with reverse disabled
			so that blockers are properly validated."""
			self.blocker_digraph = myblockers

		""" Add any unresolved blocks so that they can be displayed."""
		for blocker in self.blocker_parents:
			retlist.append(list(blocker))
		self._altlist_cache[reversed] = retlist[:]
		return retlist

	def display(self, mylist, favorites=[], verbosity=None):
		if verbosity is None:
			verbosity = ("--quiet" in self.myopts and 1 or \
				"--verbose" in self.myopts and 3 or 2)
		favorites_set = InternalPackageSet(favorites)
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
		mygraph = self.digraph
		i = 0
		depth = 0
		shown_edges = set()
		for x in mylist:
			if "blocks" == x[0]:
				display_list.append((x, 0, True))
				continue
			graph_key = tuple(x)
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
								if not isinstance(node, Package):
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
									if not isinstance(node, Package):
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
						display_list.append((list(current_node),
							len(tree_nodes), ordered))
						tree_nodes.append(current_node)
					tree_nodes = []
					add_parents(graph_key, True)
			else:
				display_list.append((x, depth, True))
		mylist = display_list

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
			if "blocks" == graph_key[0]:
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

			if x[0]=="blocks":
				addl=""+red("B")+"  "+fetch+"  "
				if ordered:
					counters.blocks += 1
				resolved = portage.key_expand(
					pkg_key, mydb=vardb, settings=pkgsettings)
				if "--columns" in self.myopts and "--quiet" in self.myopts:
					addl = addl + " " + red(resolved)
				else:
					addl = "[blocks " + addl + "] " + red(resolved)
				block_parents = self.blocker_parents[tuple(x)]
				block_parents = set([pnode[2] for pnode in block_parents])
				block_parents = ", ".join(block_parents)
				if resolved!=x[2]:
					addl += bad(" (\"%s\" is blocking %s)") % \
						(pkg_key, block_parents)
				else:
					addl += bad(" (is blocking %s)") % block_parents
				blockers.append(addl)
			else:
				pkg = self._pkg_cache[tuple(x)]
				metadata = pkg.metadata
				pkg_status = x[3]
				pkg_merge = ordered and pkg_status != "nomerge"
				if pkg in self._slot_collision_nodes or pkg.onlydeps:
					# The metadata isn't cached due to a slot collision or
					# --onlydeps.
					mydbapi = self.trees[myroot][self.pkg_tree_map[pkg_type]].dbapi
				else:
					mydbapi = self.mydbapi[myroot] # contains cached metadata
				ebuild_path = None
				repo_name = metadata["repository"]
				built = pkg_type != "ebuild"
				installed = pkg_type == "installed"
				if pkg_type == "ebuild":
					ebuild_path = portdb.findname(pkg_key)
					if not ebuild_path: # shouldn't happen
						raise portage.exception.PackageNotFound(pkg_key)
					repo_path_real = os.path.dirname(os.path.dirname(
						os.path.dirname(ebuild_path)))
				else:
					repo_path_real = portdb.getRepositoryPath(repo_name)
				pkg_use = metadata["USE"].split()
				try:
					restrict = flatten(use_reduce(paren_reduce(
						mydbapi.aux_get(pkg_key, ["RESTRICT"])[0]),
						uselist=pkg_use))
				except portage.exception.InvalidDependString, e:
					if pkg_status != "nomerge":
						restrict = mydbapi.aux_get(pkg_key, ["RESTRICT"])[0]
						show_invalid_depstring_notice(x, restrict, str(e))
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
					if x[3] != "nomerge":
						if ordered:
							counters.reinst += 1
				# filter out old-style virtual matches
				elif installed_versions and \
					portage.cpv_getkey(installed_versions[0]) == \
					portage.cpv_getkey(pkg_key):
					mynewslot = mydbapi.aux_get(pkg_key, ["SLOT"])[0]
					slot_atom = "%s:%s" % \
						(portage.cpv_getkey(pkg_key), mynewslot)
					myinslotlist = vardb.match(slot_atom)
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
						slot_atom = "%s:%s" % (portage.dep_getkey(pkg_key),
							mydbapi.aux_get(pkg_key, ["SLOT"])[0])
						inst_matches = vardb.match(slot_atom)
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
					cur_iuse = list(filter_iuse_defaults(
						mydbapi.aux_get(pkg_key, ["IUSE"])[0].split()))

					forced_flags = set()
					pkgsettings.setcpv(pkg_key, mydb=mydbapi) # for package.use.{mask,force}
					forced_flags.update(pkgsettings.useforce)
					forced_flags.update(pkgsettings.usemask)

					cur_iuse = portage.unique_array(cur_iuse)
					cur_iuse.sort()
					cur_use = pkg_use
					cur_use = [flag for flag in cur_use if flag in cur_iuse]

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
					if pkg_status == "nomerge" or not has_previous:
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

				indent = " " * depth

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
					pkg_system = system_set.findAtomForPackage(pkg_key, metadata)
					pkg_world  = world_set.findAtomForPackage(pkg_key, metadata)
					if not pkg_world and myroot == self.target_root and \
						favorites_set.findAtomForPackage(pkg_key, metadata):
						# Maybe it will be added to world now.
						if create_world_atom(pkg_key, metadata,
							favorites_set, root_config):
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
							myprint="["+pkgprint(pkg_type)+" "+addl+"] "+indent+pkgprint(pkg_cp)
							if (newlp-nc_len(myprint)) > 0:
								myprint=myprint+(" "*(newlp-nc_len(myprint)))
							myprint=myprint+"["+darkblue(xs[1]+xs[2])+"] "
							if (oldlp-nc_len(myprint)) > 0:
								myprint=myprint+" "*(oldlp-nc_len(myprint))
							myprint=myprint+myoldbest
							myprint=myprint+darkgreen("to "+x[1])+" "+verboseadd
					else:
						if not pkg_merge:
							myprint = "[%s      ] " % pkgprint("nomerge")
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
							myprint="["+pkgprint(pkg_type)+" "+addl+"] "+indent+pkgprint(pkg_cp)
							if (newlp-nc_len(myprint)) > 0:
								myprint=myprint+(" "*(newlp-nc_len(myprint)))
							myprint=myprint+green(" ["+xs[1]+xs[2]+"] ")
							if (oldlp-nc_len(myprint)) > 0:
								myprint=myprint+(" "*(oldlp-nc_len(myprint)))
							myprint=myprint+myoldbest+"  "+verboseadd
					else:
						if not pkg_merge:
							myprint="["+pkgprint("nomerge")+"      ] "+indent+pkgprint(pkg_key)+" "+myoldbest+" "+verboseadd
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
		self.display_problems()
		return os.EX_OK

	def display_problems(self):
		"""
		Display problems with the dependency graph such as slot collisions.
		This is called internally by display() to show the problems _after_
		the merge list where it is most likely to be seen, but if display()
		is not going to be called then this method should be called explicitly
		to ensure that the user is notified of problems with the graph.
		"""

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
			sys.stderr.write(" ".join(atom for arg, atom in \
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
				msg.append("  %s%s\n" % (colorize("INFORM", arg), ref_string))
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
		for pkg, pkgsettings in self._masked_installed:
			root_config = self.roots[pkg.root]
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
			metadata = dict(izip(self._mydbapi_keys,
				self.mydbapi[root].aux_get(pkg_key, self._mydbapi_keys)))
			try:
				myfavkey = create_world_atom(pkg_key, metadata,
					args_set, root_config)
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
			if k in ("args", "world"):
				continue
			s = SETPREFIX + k
			if s in world_set:
				continue
			all_added.append(SETPREFIX + k)
		all_added.extend(added_favorites)
		all_added.sort()
		for a in all_added:
			print ">>> Recording %s in \"world\" favorites file..." % \
				colorize("INFORM", a)
		if all_added:
			world_set.update(all_added)
		world_set.unlock()

	def loadResumeCommand(self, resume_data):
		"""
		Add a resume command to the graph and validate it in the process.  This
		will raise a PackageNotFound exception if a package is not available.
		"""
		self._sets["args"].update(resume_data.get("favorites", []))
		mergelist = resume_data.get("mergelist", [])
		fakedb = self.mydbapi
		trees = self.trees
		for x in mergelist:
			if len(x) != 4:
				continue
			pkg_type, myroot, pkg_key, action = x
			if pkg_type not in self.pkg_tree_map:
				continue
			if action != "merge":
				continue
			mydb = trees[myroot][self.pkg_tree_map[pkg_type]].dbapi
			try:
				metadata = dict(izip(self._mydbapi_keys,
					mydb.aux_get(pkg_key, self._mydbapi_keys)))
			except KeyError:
				# It does no exist or it is corrupt.
				raise portage.exception.PackageNotFound(pkg_key)
			if pkg_type == "ebuild":
				pkgsettings = self.pkgsettings[myroot]
				pkgsettings.setcpv(pkg_key, mydb=metadata)
				metadata["USE"] = pkgsettings["PORTAGE_USE"]
			installed = False
			built = pkg_type != "ebuild"
			pkg = Package(built=built, cpv=pkg_key, installed=installed,
				metadata=metadata, root=myroot, type_name=pkg_type)
			self._pkg_cache[pkg] = pkg
			fakedb[myroot].cpv_inject(pkg)
			self.spinner.update()

	class _dep_check_composite_db(object):
		"""
		A dbapi-like interface that is optimized for use in dep_check() calls.
		This is built on top of the existing depgraph package selection logic.
		Some packages that have been added to the graph may be masked from this
		view in order to influence the atom preference selection that occurs
		via dep_check().
		"""
		def __init__(self, depgraph, root):
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
				if pkg.installed and "selective" not in self._depgraph.myparams:
					try:
						arg = self._depgraph._iter_atoms_for_pkg(pkg).next()
					except (StopIteration, portage.exception.InvalidDependString):
						arg = None
					if arg:
						ret = []
				if ret is None and pkg.installed and \
					not visible(self._depgraph.pkgsettings[pkg.root], pkg):
					# For disjunctive || deps, this will cause alternative
					# atoms or packages to be selected if available.
					ret = []
				if ret is None:
					self._cpv_pkg_map[pkg.cpv] = pkg
					ret = [pkg.cpv]
			self._match_cache[orig_atom] = ret
			return ret[:]

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
		self.blocks     = 0
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
		if self.blocks > 0:
			details.append("%s block" % self.blocks)
			if self.blocks > 1:
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
		return "".join(myoutput)

class MergeTask(object):

	def __init__(self, settings, trees, myopts):
		self.settings = settings
		self.target_root = settings["ROOT"]
		self.trees = trees
		self.myopts = myopts
		self.edebug = 0
		if settings.get("PORTAGE_DEBUG", "") == "1":
			self.edebug = 1
		self.pkgsettings = {}
		for root in trees:
			self.pkgsettings[root] = portage.config(
				clone=trees[root]["vartree"].settings)
		self.curval = 0
		self._spawned_pids = []

	def merge(self, mylist, favorites, mtimedb):
		try:
			return self._merge(mylist, favorites, mtimedb)
		finally:
			if self._spawned_pids:
				from portage import process
				process.spawned_pids.extend(self._spawned_pids)
				self._spawned_pids = []

	def _poll_child_processes(self):
		"""
		After each merge, collect status from child processes
		in order to clean up zombies (such as the parallel-fetch
		process).
		"""
		spawned_pids = self._spawned_pids
		if not spawned_pids:
			return
		for pid in list(spawned_pids):
			try:
				if os.waitpid(pid, os.WNOHANG) == (0, 0):
					continue
			except OSError:
				# This pid has been cleaned up elsewhere,
				# so remove it from our list.
				pass
			spawned_pids.remove(pid)

	def _merge(self, mylist, favorites, mtimedb):
		from portage.elog import elog_process
		from portage.elog.filtering import filter_mergephases
		failed_fetches = []
		fetchonly = "--fetchonly" in self.myopts or \
			"--fetch-all-uri" in self.myopts
		pretend = "--pretend" in self.myopts
		mymergelist=[]
		ldpath_mtimes = mtimedb["ldpath"]
		xterm_titles = "notitles" not in self.settings.features

		if "--resume" in self.myopts:
			# We're resuming.
			print colorize("GOOD", "*** Resuming merge...")
			emergelog(xterm_titles, " *** Resuming merge...")
			mylist = mtimedb["resume"]["mergelist"][:]
			if "--skipfirst" in self.myopts and mylist:
				del mtimedb["resume"]["mergelist"][0]
				del mylist[0]
				mtimedb.commit()
			mymergelist = mylist

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
		system_set = root_config.sets["system"]
		args_set = InternalPackageSet(favorites)
		world_set = root_config.sets["world"]
		if "--resume" not in self.myopts:
			mymergelist = mylist
			mtimedb["resume"]["mergelist"]=mymergelist[:]
			mtimedb.commit()

		myfeat = self.settings.features[:]
		bad_resume_opts = set(["--ask", "--tree", "--changelog", "--skipfirst",
			"--resume"])
		if "parallel-fetch" in myfeat and \
			not ("--pretend" in self.myopts or \
			"--fetch-all-uri" in self.myopts or \
			"--fetchonly" in self.myopts):
			if "distlocks" not in myfeat:
				print red("!!!")
				print red("!!!")+" parallel-fetching requires the distlocks feature enabled"
				print red("!!!")+" you have it disabled, thus parallel-fetching is being disabled"
				print red("!!!")
			elif len(mymergelist) > 1:
				fetch_log = "/var/log/emerge-fetch.log"
				logfile = open(fetch_log, "w")
				fd_pipes = {1:logfile.fileno(), 2:logfile.fileno()}
				portage.util.apply_secpass_permissions(fetch_log,
					uid=portage.portage_uid, gid=portage.portage_gid,
					mode=0660)
				fetch_env = os.environ.copy()
				fetch_env["FEATURES"] = fetch_env.get("FEATURES", "") + " -cvs"
				fetch_env["PORTAGE_NICENESS"] = "0"
				fetch_env["PORTAGE_PARALLEL_FETCHONLY"] = "1"
				fetch_args = [sys.argv[0], "--resume", "--fetchonly"]
				resume_opts = self.myopts.copy()
				# For automatic resume, we need to prevent
				# any of bad_resume_opts from leaking in
				# via EMERGE_DEFAULT_OPTS.
				resume_opts["--ignore-default-opts"] = True
				for myopt, myarg in resume_opts.iteritems():
					if myopt not in bad_resume_opts:
						if myarg is True:
							fetch_args.append(myopt)
						else:
							fetch_args.append(myopt +"="+ myarg)
				self._spawned_pids.extend(
					portage.process.spawn(
					fetch_args, env=fetch_env,
					fd_pipes=fd_pipes, returnpid=True))
				logfile.close() # belongs to the spawned process
				del fetch_log, logfile, fd_pipes, fetch_env, fetch_args, \
					resume_opts
				print ">>> starting parallel fetching pid %d" % \
					self._spawned_pids[-1]

		metadata_keys = [k for k in portage.auxdbkeys \
			if not k.startswith("UNUSED_")] + ["USE"]

		mergecount=0
		for x in mymergelist:
			pkg_type = x[0]
			if pkg_type == "blocks":
				continue
			mergecount+=1
			myroot=x[1]
			pkg_key = x[2]
			pkgindex=2
			portdb = self.trees[myroot]["porttree"].dbapi
			bindb  = self.trees[myroot]["bintree"].dbapi
			vartree = self.trees[myroot]["vartree"]
			pkgsettings = self.pkgsettings[myroot]
			metadata = {}
			if pkg_type == "blocks":
				pass
			elif pkg_type == "ebuild":
				mydbapi = portdb
				metadata.update(izip(metadata_keys,
					mydbapi.aux_get(pkg_key, metadata_keys)))
				pkgsettings.setcpv(pkg_key, mydb=mydbapi)
				metadata["USE"] = pkgsettings["PORTAGE_USE"]
			else:
				if pkg_type == "binary":
					mydbapi = bindb
				else:
					raise AssertionError("Package type: '%s'" % pkg_type)
				metadata.update(izip(metadata_keys,
					mydbapi.aux_get(pkg_key, metadata_keys)))
			built = pkg_type != "ebuild"
			installed = pkg_type == "installed"
			pkg = Package(type_name=pkg_type, root=myroot,
				cpv=pkg_key, built=built, installed=installed,
				metadata=metadata)
			if x[0]=="blocks":
				pkgindex=3
			y = portdb.findname(pkg_key)
			if "--pretend" not in self.myopts:
				print "\n>>> Emerging (" + \
					colorize("MERGE_LIST_PROGRESS", str(mergecount)) + " of " + \
					colorize("MERGE_LIST_PROGRESS", str(len(mymergelist))) + ") " + \
					colorize("GOOD", x[pkgindex]) + " to " + x[1]
				emergelog(xterm_titles, " >>> emerge ("+\
					str(mergecount)+" of "+str(len(mymergelist))+\
					") "+x[pkgindex]+" to "+x[1])

			pkgsettings["EMERGE_FROM"] = x[0]
			pkgsettings.backup_changes("EMERGE_FROM")
			pkgsettings.reset()

			#buildsyspkg: Check if we need to _force_ binary package creation
			issyspkg = ("buildsyspkg" in myfeat) \
					and x[0] != "blocks" \
					and system_set.findAtomForPackage(pkg_key, metadata) \
					and "--buildpkg" not in self.myopts
			if x[0] in ["ebuild","blocks"]:
				if x[0] == "blocks" and "--fetchonly" not in self.myopts:
					raise Exception, "Merging a blocker"
				elif "--fetchonly" in self.myopts or \
					"--fetch-all-uri" in self.myopts:
					if "--fetch-all-uri" in self.myopts:
						retval = portage.doebuild(y, "fetch", myroot,
							pkgsettings, self.edebug,
							"--pretend" in self.myopts, fetchonly=1,
							fetchall=1, mydbapi=portdb, tree="porttree")
					else:
						retval = portage.doebuild(y, "fetch", myroot,
							pkgsettings, self.edebug,
							"--pretend" in self.myopts, fetchonly=1,
							mydbapi=portdb, tree="porttree")
					if (retval is None) or retval:
						print
						print "!!! Fetch for",y,"failed, continuing..."
						print
						failed_fetches.append(pkg_key)
					self.curval += 1
					continue

				portage.doebuild_environment(y, "setup", myroot,
					pkgsettings, self.edebug, 1, portdb)
				catdir = os.path.dirname(pkgsettings["PORTAGE_BUILDDIR"])
				portage.util.ensure_dirs(os.path.dirname(catdir),
					uid=portage.portage_uid, gid=portage.portage_gid,
					mode=070, mask=0)
				builddir_lock = None
				catdir_lock = None
				try:
					catdir_lock = portage.locks.lockdir(catdir)
					portage.util.ensure_dirs(catdir,
						gid=portage.portage_gid,
						mode=070, mask=0)
					builddir_lock = portage.locks.lockdir(
						pkgsettings["PORTAGE_BUILDDIR"])
					try:
						portage.locks.unlockdir(catdir_lock)
					finally:
						catdir_lock = None
					msg = " === (%s of %s) Cleaning (%s::%s)" % \
						(mergecount, len(mymergelist), pkg_key, y)
					short_msg = "emerge: (%s of %s) %s Clean" % \
						(mergecount, len(mymergelist), pkg_key)
					emergelog(xterm_titles, msg, short_msg=short_msg)
					retval = portage.doebuild(y, "clean", myroot,
						pkgsettings, self.edebug, cleanup=1,
						mydbapi=portdb, tree="porttree")
					if retval != os.EX_OK:
						return retval
					if "--buildpkg" in self.myopts or issyspkg:
						if issyspkg:
							print ">>> This is a system package, " + \
								"let's pack a rescue tarball."
						msg = " === (%s of %s) Compiling/Packaging (%s::%s)" % \
							(mergecount, len(mymergelist), pkg_key, y)
						short_msg = "emerge: (%s of %s) %s Compile" % \
							(mergecount, len(mymergelist), pkg_key)
						emergelog(xterm_titles, msg, short_msg=short_msg)
						self.trees[myroot]["bintree"].prevent_collision(pkg_key)
						binpkg_tmpfile = os.path.join(pkgsettings["PKGDIR"],
							pkg_key + ".tbz2." + str(os.getpid()))
						pkgsettings["PORTAGE_BINPKG_TMPFILE"] = binpkg_tmpfile
						pkgsettings.backup_changes("PORTAGE_BINPKG_TMPFILE")
						retval = portage.doebuild(y, "package", myroot,
							pkgsettings, self.edebug, mydbapi=portdb,
							tree="porttree")
						del pkgsettings["PORTAGE_BINPKG_TMPFILE"]
						if retval != os.EX_OK or \
							"--buildpkgonly" in self.myopts:
							elog_process(pkg_key, pkgsettings, phasefilter=filter_mergephases)
						if retval != os.EX_OK:
							return retval
						bintree = self.trees[myroot]["bintree"]
						bintree.inject(pkg_key, filename=binpkg_tmpfile)
						if "--buildpkgonly" not in self.myopts:
							msg = " === (%s of %s) Merging (%s::%s)" % \
								(mergecount, len(mymergelist), pkg_key, y)
							short_msg = "emerge: (%s of %s) %s Merge" % \
								(mergecount, len(mymergelist), pkg_key)
							emergelog(xterm_titles, msg, short_msg=short_msg)
							retval = portage.merge(pkgsettings["CATEGORY"],
								pkgsettings["PF"], pkgsettings["D"],
								os.path.join(pkgsettings["PORTAGE_BUILDDIR"],
								"build-info"), myroot, pkgsettings,
								myebuild=pkgsettings["EBUILD"],
								mytree="porttree", mydbapi=portdb,
								vartree=vartree, prev_mtimes=ldpath_mtimes)
							if retval != os.EX_OK:
								return retval
						elif "noclean" not in pkgsettings.features:
							portage.doebuild(y, "clean", myroot,
								pkgsettings, self.edebug, mydbapi=portdb,
								tree="porttree")
					else:
						msg = " === (%s of %s) Compiling/Merging (%s::%s)" % \
							(mergecount, len(mymergelist), pkg_key, y)
						short_msg = "emerge: (%s of %s) %s Compile" % \
							(mergecount, len(mymergelist), pkg_key)
						emergelog(xterm_titles, msg, short_msg=short_msg)
						retval = portage.doebuild(y, "merge", myroot,
							pkgsettings, self.edebug, vartree=vartree,
							mydbapi=portdb, tree="porttree",
							prev_mtimes=ldpath_mtimes)
						if retval != os.EX_OK:
							return retval
				finally:
					if builddir_lock:
						portage.locks.unlockdir(builddir_lock)
					try:
						if not catdir_lock:
							# Lock catdir for removal if empty.
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

			elif x[0]=="binary":
				#merge the tbz2
				mytbz2 = self.trees[myroot]["bintree"].getname(pkg_key)
				if "--getbinpkg" in self.myopts:
					tbz2_lock = None
					try:
						if "distlocks" in pkgsettings.features and \
							os.access(pkgsettings["PKGDIR"], os.W_OK):
							portage.util.ensure_dirs(os.path.dirname(mytbz2))
							tbz2_lock = portage.locks.lockfile(mytbz2,
								wantnewlockfile=1)
						if self.trees[myroot]["bintree"].isremote(pkg_key):
							msg = " --- (%s of %s) Fetching Binary (%s::%s)" %\
								(mergecount, len(mymergelist), pkg_key, mytbz2)
							short_msg = "emerge: (%s of %s) %s Fetch" % \
								(mergecount, len(mymergelist), pkg_key)
							emergelog(xterm_titles, msg, short_msg=short_msg)
							try:
								self.trees[myroot]["bintree"].gettbz2(pkg_key)
							except portage.exception.FileNotFound:
								writemsg("!!! Fetching Binary failed " + \
									"for '%s'\n" % pkg_key, noiselevel=-1)
								if not fetchonly:
									return 1
								failed_fetches.append(pkg_key)
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
								os.unlink(mytbz2)
								if not fetchonly:
									return 1
								failed_fetches.append(pkg_key)
					finally:
						if tbz2_lock:
							portage.locks.unlockfile(tbz2_lock)

				if "--fetchonly" in self.myopts or \
					"--fetch-all-uri" in self.myopts:
					self.curval += 1
					continue

				short_msg = "emerge: ("+str(mergecount)+" of "+str(len(mymergelist))+") "+x[pkgindex]+" Merge Binary"
				emergelog(xterm_titles, " === ("+str(mergecount)+\
					" of "+str(len(mymergelist))+") Merging Binary ("+\
					x[pkgindex]+"::"+mytbz2+")", short_msg=short_msg)
				retval = portage.pkgmerge(mytbz2, x[1], pkgsettings,
					mydbapi=bindb,
					vartree=self.trees[myroot]["vartree"],
					prev_mtimes=ldpath_mtimes)
				if retval != os.EX_OK:
					return retval
				#need to check for errors
			if "--buildpkgonly" not in self.myopts:
				self.trees[x[1]]["vartree"].inject(x[2])
				myfavkey = portage.cpv_getkey(x[2])
				if not fetchonly and not pretend and \
					args_set.findAtomForPackage(pkg_key, metadata):
					world_set.lock()
					world_set.load() # maybe it's changed on disk
					myfavkey = create_world_atom(pkg_key, metadata,
						args_set, root_config)
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
						(mergecount, len(mymergelist), x[pkgindex], y),
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
			self._poll_child_processes()

		if "--pretend" not in self.myopts:
			emergelog(xterm_titles, " *** Finished. Cleaning up...")

		# We're out of the loop... We're done. Delete the resume data.
		if mtimedb.has_key("resume"):
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

def unmerge(root_config, myopts, unmerge_action,
	unmerge_files, ldpath_mtimes, autoclean=0):
	settings = root_config.settings
	sets = root_config.sets
	vartree = root_config.trees["vartree"]
	candidate_catpkgs=[]
	global_unmerge=0
	xterm_titles = "notitles" not in settings.features

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
				#add a "=" if missing
				mymatch=localtree.dep_match("="+x)
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
					if not slotmap.has_key(myslot):
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
	del stop, pos

	# we don't want to unmerge packages that are still listed in user-editable package sets
	# listed in "world" as they would be remerged on the next update of "world" or the 
	# relevant package sets.
	for cp in xrange(len(pkgmap)):
		for cpv in pkgmap[cp]["selected"].copy():
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
				elif sets[s].containsCPV(cpv) \
					and isinstance(sets[s], EditablePackageSet):
					parents.append(s)
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
				sys.exit(retval)
			else:
				sets["world"].cleanPackage(vartree.dbapi, y)
				emergelog(xterm_titles, " >>> unmerge success: "+y)
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

				if not os.path.isdir(inforoot):
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
	vdb_lock = portage.locks.lockdir(vdb_path)
	try:
		if "noinfo" not in settings.features:
			chk_updated_info_files(target_root, infodirs, info_mtimes, retval)
		mtimedb.commit()
	finally:
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
			if settings.has_key("RSYNC_RETRIES"):
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
		myportdir, "metadata/cache", portage.auxdbkeys[:])

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
	unameout=commands.getstatusoutput("uname -mrp")[1]
	print getportageversion(settings["PORTDIR"], settings["ROOT"],
		settings.profile_path, settings["CHOST"],
		trees[settings["ROOT"]]["vartree"].dbapi)
	header_width = 65
	header_title = "System Settings"
	if myfiles:
		print header_width * "="
		print header_title.rjust(int(header_width/2 + len(header_title)/2))
	print header_width * "="
	print "System uname: "+unameout

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
		FakeVartree(trees[myroot]["vartree"],
		trees[myroot]["porttree"].dbapi,
		depgraph._mydbapi_keys, pkg_cache)
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
				metadata = dict(izip(metadata_keys,
					vardb.aux_get(pkg, metadata_keys)))
				arg_atom = None
				try:
					arg_atom = args_set.findAtomForPackage(pkg, metadata)
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
			myaux = dict(izip(aux_keys, vardb.aux_get(pkg, aux_keys)))
			mydeps = []

			usedef = vardb.aux_get(pkg, ["USE"])[0].split()
			for dep_type, depstr in myaux.iteritems():

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
				metadata = dict(izip(metadata_keys,
					vardb.aux_get(pkg, metadata_keys)))
				arg_atom = None
				try:
					arg_atom = args_set.findAtomForPackage(pkg, metadata)
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
			myaux = dict(izip(aux_keys, vardb.aux_get(node, aux_keys)))
			mydeps = []
			usedef = vardb.aux_get(node, ["USE"])[0].split()
			for dep_type, depstr in myaux.iteritems():
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

		if len(graph.order) == len(graph.root_nodes()):
			# If there are no dependencies between packages
			# then just unmerge them alphabetically.
			cleanlist = graph.order[:]
			cleanlist.sort()
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

		unmerge(root_config, myopts,
			"unmerge", cleanlist, ldpath_mtimes)

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

def action_build(settings, trees, mtimedb,
	myopts, myaction, myfiles, spinner):
	ldpath_mtimes = mtimedb["ldpath"]
	favorites=[]
	merge_count = 0
	buildpkgonly = "--buildpkgonly" in myopts
	pretend = "--pretend" in myopts
	fetchonly = "--fetchonly" in myopts or "--fetch-all-uri" in myopts
	ask = "--ask" in myopts
	tree = "--tree" in myopts
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

	# validate the state of the resume data
	# so that we can make assumptions later.
	for k in ("resume", "resume_backup"):
		if k in mtimedb:
			if "mergelist" in mtimedb[k]:
				if not mtimedb[k]["mergelist"]:
					del mtimedb[k]
			else:
				del mtimedb[k]

	if "--resume" in myopts and \
		("resume" in mtimedb or
		"resume_backup" in mtimedb):
		if "resume" not in mtimedb:
			mtimedb["resume"] = mtimedb["resume_backup"]
			del mtimedb["resume_backup"]
			mtimedb.commit()

		# Adjust config according to options of the command being resumed.
		for myroot in trees:
			mysettings =  trees[myroot]["vartree"].settings
			mysettings.unlock()
			adjust_config(myopts, mysettings)
			mysettings.lock()
			del myroot, mysettings

		# "myopts" is a list for backward compatibility.
		resume_opts = mtimedb["resume"].get("myopts", [])
		if isinstance(resume_opts, list):
			resume_opts = dict((k,True) for k in resume_opts)
		for opt in ("--skipfirst", "--ask", "--tree"):
			resume_opts.pop(opt, None)
		myopts.update(resume_opts)
		show_spinner = "--quiet" not in myopts and "--nodeps" not in myopts
		if not show_spinner:
			spinner.update = spinner.update_quiet
		if show_spinner:
			print "Calculating dependencies  ",
		myparams = create_depgraph_params(myopts, myaction)
		mydepgraph = depgraph(settings, trees,
			myopts, myparams, spinner)
		try:
			mydepgraph.loadResumeCommand(mtimedb["resume"])
		except portage.exception.PackageNotFound:
			if show_spinner:
				print
			from portage.output import EOutput
			out = EOutput()
			out.eerror("Error: The resume list contains packages that are no longer")
			out.eerror("       available to be emerged. Please restart/continue")
			out.eerror("       the merge operation manually.")

			# delete the current list and also the backup
			# since it's probably stale too.
			for k in ("resume", "resume_backup"):
				mtimedb.pop(k, None)
			mtimedb.commit()
			return 1
		if show_spinner:
			print "\b\b... done!"
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
		if not retval:
			mydepgraph.display_problems()
			return 1
		if "--quiet" not in myopts and "--nodeps" not in myopts:
			print "\b\b... done!"
		display = pretend or \
			((ask or tree or verbose) and not (quiet and not ask))
		if not display:
			mydepgraph.display_problems()

	if "--pretend" not in myopts and \
		("--ask" in myopts or "--tree" in myopts or \
		"--verbose" in myopts) and \
		not ("--quiet" in myopts and "--ask" not in myopts):
		if "--resume" in myopts:
			mymergelist = mtimedb["resume"]["mergelist"]
			if "--skipfirst" in myopts:
				mymergelist = mymergelist[1:]
			if len(mymergelist) == 0:
				print colorize("INFORM", "emerge: It seems we have nothing to resume...")
				return os.EX_OK
			favorites = mtimedb["resume"]["favorites"]
			retval = mydepgraph.display(mymergelist, favorites=favorites)
			if retval != os.EX_OK:
				return retval
			prompt="Would you like to resume merging these packages?"
		else:
			retval = mydepgraph.display(
				mydepgraph.altlist(reversed=("--tree" in myopts)),
				favorites=favorites)
			if retval != os.EX_OK:
				return retval
			mergecount=0
			for x in mydepgraph.altlist():
				if x[0] != "blocks" and x[3] != "nomerge":
					mergecount+=1
				#check for blocking dependencies
				if x[0]=="blocks" and "--fetchonly" not in myopts and "--fetch-all-uri" not in myopts:
					print "\n!!! Error: The above package list contains packages which cannot be installed"
					print   "!!!        at the same time on the same system."
					if "--quiet" not in myopts:
						show_blocker_docs_link()
					return 1
			if mergecount==0:
				if "--noreplace" in myopts and favorites:
					print
					for x in favorites:
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
			mymergelist = mtimedb["resume"]["mergelist"]
			if "--skipfirst" in myopts:
				mymergelist = mymergelist[1:]
			if len(mymergelist) == 0:
				print colorize("INFORM", "emerge: It seems we have nothing to resume...")
				return os.EX_OK
			favorites = mtimedb["resume"]["favorites"]
			retval = mydepgraph.display(mymergelist, favorites=favorites)
			if retval != os.EX_OK:
				return retval
		else:
			retval = mydepgraph.display(
				mydepgraph.altlist(reversed=("--tree" in myopts)),
				favorites=favorites)
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
			mergetask = MergeTask(settings, trees, myopts)
			if "PORTAGE_PARALLEL_FETCHONLY" in settings:
				""" parallel-fetch uses --resume --fetchonly and we don't want
				it to write the mtimedb"""
				mtimedb.filename = None
				time.sleep(3) # allow the parent to have first fetch
			del mydepgraph
			retval = mergetask.merge(
				mtimedb["resume"]["mergelist"], favorites, mtimedb)
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
			mtimedb["resume"]["favorites"]=favorites
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

			if fetchonly or "--buildpkgonly"  in myopts:
				pkglist = [pkg for pkg in pkglist if pkg[0] != "blocks"]
			else:
				for x in pkglist:
					if x[0] != "blocks":
						continue
					retval = mydepgraph.display(mydepgraph.altlist(
						reversed=("--tree" in myopts)),
						favorites=favorites)
					msg = "Error: The above package list contains " + \
						"packages which cannot be installed " + \
						"at the same time on the same system."
					prefix = bad(" * ")
					from textwrap import wrap
					print
					for line in wrap(msg, 70):
						print prefix + line
					if "--quiet" not in myopts:
						show_blocker_docs_link()
					return 1

			mydepgraph.saveNomergeFavorites()
			del mydepgraph
			mergetask = MergeTask(settings, trees, myopts)
			retval = mergetask.merge(pkglist, favorites, mtimedb)
			merge_count = mergetask.curval

		if retval == os.EX_OK and not (pretend or fetchonly):
			mtimedb.pop("resume", None)
			if "yes" == settings.get("AUTOCLEAN"):
				portage.writemsg_stdout(">>> Auto-cleaning packages...\n")
				unmerge(trees[settings["ROOT"]]["root_config"],
					myopts, "clean", [],
					ldpath_mtimes, autoclean=1)
			else:
				portage.writemsg_stdout(colorize("WARN", "WARNING:")
					+ " AUTOCLEAN is disabled.  This can cause serious"
					+ " problems due to overlapping packages.\n")

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

def load_emerge_config(trees=None):
	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		kwargs[k] = os.environ.get(envvar, None)
	trees = portage.create_trees(trees=trees, **kwargs)

	for root, root_trees in trees.iteritems():
		settings = root_trees["vartree"].settings
		setconfig = load_default_config(settings, root_trees)
		root_trees["root_config"] = RootConfig(root_trees, setconfig)

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
		"override eclasses from PORTDIR then you are advised to run " + \
		"`emerge --regen` after each time that you run `emerge --sync`. " + \
		"Set PORTAGE_ECLASS_WARNING_ENABLE=\"0\" in /etc/make.conf if " + \
		"you would like to disable this warning."
		from textwrap import wrap
		for line in wrap(msg, 72):
			writemsg("%s%s\n" % (prefix, line), noiselevel=-1)

	if "moo" in myfiles:
		print """

  Larry loves Gentoo (""" + os.uname()[0] + """)

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
					sys.stderr.write("emerge: the given set %s does " + \
						"not support unmerge operations\n" % s)
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

	if ("--resume" in myopts):
		if "--tree" in myopts:
			print "* --tree is currently broken with --resume. Disabling..."
			del myopts["--tree"]

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
		if 1 == unmerge(root_config, myopts, myaction, myfiles,
			mtimedb["ldpath"]):
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
