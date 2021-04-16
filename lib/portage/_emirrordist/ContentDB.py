# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import operator
import shelve
import typing

from portage.package.ebuild.fetch import DistfileName


class ContentDB:
	"""
	The content db serves to translate content digests to distfiles
	names, and distfiles names to content digests. All keys have one or
	more prefixes separated by colons. For a digest key, the first
	prefix is "digest" and the second prefix is the hash algorithm name.
	For a filename key, the prefix is "filename".

	The value associated with a digest key is a set of file names. The
	value associated with a distfile key is a set of content revisions.
	Each content revision is expressed as a dictionary of digests which
	is suitable for construction of a DistfileName instance.
	"""

	def __init__(self, shelve_instance: shelve.Shelf):
		self._shelve = shelve_instance

	def add(self, filename: DistfileName):
		"""
		Add file name and digests, creating a new content revision, or
		incrementing the reference count to an identical content revision
		if one exists. If the file name had previous content revisions,
		then they continue to exist independently of the new one.

		@param filename: file name with digests attribute
		"""
		distfile_str = str(filename)
		distfile_key = "filename:{}".format(distfile_str)
		for k, v in filename.digests.items():
			if k != "size":
				digest_key = "digest:{}:{}".format(k.upper(), v.lower())
				try:
					digest_files = self._shelve[digest_key]
				except KeyError:
					digest_files = set()
				digest_files.add(distfile_str)
				self._shelve[digest_key] = digest_files
		try:
			content_revisions = self._shelve[distfile_key]
		except KeyError:
			content_revisions = set()

		revision_key = tuple(
			sorted(
				(
					(algo.upper(), filename.digests[algo.upper()].lower())
					for algo in filename.digests
					if algo != "size"
				),
				key=operator.itemgetter(0),
			)
		)
		content_revisions.add(revision_key)
		self._shelve[distfile_key] = content_revisions

	def remove(self, filename: DistfileName):
		"""
		Remove a file name and digests from the database. If identical
		content is still referenced by one or more other file names,
		then those references are preserved (like removing one of many
		hardlinks). Also, this file name may reference other content
		revisions with different digests, and those content revisions
		will remain as well.

		@param filename: file name with digests attribute
		"""
		distfile_key = "filename:{}".format(filename)
		try:
			content_revisions = self._shelve[distfile_key]
		except KeyError:
			pass
		else:
			remaining = set()
			for revision_key in content_revisions:
				if not any(digest_item in revision_key for digest_item in filename.digests.items()):
					remaining.add(revision_key)
					continue
				for k, v in revision_key:
					digest_key = "digest:{}:{}".format(k, v)
					try:
						digest_files = self._shelve[digest_key]
					except KeyError:
						digest_files = set()

					try:
						digest_files.remove(filename)
					except KeyError:
						pass

					if digest_files:
						self._shelve[digest_key] = digest_files
					else:
						try:
							del self._shelve[digest_key]
						except KeyError:
							pass

			if remaining:
				logging.debug(("drop '%s' revision(s) from content db") % filename)
				self._shelve[distfile_key] = remaining
			else:
				logging.debug(("drop '%s' from content db") % filename)
				try:
					del self._shelve[distfile_key]
				except KeyError:
					pass

	def get_filenames_translate(
		self, filename: typing.Union[str, DistfileName]
	) -> typing.Generator[DistfileName, None, None]:
		"""
		Translate distfiles content digests to zero or more distfile names.
		If filename is already a distfile name, then it will pass
		through unchanged.

		A given content digest will translate to multiple distfile names if
		multiple associations have been created via the add method. The
		relationship between a content digest and a distfile name is similar
		to the relationship between an inode and a hardlink.

		@param filename: A filename listed by layout get_filenames
		"""
		if not isinstance(filename, DistfileName):
			filename = DistfileName(filename)

		# Match content digests with zero or more content revisions.
		matched_revisions = {}

		for k, v in filename.digests.items():
			digest_item = (k.upper(), v.lower())
			digest_key = "digest:{}:{}".format(*digest_item)
			try:
				digest_files = self._shelve[digest_key]
			except KeyError:
				continue

			for distfile_str in digest_files:
				matched_revisions.setdefault(distfile_str, set())
				try:
					content_revisions = self._shelve["filename:{}".format(distfile_str)]
				except KeyError:
					pass
				else:
					for revision_key in content_revisions:
						if (
							digest_item in revision_key
							and revision_key not in matched_revisions[distfile_str]
						):
							matched_revisions[distfile_str].add(revision_key)
							yield DistfileName(distfile_str, digests=dict(revision_key))

		if not any(matched_revisions.values()):
			# Since filename matched zero content revisions, allow
			# it to pass through unchanged (on the path toward deletion).
			yield filename

	def __len__(self):
		return len(self._shelve)

	def __contains__(self, k):
		return k in self._shelve

	def __iter__(self):
		return self._shelve.__iter__()

	def items(self):
		return self._shelve.items()

	def __setitem__(self, k, v):
		self._shelve[k] = v

	def __getitem__(self, k):
		return self._shelve[k]

	def __delitem__(self, k):
		del self._shelve[k]

	def get(self, k, *args):
		return self._shelve.get(k, *args)

	def close(self):
		self._shelve.close()

	def clear(self):
		self._shelve.clear()
