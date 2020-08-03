# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

class DependencyArg:

	__slots__ = ('arg', 'force_reinstall', 'internal', 'reset_depth', 'root_config')

	def __init__(self, arg=None, force_reinstall=False, internal=False,
		reset_depth=True, root_config=None):
		"""
		Use reset_depth=False for special arguments that should not interact
		with depth calculations (see the emerge --deep=DEPTH option).
		"""
		self.arg = arg
		self.force_reinstall = force_reinstall
		self.internal = internal
		self.reset_depth = reset_depth
		self.root_config = root_config

	def __eq__(self, other):
		if self.__class__ is not other.__class__:
			return False
		return self.arg == other.arg and \
			self.root_config.root == other.root_config.root

	def __hash__(self):
		return hash((self.arg, self.root_config.root))

	def __str__(self):
		return "%s" % (self.arg,)
