# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['MtimeDB']

import copy
try:
	import cPickle as pickle
except ImportError:
	import pickle

import errno
import io
import json

import portage
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.data import portage_gid, uid
from portage.localization import _
from portage.util import apply_secpass_permissions, atomic_ofstream, writemsg

class MtimeDB(dict):

	# JSON read support has been available since portage-2.1.10.49.
	_json_write = True

	_json_write_opts = {
		"ensure_ascii": False,
		"indent": "\t",
		"sort_keys": True
	}

	def __init__(self, filename):
		dict.__init__(self)
		self.filename = filename
		self._load(filename)

	def _load(self, filename):
		f = None
		content = None
		try:
			f = open(_unicode_encode(filename), 'rb')
			content = f.read()
		except EnvironmentError as e:
			if getattr(e, 'errno', None) in (errno.ENOENT, errno.EACCES):
				pass
			else:
				writemsg(_("!!! Error loading '%s': %s\n") % \
					(filename, e), noiselevel=-1)
		finally:
			if f is not None:
				f.close()

		d = None
		if content:
			try:
				d = json.loads(_unicode_decode(content,
					encoding=_encodings['repo.content'], errors='strict'))
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
					writemsg(_("!!! Error loading '%s': %s\n") % \
						(filename, e), noiselevel=-1)

		if d is None:
			d = {}

		if "old" in d:
			d["updates"] = d["old"]
			del d["old"]
		if "cur" in d:
			del d["cur"]

		d.setdefault("starttime", 0)
		d.setdefault("version", "")
		for k in ("info", "ldpath", "updates"):
			d.setdefault(k, {})

		mtimedbkeys = set(("info", "ldpath", "resume", "resume_backup",
			"starttime", "updates", "version"))

		for k in list(d):
			if k not in mtimedbkeys:
				writemsg(_("Deleting invalid mtimedb key: %s\n") % str(k))
				del d[k]
		self.update(d)
		self._clean_data = copy.deepcopy(d)

	def commit(self):
		if not self.filename:
			return
		d = {}
		d.update(self)
		# Only commit if the internal state has changed.
		if d != self._clean_data:
			d["version"] = str(portage.VERSION)
			try:
				f = atomic_ofstream(self.filename, mode='wb')
			except EnvironmentError:
				pass
			else:
				if self._json_write:
					f.write(_unicode_encode(
						json.dumps(d, **self._json_write_opts),
						encoding=_encodings['repo.content'], errors='strict'))
				else:
					pickle.dump(d, f, protocol=2)
				f.close()
				apply_secpass_permissions(self.filename,
					uid=uid, gid=portage_gid, mode=0o644)
				self._clean_data = copy.deepcopy(d)
