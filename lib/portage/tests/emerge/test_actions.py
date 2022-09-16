# Copyright 2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from unittest.mock import MagicMock, patch

from _emerge.actions import run_action
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

        bt.populate.assert_called_once_with(getbinpkgs=False, getbinpkg_refresh=True)
