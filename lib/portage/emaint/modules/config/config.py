# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.const import PRIVATE_PATH
from portage.util import grabdict, writedict

class CleanConfig:

	short_desc = "Discard any no longer installed configs from emerge's tracker list"

	@staticmethod
	def name():
		return "cleanconfmem"

	def __init__(self):
		self._root = portage.settings["ROOT"]
		self.target = os.path.join(portage.settings["EROOT"], PRIVATE_PATH, 'config')

	def load_configlist(self):
		return grabdict(self.target)

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
		msgs = self._format_output(messages)
		return (True, msgs)

	def fix(self, **kwargs):
		onProgress = kwargs.get('onProgress', None)
		configs = self.load_configlist()
		messages = []
		maxval = len(configs)
		if onProgress:
			onProgress(maxval, 0)
			i = 0

		root = self._root
		if root == "/":
			root = None
		modified = False
		for config in sorted(configs):
			if root is None:
				full_path = config
			else:
				full_path = os.path.join(root, config.lstrip(os.sep))
			if not os.path.exists(full_path):
				modified = True
				configs.pop(config)
				messages.append("  %s" % config)
			if onProgress:
				onProgress(maxval, i+1)
				i += 1
		if modified:
			writedict(configs, self.target)
		msgs = self._format_output(messages, True)
		return (True, msgs)

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
