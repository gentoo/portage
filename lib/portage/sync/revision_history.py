# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import json
import os
from typing import Optional

import portage
from portage.locks import lockfile, unlockfile
from portage.repository.config import RepoConfig
from portage.util.path import first_existing

_HISTORY_LIMIT = 25


def get_repo_revision_history(
    eroot: str, repos: Optional[list[RepoConfig]] = None
) -> dict[str, list[str]]:
    """
    Get revision history of synced repos. Returns a dict that maps
    a repo name to list of revisions in descending order by time.
    If a change is detected and the current process has permission
    to update the repo_revisions file, then the file will be updated
    with any newly detected revisions.

    This functions detects revisions which are not yet visible to the
    current process due to the sync-rcu option.

    @param eroot: EROOT to query
    @type eroot: string
    @param repos: list of RepoConfig instances to check for new revisions
    @type repos: list
    @rtype: dict
    @return: mapping of repo name to list of revisions in descending
             order by time
    """
    items = []
    for repo in repos or ():
        if repo.volatile:
            items.append((repo, None))
            continue
        if repo.sync_type:
            try:
                sync_mod = portage.sync.module_controller.get_class(repo.sync_type)
            except portage.exception.PortageException:
                continue
        else:
            continue
        repo_location_orig = repo.location
        try:
            if repo.user_location is not None:
                # Temporarily override sync-rcu behavior which pins the
                # location to a previous snapshot, since we want the
                # latest available revision here.
                repo.location = repo.user_location
            status, repo_revision = sync_mod().retrieve_head(options={"repo": repo})
        except NotImplementedError:
            repo_revision = None
        else:
            repo_revision = repo_revision.strip() if status == os.EX_OK else None
        finally:
            repo.location = repo_location_orig

        if repo_revision is not None:
            items.append((repo, repo_revision))

    return _maybe_update_revisions(eroot, items)


def _update_revisions(repo_revisions, items):
    modified = False
    for repo, repo_revision in items:
        if repo.volatile:
            # For volatile repos the revisions may be unordered,
            # which makes them unusable here where revisions are
            # intended to be ordered, so discard them.
            rev_list = repo_revisions.pop(repo.name, None)
            if rev_list:
                modified = True
            continue

        rev_list = repo_revisions.setdefault(repo.name, [])
        if not rev_list or rev_list[0] != repo_revision:
            rev_list.insert(0, repo_revision)
            del rev_list[_HISTORY_LIMIT:]
            modified = True
    return modified


def _maybe_update_revisions(eroot, items):
    repo_revisions_file = os.path.join(eroot, portage.const.REPO_REVISIONS)
    repo_revisions_lock = None
    try:
        previous_revisions = None
        try:
            with open(repo_revisions_file, encoding="utf8") as f:
                if os.fstat(f.fileno()).st_size:
                    previous_revisions = json.load(f)
        except FileNotFoundError:
            pass

        repo_revisions = {} if previous_revisions is None else previous_revisions.copy()
        modified = _update_revisions(repo_revisions, items)

        # If modified then do over with lock if permissions allow.
        if modified and os.access(
            first_existing(os.path.dirname(repo_revisions_file)), os.W_OK
        ):
            # This is a bit redundant since the config._init_dirs method
            # is supposed to create PRIVATE_PATH with these permissions.
            portage.util.ensure_dirs(
                os.path.dirname(repo_revisions_file),
                gid=portage.data.portage_gid,
                mode=0o2750,
                mask=0o2,
            )
            repo_revisions_lock = lockfile(repo_revisions_file)
            previous_revisions = None
            with open(repo_revisions_file, encoding="utf8") as f:
                if os.fstat(f.fileno()).st_size:
                    previous_revisions = json.load(f)
            repo_revisions = (
                {} if previous_revisions is None else previous_revisions.copy()
            )
            _update_revisions(repo_revisions, items)
            f = portage.util.atomic_ofstream(repo_revisions_file)
            json.dump(repo_revisions, f, ensure_ascii=False, sort_keys=True)
            f.close()
    finally:
        if repo_revisions_lock is not None:
            unlockfile(repo_revisions_lock)

    return repo_revisions
