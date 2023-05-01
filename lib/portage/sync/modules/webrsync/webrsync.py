"""WebRsync module for portage"""

import logging

import portage
from portage import os
from portage.util import writemsg_level
from portage.output import create_color_func
from portage.sync.syncbase import SyncBase

good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")

try:
    import gemato.openpgp
except ImportError:
    gemato = None


class WebRsync(SyncBase):
    """WebRSync sync class

    This class implements syncing via calls to an external binary, either:
    - emerge-delta-webrsync (if sync-webrsync-delta is set), or
    - emerge-webrsync

    It wraps them and performs PGP verification if sync-webrsync-verify-signature
    is set via gemato.
    """

    short_desc = "Perform sync operations on webrsync based repositories"

    @staticmethod
    def name():
        return "WebRSync"

    def __init__(self):
        SyncBase.__init__(self, "emerge-webrsync", ">=sys-apps/portage-2.3")

    @property
    def has_bin(self):
        if (
            self._bin_command != "emerge-delta-webrsync"
            and self.repo.module_specific_options.get(
                "sync-webrsync-delta", "false"
            ).lower()
            in ("true", "yes")
        ):
            self._bin_command = "emerge-delta-webrsync"
            self.bin_command = portage.process.find_binary(self._bin_command)
            self.bin_pkg = ">=app-portage/emerge-delta-webrsync-3.7.5"

        return super().has_bin

    def sync(self, **kwargs):
        """Sync the repository"""
        if kwargs:
            self._kwargs(kwargs)

        if not self.has_bin:
            return (1, False)

        # filter these out to prevent gpg errors
        for var in ["uid", "gid", "groups"]:
            self.spawn_kwargs.pop(var, None)

        verbose = "--verbose" in self.options["emerge_config"].opts
        quiet = "--quiet" in self.options["emerge_config"].opts
        openpgp_env = None
        try:
            if self.repo.module_specific_options.get(
                "sync-webrsync-verify-signature", "false"
            ).lower() in ("true", "yes"):
                if not self.repo.sync_openpgp_key_path:
                    writemsg_level(
                        "!!! sync-openpgp-key-path is not set\n",
                        level=logging.ERROR,
                        noiselevel=-1,
                    )
                    return (1, False)

                if not os.path.isfile(self.repo.sync_openpgp_key_path):
                    writemsg_level(
                        "!!! sync-openpgp-key-path file not found: %s\n"
                        % self.repo.sync_openpgp_key_path,
                        level=logging.ERROR,
                        noiselevel=-1,
                    )
                    return (1, False)

                if gemato is None:
                    writemsg_level(
                        "!!! Verifying against specified key requires gemato-14.5+ installed\n",
                        level=logging.ERROR,
                        noiselevel=-1,
                    )
                    return (1, False)

                self.spawn_kwargs["env"]["PORTAGE_SYNC_WEBRSYNC_GPG"] = True
                self.spawn_kwargs["env"][
                    "PORTAGE_GPG_KEY"
                ] = self.repo.sync_openpgp_key_path
                self.spawn_kwargs["env"][
                    "PORTAGE_GPG_KEY_SERVER"
                ] = self.repo.sync_openpgp_key_server

            webrsync_cmd = [self.bin_command]
            if verbose:
                webrsync_cmd.append("-v")
            elif quiet:
                webrsync_cmd.append("-q")

            if self.repo.module_specific_options.get(
                "sync-webrsync-keep-snapshots", "false"
            ).lower() in ("true", "yes"):
                webrsync_cmd.append("-k")

            exitcode = portage.process.spawn(webrsync_cmd, **self.spawn_kwargs)
            if exitcode != os.EX_OK:
                msg = f"!!! emerge-webrsync error in {self.repo.location}"
                self.logger(self.xterm_titles, msg)
                writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
                return (exitcode, False)
            return (exitcode, True)
        finally:
            if openpgp_env is not None:
                openpgp_env.close()


class PyWebRsync(SyncBase):
    """PyWebRsync sync class

    TODO: Implement the sync parts from the emerge-webrsync external
          binary to avoid split logic for various components, which
          is how we ended up with bug #597800.
    """

    short_desc = "Perform sync operations on webrsync based repositories"

    @staticmethod
    def name():
        return "WebRSync"

    def __init__(self):
        SyncBase.__init__(self, None, ">=sys-apps/portage-2.3")

    def sync(self, **kwargs):
        """Sync the repository"""
        raise NotImplementedError(
            "Python impl. of webrsync backend is not yet implemented"
        )
