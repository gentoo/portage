# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage


class CleanResume:

	short_desc = "Discard emerge --resume merge lists"

	@staticmethod
	def name():
		return "cleanresume"

	def check(self,  **kwargs):
		onProgress = kwargs.get('onProgress', None)
		messages = []
		mtimedb = portage.mtimedb
		resume_keys = ("resume", "resume_backup")
		maxval = len(resume_keys)
		if onProgress:
			onProgress(maxval, 0)
		for i, k in enumerate(resume_keys):
			try:
				d = mtimedb.get(k)
				if d is None:
					continue
				if not isinstance(d, dict):
					messages.append("unrecognized resume list: '%s'" % k)
					continue
				mergelist = d.get("mergelist")
				if mergelist is None or not hasattr(mergelist, "__len__"):
					messages.append("unrecognized resume list: '%s'" % k)
					continue
				messages.append("resume list '%s' contains %d packages" % \
					(k, len(mergelist)))
			finally:
				if onProgress:
					onProgress(maxval, i+1)
		return (True, messages)

	def fix(self,  **kwargs):
		onProgress = kwargs.get('onProgress', None)
		delete_count = 0
		mtimedb = portage.mtimedb
		resume_keys = ("resume", "resume_backup")
		maxval = len(resume_keys)
		if onProgress:
			onProgress(maxval, 0)
		for i, k in enumerate(resume_keys):
			try:
				if mtimedb.pop(k, None) is not None:
					delete_count += 1
			finally:
				if onProgress:
					onProgress(maxval, i+1)
		if delete_count:
			mtimedb.commit()
		return (True, None)
