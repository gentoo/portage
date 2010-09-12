# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.dep import Atom
from portage.exception import InvalidAtom
from portage.package.ebuild._ipc.IpcCommand import IpcCommand
from portage.util import normalize_path
from portage.versions import best

class QueryCommand(IpcCommand):

	__slots__ = ('settings',)

	_db = None

	def __init__(self, settings):
		IpcCommand.__init__(self)
		self.settings = settings

	def __call__(self, argv):
		"""
		@returns: tuple of (stdout, stderr, returncode)
		"""

		cmd, root, atom = argv

		try:
			atom = Atom(atom)
		except InvalidAtom:
			return ('', 'invalid atom: %s\n' % atom, 2)

		use = self.settings.get('PORTAGE_BUILT_USE')
		if use is None:
			use = self.settings['PORTAGE_USE']

		use = frozenset(use.split())
		atom = atom.evaluate_conditionals(use)

		db = self._db
		if db is None:
			db = portage.db

		root = normalize_path(root).rstrip(os.path.sep) + os.path.sep
		if root not in db:
			return ('', 'invalid ROOT: %s\n' % root, 2)

		vardb = db[root]["vartree"].dbapi

		if cmd == 'has_version':
			if vardb.match(atom):
				returncode = 0
			else:
				returncode = 1
			return ('', '', returncode)
		elif cmd == 'best_version':
			m = best(vardb.match(atom))
			return ('%s\n' % m, '', 0)
		else:
			return ('', 'invalid command: %s\n' % cmd, 2)
