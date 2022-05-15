# Copyright 2014-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections

from portage.versions import _pkg_str


pkg_desc_index_node = collections.namedtuple(
    "pkg_desc_index_node", ["cp", "cpv_list", "desc"]
)


class pkg_node(str):
    """
    A minimal package node class. For performance reasons, inputs
    are not validated.
    """

    def __init__(self, cp, version, repo=None):
        self.__dict__["cp"] = cp
        self.__dict__["repo"] = repo
        self.__dict__["version"] = version
        self.__dict__["build_time"] = None

    def __new__(cls, cp, version, repo=None):
        return str.__new__(cls, f"{cp}-{version}")

    def __setattr__(self, name, value):
        raise AttributeError(
            "pkg_node instances are immutable", self.__class__, name, value
        )


def pkg_desc_index_line_format(cp, pkgs, desc):
    return f"{cp} {' '.join(_pkg_str(cpv).version for cpv in pkgs)}: {desc}\n"


def pkg_desc_index_line_read(line, repo=None):
    try:
        pkgs, desc = line.split(":", 1)
        cp, pkgs = pkgs.split(" ", 1)
    except ValueError:
        return None

    desc = desc.strip()
    pkg_nodes = tuple(pkg_node(cp, ver, repo) for ver in pkgs.split())
    return pkg_desc_index_node(cp, pkg_nodes, desc)
