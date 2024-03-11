# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <gladkov.alexey@gmail.com>

doc = """Zipfile plug-in module for portage.
Performs a http download of a portage snapshot and unpacks it to the repo
location."""
__doc__ = doc[:]


import os

from portage.sync.config_checks import CheckSyncConfig


module_spec = {
    "name": "zipfile",
    "description": doc,
    "provides": {
        "zipfile-module": {
            "name": "zipfile",
            "sourcefile": "zipfile",
            "class": "ZipFile",
            "description": doc,
            "functions": ["sync", "retrieve_head"],
            "func_desc": {
                "sync": "Performs an archived http download of the "
                + "repository, then unpacks it.",
                "retrieve_head": "Returns the checksum of the unpacked archive.",
            },
            "validate_config": CheckSyncConfig,
            "module_specific_options": (),
        },
    },
}
