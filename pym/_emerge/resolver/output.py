# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	"display", "filter_iuse_defaults",
	)

import codecs
import re
import sys

from portage import os
from portage import _encodings, _unicode_decode, _unicode_encode
from portage.dbapi.dep_expand import dep_expand
from portage.const import PORTAGE_PACKAGE_ATOM
from portage.dep import cpvequal, match_from_list
from portage.exception import InvalidDependString
from portage._sets.base import InternalPackageSet
from portage.output import blue, bold, colorize, create_color_func, darkblue, darkgreen, green, nc_len, red, \
	teal, turquoise, yellow
bad = create_color_func("BAD")
from portage.util import writemsg, writemsg_stdout
from portage.versions import best, catpkgsplit, cpv_getkey

from _emerge.Blocker import Blocker
from _emerge.create_world_atom import create_world_atom
from _emerge.Package import Package

if sys.hexversion >= 0x3000000:
	basestring = str

def filter_iuse_defaults(iuse):
	for flag in iuse:
		if flag.startswith("+") or flag.startswith("-"):
			yield flag[1:]
		else:
			yield flag

class _RepoDisplay(object):
	def __init__(self, roots):
		self._shown_repos = {}
		self._unknown_repo = False
		repo_paths = set()
		for root_config in roots.values():
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
		for root_config in roots.values():
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
		for repo_path, repo_index in shown_repos.items():
			show_repo_paths[repo_index] = repo_path
		if show_repo_paths:
			for index, repo_path in enumerate(show_repo_paths):
				output.append(" "+teal("["+str(index)+"]")+" %s\n" % repo_path)
		if unknown_repo:
			output.append(" "+teal("[?]") + \
				" indicates that the source repository could not be determined\n")
		return "".join(output)

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'])

class _PackageCounters(object):

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
		self.interactive              = 0
		self.binary                   = 0

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
		if self.binary > 0:
			details.append("%s binary" % self.binary)
			if self.binary > 1:
				details[-1] = details[-1][:-1] + "ies"
		if self.uninst > 0:
			details.append("%s uninstall" % self.uninst)
			if self.uninst > 1:
				details[-1] += "s"
		if self.interactive > 0:
			details.append("%s %s" % (self.interactive,
				colorize("WARN", "interactive")))
		myoutput.append(", ".join(details))
		if total_installs != 0:
			myoutput.append(")")
		myoutput.append(", Size of downloads: %s" % _format_size(self.totalsize))
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

class _DisplayConfig(object):
	def __init__(self, depgraph, mylist, favorites, verbosity):
		frozen_config = depgraph._frozen_config
		dynamic_config = depgraph._dynamic_config

		self.mylist = mylist
		self.favorites = InternalPackageSet(favorites)
		self.verbosity = verbosity

		if self.verbosity is None:
			self.verbosity = ("--quiet" in frozen_config.myopts and 1 or \
				"--verbose" in frozen_config.myopts and 3 or 2)

		self.oneshot = "--oneshot" in frozen_config.myopts or \
			"--onlydeps" in frozen_config.myopts
		self.columns = "--columns" in frozen_config.myopts
		self.tree_display = "--tree" in frozen_config.myopts
		self.alphabetical = "--alphabetical" in frozen_config.myopts
		self.quiet = "--quiet" in frozen_config.myopts
		self.all_flags = self.verbosity == 3 or self.quiet
		self.print_use_string = self.verbosity != 1 or "--verbose" in frozen_config.myopts
		self.changelog = "--changelog" in frozen_config.myopts
		self.edebug = frozen_config.edebug
		self.no_restart = frozen_config._opts_no_restart.intersection(frozen_config.myopts)
		self.unordered_display = "--unordered-display" in frozen_config.myopts

		mywidth = 130
		if "COLUMNWIDTH" in frozen_config.settings:
			try:
				mywidth = int(frozen_config.settings["COLUMNWIDTH"])
			except ValueError as e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg("!!! Unable to parse COLUMNWIDTH='%s'\n" % \
					frozen_config.settings["COLUMNWIDTH"], noiselevel=-1)
				del e
		self.columnwidth = mywidth

		self.repo_display = _RepoDisplay(frozen_config.roots)
		self.trees = frozen_config.trees
		self.pkgsettings = frozen_config.pkgsettings
		self.target_root = frozen_config.target_root
		self.running_root = frozen_config._running_root
		self.roots = frozen_config.roots

		self.blocker_parents = dynamic_config._blocker_parents
		self.reinstall_nodes = dynamic_config._reinstall_nodes
		self.digraph = dynamic_config.digraph
		self.blocker_uninstalls = dynamic_config._blocker_uninstalls
		self.slot_pkg_map = dynamic_config._slot_pkg_map
		self.set_nodes = dynamic_config._set_nodes

		self.pkg_use_enabled = depgraph._pkg_use_enabled
		self.pkg = depgraph._pkg

# formats a size given in bytes nicely
def _format_size(mysize):
	if isinstance(mysize, basestring):
		return mysize
	if 0 != mysize % 1024:
		# Always round up to the next kB so that it doesn't show 0 kB when
		# some small file still needs to be fetched.
		mysize += 1024 - mysize % 1024
	mystr=str(mysize//1024)
	mycount=len(mystr)
	while (mycount > 3):
		mycount-=3
		mystr=mystr[:mycount]+","+mystr[mycount:]
	return mystr+" kB"

def display(depgraph, mylist, favorites=[], verbosity=None):

	conf = _DisplayConfig(depgraph, mylist, favorites, verbosity)

	changelogs=[]
	p=[]
	blockers = []
	counters = _PackageCounters()
	repo_display = conf.repo_display
	unsatisfied_blockers = []
	ordered_nodes = []
	for x in conf.mylist:
		if isinstance(x, Blocker):
			counters.blocks += 1
			if x.satisfied:
				ordered_nodes.append(x)
				counters.blocks_satisfied += 1
			else:
				unsatisfied_blockers.append(x)
		else:
			ordered_nodes.append(x)

	if conf.tree_display:
		display_list = _tree_display(conf, ordered_nodes)
	else:
		display_list = [(x, 0, True) for x in ordered_nodes]

	mylist = display_list
	for x in unsatisfied_blockers:
		mylist.append((x, 0, True))

	# files to fetch list - avoids counting a same file twice
	# in size display (verbose mode)
	myfetchlist=[]

	# Use this set to detect when all the "repoadd" strings are "[0]"
	# and disable the entire repo display in this case.
	repoadd_set = set()

	for mylist_index in range(len(mylist)):
		x, depth, ordered = mylist[mylist_index]
		pkg_type = x[0]
		myroot = x[1]
		pkg_key = x[2]
		portdb = conf.trees[myroot]["porttree"].dbapi
		vardb = conf.trees[myroot]["vartree"].dbapi
		pkgsettings = conf.pkgsettings[myroot]

		fetch=" "
		indent = " " * depth

		if isinstance(x, Blocker):
			if x.satisfied:
				blocker_style = "PKG_BLOCKER_SATISFIED"
				addl = "%s  %s  " % (colorize(blocker_style, "b"), fetch)
			else:
				blocker_style = "PKG_BLOCKER"
				addl = "%s  %s  " % (colorize(blocker_style, "B"), fetch)
			resolved = dep_expand(
				str(x.atom).lstrip("!"), mydb=vardb, settings=pkgsettings)
			if conf.columns and conf.quiet:
				addl += " " + colorize(blocker_style, str(resolved))
			else:
				addl = "[%s %s] %s%s" % \
					(colorize(blocker_style, "blocks"),
					addl, indent, colorize(blocker_style, str(resolved)))
			block_parents = conf.blocker_parents.parent_nodes(x)
			block_parents = set([pnode[2] for pnode in block_parents])
			block_parents = ", ".join(block_parents)
			if resolved!=x[2]:
				addl += colorize(blocker_style,
					" (\"%s\" is blocking %s)") % \
					(str(x.atom).lstrip("!"), block_parents)
			else:
				addl += colorize(blocker_style,
					" (is blocking %s)") % block_parents
			if isinstance(x, Blocker) and x.satisfied:
				if conf.columns:
					continue
				p.append(addl)
			else:
				blockers.append(addl)
		else:
			pkg_status = x[3]
			pkg_merge = ordered and pkg_status == "merge"
			if not pkg_merge and pkg_status == "merge":
				pkg_status = "nomerge"
			built = pkg_type != "ebuild"
			pkg = x
			metadata = pkg.metadata
			ebuild_path = None
			repo_name = metadata["repository"]
			if pkg.type_name == "ebuild":
				ebuild_path = portdb.findname(pkg.cpv)
				if ebuild_path is None:
					raise AssertionError(
						"ebuild not found for '%s'" % pkg.cpv)
				repo_path_real = os.path.dirname(os.path.dirname(
					os.path.dirname(ebuild_path)))
			else:
				repo_path_real = portdb.getRepositoryPath(repo_name)
			pkg_use = list(conf.pkg_use_enabled(pkg))
			if not pkg.built and pkg.operation == 'merge' and \
				'fetch' in pkg.metadata.restrict:
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
			installed_versions = vardb.match(cpv_getkey(pkg_key))
			if vardb.cpv_exists(pkg_key):
				addl="  "+yellow("R")+fetch+"  "
				if ordered:
					if pkg_merge:
						counters.reinst += 1
						if pkg_type == "binary":
							counters.binary += 1
					elif pkg_status == "uninstall":
						counters.uninst += 1
			# filter out old-style virtual matches
			elif installed_versions and \
				cpv_getkey(installed_versions[0]) == \
				cpv_getkey(pkg_key):
				myinslotlist = vardb.match(pkg.slot_atom)
				# If this is the first install of a new-style virtual, we
				# need to filter out old-style virtual matches.
				if myinslotlist and \
					cpv_getkey(myinslotlist[0]) != \
					cpv_getkey(pkg_key):
					myinslotlist = None
				if myinslotlist:
					myoldbest = myinslotlist[:]
					addl = "   " + fetch
					if not cpvequal(pkg_key,
						best([pkg_key] + myoldbest)):
						# Downgrade in slot
						addl += turquoise("U")+blue("D")
						if ordered:
							counters.downgrades += 1
							if pkg_type == "binary":
								counters.binary += 1
					else:
						# Update in slot
						addl += turquoise("U") + " "
						if ordered:
							counters.upgrades += 1
							if pkg_type == "binary":
								counters.binary += 1
				else:
					# New slot, mark it new.
					addl = " " + green("NS") + fetch + "  "
					myoldbest = vardb.match(cpv_getkey(pkg_key))
					if ordered:
						counters.newslot += 1
						if pkg_type == "binary":
							counters.binary += 1

				if conf.changelog:
					inst_matches = vardb.match(pkg.slot_atom)
					if inst_matches:
						ebuild_path_cl = ebuild_path
						if ebuild_path_cl is None:
							# binary package
							ebuild_path_cl = portdb.findname(pkg.cpv)

						if ebuild_path_cl is not None:
							changelogs.extend(_calc_changelog(
								ebuild_path_cl, inst_matches[0], pkg.cpv))
			else:
				addl = " " + green("N") + " " + fetch + "  "
				if ordered:
					counters.new += 1
					if pkg_type == "binary":
						counters.binary += 1

			verboseadd = ""
			repoadd = None

			if True:
				# USE flag display
				forced_flags = set()
				pkgsettings.setcpv(pkg) # for package.use.{mask,force}
				forced_flags.update(pkgsettings.useforce)
				forced_flags.update(pkgsettings.usemask)

				cur_use = [flag for flag in conf.pkg_use_enabled(pkg) \
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
				reinstall_for_flags = conf.reinstall_nodes.get(pkg)
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
					verboseadd += _create_use_string(conf, key.upper(),
						cur_iuse_map[key], iuse_forced[key],
						cur_use_map[key], old_iuse_map[key],
						old_use_map[key], is_new,
						reinst_flags_map.get(key))

			if conf.verbosity == 3:
				# size verbose
				mysize=0
				if pkg_type == "ebuild" and pkg_merge:
					try:
						myfilesdict = portdb.getfetchsizes(pkg_key,
							useflags=pkg_use, debug=conf.edebug)
					except InvalidDependString:
						# should have been masked before it was selected
						raise
					if myfilesdict is None:
						myfilesdict="[empty/missing/bad digest]"
					else:
						for myfetchfile in myfilesdict:
							if myfetchfile not in myfetchlist:
								mysize+=myfilesdict[myfetchfile]
								myfetchlist.append(myfetchfile)
						if ordered:
							counters.totalsize += mysize
					verboseadd += _format_size(mysize)

				# overlay verbose
				# assign index for a previous version in the same slot
				has_previous = False
				repo_name_prev = None
				slot_matches = vardb.match(pkg.slot_atom)
				if slot_matches:
					has_previous = True
					repo_name_prev = vardb.aux_get(slot_matches[0],
						["repository"])[0]

				# now use the data to generate output
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
				if repoadd:
					repoadd_set.add(repoadd)

			xs = [cpv_getkey(pkg_key)] + \
				list(catpkgsplit(pkg_key)[2:])
			if xs[2] == "r0":
				xs[2] = ""
			else:
				xs[2] = "-" + xs[2]

			oldlp = conf.columnwidth - 30
			newlp = oldlp - 30

			# Convert myoldbest from a list to a string.
			if not myoldbest:
				myoldbest = ""
			else:
				for pos, key in enumerate(myoldbest):
					key = catpkgsplit(key)[2] + \
						"-" + catpkgsplit(key)[3]
					if key[-3:] == "-r0":
						key = key[:-3]
					myoldbest[pos] = key
				myoldbest = blue("["+", ".join(myoldbest)+"]")

			pkg_cp = xs[0]
			root_config = conf.roots[myroot]
			system_set = root_config.sets["system"]
			world_set  = root_config.sets["selected"]

			pkg_system = False
			pkg_world = False
			try:
				pkg_system = system_set.findAtomForPackage(pkg, modified_use=conf.pkg_use_enabled(pkg))
				pkg_world  = world_set.findAtomForPackage(pkg, modified_use=conf.pkg_use_enabled(pkg))
				if not (conf.oneshot or pkg_world) and \
					myroot == conf.target_root and \
					conf.favorites.findAtomForPackage(pkg, modified_use=conf.pkg_use_enabled(pkg)):
					# Maybe it will be added to world now.
					if create_world_atom(pkg, conf.favorites, root_config):
						pkg_world = True
			except InvalidDependString:
				# This is reported elsewhere if relevant.
				pass

			def pkgprint(pkg_str):
				if pkg_merge:
					if built:
						if pkg_system:
							return colorize("PKG_BINARY_MERGE_SYSTEM", pkg_str)
						elif pkg_world:
							return colorize("PKG_BINARY_MERGE_WORLD", pkg_str)
						else:
							return colorize("PKG_BINARY_MERGE", pkg_str)
					else:
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

			if 'interactive' in pkg.metadata.properties and \
				pkg.operation == 'merge':
				addl = colorize("WARN", "I") + addl[1:]
				if ordered:
					counters.interactive += 1

			if x[1]!="/":
				if myoldbest:
					myoldbest +=" "
				if conf.columns:
					if conf.quiet:
						myprint=addl+" "+indent+pkgprint(pkg_cp)
						myprint=myprint+darkblue(" "+xs[1]+xs[2])+" "
						myprint=myprint+myoldbest
						myprint=myprint+darkgreen("to "+x[1])
						verboseadd = None
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
						myprint += darkgreen("to " + pkg.root)
				else:
					if not pkg_merge:
						myprint = "[%s] " % pkgprint(pkg_status.ljust(13))
					else:
						myprint = "[%s %s] " % (pkgprint(pkg_type), addl)
					myprint += indent + pkgprint(pkg_key) + " " + \
						myoldbest + darkgreen("to " + myroot)
			else:
				if conf.columns:
					if conf.quiet:
						myprint=addl+" "+indent+pkgprint(pkg_cp)
						myprint=myprint+" "+green(xs[1]+xs[2])+" "
						myprint=myprint+myoldbest
						verboseadd = None
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
						myprint += myoldbest
				else:
					if not pkg_merge:
						myprint = "[%s] %s%s %s" % \
							(pkgprint(pkg_status.ljust(13)),
							indent, pkgprint(pkg.cpv),
							myoldbest)
					else:
						myprint = "[%s %s] %s%s %s" % \
							(pkgprint(pkg_type), addl, indent,
							pkgprint(pkg.cpv), myoldbest)

			if conf.columns and pkg.operation == "uninstall":
				continue
			p.append((myprint, verboseadd, repoadd))

			if not conf.tree_display and \
				not conf.no_restart and \
				pkg.root == conf.running_root.root and \
				match_from_list(
				PORTAGE_PACKAGE_ATOM, [pkg]) and \
				not conf.quiet:
				if not vardb.cpv_exists(pkg.cpv) or \
					'9999' in pkg.cpv or \
					'git' in pkg.inherited or \
					'git-2' in pkg.inherited:
					if mylist_index < len(mylist) - 1:
						p.append(colorize("WARN", "*** Portage will stop merging at this point and reload itself,"))
						p.append(colorize("WARN", "    then resume the merge."))

	show_repos = repoadd_set and repoadd_set != set(["0"])

	for x in p:
		if isinstance(x, basestring):
			writemsg_stdout("%s\n" % (x,), noiselevel=-1)
			continue

		myprint, verboseadd, repoadd = x

		if verboseadd:
			myprint += " " + verboseadd

		if show_repos and repoadd:
			myprint += " " + teal("[%s]" % repoadd)

		writemsg_stdout("%s\n" % (myprint,), noiselevel=-1)

	for x in blockers:
		writemsg_stdout("%s\n" % (x,), noiselevel=-1)

	if conf.verbosity == 3:
		writemsg_stdout('\n%s\n' % (counters,), noiselevel=-1)
		if show_repos:
			# Use _unicode_decode() to force unicode format string so
			# that RepoDisplay.__unicode__() is called in python2.
			writemsg_stdout(_unicode_decode("%s") % (repo_display,),
				noiselevel=-1)

	if conf.changelog:
		writemsg_stdout('\n', noiselevel=-1)
		for revision,text in changelogs:
			writemsg_stdout(bold('*'+revision) + '\n' + text,
				noiselevel=-1)

	return os.EX_OK


def _create_use_string(conf, name, cur_iuse, iuse_forced, cur_use,
	old_iuse, old_use,
	is_new, reinst_flags):

	if not conf.print_use_string:
		return ""

	enabled = []
	if conf.alphabetical:
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
				(conf.all_flags or reinst_flag):
				flag_str = red(flag)
			elif flag not in old_iuse:
				flag_str = yellow(flag) + "%*"
			elif flag not in old_use:
				flag_str = green(flag) + "*"
		elif flag in removed_iuse:
			if conf.all_flags or reinst_flag:
				flag_str = yellow("-" + flag) + "%"
				if flag in old_use:
					flag_str += "*"
				flag_str = "(" + flag_str + ")"
				removed.append(flag_str)
			continue
		else:
			if is_new or flag in old_iuse and \
				flag not in old_use and \
				(conf.all_flags or reinst_flag):
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

	if conf.alphabetical:
		ret = " ".join(enabled)
	else:
		ret = " ".join(enabled + disabled + removed)
	if ret:
		ret = '%s="%s" ' % (name, ret)
	return ret


def _tree_display(conf, mylist):

	# If there are any Uninstall instances, add the
	# corresponding blockers to the digraph.
	mygraph = conf.digraph.copy()

	executed_uninstalls = set(node for node in mylist \
		if isinstance(node, Package) and node.operation == "unmerge")

	for uninstall in conf.blocker_uninstalls.leaf_nodes():
		uninstall_parents = \
			conf.blocker_uninstalls.parent_nodes(uninstall)
		if not uninstall_parents:
			continue

		# Remove the corresponding "nomerge" node and substitute
		# the Uninstall node.
		inst_pkg = conf.pkg(uninstall.cpv, "installed",
			uninstall.root_config, installed=True)

		try:
			mygraph.remove(inst_pkg)
		except KeyError:
			pass

		try:
			inst_pkg_blockers = conf.blocker_parents.child_nodes(inst_pkg)
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
			for parent in conf.blocker_parents.parent_nodes(blocker):
				if parent != inst_pkg:
					mygraph.add(blocker, parent)

		# If the uninstall task did not need to be executed because
		# of an upgrade, display Blocker -> Upgrade edges since the
		# corresponding Blocker -> Uninstall edges will not be shown.
		upgrade_node = \
			conf.slot_pkg_map[uninstall.root].get(uninstall.slot_atom)
		if upgrade_node is not None and \
			uninstall not in executed_uninstalls:
			for blocker in uninstall_parents:
				mygraph.add(upgrade_node, blocker)

	if conf.unordered_display:
		display_list = _unordered_tree_display(mygraph, mylist)
	else:
		display_list = _ordered_tree_display(conf, mygraph, mylist)

	_prune_tree_display(display_list)

	return display_list

def _unordered_tree_display(mygraph, mylist):
	display_list = []
	seen_nodes = set()

	def print_node(node, depth):

		if node in seen_nodes:
			pass
		else:
			seen_nodes.add(node)

			if isinstance(node, (Blocker, Package)):
				display_list.append((node, depth, True))
			else:
				depth = -1

			for child_node in mygraph.child_nodes(node):
				print_node(child_node, depth + 1)

	for root_node in mygraph.root_nodes():
		print_node(root_node, 0)

	return display_list

def _ordered_tree_display(conf, mygraph, mylist):
	depth = 0
	shown_edges = set()
	tree_nodes = []
	display_list = []

	for x in mylist:
		depth = len(tree_nodes)
		while depth and x not in \
			mygraph.child_nodes(tree_nodes[depth-1]):
				depth -= 1
		if depth:
			tree_nodes = tree_nodes[:depth]
			tree_nodes.append(x)
			display_list.append((x, depth, True))
			shown_edges.add((x, tree_nodes[depth-1]))
		else:
			traversed_nodes = set() # prevent endless circles
			traversed_nodes.add(x)
			def add_parents(current_node, ordered):
				parent_nodes = None
				# Do not traverse to parents if this node is an
				# an argument or a direct member of a set that has
				# been specified as an argument (system or world).
				if current_node not in conf.set_nodes:
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
			add_parents(x, True)

	return display_list

def _prune_tree_display(display_list):
	last_merge_depth = 0
	for i in range(len(display_list) - 1, -1, -1):
		node, depth, ordered = display_list[i]
		if not ordered and depth == 0 and i > 0 \
			and node == display_list[i-1][0] and \
			display_list[i-1][1] == 0:
			# An ordered node got a consecutive duplicate
			# when the tree was being filled in.
			del display_list[i]
			continue
		if ordered and isinstance(node, Package) \
			and node.operation in ('merge', 'uninstall'):
			last_merge_depth = depth
			continue
		if depth >= last_merge_depth or \
			i < len(display_list) - 1 and \
			depth >= display_list[i+1][1]:
				del display_list[i]

def _calc_changelog(ebuildpath,current,next):
	if ebuildpath == None or not os.path.exists(ebuildpath):
		return []
	current = '-'.join(catpkgsplit(current)[1:])
	if current.endswith('-r0'):
		current = current[:-3]
	next = '-'.join(catpkgsplit(next)[1:])
	if next.endswith('-r0'):
		next = next[:-3]
	changelogpath = os.path.join(os.path.split(ebuildpath)[0],'ChangeLog')
	try:
		changelog = codecs.open(_unicode_encode(changelogpath,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace'
		).read()
	except SystemExit:
		raise # Needed else can't exit
	except:
		return []
	divisions = _find_changelog_tags(changelog)
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

def _find_changelog_tags(changelog):
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
