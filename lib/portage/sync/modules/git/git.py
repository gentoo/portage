# Copyright 2005-2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import re
import subprocess

from typing import Tuple

import portage
from portage import os
from portage.util import writemsg_level, shlex_split
from portage.util.futures import asyncio
from portage.output import create_color_func, EOutput

good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.sync.syncbase import NewBase

try:
    from gemato.exceptions import GematoException
    import gemato.openpgp
except ImportError:
    gemato = None


class GitSync(NewBase):
    """Git sync class"""

    short_desc = "Perform sync operations on git based repositories"

    @staticmethod
    def name():
        return "GitSync"

    def __init__(self):
        NewBase.__init__(self, "git", portage.const.GIT_PACKAGE_ATOM)

    def exists(self, **kwargs) -> bool:
        """Tests whether the repo actually exists"""
        return os.path.exists(os.path.join(self.repo.location, ".git"))

    def new(self, **kwargs) -> Tuple[int, bool]:
        """Do the initial clone of the repository"""
        if kwargs:
            self._kwargs(kwargs)
        if not self.has_bin:
            return (1, False)
        try:
            if not os.path.exists(self.repo.location):
                os.makedirs(self.repo.location)
                self.logger(
                    self.xterm_titles, f"Created new directory {self.repo.location}"
                )
        except OSError:
            return (1, False)

        sync_uri = self.repo.sync_uri
        if sync_uri.startswith("file://"):
            sync_uri = sync_uri[7:]

        git_cmd_opts = ""
        if self.repo.module_specific_options.get("sync-git-env"):
            shlexed_env = shlex_split(self.repo.module_specific_options["sync-git-env"])
            env = {
                k: v
                for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
                if k
            }
            self.spawn_kwargs["env"].update(env)

        if self.repo.module_specific_options.get("sync-git-clone-env"):
            shlexed_env = shlex_split(
                self.repo.module_specific_options["sync-git-clone-env"]
            )
            clone_env = {
                k: v
                for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
                if k
            }
            self.spawn_kwargs["env"].update(clone_env)

        if self.settings.get("PORTAGE_QUIET") == "1":
            git_cmd_opts += " --quiet"
        if self.repo.clone_depth is not None:
            if self.repo.clone_depth != 0:
                git_cmd_opts += " --depth %d" % self.repo.clone_depth
        else:
            # default
            git_cmd_opts += " --depth 1"

        if self.repo.module_specific_options.get("sync-git-clone-extra-opts"):
            git_cmd_opts += (
                f" {self.repo.module_specific_options['sync-git-clone-extra-opts']}"
            )
        git_cmd = "{} clone{} {} .".format(
            self.bin_command,
            git_cmd_opts,
            portage._shell_quote(sync_uri),
        )
        writemsg_level(git_cmd + "\n")

        exitcode = portage.process.spawn_bash(
            f"cd {portage._shell_quote(self.repo.location)} ; exec {git_cmd}",
            **self.spawn_kwargs,
        )
        if exitcode != os.EX_OK:
            msg = f"!!! git clone error in {self.repo.location}"
            self.logger(self.xterm_titles, msg)
            writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
            return (exitcode, False)

        self.add_safe_directory()

        if not self.verify_head():
            return (1, False)

        return (os.EX_OK, True)

    def _gen_ceiling_string(self, path: str) -> str:
        """
        Iteratively generate a colon delimited string of all of the
        given path's parents, for use with GIT_CEILING_DIRECTORIES
        """
        directories = []

        while True:
            if path == "/":
                break
            path = os.path.dirname(path)
            directories.append(path)

        return ":".join(directories)

    def update(self) -> Tuple[int, bool]:
        """Update existing git repository, and ignore the syncuri. We are
        going to trust the user and assume that the user is in the branch
        that he/she wants updated. We'll let the user manage branches with
        git directly.
        """
        if not self.has_bin:
            return (1, False)
        git_cmd_opts = ""
        quiet = self.settings.get("PORTAGE_QUIET") == "1"

        # We don't want to operate with a .git outside of the given
        # repo in any circumstances.
        self.spawn_kwargs["env"].update(
            {"GIT_CEILING_DIRECTORIES": self._gen_ceiling_string(self.repo.location)}
        )

        if self.repo.module_specific_options.get("sync-git-env"):
            shlexed_env = shlex_split(self.repo.module_specific_options["sync-git-env"])
            env = {
                k: v
                for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
                if k
            }
            self.spawn_kwargs["env"].update(env)

        if self.repo.module_specific_options.get("sync-git-pull-env"):
            shlexed_env = shlex_split(
                self.repo.module_specific_options["sync-git-pull-env"]
            )
            pull_env = {
                k: v
                for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
                if k
            }
            self.spawn_kwargs["env"].update(pull_env)

        if quiet:
            git_cmd_opts += " --quiet"

        # The logic here is a bit delicate. We need to balance two things:
        # 1. Having a robust sync mechanism which works unattended.
        # 2. Allowing users to have the flexibility they might expect when using
        # a git repository in repos.conf for syncing.
        #
        # For sync-type=git repositories, we've seen a problem in the wild
        # where shallow clones end up "breaking themselves" especially when
        # the origin is behing a CDN. 'git pull' might return state X,
        # but on a subsequent pull, return state X-1. git will then (sometimes)
        # leave orphaned untracked files in the repository. On a subsequent pull,
        # when state >= X is returned where those files exist in the origin,
        # git then refuses to write over them and aborts to avoid clobbering
        # local work.
        #
        # To mitigate this, Portage will aggressively clobber any changes
        # in the local directory, as its priority is to keep syncing working,
        # by running 'git clean' and 'git reset --hard'.
        #
        # Portage performs this clobbering if:
        # 1. sync-type=git
        # 2.
        #   - volatile=no (explicitly set to no), OR
        #   - volatile is unset AND the repository owner is either root or portage
        # 3. Portage is syncing the respository (rather than e.g. auto-sync=no
        # and never running 'emaint sync -r foo')
        #
        # Portage will not clobber if:
        # 1. volatile=yes (explicitly set in the config), OR
        # 2. volatile is unset and the repository owner is neither root nor
        #    portage.
        #
        # 'volatile' refers to whether the repository is volatile and may
        # only be safely changed by Portage itself, i.e. whether Portage
        # should expect the user to change it or not.
        #
        # - volatile=yes:
        # The repository is volatile and may be changed at any time by the user.
        # Portage will not perform destructive operations on the repository.
        # - volatile=no
        # The repository is not volatile. Only Portage may modify the
        # repository. User changes may be lost.
        # Portage may perform destructive operations on the repository
        # to keep sync working.
        #
        # References:
        # bug #887025
        # bug #824782
        # https://archives.gentoo.org/gentoo-dev/message/f58a97027252458ad0a44090a2602897

        # Default: Perform shallow updates (but only if the target is
        # already a shallow repository).
        sync_depth = 1
        if self.repo.sync_depth is not None:
            sync_depth = self.repo.sync_depth
        else:
            if self.repo.volatile:
                # If sync-depth is not explicitly set by the user,
                # then check if the target repository is already a
                # shallow one. And do not perform a shallow update if
                # the target repository is not shallow.
                is_shallow_cmd = ["git", "rev-parse", "--is-shallow-repository"]
                is_shallow_res = portage._unicode_decode(
                    subprocess.check_output(
                        is_shallow_cmd,
                        cwd=portage._unicode_encode(self.repo.location),
                    )
                ).rstrip("\n")
                if is_shallow_res == "false":
                    sync_depth = 0
            else:
                # If the repository is marked as non-volatile, we assume
                # it's fine to Portage to do what it wishes to it.
                sync_depth = 1

        shallow = False
        if sync_depth > 0:
            git_cmd_opts += f" --depth {sync_depth}"
            shallow = True

        if self.repo.module_specific_options.get("sync-git-pull-extra-opts"):
            git_cmd_opts += (
                f" {self.repo.module_specific_options['sync-git-pull-extra-opts']}"
            )

        self.add_safe_directory()

        try:
            remote_branch = portage._unicode_decode(
                subprocess.check_output(
                    [
                        self.bin_command,
                        "rev-parse",
                        "--abbrev-ref",
                        "--symbolic-full-name",
                        "@{upstream}",
                    ],
                    cwd=portage._unicode_encode(self.repo.location),
                )
            ).rstrip("\n")
        except subprocess.CalledProcessError as e:
            msg = f"!!! git rev-parse error in {self.repo.location}"
            self.logger(self.xterm_titles, msg)
            writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
            return (e.returncode, False)

        if shallow:
            # For shallow fetch, unreachable objects may need to be pruned
            # manually, in order to prevent automatic git gc calls from
            # eventually failing (see bug 599008).
            gc_cmd = ["git", "-c", "gc.autodetach=false", "gc", "--auto"]
            if quiet:
                gc_cmd.append("--quiet")
            exitcode = portage.process.spawn(
                gc_cmd,
                cwd=portage._unicode_encode(self.repo.location),
                **self.spawn_kwargs,
            )
            if exitcode != os.EX_OK:
                msg = f"!!! git gc error in {self.repo.location}"
                self.logger(self.xterm_titles, msg)
                writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
                return (exitcode, False)

        git_cmd = "{} fetch {}{}".format(
            self.bin_command,
            remote_branch.partition("/")[0],
            git_cmd_opts,
        )

        if not quiet:
            writemsg_level(git_cmd + "\n")

        rev_cmd = [self.bin_command, "rev-list", "--max-count=1", "HEAD"]
        previous_rev = subprocess.check_output(
            rev_cmd, cwd=portage._unicode_encode(self.repo.location)
        )

        exitcode = portage.process.spawn_bash(
            f"cd {portage._shell_quote(self.repo.location)} ; exec {git_cmd}",
            **self.spawn_kwargs,
        )

        if exitcode != os.EX_OK:
            msg = f"!!! git fetch error in {self.repo.location}"
            self.logger(self.xterm_titles, msg)
            writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
            return (exitcode, False)

        if not self.verify_head(revision=f"refs/remotes/{remote_branch}"):
            return (1, False)

        if not self.repo.volatile:
            # Clean up the repo before trying to sync to upstream.
            # - Only done for volatile=false repositories to avoid losing
            # data.
            # - This is needed to avoid orphaned files preventing further syncs
            # on shallow clones.
            clean_cmd = [self.bin_command, "clean", "--force", "-d", "-x"]

            if quiet:
                clean_cmd.append("--quiet")

            exitcode = portage.process.spawn(
                clean_cmd,
                cwd=portage._unicode_encode(self.repo.location),
                **self.spawn_kwargs,
            )

            if exitcode != os.EX_OK:
                msg = f"!!! git clean error in {self.repo.location}"
                self.logger(self.xterm_titles, msg)
                writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
                return (exitcode, False)

        # `git diff --quiet` returns 0 on a clean tree and 1 otherwise
        is_clean = (
            portage.process.spawn(
                f"{self.bin_command} diff --quiet",
                cwd=portage._unicode_encode(self.repo.location),
                **self.spawn_kwargs,
            )
            == 0
        )

        if not is_clean and not self.repo.volatile:
            # If the repo isn't clean, clobber any changes for parity
            # with rsync. Only do this for non-volatile repositories.
            merge_cmd = [self.bin_command, "reset", "--hard"]
        elif shallow:
            # Since the default merge strategy typically fails when
            # the depth is not unlimited, `git reset --merge`.
            merge_cmd = [self.bin_command, "reset", "--merge"]
        else:
            merge_cmd = [self.bin_command, "merge"]

        merge_cmd.append(f"refs/remotes/{remote_branch}")
        if quiet:
            merge_cmd.append("--quiet")

        if not quiet:
            writemsg_level(" ".join(merge_cmd) + "\n")

        exitcode = portage.process.spawn(
            merge_cmd,
            cwd=portage._unicode_encode(self.repo.location),
            **self.spawn_kwargs,
        )

        if exitcode != os.EX_OK:
            if not self.repo.volatile:
                # HACK - sometimes merging results in a tree diverged from
                # upstream, so try to hack around it
                # https://stackoverflow.com/questions/41075972/how-to-update-a-git-shallow-clone/41081908#41081908
                exitcode = portage.process.spawn(
                    f"{self.bin_command} reset --hard refs/remotes/{remote_branch}",
                    cwd=portage._unicode_encode(self.repo.location),
                    **self.spawn_kwargs,
                )

            if exitcode != os.EX_OK:
                msg = f"!!! git merge error in {self.repo.location}"
                self.logger(self.xterm_titles, msg)
                writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
                return (exitcode, False)

        current_rev = subprocess.check_output(
            rev_cmd, cwd=portage._unicode_encode(self.repo.location)
        )

        return (os.EX_OK, current_rev != previous_rev)

    def verify_head(self, revision="-1") -> bool:
        if self.repo.module_specific_options.get(
            "sync-git-verify-commit-signature", "false"
        ).lower() not in ("true", "yes"):
            return True

        if self.repo.sync_openpgp_key_path is not None and gemato is None:
            writemsg_level(
                "!!! Verifying against specified key requires gemato-14.5+ installed\n",
                level=logging.ERROR,
                noiselevel=-1,
            )
            return False

        openpgp_env = self._get_openpgp_env(self.repo.sync_openpgp_key_path)

        try:
            out = EOutput()
            env = None
            if openpgp_env is not None and self.repo.sync_openpgp_key_path is not None:
                try:
                    out.einfo(f"Using keys from {self.repo.sync_openpgp_key_path}")
                    with open(self.repo.sync_openpgp_key_path, "rb") as f:
                        openpgp_env.import_key(f)
                    self._refresh_keys(openpgp_env)
                except (GematoException, asyncio.TimeoutError) as e:
                    writemsg_level(
                        f"!!! Verification impossible due to keyring problem:\n{e}\n",
                        level=logging.ERROR,
                        noiselevel=-1,
                    )
                    return False

                env = os.environ.copy()
                env["GNUPGHOME"] = openpgp_env.home

            rev_cmd = [self.bin_command, "log", "-n1", "--pretty=format:%G?", revision]
            try:
                status = portage._unicode_decode(
                    subprocess.check_output(
                        rev_cmd,
                        cwd=portage._unicode_encode(self.repo.location),
                        env=env,
                    )
                ).strip()
            except subprocess.CalledProcessError:
                return False

            if status == "G":  # good signature is good
                out.einfo("Trusted signature found on top commit")
                return True
            if status == "U":  # untrusted
                out.ewarn("Top commit signature is valid but not trusted")
                return True
            if status == "B":
                expl = "bad signature"
            elif status == "X":
                expl = "expired signature"
            elif status == "Y":
                expl = "expired key"
            elif status == "R":
                expl = "revoked key"
            elif status == "E":
                expl = "unable to verify signature (missing key?)"
            elif status == "N":
                expl = "no signature"
            else:
                expl = "unknown issue"
            out.eerror(f"No valid signature found: {expl}")
            return False
        finally:
            if openpgp_env is not None:
                openpgp_env.close()

    def retrieve_head(self, **kwargs) -> Tuple[int, bool]:
        """Get information about the head commit"""
        if kwargs:
            self._kwargs(kwargs)
        if self.bin_command is None:
            # return quietly so that we don't pollute emerge --info output
            return (1, False)
        rev_cmd = [self.bin_command, "rev-list", "--max-count=1", "HEAD"]
        try:
            ret = (
                os.EX_OK,
                portage._unicode_decode(
                    subprocess.check_output(
                        rev_cmd, cwd=portage._unicode_encode(self.repo.location)
                    )
                ),
            )
        except subprocess.CalledProcessError:
            ret = (1, False)
        return ret

    def add_safe_directory(self) -> bool:
        # Add safe.directory to system gitconfig if not already configured.
        # Workaround for bug #838271 and bug #838223.
        location_escaped = re.escape(self.repo.location)
        result = subprocess.run(
            [
                self.bin_command,
                "config",
                "--get",
                "safe.directory",
                f"^{location_escaped}$",
            ],
            stdout=subprocess.DEVNULL,
        )
        if result.returncode == 1:
            result = subprocess.run(
                [
                    self.bin_command,
                    "config",
                    "--system",
                    "--add",
                    "safe.directory",
                    self.repo.location,
                ],
                stdout=subprocess.DEVNULL,
            )
        return result.returncode == 0
