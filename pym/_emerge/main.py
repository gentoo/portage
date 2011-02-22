# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import logging
import signal
import stat
import sys
import textwrap
import platform
try:
	from subprocess import getstatusoutput as subprocess_getstatusoutput
except ImportError:
	from commands import getstatusoutput as subprocess_getstatusoutput
import portage
from portage import os
from portage import _encodings
from portage import _unicode_decode
import _emerge.help
import portage.xpak, errno, re, time
from portage.output import colorize, xtermTitle, xtermTitleReset
from portage.output import create_color_func
good = create_color_func("GOOD")
bad = create_color_func("BAD")

from portage.const import _ENABLE_DYN_LINK_MAP
import portage.elog
import portage.util
import portage.locks
import portage.exception
from portage.data import secpass
from portage.dbapi.dep_expand import dep_expand
from portage.util import normalize_path as normpath
from portage.util import shlex_split, writemsg_level, writemsg_stdout
from portage._sets import SETPREFIX
from portage._global_updates import _global_updates

from _emerge.actions import action_config, action_sync, action_metadata, \
	action_regen, action_search, action_uninstall, action_info, action_build, \
	adjust_configs, chk_updated_cfg_files, display_missing_pkg_set, \
	display_news_notification, getportageversion, load_emerge_config
import _emerge
from _emerge.emergelog import emergelog
from _emerge._flush_elog_mod_echo import _flush_elog_mod_echo
from _emerge.is_valid_package_atom import is_valid_package_atom
from _emerge.stdout_spinner import stdout_spinner

if sys.hexversion >= 0x3000000:
	long = int

options=[
"--ask",          "--alphabetical",
"--ask-enter-invalid",
"--buildpkgonly",
"--changed-use",
"--changelog",    "--columns",
"--debug",
"--digest",
"--emptytree",
"--fetchonly",    "--fetch-all-uri",
"--ignore-default-opts",
"--noconfmem",
"--newuse",
"--nodeps",       "--noreplace",
"--nospinner",    "--oneshot",
"--onlydeps",     "--pretend",
"--quiet",
"--quiet-build",
"--quiet-unmerge-warn",
"--resume",
"--searchdesc",
"--skipfirst",
"--tree",
"--unordered-display",
"--update",
"--verbose",
]

shortmapping={
"1":"--oneshot",
"a":"--ask",
"B":"--buildpkgonly",
"c":"--depclean",
"C":"--unmerge",
"d":"--debug",
"e":"--emptytree",
"f":"--fetchonly", "F":"--fetch-all-uri",
"h":"--help",
"l":"--changelog",
"n":"--noreplace", "N":"--newuse",
"o":"--onlydeps",  "O":"--nodeps",
"p":"--pretend",   "P":"--prune",
"q":"--quiet",
"r":"--resume",
"s":"--search",    "S":"--searchdesc",
"t":"--tree",
"u":"--update",
"v":"--verbose",   "V":"--version"
}

def chk_updated_info_files(root, infodirs, prev_mtimes, retval):

	if os.path.exists("/usr/bin/install-info"):
		out = portage.output.EOutput()
		regen_infodirs=[]
		for z in infodirs:
			if z=='':
				continue
			inforoot=normpath(root+z)
			if os.path.isdir(inforoot) and \
				not [x for x in os.listdir(inforoot) \
				if x.startswith('.keepinfodir')]:
					infomtime = os.stat(inforoot)[stat.ST_MTIME]
					if inforoot not in prev_mtimes or \
						prev_mtimes[inforoot] != infomtime:
							regen_infodirs.append(inforoot)

		if not regen_infodirs:
			portage.writemsg_stdout("\n")
			out.einfo("GNU info directory index is up-to-date.")
		else:
			portage.writemsg_stdout("\n")
			out.einfo("Regenerating GNU info directory index...")

			dir_extensions = ("", ".gz", ".bz2")
			icount=0
			badcount=0
			errmsg = ""
			for inforoot in regen_infodirs:
				if inforoot=='':
					continue

				if not os.path.isdir(inforoot) or \
					not os.access(inforoot, os.W_OK):
					continue

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
							except EnvironmentError as e:
								if e.errno != errno.ENOENT:
									raise
								del e
					processed_count += 1
					myso=subprocess_getstatusoutput("LANG=C LANGUAGE=C /usr/bin/install-info --dir-file="+inforoot+"/dir "+inforoot+"/"+x)[1]
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
						except EnvironmentError as e:
							if e.errno != errno.ENOENT:
								raise
							del e

				# Clean dir.old cruft so that they don't prevent
				# unmerge of otherwise empty directories.
				for ext in dir_extensions:
					try:
						os.unlink(dir_file + ext + ".old")
					except EnvironmentError as e:
						if e.errno != errno.ENOENT:
							raise
						del e

				#update mtime so we can potentially avoid regenerating.
				prev_mtimes[inforoot] = os.stat(inforoot)[stat.ST_MTIME]

			if badcount:
				out.eerror("Processed %d info files; %d errors." % \
					(icount, badcount))
				writemsg_level(errmsg, level=logging.ERROR, noiselevel=-1)
			else:
				if icount > 0:
					out.einfo("Processed %d info files." % (icount,))

def display_preserved_libs(vardbapi, myopts):
	MAX_DISPLAY = 3

	if vardbapi._linkmap is None or \
		vardbapi._plib_registry is None:
		# preserve-libs is entirely disabled
		return

	# Ensure the registry is consistent with existing files.
	vardbapi._plib_registry.pruneNonExisting()

	if vardbapi._plib_registry.hasEntries():
		if "--quiet" in myopts:
			print()
			print(colorize("WARN", "!!!") + " existing preserved libs found")
			return
		else:
			print()
			print(colorize("WARN", "!!!") + " existing preserved libs:")

		plibdata = vardbapi._plib_registry.getPreservedLibs()
		linkmap = vardbapi._linkmap
		consumer_map = {}
		owners = {}
		linkmap_broken = False

		try:
			linkmap.rebuild()
		except portage.exception.CommandNotFound as e:
			writemsg_level("!!! Command Not Found: %s\n" % (e,),
				level=logging.ERROR, noiselevel=-1)
			del e
			linkmap_broken = True
		else:
			search_for_owners = set()
			for cpv in plibdata:
				internal_plib_keys = set(linkmap._obj_key(f) \
					for f in plibdata[cpv])
				for f in plibdata[cpv]:
					if f in consumer_map:
						continue
					consumers = []
					for c in linkmap.findConsumers(f):
						# Filter out any consumers that are also preserved libs
						# belonging to the same package as the provider.
						if linkmap._obj_key(c) not in internal_plib_keys:
							consumers.append(c)
					consumers.sort()
					consumer_map[f] = consumers
					search_for_owners.update(consumers[:MAX_DISPLAY+1])

			owners = vardbapi._owners.getFileOwnerMap(search_for_owners)

		for cpv in plibdata:
			print(colorize("WARN", ">>>") + " package: %s" % cpv)
			samefile_map = {}
			for f in plibdata[cpv]:
				obj_key = linkmap._obj_key(f)
				alt_paths = samefile_map.get(obj_key)
				if alt_paths is None:
					alt_paths = set()
					samefile_map[obj_key] = alt_paths
				alt_paths.add(f)

			for alt_paths in samefile_map.values():
				alt_paths = sorted(alt_paths)
				for p in alt_paths:
					print(colorize("WARN", " * ") + " - %s" % (p,))
				f = alt_paths[0]
				consumers = consumer_map.get(f, [])
				for c in consumers[:MAX_DISPLAY]:
					print(colorize("WARN", " * ") + "     used by %s (%s)" % \
						(c, ", ".join(x.mycpv for x in owners.get(c, []))))
				if len(consumers) == MAX_DISPLAY + 1:
					print(colorize("WARN", " * ") + "     used by %s (%s)" % \
						(consumers[MAX_DISPLAY], ", ".join(x.mycpv \
						for x in owners.get(consumers[MAX_DISPLAY], []))))
				elif len(consumers) > MAX_DISPLAY:
					print(colorize("WARN", " * ") + "     used by %d other files" % (len(consumers) - MAX_DISPLAY))
		print("Use " + colorize("GOOD", "emerge @preserved-rebuild") + " to rebuild packages using these libraries")

def post_emerge(myaction, myopts, myfiles,
	target_root, trees, mtimedb, retval):
	"""
	Misc. things to run at the end of a merge session.

	Update Info Files
	Update Config Files
	Update News Items
	Commit mtimeDB
	Display preserved libs warnings
	Exit Emerge

	@param myaction: The action returned from parse_opts()
	@type myaction: String
	@param myopts: emerge options
	@type myopts: dict
	@param myfiles: emerge arguments
	@type myfiles: list
	@param target_root: The target ROOT for myaction
	@type target_root: String
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

	root_config = trees[target_root]["root_config"]
	vardbapi = trees[target_root]["vartree"].dbapi
	settings = vardbapi.settings
	info_mtimes = mtimedb["info"]

	# Load the most current variables from ${ROOT}/etc/profile.env
	settings.unlock()
	settings.reload()
	settings.regenerate()
	settings.lock()

	config_protect = shlex_split(settings.get("CONFIG_PROTECT", ""))
	infodirs = settings.get("INFOPATH","").split(":") + \
		settings.get("INFODIR","").split(":")

	os.chdir("/")

	if retval == os.EX_OK:
		exit_msg = " *** exiting successfully."
	else:
		exit_msg = " *** exiting unsuccessfully with status '%s'." % retval
	emergelog("notitles" not in settings.features, exit_msg)

	_flush_elog_mod_echo()

	if not vardbapi._pkgs_changed:
		display_news_notification(root_config, myopts)
		# If vdb state has not changed then there's nothing else to do.
		sys.exit(retval)

	vdb_path = os.path.join(root_config.settings['EROOT'], portage.VDB_PATH)
	portage.util.ensure_dirs(vdb_path)
	vdb_lock = None
	if os.access(vdb_path, os.W_OK) and not "--pretend" in myopts:
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

	chk_updated_cfg_files(settings['EROOT'], config_protect)

	display_news_notification(root_config, myopts)
	if retval in (None, os.EX_OK) or (not "--pretend" in myopts):
		display_preserved_libs(vardbapi, myopts)	

	postemerge = os.path.join(settings["PORTAGE_CONFIGROOT"],
		portage.USER_CONFIG_PATH, "bin", "post_emerge")
	if os.access(postemerge, os.X_OK):
		hook_retval = portage.process.spawn(
						[postemerge], env=settings.environ())
		if hook_retval != os.EX_OK:
			writemsg_level(
				" %s spawn failed of %s\n" % (bad("*"), postemerge,),
				level=logging.ERROR, noiselevel=-1)

	if "--quiet" not in myopts and \
		myaction is None and "@world" in myfiles:
		show_depclean_suggestion()

	sys.exit(retval)

def show_depclean_suggestion():
	out = portage.output.EOutput()
	msg = "After world updates, it is important to remove " + \
		"obsolete packages with emerge --depclean. Refer " + \
		"to `man emerge` for more information."
	for line in textwrap.wrap(msg, 72):
		out.ewarn(line)

def multiple_actions(action1, action2):
	sys.stderr.write("\n!!! Multiple actions requested... Please choose one only.\n")
	sys.stderr.write("!!! '%s' or '%s'\n\n" % (action1, action2))
	sys.exit(1)

def insert_optional_args(args):
	"""
	Parse optional arguments and insert a value if one has
	not been provided. This is done before feeding the args
	to the optparse parser since that parser does not support
	this feature natively.
	"""

	class valid_integers(object):
		def __contains__(self, s):
			try:
				return int(s) >= 0
			except (ValueError, OverflowError):
				return False

	valid_integers = valid_integers()
	y_or_n = ('y', 'n',)

	new_args = []

	default_arg_opts = {
		'--autounmask'           : y_or_n,
		'--buildpkg'             : y_or_n,
		'--complete-graph'       : y_or_n,
		'--deep'       : valid_integers,
		'--deselect'             : y_or_n,
		'--binpkg-respect-use'   : y_or_n,
		'--fail-clean'           : y_or_n,
		'--getbinpkg'            : y_or_n,
		'--getbinpkgonly'        : y_or_n,
		'--jobs'       : valid_integers,
		'--keep-going'           : y_or_n,
		'--package-moves'        : y_or_n,
		'--rebuilt-binaries'     : y_or_n,
		'--root-deps'  : ('rdeps',),
		'--select'               : y_or_n,
		'--selective'            : y_or_n,
		"--use-ebuild-visibility": y_or_n,
		'--usepkg'               : y_or_n,
		'--usepkgonly'           : y_or_n,
	}

	if _ENABLE_DYN_LINK_MAP:
		default_arg_opts['--depclean-lib-check'] = y_or_n

	short_arg_opts = {
		'D' : valid_integers,
		'j' : valid_integers,
	}

	# Don't make things like "-kn" expand to "-k n"
	# since existence of -n makes it too ambiguous.
	short_arg_opts_n = {
		'b' : y_or_n,
		'g' : y_or_n,
		'G' : y_or_n,
		'k' : y_or_n,
		'K' : y_or_n,
	}

	arg_stack = args[:]
	arg_stack.reverse()
	while arg_stack:
		arg = arg_stack.pop()

		default_arg_choices = default_arg_opts.get(arg)
		if default_arg_choices is not None:
			new_args.append(arg)
			if arg_stack and arg_stack[-1] in default_arg_choices:
				new_args.append(arg_stack.pop())
			else:
				# insert default argument
				new_args.append('True')
			continue

		if arg[:1] != "-" or arg[:2] == "--":
			new_args.append(arg)
			continue

		match = None
		for k, arg_choices in short_arg_opts.items():
			if k in arg:
				match = k
				break

		if match is None:
			for k, arg_choices in short_arg_opts_n.items():
				if k in arg:
					match = k
					break

		if match is None:
			new_args.append(arg)
			continue

		if len(arg) == 2:
			new_args.append(arg)
			if arg_stack and arg_stack[-1] in arg_choices:
				new_args.append(arg_stack.pop())
			else:
				# insert default argument
				new_args.append('True')
			continue

		# Insert an empty placeholder in order to
		# satisfy the requirements of optparse.

		new_args.append("-" + match)
		opt_arg = None
		saved_opts = None

		if arg[1:2] == match:
			if match not in short_arg_opts_n and arg[2:] in arg_choices:
				opt_arg = arg[2:]
			else:
				saved_opts = arg[2:]
				opt_arg = "True"
		else:
			saved_opts = arg[1:].replace(match, "")
			opt_arg = "True"

		if opt_arg is None and arg_stack and \
			arg_stack[-1] in arg_choices:
			opt_arg = arg_stack.pop()

		if opt_arg is None:
			new_args.append("True")
		else:
			new_args.append(opt_arg)

		if saved_opts is not None:
			# Recycle these on arg_stack since they
			# might contain another match.
			arg_stack.append("-" + saved_opts)

	return new_args

def parse_opts(tmpcmdline, silent=False):
	myaction=None
	myopts = {}
	myfiles=[]

	global options, shortmapping

	actions = frozenset([
		"clean", "config", "depclean", "help",
		"info", "list-sets", "metadata",
		"prune", "regen",  "search",
		"sync",  "unmerge", "version",
	])

	longopt_aliases = {"--cols":"--columns", "--skip-first":"--skipfirst"}
	true_y_or_n = ("True", "y", "n")
	true_y = ("True", "y")
	argument_options = {

		"--autounmask": {
			"help"    : "automatically unmask packages",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--accept-properties": {
			"help":"temporarily override ACCEPT_PROPERTIES",
			"action":"store"
		},

		"--backtrack": {

			"help"   : "Specifies how many times to backtrack if dependency " + \
				"calculation fails ",

			"action" : "store"
		},

		"--buildpkg": {
			"shortopt" : "-b",
			"help"     : "build binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--config-root": {
			"help":"specify the location for portage configuration files",
			"action":"store"
		},
		"--color": {
			"help":"enable or disable color output",
			"type":"choice",
			"choices":("y", "n")
		},

		"--complete-graph": {
			"help"    : "completely account for all known dependencies",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--deep": {

			"shortopt" : "-D",

			"help"   : "Specifies how deep to recurse into dependencies " + \
				"of packages given as arguments. If no argument is given, " + \
				"depth is unlimited. Default behavior is to skip " + \
				"dependencies of installed packages.",

			"action" : "store"
		},

		"--deselect": {
			"help"    : "remove atoms/sets from the world file",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--exclude": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge won't  install any ebuild or binary package that " + \
				"matches any of the given package atoms.",

			"action" : "append"
		},

		"--fail-clean": {
			"help"    : "clean temp files after build failure",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--jobs": {

			"shortopt" : "-j",

			"help"   : "Specifies the number of packages to build " + \
				"simultaneously.",

			"action" : "store"
		},

		"--keep-going": {
			"help"    : "continue as much as possible after an error",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--load-average": {

			"help"   :"Specifies that no new builds should be started " + \
				"if there are other builds running and the load average " + \
				"is at least LOAD (a floating-point number).",

			"action" : "store"
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
		},

		"--binpkg-respect-use": {
			"help"    : "discard binary packages if their use flags \
				don't match the current configuration",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--getbinpkg": {
			"shortopt" : "-g",
			"help"     : "fetch binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--getbinpkgonly": {
			"shortopt" : "-G",
			"help"     : "fetch binary packages only",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--package-moves": {
			"help"     : "perform package moves when necessary",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--rebuilt-binaries": {
			"help"     : "replace installed packages with binary " + \
			             "packages that have been rebuilt",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},
		
		"--rebuilt-binaries-timestamp": {
			"help"   : "use only binaries that are newer than this " + \
			           "timestamp for --rebuilt-binaries",
			"action" : "store"
		},

		"--root": {
		 "help"   : "specify the target root filesystem for merging packages",
		 "action" : "store"
		},

		"--root-deps": {
			"help"    : "modify interpretation of depedencies",
			"type"    : "choice",
			"choices" :("True", "rdeps")
		},

		"--select": {
			"help"    : "add specified packages to the world set " + \
			            "(inverse of --oneshot)",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--selective": {
			"help"    : "similar to the --noreplace but does not take " + \
			            "precedence over options such as --newuse",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--use-ebuild-visibility": {
			"help"     : "use unbuilt ebuild metadata for visibility checks on built packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--usepkg": {
			"shortopt" : "-k",
			"help"     : "use binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--usepkgonly": {
			"shortopt" : "-K",
			"help"     : "use only binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

	}

	if _ENABLE_DYN_LINK_MAP:
		argument_options["--depclean-lib-check"] = {
			"help"    : "check for consumers of libraries before removing them",
			"type"    : "choice",
			"choices" : true_y_or_n
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
	for shortopt, longopt in shortmapping.items():
		parser.add_option("-" + shortopt, action="store_true",
			dest=longopt.lstrip("--").replace("-", "_"), default=False)
	for myalias, myopt in longopt_aliases.items():
		parser.add_option(myalias, action="store_true",
			dest=myopt.lstrip("--").replace("-", "_"), default=False)

	for myopt, kwargs in argument_options.items():
		shortopt = kwargs.pop("shortopt", None)
		args = [myopt]
		if shortopt is not None:
			args.append(shortopt)
		parser.add_option(dest=myopt.lstrip("--").replace("-", "_"),
			*args, **kwargs)

	tmpcmdline = insert_optional_args(tmpcmdline)

	myoptions, myargs = parser.parse_args(args=tmpcmdline)

	if myoptions.autounmask in true_y:
		myoptions.autounmask = True

	if myoptions.buildpkg in true_y:
		myoptions.buildpkg = True
	else:
		myoptions.buildpkg = None

	if myoptions.changed_use is not False:
		myoptions.reinstall = "changed-use"
		myoptions.changed_use = False

	if myoptions.deselect in true_y:
		myoptions.deselect = True

	if myoptions.binpkg_respect_use in true_y:
		myoptions.binpkg_respect_use = True
	else:
		myoptions.binpkg_respect_use = None

	if myoptions.complete_graph in true_y:
		myoptions.complete_graph = True
	else:
		myoptions.complete_graph = None

	if _ENABLE_DYN_LINK_MAP:
		if myoptions.depclean_lib_check in true_y:
			myoptions.depclean_lib_check = True

	if myoptions.exclude:
		exclude = []
		bad_atoms = []
		for x in ' '.join(myoptions.exclude).split():
			bad_atom = False
			try:
				atom = portage.dep.Atom(x, allow_wildcard=True)
			except portage.exception.InvalidAtom:
				try:
					atom = portage.dep.Atom("*/"+x, allow_wildcard=True)
				except portage.exception.InvalidAtom:
					bad_atom = True
			
			if bad_atom:
				bad_atoms.append(x)
			else:
				if atom.operator or atom.blocker or atom.use:
					bad_atoms.append(x)
				else:
					exclude.append(atom)

		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --exclude parameter: '%s' (only package names and slot atoms (with wildcards) allowed)\n" % \
				(",".join(bad_atoms),))

	if myoptions.fail_clean in true_y:
		myoptions.fail_clean = True

	if myoptions.getbinpkg in true_y:
		myoptions.getbinpkg = True
	else:
		myoptions.getbinpkg = None

	if myoptions.getbinpkgonly in true_y:
		myoptions.getbinpkgonly = True
	else:
		myoptions.getbinpkgonly = None

	if myoptions.keep_going in true_y:
		myoptions.keep_going = True
	else:
		myoptions.keep_going = None

	if myoptions.package_moves in true_y:
		myoptions.package_moves = True

	if myoptions.rebuilt_binaries in true_y:
		myoptions.rebuilt_binaries = True

	if myoptions.root_deps in true_y:
		myoptions.root_deps = True

	if myoptions.select in true_y:
		myoptions.select = True
		myoptions.oneshot = False
	elif myoptions.select == "n":
		myoptions.oneshot = True

	if myoptions.selective in true_y:
		myoptions.selective = True

	if myoptions.backtrack is not None:

		try:
			backtrack = int(myoptions.backtrack)
		except (OverflowError, ValueError):
			backtrack = -1

		if backtrack < 0:
			backtrack = None
			if not silent:
				parser.error("Invalid --backtrack parameter: '%s'\n" % \
					(myoptions.backtrack,))

		myoptions.backtrack = backtrack

	if myoptions.deep is not None:
		deep = None
		if myoptions.deep == "True":
			deep = True
		else:
			try:
				deep = int(myoptions.deep)
			except (OverflowError, ValueError):
				deep = -1

		if deep is not True and deep < 0:
			deep = None
			if not silent:
				parser.error("Invalid --deep parameter: '%s'\n" % \
					(myoptions.deep,))

		myoptions.deep = deep

	if myoptions.jobs:
		jobs = None
		if myoptions.jobs == "True":
			jobs = True
		else:
			try:
				jobs = int(myoptions.jobs)
			except ValueError:
				jobs = -1

		if jobs is not True and \
			jobs < 1:
			jobs = None
			if not silent:
				parser.error("Invalid --jobs parameter: '%s'\n" % \
					(myoptions.jobs,))

		myoptions.jobs = jobs

	if myoptions.load_average:
		try:
			load_average = float(myoptions.load_average)
		except ValueError:
			load_average = 0.0

		if load_average <= 0.0:
			load_average = None
			if not silent:
				parser.error("Invalid --load-average parameter: '%s'\n" % \
					(myoptions.load_average,))

		myoptions.load_average = load_average
	
	if myoptions.rebuilt_binaries_timestamp:
		try:
			rebuilt_binaries_timestamp = int(myoptions.rebuilt_binaries_timestamp)
		except ValueError:
			rebuilt_binaries_timestamp = -1

		if rebuilt_binaries_timestamp < 0:
			rebuilt_binaries_timestamp = 0
			if not silent:
				parser.error("Invalid --rebuilt-binaries-timestamp parameter: '%s'\n" % \
					(myoptions.rebuilt_binaries_timestamp,))

		myoptions.rebuilt_binaries_timestamp = rebuilt_binaries_timestamp

	if myoptions.use_ebuild_visibility in true_y:
		myoptions.use_ebuild_visibility = True
	else:
		# None or "n"
		pass

	if myoptions.usepkg in true_y:
		myoptions.usepkg = True
	else:
		myoptions.usepkg = None

	if myoptions.usepkgonly in true_y:
		myoptions.usepkgonly = True
	else:
		myoptions.usepkgonly = None

	for myopt in options:
		v = getattr(myoptions, myopt.lstrip("--").replace("-", "_"))
		if v:
			myopts[myopt] = True

	for myopt in argument_options:
		v = getattr(myoptions, myopt.lstrip("--").replace("-", "_"), None)
		if v is not None:
			myopts[myopt] = v

	if myoptions.searchdesc:
		myoptions.search = True

	for action_opt in actions:
		v = getattr(myoptions, action_opt.replace("-", "_"))
		if v:
			if myaction:
				multiple_actions(myaction, action_opt)
				sys.exit(1)
			myaction = action_opt

	if myaction is None and myoptions.deselect is True:
		myaction = 'deselect'

	if myargs and sys.hexversion < 0x3000000 and \
		not isinstance(myargs[0], unicode):
		for i in range(len(myargs)):
			myargs[i] = portage._unicode_decode(myargs[i])

	myfiles += myargs

	return myaction, myopts, myfiles

# Warn about features that may confuse users and
# lead them to report invalid bugs.
_emerge_features_warn = frozenset(['keeptemp', 'keepwork'])

def validate_ebuild_environment(trees):
	features_warn = set()
	for myroot in trees:
		settings = trees[myroot]["vartree"].settings
		settings.validate()
		features_warn.update(
			_emerge_features_warn.intersection(settings.features))

	if features_warn:
		msg = "WARNING: The FEATURES variable contains one " + \
			"or more values that should be disabled under " + \
			"normal circumstances: %s" % " ".join(features_warn)
		out = portage.output.EOutput()
		for line in textwrap.wrap(msg, 65):
			out.ewarn(line)

def apply_priorities(settings):
	ionice(settings)
	nice(settings)

def nice(settings):
	try:
		os.nice(int(settings.get("PORTAGE_NICENESS", "0")))
	except (OSError, ValueError) as e:
		out = portage.output.EOutput()
		out.eerror("Failed to change nice value to '%s'" % \
			settings["PORTAGE_NICENESS"])
		out.eerror("%s\n" % str(e))

def ionice(settings):

	ionice_cmd = settings.get("PORTAGE_IONICE_COMMAND")
	if ionice_cmd:
		ionice_cmd = portage.util.shlex_split(ionice_cmd)
	if not ionice_cmd:
		return

	from portage.util import varexpand
	variables = {"PID" : str(os.getpid())}
	cmd = [varexpand(x, mydict=variables) for x in ionice_cmd]

	try:
		rval = portage.process.spawn(cmd, env=os.environ)
	except portage.exception.CommandNotFound:
		# The OS kernel probably doesn't support ionice,
		# so return silently.
		return

	if rval != os.EX_OK:
		out = portage.output.EOutput()
		out.eerror("PORTAGE_IONICE_COMMAND returned %d" % (rval,))
		out.eerror("See the make.conf(5) man page for PORTAGE_IONICE_COMMAND usage instructions.")

def setconfig_fallback(root_config):
	from portage._sets.base import DummyPackageSet
	from portage._sets.files import WorldSelectedSet
	from portage._sets.profiles import PackagesSystemSet
	setconfig = root_config.setconfig
	setconfig.psets['world'] = DummyPackageSet(atoms=['@selected', '@system'])
	setconfig.psets['selected'] = WorldSelectedSet(root_config.settings['EROOT'])
	setconfig.psets['system'] = \
		PackagesSystemSet(root_config.settings.profiles)
	root_config.sets = setconfig.getSets()

def get_missing_sets(root_config):
	# emerge requires existence of "world", "selected", and "system"
	missing_sets = []

	for s in ("selected", "system", "world",):
		if s not in root_config.sets:
			missing_sets.append(s)

	return missing_sets

def missing_sets_warning(root_config, missing_sets):
	if len(missing_sets) > 2:
		missing_sets_str = ", ".join('"%s"' % s for s in missing_sets[:-1])
		missing_sets_str += ', and "%s"' % missing_sets[-1]
	elif len(missing_sets) == 2:
		missing_sets_str = '"%s" and "%s"' % tuple(missing_sets)
	else:
		missing_sets_str = '"%s"' % missing_sets[-1]
	msg = ["emerge: incomplete set configuration, " + \
		"missing set(s): %s" % missing_sets_str]
	if root_config.sets:
		msg.append("        sets defined: %s" % ", ".join(root_config.sets))
	global_config_path = portage.const.GLOBAL_CONFIG_PATH
	if root_config.settings['EPREFIX']:
		global_config_path = os.path.join(root_config.settings['EPREFIX'],
				portage.const.GLOBAL_CONFIG_PATH.lstrip(os.sep))
	msg.append("        This usually means that '%s'" % \
		(os.path.join(global_config_path, "sets/portage.conf"),))
	msg.append("        is missing or corrupt.")
	msg.append("        Falling back to default world and system set configuration!!!")
	for line in msg:
		writemsg_level(line + "\n", level=logging.ERROR, noiselevel=-1)

def ensure_required_sets(trees):
	warning_shown = False
	for root_trees in trees.values():
		missing_sets = get_missing_sets(root_trees["root_config"])
		if missing_sets and not warning_shown:
			warning_shown = True
			missing_sets_warning(root_trees["root_config"], missing_sets)
		if missing_sets:
			setconfig_fallback(root_trees["root_config"])

def expand_set_arguments(myfiles, myaction, root_config):
	retval = os.EX_OK
	setconfig = root_config.setconfig

	sets = setconfig.getSets()

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

	# separators for set arguments
	ARG_START = "{"
	ARG_END = "}"

	for i in range(0, len(myfiles)):
		if myfiles[i].startswith(SETPREFIX):
			start = 0
			end = 0
			x = myfiles[i][len(SETPREFIX):]
			newset = ""
			while x:
				start = x.find(ARG_START)
				end = x.find(ARG_END)
				if start > 0 and start < end:
					namepart = x[:start]
					argpart = x[start+1:end]

					# TODO: implement proper quoting
					args = argpart.split(",")
					options = {}
					for a in args:
						if "=" in a:
							k, v  = a.split("=", 1)
							options[k] = v
						else:
							options[a] = "True"
					setconfig.update(namepart, options)
					newset += (x[:start-len(namepart)]+namepart)
					x = x[end+len(ARG_END):]
				else:
					newset += x
					x = ""
			myfiles[i] = SETPREFIX+newset

	sets = setconfig.getSets()

	# display errors that occured while loading the SetConfig instance
	for e in setconfig.errors:
		print(colorize("BAD", "Error during set creation: %s" % e))

	unmerge_actions = ("unmerge", "prune", "clean", "depclean")

	for a in myfiles:
		if a.startswith(SETPREFIX):		
				s = a[len(SETPREFIX):]
				if s not in sets:
					display_missing_pkg_set(root_config, s)
					return (None, 1)
				setconfig.active.append(s)
				try:
					set_atoms = setconfig.getSetAtoms(s)
				except portage.exception.PackageSetNotFound as e:
					writemsg_level(("emerge: the given set '%s' " + \
						"contains a non-existent set named '%s'.\n") % \
						(s, e), level=logging.ERROR, noiselevel=-1)
					return (None, 1)
				if myaction in unmerge_actions and \
						not sets[s].supportsOperation("unmerge"):
					sys.stderr.write("emerge: the given set '%s' does " % s + \
						"not support unmerge operations\n")
					retval = 1
				elif not set_atoms:
					print("emerge: '%s' is an empty set" % s)
				elif myaction not in do_not_expand:
					newargs.extend(set_atoms)
				else:
					newargs.append(SETPREFIX+s)
				for e in sets[s].errors:
					print(e)
		else:
			newargs.append(a)
	return (newargs, retval)

def repo_name_check(trees):
	missing_repo_names = set()
	for root_trees in trees.values():
		porttree = root_trees.get("porttree")
		if porttree:
			portdb = porttree.dbapi
			missing_repo_names.update(portdb.getMissingRepoNames())
			if portdb.porttree_root in missing_repo_names and \
				not os.path.exists(os.path.join(
				portdb.porttree_root, "profiles")):
				# This is normal if $PORTDIR happens to be empty,
				# so don't warn about it.
				missing_repo_names.remove(portdb.porttree_root)

	if missing_repo_names:
		msg = []
		msg.append("WARNING: One or more repositories " + \
			"have missing repo_name entries:")
		msg.append("")
		for p in missing_repo_names:
			msg.append("\t%s/profiles/repo_name" % (p,))
		msg.append("")
		msg.extend(textwrap.wrap("NOTE: Each repo_name entry " + \
			"should be a plain text file containing a unique " + \
			"name for the repository on the first line.", 70))
		msg.append("\n")
		writemsg_level("".join("%s\n" % l for l in msg),
			level=logging.WARNING, noiselevel=-1)

	return bool(missing_repo_names)

def repo_name_duplicate_check(trees):
	ignored_repos = {}
	for root, root_trees in trees.items():
		if 'porttree' in root_trees:
			portdb = root_trees['porttree'].dbapi
			if portdb.settings.get('PORTAGE_REPO_DUPLICATE_WARN') != '0':
				for repo_name, paths in portdb.getIgnoredRepos():
					k = (root, repo_name, portdb.getRepositoryPath(repo_name))
					ignored_repos.setdefault(k, []).extend(paths)

	if ignored_repos:
		msg = []
		msg.append('WARNING: One or more repositories ' + \
			'have been ignored due to duplicate')
		msg.append('  profiles/repo_name entries:')
		msg.append('')
		for k in sorted(ignored_repos):
			msg.append('  %s overrides' % ", ".join(k))
			for path in ignored_repos[k]:
				msg.append('    %s' % (path,))
			msg.append('')
		msg.extend('  ' + x for x in textwrap.wrap(
			"All profiles/repo_name entries must be unique in order " + \
			"to avoid having duplicates ignored. " + \
			"Set PORTAGE_REPO_DUPLICATE_WARN=\"0\" in " + \
			"/etc/make.conf if you would like to disable this warning."))
		msg.append("\n")
		writemsg_level(''.join('%s\n' % l for l in msg),
			level=logging.WARNING, noiselevel=-1)

	return bool(ignored_repos)

def config_protect_check(trees):
	for root, root_trees in trees.items():
		if not root_trees["root_config"].settings.get("CONFIG_PROTECT"):
			msg = "!!! CONFIG_PROTECT is empty"
			if root != "/":
				msg += " for '%s'" % root
			msg += "\n"
			writemsg_level(msg, level=logging.WARN, noiselevel=-1)

def profile_check(trees, myaction):
	if myaction in ("help", "info", "sync", "version"):
		return os.EX_OK
	for root, root_trees in trees.items():
		if root_trees["root_config"].settings.profiles:
			continue
		# generate some profile related warning messages
		validate_ebuild_environment(trees)
		msg = "If you have just changed your profile configuration, you " + \
			"should revert back to the previous configuration. Due to " + \
			"your current profile being invalid, allowed actions are " + \
			"limited to --help, --info, --sync, and --version."
		writemsg_level("".join("!!! %s\n" % l for l in textwrap.wrap(msg, 70)),
			level=logging.ERROR, noiselevel=-1)
		return 1
	return os.EX_OK

def check_procfs():
	procfs_path = '/proc'
	if platform.system() not in ("Linux",) or \
		os.path.ismount(procfs_path):
		return os.EX_OK
	msg = "It seems that %s is not mounted. You have been warned." % procfs_path
	writemsg_level("".join("!!! %s\n" % l for l in textwrap.wrap(msg, 70)),
		level=logging.ERROR, noiselevel=-1)
	return 1

def emerge_main():
	global portage	# NFC why this is necessary now - genone
	portage._disable_legacy_globals()
	portage.dep._internal_warnings = True
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
	if "--root" in myopts:
		os.environ["ROOT"] = myopts["--root"]
	if "--accept-properties" in myopts:
		os.environ["ACCEPT_PROPERTIES"] = myopts["--accept-properties"]

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(0o22)
	settings, trees, mtimedb = load_emerge_config()
	portdb = trees[settings["ROOT"]]["porttree"].dbapi
	rval = profile_check(trees, myaction)
	if rval != os.EX_OK:
		return rval

	tmpcmdline = []
	if "--ignore-default-opts" not in myopts:
		tmpcmdline.extend(settings["EMERGE_DEFAULT_OPTS"].split())
	tmpcmdline.extend(sys.argv[1:])
	myaction, myopts, myfiles = parse_opts(tmpcmdline)

	if myaction not in ('help', 'info', 'version') and \
		myopts.get('--package-moves') != 'n' and \
		_global_updates(trees, mtimedb["updates"], quiet=("--quiet" in myopts)):
		mtimedb.commit()
		# Reload the whole config from scratch.
		settings, trees, mtimedb = load_emerge_config(trees=trees)
		portdb = trees[settings["ROOT"]]["porttree"].dbapi

	xterm_titles = "notitles" not in settings.features
	if xterm_titles:
		xtermTitle("emerge")

	if "--digest" in myopts:
		os.environ["FEATURES"] = os.environ.get("FEATURES","") + " digest"
		# Reload the whole config from scratch so that the portdbapi internal
		# config is updated with new FEATURES.
		settings, trees, mtimedb = load_emerge_config(trees=trees)
		portdb = trees[settings["ROOT"]]["porttree"].dbapi

	adjust_configs(myopts, trees)
	apply_priorities(settings)

	if myaction == 'version':
		writemsg_stdout(getportageversion(
			settings["PORTDIR"], settings["ROOT"],
			settings.profile_path, settings["CHOST"],
			trees[settings["ROOT"]]["vartree"].dbapi) + '\n', noiselevel=-1)
		return 0
	elif myaction == 'help':
		_emerge.help.help(myopts, portage.output.havecolor)
		return 0

	spinner = stdout_spinner()
	if "candy" in settings.features:
		spinner.update = spinner.update_scroll

	if "--quiet" not in myopts:
		portage.deprecated_profile_check(settings=settings)
		if portage.const._ENABLE_REPO_NAME_WARN:
			# Bug #248603 - Disable warnings about missing
			# repo_name entries for stable branch.
			repo_name_check(trees)
		repo_name_duplicate_check(trees)
		config_protect_check(trees)
	check_procfs()

	if "getbinpkg" in settings.features:
		myopts["--getbinpkg"] = True

	if "--getbinpkgonly" in myopts:
		myopts["--getbinpkg"] = True

	if "--getbinpkgonly" in myopts:
		myopts["--usepkgonly"] = True

	if "--getbinpkg" in myopts:
		myopts["--usepkg"] = True

	if "--usepkgonly" in myopts:
		myopts["--usepkg"] = True

	if "buildpkg" in settings.features or "--buildpkgonly" in myopts:
		myopts["--buildpkg"] = True

	if "--buildpkgonly" in myopts:
		# --buildpkgonly will not merge anything, so
		# it cancels all binary package options.
		for opt in ("--getbinpkg", "--getbinpkgonly",
			"--usepkg", "--usepkgonly"):
			myopts.pop(opt, None)

	for mytrees in trees.values():
		mydb = mytrees["porttree"].dbapi
		# Freeze the portdbapi for performance (memoize all xmatch results).
		mydb.freeze()

		if myaction in ('search', None) and \
			"--usepkg" in myopts:
			# Populate the bintree with current --getbinpkg setting.
			# This needs to happen before expand_set_arguments(), in case
			# any sets use the bintree.
			mytrees["bintree"].populate(
				getbinpkgs="--getbinpkg" in myopts)

	del mytrees, mydb

	if "moo" in myfiles:
		print("""

  Larry loves Gentoo (""" + platform.system() + """)

 _______________________
< Have you mooed today? >
 -----------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\ 
                ||----w |
                ||     ||

""")

	for x in myfiles:
		ext = os.path.splitext(x)[1]
		if (ext == ".ebuild" or ext == ".tbz2") and os.path.exists(os.path.abspath(x)):
			print(colorize("BAD", "\n*** emerging by path is broken and may not always work!!!\n"))
			break

	root_config = trees[settings["ROOT"]]["root_config"]
	if myaction == "list-sets":
		writemsg_stdout("".join("%s\n" % s for s in sorted(root_config.sets)))
		return os.EX_OK

	ensure_required_sets(trees)

	# only expand sets for actions taking package arguments
	oldargs = myfiles[:]
	if myaction in ("clean", "config", "depclean", "info", "prune", "unmerge", None):
		myfiles, retval = expand_set_arguments(myfiles, myaction, root_config)
		if retval != os.EX_OK:
			return retval

		# Need to handle empty sets specially, otherwise emerge will react 
		# with the help message for empty argument lists
		if oldargs and not myfiles:
			print("emerge: no targets left after set expansion")
			return 0

	if ("--tree" in myopts) and ("--columns" in myopts):
		print("emerge: can't specify both of \"--tree\" and \"--columns\".")
		return 1

	if '--emptytree' in myopts and '--noreplace' in myopts:
		writemsg_level("emerge: can't specify both of " + \
			"\"--emptytree\" and \"--noreplace\".\n",
			level=logging.ERROR, noiselevel=-1)
		return 1

	if ("--quiet" in myopts):
		spinner.update = spinner.update_quiet
		portage.util.noiselimit = -1

	if "--fetch-all-uri" in myopts:
		myopts["--fetchonly"] = True

	if "--skipfirst" in myopts and "--resume" not in myopts:
		myopts["--resume"] = True

	# Allow -p to remove --ask
	if "--pretend" in myopts:
		myopts.pop("--ask", None)

	# forbid --ask when not in a terminal
	# note: this breaks `emerge --ask | tee logfile`, but that doesn't work anyway.
	if ("--ask" in myopts) and (not sys.stdin.isatty()):
		portage.writemsg("!!! \"--ask\" should only be used in a terminal. Exiting.\n",
			noiselevel=-1)
		return 1

	if settings.get("PORTAGE_DEBUG", "") == "1":
		spinner.update = spinner.update_quiet
		portage.debug=1
		portage.util.noiselimit = 0
		if "python-trace" in settings.features:
			import portage.debug
			portage.debug.set_trace(True)

	if not ("--quiet" in myopts):
		if '--nospinner' in myopts or \
			settings.get('TERM') == 'dumb' or \
			not sys.stdout.isatty():
			spinner.update = spinner.update_basic

	if "--debug" in myopts:
		print("myaction", myaction)
		print("myopts", myopts)

	if not myaction and not myfiles and "--resume" not in myopts:
		_emerge.help.help(myopts, portage.output.havecolor)
		return 1

	pretend = "--pretend" in myopts
	fetchonly = "--fetchonly" in myopts or "--fetch-all-uri" in myopts
	buildpkgonly = "--buildpkgonly" in myopts

	# check if root user is the current user for the actions where emerge needs this
	if portage.secpass < 2:
		# We've already allowed "--version" and "--help" above.
		if "--pretend" not in myopts and myaction not in ("search","info"):
			need_superuser = myaction in ('clean', 'depclean', 'deselect',
				'prune', 'unmerge') or not \
				(fetchonly or \
				(buildpkgonly and secpass >= 1) or \
				myaction in ("metadata", "regen", "sync"))
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
					print(("%s access is required... " + \
						"adding --pretend to options\n") % access_desc)
					if portage.secpass < 1 and not need_superuser:
						portage_group_warning()
				else:
					sys.stderr.write(("emerge: %s access is required\n") \
						% access_desc)
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
		_emerge.emergelog._disable = True

	else:
		if 'EMERGE_LOG_DIR' in settings:
			try:
				# At least the parent needs to exist for the lock file.
				portage.util.ensure_dirs(settings['EMERGE_LOG_DIR'])
			except portage.exception.PortageException as e:
				writemsg_level("!!! Error creating directory for " + \
					"EMERGE_LOG_DIR='%s':\n!!! %s\n" % \
					(settings['EMERGE_LOG_DIR'], e),
					noiselevel=-1, level=logging.ERROR)
			else:
				global _emerge_log_dir
				_emerge_log_dir = settings['EMERGE_LOG_DIR']

	if not "--pretend" in myopts:
		emergelog(xterm_titles, "Started emerge on: "+\
			_unicode_decode(
				time.strftime("%b %d, %Y %H:%M:%S", time.localtime()),
				encoding=_encodings['content'], errors='replace'))
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
		sys.exit(128 + signum)
	signal.signal(signal.SIGINT, emergeexitsig)
	signal.signal(signal.SIGTERM, emergeexitsig)

	def emergeexit():
		"""This gets out final log message in before we quit."""
		if "--pretend" not in myopts:
			emergelog(xterm_titles, " *** terminating.")
		if xterm_titles:
			xtermTitleReset()
	portage.atexit_register(emergeexit)

	if myaction in ("config", "metadata", "regen", "sync"):
		if "--pretend" in myopts:
			sys.stderr.write(("emerge: The '%s' action does " + \
				"not support '--pretend'.\n") % myaction)
			return 1

	if "sync" == myaction:
		return action_sync(settings, trees, mtimedb, myopts, myaction)
	elif "metadata" == myaction:
		action_metadata(settings, portdb, myopts)
	elif myaction=="regen":
		validate_ebuild_environment(trees)
		return action_regen(settings, portdb, myopts.get("--jobs"),
			myopts.get("--load-average"))
	# HELP action
	elif "config"==myaction:
		validate_ebuild_environment(trees)
		action_config(settings, trees, myopts, myfiles)

	# SEARCH action
	elif "search"==myaction:
		validate_ebuild_environment(trees)
		action_search(trees[settings["ROOT"]]["root_config"],
			myopts, myfiles, spinner)

	elif myaction in ('clean', 'depclean', 'deselect', 'prune', 'unmerge'):
		validate_ebuild_environment(trees)
		rval = action_uninstall(settings, trees, mtimedb["ldpath"],
			myopts, myaction, myfiles, spinner)
		if not (myaction == 'deselect' or buildpkgonly or fetchonly or pretend):
			post_emerge(myaction, myopts, myfiles, settings["ROOT"],
				trees, mtimedb, rval)
		return rval

	elif myaction == 'info':

		# Ensure atoms are valid before calling unmerge().
		vardb = trees[settings["ROOT"]]["vartree"].dbapi
		portdb = trees[settings["ROOT"]]["porttree"].dbapi
		bindb = trees[settings["ROOT"]]["bintree"].dbapi
		valid_atoms = []
		for x in myfiles:
			if is_valid_package_atom(x):
				try:
					#look at the installed files first, if there is no match
					#look at the ebuilds, since EAPI 4 allows running pkg_info
					#on non-installed packages
					valid_atom = dep_expand(x, mydb=vardb, settings=settings)
					if valid_atom.cp.split("/")[0] == "null":
						valid_atom = dep_expand(x, mydb=portdb, settings=settings)
					if valid_atom.cp.split("/")[0] == "null" and "--usepkg" in myopts:
						valid_atom = dep_expand(x, mydb=bindb, settings=settings)
					valid_atoms.append(valid_atom)
				except portage.exception.AmbiguousPackageName as e:
					msg = "The short ebuild name \"" + x + \
						"\" is ambiguous.  Please specify " + \
						"one of the following " + \
						"fully-qualified ebuild names instead:"
					for line in textwrap.wrap(msg, 70):
						writemsg_level("!!! %s\n" % (line,),
							level=logging.ERROR, noiselevel=-1)
					for i in e.args[0]:
						writemsg_level("    %s\n" % colorize("INFORM", i),
							level=logging.ERROR, noiselevel=-1)
					writemsg_level("\n", level=logging.ERROR, noiselevel=-1)
					return 1
				continue
			msg = []
			msg.append("'%s' is not a valid package atom." % (x,))
			msg.append("Please check ebuild(5) for full details.")
			writemsg_level("".join("!!! %s\n" % line for line in msg),
				level=logging.ERROR, noiselevel=-1)
			return 1

		return action_info(settings, trees, myopts, valid_atoms)

	# "update", "system", or just process files:
	else:
		validate_ebuild_environment(trees)

		for x in myfiles:
			if x.startswith(SETPREFIX) or \
				is_valid_package_atom(x, allow_repo=True):
				continue
			if x[:1] == os.sep:
				continue
			try:
				os.lstat(x)
				continue
			except OSError:
				pass
			msg = []
			msg.append("'%s' is not a valid package atom." % (x,))
			msg.append("Please check ebuild(5) for full details.")
			writemsg_level("".join("!!! %s\n" % line for line in msg),
				level=logging.ERROR, noiselevel=-1)
			return 1

		if "--pretend" not in myopts:
			display_news_notification(root_config, myopts)
		retval = action_build(settings, trees, mtimedb,
			myopts, myaction, myfiles, spinner)
		post_emerge(myaction, myopts, myfiles, settings["ROOT"],
			trees, mtimedb, retval)

		return retval
