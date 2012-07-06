# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io

import portage
from portage import os
from portage import _unicode_decode
from portage.dep import Atom
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

		cmd, root, atom_str = argv

		eapi = self.settings.get('EAPI')
		allow_repo = eapi_has_repo_deps(eapi)
		try:
			atom = Atom(atom_str, allow_repo=allow_repo)
		except InvalidAtom:
			return ('', 'invalid atom: %s\n' % atom_str, 2)

		warnings = []
		try:
			atom = Atom(atom_str, allow_repo=allow_repo, eapi=eapi)
		except InvalidAtom as e:
			warnings.append(_unicode_decode("QA Notice: %s: %s") % (cmd, e))

		use = self.settings.get('PORTAGE_BUILT_USE')
		if use is None:
			use = self.settings['PORTAGE_USE']

		use = frozenset(use.split())
		atom = atom.evaluate_conditionals(use)

		db = self.get_db()

		warnings_str = ''
		if warnings:
			warnings_str = self._elog('eqawarn', warnings)

		root = normalize_path(root).rstrip(os.path.sep) + os.path.sep
		if root not in db:
			return ('', 'invalid ROOT: %s\n' % root, 2)

		vardb = db[root]["vartree"].dbapi

		if cmd == 'has_version':
			if vardb.match(atom):
				returncode = 0
			else:
				returncode = 1
			return ('', warnings_str, returncode)
		elif cmd == 'best_version':
			m = best(vardb.match(atom))
			return ('%s\n' % m, warnings_str, 0)
		else:
			return ('', 'invalid command: %s\n' % cmd, 2)

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
