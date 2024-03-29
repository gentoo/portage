# testCommandOututSet.py -- Portage Unit Testing Functionality
# Copyright 2007-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.process import find_binary
from portage.tests import TestCase, test_cps
from portage._sets.shell import CommandOutputSet


class CommandOutputSetTestCase(TestCase):
    """Simple Test Case for CommandOutputSet"""

    def setUp(self):
        super().setUp()

    def tearDown(self):
        pass

    def testCommand(self):
        params = set(test_cps)
        command = find_binary("bash")
        command += " -c '"
        for a in params:
            command += f' echo -e "{a}" ; '
        command += "'"
        s = CommandOutputSet(command)
        atoms = s.getAtoms()
        self.assertEqual(atoms, params)
