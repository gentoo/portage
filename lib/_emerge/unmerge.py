# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import signal
import sys
import textwrap
import portage
from portage import os
from portage.dbapi._expand_new_virt import expand_new_virt
from portage.localization import _
from portage.output import bold, colorize, darkgreen, green
from portage._sets import SETPREFIX
from portage._sets.base import EditablePackageSet
from portage.versions import cpv_sort_key, _pkg_str

from _emerge.emergelog import emergelog
from _emerge.Package import Package
from _emerge.UserQuery import UserQuery
from _emerge.UninstallFailure import UninstallFailure
from _emerge.countdown import countdown

def _unmerge_display(root_config, myopts, unmerge_action,
	unmerge_files, clean_delay=1, ordered=0,
	writemsg_level=portage.util.writemsg_level):
	"""
	Returns a tuple of (returncode, pkgmap) where returncode is
	os.EX_OK if no errors occur, and 1 otherwise.
	"""

	quiet = "--quiet" in myopts
	settings = root_config.settings
	sets = root_config.sets
	vartree = root_config.trees["vartree"]
	candidate_catpkgs=[]
	global_unmerge=0
	out = portage.output.EOutput()
	pkg_cache = {}
	db_keys = list(vartree.dbapi._aux_cache_keys)

	def _pkg(cpv):
		pkg = pkg_cache.get(cpv)
		if pkg is None:
			pkg = Package(built=True, cpv=cpv, installed=True,
				metadata=zip(db_keys, vartree.dbapi.aux_get(cpv, db_keys)),
				operation="uninstall", root_config=root_config,
				type_name="installed")
			pkg_cache[cpv] = pkg
		return pkg

	vdb_path = os.path.join(settings["EROOT"], portage.VDB_PATH)
	try:
		# At least the parent needs to exist for the lock file.
		portage.util.ensure_dirs(vdb_path)
	except portage.exception.PortageException:
		pass
	vdb_lock = None
	try:
		if os.access(vdb_path, os.W_OK):
			vartree.dbapi.lock()
			vdb_lock = True

		realsyslist = []
		sys_virt_map = {}
		for x in sets["system"].getAtoms():
			for atom in expand_new_virt(vartree.dbapi, x):
				if not atom.blocker:
					realsyslist.append(atom)
					if atom.cp != x.cp:
						sys_virt_map[atom.cp] = x.cp

		syslist = []
		for x in realsyslist:
			mycp = x.cp
			# Since Gentoo stopped using old-style virtuals in
			# 2011, typically it's possible to avoid getvirtuals()
			# calls entirely. It will not be triggered here by
			# new-style virtuals since those are expanded to
			# non-virtual atoms above by expand_new_virt().
			if mycp.startswith("virtual/") and \
				mycp in settings.getvirtuals():
				providers = []
				for provider in settings.getvirtuals()[mycp]:
					if vartree.dbapi.match(provider):
						providers.append(provider)
				if len(providers) == 1:
					syslist.extend(providers)
			else:
				syslist.append(mycp)
		syslist = frozenset(syslist)

		if not unmerge_files:
			if unmerge_action in ["rage-clean", "unmerge"]:
				print()
				print(bold("emerge %s" % unmerge_action) +
						" can only be used with specific package names")
				print()
				return 1, {}

			global_unmerge = 1

		# process all arguments and add all
		# valid db entries to candidate_catpkgs
		if global_unmerge:
			if not unmerge_files:
				candidate_catpkgs.extend(vartree.dbapi.cp_all())
		else:
			#we've got command-line arguments
			if not unmerge_files:
				print("\nNo packages to %s have been provided.\n" %
						unmerge_action)
				return 1, {}
			for x in unmerge_files:
				arg_parts = x.split('/')
				if x[0] not in [".","/"] and \
					arg_parts[-1][-7:] != ".ebuild":
					#possible cat/pkg or dep; treat as such
					candidate_catpkgs.append(x)
				elif unmerge_action in ["prune","clean"]:
					print("\n!!! Prune and clean do not accept individual" + \
						" ebuilds as arguments;\n    skipping.\n")
					continue
				else:
					# it appears that the user is specifying an installed
					# ebuild and we're in "unmerge" mode, so it's ok.
					if not os.path.exists(x):
						print("\n!!! The path '"+x+"' doesn't exist.\n")
						return 1, {}

					absx   = os.path.abspath(x)
					sp_absx = absx.split("/")
					if sp_absx[-1][-7:] == ".ebuild":
						del sp_absx[-1]
						absx = "/".join(sp_absx)

					sp_absx_len = len(sp_absx)

					vdb_path = os.path.join(settings["EROOT"], portage.VDB_PATH)

					sp_vdb     = vdb_path.split("/")
					sp_vdb_len = len(sp_vdb)

					if not os.path.exists(absx+"/CONTENTS"):
						print("!!! Not a valid db dir: "+str(absx))
						return 1, {}

					if sp_absx_len <= sp_vdb_len:
						# The Path is shorter... so it can't be inside the vdb.
						print(sp_absx)
						print(absx)
						print("\n!!!",x,"cannot be inside "+ \
							vdb_path+"; aborting.\n")
						return 1, {}

					for idx in range(0,sp_vdb_len):
						if idx >= sp_absx_len or sp_vdb[idx] != sp_absx[idx]:
							print(sp_absx)
							print(absx)
							print("\n!!!", x, "is not inside "+\
								vdb_path+"; aborting.\n")
							return 1, {}

					print("="+"/".join(sp_absx[sp_vdb_len:]))
					candidate_catpkgs.append(
						"="+"/".join(sp_absx[sp_vdb_len:]))

		newline=""
		if not quiet:
			newline="\n"
		if settings["ROOT"] != "/":
			writemsg_level(darkgreen(newline+ \
				">>> Using system located in ROOT tree %s\n" % \
				settings["ROOT"]))

		if ("--pretend" in myopts or "--ask" in myopts) and not quiet:
			writemsg_level(darkgreen(newline+\
				">>> These are the packages that would be unmerged:\n"))

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
				mymatch = vartree.dbapi.match(x)
			except portage.exception.AmbiguousPackageName as errpkgs:
				print("\n\n!!! The short ebuild name \"" + \
					x + "\" is ambiguous.  Please specify")
				print("!!! one of the following fully-qualified " + \
					"ebuild names instead:\n")
				for i in errpkgs[0]:
					print("    " + green(i))
				print()
				sys.exit(1)

			if not mymatch and x[0] not in "<>=~":
				mymatch = vartree.dep_match(x)
			if not mymatch:
				portage.writemsg("\n--- Couldn't find '%s' to %s.\n" % \
					(x.replace("null/", ""), unmerge_action), noiselevel=-1)
				continue

			pkgmap.append(
				{"protected": set(), "selected": set(), "omitted": set()})
			mykey = len(pkgmap) - 1
			if unmerge_action in ["rage-clean", "unmerge"]:
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
						myslot = vartree.getslot(mypkg)
					else:
						# since we're pruning, we don't care about slots
						# and put all the pkgs in together
						myslot = 0
					if myslot not in slotmap:
						slotmap[myslot] = {}
					slotmap[myslot][vartree.dbapi.cpv_counter(mypkg)] = mypkg

				for mypkg in vartree.dbapi.cp_list(
					portage.cpv_getkey(mymatch[0])):
					myslot = vartree.getslot(mypkg)
					if myslot not in slotmap:
						slotmap[myslot] = {}
					slotmap[myslot][vartree.dbapi.cpv_counter(mypkg)] = mypkg

				for myslot in slotmap:
					counterkeys = list(slotmap[myslot])
					if not counterkeys:
						continue
					counterkeys.sort()
					pkgmap[mykey]["protected"].add(
						slotmap[myslot][counterkeys[-1]])
					del counterkeys[-1]

					for counter in counterkeys[:]:
						mypkg = slotmap[myslot][counter]
						if mypkg not in mymatch:
							counterkeys.remove(counter)
							pkgmap[mykey]["protected"].add(
								slotmap[myslot][counter])

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
			return 1, {}

		if not numselected:
			portage.writemsg_stdout(
				"\n>>> No packages selected for removal by " + \
				unmerge_action + "\n")
			return 1, {}
	finally:
		if vdb_lock:
			vartree.dbapi.flush_cache()
			vartree.dbapi.unlock()

	# generate a list of package sets that are directly or indirectly listed in "selected",
	# as there is no persistent list of "installed" sets
	installed_sets = ["selected"]
	stop = False
	pos = 0
	while not stop:
		stop = True
		pos = len(installed_sets)
		for s in installed_sets[pos - 1:]:
			if s not in sets:
				continue
			candidates = [x[len(SETPREFIX):] for x in sets[s].getNonAtoms() if x.startswith(SETPREFIX)]
			if candidates:
				stop = False
				installed_sets += candidates
	installed_sets = [x for x in installed_sets if x not in root_config.setconfig.active]
	del stop, pos

	# we don't want to unmerge packages that are still listed in user-editable package sets
	# listed in "world" as they would be remerged on the next update of "world" or the
	# relevant package sets.
	unknown_sets = set()
	for cp in range(len(pkgmap)):
		for cpv in pkgmap[cp]["selected"].copy():
			try:
				pkg = _pkg(cpv)
			except KeyError:
				# It could have been uninstalled
				# by a concurrent process.
				continue

			if unmerge_action != "clean" and root_config.root == "/":
				skip_pkg = False
				if portage.match_from_list(portage.const.PORTAGE_PACKAGE_ATOM,
						[pkg]):
					msg = ("Not unmerging package %s "
							"since there is no valid reason for Portage to "
							"%s itself.") % (pkg.cpv, unmerge_action)
					skip_pkg = True
				elif vartree.dbapi._dblink(cpv).isowner(
						portage._python_interpreter):
					msg = ("Not unmerging package %s since there is no valid "
							"reason for Portage to %s currently used Python "
							"interpreter.") % (pkg.cpv, unmerge_action)
					skip_pkg = True
				if skip_pkg:
					for line in textwrap.wrap(msg, 75):
						out.eerror(line)
					# adjust pkgmap so the display output is correct
					pkgmap[cp]["selected"].remove(cpv)
					all_selected.remove(cpv)
					pkgmap[cp]["protected"].add(cpv)
					continue

			parents = []
			for s in installed_sets:
				# skip sets that the user requested to unmerge, and skip world
				# user-selected set, since the package will be removed from
				# that set later on.
				if s in root_config.setconfig.active or s == "selected":
					continue

				if s not in sets:
					if s in unknown_sets:
						continue
					unknown_sets.add(s)
					out = portage.output.EOutput()
					out.eerror(("Unknown set '@%s' in %s%s") % \
						(s, root_config.settings['EROOT'], portage.const.WORLD_SETS_FILE))
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
				print(colorize("WARN", "Package %s is going to be unmerged," % cpv))
				print(colorize("WARN", "but still listed in the following package sets:"))
				print("    %s\n" % ", ".join(parents))

	del installed_sets

	numselected = len(all_selected)
	if not numselected:
		writemsg_level(
			"\n>>> No packages selected for removal by " + \
			unmerge_action + "\n")
		return 1, {}

	# Unmerge order only matters in some cases
	if not ordered:
		unordered = {}
		for d in pkgmap:
			selected = d["selected"]
			if not selected:
				continue
			cp = portage.cpv_getkey(next(iter(selected)))
			cp_dict = unordered.get(cp)
			if cp_dict is None:
				cp_dict = {}
				unordered[cp] = cp_dict
				for k in d:
					cp_dict[k] = set()
			for k, v in d.items():
				cp_dict[k].update(v)
		pkgmap = [unordered[cp] for cp in sorted(unordered)]

	# Sort each set of selected packages
	if ordered:
		for pkg in pkgmap:
			pkg["selected"] = sorted(pkg["selected"], key=cpv_sort_key())

	for x in range(len(pkgmap)):
		selected = pkgmap[x]["selected"]
		if not selected:
			continue
		for mytype, mylist in pkgmap[x].items():
			if mytype == "selected":
				continue
			mylist.difference_update(all_selected)
		cp = portage.cpv_getkey(next(iter(selected)))
		for y in vartree.dep_match(cp):
			if y not in pkgmap[x]["omitted"] and \
				y not in pkgmap[x]["selected"] and \
				y not in pkgmap[x]["protected"] and \
				y not in all_selected:
				pkgmap[x]["omitted"].add(y)
		if global_unmerge and not pkgmap[x]["selected"]:
			#avoid cluttering the preview printout with stuff that isn't getting unmerged
			continue
		if not (pkgmap[x]["protected"] or pkgmap[x]["omitted"]) and cp in syslist:
			virt_cp = sys_virt_map.get(cp)
			if virt_cp is None:
				cp_info = "'%s'" % (cp,)
			else:
				cp_info = "'%s' (%s)" % (cp, virt_cp)
			writemsg_level(colorize("BAD","\n\n!!! " + \
				"%s is part of your system profile.\n" % (cp_info,)),
				level=logging.WARNING, noiselevel=-1)
			writemsg_level(colorize("WARN","!!! Unmerging it may " + \
				"be damaging to your system.\n\n"),
				level=logging.WARNING, noiselevel=-1)
		if not quiet:
			writemsg_level("\n %s\n" % (bold(cp),), noiselevel=-1)
		else:
			writemsg_level(bold(cp) + ": ", noiselevel=-1)
		for mytype in ["selected","protected","omitted"]:
			if not quiet:
				writemsg_level((mytype + ": ").rjust(14), noiselevel=-1)
			if pkgmap[x][mytype]:
				sorted_pkgs = []
				for mypkg in pkgmap[x][mytype]:
					try:
						sorted_pkgs.append(mypkg.cpv)
					except AttributeError:
						sorted_pkgs.append(_pkg_str(mypkg))
				sorted_pkgs.sort(key=cpv_sort_key())
				for mypkg in sorted_pkgs:
					if mytype == "selected":
						writemsg_level(
							colorize("UNMERGE_WARN", mypkg.version + " "),
							noiselevel=-1)
					else:
						writemsg_level(
							colorize("GOOD", mypkg.version + " "),
							noiselevel=-1)
			else:
				writemsg_level("none ", noiselevel=-1)
			if not quiet:
				writemsg_level("\n", noiselevel=-1)
		if quiet:
			writemsg_level("\n", noiselevel=-1)

	writemsg_level("\nAll selected packages: %s\n" %
				" ".join('=%s' % x for x in all_selected), noiselevel=-1)

	writemsg_level("\n>>> " + colorize("UNMERGE_WARN", "'Selected'") + \
		" packages are slated for removal.\n")
	writemsg_level(">>> " + colorize("GOOD", "'Protected'") + \
			" and " + colorize("GOOD", "'omitted'") + \
			" packages will not be removed.\n\n")

	return os.EX_OK, pkgmap

def unmerge(root_config, myopts, unmerge_action,
	unmerge_files, ldpath_mtimes, autoclean=0,
	clean_world=1, clean_delay=1, ordered=0, raise_on_error=0,
	scheduler=None, writemsg_level=portage.util.writemsg_level):
	"""
	Returns os.EX_OK if no errors occur, 1 if an error occurs, and
	130 if interrupted due to a 'no' answer for --ask.
	"""

	if clean_world:
		clean_world = myopts.get('--deselect') != 'n'

	rval, pkgmap = _unmerge_display(root_config, myopts,
		unmerge_action, unmerge_files,
		clean_delay=clean_delay, ordered=ordered,
		writemsg_level=writemsg_level)

	if rval != os.EX_OK:
		return rval

	enter_invalid = '--ask-enter-invalid' in myopts
	vartree = root_config.trees["vartree"]
	sets = root_config.sets
	settings = root_config.settings
	mysettings = portage.config(clone=settings)
	xterm_titles = "notitles" not in settings.features

	if "--pretend" in myopts:
		#we're done... return
		return os.EX_OK
	if "--ask" in myopts:
		uq = UserQuery(myopts)
		if uq.query("Would you like to unmerge these packages?",
			enter_invalid) == "No":
			# enter pretend mode for correct formatting of results
			myopts["--pretend"] = True
			print()
			print("Quitting.")
			print()
			return 128 + signal.SIGINT

	if not vartree.dbapi.writable:
		writemsg_level("!!! %s\n" %
			_("Read-only file system: %s") % vartree.dbapi._dbroot,
			level=logging.ERROR, noiselevel=-1)
		return 1

	#the real unmerging begins, after a short delay unless we're raging....
	if not unmerge_action == "rage-clean" and clean_delay and not autoclean:
		countdown(int(settings["CLEAN_DELAY"]), ">>> Unmerging")

	all_selected = set()
	all_selected.update(*[x["selected"] for x in pkgmap])

	# Set counter variables
	curval = 1
	maxval = len(all_selected)

	for x in range(len(pkgmap)):
		for y in pkgmap[x]["selected"]:
			emergelog(xterm_titles, "=== Unmerging... ("+y+")")
			message = ">>> Unmerging ({0} of {1}) {2}...\n".format(
				colorize("MERGE_LIST_PROGRESS", str(curval)),
				colorize("MERGE_LIST_PROGRESS", str(maxval)),
				y)
			writemsg_level(message, noiselevel=-1)
			curval += 1

			mysplit = y.split("/")
			#unmerge...
			retval = portage.unmerge(mysplit[0], mysplit[1],
				settings=mysettings,
				vartree=vartree, ldpath_mtimes=ldpath_mtimes,
				scheduler=scheduler)

			if retval != os.EX_OK:
				emergelog(xterm_titles, " !!! unmerge FAILURE: "+y)
				if raise_on_error:
					raise UninstallFailure(retval)
				sys.exit(retval)
			else:
				if clean_world and hasattr(sets["selected"], "cleanPackage")\
						and hasattr(sets["selected"], "lock"):
					sets["selected"].lock()
					if hasattr(sets["selected"], "load"):
						sets["selected"].load()
					sets["selected"].cleanPackage(vartree.dbapi, y)
					sets["selected"].unlock()
				emergelog(xterm_titles, " >>> unmerge success: "+y)

	if clean_world and hasattr(sets["selected"], "remove")\
			and hasattr(sets["selected"], "lock"):
		sets["selected"].lock()
		# load is called inside remove()
		for s in root_config.setconfig.active:
			sets["selected"].remove(SETPREFIX + s)
		sets["selected"].unlock()

	return os.EX_OK
