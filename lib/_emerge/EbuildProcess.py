# Copyright 1999-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess


class EbuildProcess(AbstractEbuildProcess):
    __slots__ = ("actionmap",)

    def _spawn(self, args, **kwargs):
        from portage.package.ebuild.doebuild import _doebuild_spawn, _spawn_actionmap

        actionmap = self.actionmap
        if actionmap is None:
            actionmap = _spawn_actionmap(self.settings)

        if self._dummy_pipe_fd is not None:
            self.settings["PORTAGE_PIPE_FD"] = str(self._dummy_pipe_fd)

        try:
            return _doebuild_spawn(
                self.phase, self.settings, actionmap=actionmap, **kwargs
            )
        finally:
            self.settings.pop("PORTAGE_PIPE_FD", None)
