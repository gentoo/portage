# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

try:
	from subprocess import getstatusoutput as subprocess_getstatusoutput
except ImportError:
	from commands import getstatusoutput as subprocess_getstatusoutput
import errno
import logging
import platform
import pwd
import random
import re
import shutil
import signal
import socket
import stat
import sys
import tempfile
import textwrap
import time
from itertools import chain

import portage
from portage import os
from portage import digraph
from portage import _unicode_decode
from portage.cache.cache_errors import CacheError
from portage.const import GLOBAL_CONFIG_PATH, NEWS_LIB_PATH
from portage.const import _ENABLE_DYN_LINK_MAP
from portage.dbapi.dep_expand import dep_expand
from portage.dbapi._expand_new_virt import expand_new_virt
from portage.dep import Atom, extended_cp_match
from portage.exception import InvalidAtom
from portage.output import blue, bold, colorize, create_color_func, darkgreen, \
	red, yellow
good = create_color_func("GOOD")
bad = create_color_func("BAD")
from portage.package.ebuild._ipc.QueryCommand import QueryCommand
from portage.package.ebuild.doebuild import _check_temp_dir
from portage._sets import load_default_config, SETPREFIX
from portage._sets.base import InternalPackageSet
from portage.util import cmp_sort_key, writemsg, \
	writemsg_level, writemsg_stdout
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
		from textwrap import wrap
		for line in wrap(msg, 72):
			writemsg("%s%s\n" % (prefix, line))
		writemsg(prefix + "\n")

	if resume:
		favorites = mtimedb["resume"].get("favorites")
		if not isinstance(favorites, list):
			favorites = []
		myparams = create_depgraph_params(myopts, myaction)

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
			print(darkgreen("emerge: It seems we have nothing to resume..."))
			return os.EX_OK

		myparams = create_depgraph_params(myopts, myaction)
		try:
			success, mydepgraph, favorites = backtrack_depgraph(
				settings, trees, myopts, myparams, myaction, myfiles, spinner)
		except portage.exception.PackageSetNotFound as e:
			root_config = trees[settings["ROOT"]]["root_config"]
			display_missing_pkg_set(root_config, e.value)
			return 1

		if not success:
			mydepgraph.display_problems()
			return 1

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
					print()
					for x in world_candidates:
						print(" %s %s" % (good("*"), x))
					prompt="Would you like to add these packages to your world favorites?"
				elif settings["AUTOCLEAN"] and "yes"==settings["AUTOCLEAN"]:
					prompt="Nothing to merge; would you like to auto-clean packages?"
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
		if "--ask" in myopts and userquery(prompt, enter_invalid) == "No":
			print()
			print("Quitting.")
			print()
			return os.EX_OK
		# Don't ask again (e.g. when auto-cleaning packages after merge)
		myopts.pop("--ask", None)

	if ("--pretend" in myopts) and not ("--fetchonly" in myopts or "--fetch-all-uri" in myopts):
		if ("--resume" in myopts):
			mymergelist = mydepgraph.altlist()
			if len(mymergelist) == 0:
				print(colorize("INFORM", "emerge: It seems we have nothing to resume..."))
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
				graph_copy = mydepgraph._dynamic_config.digraph.copy()
				removed_nodes = set()
				for node in graph_copy:
					if not isinstance(node, Package) or \
						node.operation == "nomerge":
						removed_nodes.add(node)
				graph_copy.difference_update(removed_nodes)
				if not graph_copy.hasallzeros(ignore_priority = \
					DepPrioritySatisfiedRange.ignore_medium):
					print("\n!!! --buildpkgonly requires all dependencies to be merged.")
					print("!!! You have to merge the dependencies before you can build this package.\n")
					return 1
	else:
		if "--buildpkgonly" in myopts:
			graph_copy = mydepgraph._dynamic_config.digraph.copy()
			removed_nodes = set()
			for node in graph_copy:
				if not isinstance(node, Package) or \
					node.operation == "nomerge":
					removed_nodes.add(node)
			graph_copy.difference_update(removed_nodes)
			if not graph_copy.hasallzeros(ignore_priority = \
				DepPrioritySatisfiedRange.ignore_medium):
				print("\n!!! --buildpkgonly requires all dependencies to be merged.")
				print("!!! Cannot merge requested packages. Merge deps and try again.\n")
				return 1

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

		mergetask = Scheduler(settings, trees, mtimedb, myopts,
			spinner, favorites=favorites,
			graph_config=mydepgraph.schedulerGraph())

		del mydepgraph
		clear_caches(trees)

		retval = mergetask.merge()

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

		return retval

def action_config(settings, trees, myopts, myfiles):
	enter_invalid = '--ask-enter-invalid' in myopts
	if len(myfiles) != 1:
		print(red("!!! config can only take a single package atom at this time\n"))
		sys.exit(1)
	if not is_valid_package_atom(myfiles[0]):
		portage.writemsg("!!! '%s' is not a valid package atom.\n" % myfiles[0],
			noiselevel=-1)
		portage.writemsg("!!! Please check ebuild(5) for full details.\n")
		portage.writemsg("!!! (Did you specify a version but forget to prefix with '='?)\n")
		sys.exit(1)
	print()
	try:
		pkgs = trees[settings["ROOT"]]["vartree"].dbapi.match(myfiles[0])
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
				sys.exit(0)
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
			sys.exit(0)
	else:
		print("Configuring pkg...")
	print()
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
	if not _ENABLE_DYN_LINK_MAP:
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

	root_config = trees[settings['ROOT']]['root_config']
	vardb = root_config.trees['vartree'].dbapi

	args_set = InternalPackageSet()
	if myfiles:
		args_set.update(myfiles)
		matched_packages = False
		for x in args_set:
			if vardb.match(x):
				matched_packages = True
				break
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
		unmerge(root_config, myopts, "unmerge",
			cleanlist, ldpath_mtimes, ordered=ordered,
			scheduler=scheduler)

	if action == "prune":
		return

	if not cleanlist and "--quiet" in myopts:
		return

	print("Packages installed:   " + str(len(vardb.cpv_all())))
	print("Packages in world:    " + \
		str(len(root_config.sets["selected"].getAtoms())))
	print("Packages in system:   " + \
		str(len(root_config.sets["system"].getAtoms())))
	print("Required packages:    "+str(req_pkg_count))
	if "--pretend" in myopts:
		print("Number to remove:     "+str(len(cleanlist)))
	else:
		print("Number removed:       "+str(len(cleanlist)))

def calc_depclean(settings, trees, ldpath_mtimes,
	myopts, action, args_set, spinner):
	allow_missing_deps = bool(args_set)

	debug = '--debug' in myopts
	xterm_titles = "notitles" not in settings.features
	myroot = settings["ROOT"]
	root_config = trees[myroot]["root_config"]
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

	if not system_set or not selected_set:

		if not system_set:
			writemsg_level("!!! You have no system list.\n",
				level=logging.ERROR, noiselevel=-1)

		if not selected_set:
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
	vardb = resolver._frozen_config.trees[myroot]["vartree"].dbapi
	real_vardb = trees[myroot]["vartree"].dbapi

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
						pkg.metadata["PROVIDE"], str(e))
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
					pkg.metadata["PROVIDE"], str(e))
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
					pkg.metadata["PROVIDE"], str(e))
				del e
				required_sets['__excluded__'].add("=" + pkg.cpv)

	success = resolver._complete_graph(required_sets={myroot:required_sets})
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
				msg.append("  %s pulled in by:" % (atom,))
				msg.append("    %s" % (parent,))
				msg.append("")
			msg.append("Have you forgotten to run " + \
				good("`emerge --update --newuse --deep @world`") + " prior")
			msg.append(("to %s? It may be necessary to manually " + \
				"uninstall packages that no longer") % action)
			msg.append("exist in the portage tree since " + \
				"it may not be possible to satisfy their")
			msg.append("dependencies.  Also, be aware of " + \
				"the --with-bdeps option that is documented")
			msg.append("in " + good("`man emerge`") + ".")
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
		parent_nodes = graph.parent_nodes(child_node)
		if not parent_nodes:
			# With --prune, the highest version can be pulled in without any
			# real parent since all installed packages are pulled in.  In that
			# case there's nothing to show here.
			return
		parent_strs = []
		for node in parent_nodes:
			parent_strs.append(str(getattr(node, "cpv", node)))
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

		# Never display the special internal protected_set.
		for node in graph:
			if isinstance(node, SetArg) and node.name == protected_set_name:
				graph.remove(node)
				break

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

	if cleanlist and \
		real_vardb._linkmap is not None and \
		myopts.get('--depclean-lib-check') != 'n':

		# Check if any of these packages are the sole providers of libraries
		# with consumers that have not been selected for removal. If so, these
		# packages and any dependencies need to be added to the graph.
		linkmap = real_vardb._linkmap
		consumer_cache = {}
		provider_cache = {}
		consumer_map = {}

		writemsg_level(">>> Checking for lib consumers...\n")

		for pkg in cleanlist:
			pkg_dblink = real_vardb._dblink(pkg.cpv)
			consumers = {}

			for lib in pkg_dblink.getcontents():
				lib = lib[len(myroot):]
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
			file_owners = real_vardb._owners.getFileOwnerMap(search_files)

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
			from textwrap import wrap
			writemsg_level("".join(prefix + "%s\n" % line for \
				line in wrap(msg, 70)), level=logging.WARNING, noiselevel=-1)

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
						priority=UnmergeDepPriority(runtime=True),
						root=pkg.root)):
						resolver.display_problems()
						return 1, [], False, 0

			writemsg_level("\nCalculating dependencies  ")
			success = resolver._complete_graph(
				required_sets={myroot:required_sets})
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

		dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
		runtime = UnmergeDepPriority(runtime=True)
		runtime_post = UnmergeDepPriority(runtime_post=True)
		buildtime = UnmergeDepPriority(buildtime=True)
		priority_map = {
			"RDEPEND": runtime,
			"PDEPEND": runtime_post,
			"DEPEND": buildtime,
		}

		for node in clean_set:
			graph.add(node, None)
			mydeps = []
			for dep_type in dep_keys:
				depstr = node.metadata[dep_type]
				if not depstr:
					continue
				priority = priority_map[dep_type]

				if debug:
					writemsg_level(_unicode_decode("\nParent:    %s\n") \
						% (node,), noiselevel=-1, level=logging.DEBUG)
					writemsg_level(_unicode_decode(  "Depstring: %s\n") \
						% (depstr,), noiselevel=-1, level=logging.DEBUG)
					writemsg_level(_unicode_decode(  "Priority:  %s\n") \
						% (priority,), noiselevel=-1, level=logging.DEBUG)

				try:
					atoms = resolver._select_atoms(myroot, depstr,
						myuse=node.use.enabled, parent=node,
						priority=priority)[node]
				except portage.exception.InvalidDependString:
					# Ignore invalid deps of packages that will
					# be uninstalled anyway.
					continue

				if debug:
					writemsg_level("Candidates: [%s]\n" % \
						', '.join(_unicode_decode("'%s'") % (x,) for x in atoms),
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
							graph.add(child_node, node, priority=priority)

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
			while not graph.empty():
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
	root_config = trees[settings['ROOT']]['root_config']
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
					slot, = vardb.aux_get(cpv, ["SLOT"])
					if not slot:
						slot = "0"
					expanded_atoms.add(Atom("%s:%s" % \
						(portage.cpv_getkey(cpv), slot)))

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
						not (arg_atom.slot and not atom.slot):
						discard_atoms.add(atom)
						break
		if discard_atoms:
			for atom in sorted(discard_atoms):
				if pretend:
					print(">>> Would remove %s from \"world\" favorites file..." % \
						colorize("INFORM", str(atom)))
				else:
					print(">>> Removing %s from \"world\" favorites file..." % \
						colorize("INFORM", str(atom)))

			if '--ask' in opts:
				prompt = "Would you like to remove these " + \
					"packages from your world favorites?"
				if userquery(prompt, enter_invalid) == 'No':
					return os.EX_OK

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
	print(getportageversion(settings["PORTDIR"], settings["ROOT"],
		settings.profile_path, settings["CHOST"],
		trees[settings["ROOT"]]["vartree"].dbapi))
	header_width = 65
	header_title = "System Settings"
	if myfiles:
		print(header_width * "=")
		print(header_title.rjust(int(header_width/2 + len(header_title)/2)))
	print(header_width * "=")
	print("System uname: "+platform.platform(aliased=1))

	lastSync = portage.grabfile(os.path.join(
		settings["PORTDIR"], "metadata", "timestamp.chk"))
	print("Timestamp of tree:", end=' ')
	if lastSync:
		print(lastSync[0])
	else:
		print("Unknown")

	output=subprocess_getstatusoutput("distcc --version")
	if not output[0]:
		print(str(output[1].split("\n",1)[0]), end=' ')
		if "distcc" in settings.features:
			print("[enabled]")
		else:
			print("[disabled]")

	output=subprocess_getstatusoutput("ccache -V")
	if not output[0]:
		print(str(output[1].split("\n",1)[0]), end=' ')
		if "ccache" in settings.features:
			print("[enabled]")
		else:
			print("[disabled]")

	myvars  = ["sys-devel/autoconf", "sys-devel/automake", "virtual/os-headers",
	           "sys-devel/binutils", "sys-devel/libtool",  "dev-lang/python"]
	myvars += portage.util.grabfile(settings["PORTDIR"]+"/profiles/info_pkgs")
	atoms = []
	vardb = trees["/"]["vartree"].dbapi
	for x in myvars:
		try:
			x = Atom(x)
		except InvalidAtom:
			writemsg_stdout("%-20s %s\n" % (x+":", "[NOT VALID]"),
				noiselevel=-1)
		else:
			for atom in expand_new_virt(vardb, x):
				if not atom.blocker:
					atoms.append((x, atom))

	myvars = sorted(set(atoms))

	portdb = trees["/"]["porttree"].dbapi
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
		writemsg_stdout("%s %s\n" % \
			((cp + ":").ljust(cp_max_len + 1), versions),
			noiselevel=-1)

	libtool_vers = ",".join(trees["/"]["vartree"].dbapi.match("sys-devel/libtool"))

	if "--verbose" in myopts:
		myvars = list(settings)
	else:
		myvars = ['GENTOO_MIRRORS', 'CONFIG_PROTECT', 'CONFIG_PROTECT_MASK',
		          'PORTDIR', 'DISTDIR', 'PKGDIR', 'PORTAGE_TMPDIR',
		          'PORTDIR_OVERLAY', 'PORTAGE_BUNZIP2_COMMAND',
		          'PORTAGE_BZIP2_COMMAND',
		          'USE', 'CHOST', 'CFLAGS', 'CXXFLAGS',
		          'ACCEPT_KEYWORDS', 'ACCEPT_LICENSE', 'SYNC', 'FEATURES',
		          'EMERGE_DEFAULT_OPTS']

		myvars.extend(portage.util.grabfile(settings["PORTDIR"]+"/profiles/info_vars"))

	myvars_ignore_defaults = {
		'PORTAGE_BZIP2_COMMAND' : 'bzip2',
	}

	myvars = portage.util.unique_array(myvars)
	use_expand = settings.get('USE_EXPAND', '').split()
	use_expand.sort()
	use_expand_hidden = set(
		settings.get('USE_EXPAND_HIDDEN', '').upper().split())
	alphabetical_use = '--alphabetical' in myopts
	root_config = trees[settings["ROOT"]]['root_config']
	unset_vars = []
	myvars.sort()
	for x in myvars:
		if x in settings:
			if x != "USE":
				default = myvars_ignore_defaults.get(x)
				if default is not None and \
					default == settings[x]:
					continue
				writemsg_stdout('%s="%s"\n' % (x, settings[x]), noiselevel=-1)
			else:
				use = set(settings["USE"].split())
				for varname in use_expand:
					flag_prefix = varname.lower() + "_"
					for f in list(use):
						if f.startswith(flag_prefix):
							use.remove(f)
				use = list(use)
				use.sort()
				print('USE="%s"' % " ".join(use), end=' ')
				for varname in use_expand:
					myval = settings.get(varname)
					if myval:
						print('%s="%s"' % (varname, myval), end=' ')
				print()
		else:
			unset_vars.append(x)
	if unset_vars:
		print("Unset:  "+", ".join(unset_vars))
	print()

	if "--debug" in myopts:
		for x in dir(portage):
			module = getattr(portage, x)
			if "cvs_id_string" in dir(module):
				print("%s: %s" % (str(x), str(module.cvs_id_string)))

	# See if we can find any packages installed matching the strings
	# passed on the command line
	mypkgs = []
	vardb = trees[settings["ROOT"]]["vartree"].dbapi
	portdb = trees[settings["ROOT"]]["porttree"].dbapi
	bindb = trees[settings["ROOT"]]["bintree"].dbapi
	for x in myfiles:
		match_found = False
		installed_match = vardb.match(x)
		for installed in installed_match:
			mypkgs.append((installed, "installed"))
			match_found = True

		if match_found:
			continue

		for db, pkg_type in ((portdb, "ebuild"), (bindb, "binary")):
			if pkg_type == "binary" and "--usepkg" not in myopts:
				continue

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

	# If some packages were found...
	if mypkgs:
		# Get our global settings (we only print stuff if it varies from
		# the current config)
		mydesiredvars = [ 'CHOST', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS' ]
		auxkeys = mydesiredvars + list(vardb._aux_cache_keys)
		auxkeys.append('DEFINED_PHASES')
		global_vals = {}
		pkgsettings = portage.config(clone=settings)

		# Loop through each package
		# Only print settings if they differ from global settings
		header_title = "Package Settings"
		print(header_width * "=")
		print(header_title.rjust(int(header_width/2 + len(header_title)/2)))
		print(header_width * "=")
		from portage.output import EOutput
		out = EOutput()
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
				print("\n%s was built with the following:" % \
					colorize("INFORM", str(pkg.cpv)))
			elif pkg_type == "ebuild":
				print("\n%s would be build with the following:" % \
					colorize("INFORM", str(pkg.cpv)))
			elif pkg_type == "binary":
				print("\n%s (non-installed binary) was built with the following:" % \
					colorize("INFORM", str(pkg.cpv)))

			writemsg_stdout('%s\n' % pkg_use_display(pkg, myopts),
				noiselevel=-1)
			if pkg_type == "installed":
				for myvar in mydesiredvars:
					if metadata[myvar].split() != settings.get(myvar, '').split():
						print("%s=\"%s\"" % (myvar, metadata[myvar]))
			print()

			if metadata['DEFINED_PHASES']:
				if 'info' not in metadata['DEFINED_PHASES'].split():
					continue

			print(">>> Attempting to run pkg_info() for '%s'" % pkg.cpv)

			if pkg_type == "installed":
				ebuildpath = vardb.findname(pkg.cpv)
			elif pkg_type == "ebuild":
				ebuildpath = portdb.findname(pkg.cpv)
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
				portage.doebuild(ebuildpath, "info", pkgsettings["ROOT"],
					pkgsettings, debug=(settings.get("PORTAGE_DEBUG", "") == 1),
					mydbapi=trees[settings["ROOT"]]["vartree"].dbapi,
					tree="vartree")
			elif pkg_type == "ebuild":
				portage.doebuild(ebuildpath, "info", pkgsettings["ROOT"],
					pkgsettings, debug=(settings.get("PORTAGE_DEBUG", "") == 1),
					mydbapi=trees[settings["ROOT"]]["porttree"].dbapi,
					tree="porttree")
			elif pkg_type == "binary":
				portage.doebuild(ebuildpath, "info", pkgsettings["ROOT"],
					pkgsettings, debug=(settings.get("PORTAGE_DEBUG", "") == 1),
					mydbapi=trees[settings["ROOT"]]["bintree"].dbapi,
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

	auxdbkeys = [x for x in portage.auxdbkeys if not x.startswith("UNUSED_0")]
	auxdbkeys = tuple(auxdbkeys)

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
		if src_db is None and \
			os.path.isdir(os.path.join(path, 'metadata', 'cache')):
			src_db = portdb.metadbmodule(
				path, 'metadata/cache', auxdbkeys, readonly=True)
			try:
				src_db.ec = portdb._repo_info[path].eclass_db
			except AttributeError:
				pass

		if src_db is not None:
			porttrees_data.append(TreeData(portdb.auxdb[path],
				portdb._repo_info[path].eclass_db, path, src_db))

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

	from portage.cache.util import quiet_mirroring
	from portage import eapi_is_supported, \
		_validate_cache_for_unsupported_eapis

	# TODO: Display error messages, but do not interfere with the progress bar.
	# Here's how:
	#  1) erase the progress bar
	#  2) show the error message
	#  3) redraw the progress bar on a new line
	noise = quiet_mirroring()

	for cp in cp_all:
		for tree_data in porttrees_data:
			for cpv in portdb.cp_list(cp, mytree=tree_data.path):
				tree_data.valid_nodes.add(cpv)
				try:
					src = tree_data.src_db[cpv]
				except KeyError as e:
					noise.missing_entry(cpv)
					del e
					continue
				except CacheError as ce:
					noise.exception(cpv, ce)
					del ce
					continue

				eapi = src.get('EAPI')
				if not eapi:
					eapi = '0'
				eapi = eapi.lstrip('-')
				eapi_supported = eapi_is_supported(eapi)
				if not eapi_supported:
					if not _validate_cache_for_unsupported_eapis:
						noise.misc(cpv, "unable to validate " + \
							"cache for EAPI='%s'" % eapi)
						continue

				dest = None
				try:
					dest = tree_data.dest_db[cpv]
				except (KeyError, CacheError):
					pass

				for d in (src, dest):
					if d is not None and d.get('EAPI') in ('', '0'):
						del d['EAPI']

				if dest is not None:
					if not (dest['_mtime_'] == src['_mtime_'] and \
						tree_data.eclass_db.is_eclass_data_valid(
							dest['_eclasses_']) and \
						set(dest['_eclasses_']) == set(src['_eclasses_'])):
						dest = None
					else:
						# We don't want to skip the write unless we're really
						# sure that the existing cache is identical, so don't
						# trust _mtime_ and _eclasses_ alone.
						for k in set(chain(src, dest)).difference(
							('_mtime_', '_eclasses_')):
							if dest.get(k, '') != src.get(k, ''):
								dest = None
								break

				if dest is not None:
					# The existing data is valid and identical,
					# so there's no need to overwrite it.
					continue

				try:
					inherited = src.get('INHERITED', '')
					eclasses = src.get('_eclasses_')
				except CacheError as ce:
					noise.exception(cpv, ce)
					del ce
					continue

				if eclasses is not None:
					if not tree_data.eclass_db.is_eclass_data_valid(
						src['_eclasses_']):
						noise.eclass_stale(cpv)
						continue
					inherited = eclasses
				else:
					inherited = inherited.split()

				if tree_data.src_db.complete_eclass_entries and \
					eclasses is None:
					noise.corruption(cpv, "missing _eclasses_ field")
					continue

				if inherited:
					# Even if _eclasses_ already exists, replace it with data from
					# eclass_cache, in order to insert local eclass paths.
					try:
						eclasses = tree_data.eclass_db.get_eclass_data(inherited)
					except KeyError:
						# INHERITED contains a non-existent eclass.
						noise.eclass_stale(cpv)
						continue

					if eclasses is None:
						noise.eclass_stale(cpv)
						continue
					src['_eclasses_'] = eclasses
				else:
					src['_eclasses_'] = {}

				if not eapi_supported:
					src = {
						'EAPI'       : '-' + eapi,
						'_mtime_'    : src['_mtime_'],
						'_eclasses_' : src['_eclasses_'],
					}

				try:
					tree_data.dest_db[cpv] = src
				except CacheError as ce:
					noise.exception(cpv, ce)
					del ce

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

	sys.stdout.flush()
	os.umask(old_umask)

def action_regen(settings, portdb, max_jobs, max_load):
	xterm_titles = "notitles" not in settings.features
	emergelog(xterm_titles, " === regen")
	#regenerate cache entries
	try:
		os.close(sys.stdin.fileno())
	except SystemExit as e:
		raise # Needed else can't exit
	except:
		pass
	sys.stdout.flush()

	regen = MetadataRegen(portdb, max_jobs=max_jobs, max_load=max_load)
	received_signal = []

	def emergeexitsig(signum, frame):
		signal.signal(signal.SIGINT, signal.SIG_IGN)
		signal.signal(signal.SIGTERM, signal.SIG_IGN)
		portage.util.writemsg("\n\nExiting on signal %(signal)s\n" % \
			{"signal":signum})
		regen.terminate()
		received_signal.append(128 + signum)

	earlier_sigint_handler = signal.signal(signal.SIGINT, emergeexitsig)
	earlier_sigterm_handler = signal.signal(signal.SIGTERM, emergeexitsig)

	try:
		regen.run()
	finally:
		# Restore previous handlers
		if earlier_sigint_handler is not None:
			signal.signal(signal.SIGINT, earlier_sigint_handler)
		else:
			signal.signal(signal.SIGINT, signal.SIG_DFL)
		if earlier_sigterm_handler is not None:
			signal.signal(signal.SIGTERM, earlier_sigterm_handler)
		else:
			signal.signal(signal.SIGTERM, signal.SIG_DFL)

	if received_signal:
		sys.exit(received_signal[0])

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

def action_sync(settings, trees, mtimedb, myopts, myaction):
	enter_invalid = '--ask-enter-invalid' in myopts
	xterm_titles = "notitles" not in settings.features
	emergelog(xterm_titles, " === sync")
	portdb = trees[settings["ROOT"]]["porttree"].dbapi
	myportdir = portdb.porttree_root
	if not myportdir:
		myportdir = settings.get('PORTDIR', '')
		if myportdir and myportdir.strip():
			myportdir = os.path.realpath(myportdir)
		else:
			myportdir = None
	out = portage.output.EOutput()
	global_config_path = GLOBAL_CONFIG_PATH
	if settings['EPREFIX']:
		global_config_path = os.path.join(settings['EPREFIX'],
				GLOBAL_CONFIG_PATH.lstrip(os.sep))
	if not myportdir:
		sys.stderr.write("!!! PORTDIR is undefined.  " + \
			"Is %s/make.globals missing?\n" % global_config_path)
		sys.exit(1)
	if myportdir[-1]=="/":
		myportdir=myportdir[:-1]
	try:
		st = os.stat(myportdir)
	except OSError:
		st = None
	if st is None:
		print(">>>",myportdir,"not found, creating it.")
		portage.util.ensure_dirs(myportdir, mode=0o755)
		st = os.stat(myportdir)

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

	syncuri = settings.get("SYNC", "").strip()
	if not syncuri:
		writemsg_level("!!! SYNC is undefined. " + \
			"Is %s/make.globals missing?\n" % global_config_path,
			noiselevel=-1, level=logging.ERROR)
		return 1

	vcs_dirs = frozenset([".git", ".svn", "CVS", ".hg"])
	vcs_dirs = vcs_dirs.intersection(os.listdir(myportdir))

	os.umask(0o022)
	dosyncuri = syncuri
	updatecache_flg = False
	if myaction == "metadata":
		print("skipping sync")
		updatecache_flg = True
	elif ".git" in vcs_dirs:
		# Update existing git repository, and ignore the syncuri. We are
		# going to trust the user and assume that the user is in the branch
		# that he/she wants updated. We'll let the user manage branches with
		# git directly.
		if portage.process.find_binary("git") is None:
			msg = ["Command not found: git",
			"Type \"emerge dev-util/git\" to enable git support."]
			for l in msg:
				writemsg_level("!!! %s\n" % l,
					level=logging.ERROR, noiselevel=-1)
			return 1
		msg = ">>> Starting git pull in %s..." % myportdir
		emergelog(xterm_titles, msg )
		writemsg_level(msg + "\n")
		exitcode = portage.process.spawn_bash("cd %s ; git pull" % \
			(portage._shell_quote(myportdir),), **spawn_kwargs)
		if exitcode != os.EX_OK:
			msg = "!!! git pull error in %s." % myportdir
			emergelog(xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return exitcode
		msg = ">>> Git pull in %s successful" % myportdir
		emergelog(xterm_titles, msg)
		writemsg_level(msg + "\n")
		exitcode = git_sync_timestamps(settings, myportdir)
		if exitcode == os.EX_OK:
			updatecache_flg = True
	elif syncuri[:8]=="rsync://" or syncuri[:6]=="ssh://":
		for vcs_dir in vcs_dirs:
			writemsg_level(("!!! %s appears to be under revision " + \
				"control (contains %s).\n!!! Aborting rsync sync.\n") % \
				(myportdir, vcs_dir), level=logging.ERROR, noiselevel=-1)
			return 1
		if not os.path.exists("/usr/bin/rsync"):
			print("!!! /usr/bin/rsync does not exist, so rsync support is disabled.")
			print("!!! Type \"emerge net-misc/rsync\" to enable rsync support.")
			sys.exit(1)
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
			writemsg_level("!!! SYNC is invalid: %s\n" % syncuri,
				noiselevel=-1, level=logging.ERROR)
			return 1
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
						sys.exit(0)
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

			rsynccommand = ["/usr/bin/rsync"] + rsync_opts + extra_rsync_opts

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
							mycommand, returnpid=True, **spawn_kwargs))
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
					print()
					print(">>>")
					print(">>> Timestamps on the server and in the local repository are the same.")
					print(">>> Cancelling all further sync action. You are already up to date.")
					print(">>>")
					print(">>> In order to force sync, remove '%s'." % servertimestampfile)
					print(">>>")
					print()
					sys.exit(0)
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
					mycommand = rsynccommand + [dosyncuri+"/", myportdir]
					exitcode = portage.process.spawn(mycommand, **spawn_kwargs)
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
			sys.exit(1)
		elif exitcode == EXCEEDED_MAX_RETRIES:
			sys.stderr.write(
				">>> Exceeded PORTAGE_RSYNC_RETRIES: %s\n" % maxretries)
			sys.exit(1)
		elif (exitcode>0):
			msg = []
			if exitcode==1:
				msg.append("Rsync has reported that there is a syntax error. Please ensure")
				msg.append("that your SYNC statement is proper.")
				msg.append("SYNC=" + settings["SYNC"])
			elif exitcode==11:
				msg.append("Rsync has reported that there is a File IO error. Normally")
				msg.append("this means your disk is full, but can be caused by corruption")
				msg.append("on the filesystem that contains PORTDIR. Please investigate")
				msg.append("and try again after the problem has been fixed.")
				msg.append("PORTDIR=" + settings["PORTDIR"])
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
			sys.exit(exitcode)
	elif syncuri[:6]=="cvs://":
		if not os.path.exists("/usr/bin/cvs"):
			print("!!! /usr/bin/cvs does not exist, so CVS support is disabled.")
			print("!!! Type \"emerge dev-vcs/cvs\" to enable CVS support.")
			sys.exit(1)
		cvsroot=syncuri[6:]
		cvsdir=os.path.dirname(myportdir)
		if not os.path.exists(myportdir+"/CVS"):
			#initial checkout
			print(">>> Starting initial cvs checkout with "+syncuri+"...")
			if os.path.exists(cvsdir+"/gentoo-x86"):
				print("!!! existing",cvsdir+"/gentoo-x86 directory; exiting.")
				sys.exit(1)
			try:
				os.rmdir(myportdir)
			except OSError as e:
				if e.errno != errno.ENOENT:
					sys.stderr.write(
						"!!! existing '%s' directory; exiting.\n" % myportdir)
					sys.exit(1)
				del e
			if portage.process.spawn_bash(
					"cd %s; exec cvs -z0 -d %s co -P gentoo-x86" % \
					(portage._shell_quote(cvsdir), portage._shell_quote(cvsroot)),
					**spawn_kwargs) != os.EX_OK:
				print("!!! cvs checkout error; exiting.")
				sys.exit(1)
			os.rename(os.path.join(cvsdir, "gentoo-x86"), myportdir)
		else:
			#cvs update
			print(">>> Starting cvs update with "+syncuri+"...")
			retval = portage.process.spawn_bash(
				"cd %s; exec cvs -z0 -q update -dP" % \
				(portage._shell_quote(myportdir),), **spawn_kwargs)
			if retval != os.EX_OK:
				writemsg_level("!!! cvs update error; exiting.\n",
					noiselevel=-1, level=logging.ERROR)
				sys.exit(retval)
		dosyncuri = syncuri
	else:
		writemsg_level("!!! Unrecognized protocol: SYNC='%s'\n" % (syncuri,),
			noiselevel=-1, level=logging.ERROR)
		return 1

	if updatecache_flg and  \
		myaction != "metadata" and \
		"metadata-transfer" not in settings.features:
		updatecache_flg = False

	# Reload the whole config from scratch.
	settings, trees, mtimedb = load_emerge_config(trees=trees)
	adjust_configs(myopts, trees)
	root_config = trees[settings["ROOT"]]["root_config"]
	portdb = trees[settings["ROOT"]]["porttree"].dbapi

	if updatecache_flg and \
		os.path.exists(os.path.join(myportdir, 'metadata', 'cache')):

		# Only update cache for myportdir since that's
		# the only one that's been synced here.
		action_metadata(settings, portdb, myopts, porttrees=[myportdir])

	if myopts.get('--package-moves') != 'n' and \
		_global_updates(trees, mtimedb["updates"], quiet=("--quiet" in myopts)):
		mtimedb.commit()
		# Reload the whole config from scratch.
		settings, trees, mtimedb = load_emerge_config(trees=trees)
		adjust_configs(myopts, trees)
		portdb = trees[settings["ROOT"]]["porttree"].dbapi
		root_config = trees[settings["ROOT"]]["root_config"]

	mybestpv = portdb.xmatch("bestmatch-visible",
		portage.const.PORTAGE_PACKAGE_ATOM)
	mypvs = portage.best(
		trees[settings["ROOT"]]["vartree"].dbapi.match(
		portage.const.PORTAGE_PACKAGE_ATOM))

	chk_updated_cfg_files(settings["EROOT"],
		portage.util.shlex_split(settings.get("CONFIG_PROTECT", "")))

	if myaction != "metadata":
		postsync = os.path.join(settings["PORTAGE_CONFIGROOT"],
			portage.USER_CONFIG_PATH, "bin", "post_sync")
		if os.access(postsync, os.X_OK):
			retval = portage.process.spawn(
				[postsync, dosyncuri], env=settings.environ())
			if retval != os.EX_OK:
				writemsg_level(
					" %s spawn failed of %s\n" % (bad("*"), postsync,),
					level=logging.ERROR, noiselevel=-1)

	if(mybestpv != mypvs) and not "--quiet" in myopts:
		print()
		print(red(" * ")+bold("An update to portage is available.")+" It is _highly_ recommended")
		print(red(" * ")+"that you update portage now, before any other packages are updated.")
		print()
		print(red(" * ")+"To update portage, run 'emerge portage' now.")
		print()

	display_news_notification(root_config, myopts)
	return os.EX_OK

def action_uninstall(settings, trees, ldpath_mtimes,
	opts, action, files, spinner):
	# For backward compat, some actions do not require leading '='.
	ignore_missing_eq = action in ('clean', 'unmerge')
	root = settings['ROOT']
	vardb = trees[root]['vartree'].dbapi
	valid_atoms = []
	lookup_owners = []

	# Ensure atoms are valid before calling unmerge().
	# For backward compat, leading '=' is not required.
	for x in files:
		if is_valid_package_atom(x) or \
			(ignore_missing_eq and is_valid_package_atom('=' + x)):

			try:
				valid_atoms.append(
					dep_expand(x, mydb=vardb, settings=settings))
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

		elif x.startswith(os.sep):
			if not x.startswith(root):
				writemsg_level(("!!! '%s' does not start with" + \
					" $ROOT.\n") % x, level=logging.ERROR, noiselevel=-1)
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

			for cp in vardb.cp_all():
				if extended_cp_match(ext_atom.cp, cp):
					atom = cp
					if ext_atom.slot:
						atom += ":" + ext_atom.slot
					if ext_atom.repo:
						atom += "::" + ext_atom.repo

					if vardb.match(atom):
						valid_atoms.append(Atom(atom, allow_repo=True))

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
				slot = vardb.aux_get(cpv, ['SLOT'])[0]
				if not slot:
					# portage now masks packages with missing slot, but it's
					# possible that one was installed by an older version
					atom = portage.cpv_getkey(cpv)
				else:
					atom = '%s:%s' % (portage.cpv_getkey(cpv), slot)
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

	# Create a Scheduler for calls to unmerge(), in order to cause
	# redirection of ebuild phase output to logs as required for
	# options such as --quiet.
	sched = Scheduler(settings, trees, None, opts,
		spinner)
	sched._background = sched._background_mode()
	sched._status_display.quiet = True

	if sched._background:
		sched.settings.unlock()
		sched.settings["PORTAGE_BACKGROUND"] = "1"
		sched.settings.backup_changes("PORTAGE_BACKGROUND")
		sched.settings.lock()
		sched.pkgsettings[root] = portage.config(clone=sched.settings)

	if action in ('clean', 'unmerge') or \
		(action == 'prune' and "--nodeps" in opts):
		# When given a list of atoms, unmerge them in the order given.
		ordered = action == 'unmerge'
		unmerge(trees[settings["ROOT"]]['root_config'], opts, action,
			valid_atoms, ldpath_mtimes, ordered=ordered,
			scheduler=sched._sched_iface)
		rval = os.EX_OK
	else:
		rval = action_depclean(settings, trees, ldpath_mtimes,
			opts, action, valid_atoms, spinner, scheduler=sched._sched_iface)

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

	if "--quiet" in myopts or "--quiet-build" in myopts:
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
	elif settings.get('TERM') == 'dumb' or \
		not sys.stdout.isatty():
		portage.output.havecolor = 0
		settings["NOCOLOR"] = "true"
		settings.backup_changes("NOCOLOR")

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

def getportageversion(portdir, target_root, profile, chost, vardb):
	profilever = None
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
			libcver.append("-".join(portage.catpkgsplit(cpv)[1:]))
	else:
		libcver = ["unavailable"]

	gccver = getgccversion(chost)
	unameout=platform.release()+" "+platform.machine()

	return "Portage %s (%s, %s, %s, %s)" % \
		(portage.VERSION, profilever, gccver, ",".join(libcver), unameout)

def git_sync_timestamps(settings, portdir):
	"""
	Since git doesn't preserve timestamps, synchronize timestamps between
	entries and ebuilds/eclasses. Assume the cache has the correct timestamp
	for a given file as long as the file in the working tree is not modified
	(relative to HEAD).
	"""
	cache_dir = os.path.join(portdir, "metadata", "cache")
	if not os.path.isdir(cache_dir):
		return os.EX_OK
	writemsg_level(">>> Synchronizing timestamps...\n")

	from portage.cache.cache_errors import CacheError
	try:
		cache_db = settings.load_best_module("portdbapi.metadbmodule")(
			portdir, "metadata/cache", portage.auxdbkeys[:], readonly=True)
	except CacheError as e:
		writemsg_level("!!! Unable to instantiate cache: %s\n" % (e,),
			level=logging.ERROR, noiselevel=-1)
		return 1

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
	import subprocess
	proc = subprocess.Popen(args, stdout=subprocess.PIPE)
	modified_files = set(_unicode_decode(l).rstrip("\n") for l in proc.stdout)
	rval = proc.wait()
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

def load_emerge_config(trees=None):
	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		v = os.environ.get(envvar, None)
		if v and v.strip():
			kwargs[k] = v
	trees = portage.create_trees(trees=trees, **kwargs)

	for root, root_trees in trees.items():
		settings = root_trees["vartree"].settings
		settings._init_dirs()
		setconfig = load_default_config(settings, root_trees)
		root_trees["root_config"] = RootConfig(settings, root_trees, setconfig)

	settings = trees["/"]["vartree"].settings

	for myroot in trees:
		if myroot != "/":
			settings = trees[myroot]["vartree"].settings
			break

	mtimedbfile = os.path.join(settings['EROOT'], portage.CACHE_PATH, "mtimedb")
	mtimedb = portage.MtimeDB(mtimedbfile)
	portage.output._init(config_root=settings['PORTAGE_CONFIGROOT'])
	QueryCommand._db = trees
	return settings, trees, mtimedb

def chk_updated_cfg_files(eroot, config_protect):
	target_root = eroot
	result = list(
		portage.util.find_updated_config_files(target_root, config_protect))

	for x in result:
		writemsg_level("\n %s " % (colorize("WARN", "* IMPORTANT:"),),
			level=logging.INFO, noiselevel=-1)
		if not x[1]: # it's a protected file
			writemsg_level("config file '%s' needs updating.\n" % x[0],
				level=logging.INFO, noiselevel=-1)
		else: # it's a protected dir
			if len(x[1]) == 1:
				head, tail = os.path.split(x[1][0])
				tail = tail[len("._cfg0000_"):]
				fpath = os.path.join(head, tail)
				writemsg_level("config file '%s' needs updating.\n" % fpath,
					level=logging.INFO, noiselevel=-1)
			else:
				writemsg_level("%d config files in '%s' need updating.\n" % \
					(len(x[1]), x[0]), level=logging.INFO, noiselevel=-1)

	if result:
		print(" "+yellow("*")+" See the "+colorize("INFORM","CONFIGURATION FILES")\
				+ " section of the " + bold("emerge"))
		print(" "+yellow("*")+" man page to learn how to update config files.")

def display_news_notification(root_config, myopts):
	target_root = root_config.settings['EROOT']
	trees = root_config.trees
	settings = trees["vartree"].settings
	portdb = trees["porttree"].dbapi
	vardb = trees["vartree"].dbapi
	NEWS_PATH = os.path.join("metadata", "news")
	UNREAD_PATH = os.path.join(target_root, NEWS_LIB_PATH, "news")
	newsReaderDisplay = False
	update = "--pretend" not in myopts
	if "news" not in settings.features:
		return

	for repo in portdb.getRepositories():
		unreadItems = checkUpdatedNewsItems(
			portdb, vardb, NEWS_PATH, UNREAD_PATH, repo, update=update)
		if unreadItems:
			if not newsReaderDisplay:
				newsReaderDisplay = True
				print()
			print(colorize("WARN", " * IMPORTANT:"), end=' ')
			print("%s news items need reading for repository '%s'." % (unreadItems, repo))


	if newsReaderDisplay:
		print(colorize("WARN", " *"), end=' ')
		print("Use " + colorize("GOOD", "eselect news") + " to read news items.")
		print()

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

	mystatus, myoutput = subprocess_getstatusoutput("gcc-config -c")
	if mystatus == os.EX_OK and myoutput.startswith(chost + "-"):
		return myoutput.replace(chost + "-", gcc_ver_prefix, 1)

	mystatus, myoutput = subprocess_getstatusoutput(
		chost + "-" + gcc_ver_command)
	if mystatus == os.EX_OK:
		return gcc_ver_prefix + myoutput

	mystatus, myoutput = subprocess_getstatusoutput(gcc_ver_command)
	if mystatus == os.EX_OK:
		return gcc_ver_prefix + myoutput

	portage.writemsg(gcc_not_found_error, noiselevel=-1)
	return "[unavailable]"

def checkUpdatedNewsItems(portdb, vardb, NEWS_PATH, UNREAD_PATH, repo_id,
	update=False):
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
	return manager.getUnreadItems( repo_id, update=update )

