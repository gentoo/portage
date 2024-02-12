# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <gladkov.alexey@gmail.com>

import os
import os.path
import logging
import zipfile
import shutil
import tempfile
import urllib.request

import portage
from portage.util import writemsg_level
from portage.sync.syncbase import SyncBase


class ZipFile(SyncBase):
    """ZipFile sync module"""

    short_desc = "Perform sync operations on GitHub repositories"

    @staticmethod
    def name():
        return "ZipFile"

    def __init__(self):
        SyncBase.__init__(self, "emerge", ">=sys-apps/portage-2.3")

    def sync(self, **kwargs):
        """Sync the repository"""
        if kwargs:
            self._kwargs(kwargs)

        # initial checkout
        zip_uri = self.repo.sync_uri

        with urllib.request.urlopen(zip_uri) as response:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                shutil.copyfileobj(response, tmp_file)
            zip_file = tmp_file.name

        if not zipfile.is_zipfile(zip_file):
            msg = "!!! file is not a zip archive."
            self.logger(self.xterm_titles, msg)
            writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)

            os.unlink(zip_file)

            return (1, False)

        # Drop previous tree
        shutil.rmtree(self.repo.location)

        with zipfile.ZipFile(zip_file) as archive:
            strip_comp = 0

            for f in archive.namelist():
                f = os.path.normpath(f)
                if os.path.basename(f) == "profiles":
                    strip_comp = f.count("/")
                    break

            for n in archive.infolist():
                p = os.path.normpath(n.filename)

                if os.path.isabs(p):
                    continue

                parts = p.split("/")
                dstpath = os.path.join(self.repo.location, *parts[strip_comp:])

                if n.is_dir():
                    os.makedirs(dstpath, mode=0o755, exist_ok=True)
                    continue

                with archive.open(n) as srcfile:
                    with open(dstpath, "wb") as dstfile:
                        shutil.copyfileobj(srcfile, dstfile)

        os.unlink(zip_file)

        return (os.EX_OK, True)
