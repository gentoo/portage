# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Resolver output display operation.
"""

__all__ = (
	"Display",
	)

import sys

from portage import os
from portage import _unicode_decode
from portage.dbapi.dep_expand import dep_expand
from portage.const import PORTAGE_PACKAGE_ATOM
from portage.dep import cpvequal, match_from_list
from portage.exception import InvalidDependString
from portage.output import ( blue, bold, colorize, create_color_func,
	darkblue, darkgreen, green, nc_len, red, teal, turquoise, yellow )
bad = create_color_func("BAD")
from portage.util import writemsg_stdout, writemsg_level
from portage.versions import best, catpkgsplit, cpv_getkey

from _emerge.Blocker import Blocker
from _emerge.create_world_atom import create_world_atom
from _emerge.resolver.output_helpers import ( _DisplayConfig, _tree_display,
	_PackageCounters, _create_use_string, _format_size, _calc_changelog, PkgInfo)

if sys.hexversion >= 0x3000000:
	basestring = str


class Display(object):
	"""Formats and outputs the depgrah supplied it for merge/re-merge, etc.

	__call__()
	@param depgraph: list
	@param favorites: defaults to []
	@param verbosity: integer, defaults to None
	"""

	def __init__(self):
		self.changelogs = []
		self.print_msg = []
		self.blockers = []
		self.counters = _PackageCounters()
		self.resolver = None
		self.resolved = None
		self.vardb = None
		self.portdb = None
		self.verboseadd = ''
		self.oldlp = None
		self.myfetchlist = None
		self.indent = ''
		self.is_new = True
		self.cur_use = None
		self.cur_iuse = None
		self.old_use = ''
		self.old_iuse = ''
		self.use_expand = None
		self.use_expand_hidden = None
		self.pkgsettings = None
		self.forced_flags = None
		self.newlp = None
		self.conf = None
		self.blocker_style = None


	def _blockers(self, pkg, fetch_symbol):
		"""Processes pkg for blockers and adds colorized strings to
		self.print_msg and self.blockers

		@param pkg: _emerge.Package instance
		@param fetch_symbol: string
		@rtype: bool
		Modifies class globals: self.blocker_style, self.resolved,
			self.print_msg
		"""
		if pkg.satisfied:
			self.blocker_style = "PKG_BLOCKER_SATISFIED"
			addl = "%s  %s  " % (colorize(self.blocker_style, "b"),
				fetch_symbol)
		else:
			self.blocker_style = "PKG_BLOCKER"
			addl = "%s  %s  " % (colorize(self.blocker_style, "B"),
				fetch_symbol)
		if self.conf.verbosity == 3:
			# add column for mask status
			addl += " "
		self.resolved = dep_expand(
			str(pkg.atom).lstrip("!"), mydb=self.vardb,
			settings=self.pkgsettings
			)
		if self.conf.columns and self.conf.quiet:
			addl += " " + colorize(self.blocker_style, str(self.resolved))
		else:
			addl = "[%s %s] %s%s" % \
				(colorize(self.blocker_style, "blocks"),
				addl, self.indent,
				colorize(self.blocker_style, str(self.resolved))
				)
		block_parents = self.conf.blocker_parents.parent_nodes(pkg)
		block_parents = set([pnode[2] for pnode in block_parents])
		block_parents = ", ".join(block_parents)
		if self.resolved != pkg[2]:
			addl += colorize(self.blocker_style,
				" (\"%s\" is blocking %s)") % \
				(str(pkg.atom).lstrip("!"), block_parents)
		else:
			addl += colorize(self.blocker_style,
				" (is blocking %s)") % block_parents
		if isinstance(pkg, Blocker) and pkg.satisfied:
			if self.conf.columns:
				return True
			self.print_msg.append(addl)
		else:
			self.blockers.append(addl)
		return False


	def _display_use(self, pkg, myoldbest, myinslotlist):
		""" USE flag display

		@param pkg: _emerge.Package instance
		@param myoldbest: list of installed versions
		@param myinslotlist: list of installed slots
		Modifies class globals: self.forced_flags, self.cur_iuse,
			self.old_iuse, self.old_use, self.use_expand
		"""

		self.forced_flags = set()
		self.forced_flags.update(pkg.use.force)
		self.forced_flags.update(pkg.use.mask)

		self.cur_use = [flag for flag in self.conf.pkg_use_enabled(pkg) \
			if flag in pkg.iuse.all]
		self.cur_iuse = sorted(pkg.iuse.all)

		if myoldbest and myinslotlist:
			previous_cpv = myoldbest[0].cpv
		else:
			previous_cpv = pkg.cpv
		if self.vardb.cpv_exists(previous_cpv):
			previous_pkg = self.vardb.match_pkgs('=' + previous_cpv)[0]
			self.old_iuse = sorted(previous_pkg.iuse.all)
			self.old_use = previous_pkg.use.enabled
			self.is_new = False
		else:
			self.old_iuse = []
			self.old_use = []
			self.is_new = True

		self.old_use = [flag for flag in self.old_use if flag in self.old_iuse]

		self.use_expand = self.pkgsettings["USE_EXPAND"].lower().split()
		self.use_expand.sort()
		self.use_expand.reverse()
		self.use_expand_hidden = \
			self.pkgsettings["USE_EXPAND_HIDDEN"].lower().split()
		return

	def gen_mask_str(self, pkg):
		"""
		@param pkg: _emerge.Package instance
		"""
		used_keyword = pkg.accepted_keyword()
		hardmasked = pkg.isHardMasked()
		mask_str = " "

		if hardmasked:
			mask_str = colorize("BAD", "#")
		elif not used_keyword:
			pass
		elif used_keyword not in self.pkgsettings['ACCEPT_KEYWORDS'].split():
			if used_keyword == "**":
				mask_str = colorize("BAD", "*")
			else:
				mask_str = colorize("WARN", "~")

		return mask_str

	def map_to_use_expand(self, myvals, forced_flags=False,
		remove_hidden=True):
		"""Map use expand variables

		@param myvals: list
		@param forced_flags: bool
		@param remove_hidden: bool
		@rtype ret dictionary
			or ret dict, forced dict.
		"""
		ret = {}
		forced = {}
		for exp in self.use_expand:
			ret[exp] = []
			forced[exp] = set()
			for val in myvals[:]:
				if val.startswith(exp.lower()+"_"):
					if val in self.forced_flags:
						forced[exp].add(val[len(exp)+1:])
					ret[exp].append(val[len(exp)+1:])
					myvals.remove(val)
		ret["USE"] = myvals
		forced["USE"] = [val for val in myvals \
			if val in self.forced_flags]
		if remove_hidden:
			for exp in self.use_expand_hidden:
				ret.pop(exp, None)
		if forced_flags:
			return ret, forced
		return ret


	def recheck_hidden(self, pkg):
		""" Prevent USE_EXPAND_HIDDEN flags from being hidden if they
		are the only thing that triggered reinstallation.

		@param pkg: _emerge.Package instance
		Modifies self.use_expand_hidden, self.use_expand, self.verboseadd
		"""
		reinst_flags_map = {}
		reinstall_for_flags = self.conf.reinstall_nodes.get(pkg)
		reinst_expand_map = None
		if reinstall_for_flags:
			reinst_flags_map = self.map_to_use_expand(
				list(reinstall_for_flags), remove_hidden=False)
			for k in list(reinst_flags_map):
				if not reinst_flags_map[k]:
					del reinst_flags_map[k]
			if not reinst_flags_map.get("USE"):
				reinst_expand_map = reinst_flags_map.copy()
				reinst_expand_map.pop("USE", None)
		if reinst_expand_map and \
			not set(reinst_expand_map).difference(
			self.use_expand_hidden):
			self.use_expand_hidden = \
				set(self.use_expand_hidden).difference(
				reinst_expand_map)

		cur_iuse_map, iuse_forced = \
			self.map_to_use_expand(self.cur_iuse, forced_flags=True)
		cur_use_map = self.map_to_use_expand(self.cur_use)
		old_iuse_map = self.map_to_use_expand(self.old_iuse)
		old_use_map = self.map_to_use_expand(self.old_use)

		self.use_expand.sort()
		self.use_expand.insert(0, "USE")

		for key in self.use_expand:
			if key in self.use_expand_hidden:
				continue
			self.verboseadd += _create_use_string(self.conf, key.upper(),
				cur_iuse_map[key], iuse_forced[key],
				cur_use_map[key], old_iuse_map[key],
				old_use_map[key], self.is_new,
				reinst_flags_map.get(key))
		return


	@staticmethod
	def pkgprint(pkg_str, pkg_info):
		"""Colorizes a string acording to pkg_info settings

		@param pkg_str: string
		@param pkg_info: dictionary
		@rtype colorized string
		"""
		if pkg_info.merge:
			if pkg_info.built:
				if pkg_info.system:
					return colorize("PKG_BINARY_MERGE_SYSTEM", pkg_str)
				elif pkg_info.world:
					return colorize("PKG_BINARY_MERGE_WORLD", pkg_str)
				else:
					return colorize("PKG_BINARY_MERGE", pkg_str)
			else:
				if pkg_info.system:
					return colorize("PKG_MERGE_SYSTEM", pkg_str)
				elif pkg_info.world:
					return colorize("PKG_MERGE_WORLD", pkg_str)
				else:
					return colorize("PKG_MERGE", pkg_str)
		elif pkg_info.operation == "uninstall":
			return colorize("PKG_UNINSTALL", pkg_str)
		else:
			if pkg_info.system:
				return colorize("PKG_NOMERGE_SYSTEM", pkg_str)
			elif pkg_info.world:
				return colorize("PKG_NOMERGE_WORLD", pkg_str)
			else:
				return colorize("PKG_NOMERGE", pkg_str)


	def verbose_size(self, pkg, repoadd_set, pkg_info):
		"""Determines the size of the downloads required

		@param pkg: _emerge.Package instance
		@param repoadd_set: set of repos to add
		@param pkg_info: dictionary
		Modifies class globals: self.myfetchlist, self.counters.totalsize,
			self.verboseadd, repoadd_set.
		"""
		mysize = 0
		if pkg.type_name == "ebuild" and pkg_info.merge:
			try:
				myfilesdict = self.portdb.getfetchsizes(pkg.cpv,
					useflags=pkg_info.use, myrepo=pkg.repo)
			except InvalidDependString:
				# should have been masked before it was selected
				raise
			if myfilesdict is None:
				myfilesdict = "[empty/missing/bad digest]"
			else:
				for myfetchfile in myfilesdict:
					if myfetchfile not in self.myfetchlist:
						mysize += myfilesdict[myfetchfile]
						self.myfetchlist.append(myfetchfile)
				if pkg_info.ordered:
					self.counters.totalsize += mysize
			self.verboseadd += _format_size(mysize)

		# overlay verbose
		# assign index for a previous version in the same slot
		slot_matches = self.vardb.match(pkg.slot_atom)
		if slot_matches:
			repo_name_prev = self.vardb.aux_get(slot_matches[0],
				["repository"])[0]
		else:
			repo_name_prev = None

		# now use the data to generate output
		if pkg.installed or not slot_matches:
			self.repoadd = self.conf.repo_display.repoStr(
				pkg_info.repo_path_real)
		else:
			repo_path_prev = None
			if repo_name_prev:
				repo_path_prev = self.portdb.getRepositoryPath(
					repo_name_prev)
			if repo_path_prev == pkg_info.repo_path_real:
				self.repoadd = self.conf.repo_display.repoStr(
					pkg_info.repo_path_real)
			else:
				self.repoadd = "%s=>%s" % (
					self.conf.repo_display.repoStr(repo_path_prev),
					self.conf.repo_display.repoStr(pkg_info.repo_path_real))
		if self.repoadd:
			repoadd_set.add(self.repoadd)


	@staticmethod
	def convert_myoldbest(myoldbest):
		"""converts and colorizes a version list to a string

		@param myoldbest: list
		@rtype string.
		"""
		# Convert myoldbest from a list to a string.
		myoldbest_str = ""
		if myoldbest:
			versions = []
			for pos, pkg in enumerate(myoldbest):
				key = catpkgsplit(pkg.cpv)[2] + \
					"-" + catpkgsplit(pkg.cpv)[3]
				if key[-3:] == "-r0":
					key = key[:-3]
				versions.append(key)
			myoldbest_str = blue("["+", ".join(versions)+"]")
		return myoldbest_str


	def set_interactive(self, pkg, ordered, addl):
		"""Increments counters.interactive if the pkg is to
		be merged and it's metadata has interactive set True

		@param pkg: _emerge.Package instance
		@param ordered: boolean
		@param addl: already defined string to add to
		"""
		if 'interactive' in pkg.metadata.properties and \
			pkg.operation == 'merge':
			addl = colorize("WARN", "I") + addl[1:]
			if ordered:
				self.counters.interactive += 1
		return addl

	def _set_non_root_columns(self, addl, pkg_info, pkg):
		"""sets the indent level and formats the output

		@param addl: already defined string to add to
		@param pkg_info: dictionary
		@param pkg: _emerge.Package instance
		@rtype string
		"""
		if self.conf.quiet:
			myprint = addl + " " + self.indent + \
				self.pkgprint(pkg_info.cp, pkg_info)
			myprint = myprint+darkblue(" "+pkg_info.ver)+" "
			myprint = myprint+pkg_info.oldbest
			myprint = myprint+darkgreen("to "+pkg.root)
			self.verboseadd = None
		else:
			if not pkg_info.merge:
				myprint = "[%s] %s%s" % \
					(self.pkgprint(pkg_info.operation.ljust(13), pkg_info),
					self.indent, self.pkgprint(pkg.cp, pkg_info))
			else:
				myprint = "[%s %s] %s%s" % \
					(self.pkgprint(pkg.type_name, pkg_info), addl,
					self.indent, self.pkgprint(pkg.cp, pkg_info))
			if (self.newlp-nc_len(myprint)) > 0:
				myprint = myprint+(" "*(self.newlp-nc_len(myprint)))
			myprint = myprint+"["+darkblue(pkg_info.ver)+"] "
			if (self.oldlp-nc_len(myprint)) > 0:
				myprint = myprint+" "*(self.oldlp-nc_len(myprint))
			myprint = myprint+pkg_info.oldbest
			myprint += darkgreen("to " + pkg.root)
		return myprint


	def _set_root_columns(self, addl, pkg_info, pkg):
		"""sets the indent level and formats the output

		@param addl: already defined string to add to
		@param pkg_info: dictionary
		@param pkg: _emerge.Package instance
		@rtype string
		Modifies self.verboseadd
		"""
		if self.conf.quiet:
			myprint = addl + " " + self.indent + \
				self.pkgprint(pkg_info.cp, pkg_info)
			myprint = myprint+" "+green(pkg_info.ver)+" "
			myprint = myprint+pkg_info.oldbest
			self.verboseadd = None
		else:
			if not pkg_info.merge:
				myprint = "[%s] %s%s" % \
					(self.pkgprint(pkg_info.operation.ljust(13), pkg_info),
					self.indent, self.pkgprint(pkg.cp, pkg_info))
			else:
				myprint = "[%s %s] %s%s" % \
					(self.pkgprint(pkg.type_name, pkg_info), addl,
					self.indent, self.pkgprint(pkg.cp, pkg_info))
			if (self.newlp-nc_len(myprint)) > 0:
				myprint = myprint+(" "*(self.newlp-nc_len(myprint)))
			myprint = myprint+green(" ["+pkg_info.ver+"] ")
			if (self.oldlp-nc_len(myprint)) > 0:
				myprint = myprint+(" "*(self.oldlp-nc_len(myprint)))
			myprint += pkg_info.oldbest
		return myprint


	def _set_no_columns(self, pkg, pkg_info, addl):
		"""prints pkg info without column indentation.

		@param pkg: _emerge.Package instance
		@param pkg_info: dictionary
		@param addl: the current text to add for the next line to output
		@rtype the updated addl
		"""
		if not pkg_info.merge:
			myprint = "[%s] %s%s %s" % \
				(self.pkgprint(pkg_info.operation.ljust(13),
				pkg_info),
				self.indent, self.pkgprint(pkg.cpv, pkg_info),
				pkg_info.oldbest)
		else:
			myprint = "[%s %s] %s%s %s" % \
				(self.pkgprint(pkg.type_name, pkg_info),
				addl, self.indent,
				self.pkgprint(pkg.cpv, pkg_info), pkg_info.oldbest)
		return myprint


	def _insert_slot(self, pkg, pkg_info, myinslotlist):
		"""Adds slot info to the message

		@returns addl: formatted slot info
		@returns myoldbest: installed version list
		Modifies self.counters.downgrades, self.counters.upgrades,
			self.counters.binary
		"""
		addl = "   " + pkg_info.fetch_symbol
		if not cpvequal(pkg.cpv,
			best([pkg.cpv] + [x.cpv for x in myinslotlist])):
			# Downgrade in slot
			addl += turquoise("U")+blue("D")
			if pkg_info.ordered:
				self.counters.downgrades += 1
				if pkg.type_name == "binary":
					self.counters.binary += 1
		else:
			# Update in slot
			addl += turquoise("U") + " "
			if pkg_info.ordered:
				self.counters.upgrades += 1
				if pkg.type_name == "binary":
					self.counters.binary += 1
		return addl


	def _new_slot(self, pkg, pkg_info):
		"""New slot, mark it new.

		@returns addl: formatted slot info
		@returns myoldbest: installed version list
		Modifies self.counters.newslot, self.counters.binary
		"""
		addl = " " + green("NS") + pkg_info.fetch_symbol + "  "
		if pkg_info.ordered:
			self.counters.newslot += 1
			if pkg.type_name == "binary":
				self.counters.binary += 1
		return addl


	def print_messages(self, show_repos):
		"""Performs the actual output printing of the pre-formatted
		messages

		@param show_repos: bool.
		"""
		for msg in self.print_msg:
			if isinstance(msg, basestring):
				writemsg_stdout("%s\n" % (msg,), noiselevel=-1)
				continue
			myprint, self.verboseadd, repoadd = msg
			if self.verboseadd:
				myprint += " " + self.verboseadd
			if show_repos and repoadd:
				myprint += " " + teal("[%s]" % repoadd)
			writemsg_stdout("%s\n" % (myprint,), noiselevel=-1)
		return


	def print_blockers(self):
		"""Performs the actual output printing of the pre-formatted
		blocker messages
		"""
		for pkg in self.blockers:
			writemsg_stdout("%s\n" % (pkg,), noiselevel=-1)
		return


	def print_verbose(self, show_repos):
		"""Prints the verbose output to std_out

		@param show_repos: bool.
		"""
		writemsg_stdout('\n%s\n' % (self.counters,), noiselevel=-1)
		if show_repos:
			# Use _unicode_decode() to force unicode format string so
			# that RepoDisplay.__unicode__() is called in python2.
			writemsg_stdout(_unicode_decode("%s") % (self.conf.repo_display,),
				noiselevel=-1)
		return


	def print_changelog(self):
		"""Prints the changelog text to std_out
		"""
		writemsg_stdout('\n', noiselevel=-1)
		for revision, text in self.changelogs:
			writemsg_stdout(bold('*'+revision) + '\n' + text,
				noiselevel=-1)
		return


	def get_display_list(self, mylist):
		"""Determines the display list to process

		@param mylist
		@rtype list
		Modifies self.counters.blocks, self.counters.blocks_satisfied,

		"""
		unsatisfied_blockers = []
		ordered_nodes = []
		for pkg in mylist:
			if isinstance(pkg, Blocker):
				self.counters.blocks += 1
				if pkg.satisfied:
					ordered_nodes.append(pkg)
					self.counters.blocks_satisfied += 1
				else:
					unsatisfied_blockers.append(pkg)
			else:
				ordered_nodes.append(pkg)
		if self.conf.tree_display:
			display_list = _tree_display(self.conf, ordered_nodes)
		else:
			display_list = [(pkg, 0, True) for pkg in ordered_nodes]
		for pkg in unsatisfied_blockers:
			display_list.append((pkg, 0, True))
		return display_list


	def set_pkg_info(self, pkg, ordered):
		"""Sets various pkg_info dictionary variables

		@param pkg: _emerge.Package instance
		@param ordered: bool
		@rtype pkg_info dictionary
		Modifies self.counters.restrict_fetch,
			self.counters.restrict_fetch_satisfied
		"""
		pkg_info = PkgInfo()
		pkg_info.ordered = ordered
		pkg_info.fetch_symbol = " "
		pkg_info.operation = pkg.operation
		pkg_info.merge = ordered and pkg_info.operation == "merge"
		if not pkg_info.merge and pkg_info.operation == "merge":
			pkg_info.operation = "nomerge"
		pkg_info.built = pkg.type_name != "ebuild"
		pkg_info.ebuild_path = None
		pkg_info.repo_name = pkg.repo
		if pkg.type_name == "ebuild":
			pkg_info.ebuild_path = self.portdb.findname(
				pkg.cpv, myrepo=pkg_info.repo_name)
			if pkg_info.ebuild_path is None:
				raise AssertionError(
					"ebuild not found for '%s'" % pkg.cpv)
			pkg_info.repo_path_real = os.path.dirname(os.path.dirname(
				os.path.dirname(pkg_info.ebuild_path)))
		else:
			pkg_info.repo_path_real = \
				self.portdb.getRepositoryPath(pkg.metadata["repository"])
		pkg_info.use = list(self.conf.pkg_use_enabled(pkg))
		if not pkg.built and pkg.operation == 'merge' and \
			'fetch' in pkg.metadata.restrict:
			pkg_info.fetch_symbol = red("F")
			if pkg_info.ordered:
				self.counters.restrict_fetch += 1
			if self.portdb.fetch_check(pkg.cpv, pkg_info.use,
					myrepo=pkg.repo):
				pkg_info.fetch_symbol = green("f")
				if pkg_info.ordered:
					self.counters.restrict_fetch_satisfied += 1
		return pkg_info


	def do_changelog(self, pkg, pkg_info):
		"""Processes and adds the changelog text to the master text for output

		@param pkg: _emerge.Package instance
		@param pkg_info: dictionay
		Modifies self.changelogs
		"""
		inst_matches = self.vardb.match(pkg.slot_atom)
		if inst_matches:
			ebuild_path_cl = pkg_info.ebuild_path
			if ebuild_path_cl is None:
				# binary package
				ebuild_path_cl = self.portdb.findname(pkg.cpv, myrepo=pkg.repo)
			if ebuild_path_cl is not None:
				self.changelogs.extend(_calc_changelog(
					ebuild_path_cl, inst_matches[0], pkg.cpv))
		return


	def check_system_world(self, pkg):
		"""Checks for any occurances of the package in the system or world sets

		@param pkg: _emerge.Package instance
		@rtype system and world booleans
		"""
		root_config = self.conf.roots[pkg.root]
		system_set = root_config.sets["system"]
		world_set  = root_config.sets["selected"]
		system = False
		world = False
		try:
			system = system_set.findAtomForPackage(
				pkg, modified_use=self.conf.pkg_use_enabled(pkg))
			world = world_set.findAtomForPackage(
				pkg, modified_use=self.conf.pkg_use_enabled(pkg))
			if not (self.conf.oneshot or world) and \
				pkg.root == self.conf.target_root and \
				self.conf.favorites.findAtomForPackage(
					pkg, modified_use=self.conf.pkg_use_enabled(pkg)
					):
				# Maybe it will be added to world now.
				if create_world_atom(pkg, self.conf.favorites, root_config):
					world = True
		except InvalidDependString:
			# This is reported elsewhere if relevant.
			pass
		return system, world


	@staticmethod
	def get_ver_str(pkg):
		"""Obtains the version string
		@param pkg: _emerge.Package instance
		@rtype string
		"""
		ver_str = list(catpkgsplit(pkg.cpv)[2:])
		if ver_str[1] == "r0":
			ver_str[1] = ""
		else:
			ver_str[1] = "-" + ver_str[1]
		return ver_str[0]+ver_str[1]


	def _get_installed_best(self, pkg, pkg_info):
		""" we need to use "--emptrytree" testing here rather than
		"empty" param testing because "empty"
		param is used for -u, where you still *do* want to see when
		something is being upgraded.

		@param pkg: _emerge.Package instance
		@param pkg_info: dictionay
		@rtype addl, myoldbest: list, myinslotlist: list
		Modifies self.counters.reinst, self.counters.binary, self.counters.new

		"""
		myoldbest = []
		myinslotlist = None
		installed_versions = self.vardb.match_pkgs(pkg.cp)
		if self.vardb.cpv_exists(pkg.cpv):
			addl = "  "+yellow("R")+pkg_info.fetch_symbol+"  "
			if pkg_info.ordered:
				if pkg_info.merge:
					self.counters.reinst += 1
					if pkg.type_name == "binary":
						self.counters.binary += 1
				elif pkg_info.operation == "uninstall":
					self.counters.uninst += 1
		# filter out old-style virtual matches
		elif installed_versions and \
			installed_versions[0].cp == pkg.cp:
			myinslotlist = self.vardb.match_pkgs(pkg.slot_atom)
			# If this is the first install of a new-style virtual, we
			# need to filter out old-style virtual matches.
			if myinslotlist and \
				myinslotlist[0].cp != pkg.cp:
				myinslotlist = None
			if myinslotlist:
				myoldbest = myinslotlist[:]
				addl = self._insert_slot(pkg, pkg_info, myinslotlist)
			else:
				myoldbest = installed_versions
				addl = self._new_slot(pkg, pkg_info)
			if self.conf.changelog:
				self.do_changelog(pkg, pkg_info)
		else:
			addl = " " + green("N") + " " + pkg_info.fetch_symbol + "  "
			if pkg_info.ordered:
				self.counters.new += 1
				if pkg.type_name == "binary":
					self.counters.binary += 1
		return addl, myoldbest, myinslotlist


	def __call__(self, depgraph, mylist, favorites=None, verbosity=None):
		"""The main operation to format and display the resolver output.

		@param depgraph: dependency grah
		@param mylist: list of packages being processed
		@param favorites: list, defaults to []
		@param verbosity: verbose level, defaults to None
		Modifies self.conf, self.myfetchlist, self.portdb, self.vardb,
			self.pkgsettings, self.verboseadd, self.oldlp, self.newlp,
			self.print_msg,
		"""
		if favorites is None:
			favorites = []
		self.conf = _DisplayConfig(depgraph, mylist, favorites, verbosity)
		mylist = self.get_display_list(self.conf.mylist)
		# files to fetch list - avoids counting a same file twice
		# in size display (verbose mode)
		self.myfetchlist = []
		# Use this set to detect when all the "repoadd" strings are "[0]"
		# and disable the entire repo display in this case.
		repoadd_set = set()

		for mylist_index in range(len(mylist)):
			pkg, depth, ordered = mylist[mylist_index]
			self.portdb = self.conf.trees[pkg.root]["porttree"].dbapi
			self.vardb = self.conf.trees[pkg.root]["vartree"].dbapi
			self.pkgsettings = self.conf.pkgsettings[pkg.root]
			self.indent = " " * depth

			if isinstance(pkg, Blocker):
				if self._blockers(pkg, fetch_symbol=" "):
					continue
			else:
				pkg_info = self.set_pkg_info(pkg, ordered)
				addl, pkg_info.oldbest, myinslotlist = \
					self._get_installed_best(pkg, pkg_info)
				self.verboseadd = ""
				self.repoadd = None
				self._display_use(pkg, pkg_info.oldbest, myinslotlist)
				self.recheck_hidden(pkg)
				if self.conf.verbosity == 3:
					self.verbose_size(pkg, repoadd_set, pkg_info)

				pkg_info.cp = pkg.cp
				pkg_info.ver = self.get_ver_str(pkg)

				self.oldlp = self.conf.columnwidth - 30
				self.newlp = self.oldlp - 30
				pkg_info.oldbest = self.convert_myoldbest(pkg_info.oldbest)
				pkg_info.system, pkg_info.world = \
					self.check_system_world(pkg)
				addl = self.set_interactive(pkg, pkg_info.ordered, addl)

				if self.conf.verbosity == 3:
					addl += self.gen_mask_str(pkg)

				if pkg.root != "/":
					if pkg_info.oldbest:
						pkg_info.oldbest += " "
					if self.conf.columns:
						myprint = self._set_non_root_columns(
							addl, pkg_info, pkg)
					else:
						if not pkg_info.merge:
							addl = ""
							if self.conf.verbosity == 3:
								 # add column for mask status
								addl += " "
							myprint = "[%s%s] " % (
								self.pkgprint(pkg_info.operation.ljust(13),
								pkg_info), addl,
								)
						else:
							myprint = "[%s %s] " % (
								self.pkgprint(pkg.type_name, pkg_info), addl)
						myprint += self.indent + \
							self.pkgprint(pkg.cpv, pkg_info) + " " + \
							pkg_info.oldbest + darkgreen("to " + pkg.root)
				else:
					if self.conf.columns:
						myprint = self._set_root_columns(
							addl, pkg_info, pkg)
					else:
						myprint = self._set_no_columns(
							pkg, pkg_info, addl)

				if self.conf.columns and pkg.operation == "uninstall":
					continue
				self.print_msg.append((myprint, self.verboseadd, self.repoadd))

				if not self.conf.tree_display \
					and not self.conf.no_restart \
					and pkg.root == self.conf.running_root.root \
					and match_from_list(PORTAGE_PACKAGE_ATOM, [pkg]) \
					and not self.conf.quiet:

					if not self.vardb.cpv_exists(pkg.cpv) or \
						'9999' in pkg.cpv or \
						'git' in pkg.inherited:
						if mylist_index < len(mylist) - 1:
							self.print_msg.append(
								colorize(
									"WARN", "*** Portage will stop merging "
									"at this point and reload itself,"
									)
								)
							self.print_msg.append(
								colorize("WARN", "    then resume the merge.")
								)

		show_repos = repoadd_set and repoadd_set != set(["0"])

		# now finally print out the messages
		self.print_messages(show_repos)
		self.print_blockers()
		if self.conf.verbosity == 3:
			self.print_verbose(show_repos)
		if self.conf.changelog:
			self.print_changelog()

		return os.EX_OK
