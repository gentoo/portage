# Copyright 2022-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from unittest.mock import MagicMock, patch

from _emerge.actions import get_libc_version, run_action
from _emerge.create_world_atom import create_world_atom

from portage.const import LIBC_PACKAGE_ATOM
from portage.dbapi.virtual import fakedbapi
from portage.dep import Atom
from portage.tests import TestCase


class RunActionTestCase(TestCase):
    """This class' purpose is to encompass UTs for ``actions.run_action``.
    Since that function is extremely long (at least on Sep. 2022;
    hopefully the situation gets better with the time), the tests in this
    ``TestCase`` contain plenty of mocks/patches.
    Hopefully, with time and effort, the ``run_action`` function (and others
    in the module) are refactored to make testing easier and more robust.

    A side effect of the mocking approach is a strong dependency on the
    details of the implementation. That can be improved if functions
    are smaller and do a well defined small set of tasks. Another call to
    refactoring...
    If the implementation changes, the mocks can be adjusted to play its
    role.
    """

    @patch("_emerge.actions.profile_check")
    @patch("_emerge.actions.adjust_configs")
    @patch("_emerge.actions.apply_priorities")
    def test_binary_trees_populate_called(self, papply, padjust, profile_ckeck):
        """Ensure that ``binarytree.populate`` API is correctly used.
        The point of this test is to ensure that the ``populate`` method
        is called as expected: since it is the first time that ``populate``
        is called, it must use ``getbinpkg_refresh=True``.
        """
        config = MagicMock()
        config.action = None
        config.opts = {"--quiet": True, "--usepkg": True, "--package-moves": "n"}
        bt = MagicMock()
        tree = {"bintree": bt}
        trees = {"first": tree}
        config.trees = trees

        run_action(config)

        bt.populate.assert_called_once_with(
            getbinpkgs=False, getbinpkg_refresh=True, pretend=False, verbose=False
        )

    def testCreateWorldAtomSlottedWithRepo(self):
        pkg = MagicMock()
        pkg.slot_atom = Atom("dev-libs/foo:1")
        pkg.slot = "1"

        arg_atom = Atom("=dev-libs/foo-1::gentoo", allow_repo=True)

        args_set = MagicMock()
        args_set.findAtomForPackage.return_value = arg_atom

        portdb = MagicMock()
        portdb.porttrees = ["/usr/portage"]
        portdb.repositories.get_name_for_location.return_value = "gentoo"
        portdb.match.side_effect = lambda a: (
            ["dev-libs/foo-1"] if str(a) == "dev-libs/foo" else ["dev-libs/foo-1:1"]
        )
        slot_pkg_str = MagicMock()
        slot_pkg_str.slot = "1"
        portdb._pkg_str.return_value = slot_pkg_str

        vardb = MagicMock()
        vardb.match.return_value = ["dev-libs/foo-1"]

        root_config = MagicMock()
        root_config.trees = {
            "porttree": MagicMock(dbapi=portdb),
            "vartree": MagicMock(dbapi=vardb),
        }
        root_config.sets["selected"].findAtomForPackage.return_value = None
        root_config.sets["system"].findAtomForPackage.return_value = None

        result = create_world_atom(pkg, args_set, root_config, before_install=True)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertIn("::gentoo", result)

    def testGetSystemLibc(self):
        """
        Check that get_libc_version extracts the right version string
        from the provider LIBC_PACKAGE_ATOM for emerge --info and friends.
        """
        settings = MagicMock()

        settings.getvirtuals.return_value = {
            LIBC_PACKAGE_ATOM: [Atom("=sys-libs/musl-1.2.3")]
        }
        settings.__getitem__.return_value = {}

        vardb = fakedbapi(settings)
        vardb.cpv_inject("sys-libs/musl-1.2.3", {"SLOT": "0"})

        self.assertEqual(get_libc_version(vardb), ["musl-1.2.3"])
