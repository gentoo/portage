# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import coroutine


class AuxdbTestCase(TestCase):

	def test_anydbm(self):
		try:
			from portage.cache.anydbm import database
		except ImportError:
			self.skipTest('dbm import failed')
		self._test_mod('portage.cache.anydbm.database')

	def test_flat_hash_md5(self):
		self._test_mod('portage.cache.flat_hash.md5_database')

	def test_volatile(self):
		self._test_mod('portage.cache.volatile.database')

	def test_sqite(self):
		try:
			import sqlite3
		except ImportError:
			self.skipTest('sqlite3 import failed')
		self._test_mod('portage.cache.sqlite.database')

	def _test_mod(self, auxdbmodule):
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

		loop = asyncio._wrap_loop()
		loop.run_until_complete(self._test_mod_async(ebuilds, ebuild_inherited, eclass_defined_phases, eclass_depend, portdb))

	@coroutine
	def _test_mod_async(self, ebuilds, ebuild_inherited, eclass_defined_phases, eclass_depend, portdb):

		for cpv, metadata in ebuilds.items():
			defined_phases, depend, eapi, inherited = yield portdb.async_aux_get(cpv, ['DEFINED_PHASES', 'DEPEND', 'EAPI', 'INHERITED'])
			self.assertEqual(defined_phases, eclass_defined_phases)
			self.assertEqual(depend, eclass_depend)
			self.assertEqual(eapi, metadata['EAPI'])
			self.assertEqual(frozenset(inherited.split()), ebuild_inherited)
