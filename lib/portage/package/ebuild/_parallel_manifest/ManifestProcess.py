# Copyright 2012-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools

import portage
from portage import os
from portage.exception import FileNotFound, PermissionDenied, PortagePackageException
from portage.localization import _
from portage.util._async.ForkProcess import ForkProcess


class ManifestProcess(ForkProcess):
    __slots__ = ("cp", "distdir", "fetchlist_dict", "repo_config")

    MODIFIED = 16

    def _start(self):
        self.target = functools.partial(
            self._target,
            self.cp,
            self.distdir,
            self.fetchlist_dict,
            self.repo_config,
        )
        super()._start()

    @staticmethod
    def _target(cp, distdir, fetchlist_dict, repo_config):
        """
        TODO: Make all arguments picklable for the multiprocessing spawn start method.
        """
        mf = repo_config.load_manifest(
            os.path.join(repo_config.location, cp),
            distdir,
            fetchlist_dict=fetchlist_dict,
        )

        try:
            mf.create(assumeDistHashesAlways=True)
        except FileNotFound as e:
            portage.writemsg(
                _("!!! File %s doesn't exist, can't update " "Manifest\n") % e,
                noiselevel=-1,
            )
            return 1

        except PortagePackageException as e:
            portage.writemsg(f"!!! {e}\n", noiselevel=-1)
            return 1

        try:
            modified = mf.write(sign=False)
        except PermissionDenied as e:
            portage.writemsg(
                f"!!! {_('Permission Denied')}: {e}\n",
                noiselevel=-1,
            )
            return 1
        else:
            if modified:
                return ManifestProcess.MODIFIED
            return os.EX_OK
