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
from portage.util import writemsg_level, writemsg_stdout
from portage.sync.syncbase import SyncBase


class ZipFile(SyncBase):
    """ZipFile sync module"""

    short_desc = "Perform sync operations on GitHub repositories"

    @staticmethod
    def name():
        return "ZipFile"

    def __init__(self):
        SyncBase.__init__(self, "emerge", ">=sys-apps/portage-2.3")

    def retrieve_head(self, **kwargs):
        """Get information about the checksum of the unpacked archive"""
        if kwargs:
            self._kwargs(kwargs)
        info = portage.grabdict(os.path.join(self.repo.location, ".info"))
        if "etag" in info:
            return (os.EX_OK, info["etag"][0])
        return (1, False)

    def sync(self, **kwargs):
        """Sync the repository"""
        if kwargs:
            self._kwargs(kwargs)

        req = urllib.request.Request(url=self.repo.sync_uri)

        info = portage.grabdict(os.path.join(self.repo.location, ".info"))
        if "etag" in info:
            req.add_header("If-None-Match", info["etag"][0])

        try:
            with urllib.request.urlopen(req) as response:
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    shutil.copyfileobj(response, tmp_file)

                zip_file = tmp_file.name
                etag = response.headers.get("etag")

        except urllib.error.HTTPError as resp:
            if resp.code == 304:
                writemsg_stdout(">>> The repository has not changed.\n", noiselevel=-1)
                return (os.EX_OK, False)

            writemsg_level(
                f"!!! Unable to obtain zip archive: {resp}\n",
                noiselevel=-1,
                level=logging.ERROR,
            )
            return (1, False)

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

        with open(os.path.join(self.repo.location, ".info"), "w") as infofile:
            if etag:
                infofile.write(f"etag {etag}\n")

        os.unlink(zip_file)

        return (os.EX_OK, True)
