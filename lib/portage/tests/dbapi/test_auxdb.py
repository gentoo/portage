# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import coroutine


class AuxdbTestCase(TestCase):

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
				"EAPI": "7"
			},
			"cat/B-1": {
				"EAPI": "7"
			},
		}

		playground = ResolverPlayground(ebuilds=ebuilds,
			user_config={'modules': ('portdbapi.auxdbmodule = %s' % auxdbmodule,)})

		portdb = playground.trees[playground.eroot]["porttree"].dbapi

		loop = asyncio._wrap_loop()
		loop.run_until_complete(self._test_mod_async(ebuilds, portdb))

	@coroutine
	def _test_mod_async(self, ebuilds, portdb):

		for cpv, metadata in ebuilds.items():
			eapi, = yield portdb.async_aux_get(cpv, ['EAPI'])
			self.assertEqual(eapi, metadata['EAPI'])
