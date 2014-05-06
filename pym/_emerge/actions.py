# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function, unicode_literals

import errno
import logging
import operator
import platform
import pwd
import random
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import warnings
from itertools import chain

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.dbapi._similar_name_search:similar_name_search',
	'portage.debug',
	'portage.news:count_unread_news,display_news_notifications',
	'portage.util._get_vm_info:get_vm_info',
	'_emerge.chk_updated_cfg_files:chk_updated_cfg_files',
	'_emerge.help:help@emerge_help',
	'_emerge.post_emerge:display_news_notification,post_emerge',
	'_emerge.stdout_spinner:stdout_spinner',
)

from portage.localization import _
from portage import os
from portage import shutil
from portage import eapi_is_supported, _encodings, _unicode_decode
from portage.cache.cache_errors import CacheError
from portage.const import EPREFIX
from portage.const import GLOBAL_CONFIG_PATH, VCS_DIRS, _DEPCLEAN_LIB_CHECK_DEFAULT
from portage.const import SUPPORTED_BINPKG_FORMATS, TIMESTAMP_FORMAT
from portage.dbapi.dep_expand import dep_expand
from portage.dbapi._expand_new_virt import expand_new_virt
from portage.dep import Atom
from portage.eclass_cache import hashed_path
from portage.exception import InvalidAtom, InvalidData, ParseError
from portage.output import blue, bold, colorize, create_color_func, darkgreen, \
	red, xtermTitle, xtermTitleReset, yellow
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.package.ebuild._ipc.QueryCommand import QueryCommand
from portage.package.ebuild.doebuild import _check_temp_dir
from portage._sets import load_default_config, SETPREFIX
from portage._sets.base import InternalPackageSet
from portage.util import cmp_sort_key, writemsg, varexpand, \
	writemsg_level, writemsg_stdout
from portage.util.digraph import digraph
from portage.util.SlotObject import SlotObject
from portage.util._async.run_main_scheduler import run_main_scheduler
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop
from portage._global_updates import _global_updates

from _emerge.clear_caches import clear_caches
from _emerge.countdown import countdown
from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.Dependency import Dependency
from _emerge.depgraph import backtrack_depgraph, depgraph, resume_depgraph
from _emerge.DepPrioritySatisfiedRange import DepPrioritySatisfiedRange
from _emerge.emergelog import emergelog
from _emerge.is_valid_package_atom import is_valid_package_atom
from _emerge.MetadataRegen import MetadataRegen
from _emerge.Package import Package
from _emerge.ProgressHandler import ProgressHandler
from _emerge.RootConfig import RootConfig
from _emerge.Scheduler import Scheduler
from _emerge.search import search
from _emerge.SetArg import SetArg
from _emerge.show_invalid_depstring_notice import show_invalid_depstring_notice
from _emerge.sync.getaddrinfo_validate import getaddrinfo_validate
from _emerge.sync.old_tree_timestamp import old_tree_timestamp_warn
from _emerge.unmerge import unmerge
from _emerge.UnmergeDepPriority import UnmergeDepPriority
from _emerge.UseFlagDisplay import pkg_use_display
from _emerge.userquery import userquery

if sys.hexversion >= 0x3000000:
	long = int
	_unicode = str
else:
	_unicode = unicode

def action_build(settings, trees, mtimedb,
	myopts, myaction, myfiles, spinner):

	if '--usepkgonly' not in myopts:
		old_tree_timestamp_warn(settings['PORTDIR'], settings)

	# It's best for config updates in /etc/portage to be processed
	# before we get here, so warn if they're not (bug #267103).
	chk_updated_cfg_files(settings['EROOT'], ['/etc/portage'])

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
		for x in mergelist:
			if not (isinstance(x, list) and len(x) == 4):
				continue
			pkg_type, pkg_root, pkg_key, pkg_action = x
			if pkg_root not in trees:
				# Current $ROOT setting differs,
				# so the list must be stale.
				mergelist = None
				break
		if not mergelist:
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
		for opt in ("--ask", "--color", "--skipfirst", "--tree"):
			resume_opts.pop(opt, None)

		# Current options always override resume_opts.
		resume_opts.update(myopts)
		myopts.clear()
		myopts.update(resume_opts)

		if "--debug" in myopts:
			writemsg_level("myopts %s\n" % (myopts,))

		# Adjust config according to options of the command being resumed.
		for myroot in trees:
			mysettings =  trees[myroot]["vartree"].settings
			mysettings.unlock()
			adjust_config(myopts, mysettings)
			mysettings.lock()
			del myroot, mysettings

	ldpath_mtimes = mtimedb["ldpath"]
	favorites=[]
	buildpkgonly = "--buildpkgonly" in myopts
	pretend = "--pretend" in myopts
	fetchonly = "--fetchonly" in myopts or "--fetch-all-uri" in myopts
	ask = "--ask" in myopts
	enter_invalid = '--ask-enter-invalid' in myopts
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
	myparams = create_depgraph_params(myopts, myaction)
	mergelist_shown = False

	if pretend or fetchonly:
		# make the mtimedb readonly
		mtimedb.filename = None
	if '--digest' in myopts or 'digest' in settings.features:
		if '--digest' in myopts:
			msg = "The --digest option"
		else:
			msg = "The FEATURES=digest setting"

		msg += " can prevent corruption from being" + \
			" noticed. The `repoman manifest` command is the preferred" + \
			" way to generate manifests and it is capable of doing an" + \
			" entire repository or category at once."
		prefix = bad(" * ")
		writemsg(prefix + "\n")
		for line in textwrap.wrap(msg, 72):
			writemsg("%s%s\n" % (prefix, line))
		writemsg(prefix + "\n")

	if resume:
		favorites = mtimedb["resume"].get("favorites")
		if not isinstance(favorites, list):
			favorites = []

		resume_data = mtimedb["resume"]
		mergelist = resume_data["mergelist"]
		if mergelist and "--skipfirst" in myopts:
			for i, task in enumerate(mergelist):
				if isinstance(task, list) and \
					task and task[-1] == "merge":
					del mergelist[i]
					break

		success = False
		mydepgraph = None
		try:
			success, mydepgraph, dropped_tasks = resume_depgraph(
				settings, trees, mtimedb, myopts, myparams, spinner)
		except (portage.exception.PackageNotFound,
			depgraph.UnsatisfiedResumeDep) as e:
			if isinstance(e, depgraph.UnsatisfiedResumeDep):
				mydepgraph = e.depgraph

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
				out.eerror("One or more packages are either masked or " + \
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
				for line in textwrap.wrap(msg, 72):
					out.eerror(line)
			elif isinstance(e, portage.exception.PackageNotFound):
				out.eerror("An expected package is " + \
					"not available: %s" % str(e))
				out.eerror("")
				msg = "The resume list contains one or more " + \
					"packages that are no longer " + \
					"available. Please restart/continue " + \
					"the operation manually."
				for line in textwrap.wrap(msg, 72):
					out.eerror(line)

		if success:
			if dropped_tasks:
				portage.writemsg("!!! One or more packages have been " + \
					"dropped due to\n" + \
					"!!! masking or unsatisfied dependencies:\n\n",
					noiselevel=-1)
				for task, atoms in dropped_tasks.items():
					if not atoms:
						writemsg("  %s is masked or unavailable\n" %
							(task,), noiselevel=-1)
					else:
						writemsg("  %s requires %s\n" %
							(task, ", ".join(atoms)), noiselevel=-1)

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
			print(darkgreen("emerge: It seems we have nothing to resume..."))
			return os.EX_OK

		try:
			success, mydepgraph, favorites = backtrack_depgraph(
				settings, trees, myopts, myparams, myaction, myfiles, spinner)
		except portage.exception.PackageSetNotFound as e:
			root_config = trees[settings['EROOT']]['root_config']
			display_missing_pkg_set(root_config, e.value)
			return 1

		if not success:
			mydepgraph.display_problems()
			return 1

	mergecount = None
	if "--pretend" not in myopts and \
		("--ask" in myopts or "--tree" in myopts or \
		"--verbose" in myopts) and \
		not ("--quiet" in myopts and "--ask" not in myopts):
		if "--resume" in myopts:
			mymergelist = mydepgraph.altlist()
			if len(mymergelist) == 0:
				print(colorize("INFORM", "emerge: It seems we have nothing to resume..."))
				return os.EX_OK
			favorites = mtimedb["resume"]["favorites"]
			retval = mydepgraph.display(
				mydepgraph.altlist(),
				favorites=favorites)
			mydepgraph.display_problems()
			mergelist_shown = True
			if retval != os.EX_OK:
				return retval
			prompt="Would you like to resume merging these packages?"
		else:
			retval = mydepgraph.display(
				mydepgraph.altlist(),
				favorites=favorites)
			mydepgraph.display_problems()
			mergelist_shown = True
			if retval != os.EX_OK:
				return retval
			mergecount=0
			for x in mydepgraph.altlist():
				if isinstance(x, Package) and x.operation == "merge":
					mergecount += 1

			prompt = None
			if mergecount==0:
				sets = trees[settings['EROOT']]['root_config'].sets
				world_candidates = None
				if "selective" in myparams and \
					not oneshot and favorites:
					# Sets that are not world candidates are filtered
					# out here since the favorites list needs to be
					# complete for depgraph.loadResumeCommand() to
					# operate correctly.
					world_candidates = [x for x in favorites \
						if not (x.startswith(SETPREFIX) and \
						not sets[x[1:]].world_candidate)]

				if "selective" in myparams and \
					not oneshot and world_candidates:
					# Prompt later, inside saveNomergeFavorites.
					prompt = None
				else:
					print()
					print("Nothing to merge; quitting.")
					print()
					return os.EX_OK
			elif "--fetchonly" in myopts or "--fetch-all-uri" in myopts:
				prompt="Would you like to fetch the source files for these packages?"
			else:
				prompt="Would you like to merge these packages?"
		print()
		if prompt is not None and "--ask" in myopts and \
			userquery(prompt, enter_invalid) == "No":
			print()
			print("Quitting.")
			print()
			return 128 + signal.SIGINT
		# Don't ask again (e.g. when auto-cleaning packages after merge)
		if mergecount != 0:
			myopts.pop("--ask", None)

	if ("--pretend" in myopts) and not ("--fetchonly" in myopts or "--fetch-all-uri" in myopts):
		if ("--resume" in myopts):
			mymergelist = mydepgraph.altlist()
			if len(mymergelist) == 0:
				print(colorize("INFORM", "emerge: It seems we have nothing to resume..."))
				return os.EX_OK
			favorites = mtimedb["resume"]["favorites"]
			retval = mydepgraph.display(
				mydepgraph.altlist(),
				favorites=favorites)
			mydepgraph.display_problems()
			mergelist_shown = True
			if retval != os.EX_OK:
				return retval
		else:
			retval = mydepgraph.display(
				mydepgraph.altlist(),
				favorites=favorites)
			mydepgraph.display_problems()
			mergelist_shown = True
			if retval != os.EX_OK:
				return retval

	else:

		if not mergelist_shown:
			# If we haven't already shown the merge list above, at
			# least show warnings about missed updates and such.
			mydepgraph.display_problems()

		if ("--resume" in myopts):
			favorites=mtimedb["resume"]["favorites"]

		else:
			if "resume" in mtimedb and \
			"mergelist" in mtimedb["resume"] and \
			len(mtimedb["resume"]["mergelist"]) > 1:
				mtimedb["resume_backup"] = mtimedb["resume"]
				del mtimedb["resume"]
				mtimedb.commit()

			mydepgraph.saveNomergeFavorites()

		if mergecount == 0:
			retval = os.EX_OK
		else:
			mergetask = Scheduler(settings, trees, mtimedb, myopts,
				spinner, favorites=favorites,
				graph_config=mydepgraph.schedulerGraph())

			del mydepgraph
			clear_caches(trees)

			retval = mergetask.merge()

			if retval == os.EX_OK and \
				not (buildpkgonly or fetchonly or pretend):
				if "yes" == settings.get("AUTOCLEAN"):
					portage.writemsg_stdout(">>> Auto-cleaning packages...\n")
					unmerge(trees[settings['EROOT']]['root_config'],
						myopts, "clean", [],
						ldpath_mtimes, autoclean=1)
				else:
					portage.writemsg_stdout(colorize("WARN", "WARNING:")
						+ " AUTOCLEAN is disabled.  This can cause serious"
						+ " problems due to overlapping packages.\n")

		return retval

def action_config(settings, trees, myopts, myfiles):
	enter_invalid = '--ask-enter-invalid' in myopts
	if len(myfiles) != 1:
		print(red("!!! config can only take a single package atom at this time\n"))
		sys.exit(1)
	if not is_valid_package_atom(myfiles[0], allow_repo=True):
		portage.writemsg("!!! '%s' is not a valid package atom.\n" % myfiles[0],
			noiselevel=-1)
		portage.writemsg("!!! Please check ebuild(5) for full details.\n")
		portage.writemsg("!!! (Did you specify a version but forget to prefix with '='?)\n")
		sys.exit(1)
	print()
	try:
		pkgs = trees[settings['EROOT']]['vartree'].dbapi.match(myfiles[0])
	except portage.exception.AmbiguousPackageName as e:
		# Multiple matches thrown from cpv_expand
		pkgs = e.args[0]
	if len(pkgs) == 0:
		print("No packages found.\n")
		sys.exit(0)
	elif len(pkgs) > 1:
		if "--ask" in myopts:
			options = []
			print("Please select a package to configure:")
			idx = 0
			for pkg in pkgs:
				idx += 1
				options.append(str(idx))
				print(options[-1]+") "+pkg)
			print("X) Cancel")
			options.append("X")
			idx = userquery("Selection?", enter_invalid, responses=options)
			if idx == "X":
				sys.exit(128 + signal.SIGINT)
			pkg = pkgs[int(idx)-1]
		else:
			print("The following packages available:")
			for pkg in pkgs:
				print("* "+pkg)
			print("\nPlease use a specific atom or the --ask option.")
			sys.exit(1)
	else:
		pkg = pkgs[0]

	print()
	if "--ask" in myopts:
		if userquery("Ready to configure %s?" % pkg, enter_invalid) == "No":
			sys.exit(128 + signal.SIGINT)
	else:
		print("Configuring pkg...")
	print()
	ebuildpath = trees[settings['EROOT']]['vartree'].dbapi.findname(pkg)
	mysettings = portage.config(clone=settings)
	vardb = trees[mysettings['EROOT']]['vartree'].dbapi
	debug = mysettings.get("PORTAGE_DEBUG") == "1"
	retval = portage.doebuild(ebuildpath, "config", settings=mysettings,
		debug=(settings.get("PORTAGE_DEBUG", "") == 1), cleanup=True,
		mydbapi = trees[settings['EROOT']]['vartree'].dbapi, tree="vartree")
	if retval == os.EX_OK:
		portage.doebuild(ebuildpath, "clean", settings=mysettings,
			debug=debug, mydbapi=vardb, tree="vartree")
	print()

def action_depclean(settings, trees, ldpath_mtimes,
	myopts, action, myfiles, spinner, scheduler=None):
	# Kill packages that aren't explicitly merged or are required as a
	# dependency of another package. World file is explicit.

	# Global depclean or prune operations are not very safe when there are
	# missing dependencies since it's unknown how badly incomplete
	# the dependency graph is, and we might accidentally remove packages
	# that should have been pulled into the graph. On the other hand, it's
	# relatively safe to ignore missing deps when only asked to remove
	# specific packages.

	msg = []
	if "preserve-libs" not in settings.features and \
		not myopts.get("--depclean-lib-check", _DEPCLEAN_LIB_CHECK_DEFAULT) != "n":
		msg.append("Depclean may break link level dependencies. Thus, it is\n")
		msg.append("recommended to use a tool such as " + good("`revdep-rebuild`") + " (from\n")
		msg.append("app-portage/gentoolkit) in order to detect such breakage.\n")
		msg.append("\n")
	msg.append("Always study the list of packages to be cleaned for any obvious\n")
	msg.append("mistakes. Packages that are part of the world set will always\n")
	msg.append("be kept.  They can be manually added to this set with\n")
	msg.append(good("`emerge --noreplace <atom>`") + ".  Packages that are listed in\n")
	msg.append("package.provided (see portage(5)) will be removed by\n")
	msg.append("depclean, even if they are part of the world set.\n")
	msg.append("\n")
	msg.append("As a safety measure, depclean will not remove any packages\n")
	msg.append("unless *all* required dependencies have been resolved.  As a\n")
	msg.append("consequence, it is often necessary to run %s\n" % \
		good("`emerge --update"))
	msg.append(good("--newuse --deep @world`") + \
		" prior to depclean.\n")

	if action == "depclean" and "--quiet" not in myopts and not myfiles:
		portage.writemsg_stdout("\n")
		for x in msg:
			portage.writemsg_stdout(colorize("WARN", " * ") + x)

	root_config = trees[settings['EROOT']]['root_config']
	vardb = root_config.trees['vartree'].dbapi

	args_set = InternalPackageSet(allow_repo=True)
	if myfiles:
		args_set.update(myfiles)
		matched_packages = False
		for x in args_set:
			if vardb.match(x):
				matched_packages = True
			else:
				writemsg_level("--- Couldn't find '%s' to %s.\n" % \
					(x.replace("null/", ""), action),
					level=logging.WARN, noiselevel=-1)
		if not matched_packages:
			writemsg_level(">>> No packages selected for removal by %s\n" % \
				action)
			return 0

	# The calculation is done in a separate function so that depgraph
	# references go out of scope and the corresponding memory
	# is freed before we call unmerge().
	rval, cleanlist, ordered, req_pkg_count = \
		calc_depclean(settings, trees, ldpath_mtimes,
			myopts, action, args_set, spinner)

	clear_caches(trees)

	if rval != os.EX_OK:
		return rval

	if cleanlist:
		rval = unmerge(root_config, myopts, "unmerge",
			cleanlist, ldpath_mtimes, ordered=ordered,
			scheduler=scheduler)

	if action == "prune":
		return rval

	if not cleanlist and "--quiet" in myopts:
		return rval

	set_atoms = {}
	for k in ("system", "selected"):
		try:
			set_atoms[k] = root_config.setconfig.getSetAtoms(k)
		except portage.exception.PackageSetNotFound:
			# A nested set could not be resolved, so ignore nested sets.
			set_atoms[k] = root_config.sets[k].getAtoms()

	print("Packages installed:   " + str(len(vardb.cpv_all())))
	print("Packages in world:    %d" % len(set_atoms["selected"]))
	print("Packages in system:   %d" % len(set_atoms["system"]))
	print("Required packages:    "+str(req_pkg_count))
	if "--pretend" in myopts:
		print("Number to remove:     "+str(len(cleanlist)))
	else:
		print("Number removed:       "+str(len(cleanlist)))

	return rval

def calc_depclean(settings, trees, ldpath_mtimes,
	myopts, action, args_set, spinner):
	allow_missing_deps = bool(args_set)

	debug = '--debug' in myopts
	xterm_titles = "notitles" not in settings.features
	root_len = len(settings["ROOT"])
	eroot = settings['EROOT']
	root_config = trees[eroot]["root_config"]
	psets = root_config.setconfig.psets
	deselect = myopts.get('--deselect') != 'n'
	required_sets = {}
	required_sets['world'] = psets['world']

	# When removing packages, a temporary version of the world 'selected'
	# set may be used which excludes packages that are intended to be
	# eligible for removal.
	selected_set = psets['selected']
	required_sets['selected'] = selected_set
	protected_set = InternalPackageSet()
	protected_set_name = '____depclean_protected_set____'
	required_sets[protected_set_name] = protected_set
	system_set = psets["system"]

	set_atoms = {}
	for k in ("system", "selected"):
		try:
			set_atoms[k] = root_config.setconfig.getSetAtoms(k)
		except portage.exception.PackageSetNotFound:
			# A nested set could not be resolved, so ignore nested sets.
			set_atoms[k] = root_config.sets[k].getAtoms()

	if not set_atoms["system"] or not set_atoms["selected"]:

		if not set_atoms["system"]:
			writemsg_level("!!! You have no system list.\n",
				level=logging.ERROR, noiselevel=-1)

		if not set_atoms["selected"]:
			writemsg_level("!!! You have no world file.\n",
					level=logging.WARNING, noiselevel=-1)

		writemsg_level("!!! Proceeding is likely to " + \
			"break your installation.\n",
			level=logging.WARNING, noiselevel=-1)
		if "--pretend" not in myopts:
			countdown(int(settings["EMERGE_WARNING_DELAY"]), ">>> Depclean")

	if action == "depclean":
		emergelog(xterm_titles, " >>> depclean")

	writemsg_level("\nCalculating dependencies  ")
	resolver_params = create_depgraph_params(myopts, "remove")
	resolver = depgraph(settings, trees, myopts, resolver_params, spinner)
	resolver._load_vdb()
	vardb = resolver._frozen_config.trees[eroot]["vartree"].dbapi
	real_vardb = trees[eroot]["vartree"].dbapi

	if action == "depclean":

		if args_set:

			if deselect:
				# Start with an empty set.
				selected_set = InternalPackageSet()
				required_sets['selected'] = selected_set
				# Pull in any sets nested within the selected set.
				selected_set.update(psets['selected'].getNonAtoms())

			# Pull in everything that's installed but not matched
			# by an argument atom since we don't want to clean any
			# package if something depends on it.
			for pkg in vardb:
				if spinner:
					spinner.update()

				try:
					if args_set.findAtomForPackage(pkg) is None:
						protected_set.add("=" + pkg.cpv)
						continue
				except portage.exception.InvalidDependString as e:
					show_invalid_depstring_notice(pkg,
						pkg._metadata["PROVIDE"], _unicode(e))
					del e
					protected_set.add("=" + pkg.cpv)
					continue

	elif action == "prune":

		if deselect:
			# Start with an empty set.
			selected_set = InternalPackageSet()
			required_sets['selected'] = selected_set
			# Pull in any sets nested within the selected set.
			selected_set.update(psets['selected'].getNonAtoms())

		# Pull in everything that's installed since we don't
		# to prune a package if something depends on it.
		protected_set.update(vardb.cp_all())

		if not args_set:

			# Try to prune everything that's slotted.
			for cp in vardb.cp_all():
				if len(vardb.cp_list(cp)) > 1:
					args_set.add(cp)

		# Remove atoms from world that match installed packages
		# that are also matched by argument atoms, but do not remove
		# them if they match the highest installed version.
		for pkg in vardb:
			if spinner is not None:
				spinner.update()
			pkgs_for_cp = vardb.match_pkgs(pkg.cp)
			if not pkgs_for_cp or pkg not in pkgs_for_cp:
				raise AssertionError("package expected in matches: " + \
					"cp = %s, cpv = %s matches = %s" % \
					(pkg.cp, pkg.cpv, [str(x) for x in pkgs_for_cp]))

			highest_version = pkgs_for_cp[-1]
			if pkg == highest_version:
				# pkg is the highest version
				protected_set.add("=" + pkg.cpv)
				continue

			if len(pkgs_for_cp) <= 1:
				raise AssertionError("more packages expected: " + \
					"cp = %s, cpv = %s matches = %s" % \
					(pkg.cp, pkg.cpv, [str(x) for x in pkgs_for_cp]))

			try:
				if args_set.findAtomForPackage(pkg) is None:
					protected_set.add("=" + pkg.cpv)
					continue
			except portage.exception.InvalidDependString as e:
				show_invalid_depstring_notice(pkg,
					pkg._metadata["PROVIDE"], _unicode(e))
				del e
				protected_set.add("=" + pkg.cpv)
				continue

	if resolver._frozen_config.excluded_pkgs:
		excluded_set = resolver._frozen_config.excluded_pkgs
		required_sets['__excluded__'] = InternalPackageSet()

		for pkg in vardb:
			if spinner:
				spinner.update()

			try:
				if excluded_set.findAtomForPackage(pkg):
					required_sets['__excluded__'].add("=" + pkg.cpv)
			except portage.exception.InvalidDependString as e:
				show_invalid_depstring_notice(pkg,
					pkg._metadata["PROVIDE"], _unicode(e))
				del e
				required_sets['__excluded__'].add("=" + pkg.cpv)

	success = resolver._complete_graph(required_sets={eroot:required_sets})
	writemsg_level("\b\b... done!\n")

	resolver.display_problems()

	if not success:
		return 1, [], False, 0

	def unresolved_deps():

		unresolvable = set()
		for dep in resolver._dynamic_config._initially_unsatisfied_deps:
			if isinstance(dep.parent, Package) and \
				(dep.priority > UnmergeDepPriority.SOFT):
				unresolvable.add((dep.atom, dep.parent.cpv))

		if not unresolvable:
			return False

		if unresolvable and not allow_missing_deps:

			if "--debug" in myopts:
				writemsg("\ndigraph:\n\n", noiselevel=-1)
				resolver._dynamic_config.digraph.debug_print()
				writemsg("\n", noiselevel=-1)

			prefix = bad(" * ")
			msg = []
			msg.append("Dependencies could not be completely resolved due to")
			msg.append("the following required packages not being installed:")
			msg.append("")
			for atom, parent in unresolvable:
				if atom != atom.unevaluated_atom and \
					vardb.match(_unicode(atom)):
					msg.append("  %s (%s) pulled in by:" %
						(atom.unevaluated_atom, atom))
				else:
					msg.append("  %s pulled in by:" % (atom,))
				msg.append("    %s" % (parent,))
				msg.append("")
			msg.extend(textwrap.wrap(
				"Have you forgotten to do a complete update prior " + \
				"to depclean? The most comprehensive command for this " + \
				"purpose is as follows:", 65
			))
			msg.append("")
			msg.append("  " + \
				good("emerge --update --newuse --deep --with-bdeps=y @world"))
			msg.append("")
			msg.extend(textwrap.wrap(
				"Note that the --with-bdeps=y option is not required in " + \
				"many situations. Refer to the emerge manual page " + \
				"(run `man emerge`) for more information about " + \
				"--with-bdeps.", 65
			))
			msg.append("")
			msg.extend(textwrap.wrap(
				"Also, note that it may be necessary to manually uninstall " + \
				"packages that no longer exist in the portage tree, since " + \
				"it may not be possible to satisfy their dependencies.", 65
			))
			if action == "prune":
				msg.append("")
				msg.append("If you would like to ignore " + \
					"dependencies then use %s." % good("--nodeps"))
			writemsg_level("".join("%s%s\n" % (prefix, line) for line in msg),
				level=logging.ERROR, noiselevel=-1)
			return True
		return False

	if unresolved_deps():
		return 1, [], False, 0

	graph = resolver._dynamic_config.digraph.copy()
	required_pkgs_total = 0
	for node in graph:
		if isinstance(node, Package):
			required_pkgs_total += 1

	def show_parents(child_node):
		parent_atoms = \
			resolver._dynamic_config._parent_atoms.get(child_node, [])

		# Never display the special internal protected_set.
		parent_atoms = [parent_atom for parent_atom in parent_atoms
			if not (isinstance(parent_atom[0], SetArg) and
			parent_atom[0].name == protected_set_name)]

		if not parent_atoms:
			# With --prune, the highest version can be pulled in without any
			# real parent since all installed packages are pulled in.  In that
			# case there's nothing to show here.
			return
		parent_atom_dict = {}
		for parent, atom in parent_atoms:
			parent_atom_dict.setdefault(parent, []).append(atom)

		parent_strs = []
		for parent, atoms in parent_atom_dict.items():
			parent_strs.append("%s requires %s" %
				(getattr(parent, "cpv", parent), ", ".join(atoms)))
		parent_strs.sort()
		msg = []
		msg.append("  %s pulled in by:\n" % (child_node.cpv,))
		for parent_str in parent_strs:
			msg.append("    %s\n" % (parent_str,))
		msg.append("\n")
		portage.writemsg_stdout("".join(msg), noiselevel=-1)

	def cmp_pkg_cpv(pkg1, pkg2):
		"""Sort Package instances by cpv."""
		if pkg1.cpv > pkg2.cpv:
			return 1
		elif pkg1.cpv == pkg2.cpv:
			return 0
		else:
			return -1

	def create_cleanlist():

		if "--debug" in myopts:
			writemsg("\ndigraph:\n\n", noiselevel=-1)
			graph.debug_print()
			writemsg("\n", noiselevel=-1)

		pkgs_to_remove = []

		if action == "depclean":
			if args_set:

				for pkg in sorted(vardb, key=cmp_sort_key(cmp_pkg_cpv)):
					arg_atom = None
					try:
						arg_atom = args_set.findAtomForPackage(pkg)
					except portage.exception.InvalidDependString:
						# this error has already been displayed by now
						continue

					if arg_atom:
						if pkg not in graph:
							pkgs_to_remove.append(pkg)
						elif "--verbose" in myopts:
							show_parents(pkg)

			else:
				for pkg in sorted(vardb, key=cmp_sort_key(cmp_pkg_cpv)):
					if pkg not in graph:
						pkgs_to_remove.append(pkg)
					elif "--verbose" in myopts:
						show_parents(pkg)

		elif action == "prune":

			for atom in args_set:
				for pkg in vardb.match_pkgs(atom):
					if pkg not in graph:
						pkgs_to_remove.append(pkg)
					elif "--verbose" in myopts:
						show_parents(pkg)

		if not pkgs_to_remove:
			writemsg_level(
				">>> No packages selected for removal by %s\n" % action)
			if "--verbose" not in myopts:
				writemsg_level(
					">>> To see reverse dependencies, use %s\n" % \
						good("--verbose"))
			if action == "prune":
				writemsg_level(
					">>> To ignore dependencies, use %s\n" % \
						good("--nodeps"))

		return pkgs_to_remove

	cleanlist = create_cleanlist()
	clean_set = set(cleanlist)

	depclean_lib_check = cleanlist and real_vardb._linkmap is not None and \
		myopts.get("--depclean-lib-check", _DEPCLEAN_LIB_CHECK_DEFAULT) != "n"
	preserve_libs = "preserve-libs" in settings.features
	preserve_libs_restrict = False

	if depclean_lib_check and preserve_libs:
		for pkg in cleanlist:
			if "preserve-libs" in pkg.restrict:
				preserve_libs_restrict = True
				break

	if depclean_lib_check and \
		(preserve_libs_restrict or not preserve_libs):

		# Check if any of these packages are the sole providers of libraries
		# with consumers that have not been selected for removal. If so, these
		# packages and any dependencies need to be added to the graph.
		linkmap = real_vardb._linkmap
		consumer_cache = {}
		provider_cache = {}
		consumer_map = {}

		writemsg_level(">>> Checking for lib consumers...\n")

		for pkg in cleanlist:

			if preserve_libs and "preserve-libs" not in pkg.restrict:
				# Any needed libraries will be preserved
				# when this package is unmerged, so there's
				# no need to account for it here.
				continue

			pkg_dblink = real_vardb._dblink(pkg.cpv)
			consumers = {}

			for lib in pkg_dblink.getcontents():
				lib = lib[root_len:]
				lib_key = linkmap._obj_key(lib)
				lib_consumers = consumer_cache.get(lib_key)
				if lib_consumers is None:
					try:
						lib_consumers = linkmap.findConsumers(lib_key)
					except KeyError:
						continue
					consumer_cache[lib_key] = lib_consumers
				if lib_consumers:
					consumers[lib_key] = lib_consumers

			if not consumers:
				continue

			for lib, lib_consumers in list(consumers.items()):
				for consumer_file in list(lib_consumers):
					if pkg_dblink.isowner(consumer_file):
						lib_consumers.remove(consumer_file)
				if not lib_consumers:
					del consumers[lib]

			if not consumers:
				continue

			for lib, lib_consumers in consumers.items():

				soname = linkmap.getSoname(lib)

				consumer_providers = []
				for lib_consumer in lib_consumers:
					providers = provider_cache.get(lib)
					if providers is None:
						providers = linkmap.findProviders(lib_consumer)
						provider_cache[lib_consumer] = providers
					if soname not in providers:
						# Why does this happen?
						continue
					consumer_providers.append(
						(lib_consumer, providers[soname]))

				consumers[lib] = consumer_providers

			consumer_map[pkg] = consumers

		if consumer_map:

			search_files = set()
			for consumers in consumer_map.values():
				for lib, consumer_providers in consumers.items():
					for lib_consumer, providers in consumer_providers:
						search_files.add(lib_consumer)
						search_files.update(providers)

			writemsg_level(">>> Assigning files to packages...\n")
			file_owners = {}
			for f in search_files:
				owner_set = set()
				for owner in linkmap.getOwners(f):
					owner_dblink = real_vardb._dblink(owner)
					if owner_dblink.exists():
						owner_set.add(owner_dblink)
				if owner_set:
					file_owners[f] = owner_set

			for pkg, consumers in list(consumer_map.items()):
				for lib, consumer_providers in list(consumers.items()):
					lib_consumers = set()

					for lib_consumer, providers in consumer_providers:
						owner_set = file_owners.get(lib_consumer)
						provider_dblinks = set()
						provider_pkgs = set()

						if len(providers) > 1:
							for provider in providers:
								provider_set = file_owners.get(provider)
								if provider_set is not None:
									provider_dblinks.update(provider_set)

						if len(provider_dblinks) > 1:
							for provider_dblink in provider_dblinks:
								provider_pkg = resolver._pkg(
									provider_dblink.mycpv, "installed",
									root_config, installed=True)
								if provider_pkg not in clean_set:
									provider_pkgs.add(provider_pkg)

						if provider_pkgs:
							continue

						if owner_set is not None:
							lib_consumers.update(owner_set)

					for consumer_dblink in list(lib_consumers):
						if resolver._pkg(consumer_dblink.mycpv, "installed",
							root_config, installed=True) in clean_set:
							lib_consumers.remove(consumer_dblink)
							continue

					if lib_consumers:
						consumers[lib] = lib_consumers
					else:
						del consumers[lib]
				if not consumers:
					del consumer_map[pkg]

		if consumer_map:
			# TODO: Implement a package set for rebuilding consumer packages.

			msg = "In order to avoid breakage of link level " + \
				"dependencies, one or more packages will not be removed. " + \
				"This can be solved by rebuilding " + \
				"the packages that pulled them in."

			prefix = bad(" * ")
			writemsg_level("".join(prefix + "%s\n" % line for \
				line in textwrap.wrap(msg, 70)), level=logging.WARNING, noiselevel=-1)

			msg = []
			for pkg in sorted(consumer_map, key=cmp_sort_key(cmp_pkg_cpv)):
				consumers = consumer_map[pkg]
				consumer_libs = {}
				for lib, lib_consumers in consumers.items():
					for consumer in lib_consumers:
						consumer_libs.setdefault(
							consumer.mycpv, set()).add(linkmap.getSoname(lib))
				unique_consumers = set(chain(*consumers.values()))
				unique_consumers = sorted(consumer.mycpv \
					for consumer in unique_consumers)
				msg.append("")
				msg.append("  %s pulled in by:" % (pkg.cpv,))
				for consumer in unique_consumers:
					libs = consumer_libs[consumer]
					msg.append("    %s needs %s" % \
						(consumer, ', '.join(sorted(libs))))
			msg.append("")
			writemsg_level("".join(prefix + "%s\n" % line for line in msg),
				level=logging.WARNING, noiselevel=-1)

			# Add lib providers to the graph as children of lib consumers,
			# and also add any dependencies pulled in by the provider.
			writemsg_level(">>> Adding lib providers to graph...\n")

			for pkg, consumers in consumer_map.items():
				for consumer_dblink in set(chain(*consumers.values())):
					consumer_pkg = resolver._pkg(consumer_dblink.mycpv,
						"installed", root_config, installed=True)
					if not resolver._add_pkg(pkg,
						Dependency(parent=consumer_pkg,
						priority=UnmergeDepPriority(runtime=True,
							runtime_slot_op=True),
						root=pkg.root)):
						resolver.display_problems()
						return 1, [], False, 0

			writemsg_level("\nCalculating dependencies  ")
			success = resolver._complete_graph(
				required_sets={eroot:required_sets})
			writemsg_level("\b\b... done!\n")
			resolver.display_problems()
			if not success:
				return 1, [], False, 0
			if unresolved_deps():
				return 1, [], False, 0

			graph = resolver._dynamic_config.digraph.copy()
			required_pkgs_total = 0
			for node in graph:
				if isinstance(node, Package):
					required_pkgs_total += 1
			cleanlist = create_cleanlist()
			if not cleanlist:
				return 0, [], False, required_pkgs_total
			clean_set = set(cleanlist)

	if clean_set:
		writemsg_level(">>> Calculating removal order...\n")
		# Use a topological sort to create an unmerge order such that
		# each package is unmerged before it's dependencies. This is
		# necessary to avoid breaking things that may need to run
		# during pkg_prerm or pkg_postrm phases.

		# Create a new graph to account for dependencies between the
		# packages being unmerged.
		graph = digraph()
		del cleanlist[:]

		runtime = UnmergeDepPriority(runtime=True)
		runtime_post = UnmergeDepPriority(runtime_post=True)
		buildtime = UnmergeDepPriority(buildtime=True)
		priority_map = {
			"RDEPEND": runtime,
			"PDEPEND": runtime_post,
			"HDEPEND": buildtime,
			"DEPEND": buildtime,
		}

		for node in clean_set:
			graph.add(node, None)
			for dep_type in Package._dep_keys:
				depstr = node._metadata[dep_type]
				if not depstr:
					continue
				priority = priority_map[dep_type]

				if debug:
					writemsg_level("\nParent:    %s\n"
						% (node,), noiselevel=-1, level=logging.DEBUG)
					writemsg_level(  "Depstring: %s\n"
						% (depstr,), noiselevel=-1, level=logging.DEBUG)
					writemsg_level(  "Priority:  %s\n"
						% (priority,), noiselevel=-1, level=logging.DEBUG)

				try:
					atoms = resolver._select_atoms(eroot, depstr,
						myuse=node.use.enabled, parent=node,
						priority=priority)[node]
				except portage.exception.InvalidDependString:
					# Ignore invalid deps of packages that will
					# be uninstalled anyway.
					continue

				if debug:
					writemsg_level("Candidates: [%s]\n" % \
						', '.join("'%s'" % (x,) for x in atoms),
						noiselevel=-1, level=logging.DEBUG)

				for atom in atoms:
					if not isinstance(atom, portage.dep.Atom):
						# Ignore invalid atoms returned from dep_check().
						continue
					if atom.blocker:
						continue
					matches = vardb.match_pkgs(atom)
					if not matches:
						continue
					for child_node in matches:
						if child_node in clean_set:

							mypriority = priority.copy()
							if atom.slot_operator_built:
								if mypriority.buildtime:
									mypriority.buildtime_slot_op = True
								if mypriority.runtime:
									mypriority.runtime_slot_op = True

							graph.add(child_node, node, priority=mypriority)

		if debug:
			writemsg_level("\nunmerge digraph:\n\n",
				noiselevel=-1, level=logging.DEBUG)
			graph.debug_print()
			writemsg_level("\n", noiselevel=-1, level=logging.DEBUG)

		ordered = True
		if len(graph.order) == len(graph.root_nodes()):
			# If there are no dependencies between packages
			# let unmerge() group them by cat/pn.
			ordered = False
			cleanlist = [pkg.cpv for pkg in graph.order]
		else:
			# Order nodes from lowest to highest overall reference count for
			# optimal root node selection (this can help minimize issues
			# with unaccounted implicit dependencies).
			node_refcounts = {}
			for node in graph.order:
				node_refcounts[node] = len(graph.parent_nodes(node))
			def cmp_reference_count(node1, node2):
				return node_refcounts[node1] - node_refcounts[node2]
			graph.order.sort(key=cmp_sort_key(cmp_reference_count))

			ignore_priority_range = [None]
			ignore_priority_range.extend(
				range(UnmergeDepPriority.MIN, UnmergeDepPriority.MAX + 1))
			while graph:
				for ignore_priority in ignore_priority_range:
					nodes = graph.root_nodes(ignore_priority=ignore_priority)
					if nodes:
						break
				if not nodes:
					raise AssertionError("no root nodes")
				if ignore_priority is not None:
					# Some deps have been dropped due to circular dependencies,
					# so only pop one node in order to minimize the number that
					# are dropped.
					del nodes[1:]
				for node in nodes:
					graph.remove(node)
					cleanlist.append(node.cpv)

		return 0, cleanlist, ordered, required_pkgs_total
	return 0, [], False, required_pkgs_total

def action_deselect(settings, trees, opts, atoms):
	enter_invalid = '--ask-enter-invalid' in opts
	root_config = trees[settings['EROOT']]['root_config']
	world_set = root_config.sets['selected']
	if not hasattr(world_set, 'update'):
		writemsg_level("World @selected set does not appear to be mutable.\n",
			level=logging.ERROR, noiselevel=-1)
		return 1

	pretend = '--pretend' in opts
	locked = False
	if not pretend and hasattr(world_set, 'lock'):
		world_set.lock()
		locked = True
	try:
		world_set.load()
		world_atoms = world_set.getAtoms()
		vardb = root_config.trees["vartree"].dbapi
		expanded_atoms = set(atoms)

		for atom in atoms:
			if not atom.startswith(SETPREFIX):
				if atom.cp.startswith("null/"):
					# try to expand category from world set
					null_cat, pn = portage.catsplit(atom.cp)
					for world_atom in world_atoms:
						cat, world_pn = portage.catsplit(world_atom.cp)
						if pn == world_pn:
							expanded_atoms.add(
								Atom(atom.replace("null", cat, 1),
								allow_repo=True, allow_wildcard=True))

				for cpv in vardb.match(atom):
					pkg = vardb._pkg_str(cpv, None)
					expanded_atoms.add(Atom("%s:%s" % (pkg.cp, pkg.slot)))

		discard_atoms = set()
		for atom in world_set:
			for arg_atom in expanded_atoms:
				if arg_atom.startswith(SETPREFIX):
					if atom.startswith(SETPREFIX) and \
						arg_atom == atom:
						discard_atoms.add(atom)
						break
				else:
					if not atom.startswith(SETPREFIX) and \
						arg_atom.intersects(atom) and \
						not (arg_atom.slot and not atom.slot) and \
						not (arg_atom.repo and not atom.repo):
						discard_atoms.add(atom)
						break
		if discard_atoms:
			for atom in sorted(discard_atoms):

				if pretend:
					action_desc = "Would remove"
				else:
					action_desc = "Removing"

				if atom.startswith(SETPREFIX):
					filename = "world_sets"
				else:
					filename = "world"

				writemsg_stdout(
					">>> %s %s from \"%s\" favorites file...\n" %
					(action_desc, colorize("INFORM", _unicode(atom)),
					filename), noiselevel=-1)

			if '--ask' in opts:
				prompt = "Would you like to remove these " + \
					"packages from your world favorites?"
				if userquery(prompt, enter_invalid) == 'No':
					return 128 + signal.SIGINT

			remaining = set(world_set)
			remaining.difference_update(discard_atoms)
			if not pretend:
				world_set.replace(remaining)
		else:
			print(">>> No matching atoms found in \"world\" favorites file...")
	finally:
		if locked:
			world_set.unlock()
	return os.EX_OK

class _info_pkgs_ver(object):
	def __init__(self, ver, repo_suffix, provide_suffix):
		self.ver = ver
		self.repo_suffix = repo_suffix
		self.provide_suffix = provide_suffix

	def __lt__(self, other):
		return portage.versions.vercmp(self.ver, other.ver) < 0

	def toString(self):
		"""
		This may return unicode if repo_name contains unicode.
		Don't use __str__ and str() since unicode triggers compatibility
		issues between python 2.x and 3.x.
		"""
		return self.ver + self.repo_suffix + self.provide_suffix

def action_info(settings, trees, myopts, myfiles):

	# See if we can find any packages installed matching the strings
	# passed on the command line
	mypkgs = []
	eroot = settings['EROOT']
	vardb = trees[eroot]["vartree"].dbapi
	portdb = trees[eroot]['porttree'].dbapi
	bindb = trees[eroot]["bintree"].dbapi
	for x in myfiles:
		any_match = False
		cp_exists = bool(vardb.match(x.cp))
		installed_match = vardb.match(x)
		for installed in installed_match:
			mypkgs.append((installed, "installed"))
			any_match = True

		if any_match:
			continue

		for db, pkg_type in ((portdb, "ebuild"), (bindb, "binary")):
			if pkg_type == "binary" and "--usepkg" not in myopts:
				continue

			# Use match instead of cp_list, to account for old-style virtuals.
			if not cp_exists and db.match(x.cp):
				cp_exists = True
			# Search for masked packages too.
			if not cp_exists and hasattr(db, "xmatch") and \
				db.xmatch("match-all", x.cp):
				cp_exists = True

			matches = db.match(x)
			matches.reverse()
			for match in matches:
				if pkg_type == "binary":
					if db.bintree.isremote(match):
						continue
				auxkeys = ["EAPI", "DEFINED_PHASES"]
				metadata = dict(zip(auxkeys, db.aux_get(match, auxkeys)))
				if metadata["EAPI"] not in ("0", "1", "2", "3") and \
					"info" in metadata["DEFINED_PHASES"].split():
					mypkgs.append((match, pkg_type))
					break

		if not cp_exists:
			xinfo = '"%s"' % x.unevaluated_atom
			# Discard null/ from failed cpv_expand category expansion.
			xinfo = xinfo.replace("null/", "")
			if settings["ROOT"] != "/":
				xinfo = "%s for %s" % (xinfo, eroot)
			writemsg("\nemerge: there are no ebuilds to satisfy %s.\n" %
				colorize("INFORM", xinfo), noiselevel=-1)

			if myopts.get("--misspell-suggestions", "y") != "n":

				writemsg("\nemerge: searching for similar names..."
					, noiselevel=-1)

				dbs = [vardb]
				#if "--usepkgonly" not in myopts:
				dbs.append(portdb)
				if "--usepkg" in myopts:
					dbs.append(bindb)

				matches = similar_name_search(dbs, x)

				if len(matches) == 1:
					writemsg("\nemerge: Maybe you meant " + matches[0] + "?\n"
						, noiselevel=-1)
				elif len(matches) > 1:
					writemsg(
						"\nemerge: Maybe you meant any of these: %s?\n" % \
						(", ".join(matches),), noiselevel=-1)
				else:
					# Generally, this would only happen if
					# all dbapis are empty.
					writemsg(" nothing similar found.\n"
						, noiselevel=-1)

			return 1

	output_buffer = []
	append = output_buffer.append
	root_config = trees[settings['EROOT']]['root_config']
	chost = settings.get("CHOST")

	append(getportageversion(settings["PORTDIR"], None,
		settings.profile_path, settings["CHOST"],
		trees[settings['EROOT']]["vartree"].dbapi))

	header_width = 65
	header_title = "System Settings"
	if myfiles:
		append(header_width * "=")
		append(header_title.rjust(int(header_width/2 + len(header_title)/2)))
	append(header_width * "=")
	append("System uname: %s" % (platform.platform(aliased=1),))

	vm_info = get_vm_info()
	if "ram.total" in vm_info:
		line = "%-9s %10d total" % ("KiB Mem:", vm_info["ram.total"] / 1024)
		if "ram.free" in vm_info:
			line += ",%10d free" % (vm_info["ram.free"] / 1024,)
		append(line)
	if "swap.total" in vm_info:
		line = "%-9s %10d total" % ("KiB Swap:", vm_info["swap.total"] / 1024)
		if "swap.free" in vm_info:
			line += ",%10d free" % (vm_info["swap.free"] / 1024,)
		append(line)

	lastSync = portage.grabfile(os.path.join(
		settings["PORTDIR"], "metadata", "timestamp.chk"))
	if lastSync:
		lastSync = lastSync[0]
	else:
		lastSync = "Unknown"
	append("Timestamp of tree: %s" % (lastSync,))

	ld_names = []
	if chost:
		ld_names.append(chost + "-ld")
	ld_names.append("ld")
	for name in ld_names:
		try:
			proc = subprocess.Popen([name, "--version"],
				stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		except OSError:
			pass
		else:
			output = _unicode_decode(proc.communicate()[0]).splitlines()
			proc.wait()
			if proc.wait() == os.EX_OK and output:
				append("ld %s" % (output[0]))
				break

	try:
		proc = subprocess.Popen(["distcc", "--version"],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	except OSError:
		output = (1, None)
	else:
		output = _unicode_decode(proc.communicate()[0]).rstrip("\n")
		output = (proc.wait(), output)
	if output[0] == os.EX_OK:
		distcc_str = output[1].split("\n", 1)[0]
		if "distcc" in settings.features:
			distcc_str += " [enabled]"
		else:
			distcc_str += " [disabled]"
		append(distcc_str)

	try:
		proc = subprocess.Popen(["ccache", "-V"],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	except OSError:
		output = (1, None)
	else:
		output = _unicode_decode(proc.communicate()[0]).rstrip("\n")
		output = (proc.wait(), output)
	if output[0] == os.EX_OK:
		ccache_str = output[1].split("\n", 1)[0]
		if "ccache" in settings.features:
			ccache_str += " [enabled]"
		else:
			ccache_str += " [disabled]"
		append(ccache_str)

	myvars  = ["sys-devel/autoconf", "sys-devel/automake", "virtual/os-headers",
	           "sys-devel/binutils", "sys-devel/libtool",  "dev-lang/python"]
	myvars += portage.util.grabfile(settings["PORTDIR"]+"/profiles/info_pkgs")
	atoms = []
	for x in myvars:
		try:
			x = Atom(x)
		except InvalidAtom:
			append("%-20s %s" % (x+":", "[NOT VALID]"))
		else:
			for atom in expand_new_virt(vardb, x):
				if not atom.blocker:
					atoms.append((x, atom))

	myvars = sorted(set(atoms))

	main_repo = portdb.getRepositoryName(portdb.porttree_root)
	cp_map = {}
	cp_max_len = 0

	for orig_atom, x in myvars:
			pkg_matches = vardb.match(x)

			versions = []
			for cpv in pkg_matches:
				matched_cp = portage.versions.cpv_getkey(cpv)
				ver = portage.versions.cpv_getversion(cpv)
				ver_map = cp_map.setdefault(matched_cp, {})
				prev_match = ver_map.get(ver)
				if prev_match is not None:
					if prev_match.provide_suffix:
						# prefer duplicate matches that include
						# additional virtual provider info
						continue

				if len(matched_cp) > cp_max_len:
					cp_max_len = len(matched_cp)
				repo = vardb.aux_get(cpv, ["repository"])[0]
				if repo == main_repo:
					repo_suffix = ""
				elif not repo:
					repo_suffix = "::<unknown repository>"
				else:
					repo_suffix = "::" + repo

				if matched_cp == orig_atom.cp:
					provide_suffix = ""
				else:
					provide_suffix = " (%s)" % (orig_atom,)

				ver_map[ver] = _info_pkgs_ver(ver, repo_suffix, provide_suffix)

	for cp in sorted(cp_map):
		versions = sorted(cp_map[cp].values())
		versions = ", ".join(ver.toString() for ver in versions)
		append("%s %s" % \
			((cp + ":").ljust(cp_max_len + 1), versions))

	repos = portdb.settings.repositories
	if "--verbose" in myopts:
		append("Repositories:\n")
		for repo in repos:
			append(repo.info_string())
	else:
		append("Repositories: %s" % \
			" ".join(repo.name for repo in repos))

	installed_sets = sorted(s for s in
		root_config.sets['selected'].getNonAtoms() if s.startswith(SETPREFIX))
	if installed_sets:
		sets_line = "Installed sets: "
		sets_line += ", ".join(installed_sets)
		append(sets_line)

	if "--verbose" in myopts:
		myvars = list(settings)
	else:
		myvars = ['GENTOO_MIRRORS', 'CONFIG_PROTECT', 'CONFIG_PROTECT_MASK',
		          'PORTDIR', 'DISTDIR', 'PKGDIR', 'PORTAGE_TMPDIR',
		          'PORTDIR_OVERLAY', 'PORTAGE_BUNZIP2_COMMAND',
		          'PORTAGE_BZIP2_COMMAND',
		          'USE', 'CHOST', 'CFLAGS', 'CXXFLAGS',
		          'ACCEPT_KEYWORDS', 'ACCEPT_LICENSE', 'FEATURES',
		          'EMERGE_DEFAULT_OPTS']

		myvars.extend(portage.util.grabfile(settings["PORTDIR"]+"/profiles/info_vars"))

	myvars_ignore_defaults = {
		'PORTAGE_BZIP2_COMMAND' : 'bzip2',
	}

	myvars = portage.util.unique_array(myvars)
	use_expand = settings.get('USE_EXPAND', '').split()
	use_expand.sort()
	unset_vars = []
	myvars.sort()
	for k in myvars:
		v = settings.get(k)
		if v is not None:
			if k != "USE":
				default = myvars_ignore_defaults.get(k)
				if default is not None and \
					default == v:
					continue
				append('%s="%s"' % (k, v))
			else:
				use = set(v.split())
				for varname in use_expand:
					flag_prefix = varname.lower() + "_"
					for f in list(use):
						if f.startswith(flag_prefix):
							use.remove(f)
				use = list(use)
				use.sort()
				use = ['USE="%s"' % " ".join(use)]
				for varname in use_expand:
					myval = settings.get(varname)
					if myval:
						use.append('%s="%s"' % (varname, myval))
				append(" ".join(use))
		else:
			unset_vars.append(k)
	if unset_vars:
		append("Unset:  "+", ".join(unset_vars))
	append("")
	append("")
	writemsg_stdout("\n".join(output_buffer),
		noiselevel=-1)
	del output_buffer[:]

	# If some packages were found...
	if mypkgs:
		# Get our global settings (we only print stuff if it varies from
		# the current config)
		mydesiredvars = [ 'CHOST', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS' ]
		auxkeys = mydesiredvars + list(vardb._aux_cache_keys)
		auxkeys.append('DEFINED_PHASES')
		pkgsettings = portage.config(clone=settings)

		# Loop through each package
		# Only print settings if they differ from global settings
		header_title = "Package Settings"
		append(header_width * "=")
		append(header_title.rjust(int(header_width/2 + len(header_title)/2)))
		append(header_width * "=")
		append("")
		writemsg_stdout("\n".join(output_buffer),
			noiselevel=-1)
		del output_buffer[:]

		out = portage.output.EOutput()
		for mypkg in mypkgs:
			cpv = mypkg[0]
			pkg_type = mypkg[1]
			# Get all package specific variables
			if pkg_type == "installed":
				metadata = dict(zip(auxkeys, vardb.aux_get(cpv, auxkeys)))
			elif pkg_type == "ebuild":
				metadata = dict(zip(auxkeys, portdb.aux_get(cpv, auxkeys)))
			elif pkg_type == "binary":
				metadata = dict(zip(auxkeys, bindb.aux_get(cpv, auxkeys)))

			pkg = Package(built=(pkg_type!="ebuild"), cpv=cpv,
				installed=(pkg_type=="installed"), metadata=zip(Package.metadata_keys,
				(metadata.get(x, '') for x in Package.metadata_keys)),
				root_config=root_config, type_name=pkg_type)

			if pkg_type == "installed":
				append("\n%s was built with the following:" % \
					colorize("INFORM", str(pkg.cpv)))
			elif pkg_type == "ebuild":
				append("\n%s would be build with the following:" % \
					colorize("INFORM", str(pkg.cpv)))
			elif pkg_type == "binary":
				append("\n%s (non-installed binary) was built with the following:" % \
					colorize("INFORM", str(pkg.cpv)))

			append('%s' % pkg_use_display(pkg, myopts))
			if pkg_type == "installed":
				for myvar in mydesiredvars:
					if metadata[myvar].split() != settings.get(myvar, '').split():
						append("%s=\"%s\"" % (myvar, metadata[myvar]))
			append("")
			append("")
			writemsg_stdout("\n".join(output_buffer),
				noiselevel=-1)
			del output_buffer[:]

			if metadata['DEFINED_PHASES']:
				if 'info' not in metadata['DEFINED_PHASES'].split():
					continue

			writemsg_stdout(">>> Attempting to run pkg_info() for '%s'\n"
				% pkg.cpv, noiselevel=-1)

			if pkg_type == "installed":
				ebuildpath = vardb.findname(pkg.cpv)
			elif pkg_type == "ebuild":
				ebuildpath = portdb.findname(pkg.cpv, myrepo=pkg.repo)
			elif pkg_type == "binary":
				tbz2_file = bindb.bintree.getname(pkg.cpv)
				ebuild_file_name = pkg.cpv.split("/")[1] + ".ebuild"
				ebuild_file_contents = portage.xpak.tbz2(tbz2_file).getfile(ebuild_file_name)
				tmpdir = tempfile.mkdtemp()
				ebuildpath = os.path.join(tmpdir, ebuild_file_name)
				file = open(ebuildpath, 'w')
				file.write(ebuild_file_contents)
				file.close()

			if not ebuildpath or not os.path.exists(ebuildpath):
				out.ewarn("No ebuild found for '%s'" % pkg.cpv)
				continue

			if pkg_type == "installed":
				portage.doebuild(ebuildpath, "info", settings=pkgsettings,
					debug=(settings.get("PORTAGE_DEBUG", "") == 1),
					mydbapi=trees[settings['EROOT']]["vartree"].dbapi,
					tree="vartree")
			elif pkg_type == "ebuild":
				portage.doebuild(ebuildpath, "info", settings=pkgsettings,
					debug=(settings.get("PORTAGE_DEBUG", "") == 1),
					mydbapi=trees[settings['EROOT']]['porttree'].dbapi,
					tree="porttree")
			elif pkg_type == "binary":
				portage.doebuild(ebuildpath, "info", settings=pkgsettings,
					debug=(settings.get("PORTAGE_DEBUG", "") == 1),
					mydbapi=trees[settings['EROOT']]["bintree"].dbapi,
					tree="bintree")
				shutil.rmtree(tmpdir)

def action_metadata(settings, portdb, myopts, porttrees=None):
	if porttrees is None:
		porttrees = portdb.porttrees
	portage.writemsg_stdout("\n>>> Updating Portage cache\n")
	old_umask = os.umask(0o002)
	cachedir = os.path.normpath(settings.depcachedir)
	if cachedir in ["/",    "/bin", "/dev",  "/etc",  "/home",
					"/lib", "/opt", "/proc", "/root", "/sbin",
					"/sys", "/tmp", "/usr",  "/var"]:
		print("!!! PORTAGE_DEPCACHEDIR IS SET TO A PRIMARY " + \
			"ROOT DIRECTORY ON YOUR SYSTEM.", file=sys.stderr)
		print("!!! This is ALMOST CERTAINLY NOT what you want: '%s'" % cachedir, file=sys.stderr)
		sys.exit(73)
	if not os.path.exists(cachedir):
		os.makedirs(cachedir)

	auxdbkeys = portdb._known_keys

	class TreeData(object):
		__slots__ = ('dest_db', 'eclass_db', 'path', 'src_db', 'valid_nodes')
		def __init__(self, dest_db, eclass_db, path, src_db):
			self.dest_db = dest_db
			self.eclass_db = eclass_db
			self.path = path
			self.src_db = src_db
			self.valid_nodes = set()

	porttrees_data = []
	for path in porttrees:
		src_db = portdb._pregen_auxdb.get(path)
		if src_db is None:
			# portdbapi does not populate _pregen_auxdb
			# when FEATURES=metadata-transfer is enabled
			src_db = portdb._create_pregen_cache(path)

		if src_db is not None:
			porttrees_data.append(TreeData(portdb.auxdb[path],
				portdb.repositories.get_repo_for_location(path).eclass_db, path, src_db))

	porttrees = [tree_data.path for tree_data in porttrees_data]

	quiet = settings.get('TERM') == 'dumb' or \
		'--quiet' in myopts or \
		not sys.stdout.isatty()

	onProgress = None
	if not quiet:
		progressBar = portage.output.TermProgressBar()
		progressHandler = ProgressHandler()
		onProgress = progressHandler.onProgress
		def display():
			progressBar.set(progressHandler.curval, progressHandler.maxval)
		progressHandler.display = display
		def sigwinch_handler(signum, frame):
			lines, progressBar.term_columns = \
				portage.output.get_term_size()
		signal.signal(signal.SIGWINCH, sigwinch_handler)

	# Temporarily override portdb.porttrees so portdb.cp_all()
	# will only return the relevant subset.
	portdb_porttrees = portdb.porttrees
	portdb.porttrees = porttrees
	try:
		cp_all = portdb.cp_all()
	finally:
		portdb.porttrees = portdb_porttrees

	curval = 0
	maxval = len(cp_all)
	if onProgress is not None:
		onProgress(maxval, curval)

	# TODO: Display error messages, but do not interfere with the progress bar.
	# Here's how:
	#  1) erase the progress bar
	#  2) show the error message
	#  3) redraw the progress bar on a new line

	for cp in cp_all:
		for tree_data in porttrees_data:

			src_chf = tree_data.src_db.validation_chf
			dest_chf = tree_data.dest_db.validation_chf
			dest_chf_key = '_%s_' % dest_chf
			dest_chf_getter = operator.attrgetter(dest_chf)

			for cpv in portdb.cp_list(cp, mytree=tree_data.path):
				tree_data.valid_nodes.add(cpv)
				try:
					src = tree_data.src_db[cpv]
				except (CacheError, KeyError):
					continue

				ebuild_location = portdb.findname(cpv, mytree=tree_data.path)
				if ebuild_location is None:
					continue
				ebuild_hash = hashed_path(ebuild_location)

				try:
					if not tree_data.src_db.validate_entry(src,
						ebuild_hash, tree_data.eclass_db):
						continue
				except CacheError:
					continue

				eapi = src.get('EAPI')
				if not eapi:
					eapi = '0'
				eapi_supported = eapi_is_supported(eapi)
				if not eapi_supported:
					continue

				dest = None
				try:
					dest = tree_data.dest_db[cpv]
				except (KeyError, CacheError):
					pass

				for d in (src, dest):
					if d is not None and d.get('EAPI') in ('', '0'):
						del d['EAPI']

				if src_chf != 'mtime':
					# src may contain an irrelevant _mtime_ which corresponds
					# to the time that the cache entry was written
					src.pop('_mtime_', None)

				if src_chf != dest_chf:
					# populate src entry with dest_chf_key
					# (the validity of the dest_chf that we generate from the
					# ebuild here relies on the fact that we already used
					# validate_entry to validate the ebuild with src_chf)
					src[dest_chf_key] = dest_chf_getter(ebuild_hash)

				if dest is not None:
					if not (dest[dest_chf_key] == src[dest_chf_key] and \
						tree_data.eclass_db.validate_and_rewrite_cache(
							dest['_eclasses_'], tree_data.dest_db.validation_chf,
							tree_data.dest_db.store_eclass_paths) is not None and \
						set(dest['_eclasses_']) == set(src['_eclasses_'])):
						dest = None
					else:
						# We don't want to skip the write unless we're really
						# sure that the existing cache is identical, so don't
						# trust _mtime_ and _eclasses_ alone.
						for k in auxdbkeys:
							if dest.get(k, '') != src.get(k, ''):
								dest = None
								break

				if dest is not None:
					# The existing data is valid and identical,
					# so there's no need to overwrite it.
					continue

				try:
					tree_data.dest_db[cpv] = src
				except CacheError:
					# ignore it; can't do anything about it.
					pass

		curval += 1
		if onProgress is not None:
			onProgress(maxval, curval)

	if onProgress is not None:
		onProgress(maxval, curval)

	for tree_data in porttrees_data:
		try:
			dead_nodes = set(tree_data.dest_db)
		except CacheError as e:
			writemsg_level("Error listing cache entries for " + \
				"'%s': %s, continuing...\n" % (tree_data.path, e),
				level=logging.ERROR, noiselevel=-1)
			del e
		else:
			dead_nodes.difference_update(tree_data.valid_nodes)
			for cpv in dead_nodes:
				try:
					del tree_data.dest_db[cpv]
				except (KeyError, CacheError):
					pass

	if not quiet:
		# make sure the final progress is displayed
		progressHandler.display()
		print()
		signal.signal(signal.SIGWINCH, signal.SIG_DFL)

	portdb.flush_cache()
	sys.stdout.flush()
	os.umask(old_umask)

def action_regen(settings, portdb, max_jobs, max_load):
	xterm_titles = "notitles" not in settings.features
	emergelog(xterm_titles, " === regen")
	#regenerate cache entries
	sys.stdout.flush()

	regen = MetadataRegen(portdb, max_jobs=max_jobs,
		max_load=max_load, main=True)

	signum = run_main_scheduler(regen)
	if signum is not None:
		sys.exit(128 + signum)

	portage.writemsg_stdout("done!\n")
	return regen.returncode

def action_search(root_config, myopts, myfiles, spinner):
	if not myfiles:
		print("emerge: no search terms provided.")
	else:
		searchinstance = search(root_config,
			spinner, "--searchdesc" in myopts,
			"--quiet" not in myopts, "--usepkg" in myopts,
			"--usepkgonly" in myopts)
		for mysearch in myfiles:
			try:
				searchinstance.execute(mysearch)
			except re.error as comment:
				print("\n!!! Regular expression error in \"%s\": %s" % ( mysearch, comment ))
				sys.exit(1)
			searchinstance.output()

def action_sync(emerge_config, trees=DeprecationWarning,
	mtimedb=DeprecationWarning, opts=DeprecationWarning,
	action=DeprecationWarning):

	if not isinstance(emerge_config, _emerge_config):
		warnings.warn("_emerge.actions.action_sync() now expects "
			"an _emerge_config instance as the first parameter",
			DeprecationWarning, stacklevel=2)
		emerge_config = load_emerge_config(
			action=action, args=[], trees=trees, opts=opts)

	xterm_titles = "notitles" not in \
		emerge_config.target_config.settings.features
	emergelog(xterm_titles, " === sync")

	selected_repos = []
	unknown_repo_names = []
	missing_sync_type = []
	if emerge_config.args:
		for repo_name in emerge_config.args:
			try:
				repo = emerge_config.target_config.settings.repositories[repo_name]
			except KeyError:
				unknown_repo_names.append(repo_name)
			else:
				selected_repos.append(repo)
				if repo.sync_type is None:
					missing_sync_type.append(repo)

		if unknown_repo_names:
			writemsg_level("!!! %s\n" % _("Unknown repo(s): %s") %
				" ".join(unknown_repo_names),
				level=logging.ERROR, noiselevel=-1)

		if missing_sync_type:
			writemsg_level("!!! %s\n" %
				_("Missing sync-type for repo(s): %s") %
				" ".join(repo.name for repo in missing_sync_type),
				level=logging.ERROR, noiselevel=-1)

		if unknown_repo_names or missing_sync_type:
			return 1

	else:
		selected_repos.extend(emerge_config.target_config.settings.repositories)

	for repo in selected_repos:
		if repo.sync_type is not None:
			returncode = _sync_repo(emerge_config, repo)
			if returncode != os.EX_OK:
				return returncode

	# Reload the whole config from scratch.
	portage._sync_mode = False
	load_emerge_config(emerge_config=emerge_config)
	adjust_configs(emerge_config.opts, emerge_config.trees)

	if emerge_config.opts.get('--package-moves') != 'n' and \
		_global_updates(emerge_config.trees,
		emerge_config.target_config.mtimedb["updates"],
		quiet=("--quiet" in emerge_config.opts)):
		emerge_config.target_config.mtimedb.commit()
		# Reload the whole config from scratch.
		load_emerge_config(emerge_config=emerge_config)
		adjust_configs(emerge_config.opts, emerge_config.trees)

	mybestpv = emerge_config.target_config.trees['porttree'].dbapi.xmatch(
		"bestmatch-visible", portage.const.PORTAGE_PACKAGE_ATOM)
	mypvs = portage.best(
		emerge_config.target_config.trees['vartree'].dbapi.match(
			portage.const.PORTAGE_PACKAGE_ATOM))

	chk_updated_cfg_files(emerge_config.target_config.root,
		portage.util.shlex_split(
			emerge_config.target_config.settings.get("CONFIG_PROTECT", "")))

	if mybestpv != mypvs and "--quiet" not in emerge_config.opts:
		print()
		print(warn(" * ")+bold("An update to portage is available.")+" It is _highly_ recommended")
		print(warn(" * ")+"that you update portage now, before any other packages are updated.")
		print()
		print(warn(" * ")+"To update portage, run 'emerge --oneshot portage' now.")
		print()

	display_news_notification(emerge_config.target_config, emerge_config.opts)
	return os.EX_OK

def _sync_repo(emerge_config, repo):
	settings, trees, mtimedb = emerge_config
	myopts = emerge_config.opts
	enter_invalid = '--ask-enter-invalid' in myopts
	xterm_titles = "notitles" not in settings.features
	msg = ">>> Synchronization of repository '%s' located in '%s'..." % (repo.name, repo.location)
	emergelog(xterm_titles, msg)
	writemsg_level(msg + "\n")
	out = portage.output.EOutput()
	try:
		st = os.stat(repo.location)
	except OSError:
		st = None
	if st is None:
		print(">>> '%s' not found, creating it." % repo.location)
		portage.util.ensure_dirs(repo.location, mode=0o755)
		st = os.stat(repo.location)

	usersync_uid = None
	spawn_kwargs = {}
	spawn_kwargs["env"] = settings.environ()
	if 'usersync' in settings.features and \
		portage.data.secpass >= 2 and \
		(st.st_uid != os.getuid() and st.st_mode & 0o700 or \
		st.st_gid != os.getgid() and st.st_mode & 0o070):
		try:
			homedir = pwd.getpwuid(st.st_uid).pw_dir
		except KeyError:
			pass
		else:
			# Drop privileges when syncing, in order to match
			# existing uid/gid settings.
			usersync_uid = st.st_uid
			spawn_kwargs["uid"]    = st.st_uid
			spawn_kwargs["gid"]    = st.st_gid
			spawn_kwargs["groups"] = [st.st_gid]
			spawn_kwargs["env"]["HOME"] = homedir
			umask = 0o002
			if not st.st_mode & 0o020:
				umask = umask | 0o020
			spawn_kwargs["umask"] = umask

	if usersync_uid is not None:
		# PORTAGE_TMPDIR is used below, so validate it and
		# bail out if necessary.
		rval = _check_temp_dir(settings)
		if rval != os.EX_OK:
			return rval

	syncuri = repo.sync_uri

	vcs_dirs = frozenset(VCS_DIRS)
	vcs_dirs = vcs_dirs.intersection(os.listdir(repo.location))

	os.umask(0o022)
	dosyncuri = syncuri
	updatecache_flg = False
	if repo.sync_type == "git":
		# Update existing git repository, and ignore the syncuri. We are
		# going to trust the user and assume that the user is in the branch
		# that he/she wants updated. We'll let the user manage branches with
		# git directly.
		if portage.process.find_binary("git") is None:
			msg = ["Command not found: git",
			"Type \"emerge %s\" to enable git support." % portage.const.GIT_PACKAGE_ATOM]
			for l in msg:
				writemsg_level("!!! %s\n" % l,
					level=logging.ERROR, noiselevel=-1)
			return 1
		msg = ">>> Starting git pull in %s..." % repo.location
		emergelog(xterm_titles, msg )
		writemsg_level(msg + "\n")
		exitcode = portage.process.spawn_bash("cd %s ; git pull" % \
			(portage._shell_quote(repo.location),),
			**portage._native_kwargs(spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! git pull error in %s." % repo.location
			emergelog(xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return exitcode
		msg = ">>> Git pull in %s successful" % repo.location
		emergelog(xterm_titles, msg)
		writemsg_level(msg + "\n")
	elif repo.sync_type == "rsync":
		for vcs_dir in vcs_dirs:
			writemsg_level(("!!! %s appears to be under revision " + \
				"control (contains %s).\n!!! Aborting rsync sync.\n") % \
				(repo.location, vcs_dir), level=logging.ERROR, noiselevel=-1)
			return 1
		rsync_binary = portage.process.find_binary("rsync")
		if rsync_binary is None:
			print("!!! /usr/bin/rsync does not exist, so rsync support is disabled.")
			print("!!! Type \"emerge %s\" to enable rsync support." % portage.const.RSYNC_PACKAGE_ATOM)
			return os.EX_UNAVAILABLE
		mytimeout=180

		rsync_opts = []
		if settings["PORTAGE_RSYNC_OPTS"] == "":
			portage.writemsg("PORTAGE_RSYNC_OPTS empty or unset, using hardcoded defaults\n")
			rsync_opts.extend([
				"--recursive",    # Recurse directories
				"--links",        # Consider symlinks
				"--safe-links",   # Ignore links outside of tree
				"--perms",        # Preserve permissions
				"--times",        # Preserive mod times
				"--omit-dir-times",
				"--compress",     # Compress the data transmitted
				"--force",        # Force deletion on non-empty dirs
				"--whole-file",   # Don't do block transfers, only entire files
				"--delete",       # Delete files that aren't in the master tree
				"--stats",        # Show final statistics about what was transfered
				"--human-readable",
				"--timeout="+str(mytimeout), # IO timeout if not done in X seconds
				"--exclude=/distfiles",   # Exclude distfiles from consideration
				"--exclude=/local",       # Exclude local     from consideration
				"--exclude=/packages",    # Exclude packages  from consideration
			])

		else:
			# The below validation is not needed when using the above hardcoded
			# defaults.

			portage.writemsg("Using PORTAGE_RSYNC_OPTS instead of hardcoded defaults\n", 1)
			rsync_opts.extend(portage.util.shlex_split(
				settings.get("PORTAGE_RSYNC_OPTS", "")))
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

		# Real local timestamp file.
		servertimestampfile = os.path.join(
			repo.location, "metadata", "timestamp.chk")

		content = portage.util.grabfile(servertimestampfile)
		mytimestamp = 0
		if content:
			try:
				mytimestamp = time.mktime(time.strptime(content[0],
					TIMESTAMP_FORMAT))
			except (OverflowError, ValueError):
				pass
		del content

		try:
			rsync_initial_timeout = \
				int(settings.get("PORTAGE_RSYNC_INITIAL_TIMEOUT", "15"))
		except ValueError:
			rsync_initial_timeout = 15

		try:
			maxretries=int(settings["PORTAGE_RSYNC_RETRIES"])
		except SystemExit as e:
			raise # Needed else can't exit
		except:
			maxretries = -1 #default number of retries

		retries=0
		try:
			proto, user_name, hostname, port = re.split(
				r"(rsync|ssh)://([^:/]+@)?(\[[:\da-fA-F]*\]|[^:/]*)(:[0-9]+)?",
				syncuri, maxsplit=4)[1:5]
		except ValueError:
			writemsg_level("!!! sync-uri is invalid: %s\n" % syncuri,
				noiselevel=-1, level=logging.ERROR)
			return 1

		ssh_opts = settings.get("PORTAGE_SSH_OPTS")

		if port is None:
			port=""
		if user_name is None:
			user_name=""
		if re.match(r"^\[[:\da-fA-F]*\]$", hostname) is None:
			getaddrinfo_host = hostname
		else:
			# getaddrinfo needs the brackets stripped
			getaddrinfo_host = hostname[1:-1]
		updatecache_flg=True
		all_rsync_opts = set(rsync_opts)
		extra_rsync_opts = portage.util.shlex_split(
			settings.get("PORTAGE_RSYNC_EXTRA_OPTS",""))
		all_rsync_opts.update(extra_rsync_opts)

		family = socket.AF_UNSPEC
		if "-4" in all_rsync_opts or "--ipv4" in all_rsync_opts:
			family = socket.AF_INET
		elif socket.has_ipv6 and \
			("-6" in all_rsync_opts or "--ipv6" in all_rsync_opts):
			family = socket.AF_INET6

		addrinfos = None
		uris = []

		try:
			addrinfos = getaddrinfo_validate(
				socket.getaddrinfo(getaddrinfo_host, None,
				family, socket.SOCK_STREAM))
		except socket.error as e:
			writemsg_level(
				"!!! getaddrinfo failed for '%s': %s\n" % (hostname, e),
				noiselevel=-1, level=logging.ERROR)

		if addrinfos:

			AF_INET = socket.AF_INET
			AF_INET6 = None
			if socket.has_ipv6:
				AF_INET6 = socket.AF_INET6

			ips_v4 = []
			ips_v6 = []

			for addrinfo in addrinfos:
				if addrinfo[0] == AF_INET:
					ips_v4.append("%s" % addrinfo[4][0])
				elif AF_INET6 is not None and addrinfo[0] == AF_INET6:
					# IPv6 addresses need to be enclosed in square brackets
					ips_v6.append("[%s]" % addrinfo[4][0])

			random.shuffle(ips_v4)
			random.shuffle(ips_v6)

			# Give priority to the address family that
			# getaddrinfo() returned first.
			if AF_INET6 is not None and addrinfos and \
				addrinfos[0][0] == AF_INET6:
				ips = ips_v6 + ips_v4
			else:
				ips = ips_v4 + ips_v6

			for ip in ips:
				uris.append(syncuri.replace(
					"//" + user_name + hostname + port + "/",
					"//" + user_name + ip + port + "/", 1))

		if not uris:
			# With some configurations we need to use the plain hostname
			# rather than try to resolve the ip addresses (bug #340817).
			uris.append(syncuri)

		# reverse, for use with pop()
		uris.reverse()

		effective_maxretries = maxretries
		if effective_maxretries < 0:
			effective_maxretries = len(uris) - 1

		SERVER_OUT_OF_DATE = -1
		EXCEEDED_MAX_RETRIES = -2
		while (1):
			if uris:
				dosyncuri = uris.pop()
			else:
				writemsg("!!! Exhausted addresses for %s\n" % \
					hostname, noiselevel=-1)
				return 1

			if (retries==0):
				if "--ask" in myopts:
					if userquery("Do you want to sync your Portage tree " + \
						"with the mirror at\n" + blue(dosyncuri) + bold("?"),
						enter_invalid) == "No":
						print()
						print("Quitting.")
						print()
						sys.exit(128 + signal.SIGINT)
				emergelog(xterm_titles, ">>> Starting rsync with " + dosyncuri)
				if "--quiet" not in myopts:
					print(">>> Starting rsync with "+dosyncuri+"...")
			else:
				emergelog(xterm_titles,
					">>> Starting retry %d of %d with %s" % \
						(retries, effective_maxretries, dosyncuri))
				writemsg_stdout(
					"\n\n>>> Starting retry %d of %d with %s\n" % \
					(retries, effective_maxretries, dosyncuri), noiselevel=-1)

			if dosyncuri.startswith('ssh://'):
				dosyncuri = dosyncuri[6:].replace('/', ':/', 1)

			if mytimestamp != 0 and "--quiet" not in myopts:
				print(">>> Checking server timestamp ...")

			rsynccommand = [rsync_binary] + rsync_opts + extra_rsync_opts

			if proto == 'ssh' and ssh_opts:
				rsynccommand.append("--rsh=ssh " + ssh_opts)

			if "--debug" in myopts:
				print(rsynccommand)

			exitcode = os.EX_OK
			servertimestamp = 0
			# Even if there's no timestamp available locally, fetch the
			# timestamp anyway as an initial probe to verify that the server is
			# responsive.  This protects us from hanging indefinitely on a
			# connection attempt to an unresponsive server which rsync's
			# --timeout option does not prevent.
			if True:
				# Temporary file for remote server timestamp comparison.
				# NOTE: If FEATURES=usersync is enabled then the tempfile
				# needs to be in a directory that's readable by the usersync
				# user. We assume that PORTAGE_TMPDIR will satisfy this
				# requirement, since that's not necessarily true for the
				# default directory used by the tempfile module.
				if usersync_uid is not None:
					tmpdir = settings['PORTAGE_TMPDIR']
				else:
					# use default dir from tempfile module
					tmpdir = None
				fd, tmpservertimestampfile = \
					tempfile.mkstemp(dir=tmpdir)
				os.close(fd)
				if usersync_uid is not None:
					portage.util.apply_permissions(tmpservertimestampfile,
						uid=usersync_uid)
				mycommand = rsynccommand[:]
				mycommand.append(dosyncuri.rstrip("/") + \
					"/metadata/timestamp.chk")
				mycommand.append(tmpservertimestampfile)
				content = None
				mypids = []
				try:
					# Timeout here in case the server is unresponsive.  The
					# --timeout rsync option doesn't apply to the initial
					# connection attempt.
					try:
						if rsync_initial_timeout:
							portage.exception.AlarmSignal.register(
								rsync_initial_timeout)

						mypids.extend(portage.process.spawn(
							mycommand, returnpid=True,
							**portage._native_kwargs(spawn_kwargs)))
						exitcode = os.waitpid(mypids[0], 0)[1]
						if usersync_uid is not None:
							portage.util.apply_permissions(tmpservertimestampfile,
								uid=os.getuid())
						content = portage.grabfile(tmpservertimestampfile)
					finally:
						if rsync_initial_timeout:
							portage.exception.AlarmSignal.unregister()
						try:
							os.unlink(tmpservertimestampfile)
						except OSError:
							pass
				except portage.exception.AlarmSignal:
					# timed out
					print('timed out')
					# With waitpid and WNOHANG, only check the
					# first element of the tuple since the second
					# element may vary (bug #337465).
					if mypids and os.waitpid(mypids[0], os.WNOHANG)[0] == 0:
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

				if content:
					try:
						servertimestamp = time.mktime(time.strptime(
							content[0], TIMESTAMP_FORMAT))
					except (OverflowError, ValueError):
						pass
				del mycommand, mypids, content
			if exitcode == os.EX_OK:
				if (servertimestamp != 0) and (servertimestamp == mytimestamp):
					emergelog(xterm_titles,
						">>> Cancelling sync -- Already current.")
					print()
					print(">>>")
					print(">>> Timestamps on the server and in the local repository are the same.")
					print(">>> Cancelling all further sync action. You are already up to date.")
					print(">>>")
					print(">>> In order to force sync, remove '%s'." % servertimestampfile)
					print(">>>")
					print()
					return os.EX_OK
				elif (servertimestamp != 0) and (servertimestamp < mytimestamp):
					emergelog(xterm_titles,
						">>> Server out of date: %s" % dosyncuri)
					print()
					print(">>>")
					print(">>> SERVER OUT OF DATE: %s" % dosyncuri)
					print(">>>")
					print(">>> In order to force sync, remove '%s'." % servertimestampfile)
					print(">>>")
					print()
					exitcode = SERVER_OUT_OF_DATE
				elif (servertimestamp == 0) or (servertimestamp > mytimestamp):
					# actual sync
					mycommand = rsynccommand + [dosyncuri+"/", repo.location]
					exitcode = None
					try:
						exitcode = portage.process.spawn(mycommand,
							**portage._native_kwargs(spawn_kwargs))
					finally:
						if exitcode is None:
							# interrupted
							exitcode = 128 + signal.SIGINT

						#   0	Success
						#   1	Syntax or usage error
						#   2	Protocol incompatibility
						#   5	Error starting client-server protocol
						#  35	Timeout waiting for daemon connection
						if exitcode not in (0, 1, 2, 5, 35):
							# If the exit code is not among those listed above,
							# then we may have a partial/inconsistent sync
							# state, so our previously read timestamp as well
							# as the corresponding file can no longer be
							# trusted.
							mytimestamp = 0
							try:
								os.unlink(servertimestampfile)
							except OSError:
								pass

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

			if maxretries < 0 or retries <= maxretries:
				print(">>> Retrying...")
			else:
				# over retries
				# exit loop
				updatecache_flg=False
				exitcode = EXCEEDED_MAX_RETRIES
				break

		if (exitcode==0):
			emergelog(xterm_titles, "=== Sync completed with %s" % dosyncuri)
		elif exitcode == SERVER_OUT_OF_DATE:
			return 1
		elif exitcode == EXCEEDED_MAX_RETRIES:
			sys.stderr.write(
				">>> Exceeded PORTAGE_RSYNC_RETRIES: %s\n" % maxretries)
			return 1
		elif (exitcode>0):
			msg = []
			if exitcode==1:
				msg.append("Rsync has reported that there is a syntax error. Please ensure")
				msg.append("that sync-uri attribute for repository '%s' is proper." % repo.name)
				msg.append("sync-uri: '%s'" % repo.sync_uri)
			elif exitcode==11:
				msg.append("Rsync has reported that there is a File IO error. Normally")
				msg.append("this means your disk is full, but can be caused by corruption")
				msg.append("on the filesystem that contains repository '%s'. Please investigate" % repo.name)
				msg.append("and try again after the problem has been fixed.")
				msg.append("Location of repository: '%s'" % repo.location)
			elif exitcode==20:
				msg.append("Rsync was killed before it finished.")
			else:
				msg.append("Rsync has not successfully finished. It is recommended that you keep")
				msg.append("trying or that you use the 'emerge-webrsync' option if you are unable")
				msg.append("to use rsync due to firewall or other restrictions. This should be a")
				msg.append("temporary problem unless complications exist with your network")
				msg.append("(and possibly your system's filesystem) configuration.")
			for line in msg:
				out.eerror(line)
			return exitcode
	elif repo.sync_type == "cvs":
		if not os.path.exists(EPREFIX + "/usr/bin/cvs"):
			print("!!! %s/usr/bin/cvs does not exist, so CVS support is disabled." % (EPREFIX))
			print("!!! Type \"emerge %s\" to enable CVS support." % portage.const.CVS_PACKAGE_ATOM)
			return os.EX_UNAVAILABLE
		cvs_root = syncuri
		if cvs_root.startswith("cvs://"):
			cvs_root = cvs_root[6:]
		if not os.path.exists(os.path.join(repo.location, "CVS")):
			#initial checkout
			print(">>> Starting initial cvs checkout with "+syncuri+"...")
			try:
				os.rmdir(repo.location)
			except OSError as e:
				if e.errno != errno.ENOENT:
					sys.stderr.write(
						"!!! existing '%s' directory; exiting.\n" % repo.location)
					return 1
				del e
			if portage.process.spawn_bash(
					"cd %s; exec cvs -z0 -d %s co -P -d %s %s" %
					(portage._shell_quote(os.path.dirname(repo.location)), portage._shell_quote(cvs_root),
					portage._shell_quote(os.path.basename(repo.location)), portage._shell_quote(repo.sync_cvs_repo)),
					**portage._native_kwargs(spawn_kwargs)) != os.EX_OK:
				print("!!! cvs checkout error; exiting.")
				return 1
		else:
			#cvs update
			print(">>> Starting cvs update with "+syncuri+"...")
			retval = portage.process.spawn_bash(
				"cd %s; exec cvs -z0 -q update -dP" % \
				(portage._shell_quote(repo.location),),
				**portage._native_kwargs(spawn_kwargs))
			if retval != os.EX_OK:
				writemsg_level("!!! cvs update error; exiting.\n",
					noiselevel=-1, level=logging.ERROR)
				return retval
		dosyncuri = syncuri

	# Reload the whole config from scratch.
	settings, trees, mtimedb = load_emerge_config(emerge_config=emerge_config)
	adjust_configs(emerge_config.opts, emerge_config.trees)
	portdb = trees[settings['EROOT']]['porttree'].dbapi

	if repo.sync_type == "git":
		# NOTE: Do this after reloading the config, in case
		# it did not exist prior to sync, so that the config
		# and portdb properly account for its existence.
		exitcode = git_sync_timestamps(portdb, repo.location)
		if exitcode == os.EX_OK:
			updatecache_flg = True

	if updatecache_flg and "metadata-transfer" not in settings.features:
		updatecache_flg = False

	if updatecache_flg and \
		os.path.exists(os.path.join(repo.location, 'metadata', 'cache')):

		# Only update cache for repo.location since that's
		# the only one that's been synced here.
		action_metadata(settings, portdb, myopts, porttrees=[repo.location])

	postsync = os.path.join(settings["PORTAGE_CONFIGROOT"], portage.USER_CONFIG_PATH, "bin", "post_sync")
	if os.access(postsync, os.X_OK):
		retval = portage.process.spawn([postsync, dosyncuri], env=settings.environ())
		if retval != os.EX_OK:
			writemsg_level(" %s spawn failed of %s\n" % (bad("*"), postsync,),
				level=logging.ERROR, noiselevel=-1)

	return os.EX_OK

def action_uninstall(settings, trees, ldpath_mtimes,
	opts, action, files, spinner):
	# For backward compat, some actions do not require leading '='.
	ignore_missing_eq = action in ('clean', 'unmerge')
	root = settings['ROOT']
	eroot = settings['EROOT']
	vardb = trees[settings['EROOT']]['vartree'].dbapi
	valid_atoms = []
	lookup_owners = []

	# Ensure atoms are valid before calling unmerge().
	# For backward compat, leading '=' is not required.
	for x in files:
		if is_valid_package_atom(x, allow_repo=True) or \
			(ignore_missing_eq and is_valid_package_atom('=' + x)):

			try:
				atom = dep_expand(x, mydb=vardb, settings=settings)
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
			else:
				if atom.use and atom.use.conditional:
					writemsg_level(
						("\n\n!!! '%s' contains a conditional " + \
						"which is not allowed.\n") % (x,),
						level=logging.ERROR, noiselevel=-1)
					writemsg_level(
						"!!! Please check ebuild(5) for full details.\n",
						level=logging.ERROR)
					return 1
				valid_atoms.append(atom)

		elif x.startswith(os.sep):
			if not x.startswith(eroot):
				writemsg_level(("!!! '%s' does not start with" + \
					" $EROOT.\n") % x, level=logging.ERROR, noiselevel=-1)
				return 1
			# Queue these up since it's most efficient to handle
			# multiple files in a single iter_owners() call.
			lookup_owners.append(x)

		elif x.startswith(SETPREFIX) and action == "deselect":
			valid_atoms.append(x)

		elif "*" in x:
			try:
				ext_atom = Atom(x, allow_repo=True, allow_wildcard=True)
			except InvalidAtom:
				msg = []
				msg.append("'%s' is not a valid package atom." % (x,))
				msg.append("Please check ebuild(5) for full details.")
				writemsg_level("".join("!!! %s\n" % line for line in msg),
					level=logging.ERROR, noiselevel=-1)
				return 1

			for cpv in vardb.cpv_all():
				if portage.match_from_list(ext_atom, [cpv]):
					require_metadata = False
					atom = portage.cpv_getkey(cpv)
					if ext_atom.operator == '=*':
						atom = "=" + atom + "-" + \
							portage.versions.cpv_getversion(cpv)
					if ext_atom.slot:
						atom += ":" + ext_atom.slot
						require_metadata = True
					if ext_atom.repo:
						atom += "::" + ext_atom.repo
						require_metadata = True

					atom = Atom(atom, allow_repo=True)
					if require_metadata:
						try:
							cpv = vardb._pkg_str(cpv, ext_atom.repo)
						except (KeyError, InvalidData):
							continue
						if not portage.match_from_list(atom, [cpv]):
							continue

					valid_atoms.append(atom)

		else:
			msg = []
			msg.append("'%s' is not a valid package atom." % (x,))
			msg.append("Please check ebuild(5) for full details.")
			writemsg_level("".join("!!! %s\n" % line for line in msg),
				level=logging.ERROR, noiselevel=-1)
			return 1

	if lookup_owners:
		relative_paths = []
		search_for_multiple = False
		if len(lookup_owners) > 1:
			search_for_multiple = True

		for x in lookup_owners:
			if not search_for_multiple and os.path.isdir(x):
				search_for_multiple = True
			relative_paths.append(x[len(root)-1:])

		owners = set()
		for pkg, relative_path in \
			vardb._owners.iter_owners(relative_paths):
			owners.add(pkg.mycpv)
			if not search_for_multiple:
				break

		if owners:
			for cpv in owners:
				pkg = vardb._pkg_str(cpv, None)
				atom = '%s:%s' % (pkg.cp, pkg.slot)
				valid_atoms.append(portage.dep.Atom(atom))
		else:
			writemsg_level(("!!! '%s' is not claimed " + \
				"by any package.\n") % lookup_owners[0],
				level=logging.WARNING, noiselevel=-1)

	if files and not valid_atoms:
		return 1

	if action == 'unmerge' and \
		'--quiet' not in opts and \
		'--quiet-unmerge-warn' not in opts:
		msg = "This action can remove important packages! " + \
			"In order to be safer, use " + \
			"`emerge -pv --depclean <atom>` to check for " + \
			"reverse dependencies before removing packages."
		out = portage.output.EOutput()
		for line in textwrap.wrap(msg, 72):
			out.ewarn(line)

	if action == 'deselect':
		return action_deselect(settings, trees, opts, valid_atoms)

	# Use the same logic as the Scheduler class to trigger redirection
	# of ebuild pkg_prerm/postrm phase output to logs as appropriate
	# for options such as --jobs, --quiet and --quiet-build.
	max_jobs = opts.get("--jobs", 1)
	background = (max_jobs is True or max_jobs > 1 or
		"--quiet" in opts or opts.get("--quiet-build") == "y")
	sched_iface = SchedulerInterface(global_event_loop(),
		is_background=lambda: background)

	if background:
		settings.unlock()
		settings["PORTAGE_BACKGROUND"] = "1"
		settings.backup_changes("PORTAGE_BACKGROUND")
		settings.lock()

	if action in ('clean', 'unmerge') or \
		(action == 'prune' and "--nodeps" in opts):
		# When given a list of atoms, unmerge them in the order given.
		ordered = action == 'unmerge'
		rval = unmerge(trees[settings['EROOT']]['root_config'], opts, action,
			valid_atoms, ldpath_mtimes, ordered=ordered,
			scheduler=sched_iface)
	else:
		rval = action_depclean(settings, trees, ldpath_mtimes,
			opts, action, valid_atoms, spinner,
			scheduler=sched_iface)

	return rval

def adjust_configs(myopts, trees):
	for myroot in trees:
		mysettings =  trees[myroot]["vartree"].settings
		mysettings.unlock()
		adjust_config(myopts, mysettings)
		mysettings.lock()

def adjust_config(myopts, settings):
	"""Make emerge specific adjustments to the config."""

	# Kill noauto as it will break merges otherwise.
	if "noauto" in settings.features:
		settings.features.remove('noauto')

	fail_clean = myopts.get('--fail-clean')
	if fail_clean is not None:
		if fail_clean is True and \
			'fail-clean' not in settings.features:
			settings.features.add('fail-clean')
		elif fail_clean == 'n' and \
			'fail-clean' in settings.features:
			settings.features.remove('fail-clean')

	CLEAN_DELAY = 5
	try:
		CLEAN_DELAY = int(settings.get("CLEAN_DELAY", str(CLEAN_DELAY)))
	except ValueError as e:
		portage.writemsg("!!! %s\n" % str(e), noiselevel=-1)
		portage.writemsg("!!! Unable to parse integer: CLEAN_DELAY='%s'\n" % \
			settings["CLEAN_DELAY"], noiselevel=-1)
	settings["CLEAN_DELAY"] = str(CLEAN_DELAY)
	settings.backup_changes("CLEAN_DELAY")

	EMERGE_WARNING_DELAY = 10
	try:
		EMERGE_WARNING_DELAY = int(settings.get(
			"EMERGE_WARNING_DELAY", str(EMERGE_WARNING_DELAY)))
	except ValueError as e:
		portage.writemsg("!!! %s\n" % str(e), noiselevel=-1)
		portage.writemsg("!!! Unable to parse integer: EMERGE_WARNING_DELAY='%s'\n" % \
			settings["EMERGE_WARNING_DELAY"], noiselevel=-1)
	settings["EMERGE_WARNING_DELAY"] = str(EMERGE_WARNING_DELAY)
	settings.backup_changes("EMERGE_WARNING_DELAY")

	buildpkg = myopts.get("--buildpkg")
	if buildpkg is True:
		settings.features.add("buildpkg")
	elif buildpkg == 'n':
		settings.features.discard("buildpkg")

	if "--quiet" in myopts:
		settings["PORTAGE_QUIET"]="1"
		settings.backup_changes("PORTAGE_QUIET")

	if "--verbose" in myopts:
		settings["PORTAGE_VERBOSE"] = "1"
		settings.backup_changes("PORTAGE_VERBOSE")

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
	except ValueError as e:
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

	# The explicit --color < y | n > option overrides the NOCOLOR environment
	# variable and stdout auto-detection.
	if "--color" in myopts:
		if "y" == myopts["--color"]:
			portage.output.havecolor = 1
			settings["NOCOLOR"] = "false"
		else:
			portage.output.havecolor = 0
			settings["NOCOLOR"] = "true"
		settings.backup_changes("NOCOLOR")
	elif settings.get('TERM') == 'dumb' or \
		not sys.stdout.isatty():
		portage.output.havecolor = 0
		settings["NOCOLOR"] = "true"
		settings.backup_changes("NOCOLOR")

	if "--pkg-format" in myopts:
		settings["PORTAGE_BINPKG_FORMAT"] = myopts["--pkg-format"]
		settings.backup_changes("PORTAGE_BINPKG_FORMAT")

def display_missing_pkg_set(root_config, set_name):

	msg = []
	msg.append(("emerge: There are no sets to satisfy '%s'. " + \
		"The following sets exist:") % \
		colorize("INFORM", set_name))
	msg.append("")

	for s in sorted(root_config.sets):
		msg.append("    %s" % s)
	msg.append("")

	writemsg_level("".join("%s\n" % l for l in msg),
		level=logging.ERROR, noiselevel=-1)

def relative_profile_path(portdir, abs_profile):
	realpath = os.path.realpath(abs_profile)
	basepath   = os.path.realpath(os.path.join(portdir, "profiles"))
	if realpath.startswith(basepath):
		profilever = realpath[1 + len(basepath):]
	else:
		profilever = None
	return profilever

def getportageversion(portdir, _unused, profile, chost, vardb):
	pythonver = 'python %d.%d.%d-%s-%d' % sys.version_info[:]
	profilever = None
	repositories = vardb.settings.repositories
	if profile:
		profilever = relative_profile_path(portdir, profile)
		if profilever is None:
			try:
				for parent in portage.grabfile(
					os.path.join(profile, 'parent')):
					profilever = relative_profile_path(portdir,
						os.path.join(profile, parent))
					if profilever is not None:
						break
					colon = parent.find(":")
					if colon != -1:
						p_repo_name = parent[:colon]
						try:
							p_repo_loc = \
								repositories.get_location_for_name(p_repo_name)
						except KeyError:
							pass
						else:
							profilever = relative_profile_path(p_repo_loc,
								os.path.join(p_repo_loc, 'profiles',
									parent[colon+1:]))
							if profilever is not None:
								break
			except portage.exception.PortageException:
				pass

			if profilever is None:
				try:
					profilever = "!" + os.readlink(profile)
				except (OSError):
					pass

	if profilever is None:
		profilever = "unavailable"

	libcver = []
	libclist = set()
	for atom in expand_new_virt(vardb, portage.const.LIBC_PACKAGE_ATOM):
		if not atom.blocker:
			libclist.update(vardb.match(atom))
	if libclist:
		for cpv in sorted(libclist):
			libc_split = portage.catpkgsplit(cpv)[1:]
			if libc_split[-1] == "r0":
				libc_split = libc_split[:-1]
			libcver.append("-".join(libc_split))
	else:
		libcver = ["unavailable"]

	gccver = getgccversion(chost)
	unameout=platform.release()+" "+platform.machine()

	return "Portage %s (%s, %s, %s, %s, %s)" % \
		(portage.VERSION, pythonver, profilever, gccver, ",".join(libcver), unameout)

def git_sync_timestamps(portdb, portdir):
	"""
	Since git doesn't preserve timestamps, synchronize timestamps between
	entries and ebuilds/eclasses. Assume the cache has the correct timestamp
	for a given file as long as the file in the working tree is not modified
	(relative to HEAD).
	"""

	cache_db = portdb._pregen_auxdb.get(portdir)

	try:
		if cache_db is None:
			# portdbapi does not populate _pregen_auxdb
			# when FEATURES=metadata-transfer is enabled
			cache_db = portdb._create_pregen_cache(portdir)
	except CacheError as e:
		writemsg_level("!!! Unable to instantiate cache: %s\n" % (e,),
			level=logging.ERROR, noiselevel=-1)
		return 1

	if cache_db is None:
		return os.EX_OK

	if cache_db.validation_chf != 'mtime':
		# newer formats like md5-dict do not require mtime sync
		return os.EX_OK

	writemsg_level(">>> Synchronizing timestamps...\n")

	ec_dir = os.path.join(portdir, "eclass")
	try:
		ec_names = set(f[:-7] for f in os.listdir(ec_dir) \
			if f.endswith(".eclass"))
	except OSError as e:
		writemsg_level("!!! Unable to list eclasses: %s\n" % (e,),
			level=logging.ERROR, noiselevel=-1)
		return 1

	args = [portage.const.BASH_BINARY, "-c",
		"cd %s && git diff-index --name-only --diff-filter=M HEAD" % \
		portage._shell_quote(portdir)]
	proc = subprocess.Popen(args, stdout=subprocess.PIPE)
	modified_files = set(_unicode_decode(l).rstrip("\n") for l in proc.stdout)
	rval = proc.wait()
	proc.stdout.close()
	if rval != os.EX_OK:
		return rval

	modified_eclasses = set(ec for ec in ec_names \
		if os.path.join("eclass", ec + ".eclass") in modified_files)

	updated_ec_mtimes = {}

	for cpv in cache_db:
		cpv_split = portage.catpkgsplit(cpv)
		if cpv_split is None:
			writemsg_level("!!! Invalid cache entry: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue

		cat, pn, ver, rev = cpv_split
		cat, pf = portage.catsplit(cpv)
		relative_eb_path = os.path.join(cat, pn, pf + ".ebuild")
		if relative_eb_path in modified_files:
			continue

		try:
			cache_entry = cache_db[cpv]
			eb_mtime = cache_entry.get("_mtime_")
			ec_mtimes = cache_entry.get("_eclasses_")
		except KeyError:
			writemsg_level("!!! Missing cache entry: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue
		except CacheError as e:
			writemsg_level("!!! Unable to access cache entry: %s %s\n" % \
				(cpv, e), level=logging.ERROR, noiselevel=-1)
			continue

		if eb_mtime is None:
			writemsg_level("!!! Missing ebuild mtime: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue

		try:
			eb_mtime = long(eb_mtime)
		except ValueError:
			writemsg_level("!!! Invalid ebuild mtime: %s %s\n" % \
				(cpv, eb_mtime), level=logging.ERROR, noiselevel=-1)
			continue

		if ec_mtimes is None:
			writemsg_level("!!! Missing eclass mtimes: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue

		if modified_eclasses.intersection(ec_mtimes):
			continue

		missing_eclasses = set(ec_mtimes).difference(ec_names)
		if missing_eclasses:
			writemsg_level("!!! Non-existent eclass(es): %s %s\n" % \
				(cpv, sorted(missing_eclasses)), level=logging.ERROR,
				noiselevel=-1)
			continue

		eb_path = os.path.join(portdir, relative_eb_path)
		try:
			current_eb_mtime = os.stat(eb_path)
		except OSError:
			writemsg_level("!!! Missing ebuild: %s\n" % \
				(cpv,), level=logging.ERROR, noiselevel=-1)
			continue

		inconsistent = False
		for ec, (ec_path, ec_mtime) in ec_mtimes.items():
			updated_mtime = updated_ec_mtimes.get(ec)
			if updated_mtime is not None and updated_mtime != ec_mtime:
				writemsg_level("!!! Inconsistent eclass mtime: %s %s\n" % \
					(cpv, ec), level=logging.ERROR, noiselevel=-1)
				inconsistent = True
				break

		if inconsistent:
			continue

		if current_eb_mtime != eb_mtime:
			os.utime(eb_path, (eb_mtime, eb_mtime))

		for ec, (ec_path, ec_mtime) in ec_mtimes.items():
			if ec in updated_ec_mtimes:
				continue
			ec_path = os.path.join(ec_dir, ec + ".eclass")
			current_mtime = os.stat(ec_path)[stat.ST_MTIME]
			if current_mtime != ec_mtime:
				os.utime(ec_path, (ec_mtime, ec_mtime))
			updated_ec_mtimes[ec] = ec_mtime

	return os.EX_OK

class _emerge_config(SlotObject):

	__slots__ = ('action', 'args', 'opts',
		'running_config', 'target_config', 'trees')

	# Support unpack as tuple, for load_emerge_config backward compatibility.
	def __iter__(self):
		yield self.target_config.settings
		yield self.trees
		yield self.target_config.mtimedb

	def __getitem__(self, index):
		return list(self)[index]

	def __len__(self):
		return 3

def load_emerge_config(emerge_config=None, **kargs):

	if emerge_config is None:
		emerge_config = _emerge_config(**kargs)

	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT"),
			("eprefix", "EPREFIX")):
		v = os.environ.get(envvar, None)
		if v and v.strip():
			kwargs[k] = v
	emerge_config.trees = portage.create_trees(trees=emerge_config.trees,
				**portage._native_kwargs(kwargs))

	for root_trees in emerge_config.trees.values():
		settings = root_trees["vartree"].settings
		settings._init_dirs()
		setconfig = load_default_config(settings, root_trees)
		root_trees["root_config"] = RootConfig(settings, root_trees, setconfig)

	target_eroot = emerge_config.trees._target_eroot
	emerge_config.target_config = \
		emerge_config.trees[target_eroot]['root_config']
	emerge_config.target_config.mtimedb = portage.MtimeDB(
		os.path.join(target_eroot, portage.CACHE_PATH, "mtimedb"))
	emerge_config.running_config = emerge_config.trees[
		emerge_config.trees._running_eroot]['root_config']
	QueryCommand._db = emerge_config.trees

	return emerge_config

def getgccversion(chost):
	"""
	rtype: C{str}
	return:  the current in-use gcc version
	"""

	gcc_ver_command = ['gcc', '-dumpversion']
	gcc_ver_prefix = 'gcc-'

	gcc_not_found_error = red(
	"!!! No gcc found. You probably need to 'source /etc/profile'\n" +
	"!!! to update the environment of this terminal and possibly\n" +
	"!!! other terminals also.\n"
	)

	try:
		proc = subprocess.Popen(["gcc-config", "-c"],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	except OSError:
		myoutput = None
		mystatus = 1
	else:
		myoutput = _unicode_decode(proc.communicate()[0]).rstrip("\n")
		mystatus = proc.wait()
	if mystatus == os.EX_OK and myoutput.startswith(chost + "-"):
		return myoutput.replace(chost + "-", gcc_ver_prefix, 1)

	try:
		proc = subprocess.Popen(
			[chost + "-" + gcc_ver_command[0]] + gcc_ver_command[1:],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	except OSError:
		myoutput = None
		mystatus = 1
	else:
		myoutput = _unicode_decode(proc.communicate()[0]).rstrip("\n")
		mystatus = proc.wait()
	if mystatus == os.EX_OK:
		return gcc_ver_prefix + myoutput

	try:
		proc = subprocess.Popen(gcc_ver_command,
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	except OSError:
		myoutput = None
		mystatus = 1
	else:
		myoutput = _unicode_decode(proc.communicate()[0]).rstrip("\n")
		mystatus = proc.wait()
	if mystatus == os.EX_OK:
		return gcc_ver_prefix + myoutput

	portage.writemsg(gcc_not_found_error, noiselevel=-1)
	return "[unavailable]"

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

def check_procfs():
	procfs_path = '/proc'
	if platform.system() not in ("Linux",) or \
		os.path.ismount(procfs_path):
		return os.EX_OK
	msg = "It seems that %s is not mounted. You have been warned." % procfs_path
	writemsg_level("".join("!!! %s\n" % l for l in textwrap.wrap(msg, 70)),
		level=logging.ERROR, noiselevel=-1)
	return 1

def config_protect_check(trees):
	for root, root_trees in trees.items():
		settings = root_trees["root_config"].settings
		if not settings.get("CONFIG_PROTECT"):
			msg = "!!! CONFIG_PROTECT is empty"
			if settings["ROOT"] != "/":
				msg += " for '%s'" % root
			msg += "\n"
			writemsg_level(msg, level=logging.WARN, noiselevel=-1)

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
	setconfig = root_config.setconfig
	setconfig._create_default_config()
	setconfig._parse(update=True)
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
	if portage.const.EPREFIX:
		global_config_path = os.path.join(portage.const.EPREFIX,
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
	do_not_expand = myaction is None
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

	# display errors that occurred while loading the SetConfig instance
	for e in setconfig.errors:
		print(colorize("BAD", "Error during set creation: %s" % e))

	unmerge_actions = ("unmerge", "prune", "clean", "depclean")

	for a in myfiles:
		if a.startswith(SETPREFIX):
				s = a[len(SETPREFIX):]
				if s not in sets:
					display_missing_pkg_set(root_config, s)
					return (None, 1)
				if s == "installed":
					msg = ("The @installed set is deprecated and will soon be "
					"removed. Please refer to bug #387059 for details.")
					out = portage.output.EOutput()
					for line in textwrap.wrap(msg, 50):
						out.ewarn(line)
				setconfig.active.append(s)

				if do_not_expand:
					# Loading sets can be slow, so skip it here, in order
					# to allow the depgraph to indicate progress with the
					# spinner while sets are loading (bug #461412).
					newargs.append(a)
					continue

				try:
					set_atoms = setconfig.getSetAtoms(s)
				except portage.exception.PackageSetNotFound as e:
					writemsg_level(("emerge: the given set '%s' " + \
						"contains a non-existent set named '%s'.\n") % \
						(s, e), level=logging.ERROR, noiselevel=-1)
					if s in ('world', 'selected') and \
						SETPREFIX + e.value in sets['selected']:
						writemsg_level(("Use `emerge --deselect %s%s` to "
							"remove this set from world_sets.\n") %
							(SETPREFIX, e,), level=logging.ERROR,
							noiselevel=-1)
					return (None, 1)
				if myaction in unmerge_actions and \
						not sets[s].supportsOperation("unmerge"):
					writemsg_level("emerge: the given set '%s' does " % s + \
						"not support unmerge operations\n",
						level=logging.ERROR, noiselevel=-1)
					retval = 1
				elif not set_atoms:
					writemsg_level("emerge: '%s' is an empty set\n" % s,
						level=logging.INFO, noiselevel=-1)
				else:
					newargs.extend(set_atoms)
				for error_msg in sets[s].errors:
					writemsg_level("%s\n" % (error_msg,),
						level=logging.ERROR, noiselevel=-1)
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

	# Skip warnings about missing repo_name entries for
	# /usr/local/portage (see bug #248603).
	try:
		missing_repo_names.remove('/usr/local/portage')
	except KeyError:
		pass

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
			"/etc/portage/make.conf if you would like to disable this warning."))
		msg.append("\n")
		writemsg_level(''.join('%s\n' % l for l in msg),
			level=logging.WARNING, noiselevel=-1)

	return bool(ignored_repos)

def run_action(emerge_config):

	# skip global updates prior to sync, since it's called after sync
	if emerge_config.action not in ('help', 'info', 'sync', 'version') and \
		emerge_config.opts.get('--package-moves') != 'n' and \
		_global_updates(emerge_config.trees,
		emerge_config.target_config.mtimedb["updates"],
		quiet=("--quiet" in emerge_config.opts)):
		emerge_config.target_config.mtimedb.commit()
		# Reload the whole config from scratch.
		load_emerge_config(emerge_config=emerge_config)

	xterm_titles = "notitles" not in \
		emerge_config.target_config.settings.features
	if xterm_titles:
		xtermTitle("emerge")

	if "--digest" in emerge_config.opts:
		os.environ["FEATURES"] = os.environ.get("FEATURES","") + " digest"
		# Reload the whole config from scratch so that the portdbapi internal
		# config is updated with new FEATURES.
		load_emerge_config(emerge_config=emerge_config)

	# NOTE: adjust_configs() can map options to FEATURES, so any relevant
	# options adjustments should be made prior to calling adjust_configs().
	if "--buildpkgonly" in emerge_config.opts:
		emerge_config.opts["--buildpkg"] = True

	if "getbinpkg" in emerge_config.target_config.settings.features:
		emerge_config.opts["--getbinpkg"] = True

	if "--getbinpkgonly" in emerge_config.opts:
		emerge_config.opts["--getbinpkg"] = True

	if "--getbinpkgonly" in emerge_config.opts:
		emerge_config.opts["--usepkgonly"] = True

	if "--getbinpkg" in emerge_config.opts:
		emerge_config.opts["--usepkg"] = True

	if "--usepkgonly" in emerge_config.opts:
		emerge_config.opts["--usepkg"] = True

	if "--buildpkgonly" in emerge_config.opts:
		# --buildpkgonly will not merge anything, so
		# it cancels all binary package options.
		for opt in ("--getbinpkg", "--getbinpkgonly",
			"--usepkg", "--usepkgonly"):
			emerge_config.opts.pop(opt, None)

	adjust_configs(emerge_config.opts, emerge_config.trees)
	apply_priorities(emerge_config.target_config.settings)

	for fmt in emerge_config.target_config.settings["PORTAGE_BINPKG_FORMAT"].split():
		if not fmt in portage.const.SUPPORTED_BINPKG_FORMATS:
			if "--pkg-format" in emerge_config.opts:
				problematic="--pkg-format"
			else:
				problematic="PORTAGE_BINPKG_FORMAT"

			writemsg_level(("emerge: %s is not set correctly. Format " + \
				"'%s' is not supported.\n") % (problematic, fmt),
				level=logging.ERROR, noiselevel=-1)
			return 1

	if emerge_config.action == 'version':
		writemsg_stdout(getportageversion(
			emerge_config.target_config.settings["PORTDIR"],
			None,
			emerge_config.target_config.settings.profile_path,
			emerge_config.target_config.settings["CHOST"],
			emerge_config.target_config.trees['vartree'].dbapi) + '\n',
			noiselevel=-1)
		return 0
	elif emerge_config.action == 'help':
		emerge_help()
		return 0

	spinner = stdout_spinner()
	if "candy" in emerge_config.target_config.settings.features:
		spinner.update = spinner.update_scroll

	if "--quiet" not in emerge_config.opts:
		portage.deprecated_profile_check(
			settings=emerge_config.target_config.settings)
		repo_name_check(emerge_config.trees)
		repo_name_duplicate_check(emerge_config.trees)
		config_protect_check(emerge_config.trees)
	check_procfs()

	for mytrees in emerge_config.trees.values():
		mydb = mytrees["porttree"].dbapi
		# Freeze the portdbapi for performance (memoize all xmatch results).
		mydb.freeze()

		if emerge_config.action in ('search', None) and \
			"--usepkg" in emerge_config.opts:
			# Populate the bintree with current --getbinpkg setting.
			# This needs to happen before expand_set_arguments(), in case
			# any sets use the bintree.
			try:
				mytrees["bintree"].populate(
					getbinpkgs="--getbinpkg" in emerge_config.opts)
			except ParseError as e:
				writemsg("\n\n!!!%s.\nSee make.conf(5) for more info.\n"
						 % e, noiselevel=-1)
				return 1

	del mytrees, mydb

	for x in emerge_config.args:
		if x.endswith((".ebuild", ".tbz2")) and \
			os.path.exists(os.path.abspath(x)):
			print(colorize("BAD", "\n*** emerging by path is broken "
				"and may not always work!!!\n"))
			break

	if emerge_config.action == "list-sets":
		writemsg_stdout("".join("%s\n" % s for s in
			sorted(emerge_config.target_config.sets)))
		return os.EX_OK
	elif emerge_config.action == "check-news":
		news_counts = count_unread_news(
			emerge_config.target_config.trees["porttree"].dbapi,
			emerge_config.target_config.trees["vartree"].dbapi)
		if any(news_counts.values()):
			display_news_notifications(news_counts)
		elif "--quiet" not in emerge_config.opts:
			print("", colorize("GOOD", "*"), "No news items were found.")
		return os.EX_OK

	ensure_required_sets(emerge_config.trees)

	if emerge_config.action is None and \
		"--resume" in emerge_config.opts and emerge_config.args:
		writemsg("emerge: unexpected argument(s) for --resume: %s\n" %
		   " ".join(emerge_config.args), noiselevel=-1)
		return 1

	# only expand sets for actions taking package arguments
	oldargs = emerge_config.args[:]
	if emerge_config.action in ("clean", "config", "depclean",
		"info", "prune", "unmerge", None):
		newargs, retval = expand_set_arguments(
			emerge_config.args, emerge_config.action,
			emerge_config.target_config)
		if retval != os.EX_OK:
			return retval

		# Need to handle empty sets specially, otherwise emerge will react
		# with the help message for empty argument lists
		if oldargs and not newargs:
			print("emerge: no targets left after set expansion")
			return 0

		emerge_config.args = newargs

	if "--tree" in emerge_config.opts and \
		"--columns" in emerge_config.opts:
		print("emerge: can't specify both of \"--tree\" and \"--columns\".")
		return 1

	if '--emptytree' in emerge_config.opts and \
		'--noreplace' in emerge_config.opts:
		writemsg_level("emerge: can't specify both of " + \
			"\"--emptytree\" and \"--noreplace\".\n",
			level=logging.ERROR, noiselevel=-1)
		return 1

	if ("--quiet" in emerge_config.opts):
		spinner.update = spinner.update_quiet
		portage.util.noiselimit = -1

	if "--fetch-all-uri" in emerge_config.opts:
		emerge_config.opts["--fetchonly"] = True

	if "--skipfirst" in emerge_config.opts and \
		"--resume" not in emerge_config.opts:
		emerge_config.opts["--resume"] = True

	# Allow -p to remove --ask
	if "--pretend" in emerge_config.opts:
		emerge_config.opts.pop("--ask", None)

	# forbid --ask when not in a terminal
	# note: this breaks `emerge --ask | tee logfile`, but that doesn't work anyway.
	if ("--ask" in emerge_config.opts) and (not sys.stdin.isatty()):
		portage.writemsg("!!! \"--ask\" should only be used in a terminal. Exiting.\n",
			noiselevel=-1)
		return 1

	if emerge_config.target_config.settings.get("PORTAGE_DEBUG", "") == "1":
		spinner.update = spinner.update_quiet
		portage.util.noiselimit = 0
		if "python-trace" in emerge_config.target_config.settings.features:
			portage.debug.set_trace(True)

	if not ("--quiet" in emerge_config.opts):
		if '--nospinner' in emerge_config.opts or \
			emerge_config.target_config.settings.get('TERM') == 'dumb' or \
			not sys.stdout.isatty():
			spinner.update = spinner.update_basic

	if "--debug" in emerge_config.opts:
		print("myaction", emerge_config.action)
		print("myopts", emerge_config.opts)

	if not emerge_config.action and not emerge_config.args and \
		"--resume" not in emerge_config.opts:
		emerge_help()
		return 1

	pretend = "--pretend" in emerge_config.opts
	fetchonly = "--fetchonly" in emerge_config.opts or \
		"--fetch-all-uri" in emerge_config.opts
	buildpkgonly = "--buildpkgonly" in emerge_config.opts

	# check if root user is the current user for the actions where emerge needs this
	if portage.data.secpass < 2:
		# We've already allowed "--version" and "--help" above.
		if "--pretend" not in emerge_config.opts and \
			emerge_config.action not in ("search", "info"):
			need_superuser = emerge_config.action in ('clean', 'depclean',
				'deselect', 'prune', 'unmerge') or not \
				(fetchonly or \
				(buildpkgonly and portage.data.secpass >= 1) or \
				emerge_config.action in ("metadata", "regen", "sync"))
			if portage.data.secpass < 1 or \
				need_superuser:
				if need_superuser:
					access_desc = "superuser"
				else:
					access_desc = "portage group"
				# Always show portage_group_warning() when only portage group
				# access is required but the user is not in the portage group.
				if "--ask" in emerge_config.opts:
					writemsg_stdout("This action requires %s access...\n" % \
						(access_desc,), noiselevel=-1)
					if portage.data.secpass < 1 and not need_superuser:
						portage.data.portage_group_warning()
					if userquery("Would you like to add --pretend to options?",
						"--ask-enter-invalid" in emerge_config.opts) == "No":
						return 128 + signal.SIGINT
					emerge_config.opts["--pretend"] = True
					emerge_config.opts.pop("--ask")
				else:
					sys.stderr.write(("emerge: %s access is required\n") \
						% access_desc)
					if portage.data.secpass < 1 and not need_superuser:
						portage.data.portage_group_warning()
					return 1

	# Disable emergelog for everything except build or unmerge operations.
	# This helps minimize parallel emerge.log entries that can confuse log
	# parsers like genlop.
	disable_emergelog = False
	for x in ("--pretend", "--fetchonly", "--fetch-all-uri"):
		if x in emerge_config.opts:
			disable_emergelog = True
			break
	if disable_emergelog:
		pass
	elif emerge_config.action in ("search", "info"):
		disable_emergelog = True
	elif portage.data.secpass < 1:
		disable_emergelog = True

	import _emerge.emergelog
	_emerge.emergelog._disable = disable_emergelog

	if not disable_emergelog:
		emerge_log_dir = \
			emerge_config.target_config.settings.get('EMERGE_LOG_DIR')
		if emerge_log_dir:
			try:
				# At least the parent needs to exist for the lock file.
				portage.util.ensure_dirs(emerge_log_dir)
			except portage.exception.PortageException as e:
				writemsg_level("!!! Error creating directory for " + \
					"EMERGE_LOG_DIR='%s':\n!!! %s\n" % \
					(emerge_log_dir, e),
					noiselevel=-1, level=logging.ERROR)
				portage.util.ensure_dirs(_emerge.emergelog._emerge_log_dir)
			else:
				_emerge.emergelog._emerge_log_dir = emerge_log_dir
		else:
			_emerge.emergelog._emerge_log_dir = os.path.join(os.sep,
				portage.const.EPREFIX.lstrip(os.sep), "var", "log")
			portage.util.ensure_dirs(_emerge.emergelog._emerge_log_dir)

	if not "--pretend" in emerge_config.opts:
		time_fmt = "%b %d, %Y %H:%M:%S"
		if sys.hexversion < 0x3000000:
			time_fmt = portage._unicode_encode(time_fmt)
		time_str = time.strftime(time_fmt, time.localtime(time.time()))
		# Avoid potential UnicodeDecodeError in Python 2, since strftime
		# returns bytes in Python 2, and %b may contain non-ascii chars.
		time_str = _unicode_decode(time_str,
			encoding=_encodings['content'], errors='replace')
		emergelog(xterm_titles, "Started emerge on: %s" % time_str)
		myelogstr=""
		if emerge_config.opts:
			opt_list = []
			for opt, arg in emerge_config.opts.items():
				if arg is True:
					opt_list.append(opt)
				elif isinstance(arg, list):
					# arguments like --exclude that use 'append' action
					for x in arg:
						opt_list.append("%s=%s" % (opt, x))
				else:
					opt_list.append("%s=%s" % (opt, arg))
			myelogstr=" ".join(opt_list)
		if emerge_config.action:
			myelogstr += " --" + emerge_config.action
		if oldargs:
			myelogstr += " " + " ".join(oldargs)
		emergelog(xterm_titles, " *** emerge " + myelogstr)

	oldargs = None

	def emergeexitsig(signum, frame):
		signal.signal(signal.SIGTERM, signal.SIG_IGN)
		portage.util.writemsg(
			"\n\nExiting on signal %(signal)s\n" % {"signal":signum})
		sys.exit(128 + signum)

	signal.signal(signal.SIGTERM, emergeexitsig)

	def emergeexit():
		"""This gets out final log message in before we quit."""
		if "--pretend" not in emerge_config.opts:
			emergelog(xterm_titles, " *** terminating.")
		if xterm_titles:
			xtermTitleReset()
	portage.atexit_register(emergeexit)

	if emerge_config.action in ("config", "metadata", "regen", "sync"):
		if "--pretend" in emerge_config.opts:
			sys.stderr.write(("emerge: The '%s' action does " + \
				"not support '--pretend'.\n") % emerge_config.action)
			return 1

	if "sync" == emerge_config.action:
		return action_sync(emerge_config)
	elif "metadata" == emerge_config.action:
		action_metadata(emerge_config.target_config.settings,
			emerge_config.target_config.trees['porttree'].dbapi,
			emerge_config.opts)
	elif emerge_config.action=="regen":
		validate_ebuild_environment(emerge_config.trees)
		return action_regen(emerge_config.target_config.settings,
			emerge_config.target_config.trees['porttree'].dbapi,
			emerge_config.opts.get("--jobs"),
			emerge_config.opts.get("--load-average"))
	# HELP action
	elif "config" == emerge_config.action:
		validate_ebuild_environment(emerge_config.trees)
		action_config(emerge_config.target_config.settings,
			emerge_config.trees, emerge_config.opts, emerge_config.args)

	# SEARCH action
	elif "search" == emerge_config.action:
		validate_ebuild_environment(emerge_config.trees)
		action_search(emerge_config.target_config,
			emerge_config.opts, emerge_config.args, spinner)

	elif emerge_config.action in \
		('clean', 'depclean', 'deselect', 'prune', 'unmerge'):
		validate_ebuild_environment(emerge_config.trees)
		rval = action_uninstall(emerge_config.target_config.settings,
			emerge_config.trees, emerge_config.target_config.mtimedb["ldpath"],
			emerge_config.opts, emerge_config.action,
			emerge_config.args, spinner)
		if not (emerge_config.action == 'deselect' or
			buildpkgonly or fetchonly or pretend):
			post_emerge(emerge_config.action, emerge_config.opts,
				emerge_config.args, emerge_config.target_config.root,
				emerge_config.trees, emerge_config.target_config.mtimedb, rval)
		return rval

	elif emerge_config.action == 'info':

		# Ensure atoms are valid before calling unmerge().
		vardb = emerge_config.target_config.trees['vartree'].dbapi
		portdb = emerge_config.target_config.trees['porttree'].dbapi
		bindb = emerge_config.target_config.trees['bintree'].dbapi
		valid_atoms = []
		for x in emerge_config.args:
			if is_valid_package_atom(x, allow_repo=True):
				try:
					#look at the installed files first, if there is no match
					#look at the ebuilds, since EAPI 4 allows running pkg_info
					#on non-installed packages
					valid_atom = dep_expand(x, mydb=vardb)
					if valid_atom.cp.split("/")[0] == "null":
						valid_atom = dep_expand(x, mydb=portdb)

					if valid_atom.cp.split("/")[0] == "null" and \
						"--usepkg" in emerge_config.opts:
						valid_atom = dep_expand(x, mydb=bindb)

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

		return action_info(emerge_config.target_config.settings,
			emerge_config.trees, emerge_config.opts, valid_atoms)

	# "update", "system", or just process files:
	else:
		validate_ebuild_environment(emerge_config.trees)

		for x in emerge_config.args:
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

		# GLEP 42 says to display news *after* an emerge --pretend
		if "--pretend" not in emerge_config.opts:
			display_news_notification(
				emerge_config.target_config, emerge_config.opts)
		retval = action_build(emerge_config.target_config.settings,
			emerge_config.trees, emerge_config.target_config.mtimedb,
			emerge_config.opts, emerge_config.action,
			emerge_config.args, spinner)
		post_emerge(emerge_config.action, emerge_config.opts,
			emerge_config.args, emerge_config.target_config.root,
			emerge_config.trees, emerge_config.target_config.mtimedb, retval)

		return retval
