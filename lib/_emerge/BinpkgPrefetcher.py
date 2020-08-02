# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.BinpkgFetcher import BinpkgFetcher
from _emerge.CompositeTask import CompositeTask
from _emerge.BinpkgVerifier import BinpkgVerifier
from portage import os

class BinpkgPrefetcher(CompositeTask):

	__slots__ = ("pkg",) + \
		("pkg_path", "_bintree",)

	def _start(self):
		self._bintree = self.pkg.root_config.trees["bintree"]
		fetcher = BinpkgFetcher(background=self.background,
			logfile=self.scheduler.fetch.log_file, pkg=self.pkg,
			scheduler=self.scheduler)
		self.pkg_path = fetcher.pkg_path
		self._start_task(fetcher, self._fetcher_exit)

	def _fetcher_exit(self, fetcher):

		if self._default_exit(fetcher) != os.EX_OK:
			self.wait()
			return

		verifier = BinpkgVerifier(background=self.background,
			logfile=self.scheduler.fetch.log_file, pkg=self.pkg,
			scheduler=self.scheduler, _pkg_path=self.pkg_path)
		self._start_task(verifier, self._verifier_exit)

	def _verifier_exit(self, verifier):
		if self._default_exit(verifier) != os.EX_OK:
			self.wait()
			return

		self._bintree.inject(self.pkg.cpv, filename=self.pkg_path)

		self._current_task = None
		self.returncode = os.EX_OK
		self.wait()
