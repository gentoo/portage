# Copyright 2013-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools

from portage.checksum import perform_multiple_checksums
from portage.util._async.AsyncFunction import AsyncFunction


class FileDigester(AsyncFunction):
    """
    Asynchronously generate file digests. Pass in file_path and
    hash_names, and after successful execution, the digests
    attribute will be a dict containing all of the requested
    digests.
    """

    __slots__ = (
        "file_path",
        "hash_names",
    )

    def _start(self):
        self.target = functools.partial(
            perform_multiple_checksums, self.file_path, hashes=self.hash_names
        )
        super()._start()

    @property
    def digests(self):
        return self.result
