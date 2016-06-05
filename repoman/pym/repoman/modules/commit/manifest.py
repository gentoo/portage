# -*- coding:utf-8 -*-

import logging
import sys

# import our initialized portage instance
from repoman._portage import portage

from portage import os
from portage.package.ebuild.digestgen import digestgen
from portage.util import writemsg_level


class Manifest(object):
	'''Creates as well as checks pkg Manifest entries/files'''

	def __init__(self, **kwargs):
		'''Class init

		@param options: the run time cli options
		@param portdb: portdb instance
		@param repo_settings: repository settings instance
		'''
		self.options = kwargs.get('options')
		self.portdb = kwargs.get('portdb')
		self.repoman_settings = kwargs.get('repo_settings').repoman_settings
		self.generated_manifest = False

	def update_manifest(self, checkdir):
		'''Perform a manifest generation for the pkg

		@param checkdir: the current package directory
		@returns: dictionary
		'''
		self.generated_manifest = False
		self.digest_only = self.options.mode != 'manifest-check' \
			and self.options.digest == 'y'
		if self.options.mode in ("manifest", 'commit', 'fix') or self.digest_only:
			failed = False
			self.auto_assumed = set()
			fetchlist_dict = portage.FetchlistDict(
				checkdir, self.repoman_settings, self.portdb)
			if self.options.mode == 'manifest' and self.options.force:
				portage._doebuild_manifest_exempt_depend += 1
				self._create_manifest(checkdir, fetchlist_dict)
			self.repoman_settings["O"] = checkdir
			try:
				self.generated_manifest = digestgen(
					mysettings=self.repoman_settings, myportdb=self.portdb)
			except portage.exception.PermissionDenied as e:
				self.generated_manifest = False
				writemsg_level(
					"!!! Permission denied: '%s'\n" % (e,),
					level=logging.ERROR, noiselevel=-1)

			if not self.generated_manifest:
				writemsg_level(
					"Unable to generate manifest.",
					level=logging.ERROR, noiselevel=-1)
				failed = True

			if self.options.mode == "manifest":
				if not failed and self.options.force and self.auto_assumed and \
					'assume-digests' in self.repoman_settings.features:
					# Show which digests were assumed despite the --force option
					# being given. This output will already have been shown by
					# digestgen() if assume-digests is not enabled, so only show
					# it here if assume-digests is enabled.
					pkgs = list(fetchlist_dict)
					pkgs.sort()
					portage.writemsg_stdout(
						"  digest.assumed %s" %
						portage.output.colorize(
							"WARN", str(len(self.auto_assumed)).rjust(18)) + "\n")
					for cpv in pkgs:
						fetchmap = fetchlist_dict[cpv]
						pf = portage.catsplit(cpv)[1]
						for distfile in sorted(fetchmap):
							if distfile in self.auto_assumed:
								portage.writemsg_stdout(
									"   %s::%s\n" % (pf, distfile))
				# continue, skip remaining main loop code
				return True
			elif failed:
				sys.exit(1)
		return False

	def _create_manifest(self, checkdir, fetchlist_dict):
		'''Creates a Manifest file

		@param checkdir: the directory to generate the Manifest in
		@param fetchlist_dict: dictionary of files to fetch and/or include
							in the manifest
		'''
		try:
			distdir = self.repoman_settings['DISTDIR']
			mf = self.repoman_settings.repositories.get_repo_for_location(
				os.path.dirname(os.path.dirname(checkdir)))
			mf = mf.load_manifest(
				checkdir, distdir, fetchlist_dict=fetchlist_dict)
			mf.create(
				requiredDistfiles=None, assumeDistHashesAlways=True)
			for distfiles in fetchlist_dict.values():
				for distfile in distfiles:
					if os.path.isfile(os.path.join(distdir, distfile)):
						mf.fhashdict['DIST'].pop(distfile, None)
					else:
						self.auto_assumed.add(distfile)
			mf.write()
		finally:
			portage._doebuild_manifest_exempt_depend -= 1
