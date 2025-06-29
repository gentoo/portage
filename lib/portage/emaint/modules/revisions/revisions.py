# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import json
import os

import portage


class PurgeRevisions:
    short_desc = "Purge repo_revisions history file."

    @staticmethod
    def name():
        return "revisions"

    def __init__(self, settings=None):
        """Class init function

        @param settings: optional portage.config instance to get EROOT from.
        """
        self._settings = settings

    @property
    def settings(self):
        return self._settings or portage.settings

    def purgeallrepos(self, **kwargs):
        """Purge revisions for all repos"""
        repo_revisions_file = os.path.join(
            self.settings["EROOT"], portage.const.REPO_REVISIONS
        )
        msgs = []
        try:
            os.stat(repo_revisions_file)
        except FileNotFoundError:
            pass
        except OSError as e:
            msgs.append(f"{repo_revisions_file}: {e}")
        else:
            repo_revisions_lock = None
            try:
                repo_revisions_lock = portage.locks.lockfile(repo_revisions_file)
                os.unlink(repo_revisions_file)
            except FileNotFoundError:
                pass
            except OSError as e:
                msgs.append(f"{repo_revisions_file}: {e}")
            finally:
                if repo_revisions_lock is not None:
                    portage.locks.unlockfile(repo_revisions_lock)
        return (not msgs, msgs)

    def purgerepos(self, **kwargs):
        """Purge revisions for specified repos"""
        options = kwargs.get("options", None)
        if options:
            repo_names = options.get("purgerepos", "")
        if isinstance(repo_names, str):
            repo_names = repo_names.split()

        repo_revisions_file = os.path.join(
            self.settings["EROOT"], portage.const.REPO_REVISIONS
        )
        msgs = []
        try:
            os.stat(repo_revisions_file)
        except FileNotFoundError:
            pass
        except OSError as e:
            msgs.append(f"{repo_revisions_file}: {e}")
        else:
            repo_revisions_lock = None
            try:
                repo_revisions_lock = portage.locks.lockfile(repo_revisions_file)
                with open(repo_revisions_file, encoding="utf8") as f:
                    if os.fstat(f.fileno()).st_size:
                        previous_revisions = json.load(f)
                repo_revisions = (
                    {} if previous_revisions is None else previous_revisions.copy()
                )
                for repo_name in repo_names:
                    repo_revisions.pop(repo_name, None)
                if not repo_revisions:
                    os.unlink(repo_revisions_file)
                elif repo_revisions != previous_revisions:
                    f = portage.util.atomic_ofstream(repo_revisions_file)
                    json.dump(repo_revisions, f, ensure_ascii=False, sort_keys=True)
                    f.close()
            except OSError as e:
                msgs.append(f"{repo_revisions_file}: {e}")
            finally:
                if repo_revisions_lock is not None:
                    portage.locks.unlockfile(repo_revisions_lock)
        return (not msgs, msgs)
