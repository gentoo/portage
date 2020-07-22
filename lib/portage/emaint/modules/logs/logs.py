# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.util import shlex_split, varexpand

## default clean command from make.globals
## PORTAGE_LOGDIR_CLEAN = 'find "${PORTAGE_LOGDIR}" -type f ! -name "summary.log*" -mtime +7 -delete'

ERROR_MESSAGES = {
	78	: "PORTAGE_LOGDIR variable not set or PORTAGE_LOGDIR not a directory.",
	127	: "PORTAGE_LOGDIR_CLEAN command not found."
}


class CleanLogs:

	short_desc = "Clean PORTAGE_LOGDIR logs"

	@staticmethod
	def name():
		return "logs"


	def can_progressbar(self, func):
		return False


	def check(self, **kwargs):
		options = kwargs.get('options', None)
		if options:
			options['pretend'] = True
		return self.clean(**kwargs)


	def clean(self, **kwargs):
		"""Log directory cleaning function

		@param **kwargs: optional dictionary of values used in this function are:
			settings: portage settings instance: defaults to portage.settings
				"PORTAGE_LOGDIR": directory to clean
				"PORTAGE_LOGDIR_CLEAN": command for cleaning the logs.
			options: dict:
				'NUM': int: number of days
				'pretend': boolean
		"""
		num_of_days = None
		pretend = False

		# convoluted, I know, but portage.settings does not exist in
		# kwargs.get() when called from _emerge.main.clean_logs()
		settings = kwargs.get('settings', getattr(portage, 'settings', {}))

		options = kwargs.get('options', None)
		if options:
			num_of_days = options.get('NUM', None)
			pretend = options.get('pretend', False)

		clean_cmd = settings.get("PORTAGE_LOGDIR_CLEAN")
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
		logdir = settings.get("PORTAGE_LOGDIR")
		if logdir is None or not os.path.isdir(logdir):
			return 78

		variables = {"PORTAGE_LOGDIR" : logdir}
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
				msg.append("PORTAGE_LOGDIR_CLEAN command returned %s" % rval)
			msg.append("See the make.conf(5) man page for "
				"PORTAGE_LOGDIR_CLEAN usage instructions.")
		return msg
