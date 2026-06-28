# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import subprocess

import os
from portage._sets.base import PackageSet
from portage._sets import SetConfigError

__all__ = ["CommandOutputSet"]


class CommandOutputSet(PackageSet):
    """This class creates a PackageSet from the output of a shell command.
    The shell command should produce one atom per line, that is:

    >>> atom1
        atom2
        ...
        atomN

    Args:
      name: A string that identifies the set.
      command: A string or sequence identifying the command to run
      (see the subprocess.Popen documentation for the format)
    """

    _operations = ["merge", "unmerge"]

    def __init__(self, command):
        super().__init__()
        self._command = command
        self.description = f"Package set generated from output of '{self._command}'"

    def load(self):
        pipe = subprocess.Popen(
            self._command,
            stdout=subprocess.PIPE,
            shell=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = pipe.communicate()
        if pipe.wait() == os.EX_OK:
            self._setAtoms(stdout.splitlines())

    def singleBuilder(self, options, settings, trees):
        if "command" not in options:
            raise SetConfigError("no command specified")
        return CommandOutputSet(options["command"])

    singleBuilder = classmethod(singleBuilder)
