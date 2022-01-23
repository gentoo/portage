# Copright Gentoo Foundation 2006-2020
# Portage Unit Testing Functionality

import io
import sys
import tarfile
import tempfile
from os import urandom

from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.gpkg import gpkg
from portage.gpg import GPG
from portage.exception import MissingSignature, InvalidSignature


class test_gpkg_gpg_case(TestCase):
    def test_gpkg_missing_manifest_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-request-signature"',
                    'BINPKG_FORMAT="gpkg"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name == "Manifest":
                            manifest = tar_1.extractfile(f).read().decode("UTF-8")
                            manifest = manifest.replace(
                                "-----BEGIN PGP SIGNATURE-----", ""
                            )
                            manifest = manifest.replace(
                                "-----END PGP SIGNATURE-----", ""
                            )
                            manifest_data = io.BytesIO(manifest.encode("UTF-8"))
                            manifest_data.seek(0, io.SEEK_END)
                            f.size = manifest_data.tell()
                            manifest_data.seek(0)
                            tar_2.addfile(f, manifest_data)
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                InvalidSignature, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_missing_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-request-signature"',
                    'BINPKG_FORMAT="gpkg"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name.endswith(".sig"):
                            pass
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))
            self.assertRaises(
                MissingSignature, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )

        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_ignore_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-ignore-signature"',
                    'BINPKG_FORMAT="gpkg"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name == "Manifest.sig":
                            pass
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))
            binpkg_2.decompress(os.path.join(tmpdir, "test"))
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_auto_use_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} binpkg-signing '
                    '-binpkg-request-signature"',
                    'BINPKG_FORMAT="gpkg"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name.endswith(".sig"):
                            pass
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))
            self.assertRaises(
                MissingSignature, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_invalid_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-request-signature"',
                    'BINPKG_FORMAT="gpkg"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name == "Manifest":
                            sig = b"""
-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

DATA test/image.tar.zst 1049649 BLAKE2B 3112adba9c09023962f26d9dcbf8e74107c05220f2f29aa2ce894f8a4104c3bb238f87095df73735befcf1e1f6039fc3abf4defa87e68ce80f33dd01e09c055a SHA512 9f584727f2e20a50a30e0077b94082c8c1f517ebfc9978eb3281887e24458108e73d1a2ce82eb0b59f5df7181597e4b0a297ae68bbfb36763aa052e6bdbf2c59
DATA test/image.tar.zst.sig 833 BLAKE2B 214724ae4ff9198879c8c960fd8167632e27982c2278bb873f195abe75b75afa1ebed4c37ec696f5f5bc35c3a1184b60e0b50d56695b072b254f730db01eddb5 SHA512 67316187da8bb6b7a5f9dc6a42ed5c7d72c6184483a97f23c0bebd8b187ac9268e0409eb233c935101606768718c99eaa5699037d6a68c2d88c9ed5331a3f73c
-----BEGIN PGP SIGNATURE-----

iQIzBAEBCgAdFiEEBrOjEb13XCgNIqkwXZDqBjUhd/YFAmFazXEACgkQXZDqBjUh
d/YFZA//eiXkYAS2NKxim6Ppr1HcZdjU1f6H+zyQzC7OdPkAh7wsVXpSr1aq+giD
G4tNtI6nsFokpA5CMhDf+ffBofKmFY5plk9zyQHr43N/RS5G6pcb2LHk0mQqgIdB
EsZRRD75Na4uGDWjuNHRmsasPTsc9qyW7FLckjwUsVmk9foAoiLYYaTsilsEGqXD
Bl/Z6PaQXvdd8txbcP6dOXfhVT06b+RWcnHI06KQrmFkZjZQh/7bCIeCVwNbXr7d
Obo8SVzCrQbTONei57AkyuRfnPqBfP61k8rQtcDUmCckQQfyaRwoW2nDIewOPfIH
xfvM137to2GEI2RR1TpWmGfu3iQzgC71f4svdX9Tyi5N7aFmfud7LZs6/Un3IdVk
ZH9/AmRzeH6hKllqSv/6WuhjsTNvr0bOzGbskkhqlLga2tml08gHFYOMWRJb/bRz
N8FZMhHzFoc0hsG8SU9uC+OeW+y5NdqpbRnQwgABmAiKEpgAPnABTsr0HjyxvjY+
uCUdvMMHvnTxTjNEZ3Q+UQ2VsSoZzPbW9Y4PuM0XxxmTI8htdn4uIhy9dLNPsJmB
eTE8aov/1uKq9VMsYC8wcx5vLMaR7/O/9XstP+r6PaZwiLlyrKHGexV4O52sj6LC
qGAN3VUF+8EsdcsV781H0F86PANhyBgEYTGDrnItTGe3/vAPjCo=
=S/Vn
-----END PGP SIGNATURE-----
"""
                            data = io.BytesIO(sig)
                            f.size = len(sig)
                            tar_2.addfile(f, data)
                            data.close()
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))
            self.assertRaises(
                InvalidSignature, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_untrusted_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        gpg_test_path = os.environ["PORTAGE_GNUPGHOME"]

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-request-signature"',
                    'BINPKG_FORMAT="gpkg"',
                    f'BINPKG_GPG_SIGNING_BASE_COMMAND="flock {gpg_test_path}/portage-binpkg-gpg.lock /usr/bin/gpg --sign --armor --batch --no-tty --yes --pinentry-mode loopback --passphrase GentooTest [PORTAGE_CONFIG]"',
                    'BINPKG_GPG_SIGNING_DIGEST="SHA512"',
                    f'BINPKG_GPG_SIGNING_GPG_HOME="{gpg_test_path}"',
                    'BINPKG_GPG_SIGNING_KEY="0x8812797DDF1DD192"',
                    'BINPKG_GPG_VERIFY_BASE_COMMAND="/usr/bin/gpg --verify --batch --no-tty --yes --no-auto-check-trustdb --status-fd 1 [PORTAGE_CONFIG] [SIGNATURE]"',
                    f'BINPKG_GPG_VERIFY_GPG_HOME="{gpg_test_path}"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            self.assertRaises(
                InvalidSignature, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )

        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_unknown_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-request-signature"',
                    'BINPKG_FORMAT="gpkg"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name == "Manifest":
                            sig = b"""
-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA256


DATA test/image.tar.zst 1049649 BLAKE2B 3112adba9c09023962f26d9dcbf8e74107c05220f2f29aa2ce894f8a4104c3bb238f87095df73735befcf1e1f6039fc3abf4defa87e68ce80f33dd01e09c055a SHA512 9f584727f2e20a50a30e0077b94082c8c1f517ebfc9978eb3281887e24458108e73d1a2ce82eb0b59f5df7181597e4b0a297ae68bbfb36763aa052e6bdbf2c59
DATA test/image.tar.zst.sig 833 BLAKE2B 214724ae4ff9198879c8c960fd8167632e27982c2278bb873f195abe75b75afa1ebed4c37ec696f5f5bc35c3a1184b60e0b50d56695b072b254f730db01eddb5 SHA512 67316187da8bb6b7a5f9dc6a42ed5c7d72c6184483a97f23c0bebd8b187ac9268e0409eb233c935101606768718c99eaa5699037d6a68c2d88c9ed5331a3f73c
-----BEGIN PGP SIGNATURE-----

iNUEARYIAH0WIQSMe+CQzU+/D/DeMitA3PGOlxUHlQUCYVrQal8UgAAAAAAuAChp
c3N1ZXItZnByQG5vdGF0aW9ucy5vcGVucGdwLmZpZnRoaG9yc2VtYW4ubmV0OEM3
QkUwOTBDRDRGQkYwRkYwREUzMjJCNDBEQ0YxOEU5NzE1MDc5NQAKCRBA3PGOlxUH
lbmTAP4jdhMTW6g550/t0V7XcixqVtBockOTln8hZrZIQrjAJAD/caDkxgz5Xl8C
EP1pgSXXGtlUnv6akg/wueFJKEr9KQs=
=edEg
-----END PGP SIGNATURE-----
"""
                            data = io.BytesIO(sig)
                            f.size = len(sig)
                            tar_2.addfile(f, data)
                            data.close()
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))
            self.assertRaises(
                InvalidSignature, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )

        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()
