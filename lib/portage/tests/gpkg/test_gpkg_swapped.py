# Copyright 2026 Gentoo Authors
# Portage Unit Testing Functionality

import os
import shutil
import tempfile

from portage.exception import DigestException
from portage.gpkg import gpkg
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class test_gpkg_swapped_file_case(TestCase):
    def test_gpkg_extraction_hashes_whole_image(self):
        # The hash covers the member only if every byte of it is read.
        # BINPKG_COMPRESS="none" is the path with no decompressor thread.
        for compression in ("none", "gzip"):
            with self.subTest(compression=compression):
                playground = ResolverPlayground(
                    user_config={"make.conf": (f'BINPKG_COMPRESS="{compression}"',)}
                )
                tmpdir = tempfile.mkdtemp()
                try:
                    image = os.path.join(tmpdir, "image", "usr", "bin")
                    os.makedirs(image)
                    for i in range(64):
                        with open(os.path.join(image, f"test{i}"), "wb") as f:
                            f.write(os.urandom(9999))

                    binpkg = os.path.join(tmpdir, "test.gpkg.tar")
                    gpkg(playground.settings, "test", binpkg).compress(
                        os.path.join(tmpdir, "image"), {"meta": "test"}
                    )

                    dest_dir = os.path.join(tmpdir, "dest")
                    gpkg(playground.settings, "test", binpkg).decompress(dest_dir)
                    self.assertEqual(
                        sorted(os.listdir(os.path.join(dest_dir, "usr", "bin"))),
                        sorted(os.listdir(image)),
                    )
                finally:
                    shutil.rmtree(tmpdir)
                    playground.cleanup()

    def test_gpkg_swapped_after_verification(self):
        playground = ResolverPlayground(
            user_config={"make.conf": ('BINPKG_COMPRESS="none"',)}
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings

            for name, content in (
                ("original", b"original" * 1024),
                ("replacement", b"replacement" * 1024),
            ):
                src = os.path.join(tmpdir, name, "usr", "bin")
                os.makedirs(src)
                with open(os.path.join(src, "test"), "wb") as f:
                    f.write(content)
                pkg = gpkg(settings, "test", os.path.join(tmpdir, f"{name}.gpkg.tar"))
                pkg.compress(os.path.join(tmpdir, name), {"meta": "test"})

            binpkg = os.path.join(tmpdir, "original.gpkg.tar")
            test_gpkg = gpkg(settings, "test", binpkg)

            # Verify the file, then replace it, as a concurrent writer
            # could between verification and extraction.
            test_gpkg._verify_binpkg()
            shutil.copyfile(os.path.join(tmpdir, "replacement.gpkg.tar"), binpkg)

            # decompress() calls _verify_binpkg() again, which would catch
            # the replacement on its own. Stub it out so what is under test
            # is the check against the bytes extraction actually consumed.
            test_gpkg._verify_binpkg = lambda *args, **kwargs: None

            dest_dir = os.path.join(tmpdir, "dest")
            self.assertRaises(DigestException, test_gpkg.decompress, dest_dir)
            self.assertFalse(os.path.exists(os.path.join(dest_dir, "usr")))
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()
