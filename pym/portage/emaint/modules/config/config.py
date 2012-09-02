# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.const import PRIVATE_PATH


class CleanConfig(object):

	short_desc = "Discard any no longer installed configs from emerge's tracker list"

	def __init__(self):
		self.target = os.path.join(portage.settings["EROOT"], PRIVATE_PATH, 'config')

	def name():
		return "cleanconfmem"
	name = staticmethod(name)

	def load_configlist(self):
		
		configs = {}
		with open(self.target, 'r') as configfile:
			lines = configfile.readlines()
		for line in lines:
			ls = line.split()
			configs[ls[0]] = ls[1]
		return configs

	def check(self,  **kwargs):
		onProgress = kwargs.get('onProgress', None)
		configs = self.load_configlist()
		messages = []
		maxval = len(configs)
		if onProgress:
			onProgress(maxval, 0)
			i = 0
		keys = sorted(configs)
		for config in keys:
			if not os.path.exists(config):
				messages.append("  %s" % config)
			if onProgress:
				onProgress(maxval, i+1)
				i += 1
		return self._format_output(messages)

	def fix(self, **kwargs):
		onProgress = kwargs.get('onProgress', None)
		configs = self.load_configlist()
		messages = []
		maxval = len(configs)
		if onProgress:
			onProgress(maxval, 0)
			i = 0
		keys = sorted(configs)
		for config in keys:
			if not os.path.exists(config):
				configs.pop(config)
				messages.append("  %s" % config)
			if onProgress:
				onProgress(maxval, i+1)
				i += 1
		lines = []
		keys = sorted(configs)
		for key in keys:
			line = ' '.join([key, configs[key]])
			lines.append(line)
		lines.append('')
		with open(self.target, 'w') as configfile:
			configfile.write('\n'.join(lines))
		return self._format_output(messages, True)

	def _format_output(self, messages=[], cleaned=False):
		output = []
		if messages:
			output.append('Not Installed:')
			output += messages
			tot = '------------------------------------\n  Total %i Not installed'
			if cleaned:
				tot += ' ...Cleaned'
			output.append(tot  % len(messages))
		return output
