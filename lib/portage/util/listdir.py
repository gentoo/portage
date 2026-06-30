# Copyright 2010-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["cacheddir", "listdir"]

import os

from portage.const import VCS_DIRS
from portage.exception import DirectoryNotFound, PermissionDenied, PortageException
from portage.util import normalize_path


def cacheddir(my_original_path, ignorecvs, ignorelist, followSymlinks=True):
    fpaths = []
    ftype = []
    mypath = normalize_path(my_original_path)

    try:
        with os.scandir(mypath) as it:
            for entry in it:
                fpaths.append(entry.name)

                try:
                    if entry.is_file(follow_symlinks=followSymlinks):
                        ftype.append(0)
                    elif entry.is_dir(follow_symlinks=followSymlinks):
                        ftype.append(1)
                    elif entry.is_symlink():
                        ftype.append(2)
                    else:
                        ftype.append(3)
                except OSError:
                    ftype.append(3)
    except NotADirectoryError:
        raise DirectoryNotFound(mypath)
    except OSError as e:
        if e.errno == PermissionDenied.errno:
            raise PermissionDenied(mypath)
        return fpaths, ftype
    except PortageException:
        return fpaths, ftype

    if ignorelist or ignorecvs:
        ret_list = []
        ret_ftype = []
        for file_path, file_type in zip(fpaths, ftype):
            if file_path in ignorelist:
                pass
            elif ignorecvs:
                if file_path[:2] != ".#" and not (
                    file_type == 1 and file_path in VCS_DIRS
                ):
                    ret_list.append(file_path)
                    ret_ftype.append(file_type)
    else:
        ret_list = fpaths
        ret_ftype = ftype

    return ret_list, ret_ftype


def listdir(
    mypath,
    recursive=False,
    filesonly=False,
    ignorecvs=False,
    ignorelist=[],
    followSymlinks=True,
    dirsonly=False,
):
    """
    Portage-specific implementation of os.listdir

    @param mypath: Path whose contents you wish to list
    @type mypath: String
    @param recursive: Recursively scan directories contained within mypath
    @type recursive: Boolean
    @param filesonly; Only return files, not more directories
    @type filesonly: Boolean
    @param ignorecvs: Ignore VCS directories
    @type ignorecvs: Boolean
    @param ignorelist: List of filenames/directories to exclude
    @type ignorelist: List
    @param followSymlinks: Follow Symlink'd files and directories
    @type followSymlinks: Boolean
    @param dirsonly: Only return directories.
    @type dirsonly: Boolean
    @rtype: List
    @return: A list of files and directories (or just files or just directories) or an empty list.
    """

    fpaths, ftype = cacheddir(mypath, ignorecvs, ignorelist, followSymlinks)

    if fpaths is None:
        fpaths = []
    if ftype is None:
        ftype = []

    if not (filesonly or dirsonly or recursive):
        return fpaths

    if recursive:
        stack = list(zip(fpaths, ftype))
        fpaths = []
        ftype = []
        while stack:
            file_path, file_type = stack.pop()
            fpaths.append(file_path)
            ftype.append(file_type)
            if file_type == 1:
                subdir_list, subdir_types = cacheddir(
                    os.path.join(mypath, file_path),
                    ignorecvs,
                    ignorelist,
                    followSymlinks,
                )
                stack.extend(
                    (os.path.join(file_path, x), x_type)
                    for x, x_type in zip(subdir_list, subdir_types)
                )

    if filesonly:
        fpaths = [x for x, x_type in zip(fpaths, ftype) if x_type == 0]

    elif dirsonly:
        fpaths = [x for x, x_type in zip(fpaths, ftype) if x_type == 1]

    return fpaths
