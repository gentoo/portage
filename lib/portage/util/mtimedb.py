# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["MtimeDB"]

import copy
import errno
import io
import json
import pickle

import portage
from portage.data import portage_gid, uid
from portage.localization import _
from portage.util import apply_secpass_permissions, atomic_ofstream, writemsg

_MTIMEDBKEYS = {
    "info",
    "ldpath",
    "resume",
    "resume_backup",
    "starttime",
    "updates",
    "version",
}


class MtimeDB(dict):
    """The MtimeDB class is used to interact with a file storing the
    current resume lists.
    It is a subclass of ``dict`` and it reads from/writes to JSON, by
    default, although it can be configured to use ``pickle``.
    """

    # JSON read support has been available since portage-2.1.10.49.
    _json_write = True

    _json_write_opts = {"ensure_ascii": False, "indent": "\t", "sort_keys": True}

    def __init__(self, filename):
        dict.__init__(self)
        self.filename = filename
        self._load(filename)

    @property
    def is_readonly(self):
        if self.filename is None:
            return True
        else:
            return False

    def make_readonly(self):
        self.filename = None

    def _load(self, filename):
        f = None
        content = None
        try:
            f = open(filename.encode("utf-8", "backslashreplace"), "rb")
            content = f.read()
        except OSError as e:
            if getattr(e, "errno", None) in (errno.ENOENT, errno.EACCES):
                pass
            else:
                writemsg(_(f"!!! Error loading '{filename}': {e}\n"), noiselevel=-1)
        finally:
            if f is not None:
                f.close()

        d = {}
        if content:
            try:
                d = json.loads(
                    content.decode("utf-8", "strict")
                    if isinstance(content, bytes)
                    else content
                )
            except SystemExit:
                raise
            except Exception as e:
                try:
                    mypickle = pickle.Unpickler(io.BytesIO(content))
                    try:
                        mypickle.find_global = None
                    except AttributeError:
                        # Python >=3
                        pass
                    d = mypickle.load()
                except SystemExit:
                    raise
                except Exception:
                    writemsg(_(f"!!! Error loading '{filename}': {e}\n"), noiselevel=-1)

        if "old" in d:
            d["updates"] = d["old"]
            del d["old"]
        if "cur" in d:
            del d["cur"]

        d.setdefault("starttime", 0)
        d.setdefault("version", "")
        for k in ("info", "ldpath", "updates"):
            d.setdefault(k, {})

        for k in set(d.keys()) - _MTIMEDBKEYS:
            writemsg(_(f"Deleting invalid mtimedb key: {k}\n"))
            del d[k]
        self.update(d)
        self._clean_data = copy.deepcopy(d)

    def commit(self):
        if self.is_readonly:
            return
        d = {}
        d.update(self)
        # Only commit if the internal state has changed.
        if d != self._clean_data:
            self.__write_to_disk(d)

    def __write_to_disk(self, d):
        """Private method used by the ``commit`` method."""
        d["version"] = str(portage.VERSION)
        try:
            f = atomic_ofstream(self.filename, mode="wb")
        except OSError:
            pass
        else:
            if self._json_write:
                f.write(
                    json.dumps(d, **self._json_write_opts).encode("utf-8", "strict")
                )
            else:
                pickle.dump(d, f, protocol=2)
            f.close()
            apply_secpass_permissions(
                self.filename, uid=uid, gid=portage_gid, mode=0o644
            )
            self._clean_data = copy.deepcopy(d)
