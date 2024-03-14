# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Purge repo_revisions history file."""
__doc__ = doc


module_spec = {
    "name": "revisions",
    "description": doc,
    "provides": {
        "purgerevisions": {
            "name": "revisions",
            "sourcefile": "revisions",
            "class": "PurgeRevisions",
            "description": "Purge repo_revisions history",
            "functions": ["purgeallrepos", "purgerepos"],
            "func_desc": {
                "repo": {
                    "long": "--purgerepos",
                    "help": "(revisions module only): --purgerepos  Purge revisions for the specified repo(s)",
                    "status": "Purging %s",
                    "action": "store",
                    "func": "purgerepos",
                },
                "allrepos": {
                    "long": "--purgeallrepos",
                    "help": "(revisions module only): --purgeallrepos  Purge revisions for all repos",
                    "status": "Purging %s",
                    "action": "store_true",
                    "func": "purgeallrepos",
                },
            },
        },
    },
}
