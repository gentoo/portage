# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""Resolver output display operation.
"""

__all__ = (
	"Display", "format_unmatched_atom",
	)

from portage import os
from portage.dbapi.dep_expand import dep_expand
from portage.dep import Atom, cpvequal, _repo_separator, _slot_separator
from portage.eapi import _get_eapi_attrs
from portage.exception import InvalidDependString, SignatureException
from portage.localization import localized_size
from portage.package.ebuild.config import _get_feature_flags
from portage.package.ebuild._spawn_nofetch import spawn_nofetch
from portage.output import ( blue, colorize, create_color_func,
	darkblue, darkgreen, green, nc_len, teal)
bad = create_color_func("BAD")
from portage._sets.base import InternalPackageSet
from portage.util import writemsg_stdout
from portage.versions import best, cpv_getversion

from _emerge.Blocker import Blocker
from _emerge.create_world_atom import create_world_atom
from _emerge.resolver.output_helpers import ( _DisplayConfig, _tree_display,
	_PackageCounters, _create_use_string, PkgInfo)
from _emerge.show_invalid_depstring_notice import show_invalid_depstring_notice

class Display:
	"""Formats and outputs the depgrah supplied it for merge/re-merge, etc.

	__call__()
	@param depgraph: list
	@param favorites: defaults to []
	@param verbosity: integer, defaults to None
	"""

	def __init__(self):
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
		self.use_expand = None
		self.use_expand_hidden = None
		self.pkgsettings = None
		self.forced_flags = None
		self.newlp = None
		self.conf = None
		self.blocker_style = None


	def _blockers(self, blocker):
		"""Adds colorized strings to
		self.print_msg and self.blockers

		@param blocker: _emerge.Blocker.Blocker instance
		@rtype: bool
		Modifies class globals: self.blocker_style, self.resolved,
			self.print_msg
		"""
		if blocker.satisfied:
			self.blocker_style = "PKG_BLOCKER_SATISFIED"
			addl = "%s     " % (colorize(self.blocker_style, "b"),)
		else:
			self.blocker_style = "PKG_BLOCKER"
			addl = "%s     " % (colorize(self.blocker_style, "B"),)
		addl += self.empty_space_in_brackets()
		self.resolved = dep_expand(
			str(blocker.atom).lstrip("!"), mydb=self.vardb,
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
		block_parents = self.conf.blocker_parents.parent_nodes(blocker)
		block_parents = set(str(pnode.cpv) for pnode in block_parents)
		block_parents = ", ".join(block_parents)
		if blocker.atom.blocker.overlap.forbid:
			blocking_desc = "hard blocking"
		else:
			blocking_desc = "blocking"
		if self.resolved != blocker.atom:
			addl += colorize(self.blocker_style,
				" (\"%s\" is %s %s)" %
				(str(blocker.atom).lstrip("!"),
				blocking_desc, block_parents))
		else:
			addl += colorize(self.blocker_style,
				" (is %s %s)" % (blocking_desc, block_parents))
		if blocker.satisfied:
			if not self.conf.columns:
				self.print_msg.append(addl)
		else:
			self.blockers.append(addl)

	def include_mask_str(self):
		return self.conf.verbosity > 1

	def gen_mask_str(self, pkg):
		"""
		@param pkg: _emerge.Package.Package instance
		"""
		hardmasked = pkg.isHardMasked()
		mask_str = " "

		if hardmasked:
			mask_str = colorize("BAD", "#")
		else:
			keyword_mask = pkg.get_keyword_mask()

			if keyword_mask is None:
				pass
			elif keyword_mask == "missing":
				mask_str = colorize("BAD", "*")
			else:
				mask_str = colorize("WARN", "~")

		return mask_str

	def empty_space_in_brackets(self):
		space = ""
		if self.include_mask_str():
			# add column for mask status
			space += " "
		return space

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


	def _display_use(self, pkg, pkg_info):
		""" USE flag display

		@param pkg: _emerge.Package.Package instance
		@param pkg_info: PkgInfo instance
		Modifies self.use_expand_hidden, self.use_expand, self.verboseadd,
			self.forced_flags
		"""

		self.forced_flags = set()
		self.forced_flags.update(pkg.use.force)
		self.forced_flags.update(pkg.use.mask)

		cur_use = [flag for flag in self.conf.pkg_use_enabled(pkg) \
			if flag in pkg.iuse.all]
		cur_iuse = sorted(pkg.iuse.all)

		if pkg_info.previous_pkg is not None:
			previous_pkg = pkg_info.previous_pkg
			old_iuse = sorted(previous_pkg.iuse.all)
			old_use = previous_pkg.use.enabled
			is_new = False
		else:
			old_iuse = []
			old_use = []
			is_new = True

		old_use = [flag for flag in old_use if flag in old_iuse]

		self.use_expand = pkg.use.expand
		self.use_expand_hidden = pkg.use.expand_hidden

		# Prevent USE_EXPAND_HIDDEN flags from being hidden if they
		# are the only thing that triggered reinstallation.
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
			self.map_to_use_expand(cur_iuse, forced_flags=True)
		cur_use_map = self.map_to_use_expand(cur_use)
		old_iuse_map = self.map_to_use_expand(old_iuse)
		old_use_map = self.map_to_use_expand(old_use)

		use_expand = sorted(self.use_expand)
		use_expand.insert(0, "USE")
		feature_flags = _get_feature_flags(_get_eapi_attrs(pkg.eapi))

		for key in use_expand:
			if key in self.use_expand_hidden:
				continue
			self.verboseadd += _create_use_string(self.conf, key.upper(),
				cur_iuse_map[key], iuse_forced[key],
				cur_use_map[key], old_iuse_map[key],
				old_use_map[key], is_new, feature_flags,
				reinst_flags_map.get(key))


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
				if pkg_info.world:
					return colorize("PKG_BINARY_MERGE_WORLD", pkg_str)
				return colorize("PKG_BINARY_MERGE", pkg_str)

			if pkg_info.system:
				return colorize("PKG_MERGE_SYSTEM", pkg_str)
			if pkg_info.world:
				return colorize("PKG_MERGE_WORLD", pkg_str)
			return colorize("PKG_MERGE", pkg_str)

		if pkg_info.operation == "uninstall":
			return colorize("PKG_UNINSTALL", pkg_str)

		if pkg_info.system:
			return colorize("PKG_NOMERGE_SYSTEM", pkg_str)
		if pkg_info.world:
			return colorize("PKG_NOMERGE_WORLD", pkg_str)
		return colorize("PKG_NOMERGE", pkg_str)


	def verbose_size(self, pkg, repoadd_set, pkg_info):
		"""Determines the size of the downloads required

		@param pkg: _emerge.Package.Package instance
		@param repoadd_set: set of repos to add
		@param pkg_info: dictionary
		Modifies class globals: self.myfetchlist, self.counters.totalsize,
			self.verboseadd, repoadd_set.
		"""
		mysize = 0
		if pkg.type_name in ("binary", "ebuild") and pkg_info.merge:
			db = pkg.root_config.trees[
				pkg.root_config.pkg_tree_map[pkg.type_name]].dbapi
			kwargs = {}
			if pkg.type_name == "ebuild":
				kwargs["useflags"] = pkg_info.use
				kwargs["myrepo"] = pkg.repo
			myfilesdict = None
			try:
				myfilesdict = db.getfetchsizes(pkg.cpv, **kwargs)
			except InvalidDependString as e:
				# FIXME: validate SRC_URI earlier
				depstr, = db.aux_get(pkg.cpv,
					["SRC_URI"], myrepo=pkg.repo)
				show_invalid_depstring_notice(
					pkg, str(e))
				raise
			except SignatureException:
				# missing/invalid binary package SIZE signature
				pass
			if myfilesdict is None:
				myfilesdict = "[empty/missing/bad digest]"
			else:
				for myfetchfile in myfilesdict:
					if myfetchfile not in self.myfetchlist:
						mysize += myfilesdict[myfetchfile]
						self.myfetchlist.add(myfetchfile)
				if pkg_info.ordered:
					self.counters.totalsize += mysize
			self.verboseadd += localized_size(mysize)

		if self.quiet_repo_display:
			# overlay verbose
			# assign index for a previous version in the same slot
			if pkg_info.previous_pkg is not None:
				repo_name_prev = pkg_info.previous_pkg.repo
			else:
				repo_name_prev = None

			# now use the data to generate output
			if pkg.installed or pkg_info.previous_pkg is None:
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


	def convert_myoldbest(self, pkg, pkg_info):
		"""converts and colorizes a version list to a string

		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionary
		@rtype string.
		"""
		myoldbest = pkg_info.oldbest_list
		# Convert myoldbest from a list to a string.
		myoldbest_str = ""
		if myoldbest:
			versions = []
			for pos, old_pkg in enumerate(myoldbest):
				key = old_pkg.version
				if key[-3:] == "-r0":
					key = key[:-3]
				if self.conf.verbosity == 3:
					if pkg_info.attr_display.new_slot:
						key += _slot_separator + old_pkg.slot
						if old_pkg.slot != old_pkg.sub_slot:
							key += "/" + old_pkg.sub_slot
					elif any(x.slot + "/" + x.sub_slot != "0/0" for x in myoldbest + [pkg]):
						key += _slot_separator + old_pkg.slot
						if old_pkg.slot != old_pkg.sub_slot or \
							old_pkg.slot == pkg.slot and old_pkg.sub_slot != pkg.sub_slot:
							key += "/" + old_pkg.sub_slot
					if not self.quiet_repo_display:
						key += _repo_separator + old_pkg.repo
				versions.append(key)
			myoldbest_str = blue("["+", ".join(versions)+"]")
		return myoldbest_str

	def _append_slot(self, pkg_str, pkg, pkg_info):
		"""Potentially appends slot and subslot to package string.

		@param pkg_str: string
		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionary
		@rtype string
		"""
		if pkg_info.attr_display.new_slot:
			pkg_str += _slot_separator + pkg_info.slot
			if pkg_info.slot != pkg_info.sub_slot:
				pkg_str += "/" + pkg_info.sub_slot
		elif any(x.slot + "/" + x.sub_slot != "0/0" for x in pkg_info.oldbest_list + [pkg]):
			pkg_str += _slot_separator + pkg_info.slot
			if pkg_info.slot != pkg_info.sub_slot or \
				any(x.slot == pkg_info.slot and x.sub_slot != pkg_info.sub_slot for x in pkg_info.oldbest_list):
				pkg_str += "/" + pkg_info.sub_slot
		return pkg_str

	def _append_repository(self, pkg_str, pkg, pkg_info):
		"""Potentially appends repository to package string.

		@param pkg_str: string
		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionary
		@rtype string
		"""
		if not self.quiet_repo_display:
			pkg_str += _repo_separator + pkg.repo
		return pkg_str

	def _append_build_id(self, pkg_str, pkg, pkg_info):
		"""Potentially appends repository to package string.

		@param pkg_str: string
		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionary
		@rtype string
		"""
		if pkg.type_name == "binary" and pkg.cpv.build_id is not None:
			pkg_str += "-%s" % pkg.cpv.build_id
		return pkg_str

	def _set_non_root_columns(self, pkg, pkg_info):
		"""sets the indent level and formats the output

		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionary
		@rtype string
		"""
		ver_str = self._append_build_id(pkg_info.ver, pkg, pkg_info)
		if self.conf.verbosity == 3:
			ver_str = self._append_slot(ver_str, pkg, pkg_info)
			ver_str = self._append_repository(ver_str, pkg, pkg_info)
		if self.conf.quiet:
			myprint = str(pkg_info.attr_display) + " " + self.indent + \
				self.pkgprint(pkg_info.cp, pkg_info)
			myprint = myprint+darkblue(" "+ver_str)+" "
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
					(self.pkgprint(pkg.type_name, pkg_info),
					pkg_info.attr_display,
					self.indent, self.pkgprint(pkg.cp, pkg_info))
			if (self.newlp-nc_len(myprint)) > 0:
				myprint = myprint+(" "*(self.newlp-nc_len(myprint)))
			myprint = myprint+" "+darkblue("["+ver_str+"]")+" "
			if (self.oldlp-nc_len(myprint)) > 0:
				myprint = myprint+" "*(self.oldlp-nc_len(myprint))
			myprint = myprint+pkg_info.oldbest
			myprint += darkgreen("to " + pkg.root)
		return myprint


	def _set_root_columns(self, pkg, pkg_info):
		"""sets the indent level and formats the output

		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionary
		@rtype string
		Modifies self.verboseadd
		"""
		ver_str = self._append_build_id(pkg_info.ver, pkg, pkg_info)
		if self.conf.verbosity == 3:
			ver_str = self._append_slot(ver_str, pkg, pkg_info)
			ver_str = self._append_repository(ver_str, pkg, pkg_info)
		if self.conf.quiet:
			myprint = str(pkg_info.attr_display) + " " + self.indent + \
				self.pkgprint(pkg_info.cp, pkg_info)
			myprint = myprint+" "+green(ver_str)+" "
			myprint = myprint+pkg_info.oldbest
			self.verboseadd = None
		else:
			if not pkg_info.merge:
				addl = self.empty_space_in_brackets()
				myprint = "[%s%s] %s%s" % \
					(self.pkgprint(pkg_info.operation.ljust(13), pkg_info),
					addl, self.indent, self.pkgprint(pkg.cp, pkg_info))
			else:
				myprint = "[%s %s] %s%s" % \
					(self.pkgprint(pkg.type_name, pkg_info),
					pkg_info.attr_display,
					self.indent, self.pkgprint(pkg.cp, pkg_info))
			if (self.newlp-nc_len(myprint)) > 0:
				myprint = myprint+(" "*(self.newlp-nc_len(myprint)))
			myprint = myprint+" "+green("["+ver_str+"]")+" "
			if (self.oldlp-nc_len(myprint)) > 0:
				myprint = myprint+(" "*(self.oldlp-nc_len(myprint)))
			myprint += pkg_info.oldbest
		return myprint


	def _set_no_columns(self, pkg, pkg_info):
		"""prints pkg info without column indentation.

		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionary
		@rtype the updated addl
		"""
		pkg_str = self._append_build_id(pkg.cpv, pkg, pkg_info)
		if self.conf.verbosity == 3:
			pkg_str = self._append_slot(pkg_str, pkg, pkg_info)
			pkg_str = self._append_repository(pkg_str, pkg, pkg_info)
		if not pkg_info.merge:
			addl = self.empty_space_in_brackets()
			myprint = "[%s%s] %s%s %s" % \
				(self.pkgprint(pkg_info.operation.ljust(13),
				pkg_info), addl,
				self.indent, self.pkgprint(pkg_str, pkg_info),
				pkg_info.oldbest)
		else:
			myprint = "[%s %s] %s%s %s" % \
				(self.pkgprint(pkg.type_name, pkg_info),
				pkg_info.attr_display, self.indent,
				self.pkgprint(pkg_str, pkg_info), pkg_info.oldbest)
		return myprint

	def print_messages(self, show_repos):
		"""Performs the actual output printing of the pre-formatted
		messages

		@param show_repos: bool.
		"""
		for msg in self.print_msg:
			if isinstance(msg, str):
				writemsg_stdout("%s\n" % (msg,), noiselevel=-1)
				continue
			myprint, self.verboseadd, repoadd = msg
			if self.verboseadd:
				myprint += " " + self.verboseadd
			if show_repos and repoadd:
				myprint += " " + teal("[%s]" % repoadd)
			writemsg_stdout("%s\n" % (myprint,), noiselevel=-1)


	def print_blockers(self):
		"""Performs the actual output printing of the pre-formatted
		blocker messages
		"""
		for pkg in self.blockers:
			writemsg_stdout("%s\n" % (pkg,), noiselevel=-1)


	def print_verbose(self, show_repos):
		"""Prints the verbose output to std_out

		@param show_repos: bool.
		"""
		writemsg_stdout('\n%s\n' % (self.counters,), noiselevel=-1)
		if show_repos:
			writemsg_stdout("%s" % (self.conf.repo_display,),
				noiselevel=-1)


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

		@param pkg: _emerge.Package.Package instance
		@param ordered: bool
		@rtype pkg_info dictionary
		Modifies self.counters.restrict_fetch,
			self.counters.restrict_fetch_satisfied
		"""
		pkg_info = PkgInfo()
		pkg_info.cp = pkg.cp
		pkg_info.ver = self.get_ver_str(pkg)
		pkg_info.slot = pkg.slot
		pkg_info.sub_slot = pkg.sub_slot
		pkg_info.repo_name = pkg.repo
		pkg_info.ordered = ordered
		pkg_info.operation = pkg.operation
		pkg_info.merge = ordered and pkg_info.operation == "merge"
		if not pkg_info.merge and pkg_info.operation == "merge":
			pkg_info.operation = "nomerge"
		pkg_info.built = pkg.type_name != "ebuild"
		pkg_info.ebuild_path = None
		if ordered:
			if pkg_info.merge:
				if pkg.type_name == "binary":
					self.counters.binary += 1
			elif pkg_info.operation == "uninstall":
				self.counters.uninst += 1
		if pkg.type_name == "ebuild":
			pkg_info.ebuild_path = self.portdb.findname(
				pkg.cpv, myrepo=pkg_info.repo_name)
			if pkg_info.ebuild_path is None:
				raise AssertionError(
					"ebuild not found for '%s'" % pkg.cpv)
			pkg_info.repo_path_real = os.path.dirname(os.path.dirname(
				os.path.dirname(pkg_info.ebuild_path)))
		else:
			pkg_info.repo_path_real = self.portdb.getRepositoryPath(pkg.repo)
		pkg_info.use = list(self.conf.pkg_use_enabled(pkg))
		if not pkg.built and pkg.operation == 'merge' and \
			'fetch' in pkg.restrict:
			if pkg_info.ordered:
				self.counters.restrict_fetch += 1
			pkg_info.attr_display.fetch_restrict = True
			if not self.portdb.getfetchsizes(pkg.cpv,
				useflags=pkg_info.use, myrepo=pkg.repo):
				pkg_info.attr_display.fetch_restrict_satisfied = True
				if pkg_info.ordered:
					self.counters.restrict_fetch_satisfied += 1
			else:
				if pkg_info.ebuild_path is not None:
					self.restrict_fetch_list[pkg] = pkg_info

		if self.vardb.cpv_exists(pkg.cpv):
			# Do a cpv match first, in case the SLOT has changed.
			pkg_info.previous_pkg = self.vardb.match_pkgs(
				Atom('=' + pkg.cpv))[0]
		else:
			cp_slot_matches = self.vardb.match_pkgs(pkg.slot_atom)
			if cp_slot_matches:
				pkg_info.previous_pkg = cp_slot_matches[0]
			else:
				cp_matches = self.vardb.match_pkgs(Atom(pkg.cp))
				if cp_matches:
					# Use highest installed other-slot package instance.
					pkg_info.previous_pkg = cp_matches[-1]

		return pkg_info


	def check_system_world(self, pkg):
		"""Checks for any occurances of the package in the system or world sets

		@param pkg: _emerge.Package.Package instance
		@rtype system and world booleans
		"""
		root_config = self.conf.roots[pkg.root]
		system_set = root_config.sets["system"]
		world_set  = self.conf.selected_sets[pkg.root]
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
		@param pkg: _emerge.Package.Package instance
		@rtype string
		"""
		ver_str = pkg.cpv.version
		if ver_str.endswith("-r0"):
			ver_str = ver_str[:-3]
		return ver_str


	def _get_installed_best(self, pkg, pkg_info):
		""" we need to use "--emptrytree" testing here rather than
		"empty" param testing because "empty"
		param is used for -u, where you still *do* want to see when
		something is being upgraded.

		@param pkg: _emerge.Package.Package instance
		@param pkg_info: dictionay
		@rtype addl, myoldbest: list, myinslotlist: list
		Modifies self.counters.reinst, self.counters.new

		"""
		myoldbest = []
		myinslotlist = None
		installed_versions = self.vardb.match_pkgs(Atom(pkg.cp))
		if self.vardb.cpv_exists(pkg.cpv):
			pkg_info.attr_display.replace = True
			installed_version = pkg_info.previous_pkg
			if installed_version.slot != pkg.slot or installed_version.sub_slot != pkg.sub_slot or \
				not self.quiet_repo_display and installed_version.repo != pkg.repo:
				myoldbest = [installed_version]
			if pkg_info.ordered:
				if pkg_info.merge:
					self.counters.reinst += 1
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
				if not cpvequal(pkg.cpv,
					best([pkg.cpv] + [x.cpv for x in myinslotlist])):
					# Downgrade in slot
					pkg_info.attr_display.new_version = True
					pkg_info.attr_display.downgrade = True
					if pkg_info.ordered:
						self.counters.downgrades += 1
				else:
					# Update in slot
					pkg_info.attr_display.new_version = True
					if pkg_info.ordered:
						self.counters.upgrades += 1
			else:
				myoldbest = installed_versions
				pkg_info.attr_display.new = True
				pkg_info.attr_display.new_slot = True
				if pkg_info.ordered:
					self.counters.newslot += 1
		else:
			pkg_info.attr_display.new = True
			if pkg_info.ordered:
				self.counters.new += 1
		return myoldbest, myinslotlist


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
		self.myfetchlist = set()

		self.quiet_repo_display = "--quiet-repo-display" in depgraph._frozen_config.myopts
		if self.quiet_repo_display:
			# Use this set to detect when all the "repoadd" strings are "[0]"
			# and disable the entire repo display in this case.
			repoadd_set = set()

		self.restrict_fetch_list = {}

		for mylist_index in range(len(mylist)):
			pkg, depth, ordered = mylist[mylist_index]
			self.portdb = self.conf.trees[pkg.root]["porttree"].dbapi
			self.vardb = self.conf.trees[pkg.root]["vartree"].dbapi
			self.pkgsettings = self.conf.pkgsettings[pkg.root]
			self.indent = " " * depth

			if isinstance(pkg, Blocker):
				self._blockers(pkg)
			else:
				pkg_info = self.set_pkg_info(pkg, ordered)
				pkg_info.oldbest_list, myinslotlist = \
					self._get_installed_best(pkg, pkg_info)
				if ordered and pkg_info.merge and \
					not pkg_info.attr_display.new:
					for arg, atom in depgraph._iter_atoms_for_pkg(pkg):
						if arg.force_reinstall:
							pkg_info.attr_display.force_reinstall = True
							break

				self.verboseadd = ""
				if self.quiet_repo_display:
					self.repoadd = None
				self._display_use(pkg, pkg_info)
				if self.conf.verbosity == 3:
					if self.quiet_repo_display:
						self.verbose_size(pkg, repoadd_set, pkg_info)
					else:
						self.verbose_size(pkg, None, pkg_info)

				self.oldlp = self.conf.columnwidth - 30
				self.newlp = self.oldlp - 30
				pkg_info.oldbest = self.convert_myoldbest(pkg, pkg_info)
				pkg_info.system, pkg_info.world = \
					self.check_system_world(pkg)
				if 'interactive' in pkg.properties and \
					pkg.operation == 'merge':
					pkg_info.attr_display.interactive = True
					if ordered:
						self.counters.interactive += 1

				if self.include_mask_str():
					pkg_info.attr_display.mask = self.gen_mask_str(pkg)

				if pkg.root_config.settings["ROOT"] != "/":
					if pkg_info.oldbest:
						pkg_info.oldbest += " "
					if self.conf.columns:
						myprint = self._set_non_root_columns(pkg, pkg_info)
					else:
						pkg_str = self._append_build_id(
							pkg.cpv, pkg, pkg_info)
						if self.conf.verbosity == 3:
							pkg_str = self._append_slot(pkg_str, pkg, pkg_info)
							pkg_str = self._append_repository(pkg_str, pkg, pkg_info)
						if not pkg_info.merge:
							addl = self.empty_space_in_brackets()
							myprint = "[%s%s] " % (
								self.pkgprint(pkg_info.operation.ljust(13),
								pkg_info), addl,
								)
						else:
							myprint = "[%s %s] " % (
								self.pkgprint(pkg.type_name, pkg_info),
								pkg_info.attr_display)
						myprint += self.indent + \
							self.pkgprint(pkg_str, pkg_info) + " " + \
							pkg_info.oldbest + darkgreen("to " + pkg.root)
				else:
					if self.conf.columns:
						myprint = self._set_root_columns(pkg, pkg_info)
					else:
						myprint = self._set_no_columns(pkg, pkg_info)

				if self.conf.columns and pkg.operation == "uninstall":
					continue
				if self.quiet_repo_display:
					self.print_msg.append((myprint, self.verboseadd, self.repoadd))
				else:
					self.print_msg.append((myprint, self.verboseadd, None))

		show_repos = self.quiet_repo_display and repoadd_set and repoadd_set != set(["0"])

		# now finally print out the messages
		self.print_messages(show_repos)
		self.print_blockers()
		if self.conf.verbosity == 3:
			self.print_verbose(show_repos)
		for pkg, pkg_info in self.restrict_fetch_list.items():
			writemsg_stdout("\nFetch instructions for %s:\n" % (pkg.cpv,),
							noiselevel=-1)
			spawn_nofetch(self.conf.trees[pkg.root]["porttree"].dbapi,
				pkg_info.ebuild_path)

		return os.EX_OK


def format_unmatched_atom(pkg, atom, pkg_use_enabled):
	"""
	Returns two strings. The first string contains the
	'atom' with parts of the atom colored, which 'pkg'
	doesn't match. The second string has the same number
	of characters as the first one, but consists of only
	white space or ^. The ^ characters have the same position
	as the colored parts of the first string.
	"""
	# Things to check:
	#	1. Version
	#	2. cp
	#   3. slot/sub_slot
	#	4. repository
	#	5. USE

	if atom.soname:
		return "%s" % (atom,), ""

	highlight = set()

	def perform_coloring():
		atom_str = ""
		marker_str = ""
		for ii, x in enumerate(atom):
			if ii in highlight:
				atom_str += colorize("BAD", x)
				marker_str += "^"
			else:
				atom_str += x
				marker_str += " "
		return atom_str, marker_str

	if atom.cp != pkg.cp:
		# Highlight the cp part only.
		ii = atom.find(atom.cp)
		highlight.update(range(ii, ii + len(atom.cp)))
		return perform_coloring()

	version_atom = atom.without_repo.without_slot.without_use
	version_atom_set = InternalPackageSet(initial_atoms=(version_atom,))
	highlight_version = not bool(version_atom_set.findAtomForPackage(pkg,
		modified_use=pkg_use_enabled(pkg)))

	highlight_slot = False
	if (atom.slot and atom.slot != pkg.slot) or \
		(atom.sub_slot and atom.sub_slot != pkg.sub_slot):
		highlight_slot = True

	if highlight_version:
		op = atom.operator
		ver = None
		if atom.cp != atom.cpv:
			ver = cpv_getversion(atom.cpv)

		if op == "=*":
			op = "="
			ver += "*"

		if op is not None:
			highlight.update(range(len(op)))

		if ver is not None:
			start = atom.rfind(ver)
			end = start + len(ver)
			highlight.update(range(start, end))

	if highlight_slot:
		slot_str = ":" + atom.slot
		if atom.sub_slot:
			slot_str += "/" + atom.sub_slot
		if atom.slot_operator:
			slot_str += atom.slot_operator
		start = atom.find(slot_str)
		end = start + len(slot_str)
		highlight.update(range(start, end))

	highlight_use = set()
	if atom.use:
		use_atom = "%s[%s]" % (atom.cp, str(atom.use))
		use_atom_set = InternalPackageSet(initial_atoms=(use_atom,))
		if not use_atom_set.findAtomForPackage(pkg, \
			modified_use=pkg_use_enabled(pkg)):
			missing_iuse = pkg.iuse.get_missing_iuse(
				atom.unevaluated_atom.use.required)
			if missing_iuse:
				highlight_use = set(missing_iuse)
			else:
				#Use conditionals not met.
				violated_atom = atom.violated_conditionals(
					pkg_use_enabled(pkg), pkg.iuse.is_valid_flag)
				if violated_atom.use is not None:
					highlight_use = set(violated_atom.use.enabled.union(
						violated_atom.use.disabled))

	if highlight_use:
		ii = atom.find("[") + 1
		for token in atom.use.tokens:
			if token.lstrip("-!").rstrip("=?") in highlight_use:
				highlight.update(range(ii, ii + len(token)))
			ii += len(token) + 1

	return perform_coloring()
