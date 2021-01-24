# Copyright 2020-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor


class AuxdbTestCase(TestCase):

	def test_anydbm(self):
		try:
			from portage.cache.anydbm import database
		except ImportError:
			self.skipTest('dbm import failed')
		self._test_mod('portage.cache.anydbm.database', multiproc=False)

	def test_flat_hash_md5(self):
		self._test_mod('portage.cache.flat_hash.md5_database')

	def test_volatile(self):
		self._test_mod('portage.cache.volatile.database', multiproc=False)

	def test_sqite(self):
		try:
			import sqlite3
		except ImportError:
			self.skipTest('sqlite3 import failed')
		self._test_mod('portage.cache.sqlite.database')

	def _test_mod(self, auxdbmodule, multiproc=True):
		ebuilds = {
			"cat/A-1": {
				"EAPI": "7",
				"MISC_CONTENT": "inherit foo",
			},
			"cat/B-1": {
				"EAPI": "7",
				"MISC_CONTENT": "inherit foo",
			},
		}

		ebuild_inherited = frozenset(["bar", "foo"])
		eclass_defined_phases = "prepare"
		eclass_depend = "bar/foo"

		eclasses = {
			"foo": (
				"inherit bar",
			),
			"bar": (
				"EXPORT_FUNCTIONS src_prepare",
				"DEPEND=\"{}\"".format(eclass_depend),
				"bar_src_prepare() { default; }",
			),
		}

		playground = ResolverPlayground(ebuilds=ebuilds, eclasses=eclasses,
			user_config={'modules': ('portdbapi.auxdbmodule = %s' % auxdbmodule,)})

		portdb = playground.trees[playground.eroot]["porttree"].dbapi

		def test_func():
			loop = asyncio._wrap_loop()
			return loop.run_until_complete(self._test_mod_async(
				ebuilds, ebuild_inherited, eclass_defined_phases, eclass_depend, portdb))

		self.assertTrue(test_func())

		loop = asyncio._wrap_loop()
		self.assertTrue(loop.run_until_complete(loop.run_in_executor(ForkExecutor(), test_func)))

		auxdb = portdb.auxdb[portdb.getRepositoryPath('test_repo')]
		cpv = next(iter(ebuilds))

		def modify_auxdb():
			metadata = auxdb[cpv]
			metadata['RESTRICT'] = 'test'
			try:
				del metadata['_eclasses_']
			except KeyError:
				pass
			auxdb[cpv] = metadata

		if multiproc:
			loop.run_until_complete(loop.run_in_executor(ForkExecutor(), modify_auxdb))
		else:
			modify_auxdb()

		self.assertEqual(auxdb[cpv]['RESTRICT'], 'test')

	async def _test_mod_async(self, ebuilds, ebuild_inherited, eclass_defined_phases, eclass_depend, portdb):

		for cpv, metadata in ebuilds.items():
			defined_phases, depend, eapi, inherited = await portdb.async_aux_get(cpv, ['DEFINED_PHASES', 'DEPEND', 'EAPI', 'INHERITED'])
			self.assertEqual(defined_phases, eclass_defined_phases)
			self.assertEqual(depend, eclass_depend)
			self.assertEqual(eapi, metadata['EAPI'])
			self.assertEqual(frozenset(inherited.split()), ebuild_inherited)

		return True
