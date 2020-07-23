# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2


from portage.dep.soname.SonameAtom import SonameAtom
from portage.tests import TestCase
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor


class TestSonameAtomPickle(TestCase):

	_ALL_PROVIDES = frozenset([SonameAtom('x86_64', 'libc.so.6')])

	def test_soname_atom_pickle(self):
		loop = asyncio._wrap_loop()
		with ForkExecutor(loop=loop) as executor:
			result = loop.run_until_complete(loop.run_in_executor(executor, self._get_all_provides))
		self.assertEqual(self._ALL_PROVIDES, result)

	@classmethod
	def _get_all_provides(cls):
		return cls._ALL_PROVIDES
