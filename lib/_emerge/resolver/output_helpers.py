# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""Contains private support functions for the Display class
in output.py
"""

__all__ = (
	)

import io
import re

from portage import os
from portage import _encodings, _unicode_encode
from portage._sets.base import InternalPackageSet
from portage.exception import PackageSetNotFound
from portage.localization import localized_size
from portage.output import (blue, bold, colorize, create_color_func,
	green, red, teal, turquoise, yellow)
bad = create_color_func("BAD")
from portage.util import writemsg
from portage.util.SlotObject import SlotObject
from portage.versions import catpkgsplit

from _emerge.Blocker import Blocker
from _emerge.Package import Package


class _RepoDisplay:
	def __init__(self, roots):
		self._shown_repos = {}
		self._unknown_repo = False
		repo_paths = set()
		for root_config in roots.values():
			for repo in root_config.settings.repositories:
				repo_paths.add(repo.location)
		repo_paths = list(repo_paths)
		self._repo_paths = repo_paths
		self._repo_paths_real = [ os.path.realpath(repo_path) \
			for repo_path in repo_paths ]

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
			output.append("Repositories:\n")
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


class _PackageCounters:

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
		myoutput.append(", Size of downloads: %s" % localized_size(self.totalsize))
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


class _DisplayConfig:

	def __init__(self, depgraph, mylist, favorites, verbosity):
		frozen_config = depgraph._frozen_config
		dynamic_config = depgraph._dynamic_config

		self.mylist = mylist
		self.favorites = InternalPackageSet(favorites, allow_repo=True)
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

		if "--quiet-repo-display" in frozen_config.myopts:
			self.repo_display = _RepoDisplay(frozen_config.roots)
		self.trees = frozen_config.trees
		self.pkgsettings = frozen_config.pkgsettings
		self.target_root = frozen_config.target_root
		self.running_root = frozen_config._running_root
		self.roots = frozen_config.roots

		# Create a set of selected packages for each root
		self.selected_sets = {}
		for root_name, root in self.roots.items():
			try:
				self.selected_sets[root_name] = InternalPackageSet(
					initial_atoms=root.setconfig.getSetAtoms("selected"))
			except PackageSetNotFound:
				# A nested set could not be resolved, so ignore nested sets.
				self.selected_sets[root_name] = root.sets["selected"]

		self.blocker_parents = dynamic_config._blocker_parents
		self.reinstall_nodes = dynamic_config._reinstall_nodes
		self.digraph = dynamic_config.digraph
		self.blocker_uninstalls = dynamic_config._blocker_uninstalls
		self.package_tracker = dynamic_config._package_tracker
		self.set_nodes = dynamic_config._set_nodes

		self.pkg_use_enabled = depgraph._pkg_use_enabled
		self.pkg = depgraph._pkg


def _create_use_string(conf, name, cur_iuse, iuse_forced, cur_use,
	old_iuse, old_use,
	is_new, feature_flags, reinst_flags):

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
			if flag in feature_flags:
				flag_str = "{" + flag_str + "}"
			elif flag in iuse_forced:
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
		upgrade_node = next(conf.package_tracker.match(
			uninstall.root, uninstall.slot_atom), None)

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


def _calc_changelog(ebuildpath,current,next): # pylint: disable=redefined-builtin
	if ebuildpath == None or not os.path.exists(ebuildpath):
		return []
	current = '-'.join(catpkgsplit(current)[1:])
	if current.endswith('-r0'):
		current = current[:-3]
	next = '-'.join(catpkgsplit(next)[1:])
	if next.endswith('-r0'):
		next = next[:-3]

	changelogdir = os.path.dirname(ebuildpath)
	changelogs = ['ChangeLog']
	# ChangeLog-YYYY (see bug #389611)
	changelogs.extend(sorted((fn for fn in os.listdir(changelogdir)
		if fn.startswith('ChangeLog-')), reverse=True))

	divisions = []
	found_current = False
	for fn in changelogs:
		changelogpath = os.path.join(changelogdir, fn)
		try:
			with io.open(_unicode_encode(changelogpath,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace') as f:
				changelog = f.read()
		except EnvironmentError:
			return []
		for node in _find_changelog_tags(changelog):
			if node[0] == current:
				found_current = True
				break
			else:
				divisions.append(node)
		if found_current:
			break

	if not found_current:
		return []

	#print 'XX from',current,'to',next
	#for div,text in divisions: print 'XX',div
	# skip entries for all revisions above the one we are about to emerge
	later_rev_index = None
	for i, node in enumerate(divisions):
		if node[0] == next:
			if later_rev_index is not None:
				first_node = divisions[later_rev_index]
				# Discard the later revision and the first ChangeLog entry
				# that follows it. We want to display all the entries after
				# that first entry, as discussed in bug #373009.
				trimmed_lines = []
				iterator = iter(first_node[1])
				for l in iterator:
					if not l:
						# end of the first entry that's discarded
						break
				first_node = (None, list(iterator))
				divisions = [first_node] + divisions[later_rev_index+1:]
			break
		if node[0] is not None:
			later_rev_index = i

	output = []
	prev_blank = False
	prev_rev = False
	for rev, lines in divisions:
		if rev is not None:
			if not (prev_blank or prev_rev):
				output.append("\n")
			output.append(bold('*' + rev) + '\n')
			prev_rev = True
			prev_blank = False
		if lines:
			prev_rev = False
			if not prev_blank:
				output.append("\n")
			for l in lines:
				output.append(l + "\n")
			output.append("\n")
			prev_blank = True
	return output

def _strip_header_comments(lines):
	# strip leading and trailing blank or header/comment lines
	i = 0
	while i < len(lines) and (not lines[i] or lines[i][:1] == "#"):
		i += 1
	if i:
		lines = lines[i:]
	while lines and (not lines[-1] or lines[-1][:1] == "#"):
		lines.pop()
	return lines

def _find_changelog_tags(changelog):
	divs = []
	if not changelog:
		return divs
	release = None
	release_end = 0
	for match in re.finditer(r'^\*\ ?([-a-zA-Z0-9_.+]*)(?:\ .*)?$',
		changelog, re.M):
		divs.append((release, _strip_header_comments(
			changelog[release_end:match.start()].splitlines())))
		release_end = match.end()
		release = match.group(1)
		if release.endswith('.ebuild'):
			release = release[:-7]
		if release.endswith('-r0'):
			release = release[:-3]

	divs.append((release,
		_strip_header_comments(changelog[release_end:].splitlines())))
	return divs

class PkgInfo:
	"""Simple class to hold instance attributes for current
	information about the pkg being printed.
	"""

	__slots__ = ("attr_display", "built", "cp",
		"ebuild_path", "fetch_symbol", "merge",
		"oldbest", "oldbest_list", "operation", "ordered", "previous_pkg",
		"repo_name", "repo_path_real", "slot", "sub_slot", "system", "use", "ver", "world")


	def __init__(self):
		self.built = False
		self.cp = ''
		self.ebuild_path = ''
		self.fetch_symbol = ''
		self.merge = ''
		self.oldbest = ''
		self.oldbest_list = []
		self.operation = ''
		self.ordered = False
		self.previous_pkg = None
		self.repo_path_real = ''
		self.repo_name = ''
		self.slot = ''
		self.sub_slot = ''
		self.system = False
		self.use = ''
		self.ver = ''
		self.world = False
		self.attr_display = PkgAttrDisplay()

class PkgAttrDisplay(SlotObject):

	__slots__ = ("downgrade", "fetch_restrict", "fetch_restrict_satisfied",
		"force_reinstall",
		"interactive", "mask", "new", "new_slot", "new_version", "replace")

	def __str__(self):
		output = []

		if self.interactive:
			output.append(colorize("WARN", "I"))
		else:
			output.append(" ")

		if self.new or self.force_reinstall:
			if self.force_reinstall:
				output.append(red("r"))
			else:
				output.append(green("N"))
		else:
			output.append(" ")

		if self.new_slot or self.replace:
			if self.replace:
				output.append(yellow("R"))
			else:
				output.append(green("S"))
		else:
			output.append(" ")

		if self.fetch_restrict or self.fetch_restrict_satisfied:
			if self.fetch_restrict_satisfied:
				output.append(green("f"))
			else:
				output.append(red("F"))
		else:
			output.append(" ")

		if self.new_version:
			output.append(turquoise("U"))
		else:
			output.append(" ")

		if self.downgrade:
			output.append(blue("D"))
		else:
			output.append(" ")

		if self.mask is not None:
			output.append(self.mask)

		return "".join(output)
