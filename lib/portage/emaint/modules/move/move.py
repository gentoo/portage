# Copyright 2005-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.Package import Package

import portage
from portage import os
from portage.exception import InvalidData
from portage.versions import _pkg_str

class MoveHandler:

	def __init__(self, tree, porttree):
		self._tree = tree
		self._portdb = porttree.dbapi
		self._update_keys = Package._dep_keys
		self._master_repo = self._portdb.repositories.mainRepo()
		if self._master_repo is not None:
			self._master_repo = self._master_repo.name

	def _grab_global_updates(self):
		from portage.update import grab_updates, parse_updates
		retupdates = {}
		errors = []

		for repo_name in self._portdb.getRepositories():
			repo = self._portdb.getRepositoryPath(repo_name)
			updpath = os.path.join(repo, "profiles", "updates")
			if not os.path.isdir(updpath):
				continue

			try:
				rawupdates = grab_updates(updpath)
			except portage.exception.DirectoryNotFound:
				rawupdates = []
			upd_commands = []
			for mykey, mystat, mycontent in rawupdates:
				commands, errors = parse_updates(mycontent)
				upd_commands.extend(commands)
				errors.extend(errors)
			retupdates[repo_name] = upd_commands

		if self._master_repo in retupdates:
			retupdates['DEFAULT'] = retupdates[self._master_repo]

		return retupdates, errors

	def check(self, **kwargs):
		onProgress = kwargs.get('onProgress', None)
		allupdates, errors = self._grab_global_updates()
		# Matching packages and moving them is relatively fast, so the
		# progress bar is updated in indeterminate mode.
		match = self._tree.dbapi.match
		aux_get = self._tree.dbapi.aux_get
		pkg_str = self._tree.dbapi._pkg_str
		settings = self._tree.dbapi.settings
		if onProgress:
			onProgress(0, 0)
		for repo, updates in allupdates.items():
			if repo == 'DEFAULT':
				continue
			if not updates:
				continue

			def repo_match(repository):
				return repository == repo or \
					(repo == self._master_repo and \
					repository not in allupdates)

			for i, update_cmd in enumerate(updates):
				if update_cmd[0] == "move":
					origcp, newcp = update_cmd[1:]
					for cpv in match(origcp):
						try:
							cpv = pkg_str(cpv, origcp.repo)
						except (KeyError, InvalidData):
							continue
						if repo_match(cpv.repo):
							build_time = getattr(cpv, 'build_time', None)
							if build_time is not None:
								# If this update has already been applied to the same
								# package build then silently continue.
								for maybe_applied in match('={}'.format(
									cpv.replace(cpv.cp, str(newcp), 1))):
									if maybe_applied.build_time == build_time:
										break
								else:
									errors.append("'%s' moved to '%s'" % (cpv, newcp))
				elif update_cmd[0] == "slotmove":
					pkg, origslot, newslot = update_cmd[1:]
					atom = pkg.with_slot(origslot)
					for cpv in match(atom):
						try:
							cpv = pkg_str(cpv, atom.repo)
						except (KeyError, InvalidData):
							continue
						if repo_match(cpv.repo):
							errors.append("'%s' slot moved from '%s' to '%s'" % \
								(cpv, origslot, newslot))
				if onProgress:
					onProgress(0, 0)

		# Searching for updates in all the metadata is relatively slow, so this
		# is where the progress bar comes out of indeterminate mode.
		cpv_all = self._tree.dbapi.cpv_all()
		cpv_all.sort()
		maxval = len(cpv_all)
		meta_keys = self._update_keys + self._portdb._pkg_str_aux_keys
		if onProgress:
			onProgress(maxval, 0)
		for i, cpv in enumerate(cpv_all):
			try:
				metadata = dict(zip(meta_keys, aux_get(cpv, meta_keys)))
			except KeyError:
				continue
			try:
				pkg = _pkg_str(cpv, metadata=metadata, settings=settings)
			except InvalidData:
				continue
			metadata = dict((k, metadata[k]) for k in self._update_keys)
			try:
				updates = allupdates[pkg.repo]
			except KeyError:
				try:
					updates = allupdates['DEFAULT']
				except KeyError:
					continue
			if not updates:
				continue
			metadata_updates = \
				portage.update_dbentries(updates, metadata, parent=pkg)
			if metadata_updates:
				errors.append("'%s' has outdated metadata" % cpv)
			if onProgress:
				onProgress(maxval, i+1)

		if errors:
			return (False, errors)
		return (True, None)

	def fix(self,  **kwargs):
		onProgress = kwargs.get('onProgress', None)
		allupdates, errors = self._grab_global_updates()
		# Matching packages and moving them is relatively fast, so the
		# progress bar is updated in indeterminate mode.
		move = self._tree.dbapi.move_ent
		slotmove = self._tree.dbapi.move_slot_ent
		if onProgress:
			onProgress(0, 0)
		for repo, updates in allupdates.items():
			if repo == 'DEFAULT':
				continue
			if not updates:
				continue

			def repo_match(repository):
				return repository == repo or \
					(repo == self._master_repo and \
					repository not in allupdates)

			for i, update_cmd in enumerate(updates):
				if update_cmd[0] == "move":
					move(update_cmd, repo_match=repo_match)
				elif update_cmd[0] == "slotmove":
					slotmove(update_cmd, repo_match=repo_match)
				if onProgress:
					onProgress(0, 0)

		# Searching for updates in all the metadata is relatively slow, so this
		# is where the progress bar comes out of indeterminate mode.
		self._tree.dbapi.update_ents(allupdates, onProgress=onProgress)
		if errors:
			return (False, errors)
		return (True, None)

class MoveInstalled(MoveHandler):

	short_desc = "Perform package move updates for installed packages"

	@staticmethod
	def name():
		return "moveinst"

	def __init__(self):
		eroot = portage.settings['EROOT']
		MoveHandler.__init__(self, portage.db[eroot]["vartree"], portage.db[eroot]["porttree"])

class MoveBinary(MoveHandler):

	short_desc = "Perform package move updates for binary packages"

	@staticmethod
	def name():
		return "movebin"

	def __init__(self):
		eroot = portage.settings['EROOT']
		MoveHandler.__init__(self, portage.db[eroot]["bintree"], portage.db[eroot]['porttree'])
