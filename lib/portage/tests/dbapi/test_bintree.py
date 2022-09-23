# Copyright 2020-2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from unittest.mock import MagicMock

from portage.tests import TestCase

from portage.dbapi.bintree import binarytree


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
            "pkgdir", "_multi_instance", "dbapi", "update_ents",
            "move_slot_ent", "populated", "tree", "_binrepos_conf",
            "_remote_has_index", "_remotepkgs", "_additional_pkgs",
            "invalids", "settings", "_pkg_paths", "_populating",
            "_all_directory", "_pkgindex_version", "_pkgindex_hashes",
            "_pkgindex_file", "_pkgindex_keys", "_pkgindex_aux_keys",
            "_pkgindex_use_evaluated_keys", "_pkgindex_header",
            "_pkgindex_header_keys", "_pkgindex_default_pkg_data",
            "_pkgindex_inherited_keys", "_pkgindex_default_header_data",
            "_pkgindex_translated_keys", "_pkgindex_allowed_pkg_keys",
        }
        no_multi_instance_settings = MagicMock()
        no_multi_instance_settings.features = ""
        no_multi_instance_bt = binarytree(
            pkgdir="/tmp", settings=no_multi_instance_settings)
        multi_instance_settings = MagicMock()
        multi_instance_settings.features = "binpkg-multi-instance"
        multi_instance_bt = binarytree(
            pkgdir="/tmp", settings=multi_instance_settings)
        for attr in required_attrs_no_multi_instance:
            getattr(no_multi_instance_bt, attr)
            getattr(multi_instance_bt, attr)
        # The next attribute is the difference between multi instance
        # and no multi instance:
        getattr(multi_instance_bt, "_allocate_filename")
