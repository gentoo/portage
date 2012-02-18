# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['MtimeDB']

import copy
try:
	import cPickle as pickle
except ImportError:
	import pickle

import errno
import portage
from portage import _unicode_encode
from portage.data import portage_gid, uid
from portage.localization import _
from portage.util import apply_secpass_permissions, atomic_ofstream, writemsg

class MtimeDB(dict):
	def __init__(self, filename):
		dict.__init__(self)
		self.filename = filename
		self._load(filename)

	def _load(self, filename):
		f = None
		try:
			f = open(_unicode_encode(filename), 'rb')
			mypickle = pickle.Unpickler(f)
			try:
				mypickle.find_global = None
			except AttributeError:
				# TODO: If py3k, override Unpickler.find_class().
				pass
			d = mypickle.load()
		except (AttributeError, EOFError, EnvironmentError, ValueError, pickle.UnpicklingError) as e:
			if isinstance(e, EnvironmentError) and \
				getattr(e, 'errno', None) in (errno.ENOENT, errno.EACCES):
				pass
			else:
				writemsg(_("!!! Error loading '%s': %s\n") % \
					(filename, str(e)), noiselevel=-1)
			del e
			d = {}
		finally:
			if f is not None:
				f.close()

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
				pickle.dump(d, f, protocol=2)
				f.close()
				apply_secpass_permissions(self.filename,
					uid=uid, gid=portage_gid, mode=0o644)
				self._clean_data = copy.deepcopy(d)
