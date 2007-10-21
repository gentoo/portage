#!@PYTHON@ -O
# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

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
from portage.const import EPREFIX
from portage.data import secpass
from portage.util import normalize_path as normpath
from portage.util import writemsg
from portage.sets import InternalPackageSet, SetConfig, make_default_config
from portage.sets.profiles import PackagesSystemSet as SystemSet
from portage.sets.files import WorldSet

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

	def update_basic(self):
		self.spinpos = (self.spinpos + 1) % 500
		if (self.spinpos % 100) == 0:
			if self.spinpos == 0:
				sys.stdout.write(". ")
			else:
				sys.stdout.write(".")
		sys.stdout.flush()

	def update_scroll(self):
		if(self.spinpos >= len(self.scroll_sequence)):
			sys.stdout.write(darkgreen(" \b\b\b" + self.scroll_sequence[
				len(self.scroll_sequence) - 1 - (self.spinpos % len(self.scroll_sequence))]))
		else:
			sys.stdout.write(green("\b " + self.scroll_sequence[self.spinpos]))
		sys.stdout.flush()
		self.spinpos = (self.spinpos + 1) % (2 * len(self.scroll_sequence))

	def update_twirl(self):
		self.spinpos = (self.spinpos + 1) % len(self.twirl_sequence)
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
"sync",  "system", "unmerge",  "world",
]
options=[
"--ask",          "--alphabetical",
"--buildpkg",     "--buildpkgonly",
"--changelog",    "--columns",
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
't':"--tree",
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
		file_path = EPREFIX+"/var/log/emerge.log"
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
	myparams = set(["recurse"])
	if "--update" in myopts or \
		"--newuse" in myopts or \
		"--reinstall" in myopts or \
		"--noreplace" in myopts or \
		myaction in ("system", "world"):
		myparams.add("selective")
	if "--emptytree" in myopts:
		myparams.add("empty")
		myparams.discard("selective")
	if "--nodeps" in myopts:
		myparams.discard("recurse")
	if "--deep" in myopts:
		myparams.add("deep")
	return myparams


class EmergeConfig(portage.config):
	def __init__(self, settings, trees=None, setconfig=None):
		""" You have to specify one of trees or setconfig """
		portage.config.__init__(self, clone=settings)
		if not setconfig:
			setconfigpaths = [os.path.join(GLOBAL_CONFIG_PATH, "sets.conf")]
			setconfigpaths.append(os.path.join(settings["PORTDIR"], "sets.conf"))
			setconfigpaths += [os.path.join(x, "sets.conf") for x in settings["PORDIR_OVERLAY"].split()]
			setconfigpaths.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
				USER_CONFIG_PATH.lstrip(os.path.sep), "sets.conf"))
			#setconfig = SetConfig(setconfigpaths, settings, trees)
			setconfig = make_default_config(settings, trees)
		self.setconfig = setconfig
		self.sets = self.setconfig.getSetsWithAliases()

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
	def __init__(self, settings, portdb, vartree, spinner, searchdesc,
		verbose):
		"""Searches the available and installed packages for the supplied search key.
		The list of available and installed packages is created at object instantiation.
		This makes successive searches faster."""
		self.settings = settings
		self.portdb = portdb
		self.vartree = vartree
		self.spinner = spinner
		self.verbose = verbose
		self.searchdesc = searchdesc
		self.setconfig = settings.setconfig

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
				if self.searchre.search(sdict[setname].getMetadata("DESCRIPTION")):
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
					match        = portage.pkgsplit(match)[0]
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
					mycat = match.split("/")[0]
					mypkg = match.split("/")[1]
					mycpv = match + "-" + myversion
					myebuild = self.portdb.findname(mycpv)
					pkgdir = os.path.dirname(myebuild)
					from portage import manifest
					mf = manifest.Manifest(
						pkgdir, self.settings["DISTDIR"])
					fetchlist = self.portdb.getfetchlist(mycpv,
						mysettings=self.settings, all=True)[1]
					try:
						mysum[0] = mf.getDistfilesSize(fetchlist)
						mystr = str(mysum[0]/1024)
						mycount=len(mystr)
						while (mycount > 3):
							mycount-=3
							mystr=mystr[:mycount]+","+mystr[mycount:]
						mysum[0]=mystr+" kB"
					except KeyError, e:
						mysum[0] = "Unknown (missing digest for %s)" % str(e)

					if self.verbose:
						print "     ", darkgreen("Latest version available:"),myversion
						print "     ", self.getInstallationStatus(mycat+'/'+mypkg)
						print "     ", darkgreen("Size of files:"),mysum[0]
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
	def __init__(self, trees):
		self.trees = trees
		self.settings = EmergeConfig(trees["vartree"].settings, trees=trees)
		self.root = self.settings["ROOT"]

def create_world_atom(pkg_key, metadata, args_set, root_config):
	"""Create a new atom for the world file if one does not exist.  If the
	argument atom is precise enough to identify a specific slot then a slot
	atom will be returned. Atoms that are in the system set may also be stored
	in world since system atoms can only match one slot while world atoms can
	be greedy with respect to slots.  Unslotted system packages will not be
	stored in world."""
	arg_atom = args_set.findAtomForPackage(pkg_key, metadata)
	cp = portage.dep_getkey(arg_atom)
	new_world_atom = cp
	sets = root_config.settings.sets
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
		# First verify the slot is in the portage tree to avoid
		# adding a bogus slot like that produced by multislot.
		if portdb.match(slot_atom):
			# Now verify that the argument is precise enough to identify a
			# specific slot.
			matches = portdb.match(arg_atom)
			matched_slots = set()
			for cpv in matches:
				matched_slots.add(portdb.aux_get(cpv, ["SLOT"])[0])
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

class DepPriority(object):
	"""
		This class generates an integer priority level based of various
		attributes of the dependency relationship.  Attributes can be assigned
		at any time and the new integer value will be generated on calls to the
		__int__() method.  Rich comparison operators are supported.

		The boolean attributes that affect the integer value are "satisfied",
		"buildtime", "runtime", and "system".  Various combinations of
		attributes lead to the following priority levels:

		Combination of properties    Priority level

		not satisfied and buildtime     0
		not satisfied and runtime      -1
		satisfied and buildtime        -2
		satisfied and runtime          -3
		(none of the above)            -4

		Several integer constants are defined for categorization of priority
		levels:

		MEDIUM   The upper boundary for medium dependencies.
		MEDIUM_SOFT   The upper boundary for medium-soft dependencies.
		SOFT     The upper boundary for soft dependencies.
		MIN      The lower boundary for soft dependencies.
	"""
	__slots__ = ("__weakref__", "satisfied", "buildtime", "runtime", "runtime_post", "rebuild")
	MEDIUM = -1
	MEDIUM_SOFT = -2
	SOFT   = -3
	MIN    = -6
	def __init__(self, **kwargs):
		for myattr in self.__slots__:
			if myattr == "__weakref__":
				continue
			myvalue = kwargs.get(myattr, False)
			setattr(self, myattr, myvalue)
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
	def __str__(self):
		myvalue = self.__int__()
		if myvalue > self.MEDIUM:
			return "hard"
		if myvalue > self.MEDIUM_SOFT:
			return "medium"
		if myvalue > self.SOFT:
			return "medium-soft"
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
	def __init__(self, real_vartree, portdb, db_keys):
		self.root = real_vartree.root
		self.settings = real_vartree.settings
		mykeys = db_keys[:]
		for required_key in ("COUNTER", "SLOT"):
			if required_key not in mykeys:
				mykeys.append(required_key)
		self.dbapi = portage.fakedbapi(settings=real_vartree.settings)
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
				self.dbapi.cpv_inject(cpv, metadata=metadata)
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
		self._aux_get_history = set()
		self._portdb_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
		self._portdb = portdb
		self._global_updates = None

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

def cpv_sort_descending(cpv_list):
	"""Sort in place, returns None."""
	if len(cpv_list) <= 1:
		return
	first_split = portage.catpkgsplit(cpv_list[0])
	cat = first_split[0]
	cpv_list[0] = first_split[1:]
	for i in xrange(1, len(cpv_list)):
		cpv_list[i] = portage.catpkgsplit(cpv_list[i])[1:]
	cpv_list.sort(portage.pkgcmp, reverse=True)
	for i, (pn, ver, rev) in enumerate(cpv_list):
		if rev == "r0":
			cpv = cat + "/" + pn + "-" + ver
		else:
			cpv = cat + "/" + pn + "-" + ver + "-" + rev
		cpv_list[i] = cpv

def visible(pkgsettings, cpv, metadata, built=False, installed=False):
	"""
	Check if a package is visible. This can raise an InvalidDependString
	exception if LICENSE is invalid.
	TODO: optionally generate a list of masking reasons
	@rtype: Boolean
	@returns: True if the package is visible, False otherwise.
	"""
	if built and not installed and \
		metadata["CHOST"] != pkgsettings["CHOST"]:
		return False
	if built:
		# we can have an old binary which has no EPREFIX information
		if "EPREFIX" not in metadata or not metadata["EPREFIX"]:
			return False
		if len(metadata["EPREFIX"].strip()) < len(pkgsettings["EPREFIX"]):
			return False
	if not portage.eapi_is_supported(metadata["EAPI"]):
		return False
	if pkgsettings.getMissingKeywords(cpv, metadata):
		return False
	if pkgsettings.getMaskAtom(cpv, metadata):
		return False
	if pkgsettings.getProfileMaskAtom(cpv, metadata):
		return False
	if pkgsettings.getMissingLicenses(cpv, metadata):
		return False
	return True

def iter_atoms(deps):
	"""Take a dependency structure as returned by paren_reduce or use_reduce
	and iterate over all the atoms."""
	i = iter(deps)
	for x in i:
		if isinstance(x, basestring):
			if x == '||' or x.endswith('?'):
				for x in iter_atoms(i.next()):
					yield x
			else:
				yield x
		else:
			for x in iter_atoms(x):
				yield x

class Package(object):
	__slots__ = ("__weakref__", "built", "cpv",
		"installed", "metadata", "root", "type_name")
	def __init__(self, **kwargs):
		for myattr in self.__slots__:
			if myattr == "__weakref__":
				continue
			myvalue = kwargs.get(myattr, None)
			setattr(self, myattr, myvalue)

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

class depgraph(object):

	pkg_tree_map = {
		"ebuild":"porttree",
		"binary":"bintree",
		"installed":"vartree"}

	_mydbapi_keys = [
		"CHOST", "DEPEND", "EAPI", "IUSE", "KEYWORDS",
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
		# Maps cpv to digraph node for all nodes added to the graph.
		self.pkg_node_map = {}
		# Maps slot atom to digraph node for all nodes added to the graph.
		self._slot_node_map = {}
		# Maps nodes to the reasons they were selected for reinstallation.
		self._reinstall_nodes = {}
		self.mydbapi = {}
		self.trees = {}
		self.roots = {}
		# Contains a filtered view of preferred packages that are selected
		# from available repositories.
		self._filtered_trees = {}
		for myroot in trees:
			self.trees[myroot] = {}
			for tree in ("porttree", "bintree"):
				self.trees[myroot][tree] = trees[myroot][tree]
			self.trees[myroot]["vartree"] = \
				FakeVartree(trees[myroot]["vartree"],
					trees[myroot]["porttree"].dbapi,
					self._mydbapi_keys)
			self.pkgsettings[myroot] = portage.config(
				clone=self.trees[myroot]["vartree"].settings)
			self.pkg_node_map[myroot] = {}
			self._slot_node_map[myroot] = {}
			vardb = self.trees[myroot]["vartree"].dbapi
			self.roots[myroot] = RootConfig(self.trees[myroot])
			# This fakedbapi instance will model the state that the vdb will
			# have after new packages have been installed.
			fakedb = portage.fakedbapi(settings=self.pkgsettings[myroot])
			self.mydbapi[myroot] = fakedb
			if "--nodeps" not in self.myopts and \
				"--buildpkgonly" not in self.myopts:
				# --nodeps bypasses this, since it isn't needed in this case
				# and the cache pulls might trigger (slow) cache generation.
				for pkg in vardb.cpv_all():
					self.spinner.update()
					fakedb.cpv_inject(pkg,
						metadata=dict(izip(self._mydbapi_keys,
						vardb.aux_get(pkg, self._mydbapi_keys))))
			del vardb, fakedb
			self._filtered_trees[myroot] = {}
			self._filtered_trees[myroot]["vartree"] = self.trees[myroot]["vartree"]
			def filtered_tree():
				pass
			filtered_tree.dbapi = portage.fakedbapi(
				settings=self.pkgsettings[myroot], exclusive_slots=False)
			self._filtered_trees[myroot]["porttree"] = filtered_tree
			self._filtered_trees[myroot]["atoms"] = set()
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

		self.missingbins=[]
		self.digraph=portage.digraph()
		# Tracks simple parent/child relationships (PDEPEND relationships are
		# not reversed).
		self._parent_child_digraph = digraph()
		self.orderedkeys=[]
		self.outdatedpackages=[]
		# contains all sets added to the graph
		self._sets = {}
		# contains atoms given as arguments
		self._sets["args"] = InternalPackageSet()
		# contains all atoms from all sets added to the graph, including
		# atoms given as arguments
		self._set_atoms = InternalPackageSet()
		# contains all nodes pulled in by self._set_atoms
		self._set_nodes = set()
		self.blocker_digraph = digraph()
		self.blocker_parents = {}
		self._unresolved_blocker_parents = {}
		self._slot_collision_info = []
		# Slot collision nodes are not allowed to block other packages since
		# blocker validation is only able to account for one package per slot.
		self._slot_collision_nodes = set()
		self._altlist_cache = {}
		self._pprovided_args = []

	def _show_slot_collision_notice(self, packages):
		"""Show an informational message advising the user to mask one of the
		the packages. In some cases it may be possible to resolve this
		automatically, but support for backtracking (removal nodes that have
		already been selected) will be required in order to handle all possible
		cases."""

		msg = []
		msg.append("\n!!! Multiple versions within a single " + \
			"package slot have been \n")
		msg.append("!!! pulled into the dependency graph:\n\n")
		for node, parents in packages:
			msg.append(str(node))
			if parents:
				msg.append(" pulled in by\n")
				for parent in parents:
					msg.append("  ")
					msg.append(str(parent))
					msg.append("\n")
			else:
				msg.append(" (no parents)\n")
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

	def create(self, pkg, myparent=None, addme=1,
		priority=None, arg=None, depth=0):
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

		# unused parameters
		rev_dep = False

		mytype = pkg.type_name
		myroot = pkg.root
		mykey = pkg.cpv
		metadata = pkg.metadata
		mybigkey = [mytype, myroot, mykey]

		# select the correct /var database that we'll be checking against
		vardbapi = self.trees[myroot]["vartree"].dbapi
		portdb = self.trees[myroot]["porttree"].dbapi
		bindb = self.trees[myroot]["bintree"].dbapi
		pkgsettings = self.pkgsettings[myroot]

		# if the package is already on the system, we add a "nomerge"
		# directive, otherwise we add a "merge" directive.

		mydbapi = self.trees[myroot][self.pkg_tree_map[mytype]].dbapi
		if metadata is None:
			metadata = dict(izip(self._mydbapi_keys,
				mydbapi.aux_get(mykey, self._mydbapi_keys)))
			if mytype == "ebuild":
				pkgsettings.setcpv(mykey, mydb=portdb)
				metadata["USE"] = pkgsettings["USE"]
		myuse = metadata["USE"].split()

		if not arg and myroot == self.target_root:
			try:
				arg = self._set_atoms.findAtomForPackage(mykey, metadata)
			except portage.exception.InvalidDependString, e:
				if mytype != "installed":
					show_invalid_depstring_notice(tuple(mybigkey+["merge"]),
						metadata["PROVIDE"], str(e))
					return 0
				del e

		if "--nodeps" not in self.myopts:
			self.spinner.update()

		merging = mytype != "installed"

		if addme and mytype != "installed":
			mybigkey.append("merge")
		else:
			mybigkey.append("nomerge")
		jbigkey = tuple(mybigkey)

		if addme:
			slot_atom = "%s:%s" % (portage.dep_getkey(mykey), metadata["SLOT"])
			if myparent and \
				merging and \
				"empty" not in self.myparams and \
				vardbapi.match(slot_atom):
				# Increase the priority of dependencies on packages that
				# are being rebuilt. This optimizes merge order so that
				# dependencies are rebuilt/updated as soon as possible,
				# which is needed especially when emerge is called by
				# revdep-rebuild since dependencies may be affected by ABI
				# breakage that has rendered them useless. Don't adjust
				# priority here when in "empty" mode since all packages
				# are being merged in that case.
				priority.rebuild = True

			existing_node = self._slot_node_map[myroot].get(
				slot_atom, None)
			slot_collision = False
			if existing_node:
				e_type, myroot, e_cpv, e_status = existing_node
				if mykey == e_cpv:
					# The existing node can be reused.
					if existing_node != myparent:
						# Refuse to make a node depend on itself so that
						# we don't create a bogus circular dependency
						# in self.altlist().
						self._parent_child_digraph.add(existing_node, myparent)
						self.digraph.addnode(existing_node, myparent,
							priority=priority)
					return 1
				else:
					if jbigkey in self._slot_collision_nodes:
						return 1
					# A slot collision has occurred.  Sometimes this coincides
					# with unresolvable blockers, so the slot collision will be
					# shown later if there are no unresolvable blockers.
					e_parents = self._parent_child_digraph.parent_nodes(
						existing_node)
					myparents = []
					if myparent:
						myparents.append(myparent)
					self._slot_collision_info.append(
						((jbigkey, myparents), (existing_node, e_parents)))
					self._slot_collision_nodes.add(jbigkey)
					slot_collision = True

			if slot_collision:
				# Now add this node to the graph so that self.display()
				# can show use flags and --tree portage.output.  This node is
				# only being partially added to the graph.  It must not be
				# allowed to interfere with the other nodes that have been
				# added.  Do not overwrite data for existing nodes in
				# self.pkg_node_map and self.mydbapi since that data will
				# be used for blocker validation.
				self.pkg_node_map[myroot].setdefault(mykey, jbigkey)
				# Even though the graph is now invalid, continue to process
				# dependencies so that things like --fetchonly can still
				# function despite collisions.
			else:
				self.mydbapi[myroot].cpv_inject(mykey, metadata=metadata)
				self._slot_node_map[myroot][slot_atom] = jbigkey
				self.pkg_node_map[myroot][mykey] = jbigkey

			if rev_dep and myparent:
				self.digraph.addnode(myparent, jbigkey,
					priority=priority)
			else:
				self.digraph.addnode(jbigkey, myparent,
					priority=priority)

			if mytype != "installed":
				# Allow this package to satisfy old-style virtuals in case it
				# doesn't already. Any pre-existing providers will be preferred
				# over this one.
				try:
					pkgsettings.setinst(mykey, metadata)
					# For consistency, also update the global virtuals.
					settings = self.roots[myroot].settings
					settings.unlock()
					settings.setinst(mykey, metadata)
					settings.lock()
				except portage.exception.InvalidDependString, e:
					show_invalid_depstring_notice(jbigkey, metadata["PROVIDE"], str(e))
					del e
					return 0

		if arg:
			self._set_nodes.add(jbigkey)

		# Do this even when addme is False (--onlydeps) so that the
		# parent/child relationship is always known in case
		# self._show_slot_collision_notice() needs to be called later.
		self._parent_child_digraph.add(jbigkey, myparent)

		""" This section determines whether we go deeper into dependencies or not.
		    We want to go deeper on a few occasions:
		    Installing package A, we need to make sure package A's deps are met.
		    emerge --deep <pkgspec>; we need to recursively check dependencies of pkgspec
		    If we are in --nodeps (no recursion) mode, we obviously only check 1 level of dependencies.
		"""
		if "deep" not in self.myparams and not merging and \
			not ("--update" in self.myopts and arg and merging):
			return 1
		elif "recurse" not in self.myparams:
			return 1

		""" Check DEPEND/RDEPEND/PDEPEND/SLOT
		Pull from bintree if it's binary package, porttree if it's ebuild.
		Binpkg's can be either remote or local. """

		edepend={}
		depkeys = ["DEPEND","RDEPEND","PDEPEND"]
		for k in depkeys:
			edepend[k] = metadata[k]

		if mytype == "ebuild":
			if "--buildpkgonly" in self.myopts:
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

		""" We have retrieve the dependency information, now we need to recursively
		    process them.  DEPEND gets processed for root = "/", {R,P}DEPEND in myroot. """

		if arg:
			depth = 0
		depth += 1

		try:
			if not self._select_dep("/", edepend["DEPEND"], myuse,
				jbigkey, depth,
				DepPriority(buildtime=True, satisfied=bdeps_satisfied)):
				return 0
			"""RDEPEND is soft by definition.  However, in order to ensure
			correct merge order, we make it a hard dependency.  Otherwise, a
			build time dependency might not be usable due to it's run time
			dependencies not being installed yet.
			"""
			if not self._select_dep(myroot, edepend["RDEPEND"], myuse,
				jbigkey, depth, DepPriority(runtime=True)):
				return 0
			if edepend.has_key("PDEPEND") and edepend["PDEPEND"]:
				# Post Depend -- Add to the list without a parent, as it depends
				# on a package being present AND must be built after that package.
				if not self._select_dep(myroot, edepend["PDEPEND"], myuse,
					jbigkey, depth, DepPriority(runtime_post=True)):
					return 0
		except ValueError, e:
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
				myebuild, mylocation = portdb.findname2(mykey)
				portage.writemsg("!!! This ebuild cannot be installed: " + \
					"'%s'\n" % myebuild, noiselevel=-1)
			portage.writemsg("!!! Please notify the package maintainer " + \
				"that atoms must be fully-qualified.\n", noiselevel=-1)
			return 0
		return 1

	def select_files(self,myfiles):
		"given a list of .tbz2s, .ebuilds and deps, create the appropriate depgraph and return a favorite list"
		myfavorites=[]
		myroot = self.target_root
		dbs = self._filtered_trees[myroot]["dbs"]
		filtered_db = self._filtered_trees[myroot]["porttree"].dbapi
		vardb = self.trees[myroot]["vartree"].dbapi
		portdb = self.trees[myroot]["porttree"].dbapi
		bindb = self.trees[myroot]["bintree"].dbapi
		pkgsettings = self.pkgsettings[myroot]
		arg_atoms = []
		addme = "--onlydeps" not in self.myopts
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
				pkg = Package(type_name="binary", root=myroot,
					cpv=mykey, built=True)
				if not self.create(pkg, addme=addme, arg=x):
					return 0, myfavorites
				arg_atoms.append((x, "="+mykey))
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
				pkg = Package(type_name="ebuild", root=myroot,
					cpv=mykey)
				if not self.create(pkg, addme=addme, arg=x):
					return 0, myfavorites
				arg_atoms.append((x, "="+mykey))
			else:
				if not is_valid_package_atom(x):
					portage.writemsg("\n\n!!! '%s' is not a valid package atom.\n" % x,
						noiselevel=-1)
					portage.writemsg("!!! Please check ebuild(5) for full details.\n")
					portage.writemsg("!!! (Did you specify a version but forget to prefix with '='?)\n")
					return (0,[])
				try:
					try:
						for db, pkg_type, built, installed, db_keys in dbs:
							mykey = portage.dep_expand(x,
								mydb=db, settings=pkgsettings)
							if portage.dep_getkey(mykey).startswith("null/"):
								continue
							break
					except ValueError, e:
						if not e.args or not isinstance(e.args[0], list) or \
							len(e.args[0]) < 2:
							raise
						mykey = portage.dep_expand(x,
							mydb=vardb, settings=pkgsettings)
						cp = portage.dep_getkey(mykey)
						if cp.startswith("null/") or \
							cp not in e[0]:
							raise
						del e
					arg_atoms.append((x, mykey))
				except ValueError, e:
					if not e.args or not isinstance(e.args[0], list) or \
						len(e.args[0]) < 2:
						raise
					print "\n\n!!! The short ebuild name \"" + x + "\" is ambiguous.  Please specify"
					print "!!! one of the following fully-qualified ebuild names instead:\n"
					for i in e.args[0]:
						print "    " + green(i)
					print
					return False, myfavorites

		if "--update" in self.myopts:
			"""Make sure all installed slots are updated when possible. Do this
			with --emptytree also, to ensure that all slots are remerged."""
			greedy_atoms = []
			for myarg, atom in arg_atoms:
				greedy_atoms.append((myarg, atom))
				mykey = portage.dep_getkey(atom)
				myslots = set()
				for cpv in vardb.match(mykey):
					myslots.add(vardb.aux_get(cpv, ["SLOT"])[0])
				if myslots:
					self._populate_filtered_repo(myroot, atom,
						exclude_installed=True)
					mymatches = filtered_db.match(atom)
					best_pkg = portage.best(mymatches)
					if best_pkg:
						best_slot = filtered_db.aux_get(best_pkg, ["SLOT"])[0]
						myslots.add(best_slot)
				if len(myslots) > 1:
					for myslot in myslots:
						myslot_atom = "%s:%s" % (mykey, myslot)
						self._populate_filtered_repo(
							myroot, myslot_atom,
							exclude_installed=True)
						if filtered_db.match(myslot_atom):
							greedy_atoms.append((myarg, myslot_atom))
			arg_atoms = greedy_atoms

			# Since populate_filtered_repo() was called with the
			# exclude_installed flag, these atoms will need to be processed
			# again in case installed packages are required to satisfy
			# dependencies.
			self._filtered_trees[myroot]["atoms"].clear()

		oneshot = "--oneshot" in self.myopts or \
			"--onlydeps" in self.myopts
		""" These are used inside self.create() in order to ensure packages
		that happen to match arguments are not incorrectly marked as nomerge."""
		args_set = self._sets["args"]
		for myarg, myatom in arg_atoms:
			if myatom in args_set:
				continue
			args_set.add(myatom)
			self._set_atoms.add(myatom)
			if not oneshot:
				myfavorites.append(myatom)
		for myarg, myatom in arg_atoms:
				try:
					if not self._select_arg(myroot, myatom, myarg, addme):
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
					print >> sys.stderr, "\n\n!!! Problem in '%s' dependencies." % mykey
					print >> sys.stderr, "!!!", str(e), getattr(e, "__module__", None)
					raise

		missing=0
		if "--usepkgonly" in self.myopts:
			for xs in self.digraph.all_nodes():
				if len(xs) >= 4 and xs[0] != "binary" and xs[3] == "merge":
					if missing == 0:
						print
					missing += 1
					print "Missing binary for:",xs[2]

		if not self.validate_blockers():
			return False, myfavorites
		
		# We're true here unless we are missing binaries.
		return (not missing,myfavorites)

	def _populate_filtered_repo(self, myroot, depstring,
			myparent=None, myuse=None, exclude_installed=False):
		"""Extract all of the atoms from the depstring, select preferred
		packages from appropriate repositories, and use them to populate
		the filtered repository. This will raise InvalidDependString when
		necessary."""

		filtered_db = self._filtered_trees[myroot]["porttree"].dbapi
		pkgsettings = self.pkgsettings[myroot]
		usepkgonly = "--usepkgonly" in self.myopts
		if myparent:
			p_type, p_root, p_key, p_status = myparent

		from portage.dep import paren_reduce, use_reduce
		try:
			if myparent and p_type == "installed":
				portage.dep._dep_check_strict = False
			atoms = paren_reduce(depstring)
			atoms = use_reduce(atoms, uselist=myuse)
			atoms = list(iter_atoms(atoms))
			for x in atoms:
				if portage.dep._dep_check_strict and \
					not portage.isvalidatom(x, allow_blockers=True):
					raise portage.exception.InvalidDependString(
						"Invalid atom: %s" % x)
		finally:
			portage.dep._dep_check_strict = True

		filtered_atoms = self._filtered_trees[myroot]["atoms"]
		dbs = self._filtered_trees[myroot]["dbs"]
		old_virts = pkgsettings.getvirtuals()
		while atoms:
			x = atoms.pop()
			if x.startswith("!"):
				continue
			if x in filtered_atoms:
				continue
			filtered_atoms.add(x)
			cp = portage.dep_getkey(x)
			cat = portage.catsplit(cp)[0]
			slot = portage.dep.dep_getslot(x)
			is_virt = cp.startswith("virtual/")
			atom_populated = False
			for db, pkg_type, built, installed, db_keys in dbs:
				if installed and \
					(exclude_installed or not usepkgonly):
					continue
				cpv_list = db.cp_list(cp)
				if not cpv_list:
					if is_virt:
						# old-style virtual
						# Create a transformed atom for each choice
						# and add it to the stack for processing.
						for choice in old_virts.get(cp, []):
							atoms.append(x.replace(cp, choice))
						# Maybe a new-style virtual exists in another db, so
						# we have to try all of them to prevent the old-style
						# virtuals from overriding available new-styles.
					continue
				cpv_sort_descending(cpv_list)
				for cpv in cpv_list:
					if filtered_db.cpv_exists(cpv):
						continue
					if not portage.match_from_list(x, [cpv]):
						continue
					if is_virt:
						mykeys = db_keys[:]
						mykeys.extend(self._dep_keys)
					else:
						mykeys = db_keys
					try:
						metadata = dict(izip(mykeys,
							db.aux_get(cpv, mykeys)))
					except KeyError:
						# masked by corruption
						continue
					if slot is not None:
						if slot != metadata["SLOT"]:
							continue
					if not built:
						if (is_virt or "?" in metadata["LICENSE"]):
							pkgsettings.setcpv(cpv, mydb=metadata)
							metadata["USE"] = pkgsettings["USE"]
						else:
							metadata["USE"] = ""

					try:
						if not visible(pkgsettings, cpv, metadata,
							built=built, installed=installed):
							continue
					except portage.exception.InvalidDependString:
						# masked by corruption
						continue

					filtered_db.cpv_inject(cpv, metadata=metadata)
					if not is_virt:
						# break here since we only want the best version
						# for now (eventually will be configurable).
						atom_populated = True
						break
					# For new-style virtuals, we explore all available
					# versions and recurse on their deps. This is a
					# preparation for the lookahead that happens when
					# new-style virtuals are expanded by dep_check().
					virtual_deps = " ".join(metadata[k] \
						for k in self._dep_keys)
					try:
						if installed:
							portage.dep._dep_check_strict = False
						try:
							deps = paren_reduce(virtual_deps)
							deps = use_reduce(deps,
								uselist=metadata["USE"].split())
							for y in iter_atoms(deps):
								if portage.dep._dep_check_strict and \
									not portage.isvalidatom(y,
									allow_blockers=True):
									raise portage.exception.InvalidDependString(
										"Invalid atom: %s" % y)
								atoms.append(y)
						except portage.exception.InvalidDependString, e:
							# Masked by corruption
							filtered_db.cpv_remove(cpv)
					finally:
						portage.dep._dep_check_strict = True
				if atom_populated:
					break

	def _select_atoms(self, root, depstring, myuse=None, strict=True):
		"""This will raise InvalidDependString if necessary."""
		pkgsettings = self.pkgsettings[root]
		if True:
			try:
				if not strict:
					portage.dep._dep_check_strict = False
				mycheck = portage.dep_check(depstring, None,
					pkgsettings, myuse=myuse,
					myroot=root, trees=self._filtered_trees)
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
		if myparent:
			xfrom = '(dependency required by '+ \
				green('"%s"' % myparent[2]) + \
				red(' [%s]' % myparent[0]) + ')'
		masked_packages = []
		missing_licenses = []
		pkgsettings = self.pkgsettings[root]
		portdb = self.roots[root].trees["porttree"].dbapi
		dbs = self._filtered_trees[root]["dbs"]
		for db, pkg_type, built, installed, db_keys in dbs:
			match = db.match
			if hasattr(db, "xmatch"):
				cpv_list = db.xmatch("match-all", atom)
			else:
				cpv_list = db.match(atom)
			cpv_sort_descending(cpv_list)
			for cpv in cpv_list:
				try:
					metadata = dict(izip(db_keys,
						db.aux_get(cpv, db_keys)))
				except KeyError:
					mreasons = ["corruption"]
					metadata = None
				if metadata and not built:
					if "?" in metadata["LICENSE"]:
						pkgsettings.setcpv(p, mydb=portdb)
						metadata["USE"] = pkgsettings.get("USE", "")
					else:
						metadata["USE"] = ""
				mreasons = portage.getmaskingstatus(
					cpv, metadata=metadata,
					settings=pkgsettings, portdb=portdb)
				comment, filename = None, None
				if "package.mask" in mreasons:
					comment, filename = \
						portage.getmaskingreason(
						cpv, metadata=metadata,
						settings=pkgsettings, portdb=portdb,
						return_location=True)
				if built and \
					metadata["CHOST"] != pkgsettings["CHOST"]:
					mreasons.append("CHOST: %s" % \
						metadata["CHOST"])
				if built:
					if not metadata["EPREFIX"]:
						mreasons.append("missing EPREFIX")
					elif len(metadata["EPREFIX"].strip()) < len(pkgsettings["EPREFIX"]):
						mreasons.append("EPREFIX: '%s' too small" % metadata["EPREFIX"])
				missing_licenses = []
				if metadata:
					try:
						missing_licenses = \
							pkgsettings.getMissingLicenses(
								cpv, metadata)
					except portage.exception.InvalidDependString:
						# This will have already been reported
						# above via mreasons.
						pass
				masked_packages.append((cpv, mreasons,
					comment, filename, missing_licenses))
		if masked_packages:
			print "\n!!! "+red("All ebuilds that could satisfy ")+green(xinfo)+red(" have been masked.")
			print "!!! One of the following masked packages is required to complete your request:"
			shown_licenses = set()
			shown_comments = set()
			# Maybe there is both an ebuild and a binary. Only
			# show one of them to avoid redundant appearance.
			shown_cpvs = set()
			for cpv, mreasons, comment, filename, missing_licenses in masked_packages:
				if cpv in shown_cpvs:
					continue
				shown_cpvs.add(cpv)
				print "- "+cpv+" (masked by: "+", ".join(mreasons)+")"
				if comment and comment not in shown_comments:
					print filename+":"
					print comment
					shown_comments.add(comment)
				for l in missing_licenses:
					l_path = portdb.findLicensePath(l)
					if l in shown_licenses:
						continue
					msg = ("A copy of the '%s' license" + \
					" is located at '%s'.") % (l, l_path)
					print msg
					print
					shown_licenses.add(l)
			print
			print "For more information, see MASKED PACKAGES section in the emerge man page or "
			print "refer to the Gentoo Handbook."
		else:
			print "\nemerge: there are no ebuilds to satisfy "+green(xinfo)+"."
		if myparent:
			print xfrom
		print

	def _select_package(self, root, atom):
		pkgsettings = self.pkgsettings[root]
		dbs = self._filtered_trees[root]["dbs"]
		vardb = self.roots[root].trees["vartree"].dbapi
		portdb = self.roots[root].trees["porttree"].dbapi
		# List of acceptable packages, ordered by type preference.
		matched_packages = []
		existing_node = None
		myeb = None
		usepkgonly = "--usepkgonly" in self.myopts
		empty = "empty" in self.myparams
		selective = "selective" in self.myparams
		for find_existing_node in True, False:
			if existing_node:
				break
			for db, pkg_type, built, installed, db_keys in dbs:
				if existing_node:
					break
				if installed and not find_existing_node and \
					(matched_packages or empty):
					# We only need to select an installed package here
					# if there is no other choice.
					continue
				if hasattr(db, "xmatch"):
					cpv_list = db.xmatch("match-all", atom)
				else:
					cpv_list = db.match(atom)
				cpv_sort_descending(cpv_list)
				for cpv in cpv_list:
					reinstall_for_flags = None
					try:
						metadata = dict(izip(db_keys,
							db.aux_get(cpv, db_keys)))
					except KeyError:
						continue
					if not built:
						if "?" in metadata["LICENSE"]:
							pkgsettings.setcpv(cpv, mydb=metadata)
							metadata["USE"] = pkgsettings.get("USE","")
						else:
							metadata["USE"] = ""
					if not installed:
						try:
							if not visible(pkgsettings, cpv, metadata,
								built=built, installed=installed):
								continue
						except portage.exception.InvalidDependString:
							# masked by corruption
							continue
					# At this point, we've found the highest visible
					# match from the current repo. Any lower versions
					# from this repo are ignored, so this so the loop
					# will always end with a break statement below
					# this point.
					if find_existing_node:
						slot_atom = "%s:%s" % (
							portage.cpv_getkey(cpv), metadata["SLOT"])
						existing_node = self._slot_node_map[root].get(
							slot_atom)
						if not existing_node:
							break
						e_type, root, e_cpv, e_status = existing_node
						metadata = dict(izip(self._mydbapi_keys,
							self.mydbapi[root].aux_get(
							e_cpv, self._mydbapi_keys)))
						cpv_slot = "%s:%s" % (e_cpv, metadata["SLOT"])
						if portage.dep.match_from_list(atom, [cpv_slot]):
							matched_packages.append(
								Package(type_name=e_type, root=root,
									cpv=e_cpv, metadata=metadata))
						else:
							existing_node = None
						break
					# Compare built package to current config and
					# reject the built package if necessary.
					if built and not installed and \
						("--newuse" in self.myopts or \
						"--reinstall" in self.myopts):
						iuses = set(filter_iuse_defaults(
							metadata["IUSE"].split()))
						old_use = metadata["USE"].split()
						mydb = metadata
						if myeb and not usepkgonly:
							mydb = portdb
						if myeb:
							pkgsettings.setcpv(myeb, mydb=mydb)
						else:
							pkgsettings.setcpv(cpv, mydb=mydb)
						now_use = pkgsettings["USE"].split()
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
						vardb.cpv_exists(cpv):
						pkgsettings.setcpv(cpv, mydb=metadata)
						forced_flags = set()
						forced_flags.update(pkgsettings.useforce)
						forced_flags.update(pkgsettings.usemask)
						old_use = vardb.aux_get(cpv, ["USE"])[0].split()
						old_iuse = set(filter_iuse_defaults(
							vardb.aux_get(cpv, ["IUSE"])[0].split()))
						cur_use = pkgsettings["USE"].split()
						cur_iuse = set(filter_iuse_defaults(
							metadata["IUSE"].split()))
						reinstall_for_flags = \
							self._reinstall_for_flags(
							forced_flags, old_use, old_iuse,
							cur_use, cur_iuse)
					myarg = None
					if root == self.target_root:
						try:
							myarg = self._set_atoms.findAtomForPackage(
								cpv, metadata)
						except portage.exception.InvalidDependString:
							# If relevant this error will be shown
							# in the masked package display.
							if not installed:
								break
					if not installed and not reinstall_for_flags and \
						("selective" in self.myparams or \
						not myarg) and \
						not empty and \
						vardb.cpv_exists(cpv):
						break
					if installed and not (selective or not myarg):
						break
					# Metadata accessed above is cached internally by
					# each db in order to optimize visibility checks.
					# Now that all possible checks visibility checks
					# are complete, it's time to pull the rest of the
					# metadata (including *DEPEND). This part is more
					# expensive, so avoid it whenever possible.
					metadata.update(izip(self._mydbapi_keys,
						db.aux_get(cpv, self._mydbapi_keys)))
					if not built:
						pkgsettings.setcpv(cpv, mydb=metadata)
						metadata["USE"] = pkgsettings.get("USE","")
						myeb = cpv
					matched_packages.append(
						Package(type_name=pkg_type, root=root,
							cpv=cpv, metadata=metadata,
							built=built, installed=installed))
					if reinstall_for_flags:
						pkg_node = (pkg_type, root, cpv, "merge")
						self._reinstall_nodes[pkg_node] = \
							reinstall_for_flags
					break

		if not matched_packages:
			return None, None

		if "--debug" in self.myopts:
			for pkg in matched_packages:
				print (pkg.type_name + ":").rjust(10), pkg.cpv

		if len(matched_packages) > 1:
			bestmatch = portage.best(
				[pkg.cpv for pkg in matched_packages])
			matched_packages = [pkg for pkg in matched_packages \
				if pkg.cpv == bestmatch]

		# ordered by type preference ("ebuild" type is the last resort)
		return  matched_packages[-1], existing_node

	def _select_dep(self, myroot, depstring, myuse,
		myparent, depth, priority):
		""" Given a depstring, create the depgraph such that all dependencies are satisfied.
		@param myroot: $ROOT where these dependencies should be merged to.
		@param myuse: List of USE flags enabled for myparent.
		@param myparent: The node whose depstring is being passed in.
		@param priority: DepPriority indicating the dependency type.
		@param depth: The depth of recursion in dependencies relative to the
			nearest argument atom.
		@returns: 1 on success and 0 on failure
		"""

		if not depstring:
			return 1 # nothing to do

		vardb  = self.roots[myroot].trees["vartree"].dbapi
		strict = True
		if myparent:
			p_type, p_root, p_key, p_status = myparent
			if p_type == "installed":
				strict = False

		if "--debug" in self.myopts:
			print
			print "Parent:   ",myparent
			print "Depstring:",depstring
			print "Priority:", priority

		try:
			self._populate_filtered_repo(
				myroot, depstring, myparent=myparent, myuse=myuse)
			mymerge = self._select_atoms(myroot, depstring,
				myuse=myuse, strict=strict)
		except portage.exception.InvalidDependString, e:
			if myparent:
				show_invalid_depstring_notice(
					myparent, depstring, str(e))
			else:
				sys.stderr.write("\n%s\n%s\n" % (depstring, str(e)))
			return 0

		if "--debug" in self.myopts:
			print "Candidates:",mymerge
		for x in mymerge:
			selected_pkg = None
			if x.startswith("!"):
				if "--buildpkgonly" not in self.myopts and \
					"--nodeps" not in self.myopts and \
					myparent not in self._slot_collision_nodes:
					p_type, p_root, p_key, p_status = myparent
					if  p_type != "installed" and p_status != "merge":
						# It's safe to ignore blockers from --onlydeps nodes.
						continue
					self.blocker_parents.setdefault(
						("blocks", p_root, x[1:]), set()).add(myparent)
				continue
			else:

				pkg, existing_node = self._select_package(myroot, x)
				if not pkg:
					self._show_unsatisfied_dep(myroot, x, myparent=myparent)
					return 0

				# In some cases, dep_check will return deps that shouldn't
				# be proccessed any further, so they are identified and
				# discarded here. Try to discard as few as possible since
				# discarded dependencies reduce the amount of information
				# available for optimization of merge order.
				if myparent and vardb.match(x) and \
					not existing_node and \
					"empty" not in self.myparams and \
					"deep" not in self.myparams and \
					not ("--update" in self.myopts and depth <= 1):
					myarg = None
					if myroot == self.target_root:
						try:
							myarg = self._set_atoms.findAtomForPackage(
								pkg.cpv, pkg.metadata)
						except portage.exception.InvalidDependString:
							# This is already handled inside
							# self.create() when necessary.
							pass
					if not myarg:
						continue

			mypriority = None
			if myparent:
				mypriority = priority.copy()
				if vardb.match(x):
					mypriority.satisfied = True
			if not self.create(pkg, myparent=myparent,
				priority=mypriority, depth=depth):
				return 0

		if "--debug" in self.myopts:
			print "Exiting...",myparent
		return 1

	def _select_arg(self, root, atom, arg, addme):
		pprovided = self.pkgsettings[root].pprovideddict.get(
			portage.dep_getkey(atom))
		if pprovided and portage.match_from_list(atom, pprovided):
			# A provided package has been specified on the command line.
			self._pprovided_args.append((arg, atom))
			return 1
		self._populate_filtered_repo(root, atom)
		pkg, existing_node = self._select_package(root, atom)
		if not pkg:
			self._show_unsatisfied_dep(root, atom, arg=arg)
			return 0
		return self.create(pkg, addme=addme)

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
			slot_node_map = self._slot_node_map[myroot]
			for slot_atom, mynode in slot_node_map.iteritems():
				mytype, myroot, mycpv, mystatus = mynode
				if mystatus == "merge":
					myslots[slot_atom] = mycpv

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
				pkg_node_map = self.pkg_node_map[myroot]
				vardb = self.trees[myroot]["vartree"].dbapi
				portdb = self.trees[myroot]["porttree"].dbapi
				pkgsettings = self.pkgsettings[myroot]
				final_db = self.mydbapi[myroot]
				cpv_all_installed = self.trees[myroot]["vartree"].dbapi.cpv_all()
				blocker_cache = BlockerCache(myroot, vardb)
				for pkg in cpv_all_installed:
					blocker_atoms = None
					matching_node = pkg_node_map.get(pkg, None)
					if matching_node and \
						matching_node[3] == "nomerge":
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
									("installed", myroot, pkg, "nomerge"),
									depstr, str(e))
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
							show_invalid_depstring_notice(
								("installed", myroot, pkg, "nomerge"),
								depstr, atoms)
							return False
						blocker_atoms = [myatom for myatom in atoms \
							if myatom.startswith("!")]
						counter = long(vardb.aux_get(pkg, ["COUNTER"])[0])
						blocker_cache[pkg] = \
							blocker_cache.BlockerData(counter, blocker_atoms)
					if blocker_atoms:
						# Don't store this parent in pkg_node_map, because it's
						# not needed there and it might overwrite a "merge"
						# node with the same cpv.
						myparent = ("installed", myroot, pkg, "nomerge")
						for myatom in blocker_atoms:
							blocker = ("blocks", myroot, myatom[1:])
							myparents = \
								self.blocker_parents.get(blocker, None)
							if not myparents:
								myparents = set()
								self.blocker_parents[blocker] = myparents
							myparents.add(myparent)
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
						replacement = final_db.match(slot_atom)
						if replacement:
							if not portage.match_from_list(mydep, replacement):
								# Apparently a replacement may be able to
								# invalidate this block.
								replacement_node = \
									self.pkg_node_map[proot][replacement[0]]
								depends_on_order.add((replacement_node, parent))
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
						replacement = final_db.match(pslot_atom)
						if replacement:
							replacement_node = \
								self.pkg_node_map[proot][replacement[0]]
							if replacement_node not in \
								self.blocker_parents[blocker]:
								# Apparently a replacement may be able to
								# invalidate this block.
								blocked_node = self.pkg_node_map[proot][cpv]
								depends_on_order.add(
									(replacement_node, blocked_node))
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
					return True
			self._show_slot_collision_notice(self._slot_collision_info[0])
			if not self._accept_collisions():
				return False
		return True

	def _accept_collisions(self):
		acceptable = False
		for x in ("--nodeps", "--pretend", "--fetchonly", "--fetch-all-uri"):
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
		self._merge_order_bias(mygraph)
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
			for cpv, node in self.pkg_node_map["/"].iteritems():
				if "portage" == portage.catsplit(portage.dep_getkey(cpv))[-1]:
					portage_node = node
					asap_nodes.append(node)
					break
		ignore_priority_soft_range = [None]
		ignore_priority_soft_range.extend(
			xrange(DepPriority.MIN, DepPriority.SOFT + 1))
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
								# TODO: Try harder to make these nodes get
								# merged absolutely as soon as possible.
								asap_nodes.append(child)

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
						ignore_priority=DepPriority.SOFT)
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

	def xcreate(self,mode="system"):
		vardb = self.trees[self.target_root]["vartree"].dbapi
		filtered_db = self._filtered_trees[self.target_root]["porttree"].dbapi
		world_problems = False

		root_config = self.roots[self.target_root]
		world_set = root_config.settings.sets["world"]
		system_set = root_config.settings.sets["system"]
		mylist = list(system_set)
		self._sets["system"] = system_set
		if mode == "world":
			self._sets["world"] = world_set
			for x in world_set:
				if not portage.isvalidatom(x):
					world_problems = True
					continue
				elif not vardb.match(x):
					world_problems = True
					self._populate_filtered_repo(self.target_root, x,
						exclude_installed=True)
					if not filtered_db.match(x):
						continue
				mylist.append(x)

		newlist = []
		missing_atoms = []
		empty = "empty" in self.myparams
		for atom in mylist:
			self._populate_filtered_repo(self.target_root, atom,
				exclude_installed=True)
			if not filtered_db.match(atom):
				if empty or not vardb.match(atom):
					missing_atoms.append(atom)
				continue
			mykey = portage.dep_getkey(atom)
			if True:
				newlist.append(atom)
				if mode == "system" or atom not in world_set:
					# only world is greedy for slots, not system
					continue
				# Make sure all installed slots are updated when possible.
				# Do this with --emptytree also, to ensure that all slots are
				# remerged.
				myslots = set()
				for cpv in vardb.match(mykey):
					myslots.add(vardb.aux_get(cpv, ["SLOT"])[0])
				if myslots:
					self._populate_filtered_repo(self.target_root, atom,
						exclude_installed=True)
					mymatches = filtered_db.match(atom)
					best_pkg = portage.best(mymatches)
					if best_pkg:
						best_slot = filtered_db.aux_get(best_pkg, ["SLOT"])[0]
						myslots.add(best_slot)
				if len(myslots) > 1:
					for myslot in myslots:
						myslot_atom = "%s:%s" % (mykey, myslot)
						self._populate_filtered_repo(
							self.target_root, myslot_atom,
							exclude_installed=True)
						if filtered_db.match(myslot_atom):
							newlist.append(myslot_atom)
		mylist = newlist

		for myatom in mylist:
			self._set_atoms.add(myatom)

		# Since populate_filtered_repo() was called with the exclude_installed
		# flag, these atoms will need to be processed again in case installed
		# packages are required to satisfy dependencies.
		self._filtered_trees[self.target_root]["atoms"].clear()
		addme = "--onlydeps" not in self.myopts
		for mydep in mylist:
			if not self._select_arg(self.target_root, mydep, mydep, addme):
				print >> sys.stderr, "\n\n!!! Problem resolving dependencies for", mydep
				return 0

		if not self.validate_blockers():
			return False

		if world_problems:
			print >> sys.stderr, "\n!!! Problems have been detected with your world file"
			print >> sys.stderr, "!!! Please run "+green("emaint --check world")+"\n"

		if missing_atoms:
			print >> sys.stderr, "\n" + colorize("BAD", "!!!") + \
				" Ebuilds for the following packages are either all"
			print >> sys.stderr, colorize("BAD", "!!!") + " masked or don't exist:"
			print >> sys.stderr, " ".join(missing_atoms) + "\n"

		return 1

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
		mygraph = self._parent_child_digraph
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
			pkg_node = tuple(x)
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
				pkg_status = x[3]
				pkg_merge = ordered and pkg_status != "nomerge"
				if pkg_node in self._slot_collision_nodes or \
					(pkg_status == "nomerge" and pkg_type != "installed"):
					# The metadata isn't cached due to a slot collision or
					# --onlydeps.
					mydbapi = self.trees[myroot][self.pkg_tree_map[pkg_type]].dbapi
				else:
					mydbapi = self.mydbapi[myroot] # contains cached metadata
				metadata = dict(izip(self._mydbapi_keys,
					mydbapi.aux_get(pkg_key, self._mydbapi_keys)))
				ebuild_path = None
				if pkg_type == "binary":
					repo_name = self.roots[myroot].settings.get("PORTAGE_BINHOST")
				else:
					repo_name = metadata["repository"]
				if pkg_type == "ebuild":
					ebuild_path = portdb.findname(pkg_key)
					if not ebuild_path: # shouldn't happen
						raise portage.exception.PackageNotFound(pkg_key)
					repo_path_real = os.path.dirname(os.path.dirname(
						os.path.dirname(ebuild_path)))
					pkgsettings.setcpv(pkg_key, mydb=mydbapi)
					metadata["USE"] = pkgsettings["USE"]
				else:
					repo_path_real = repo_name
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
				myoldbest=""
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
						myoldbest=portage.best(myinslotlist)
						addl="   "+fetch
						if portage.pkgcmp(portage.pkgsplit(x[2]), portage.pkgsplit(myoldbest)) < 0:
							# Downgrade in slot
							addl+=turquoise("U")+blue("D")
							if ordered:
								counters.downgrades += 1
						else:
							# Update in slot
							addl+=turquoise("U")+" "
							if ordered:
								counters.upgrades += 1
					else:
						# New slot, mark it new.
						addl=" "+green("NS")+fetch+"  "
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
					addl=" "+green("N")+" "+fetch+"  "
					if ordered:
						counters.new += 1

				verboseadd=""
				
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

					if myoldbest:
						pkg = myoldbest
					else:
						pkg = x[2]
					if self.trees[x[1]]["vartree"].dbapi.cpv_exists(pkg):
						old_iuse, old_use = \
							self.trees[x[1]]["vartree"].dbapi.aux_get(
								pkg, ["IUSE", "USE"])
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
					reinstall_for_flags = self._reinstall_nodes.get(pkg_node)
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
						# To avoid spam during the transition period, don't
						# show ? if the installed package is missing a
						# repository label.
						if not repo_path_prev or \
							repo_path_prev == repo_path_real:
							repoadd = repo_display.repoStr(repo_path_real)
						else:
							repoadd = "%s=>%s" % (
								repo_display.repoStr(repo_path_prev),
								repo_display.repoStr(repo_path_real))
					if repoadd and repoadd != "0":
						show_repos = True
						verboseadd += teal("[%s]" % repoadd)

				xs = list(portage.pkgsplit(x[2]))
				if xs[2]=="r0":
					xs[2]=""
				else:
					xs[2]="-"+xs[2]

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
				oldlp=mywidth-30
				newlp=oldlp-30

				indent = " " * depth

				if myoldbest:
					myoldbest=portage.pkgsplit(myoldbest)[1]+"-"+portage.pkgsplit(myoldbest)[2]
					if myoldbest[-3:]=="-r0":
						myoldbest=myoldbest[:-3]
					myoldbest=blue("["+myoldbest+"]")

				pkg_cp = xs[0]
				root_config = self.roots[myroot]
				system_set = root_config.settings.sets["system"]
				world_set  = root_config.settings.sets["world"]

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

				def pkgprint(pkg):
					if pkg_merge:
						if pkg_system:
							return colorize("PKG_MERGE_SYSTEM", pkg)
						elif pkg_world:
							return colorize("PKG_MERGE_WORLD", pkg)
						else:
							return colorize("PKG_MERGE", pkg)
					else:
						if pkg_system:
							return colorize("PKG_NOMERGE_SYSTEM", pkg)
						elif pkg_world:
							return colorize("PKG_NOMERGE_WORLD", pkg)
						else:
							return colorize("PKG_NOMERGE", pkg)

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

			mysplit = portage.pkgsplit(x[2])
			if "--tree" not in self.myopts and mysplit and \
				len(mysplit) == 3 and mysplit[0] == "sys-apps/portage" and \
				x[1] == "/":

				if mysplit[2] == "r0":
					myversion = mysplit[1]
				else:
					myversion = "%s-%s" % (mysplit[1], mysplit[2])

				if myversion != portage.VERSION and "--quiet" not in self.myopts:
					if mylist_index < len(mylist) - 1 and \
						"livecvsportage" not in self.settings.features:
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

		if self._pprovided_args:
			arg_refs = {}
			for arg_atom in self._pprovided_args:
				arg, atom = arg_atom
				arg_refs[arg_atom] = []
				cp = portage.dep_getkey(atom)
				for set_name, atom_set in self._sets.iteritems():
					if atom in atom_set:
						arg_refs[arg_atom].append(set_name)
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
		return os.EX_OK

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
		for x in ("--fetchonly", "--fetch-all-uri",
			"--oneshot", "--onlydeps", "--pretend"):
			if x in self.myopts:
				return
		root_config = self.roots[self.target_root]
		world_set = root_config.settings.sets["world"]
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
					world_set.add(myfavkey)
					print ">>> Recording",myfavkey,"in \"world\" favorites file..."
			except portage.exception.InvalidDependString, e:
				writemsg("\n\n!!! '%s' has invalid PROVIDE: %s\n" % \
					(pkg_key, str(e)), noiselevel=-1)
				writemsg("!!! see '%s'\n\n" % os.path.join(
					root, portage.VDB_PATH, pkg_key, "PROVIDE"), noiselevel=-1)
				del e
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
			fakedb[myroot].cpv_inject(pkg_key, metadata=metadata)
			if pkg_type == "ebuild":
				pkgsettings = self.pkgsettings[myroot]
				pkgsettings.setcpv(pkg_key, mydb=fakedb[myroot])
				fakedb[myroot].aux_update(pkg_key, {"USE":pkgsettings["USE"]})
			self.spinner.update()

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

		if root_config.settings.get("PORTAGE_BINHOST"):
			binhost = root_config.settings.get("PORTAGE_BINHOST")
			self._repo_paths.append(binhost)
			self._repo_paths_real.append(binhost)

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
		self.pkgsettings[self.target_root] = EmergeConfig(settings, setconfig=settings.setconfig)
		if self.target_root != "/":
			self.pkgsettings["/"] = \
				EmergeConfig(trees["/"]["vartree"].settings, setconfig=settings.setconfig)
		self.curval = 0

	def merge(self, mylist, favorites, mtimedb):
		from portage.elog import elog_process
		from portage.elog.filtering import filter_mergephases
		failed_fetches = []
		fetchonly = "--fetchonly" in self.myopts or \
			"--fetch-all-uri" in self.myopts
		pretend = "--pretend" in self.myopts
		mymergelist=[]
		ldpath_mtimes = mtimedb["ldpath"]
		xterm_titles = "notitles" not in self.settings.features

		#check for blocking dependencies
		if "--fetchonly" not in self.myopts and \
			"--fetch-all-uri" not in self.myopts and \
			"--buildpkgonly" not in self.myopts:
			for x in mylist:
				if x[0]=="blocks":
					print "\n!!! Error: the "+x[2]+" package conflicts with another package;"
					print   "!!!        the two packages cannot be installed on the same system together."
					print   "!!!        Please use 'emerge --pretend' to determine blockers."
					if "--quiet" not in self.myopts:
						show_blocker_docs_link()
					return 1

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

		root_config = RootConfig(self.trees[self.target_root])
		system_set = root_config.settings.sets["system"]
		args_set = InternalPackageSet(favorites)
		world_set = root_config.settings.sets["world"]
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
				print ">>> starting parallel fetching"
				fetch_log = EPREFIX+"/var/log/emerge-fetch.log"
				logfile = open(fetch_log, "w")
				fd_pipes = {1:logfile.fileno(), 2:logfile.fileno()}
				portage.util.apply_secpass_permissions(fetch_log,
					uid=portage.portage_uid, gid=portage.portage_gid,
					mode=0660)
				fetch_env = os.environ.copy()
				fetch_env["FEATURES"] = fetch_env.get("FEATURES", "") + " -cvs"
				fetch_env["PORTAGE_NICENESS"] = "0"
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
				portage.process.spawn(fetch_args, env=fetch_env,
					fd_pipes=fd_pipes, returnpid=True)
				logfile.close() # belongs to the spawned process
				del fetch_log, logfile, fd_pipes, fetch_env, fetch_args, \
					resume_opts

		metadata_keys = [k for k in portage.auxdbkeys \
			if not k.startswith("UNUSED_")] + ["USE"]

		mergecount=0
		for x in mymergelist:
			mergecount+=1
			pkg_type = x[0]
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
				metadata["USE"] = pkgsettings["USE"]
			else:
				if pkg_type == "binary":
					mydbapi = bindb
				else:
					raise AssertionError("Package type: '%s'" % pkg_type)
				metadata.update(izip(metadata_keys,
					mydbapi.aux_get(pkg_key, metadata_keys)))
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
						uid=portage.portage_uid, gid=portage.portage_gid,
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
					# Clean the old package that we have merged over top of it.
					if pkgsettings.get("AUTOCLEAN", "yes") == "yes":
						xsplit=portage.pkgsplit(x[2])
						emergelog(xterm_titles, " >>> AUTOCLEAN: " + xsplit[0])
						retval = unmerge(pkgsettings, self.myopts, vartree,
							"clean", [xsplit[0]], ldpath_mtimes, autoclean=1)
						if not retval:
							emergelog(xterm_titles,
								" --- AUTOCLEAN: Nothing unmerged.")
					else:
						portage.writemsg_stdout(colorize("WARN", "WARNING:")
							+ " AUTOCLEAN is disabled.  This can cause serious"
							+ " problems due to overlapping packages.\n")

					# Figure out if we need a restart.
					mysplit=portage.pkgsplit(x[2])
					if mysplit[0] == "sys-apps/portage" and x[1] == "/":
						myver=mysplit[1]+"-"+mysplit[2]
						if myver[-3:]=='-r0':
							myver=myver[:-3]
						if (myver != portage.VERSION) and \
						   "livecvsportage" not in self.settings.features:
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

def unmerge(settings, myopts, vartree, unmerge_action, unmerge_files,
	ldpath_mtimes, autoclean=0):
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
		realsyslist = settings.sets["system"].getAtoms()
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
	
		if not unmerge_files or "world" in unmerge_files or \
			"system" in unmerge_files:
			if "unmerge"==unmerge_action:
				print
				print bold("emerge unmerge") + " can only be used with " + \
					"specific package names, not with "+bold("world")+" or"
				print bold("system")+" targets."
				print
				return 0
			else:
				global_unmerge = 1
	
		localtree = vartree
		# process all arguments and add all
		# valid db entries to candidate_catpkgs
		if global_unmerge:
			if not unmerge_files or "world" in unmerge_files:
				candidate_catpkgs.extend(vartree.dbapi.cp_all())
			elif "system" in unmerge_files:
				candidate_catpkgs.extend(settings.sets["system"].getAtoms())
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
	
		pkgmap={}
		numselected=0
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
			mykey = portage.key_expand(
				portage.dep_getkey(
					mymatch[0]), mydb=vartree.dbapi, settings=settings)
			if not pkgmap.has_key(mykey):
				pkgmap[mykey]={"protected":[], "selected":[], "omitted":[] }
			if unmerge_action=="unmerge":
					for y in mymatch:
						if y not in pkgmap[mykey]["selected"]:
							pkgmap[mykey]["selected"].append(y)
							numselected=numselected+len(mymatch)
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
				pkgmap[mykey]["protected"].append(best_version)
				pkgmap[mykey]["selected"] = [mypkg for mypkg in mymatch \
					if mypkg != best_version]
				numselected = numselected + len(pkgmap[mykey]["selected"])
			else:
				# unmerge_action == "clean"
				slotmap={}
				for mypkg in mymatch:
					if unmerge_action=="clean":
						myslot=localtree.getslot(mypkg)
					else:
						# since we're pruning, we don't care about slots
						# and put all the pkgs in together
						myslot=0
					if not slotmap.has_key(myslot):
						slotmap[myslot]={}
					slotmap[myslot][localtree.dbapi.cpv_counter(mypkg)]=mypkg
				for myslot in slotmap:
					counterkeys=slotmap[myslot].keys()
					counterkeys.sort()
					if not counterkeys:
						continue
					counterkeys.sort()
					pkgmap[mykey]["protected"].append(
						slotmap[myslot][counterkeys[-1]])
					del counterkeys[-1]
					#be pretty and get them in order of merge:
					for ckey in counterkeys:
						pkgmap[mykey]["selected"].append(slotmap[myslot][ckey])
						numselected=numselected+1
					# ok, now the last-merged package
					# is protected, and the rest are selected
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
	for x in pkgmap:
		for y in localtree.dep_match(x):
			if y not in pkgmap[x]["omitted"] and \
			   y not in pkgmap[x]["selected"] and \
			   y not in pkgmap[x]["protected"]:
				pkgmap[x]["omitted"].append(y)
		if global_unmerge and not pkgmap[x]["selected"]:
			#avoid cluttering the preview printout with stuff that isn't getting unmerged
			continue
		if not (pkgmap[x]["protected"] or pkgmap[x]["omitted"]) and (x in syslist):
			print colorize("BAD","\a\n\n!!! '%s' is part of your system profile." % x)
			print colorize("WARN","\a!!! Unmerging it may be damaging to your system.\n")
			if "--pretend" not in myopts and "--ask" not in myopts:
				countdown(int(settings["EMERGE_WARNING_DELAY"]),
					colorize("UNMERGE_WARN", "Press Ctrl-C to Stop"))
		if "--quiet" not in myopts:
			print "\n "+white(x)
		else:
			print white(x)+": ",
		for mytype in ["selected","protected","omitted"]:
			if "--quiet" not in myopts:
				portage.writemsg_stdout((mytype + ": ").rjust(14), noiselevel=-1)
			if pkgmap[x][mytype]:
				sorted_pkgs = [portage.catpkgsplit(mypkg)[1:] \
					for mypkg in pkgmap[x][mytype]]
				sorted_pkgs.sort(portage.pkgcmp)
				for pn, ver, rev in sorted_pkgs:
					if rev == "r0":
						myversion = ver
					else:
						myversion = ver + "-" + rev
					if mytype=="selected":
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

	for x in pkgmap:
		for y in pkgmap[x]["selected"]:
			print ">>> Unmerging "+y+"..."
			emergelog(xterm_titles, "=== Unmerging... ("+y+")")
			mysplit=y.split("/")
			#unmerge...
			retval = portage.unmerge(mysplit[0], mysplit[1], settings["ROOT"],
				mysettings, unmerge_action not in ["clean","prune"],
				vartree=vartree, ldpath_mtimes=ldpath_mtimes)
			if retval != os.EX_OK:
				emergelog(xterm_titles, " !!! unmerge FAILURE: "+y)
				ebuild = vartree.dbapi.findname(y)
				show_unmerge_failure_message(y, ebuild, retval)
				sys.exit(retval)
			else:
				settings.sets["world"].cleanPackage(vartree.dbapi, y)
				emergelog(xterm_titles, " >>> unmerge success: "+y)
	return 1

def show_unmerge_failure_message(pkg, ebuild, retval):

	from formatter import AbstractFormatter, DumbWriter
	f = AbstractFormatter(DumbWriter(sys.stderr, maxcol=72))

	msg = []
	msg.append("A removal phase of the '%s' package " % pkg)
	msg.append("has failed with exit value %s.  " % retval)
	msg.append("The problem occurred while executing ")
	msg.append("the ebuild located at '%s'.  " % ebuild)
	msg.append("If necessary, manually remove the ebuild " )
	msg.append("in order to skip the execution of removal phases.")

	f.end_paragraph(1)
	for x in msg:
		f.add_flowing_data(x)
	f.end_paragraph(1)
	f.writer.flush()

def chk_updated_info_files(root, infodirs, prev_mtimes, retval):

	if os.path.exists(EPREFIX+"/usr/bin/install-info"):
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
			portage.writemsg_stdout(" "+green("*")+" GNU info directory index is up-to-date.\n")
		else:
			portage.writemsg_stdout(" "+green("*")+" Regenerating GNU info directory index...\n")

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
					myso=commands.getstatusoutput("LANG=C LANGUAGE=C "+EPREFIX+"/usr/bin/install-info --dir-file="+inforoot+"/dir "+inforoot+"/"+x)[1]
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

	from portage.util import normalize_path
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
			chk_updated_info_files(target_root + EPREFIX, infodirs, info_mtimes, retval)
		mtimedb.commit()
	finally:
		portage.locks.unlockdir(vdb_lock)

	chk_updated_cfg_files(target_root + EPREFIX, config_protect)
	
	display_news_notification(trees)
	
	if vardbapi.plib_registry.hasEntries():
		print colorize("WARN", "!!!") + " existing preserved libs:"
		plibdata = vardbapi.plib_registry.getPreservedLibs()
		for cpv in plibdata:
			print colorize("WARN", ">>>") + " package: %s" % cpv
			for f in plibdata[cpv]:
				print colorize("WARN", " * ") + " - %s" % f
		print "Use " + colorize("GOOD", "revdep-rebuild") + " to rebuild packages using these libraries"
		print "and then remerge the packages listed above."

	sys.exit(retval)


def chk_updated_cfg_files(target_root, config_protect):
	if config_protect:
		#number of directories with some protect files in them
		procount=0
		for x in config_protect:
			x = os.path.join(target_root, x.lstrip(os.path.sep))
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
					print colorize("WARN", " * IMPORTANT:"),
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

def is_valid_package_atom(x):
	try:
		testkey = portage.dep_getkey(x)
	except portage.exception.InvalidData:
		return False
	if testkey.startswith("null/"):
		testatom = x.replace(testkey[5:], "cat/"+testkey[5:])
	elif "/" not in x:
		testatom = "cat/"+x
	else:
		testatom = x
	return portage.isvalidatom(testatom)

def show_blocker_docs_link():
	print
	print "For more information about " + bad("Blocked Packages") + ", please refer to the following"
	print "section of the Gentoo Linux x86 Handbook (architecture is irrelevant):"
	print
	print "http://www.gentoo.org/doc/en/handbook/handbook-x86.xml?full=1#blocked"
	print

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
		if not os.path.exists(EPREFIX+"/usr/bin/rsync"):
			print "!!! rsync does not exist, so rsync support is disabled."
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
				"--delete-after", # Delete only after everything else is done
				"--stats",        # Show final statistics about what was transfered
				"--timeout="+str(mytimeout), # IO timeout if not done in X seconds
				"--exclude=/distfiles",   # Exclude distfiles from consideration
				"--exclude=/local",       # Exclude local     from consideration
				"--exclude=/packages",    # Exclude packages  from consideration
				"--filter=H_**/files/digest-*", # Exclude manifest1 digests and delete on the receiving side
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

			rsynccommand = [EPREFIX+"/usr/bin/rsync"] + rsync_opts + extra_rsync_opts

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
				break

		if (exitcode==0):
			emergelog(xterm_titles, "=== Sync completed with %s" % dosyncuri)
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
		if not os.path.exists(EPREFIX+"/usr/bin/cvs"):
			print "!!! cvs does not exist, so CVS support is disabled."
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
	elif syncuri[:11]=="svn+http://":
		# this should be way more generic!
		if not os.path.exists(EPREFIX+"/usr/bin/svn"):
			print "!!! svn does not exist, so SVN support is disabled."
			print "!!! Type \"emerge dev-util/subversion\" to enable SVN support."
			sys.exit(1)
		svndir=os.path.dirname(myportdir)
		if not os.path.exists(myportdir+"/.svn"):
			#initial checkout
			print ">>> Starting initial svn checkout with "+syncuri+"..."
			if os.path.exists(svndir+"/prefix-overlay"):
				print "!!! existing",svndir+"/prefix-overlay directory; exiting."
				sys.exit(1)
			try:
				os.rmdir(myportdir)
			except OSError, e:
				if e.errno != errno.ENOENT:
					sys.stderr.write(
						"!!! existing '%s' directory; exiting.\n" % myportdir)
					sys.exit(1)
				del e
			if portage.spawn("cd "+svndir+"; svn checkout "+syncuri[4:],settings,free=1):
				print "!!! svn checkout error; exiting."
				sys.exit(1)
			os.rename(os.path.join(svndir, "prefix-overlay"), myportdir)
		else:
			#svn update
			print ">>> Starting svn update..."
			retval = portage.spawn("cd '%s'; svn update" % myportdir, \
				settings, free=1)
			if retval != os.EX_OK:
				sys.exit(retval)

		# write timestamp.chk
		try:
			if not os.path.exists(os.path.join(myportdir, "metadata")):
				os.mkdir(os.path.join(myportdir, "metadata"))
			f = open(os.path.join(myportdir, "metadata", "timestamp.chk"), 'w')
			f.write(time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime()))
			f.write('\n')
			f.close()
		except IOError, e:
			# too bad, next time better luck!
			pass

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

	chk_updated_cfg_files(EPREFIX, settings.get("CONFIG_PROTECT","").split())

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
	print "Regenerating cache entries... "
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
			print "\n  error listing cache entries for " + \
				"'%s': %s, continuing..." % (mytree, e)
			del e
			dead_nodes = None
			break
	for x in mynodes:
		mymatches = portdb.cp_list(x)
		portage.writemsg_stdout("processing %s\n" % x)
		for y in mymatches:
			try:
				foo = portdb.aux_get(y,["DEPEND"])
			except SystemExit, e:
				# sys.exit is an exception... And consequently, we can't catch it.
				raise
			except Exception, e:
				print "\n  error processing %(cpv)s, continuing... (%(e)s)" % {"cpv":y,"e":str(e)}
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
	print "done!"

def action_config(settings, trees, myopts, myfiles):
	if len(myfiles) != 1 or "system" in myfiles or "world" in myfiles:
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
	portage.doebuild(ebuildpath, "config", settings["ROOT"], mysettings,
		debug=(settings.get("PORTAGE_DEBUG", "") == 1), cleanup=True,
		mydbapi=trees[settings["ROOT"]]["vartree"].dbapi, tree="vartree")
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
		          'ACCEPT_KEYWORDS', 'SYNC', 'FEATURES', 'EMERGE_DEFAULT_OPTS',
		          'EPREFIX']

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
		mydesiredvars = [ 'CHOST', 'CFLAGS', 'CXXFLAGS', 'EPREFIX' ]
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
			if valuesmap["IUSE"].intersection(pkgsettings["USE"].split()) != \
				valuesmap["USE"]:
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

def action_search(settings, portdb, vartree, myopts, myfiles, spinner):
	if not myfiles:
		print "emerge: no search terms provided."
	else:
		searchinstance = search(settings, portdb,
			vartree, spinner, "--searchdesc" in myopts,
			"--quiet" not in myopts)
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
	dep_check_trees = {}
	dep_check_trees[myroot] = {}
	dep_check_trees[myroot]["vartree"] = \
		FakeVartree(trees[myroot]["vartree"],
		trees[myroot]["porttree"].dbapi,
		depgraph._mydbapi_keys)
	vardb = dep_check_trees[myroot]["vartree"].dbapi
	# Constrain dependency selection to the installed packages.
	dep_check_trees[myroot]["porttree"] = dep_check_trees[myroot]["vartree"]
	system_set = SystemSet(settings.profiles)
	syslist = list(system_set)
	world_set = WorldSet(myroot)
	worldlist = list(world_set)
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

	soft = 0
	hard = 1
	remaining_atoms = []
	if action == "depclean":
		for atom in worldlist:
			if vardb.match(atom):
				remaining_atoms.append((atom, 'world', hard))
		for atom in syslist:
			if vardb.match(atom):
				remaining_atoms.append((atom, 'system', hard))
	elif action == "prune":
		for atom in syslist:
			if vardb.match(atom):
				remaining_atoms.append((atom, 'system', hard))
		# Pull in everything that's installed since we don't want to prune a
		# package if something depends on it.
		remaining_atoms.extend((atom, 'world', hard) for atom in vardb.cp_all())
		if not myfiles:
			# Try to prune everything that's slotted.
			for cp in vardb.cp_all():
				if len(vardb.cp_list(cp)) > 1:
					args_set.add(cp)

	unresolveable = {}
	aux_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
	metadata_keys = ["PROVIDE", "SLOT", "USE"]
	graph = digraph()

	while remaining_atoms:
		atom, parent, priority = remaining_atoms.pop()
		pkgs = vardb.match(atom)
		if not pkgs:
			if not atom.startswith("!") and priority == hard:
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
					file_path = os.path.join(myroot, VDB_PATH, pkg, "PROVIDE")
					portage.writemsg("\n\nInvalid PROVIDE: %s\n" % str(s),
						noiselevel=-1)
					portage.writemsg("See '%s'\n" % file_path,
						noiselevel=-1)
					del e
				if not arg_atom:
					filtered_pkgs.append(pkg)
			pkgs = filtered_pkgs
		prune_this = False
		if action == "prune":
			for pkg in pkgs:
				metadata = dict(izip(metadata_keys,
					vardb.aux_get(pkg, metadata_keys)))
				try:
					arg_atom = args_set.findAtomForPackage(pkg, metadata)
				except portage.exception.InvalidDependString, e:
					file_path = os.path.join(myroot, VDB_PATH, pkg, "PROVIDE")
					portage.writemsg("\n\nInvalid PROVIDE: %s\n" % str(s),
						noiselevel=-1)
					portage.writemsg("See '%s'\n" % file_path,
						noiselevel=-1)
					del e
					continue
				if arg_atom:
					prune_this = True
					break
		if len(pkgs) > 1 and (parent != "world" or prune_this):
			# Prune all but the best matching slot, since that's all that a
			# deep world update would pull in.  Don't prune if this atom comes
			# directly from world though, since world atoms are greedy when
			# they don't specify a slot.
			visible_in_portdb = [cpv for cpv in pkgs if portdb.match("="+cpv)]
			if visible_in_portdb:
				# For consistency with the update algorithm, keep the highest
				# visible version and prune any versions that are either masked
				# or no longer exist in the portage tree.
				pkgs = visible_in_portdb
			pkgs = [portage.best(pkgs)]
		for pkg in pkgs:
			graph.add(pkg, parent)
			if fakedb.cpv_exists(pkg):
				continue
			spinner.update()
			fakedb.cpv_inject(pkg)
			myaux = dict(izip(aux_keys, vardb.aux_get(pkg, aux_keys)))
			mydeps = []
			if myopts.get("--with-bdeps", "y") == "y":
				mydeps.append((myaux["DEPEND"], soft))
			del myaux["DEPEND"]
			mydeps.append((" ".join(myaux.values()), hard))
			usedef = vardb.aux_get(pkg, ["USE"])[0].split()
			for depstr, priority in mydeps:

				if not depstr:
					continue

				if "--debug" in myopts:
					print
					print "Parent:   ", pkg
					print "Depstring:", depstr
					print "Priority:",
					if priority == soft:
						print "soft"
					else:
						print "hard"

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
					remaining_atoms.append((atom, pkg, priority))

	if "--quiet" not in myopts:
		print "\b\b... done!\n"

	if unresolveable:
		print "Dependencies could not be completely resolved due to"
		print "the following required packages not being installed:"
		print
		for atom in unresolveable:
			print atom, "required by", " ".join(unresolveable[atom])
	if unresolveable:
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
		unmerge(settings, myopts, trees[settings["ROOT"]]["vartree"],
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
	pretend = "--pretend" in myopts
	fetchonly = "--fetchonly" in myopts or "--fetch-all-uri" in myopts
	if pretend or fetchonly:
		# make the mtimedb readonly
		mtimedb.filename = None
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
			return 1
		if show_spinner:
			print "\b\b... done!"
	else:
		if ("--resume" in myopts):
			print darkgreen("emerge: It seems we have nothing to resume...")
			return os.EX_OK

		myparams = create_depgraph_params(myopts, myaction)
		if myaction in ["system","world"]:
			if "--quiet" not in myopts and "--nodeps" not in myopts:
				print "Calculating",myaction,"dependencies  ",
				sys.stdout.flush()
			mydepgraph = depgraph(settings, trees, myopts, myparams, spinner)
			if not mydepgraph.xcreate(myaction):
				print "!!! Depgraph creation failed."
				return 1
			if "--quiet" not in myopts and "--nodeps" not in myopts:
				print "\b\b... done!"
		else:
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
				return 1
			if "--quiet" not in myopts and "--nodeps" not in myopts:
				print "\b\b... done!"

			if ("--usepkgonly" in myopts) and mydepgraph.missingbins:
				sys.stderr.write(red("The following binaries are not available for merging...\n"))

		if mydepgraph.missingbins:
			for x in mydepgraph.missingbins:
				sys.stderr.write("   "+str(x)+"\n")
			sys.stderr.write("\nThese are required by '--usepkgonly' -- Terminating.\n\n")
			return 1

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
			if "--buildpkgonly" in myopts and \
				not mydepgraph.digraph.hasallzeros(ignore_priority=DepPriority.MEDIUM):
					print "\n!!! --buildpkgonly requires all dependencies to be merged."
					print "!!! You have to merge the dependencies before you can build this package.\n"
					return 1
	else:
		if ("--buildpkgonly" in myopts):
			if not mydepgraph.digraph.hasallzeros(ignore_priority=DepPriority.MEDIUM):
				print "\n!!! --buildpkgonly requires all dependencies to be merged."
				print "!!! Cannot merge requested packages. Merge deps and try again.\n"
				return 1

		if ("--resume" in myopts):
			favorites=mtimedb["resume"]["favorites"]
			mergetask = MergeTask(settings, trees, myopts)
			if "--fetchonly" in myopts:
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
			if "--fetchonly" in myopts or "--fetch-all-uri" in myopts:
				pkglist = []
				for pkg in mydepgraph.altlist():
					if pkg[0] != "blocks":
						pkglist.append(pkg)
			else:
				pkglist = mydepgraph.altlist()
			if favorites:
				mydepgraph.saveNomergeFavorites()
			del mydepgraph
			mergetask = MergeTask(settings, trees, myopts)
			retval = mergetask.merge(pkglist, favorites, mtimedb)
			merge_count = mergetask.curval

		if retval == os.EX_OK and not (pretend or fetchonly):
			mtimedb.pop("resume", None)
			if "yes" == settings.get("AUTOCLEAN"):
				portage.writemsg_stdout(">>> Auto-cleaning packages...\n")
				vartree = trees[settings["ROOT"]]["vartree"]
				unmerge(settings, myopts, vartree, "clean", ["world"],
					ldpath_mtimes, autoclean=1)
			else:
				portage.writemsg_stdout(colorize("WARN", "WARNING:")
					+ " AUTOCLEAN is disabled.  This can cause serious"
					+ " problems due to overlapping packages.\n")

		if merge_count and not (pretend or fetchonly):
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
			if not silent and x not in ["system", "world"]:
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
		mysettings = trees[myroot]["vartree"].settings
		for var in "ARCH", "USERLAND":
			if mysettings.get(var):
				continue
			print >> sys.stderr, bad(("\a!!! %s is not set... " % var) + \
				"Are you missing the '%setc/make.profile' symlink?" % \
				mysettings["PORTAGE_CONFIGROOT"])
			print >> sys.stderr, bad("\a!!! Is the symlink correct? " + \
				"Is your portage tree complete?\n")
			sys.exit(9)
		del myroot, mysettings

def load_emerge_config(trees=None):
	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		kwargs[k] = os.environ.get(envvar, None)
	trees = portage.create_trees(trees=trees, **kwargs)

	settings = trees["/"]["vartree"].settings

	for myroot in trees:
		if myroot != "/":
			settings = trees[myroot]["vartree"].settings
			break
	
	settings = EmergeConfig(settings, trees=trees[settings["ROOT"]])

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

	#Freeze the portdbapi for enhanced performance:
	for myroot in trees:
		trees[myroot]["porttree"].dbapi.freeze()
		del myroot

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

	if (myaction in ["world", "system"]) and myfiles:
		print "emerge: please specify a package class (\"world\" or \"system\") or individual packages, but not both."
		sys.exit(1)

	for x in myfiles:
		ext = os.path.splitext(x)[1]
		if (ext == ".ebuild" or ext == ".tbz2") and os.path.exists(os.path.abspath(x)):
			print colorize("BAD", "\n*** emerging by path is broken and may not always work!!!\n")
			break

	# only expand sets for actions taking package arguments
	if myaction not in ["search", "metadata", "sync"]:
		oldargs = myfiles[:]
		for s in settings.sets:
			if s in myfiles:
				# TODO: check if the current setname also resolves to a package name
				if myaction in ["unmerge", "prune", "clean", "depclean"] and not packagesets[s].supportsOperation("unmerge"):
					print "emerge: the given set %s does not support unmerge operations" % s
					sys.exit(1)
				if not settings.sets[s].getAtoms():
					print "emerge: '%s' is an empty set" % s
				else:
					myfiles.extend(settings.sets[s].getAtoms())
				for e in settings.sets[s].errors:
					print e
				myfiles.remove(s)
		# Need to handle empty sets specially, otherwise emerge will react 
		# with the help message for empty argument lists
		if oldargs and not myfiles:
			print "emerge: no targets left after set expansion"
			sys.exit(0)
		del oldargs

	if ("--tree" in myopts) and ("--columns" in myopts):
		print "emerge: can't specify both of \"--tree\" and \"--columns\"."
		sys.exit(1)

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
		sys.exit(1)

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
		sys.exit(0)
	elif "--help" in myopts:
		_emerge.help.help(myaction, myopts, portage.output.havecolor)
		sys.exit(0)

	if "--debug" in myopts:
		print "myaction", myaction
		print "myopts", myopts

	if not myaction and not myfiles and "--resume" not in myopts:
		_emerge.help.help(myaction, myopts, portage.output.havecolor)
		sys.exit(1)

	# check if root user is the current user for the actions where emerge needs this
	if portage.secpass < 2:
		# We've already allowed "--version" and "--help" above.
		if "--pretend" not in myopts and myaction not in ("search","info"):
			need_superuser = not \
				("--fetchonly" in myopts or \
				"--fetch-all-uri" in myopts or \
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
			myelogstr+=" "+" ".join(myfiles)
		emergelog(xterm_titles, " *** emerge " + myelogstr)

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
		action_search(settings, portdb, trees["/"]["vartree"],
			myopts, myfiles, spinner)
	elif myaction in ("clean", "unmerge") or \
		(myaction == "prune" and "--nodeps" in myopts):
		validate_ebuild_environment(trees)
		vartree = trees[settings["ROOT"]]["vartree"]
		if 1 == unmerge(settings, myopts, vartree, myaction, myfiles,
			mtimedb["ldpath"]):
			if "--pretend" not in myopts:
				post_emerge(trees, mtimedb, os.EX_OK)

	elif myaction in ("depclean", "prune"):
		validate_ebuild_environment(trees)
		action_depclean(settings, trees, mtimedb["ldpath"],
			myopts, myaction, myfiles, spinner)
		if "--pretend" not in myopts:
			post_emerge(trees, mtimedb, os.EX_OK)
	# "update", "system", or just process files:
	else:
		validate_ebuild_environment(trees)
		if "--pretend" not in myopts:
			display_news_notification(trees)
		retval = action_build(settings, trees, mtimedb,
			myopts, myaction, myfiles, spinner)
		if "--pretend" not in myopts:
			display_news_notification(trees)
		return retval

if __name__ == "__main__":
	retval = emerge_main()
	sys.exit(retval)
