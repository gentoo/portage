# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.dep import use_reduce
from portage.exception import PortageException
from portage.manifest import Manifest
from .FetchTask import FetchTask

class FetchIterator(object):

	def __init__(self, config):
		self._config = config
		self._log_failure = config.log_failure

	def _iter_every_cp(self):
		# List categories individually, in order to start yielding quicker,
		# and in order to reduce latency in case of a signal interrupt.
		cp_all = self._config.portdb.cp_all
		for category in sorted(self._config.portdb.categories):
			for cp in cp_all(categories=(category,)):
				yield cp

	def __iter__(self):

		portdb = self._config.portdb
		file_owners = self._config.file_owners
		file_failures = self._config.file_failures
		restrict_mirror_exemptions = self._config.restrict_mirror_exemptions

		for cp in self._iter_every_cp():

			for tree in portdb.porttrees:

				# Reset state so the Manifest is pulled once
				# for this cp / tree combination.
				digests = None

				for cpv in portdb.cp_list(cp, mytree=tree):

					try:
						restrict, = portdb.aux_get(cpv, ("RESTRICT",),
							mytree=tree)
					except (KeyError, PortageException) as e:
						self._log_failure("%s\t\taux_get exception %s" %
							(cpv, e))
						continue

					# Here we use matchnone=True to ignore conditional parts
					# of RESTRICT since they don't apply unconditionally.
					# Assume such conditionals only apply on the client side.
					try:
						restrict = frozenset(use_reduce(restrict,
							flat=True, matchnone=True))
					except PortageException as e:
						self._log_failure("%s\t\tuse_reduce exception %s" %
							(cpv, e))
						continue

					if "fetch" in restrict:
						continue

					try:
						uri_map = portdb.getFetchMap(cpv)
					except PortageException as e:
						self._log_failure("%s\t\tgetFetchMap exception %s" %
							(cpv, e))
						continue

					if not uri_map:
						continue

					if "mirror" in restrict:
						skip = False
						if restrict_mirror_exemptions is not None:
							new_uri_map = {}
							for filename, uri_tuple in uri_map.items():
								for uri in uri_tuple:
									if uri[:9] == "mirror://":
										i = uri.find("/", 9)
										if i != -1 and uri[9:i].strip("/") in \
											restrict_mirror_exemptions:
											new_uri_map[filename] = uri_tuple
											break
							if new_uri_map:
								uri_map = new_uri_map
							else:
								skip = True
						else:
							skip = True

						if skip:
							continue

					# Parse Manifest for this cp if we haven't yet.
					if digests is None:
						try:
							digests = Manifest(os.path.join(
								tree, cp)).getTypeDigests("DIST")
						except (EnvironmentError, PortageException) as e:
							for filename in uri_map:
								self._log_failure(
									"%s\t%s\tManifest exception %s" %
									(cpv, filename, e))
								file_failures[filename] = cpv
							continue

					if not digests:
						for filename in uri_map:
							self._log_failure("%s\t%s\tdigest entry missing" %
								(cpv, filename))
							file_failures[filename] = cpv
						continue

					for filename, uri_tuple in uri_map.items():
						file_digests = digests.get(filename)
						if file_digests is None:
							self._log_failure("%s\t%s\tdigest entry missing" %
								(cpv, filename))
							file_failures[filename] = cpv
							continue
						if filename in file_owners:
							continue
						file_owners[filename] = cpv

						yield FetchTask(cpv=cpv,
							background=True,
							digests=file_digests,
							distfile=filename,
							restrict=restrict,
							uri_tuple=uri_tuple,
							config=self._config)
