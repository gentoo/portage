# Copyright 2010-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io

import portage
from portage import os
from portage.dep import Atom, _repo_name_re
from portage.eapi import eapi_has_repo_deps
from portage.elog import messages as elog_messages
from portage.exception import InvalidAtom
from portage.package.ebuild._ipc.IpcCommand import IpcCommand
from portage.util import normalize_path
from portage.versions import best

class QueryCommand(IpcCommand):

	__slots__ = ('phase', 'settings',)

	_db = None

	@classmethod
	def get_db(cls):
		if cls._db is not None:
			return cls._db
		return portage.db

	def __init__(self, settings, phase):
		IpcCommand.__init__(self)
		self.settings = settings
		self.phase = phase

	def __call__(self, argv):
		"""
		@return: tuple of (stdout, stderr, returncode)
		"""

		# Python 3:
		# cmd, root, *args = argv
		cmd = argv[0]
		root = argv[1]
		args = argv[2:]

		warnings = []
		warnings_str = ''

		db = self.get_db()
		eapi = self.settings.get('EAPI')

		root = normalize_path(root or os.sep).rstrip(os.sep) + os.sep
		if root not in db:
			return ('', '%s: Invalid ROOT: %s\n' % (cmd, root), 3)

		portdb = db[root]["porttree"].dbapi
		vardb = db[root]["vartree"].dbapi

		if cmd in ('best_version', 'has_version'):
			allow_repo = eapi_has_repo_deps(eapi)
			try:
				atom = Atom(args[0], allow_repo=allow_repo)
			except InvalidAtom:
				return ('', '%s: Invalid atom: %s\n' % (cmd, args[0]), 2)

			try:
				atom = Atom(args[0], allow_repo=allow_repo, eapi=eapi)
			except InvalidAtom as e:
				warnings.append("QA Notice: %s: %s" % (cmd, e))

			use = self.settings.get('PORTAGE_BUILT_USE')
			if use is None:
				use = self.settings['PORTAGE_USE']

			use = frozenset(use.split())
			atom = atom.evaluate_conditionals(use)

		if warnings:
			warnings_str = self._elog('eqawarn', warnings)

		if cmd == 'has_version':
			if vardb.match(atom):
				returncode = 0
			else:
				returncode = 1
			return ('', warnings_str, returncode)
		if cmd == 'best_version':
			m = best(vardb.match(atom))
			return ('%s\n' % m, warnings_str, 0)
		if cmd in ('master_repositories', 'repository_path', 'available_eclasses', 'eclass_path', 'license_path'):
			repo = _repo_name_re.match(args[0])
			if repo is None:
				return ('', '%s: Invalid repository: %s\n' % (cmd, args[0]), 2)
			try:
				repo = portdb.repositories[args[0]]
			except KeyError:
				return ('', warnings_str, 1)

			if cmd == 'master_repositories':
				return ('%s\n' % ' '.join(x.name for x in repo.masters), warnings_str, 0)
			if cmd == 'repository_path':
				return ('%s\n' % repo.location, warnings_str, 0)
			if cmd == 'available_eclasses':
				return ('%s\n' % ' '.join(sorted(repo.eclass_db.eclasses)), warnings_str, 0)
			if cmd == 'eclass_path':
				try:
					eclass = repo.eclass_db.eclasses[args[1]]
				except KeyError:
					return ('', warnings_str, 1)
				return ('%s\n' % eclass.location, warnings_str, 0)
			if cmd == 'license_path':
				paths = reversed([os.path.join(x.location, 'licenses', args[1]) for x in list(repo.masters) + [repo]])
				for path in paths:
					if os.path.exists(path):
						return ('%s\n' % path, warnings_str, 0)
				return ('', warnings_str, 1)
		return ('', 'Invalid command: %s\n' % cmd, 3)

	def _elog(self, elog_funcname, lines):
		"""
		This returns a string, to be returned via ipc and displayed at the
		appropriate place in the build output. We wouldn't want to open the
		log here since it is already opened by AbstractEbuildProcess and we
		don't want to corrupt it, especially if it is being written with
		compression.
		"""
		out = io.StringIO()
		phase = self.phase
		elog_func = getattr(elog_messages, elog_funcname)
		global_havecolor = portage.output.havecolor
		try:
			portage.output.havecolor = \
				self.settings.get('NOCOLOR', 'false').lower() in ('no', 'false')
			for line in lines:
				elog_func(line, phase=phase, key=self.settings.mycpv, out=out)
		finally:
			portage.output.havecolor = global_havecolor
		msg = out.getvalue()
		return msg
