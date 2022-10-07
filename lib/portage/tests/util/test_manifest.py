# Copyright 2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import tempfile

from pathlib import Path
from portage import Manifest
from portage.tests import TestCase


class ManifestTestCase(TestCase):
    def test_simple_addFile(self):
        tempdir = Path(tempfile.mkdtemp()) / "app-portage" / "diffball"
        manifest = Manifest(str(tempdir), required_hashes=["SHA512", "BLAKE2B"])

        (tempdir / "files").mkdir(parents=True)
        (tempdir / "files" / "test.patch").write_text(
            "Fix the diffball foobar functionality.\n"
        )

        # Nothing should be in the Manifest yet
        with self.assertRaises(KeyError):
            manifest.getFileData("AUX", "test.patch", "SHA512")

        manifest.addFile("AUX", "files/test.patch")

        self.assertEqual(len(manifest.fhashdict["AUX"].keys()), 1)
        self.assertEqual(
            manifest.getFileData("AUX", "test.patch", "SHA512"),
            "e30d069dcf284cbcb2d5685f03ca362469026b469dec4f8655d0c9a2bf317f5d9f68f61855ea403f4959bc0b9c003ae824fb9d6ab2472a739950623523af9da9",
        )
