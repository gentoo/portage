# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'glib',
)

class GlibEventLoop(object):

	# TODO: Support multiprocessing by using a separate glib.MainContext
	# instance for each process.
	supports_multiprocessing = False

	def __init__(self):
		self.iteration = glib.main_context_default().iteration
		self.idle_add = glib.idle_add
		self.io_add_watch = glib.io_add_watch
		self.timeout_add = glib.timeout_add
		self.source_remove = glib.source_remove
