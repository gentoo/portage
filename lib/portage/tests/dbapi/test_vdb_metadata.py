# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import tempfile

import portage
from portage.tests import TestCase
from portage.dbapi.vartree import (
    _METADATA_FILE,
    _METADATA_FILE_FIELDS,
    _METADATA_FILE_FORMAT_VERSION,
    _consolidate_to_metadata_file,
    _explode_metadata_file,
    _in_metadata_file,
    _read_metadata_file,
    _write_metadata_file,
    vardbapi,
)
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class VdbInMetadataFileTestCase(TestCase):
    def test_accepts_cached_fields(self):
        for name in ("EAPI", "SLOT", "USE", "DEPEND", "repository"):
            self.assertTrue(_in_metadata_file(name), name)

    def test_rejects_multi_line_fields(self):
        # One line per field cannot represent these, so they stay in their own
        # file and are read from there.
        for name in ("CONTENTS", "NEEDED", "NEEDED.ELF.2"):
            self.assertFalse(_in_metadata_file(name), name)

    def test_rejects_non_fields(self):
        for name in ("environment.bz2", "foo-1.ebuild", "counter"):
            self.assertFalse(_in_metadata_file(name), name)

    def test_rejects_uncached_vdb_fields(self):
        # These have individual VDB files and look like fields, but vardbapi
        # does not cache them. Serving them from the file would claim a
        # completeness it cannot have: a field outside _aux_cache_keys falls
        # back to environment.bz2 when its individual file is missing
        # (bug 395463), and "" is not that.
        for name in ("FEATURES", "IUSE_EFFECTIVE", "CFLAGS", "SRC_URI", "INHERITED"):
            self.assertFalse(_in_metadata_file(name), name)

    def test_no_multi_line_fields(self):
        # One line per field, so no field the file carries may be one _aux_get
        # preserves newlines for.
        for name in _METADATA_FILE_FIELDS:
            self.assertIsNone(vardbapi._aux_multi_line_re.match(name), name)


class VdbMetadataReadWriteTestCase(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_write_then_read_roundtrip(self):
        data = {"EAPI": "8", "SLOT": "0/0", "USE": "foo bar", "repository": "gentoo"}
        _write_metadata_file(self._tmpdir, data)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        self.assertTrue(os.path.exists(path))
        result = _read_metadata_file(path)
        self.assertEqual(result, data)

    def _write_raw(self, content, stamp=True):
        """Write raw metadata content, appending a valid #dir_mtime= by default.

        The stamp is taken after the file exists, since creating it changes the
        directory mtime the reader validates against.
        """
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        with open(path, "w") as f:
            f.write(content)
        if stamp:
            with open(path, "a") as f:
                f.write(f"#dir_mtime={os.stat(self._tmpdir).st_mtime_ns}\n")
        return path

    def test_rejects_missing_format_header(self):
        # A file written before format versioning existed cannot be trusted as
        # a complete snapshot, so it is rejected instead of read as complete.
        path = self._write_raw("EAPI=8\nSLOT=0\n")
        self.assertIsNone(_read_metadata_file(path))

    def test_rejects_other_format_version(self):
        path = self._write_raw(f"#format={_METADATA_FILE_FORMAT_VERSION + 1}\nEAPI=8\n")
        self.assertIsNone(_read_metadata_file(path))

    def test_rejects_non_integer_format_version(self):
        path = self._write_raw("#format=bogus\nEAPI=8\n")
        self.assertIsNone(_read_metadata_file(path))

    def test_rejects_missing_dir_mtime(self):
        # An interrupted write leaves the file without its trailing
        # #dir_mtime=, and a short snapshot must not be read as complete.
        path = self._write_raw(
            f"#format={_METADATA_FILE_FORMAT_VERSION}\nEAPI=8\n", stamp=False
        )
        self.assertIsNone(_read_metadata_file(path))

    def test_rejects_stale_dir_mtime(self):
        # Anything that changes the package directory after the file was
        # written invalidates it, so the caller falls back to per-field reads.
        path = self._write_raw(f"#format={_METADATA_FILE_FORMAT_VERSION}\nEAPI=8\n")
        self.assertEqual(_read_metadata_file(path), {"EAPI": "8"})
        os.utime(self._tmpdir, ns=(0, 0))
        self.assertIsNone(_read_metadata_file(path))

    def test_rejects_non_integer_dir_mtime(self):
        path = self._write_raw(
            f"#format={_METADATA_FILE_FORMAT_VERSION}\nEAPI=8\n#dir_mtime=bogus\n",
            stamp=False,
        )
        self.assertIsNone(_read_metadata_file(path))

    def test_dir_st_argument_used(self):
        # _aux_get passes the stat it already holds; it must be honored.
        path = self._write_raw(f"#format={_METADATA_FILE_FORMAT_VERSION}\nEAPI=8\n")
        st = os.stat(self._tmpdir)
        self.assertEqual(_read_metadata_file(path, dir_st=st), {"EAPI": "8"})
        os.utime(self._tmpdir, ns=(0, 0))
        # A caller passing the pre-change stat still validates against it.
        self.assertEqual(_read_metadata_file(path, dir_st=st), {"EAPI": "8"})
        self.assertIsNone(_read_metadata_file(path, dir_st=os.stat(self._tmpdir)))

    def test_write_then_read_survives_rename(self):
        # write_atomic() renames into place, bumping the directory mtime; the
        # stamp is taken afterwards so the file it just wrote is readable.
        _write_metadata_file(self._tmpdir, {"EAPI": "8", "SLOT": "0"})
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        self.assertEqual(_read_metadata_file(path), {"EAPI": "8", "SLOT": "0"})

    def test_format_version_header_written(self):
        _write_metadata_file(self._tmpdir, {"EAPI": "8"})
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        with open(path) as f:
            first_line = f.readline().rstrip("\n")
        self.assertEqual(first_line, f"#format={_METADATA_FILE_FORMAT_VERSION}")

    def test_format_version_header_ignored_on_read(self):
        _write_metadata_file(self._tmpdir, {"EAPI": "8", "SLOT": "0"})
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertNotIn(f"#format={_METADATA_FILE_FORMAT_VERSION}", result)
        self.assertEqual(result["EAPI"], "8")

    def test_comment_lines_ignored(self):
        path = self._write_raw(
            f"#format={_METADATA_FILE_FORMAT_VERSION}\n# another comment\nEAPI=8\n"
        )
        result = _read_metadata_file(path)
        self.assertEqual(result, {"EAPI": "8"})

    def test_keys_sorted_in_file(self):
        data = {"SLOT": "0", "EAPI": "8", "USE": "foo"}
        _write_metadata_file(self._tmpdir, data)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        with open(path) as f:
            lines = [l.rstrip("\n") for l in f if not l.startswith("#")]
        keys = [l.split("=", 1)[0] for l in lines if "=" in l]
        self.assertEqual(keys, sorted(keys))

    def test_value_with_equals_sign(self):
        data = {"HOMEPAGE": "https://example.com/?foo=bar"}
        _write_metadata_file(self._tmpdir, data)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertEqual(result["HOMEPAGE"], "https://example.com/?foo=bar")

    def test_value_with_hash(self):
        # A '#' inside a value must not be mistaken for a comment: only a
        # line *starting* with '#' is one.
        data = {"HOMEPAGE": "https://example.com/#anchor"}
        _write_metadata_file(self._tmpdir, data)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertEqual(result["HOMEPAGE"], "https://example.com/#anchor")

    def test_value_with_dots_and_hash(self):
        data = {"HOMEPAGE": "http://127.0.0.1/?a=1#anchor"}
        _write_metadata_file(self._tmpdir, data)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertEqual(result["HOMEPAGE"], "http://127.0.0.1/?a=1#anchor")

    def test_empty_value(self):
        data = {"IUSE": "", "EAPI": "8"}
        _write_metadata_file(self._tmpdir, data)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertEqual(result["IUSE"], "")
        self.assertEqual(result["EAPI"], "8")


class VdbConsolidateTestCase(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_field(self, name, value):
        with open(os.path.join(self._tmpdir, name), "w") as f:
            f.write(value + "\n")

    def test_basic_consolidation(self):
        self._write_field("EAPI", "8")
        self._write_field("SLOT", "0/0")
        self._write_field("USE", "foo bar")
        _consolidate_to_metadata_file(self._tmpdir)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertEqual(result["EAPI"], "8")
        self.assertEqual(result["SLOT"], "0/0")
        self.assertEqual(result["USE"], "foo bar")

    def test_contents_excluded(self):
        self._write_field("EAPI", "8")
        with open(os.path.join(self._tmpdir, "CONTENTS"), "w") as f:
            f.write("obj /usr/bin/foo abc123 1234567890\n")
        _consolidate_to_metadata_file(self._tmpdir)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertNotIn("CONTENTS", result)

    def test_dotted_files_excluded(self):
        self._write_field("EAPI", "8")
        with open(os.path.join(self._tmpdir, "NEEDED.ELF.2"), "w") as f:
            f.write("/usr/lib/libfoo.so\n")
        _consolidate_to_metadata_file(self._tmpdir)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertNotIn("NEEDED.ELF.2", result)

    def test_uncached_field_excluded(self):
        # An all-caps VDB field vardbapi does not cache. It stays in its own
        # file, and consolidation must not claim or remove it.
        self._write_field("EAPI", "8")
        self._write_field("FEATURES", "buildpkg parallel-install")
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertNotIn("FEATURES", result)
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "FEATURES")))

    def test_bare_needed_excluded(self):
        # NEEDED has no dot, so a name-based rule would accept it; it is
        # multi-line like CONTENTS and is not a cached field either.
        self._write_field("EAPI", "8")
        with open(os.path.join(self._tmpdir, "NEEDED"), "w") as f:
            f.write("/usr/bin/foo libc.so.6\n/usr/bin/bar libm.so.6\n")
        _consolidate_to_metadata_file(self._tmpdir)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertNotIn("NEEDED", result)
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "NEEDED")))

    def test_whitespace_normalized(self):
        self._write_field("USE", "  foo   bar  baz  ")
        _consolidate_to_metadata_file(self._tmpdir)
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        result = _read_metadata_file(path)
        self.assertEqual(result["USE"], "foo bar baz")

    def test_individual_files_kept_by_default(self):
        self._write_field("EAPI", "8")
        _consolidate_to_metadata_file(self._tmpdir)
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "EAPI")))

    def test_delete_individual_files(self):
        self._write_field("EAPI", "8")
        self._write_field("SLOT", "0")
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, "EAPI")))
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, "SLOT")))
        # metadata file itself must exist
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, _METADATA_FILE)))

    def test_delete_individual_leaves_readable_file(self):
        # The unlinks change the directory, so the file has to be stamped
        # after them. Stamping first would leave the package with neither its
        # individual files nor a metadata file the reader accepts.
        self._write_field("EAPI", "8")
        self._write_field("SLOT", "0")
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        result = _read_metadata_file(os.path.join(self._tmpdir, _METADATA_FILE))
        self.assertIsNotNone(result)
        self.assertEqual(result["EAPI"], "8")
        self.assertEqual(result["SLOT"], "0")

    def test_delete_individual_preserves_contents(self):
        self._write_field("EAPI", "8")
        contents = "obj /usr/bin/foo abc123 1234567890\n"
        with open(os.path.join(self._tmpdir, "CONTENTS"), "w") as f:
            f.write(contents)
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        # CONTENTS not in metadata file, not deleted
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "CONTENTS")))

    def test_empty_dir_no_metadata_file(self):
        _consolidate_to_metadata_file(self._tmpdir)
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, _METADATA_FILE)))

    def test_skips_when_file_is_already_current(self):
        # A file that still validates describes dbdir exactly, so a second
        # call must not rewrite it. write_atomic() renames a new file into
        # place, so a rewrite would change the inode.
        self._write_field("EAPI", "8")
        path = os.path.join(self._tmpdir, _METADATA_FILE)
        _consolidate_to_metadata_file(self._tmpdir)
        ino = os.stat(path).st_ino
        _consolidate_to_metadata_file(self._tmpdir)
        self.assertEqual(os.stat(path).st_ino, ino)

    def test_rebuilds_when_file_is_stale(self):
        self._write_field("EAPI", "8")
        _consolidate_to_metadata_file(self._tmpdir)
        # A changed directory invalidates the file, so it is rebuilt rather
        # than skipped, and picks up the field added along the way.
        self._write_field("SLOT", "0/0")
        _consolidate_to_metadata_file(self._tmpdir)
        result = _read_metadata_file(os.path.join(self._tmpdir, _METADATA_FILE))
        self.assertEqual(result["SLOT"], "0/0")

    def test_delete_individual_not_skipped_by_current_file(self):
        # The plain call leaves the individual files in place, so the
        # delete_individual call after it still has work despite finding a
        # metadata file that validates.
        self._write_field("EAPI", "8")
        _consolidate_to_metadata_file(self._tmpdir)
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, "EAPI")))
        result = _read_metadata_file(os.path.join(self._tmpdir, _METADATA_FILE))
        self.assertEqual(result["EAPI"], "8")


class VdbExplodeTestCase(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_field(self, name, value):
        with open(os.path.join(self._tmpdir, name), "w") as f:
            f.write(value + "\n")

    def _read_field(self, name):
        with open(os.path.join(self._tmpdir, name)) as f:
            return f.read()

    def test_no_metadata_file_is_not_an_error(self):
        self.assertEqual(_explode_metadata_file(self._tmpdir), [])

    def test_removes_file_and_keeps_individual_files(self):
        self._write_field("EAPI", "8")
        self._write_field("SLOT", "0")
        _consolidate_to_metadata_file(self._tmpdir)
        # Nothing to restore: the individual files were never removed.
        self.assertEqual(_explode_metadata_file(self._tmpdir), [])
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, _METADATA_FILE)))
        self.assertEqual(self._read_field("EAPI"), "8\n")
        self.assertEqual(self._read_field("SLOT"), "0\n")

    def test_round_trip_through_delete_individual(self):
        # The case that makes this the inverse rather than an unlink: after
        # --delete-individual-files the metadata file is the only copy.
        self._write_field("EAPI", "8")
        self._write_field("SLOT", "0/0")
        self._write_field("USE", "foo bar")
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, "EAPI")))

        self.assertEqual(_explode_metadata_file(self._tmpdir), ["EAPI", "SLOT", "USE"])
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, _METADATA_FILE)))
        self.assertEqual(self._read_field("EAPI"), "8\n")
        self.assertEqual(self._read_field("SLOT"), "0/0\n")
        self.assertEqual(self._read_field("USE"), "foo bar\n")

    def test_non_metadata_files_untouched(self):
        self._write_field("EAPI", "8")
        with open(os.path.join(self._tmpdir, "CONTENTS"), "w") as f:
            f.write("obj /usr/bin/foo abc123 1234567890\n")
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        _explode_metadata_file(self._tmpdir)
        self.assertEqual(
            self._read_field("CONTENTS"), "obj /usr/bin/foo abc123 1234567890\n"
        )

    def test_refuses_when_sole_copy_is_unusable(self):
        # Individual files gone and the snapshot no longer validates: the
        # values cannot be trusted and deleting the file would lose them.
        from portage.exception import PortageException

        self._write_field("EAPI", "8")
        self._write_field("SLOT", "0")
        _consolidate_to_metadata_file(self._tmpdir, delete_individual=True)
        os.utime(self._tmpdir, ns=(0, 0))

        self.assertRaises(PortageException, _explode_metadata_file, self._tmpdir)
        # Nothing destroyed: the file is still there to be recovered from.
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, _METADATA_FILE)))

    def test_removes_unusable_file_when_individual_files_present(self):
        # A stale file is just garbage when every field it names still has its
        # own file, so it is removed rather than refused.
        self._write_field("EAPI", "8")
        _consolidate_to_metadata_file(self._tmpdir)
        os.utime(self._tmpdir, ns=(0, 0))

        self.assertEqual(_explode_metadata_file(self._tmpdir), [])
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, _METADATA_FILE)))
        self.assertEqual(self._read_field("EAPI"), "8\n")


class VdbEmaintRoundTripTestCase(TestCase):
    def testFixDeleteIndividualThenRemoveRestoresVdb(self):
        """'emaint vdb --remove' undoes --fix --delete-individual-files.

        Without the restore step it would unlink the only remaining copy of
        every field and leave an unreadable VDB behind.
        """
        from portage.emaint.modules.vdb.vdb import VdbMetadata

        pkgs = {
            "dev-libs/A-1": {"EAPI": "7", "SLOT": "0", "RDEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "7", "SLOT": "0"},
        }
        playground = ResolverPlayground(ebuilds=pkgs, installed=pkgs)
        # The module resolves the vardb through the global portage.db, the way
        # it does under a real emaint run.
        had_db = hasattr(portage, "db")
        saved_db = getattr(portage, "db", None)
        portage.db = playground.trees
        try:
            settings = playground.settings
            vardb = playground.trees[playground.eroot]["vartree"].dbapi
            pkgdir = vardb.getpath("dev-libs/A-1")
            module = VdbMetadata()

            status, _msgs = module.fix(
                settings=settings, options={"delete_individual_files": True}
            )
            self.assertTrue(status)
            self.assertFalse(os.path.exists(os.path.join(pkgdir, "RDEPEND")))
            self.assertTrue(os.path.exists(os.path.join(pkgdir, _METADATA_FILE)))

            status, _msgs = module.remove(settings=settings)
            self.assertTrue(status)
            self.assertFalse(os.path.exists(os.path.join(pkgdir, _METADATA_FILE)))
            self.assertTrue(os.path.exists(os.path.join(pkgdir, "RDEPEND")))

            # The values have to survive the round trip, not just the files.
            vardb._aux_cache_obj = None
            self.assertEqual(
                vardb.aux_get("dev-libs/A-1", ["RDEPEND", "SLOT", "EAPI"]),
                ["dev-libs/B", "0", "7"],
            )
        finally:
            if had_db:
                portage.db = saved_db
            else:
                del portage.db
            playground.cleanup()


class VdbMetadataAuxGetTestCase(TestCase):
    def testUncachedFieldStillComesFromEnvironment(self):
        """A field the metadata file does not carry still reaches
        environment.bz2 (bug 395463). Serving it as "" because the file is a
        complete snapshot would only be right for fields the file carries."""
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "7",
                "SRC_URI": "https://example.com/A-1.tar.gz",
            },
        }
        installed = {
            "dev-libs/A-1": {
                "EAPI": "7",
                "SRC_URI": "https://example.com/A-1.tar.gz",
            },
        }
        playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
        try:
            vardb = playground.trees[playground.eroot]["vartree"].dbapi
            pkgdir = vardb.getpath("dev-libs/A-1")
            # A real merge writes no SRC_URI file; the playground writes one
            # for every key it is given, so drop it and rebuild the metadata
            # file, whose recorded dir mtime the unlink would otherwise stale.
            os.unlink(os.path.join(pkgdir, "SRC_URI"))
            _consolidate_to_metadata_file(pkgdir)
            # The optimization under test has to actually be in play, or the
            # per-field fallback would serve SRC_URI and hide the bug.
            self.assertIsNotNone(
                _read_metadata_file(os.path.join(pkgdir, _METADATA_FILE))
            )
            self.assertEqual(
                vardb.aux_get("dev-libs/A-1", ["SRC_URI"])[0],
                "https://example.com/A-1.tar.gz",
            )
        finally:
            playground.cleanup()
