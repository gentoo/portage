# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Manage the VDB consolidated metadata file."""
__doc__ = doc


module_spec = {
    "name": "vdb",
    "description": doc,
    "provides": {
        "module1": {
            "name": "vdb",
            "sourcefile": "vdb",
            "class": "VdbMetadata",
            "description": doc,
            "functions": ["check", "fix", "remove"],
            "func_desc": {
                "delete_individual_files": {
                    "long": "--delete-individual-files",
                    "help": "(fix only): also remove per-field files after writing "
                    "the metadata file. WARNING: breaks tools that read "
                    "individual VDB files directly (portage-utils, pkgcore, "
                    "shell scripts). Only use when all VDB consumers support the "
                    "consolidated format.",
                    "action": "store_true",
                    "func": "fix",
                },
                "remove": {
                    "short": "-R",
                    "long": "--remove",
                    "help": "Undo --fix: restore any per-field file that only "
                    "the metadata file still holds, then remove the metadata "
                    "files",
                    "status": "Removing VDB metadata files for %s",
                    "action": "store_true",
                    "func": "remove",
                },
            },
        }
    },
}
