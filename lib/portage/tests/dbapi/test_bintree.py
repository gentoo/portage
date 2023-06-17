# Copyright 2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from unittest.mock import MagicMock, patch, call
import os

from portage.tests import TestCase

from portage.dbapi.bintree import binarytree
from portage.localization import _
from portage.const import BINREPOS_CONF_FILE


class BinarytreeTestCase(TestCase):
    def test_required_init_params(self):
        with self.assertRaises(TypeError) as cm:
            binarytree()
        self.assertEqual(str(cm.exception), "pkgdir parameter is required")
        with self.assertRaises(TypeError) as cm:
            binarytree(pkgdir="/tmp")
        self.assertEqual(str(cm.exception), "settings parameter is required")

    def test_init_with_legacy_params_warns(self):
        with self.assertWarns(DeprecationWarning):
            binarytree(_unused=None, pkgdir="/tmp", settings=MagicMock())
        with self.assertWarns(DeprecationWarning):
            binarytree(virtual=None, pkgdir="/tmp", settings=MagicMock())

    def test_instance_has_required_attrs(self):
        # Quite smoky test. What would it be a better testing strategy?
        # Not sure yet...
        required_attrs_no_multi_instance = {
            "pkgdir",
            "_multi_instance",
            "dbapi",
            "update_ents",
            "move_slot_ent",
            "populated",
            "tree",
            "_binrepos_conf",
            "_remote_has_index",
            "_remotepkgs",
            "_additional_pkgs",
            "invalids",
            "settings",
            "_pkg_paths",
            "_populating",
            "_all_directory",
            "_pkgindex_version",
            "_pkgindex_hashes",
            "_pkgindex_file",
            "_pkgindex_keys",
            "_pkgindex_aux_keys",
            "_pkgindex_use_evaluated_keys",
            "_pkgindex_header",
            "_pkgindex_header_keys",
            "_pkgindex_default_pkg_data",
            "_pkgindex_inherited_keys",
            "_pkgindex_default_header_data",
            "_pkgindex_translated_keys",
            "_pkgindex_allowed_pkg_keys",
        }
        no_multi_instance_settings = MagicMock()
        no_multi_instance_settings.features = ""
        no_multi_instance_bt = binarytree(
            pkgdir="/tmp", settings=no_multi_instance_settings
        )
        multi_instance_settings = MagicMock()
        multi_instance_settings.features = "binpkg-multi-instance"
        multi_instance_bt = binarytree(pkgdir="/tmp", settings=multi_instance_settings)
        for attr in required_attrs_no_multi_instance:
            getattr(no_multi_instance_bt, attr)
            getattr(multi_instance_bt, attr)
        # The next attribute is the difference between multi instance
        # and no multi instance:
        getattr(multi_instance_bt, "_allocate_filename")

    @patch("portage.dbapi.bintree.binarytree._populate_local")
    def test_populate_without_updates_repos_nor_getbinspkgs(self, ppopulate_local):
        bt = binarytree(pkgdir="/tmp", settings=MagicMock())
        ppopulate_local.return_value = {}
        bt.populate()
        ppopulate_local.assert_called_once_with(reindex=True)
        self.assertFalse(bt._populating)
        self.assertTrue(bt.populated)

    @patch("portage.dbapi.bintree.binarytree._populate_local")
    def test_populate_calls_twice_populate_local_if_updates(self, ppopulate_local):
        bt = binarytree(pkgdir="/tmp", settings=MagicMock())
        bt.populate()
        self.assertIn(call(reindex=True), ppopulate_local.mock_calls)
        self.assertIn(call(), ppopulate_local.mock_calls)
        self.assertEqual(ppopulate_local.call_count, 2)

    @patch("portage.dbapi.bintree.binarytree._populate_additional")
    @patch("portage.dbapi.bintree.binarytree._populate_local")
    def test_populate_with_repos(self, ppopulate_local, ppopulate_additional):
        repos = ("one", "two")
        bt = binarytree(pkgdir="/tmp", settings=MagicMock())
        bt.populate(add_repos=repos)
        ppopulate_additional.assert_called_once_with(repos)

    @patch("portage.dbapi.bintree.BinRepoConfigLoader")
    @patch("portage.dbapi.bintree.binarytree._populate_remote")
    @patch("portage.dbapi.bintree.binarytree._populate_local")
    def test_populate_with_getbinpkgs(
        self, ppopulate_local, ppopulate_remote, pBinRepoConfigLoader
    ):
        refresh = "something"
        settings = MagicMock()
        settings.__getitem__.return_value = "/some/path"
        bt = binarytree(pkgdir="/tmp", settings=settings)
        bt.populate(getbinpkgs=True, getbinpkg_refresh=refresh)
        ppopulate_remote.assert_called_once_with(getbinpkg_refresh=refresh)

    @patch("portage.dbapi.bintree.writemsg")
    @patch("portage.dbapi.bintree.BinRepoConfigLoader")
    @patch("portage.dbapi.bintree.binarytree._populate_remote")
    @patch("portage.dbapi.bintree.binarytree._populate_local")
    def test_populate_with_getbinpkgs_and_not_BinRepoConfigLoader(
        self, ppopulate_local, ppopulate_remote, pBinRepoConfigLoader, pwritemsg
    ):
        refresh = "something"
        settings = MagicMock()
        portage_root = "/some/path"
        settings.__getitem__.return_value = portage_root
        pBinRepoConfigLoader.return_value = None
        conf_file = os.path.join(portage_root, BINREPOS_CONF_FILE)
        bt = binarytree(pkgdir="/tmp", settings=settings)
        bt.populate(getbinpkgs=True, getbinpkg_refresh=refresh)
        ppopulate_remote.assert_not_called()
        pwritemsg.assert_called_once_with(
            _(
                f"!!! {conf_file} is missing (or PORTAGE_BINHOST is unset)"
                ", but use is requested.\n"
            ),
            noiselevel=-1,
        )

    @patch("portage.dbapi.bintree.BinRepoConfigLoader")
    @patch("portage.dbapi.bintree.binarytree._populate_remote")
    @patch("portage.dbapi.bintree.binarytree._populate_local")
    def test_default_getbinpkg_refresh_in_populate(
        self, ppopulate_local, ppopulate_remote, pBinRepoConfigLoader
    ):
        """Bug #864259
        This test fixes the bug. It requires that
        ``_emerge.actions.run_action`` calls ``binarytree.populate``
        explicitly with ``getbinpkg_refresh=True``
        """
        settings = MagicMock()
        settings.__getitem__.return_value = "/some/path"
        bt = binarytree(pkgdir="/tmp", settings=settings)
        bt.populate(getbinpkgs=True)
        ppopulate_remote.assert_called_once_with(getbinpkg_refresh=False)
