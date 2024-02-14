# Copyright 2020-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools

from portage import multiprocessing
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor


class AuxdbTestCase(TestCase):
    def test_anydbm(self):
        try:
            from portage.cache.anydbm import database
        except ImportError:
            self.skipTest("dbm import failed")
        self._test_mod("portage.cache.anydbm.database", multiproc=False, picklable=True)

    def test_flat_hash_md5(self):
        self._test_mod("portage.cache.flat_hash.md5_database")

    def test_volatile(self):
        self._test_mod("portage.cache.volatile.database", multiproc=False)

    def test_sqite(self):
        try:
            import sqlite3
        except ImportError:
            self.skipTest("sqlite3 import failed")
        self._test_mod("portage.cache.sqlite.database", picklable=True)

    def _test_mod(self, auxdbmodule, multiproc=True, picklable=True):
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
            "foo": ("inherit bar",),
            "bar": (
                "EXPORT_FUNCTIONS src_prepare",
                f'DEPEND="{eclass_depend}"',
                "bar_src_prepare() { default; }",
            ),
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            eclasses=eclasses,
            user_config={"modules": (f"portdbapi.auxdbmodule = {auxdbmodule}",)},
        )

        try:
            portdb = playground.trees[playground.eroot]["porttree"].dbapi
            metadata_keys = ["DEFINED_PHASES", "DEPEND", "EAPI", "INHERITED"]

            test_func = functools.partial(
                self._run_test_mod_async, ebuilds, metadata_keys, portdb
            )

            results = test_func()

            self._compare_results(
                ebuilds, eclass_defined_phases, eclass_depend, ebuild_inherited, results
            )

            loop = asyncio._wrap_loop()
            picklable_or_fork = picklable or multiprocessing.get_start_method == "fork"
            if picklable_or_fork:
                results = loop.run_until_complete(
                    loop.run_in_executor(ForkExecutor(), test_func)
                )

                self._compare_results(
                    ebuilds,
                    eclass_defined_phases,
                    eclass_depend,
                    ebuild_inherited,
                    results,
                )

            auxdb = portdb.auxdb[portdb.getRepositoryPath("test_repo")]
            cpv = next(iter(ebuilds))

            modify_auxdb = functools.partial(self._modify_auxdb, auxdb, cpv)

            if multiproc and picklable_or_fork:
                loop.run_until_complete(
                    loop.run_in_executor(ForkExecutor(), modify_auxdb)
                )
            else:
                modify_auxdb()

            self.assertEqual(auxdb[cpv]["RESTRICT"], "test")
        finally:
            playground.cleanup()

    def _compare_results(
        self, ebuilds, eclass_defined_phases, eclass_depend, ebuild_inherited, results
    ):
        for cpv, metadata in ebuilds.items():
            self.assertEqual(results[cpv]["DEFINED_PHASES"], eclass_defined_phases)
            self.assertEqual(results[cpv]["DEPEND"], eclass_depend)
            self.assertEqual(results[cpv]["EAPI"], metadata["EAPI"])
            self.assertEqual(
                frozenset(results[cpv]["INHERITED"].split()), ebuild_inherited
            )

    @staticmethod
    def _run_test_mod_async(ebuilds, metadata_keys, portdb):
        loop = asyncio._wrap_loop()
        return loop.run_until_complete(
            AuxdbTestCase._test_mod_async(
                ebuilds,
                metadata_keys,
                portdb,
            )
        )

    @staticmethod
    async def _test_mod_async(ebuilds, metadata_keys, portdb):
        results = {}
        for cpv, metadata in ebuilds.items():
            results[cpv] = dict(
                zip(metadata_keys, await portdb.async_aux_get(cpv, metadata_keys))
            )

        return results

    @staticmethod
    def _modify_auxdb(auxdb, cpv):
        metadata = auxdb[cpv]
        metadata["RESTRICT"] = "test"
        try:
            del metadata["_eclasses_"]
        except KeyError:
            pass
        auxdb[cpv] = metadata
