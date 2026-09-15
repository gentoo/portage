# Copyright 2005-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)

import dbm

try:
    import dbm.gnu as gdbm
except ImportError:
    gdbm = None

import errno
import glob
import os
import pickle
import secrets

from portage.cache import cache_errors, fs_template


class database(fs_template.FsBased):
    validation_chf = "md5"
    chf_types = ("md5", "mtime")

    autocommits = True
    cleanse_keys = True
    serialize_eclasses = False

    __db = None

    def __init__(self, *args, **config):
        super().__init__(*args, **config)

        default_db = config.get("dbtype", "anydbm")
        if not default_db.startswith("."):
            default_db = "." + default_db

        self._db_path = os.path.join(
            self.location, fs_template.gen_label(self.location, self.label) + default_db
        )
        self.__db = None
        try:
            # dbm.open() will not work with bytes in python-3.1:
            #   TypeError: can't concat bytes to str
            self.__db = dbm.open(self._db_path, self._open_mode(), self._perms)
        except dbm.error:
            try:
                self._ensure_dirs()
                self._ensure_dirs(self._db_path)
                self._create()
                self.__db = dbm.open(self._db_path, self._open_mode(), self._perms)
            except dbm.error as e:
                raise cache_errors.InitializationError(self.__class__, e)
        self._ensure_access(self._db_path)

    def _create(self):
        # Another process may be creating the same database, and a file that
        # dbm has not finished writing has no recognizable type. Create the
        # database under a temporary name and link it into place, which is
        # atomic when the dbm type uses a single file (gdbm, sqlite3). Links
        # cannot cross filesystems, so the temporary file stays in the same
        # directory.
        db_dir, db_name = os.path.split(self._db_path)
        tmp_path = os.path.join(db_dir, f".{db_name}.{secrets.token_hex(8)}")
        tmp_glob = glob.escape(tmp_path) + "*"
        try:
            self._create_at(tmp_path)
            # Some dbm types add suffixes to the name, or use several files.
            for tmp_file in glob.glob(tmp_glob):
                try:
                    os.link(tmp_file, self._db_path + tmp_file[len(tmp_path) :])
                except FileExistsError:
                    pass
                except OSError as e:
                    if e.errno not in (errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP):
                        raise
                    # The filesystem has no hard links, so create in place.
                    self._create_at(self._db_path)
                    break
        finally:
            for tmp_file in glob.glob(tmp_glob):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass

    def _create_at(self, path):
        if gdbm is None:
            dbm.open(path, "c", self._perms).close()
        else:
            # Prefer gdbm type if available, since it allows
            # multiple concurrent writers (see bug #53607).
            gdbm.open(path, "cu", self._perms).close()

    def _open_mode(self):
        if dbm.whichdb(self._db_path) in ("dbm.gnu", "gdbm"):
            # Allow multiple concurrent writers (see bug #53607).
            return "wu"
        return "w"

    def __getstate__(self):
        state = self.__dict__.copy()
        # These attributes are not picklable, so they are automatically
        # regenerated after unpickling.
        state["_database__db"] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.__db = dbm.open(self._db_path, self._open_mode(), self._perms)

    def iteritems(self):
        # dbm doesn't implement items()
        for k in self.__db.keys():
            yield (k, self[k])

    def _getitem(self, cpv):
        # we override getitem because it's just a cpickling of the data handed in.
        return pickle.loads(self.__db[cpv.encode("utf-8", "backslashreplace")])

    def _setitem(self, cpv, values):
        self.__db[cpv.encode("utf-8", "backslashreplace")] = pickle.dumps(
            values, pickle.HIGHEST_PROTOCOL
        )

    def _delitem(self, cpv):
        del self.__db[cpv]

    def __iter__(self):
        return iter(list(self.__db.keys()))

    def __contains__(self, cpv):
        return cpv in self.__db

    def close(self):
        db, self.__db = self.__db, None
        if db is None:
            return
        try:
            super().close()
            # dbm.sqlite3 and dbm.ndbm have no sync().
            if hasattr(db, "sync"):
                db.sync()
        finally:
            db.close()

    # TODO: do we need iteritems()?
    items = iteritems
