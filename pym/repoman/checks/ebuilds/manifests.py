# -*- coding:utf-8 -*-

import logging
import sys

# import our initialized portage instance
from repoman._portage import portage

from portage import os
from portage.package.ebuild.digestgen import digestgen
from portage.util import writemsg_level


class Manifests(object):

	def __init__(self, options, qatracker=None, repoman_settings=None):
		self.options = options
		self.qatracker = qatracker
		self.repoman_settings = repoman_settings
		self.generated_manifest = False

	def run(self, checkdir, portdb):
		self.generated_manifest = False
		self.digest_only = self.options.mode != 'manifest-check' \
			and self.options.digest == 'y'
		if self.options.pretend:
			return False
		if self.options.mode in ("manifest", 'commit', 'fix') or self.digest_only:
			failed = False
			self.auto_assumed = set()
			fetchlist_dict = portage.FetchlistDict(
				checkdir, self.repoman_settings, portdb)
			if self.options.mode == 'manifest' and self.options.force:
				portage._doebuild_manifest_exempt_depend += 1
				self.create_manifest(checkdir, fetchlist_dict)
			self.repoman_settings["O"] = checkdir
			try:
				self.generated_manifest = digestgen(
					mysettings=self.repoman_settings, myportdb=portdb)
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

	def create_manifest(self, checkdir, fetchlist_dict):
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

	def digest_check(self, xpkg, checkdir):
		self.repoman_settings['O'] = checkdir
		self.repoman_settings['PORTAGE_QUIET'] = '1'
		if not portage.digestcheck([], self.repoman_settings, strict=1):
			self.qatracker.add_error("manifest.bad", os.path.join(xpkg, 'Manifest'))
		self.repoman_settings.pop('PORTAGE_QUIET', None)
