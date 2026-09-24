# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import stat
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import portage
from portage.tests import TestCase
from portage.util.futures import asyncio
from _emerge.EbuildMetadataPhase import EbuildMetadataPhase


class EbuildMetadataPhaseTestCase(TestCase):
    def test_sandbox_log_directory_and_permissions(self):
        with tempfile.NamedTemporaryFile("w", suffix=".ebuild") as ebuild_file:
            ebuild_file.write('EAPI=8\nDESCRIPTION="test"\n')
            ebuild_file.flush()

            settings = portage.config()
            ebuild_hash = SimpleNamespace(location=ebuild_file.name)
            loop = asyncio._safe_loop()

            created_sandbox_dir = None
            sandbox_dir_stat = None
            proc = None

            def fake_doebuild(*args, **kwargs):
                nonlocal created_sandbox_dir, sandbox_dir_stat
                created_sandbox_dir = proc._sandbox_dir
                sandbox_dir_stat = os.stat(created_sandbox_dir)
                return 0

            with patch(
                "portage.package.ebuild.doebuild.doebuild",
                side_effect=fake_doebuild,
            ):
                proc = EbuildMetadataPhase(
                    cpv="cat/pkg-1",
                    ebuild_hash=ebuild_hash,
                    portdb=MagicMock(),
                    repo_path=os.path.dirname(ebuild_file.name),
                    scheduler=loop,
                    settings=settings,
                )
                proc.start()
                loop.run_until_complete(proc.async_wait())

            self.assertIsNotNone(created_sandbox_dir)
            basename = os.path.basename(created_sandbox_dir)
            self.assertTrue(basename.startswith("sandbox-"))
            self.assertEqual(stat.S_IMODE(sandbox_dir_stat.st_mode), 0o750)

            # Under root privileges, apply_secpass_permissions sets portage ownership
            if os.getuid() == 0:
                self.assertEqual(sandbox_dir_stat.st_uid, portage.portage_uid)
                self.assertEqual(sandbox_dir_stat.st_gid, portage.portage_gid)

            # Verify that the directory was cleaned up after completion
            self.assertFalse(
                os.path.exists(created_sandbox_dir),
                f"Expected {created_sandbox_dir} to be cleaned up",
            )
