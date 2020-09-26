# Copyright 2005-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import sys
import textwrap

import portage
from portage import os
from portage.module import Modules
from portage.progress import ProgressBar
from portage.emaint.defaults import DEFAULT_OPTIONS

class OptionItem:
	"""class to hold module ArgumentParser options data
	"""

	def __init__(self, opt):
		"""
		@type opt: dictionary
		@param opt: options parser options
		"""
		self.short = opt.get('short')
		self.long = opt.get('long')
		# '-' are not allowed in python identifiers
		# so store the sanitized target variable name
		self.target = self.long[2:].replace('-','_')
		self.help = opt.get('help')
		self.status = opt.get('status')
		self.func = opt.get('func')
		self.action = opt.get('action')
		self.type = opt.get('type')
		self.dest = opt.get('dest')
		self.choices = opt.get('choices')

	@property
	def pargs(self):
		pargs = []
		if self.short is not None:
			pargs.append(self.short)
		if self.long is not None:
			pargs.append(self.long)
		return pargs

	@property
	def kwargs(self):
		# Support for keyword arguments varies depending on the action,
		# so only pass in the keywords that are needed, in order
		# to avoid a TypeError.
		kwargs = {}
		if self.help is not None:
			kwargs['help'] = self.help
		if self.action is not None:
			kwargs['action'] = self.action
		if self.type is not None:
			kwargs['type'] = self.type
		if self.dest is not None:
			kwargs['dest'] = self.dest
		if self.choices is not None:
			kwargs['choices'] = self.choices
		return kwargs

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
		if 'short' in optd:
			opto = "  %s, %s" % (optd['short'], optd['long'])
		else:
			opto = "  %s" % (optd['long'],)
		_usage += '%s %s\n' % (opto.ljust(15), optd['help'])
	_usage += '\n'
	return _usage


class TaskHandler:
	"""Handles the running of the tasks it is given"""

	def __init__(self, show_progress_bar=True, verbose=True, callback=None, module_output=None):
		self.show_progress_bar = show_progress_bar
		self.verbose = verbose
		self.callback = callback
		self.module_output = module_output
		self.isatty = os.environ.get('TERM') != 'dumb' and sys.stdout.isatty()
		self.progress_bar = ProgressBar(self.isatty, title="Emaint", max_desc_length=27)

	def run_tasks(self, tasks, func, status=None, verbose=True, options=None):
		"""Runs the module tasks"""
		if tasks is None or func is None:
			return
		returncodes = []
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
				'module_output': self.module_output,
				# pass in a copy of the options so a module can not pollute or change
				# them for other tasks if there is more to do.
				'options': options.copy()
				}
			returncode, msgs = getattr(inst, func)(**kwargs)
			returncodes.append(returncode)
			if show_progress:
				# make sure the final progress is displayed
				self.progress_bar.display()
				print()
				self.progress_bar.stop()
			if self.callback:
				self.callback(msgs)

		return returncodes


def print_results(results):
	if results:
		print()
		print("\n".join(results))
		print("\n")


def emaint_main(myargv):

	# Similar to emerge, emaint needs a default umask so that created
	# files (such as the world file) have sane permissions.
	os.umask(0o22)

	module_path = os.path.join(
		(os.path.dirname(
		os.path.realpath(__file__))), "modules"
		)
	module_controller = Modules(
		path=module_path,
		namepath="portage.emaint.modules")
	module_names = module_controller.module_names[:]
	module_names.insert(0, "all")

	parser = argparse.ArgumentParser(usage=usage(module_controller))
	# add default options
	parser_options = []
	for opt in DEFAULT_OPTIONS:
		parser_options.append(OptionItem(DEFAULT_OPTIONS[opt]))
	for mod in module_names[1:]:
		desc = module_controller.get_func_descriptions(mod)
		if desc:
			for opt in desc:
				parser_options.append(OptionItem(desc[opt]))
		desc = module_controller.get_opt_descriptions(mod)
		if desc:
			for opt in desc:
				parser_options.append(OptionItem(desc[opt]))
	for opt in parser_options:
		parser.add_argument(*opt.pargs, **opt.kwargs)

	options, args = parser.parse_known_args(args=myargv)

	if options.version:
		print(portage.VERSION)
		return os.EX_OK

	if len(args) != 1:
		parser.error("Incorrect number of arguments")
	if args[0] not in module_names:
		parser.error("%s target is not a known target" % args[0])

	check_opt = None
	func = status = long_action = None
	for opt in parser_options:
		if opt.long == '--check':
			# Default action
			check_opt = opt
		if opt.status and getattr(options, opt.target, False):
			if long_action is not None:
				parser.error("--%s and %s are exclusive options" %
					(long_action, opt.long))
			status = opt.status
			func = opt.func
			long_action = opt.long.lstrip('-')

	if long_action is None:
		#print("DEBUG: long_action is None: setting to 'check'")
		long_action = 'check'
		func = check_opt.func
		status = check_opt.status

	if args[0] == "all":
		tasks = []
		for m in module_names[1:]:
			#print("DEBUG: module: %s, functions: " % (m, str(module_controller.get_functions(m))))
			if long_action in module_controller.get_functions(m):
				tasks.append(module_controller.get_class(m))
	elif long_action in module_controller.get_functions(args[0]):
		tasks = [module_controller.get_class(args[0] )]
	else:
		portage.util.writemsg(
			"\nERROR: module '%s' does not have option '--%s'\n\n" %
			(args[0], long_action), noiselevel=-1)
		portage.util.writemsg(module_opts(module_controller, args[0]),
			noiselevel=-1)
		sys.exit(1)

	# need to pass the parser options dict to the modules
	# so they are available if needed.
	task_opts = options.__dict__
	task_opts['return-messages'] = True
	taskmaster = TaskHandler(callback=print_results, module_output=sys.stdout)
	returncodes = taskmaster.run_tasks(tasks, func, status, options=task_opts)

	sys.exit(False in returncodes)
