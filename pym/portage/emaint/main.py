# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function


import sys
import textwrap
from optparse import OptionParser, OptionValueError


import portage
from portage import os
from portage.emaint.module import Modules
from portage.emaint.progress import ProgressBar
from portage.emaint.defaults import DEFAULT_OPTIONS

class OptionItem(object):
	"""class to hold module OptionParser options data
	"""

	def __init__(self, opt, parser):
		"""
		@type opt: dictionary
		@param opt: options parser options
		"""
		self.parser = parser
		self.short = opt['short']
		self.long = opt['long']
		self.help = opt['help']
		self.status = opt['status']
		self.func = opt['func']
		self.action = opt.get('action', "callback")
		self.type = opt.get('type', None)
		self.dest = opt.get('dest', None)
		self.callback = opt.get('callback', self._exclusive)
		self.callback_kwargs = opt.get('callback_kwargs', {"var":"action"})


	def _exclusive(self, option, *args, **kw):
		"""Generic check for the 2 default options
		"""
		var = kw.get("var", None)
		if var is None:
			raise ValueError("var not specified to exclusive()")
		if getattr(self.parser, var, ""):
			raise OptionValueError("%s and %s are exclusive options"
				% (getattr(self.parser, var), option))
		setattr(self.parser, var, str(option))

	def check_action(self, action):
		"""Checks if 'action' is the same as this option

		@type action: string
		@param action: the action to compare
		@rtype: boolean
		"""
		if action == self.action:
			return True
		elif action == '/'.join([self.short, self.long]):
			return True
		return False


def usage(module_controller):
		_usage = "usage: emaint [options] COMMAND"

		desc = "The emaint program provides an interface to system health " + \
			"checks and maintenance. See the emaint(1) man page " + \
			"for additional information about the following commands:"

		_usage += "\n\n"
		for line in textwrap.wrap(desc, 65):
			_usage += "%s\n" % line
		_usage += "\nCommands:\n"
		_usage += "  %s" % "all".ljust(15) + \
			"Perform all supported commands\n"
		textwrap.subsequent_indent = ' '.ljust(17)
		for mod in module_controller.module_names:
			desc = textwrap.wrap(module_controller.get_description(mod), 65)
			_usage += "  %s%s\n" % (mod.ljust(15), desc[0])
			for d in desc[1:]:
				_usage += "  %s%s\n" % (' '.ljust(15), d)
		return _usage


def module_opts(module_controller, module):
	_usage = " %s module options:\n" % module
	opts = module_controller.get_func_descriptions(module)
	if opts == {}:
		opts = DEFAULT_OPTIONS
	for opt in sorted(opts):
		optd = opts[opt]
		opto = "  %s, %s" %(optd['short'], optd['long'])
		_usage += '%s %s\n' % (opto.ljust(15),optd['help'])
	_usage += '\n'
	return _usage


class TaskHandler(object):
	"""Handles the running of the tasks it is given
	"""

	def __init__(self, show_progress_bar=True, verbose=True, callback=None):
		self.show_progress_bar = show_progress_bar
		self.verbose = verbose
		self.callback = callback
		self.isatty = os.environ.get('TERM') != 'dumb' and sys.stdout.isatty()
		self.progress_bar = ProgressBar(self.isatty, title="Emaint", max_desc_length=27)


	def run_tasks(self, tasks, func, status=None, verbose=True, options=None):
		"""Runs the module tasks"""
		if tasks is None or func is None:
			return
		for task in tasks:
			inst = task()
			show_progress = self.show_progress_bar and self.isatty
			# check if the function is capable of progressbar 
			# and possibly override it off
			if show_progress and hasattr(inst, 'can_progressbar'):
				show_progress = inst.can_progressbar(func)
			if show_progress:
				self.progress_bar.reset()
				self.progress_bar.set_label(func + " " + inst.name())
				onProgress = self.progress_bar.start()
			else:
				onProgress = None
			kwargs = {
				'onProgress': onProgress,
				# pass in a copy of the options so a module can not pollute or change
				# them for other tasks if there is more to do.
				'options': options.copy()
				}
			result = getattr(inst, func)(**kwargs)
			if show_progress:
				# make sure the final progress is displayed
				self.progress_bar.display()
				print()
				self.progress_bar.stop()
			if self.callback:
				self.callback(result)


def print_results(results):
	if results:
		print()
		print("\n".join(results))
		print("\n")


def emaint_main(myargv):

	# Similar to emerge, emaint needs a default umask so that created
	# files (such as the world file) have sane permissions.
	os.umask(0o22)

	module_controller = Modules(namepath="portage.emaint.modules")
	module_names = module_controller.module_names[:]
	module_names.insert(0, "all")


	parser = OptionParser(usage=usage(module_controller), version=portage.VERSION)
	# add default options
	parser_options = []
	for opt in DEFAULT_OPTIONS:
		parser_options.append(OptionItem(DEFAULT_OPTIONS[opt], parser))
	for mod in module_names[1:]:
		desc = module_controller.get_func_descriptions(mod)
		if desc:
			for opt in desc:
				parser_options.append(OptionItem(desc[opt], parser))
	for opt in parser_options:
		parser.add_option(opt.short, opt.long, help=opt.help, action=opt.action,
		type=opt.type, dest=opt.dest,
			callback=opt.callback, callback_kwargs=opt.callback_kwargs)

	parser.action = None

	(options, args) = parser.parse_args(args=myargv)
	#print('options', options, '\nargs', args, '\naction', parser.action)
	if len(args) != 1:
		parser.error("Incorrect number of arguments")
	if args[0] not in module_names:
		parser.error("%s target is not a known target" % args[0])

	if parser.action:
		action = parser.action
	else:
		action = "-c/--check"
	long_action = action.split('/')[1].lstrip('-')
	#print("DEBUG: action = ", action, long_action)

	if args[0] == "all":
		tasks = []
		for m in module_names[1:]:
			#print("DEBUG: module: %s, functions: " %(m, str(module_controller.get_functions(m))))
			if long_action in module_controller.get_functions(m):
				tasks.append(module_controller.get_class(m))
	elif long_action in module_controller.get_functions(args[0]):
		tasks = [module_controller.get_class(args[0] )]
	else:
		print("\nERROR: module '%s' does not have option '%s'\n" %(args[0], action))
		print(module_opts(module_controller, args[0]))
		sys.exit(1)
	func = status = None
	for opt in parser_options:
		if opt.check_action(action):
			status = opt.status
			func = opt.func
			break

	# need to pass the parser options dict to the modules
	# so they are available if needed.
	task_opts = options.__dict__
	taskmaster = TaskHandler(callback=print_results)
	taskmaster.run_tasks(tasks, func, status, options=task_opts)

