# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.util import shlex_split, varexpand

## default clean command from make.globals
## PORT_LOGDIR_CLEAN = 'find "${PORT_LOGDIR}" -type f ! -name "summary.log*" -mtime +7 -delete'

ERROR_MESSAGES = {
	78	: "PORT_LOGDIR variable not set or PORT_LOGDIR not a directory.",
	127	: "PORT_LOGDIR_CLEAN command not found."
}


class CleanLogs(object):

	short_desc = "Clean PORT_LOGDIR logs"

	@staticmethod
	def name():
		return "logs"


	def can_progressbar(self, func):
		return False


	def check(self, **kwargs):
		msgs = []
		if kwargs:
			options = kwargs.get('options', None)
			settings = kwargs.get('settings', None)
			if not settings:
				settings = portage.settings
		else:
			settings = portage.settings
		if options:
			return_messages = options.get("return-messages", False)
		else:
			return_messages = False

		logdir = settings.get("PORT_LOGDIR", None)
		if logdir is None or not os.path.isdir(logdir):
			if return_messages:
				msgs.append(ERROR_MESSAGES[78])
				msgs.append("See the make.conf(5) man page for PORT_LOGDIR usage instructions.")
				return (False, msgs)
			else:
				return (False, None)

		clean_cmd = settings.get("PORT_LOGDIR_CLEAN", "")
		if not clean_cmd:
			msgs.append("PORT_LOGDIR_CLEAN variable not set.")
			msgs.append("See the make.conf(5) man page for PORT_LOGDIR_CLEAN usage instructions.")
		clean_cmd = shlex_split(clean_cmd)
		if options and "NUM" in options and options["NUM"] is not None:
			mtime = "-mtime +%d" % (options["NUM"])
		elif "-mtime" in clean_cmd:
			mtime = "-mtime %s" % (clean_cmd[clean_cmd.index("-mtime") + 1])
		else:
			mtime = None
		print_cmd = 'find ${PORT_LOGDIR} -type f ! -name "summary.log*" %s' % \
			("" if mtime is None else mtime)
		print_cmd = shlex_split(print_cmd)
		rval = self._clean_logs(print_cmd, settings)
		if rval != os.EX_OK:
			if return_messages:
				msgs.extend(self._convert_errors(rval))
				return (False, msgs)
			else:
				return (False, None)

		if return_messages:
			return (True, msgs)
		return (True, None)


	def clean(self, **kwargs):
		"""Log directory cleaning function

		@param **kwargs: optional dictionary of values used in this function are:
			settings: portage settings instance: defaults to portage.settings
				"PORT_LOGDIR": directory to clean
				"PORT_LOGDIR_CLEAN": command for cleaning the logs.
			options: dict:
				'NUM': int: number of days
				'pretend': boolean
		"""
		num_of_days = None
		pretend = False
		if kwargs:
			# convuluted, I know, but portage.settings does not exist in
			# kwargs.get() when called from _emerge.main.clean_logs()
			settings = kwargs.get('settings', None)
			if not settings:
				settings = portage.settings
			options = kwargs.get('options', None)
			if options:
				num_of_days = options.get('NUM', None)
				pretend = options.get('pretend', False)

		clean_cmd = settings.get("PORT_LOGDIR_CLEAN")
		if clean_cmd:
			clean_cmd = shlex_split(clean_cmd)
			if '-mtime' in clean_cmd and num_of_days is not None:
				if num_of_days == 0:
					i = clean_cmd.index('-mtime')
					clean_cmd.remove('-mtime')
					clean_cmd.pop(i)
				else:
					clean_cmd[clean_cmd.index('-mtime') +1] = \
						'+%s' % str(num_of_days)
			if pretend:
				if "-delete" in clean_cmd:
					clean_cmd.remove("-delete")

		if not clean_cmd:
			return (True, None)
		rval = self._clean_logs(clean_cmd, settings)
		errors = self._convert_errors(rval)
		if errors:
			return (False, errors)
		return (True, None)


	@staticmethod
	def _clean_logs(clean_cmd, settings):
		logdir = settings.get("PORT_LOGDIR")
		if logdir is None or not os.path.isdir(logdir):
			return 78

		variables = {"PORT_LOGDIR" : logdir}
		cmd = [varexpand(x, mydict=variables) for x in clean_cmd]

		try:
			rval = portage.process.spawn(cmd, env=os.environ)
		except portage.exception.CommandNotFound:
			rval = 127
		return rval


	@staticmethod
	def _convert_errors(rval):
		msg = []
		if rval != os.EX_OK:
			if rval in ERROR_MESSAGES:
				msg.append(ERROR_MESSAGES[rval])
			else:
				msg.append("PORT_LOGDIR_CLEAN command returned %s" % rval)
			msg.append("See the make.conf(5) man page for "
				"PORT_LOGDIR_CLEAN usage instructions.")
		return msg
