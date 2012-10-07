# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile

from portage import os
from portage import shutil
from portage.const import EBUILD_PHASES
from portage.elog import elog_process
from portage.package.ebuild.config import config
from portage.package.ebuild.doebuild import doebuild_environment
from portage.package.ebuild.prepare_build_dirs import prepare_build_dirs
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.EventLoop import EventLoop
from _emerge.EbuildPhase import EbuildPhase

def spawn_nofetch(portdb, ebuild_path, settings=None):
	"""
	This spawns pkg_nofetch if appropriate. The settings parameter
	is useful only if setcpv has already been called in order
	to cache metadata. It will be cloned internally, in order to
	prevent any changes from interfering with the calling code.
	If settings is None then a suitable config instance will be
	acquired from the given portdbapi instance. Do not use the
	settings parameter unless setcpv has been called on the given
	instance, since otherwise it's possible to trigger issues like
	bug #408817 due to fragile assumptions involving the config
	state inside doebuild_environment().

	A private PORTAGE_BUILDDIR will be created and cleaned up, in
	order to avoid any interference with any other processes.
	If PORTAGE_TMPDIR is writable, that will be used, otherwise
	the default directory for the tempfile module will be used.

	We only call the pkg_nofetch phase if either RESTRICT=fetch
	is set or the package has explicitly overridden the default
	pkg_nofetch implementation. This allows specialized messages
	to be displayed for problematic packages even though they do
	not set RESTRICT=fetch (bug #336499).

	This function does nothing if the PORTAGE_PARALLEL_FETCHONLY
	variable is set in the config instance.
	"""

	if settings is None:
		settings = config(clone=portdb.settings)
	else:
		settings = config(clone=settings)

	if 'PORTAGE_PARALLEL_FETCHONLY' in settings:
		return

	# We must create our private PORTAGE_TMPDIR before calling
	# doebuild_environment(), since lots of variables such
	# as PORTAGE_BUILDDIR refer to paths inside PORTAGE_TMPDIR.
	portage_tmpdir = settings.get('PORTAGE_TMPDIR')
	if not portage_tmpdir or not os.access(portage_tmpdir, os.W_OK):
		portage_tmpdir = None
	private_tmpdir = tempfile.mkdtemp(dir=portage_tmpdir)
	settings['PORTAGE_TMPDIR'] = private_tmpdir
	settings.backup_changes('PORTAGE_TMPDIR')
	# private temp dir was just created, so it's not locked yet
	settings.pop('PORTAGE_BUILDIR_LOCKED', None)

	try:
		doebuild_environment(ebuild_path, 'nofetch',
			settings=settings, db=portdb)
		restrict = settings['PORTAGE_RESTRICT'].split()
		defined_phases = settings['DEFINED_PHASES'].split()
		if not defined_phases:
			# When DEFINED_PHASES is undefined, assume all
			# phases are defined.
			defined_phases = EBUILD_PHASES

		if 'fetch' not in restrict and \
			'nofetch' not in defined_phases:
			return

		prepare_build_dirs(settings=settings)
		ebuild_phase = EbuildPhase(background=False,
			phase='nofetch',
			scheduler=SchedulerInterface(EventLoop(main=False)),
			settings=settings)
		ebuild_phase.start()
		ebuild_phase.wait()
		elog_process(settings.mycpv, settings)
	finally:
		shutil.rmtree(private_tmpdir)
