# Copyright 2005-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.exception import PortageException
from portage.cache.mappings import ProtectedDict
from portage.localization import _
from portage.util import writemsg


class InvalidModuleName(PortageException):
	"""An invalid or unknown module name."""


class ModuleVersionError(PortageException):
	'''An incompatible module version'''


class Module:
	"""Class to define and hold our plug-in module

	@type name: string
	@param name: the module name
	@type path: the path to the new module
	"""

	def __init__(self, name, namepath):
		"""Some variables initialization"""
		self.name = name
		self._namepath = namepath
		self.kids_names = []
		self.kids = {}
		self.initialized = self._initialize()

	def _initialize(self):
		"""Initialize the plug-in module

		@rtype: boolean
		"""
		self.valid = False
		try:
			mod_name = ".".join([self._namepath, self.name])
			self._module = __import__(mod_name, [], [], ["not empty"])
			self.valid = True
		except ImportError as e:
			print("MODULE; failed import", mod_name, "  error was:", e)
			return False
		self.module_spec = self._module.module_spec
		for submodule in self.module_spec['provides']:
			kid = self.module_spec['provides'][submodule]
			kidname = kid['name']
			try:
				kid['module_name'] = '.'.join([mod_name, kid['sourcefile']])
			except KeyError:
				kid['module_name'] = '.'.join([mod_name, self.name])
				msg = ("%s module's module_spec is old, missing attribute: "
						"'sourcefile'.  Backward compatibility may be "
						"removed in the future.\nFile: %s\n")
				writemsg(_(msg) % (self.name, self._module.__file__))
			kid['is_imported'] = False
			self.kids[kidname] = kid
			self.kids_names.append(kidname)
		return True

	def get_class(self, name):
		if not name or name not in self.kids_names:
			raise InvalidModuleName("Module name '%s' is invalid or not"
				%name + "part of the module '%s'" %self.name)
		kid = self.kids[name]
		if kid['is_imported']:
			module = kid['instance']
		else:
			try:
				module = __import__(kid['module_name'], [], [], ["not empty"])
				kid['instance'] = module
				kid['is_imported'] = True
			except ImportError:
				raise
		mod_class = getattr(module, kid['class'])
		return mod_class


class Modules:
	"""Dynamic modules system for loading and retrieving any of the
	installed emaint modules and/or provided class's

	@param path: Path to the "modules" directory
	@param namepath: Python import path to the "modules" directory
	"""

	def __init__(self, path, namepath, compat_versions=None):
		self._module_path = path
		self._namepath = namepath
		self.compat_versions = compat_versions
		self.parents = []
		self._modules = self._get_all_modules()
		self.modules = ProtectedDict(self._modules)
		self.module_names = sorted(self._modules)

	def _get_all_modules(self):
		"""scans the _module_path dir for loadable modules

		@rtype: dictionary of module_plugins
		"""
		module_dir =  self._module_path
		importables = []
		names = os.listdir(module_dir)
		for entry in names:
			# skip any __init__ or __pycache__ files or directories
			if entry.startswith('__'):
				continue
			try:
				# test for statinfo to ensure it should a real module
				# it will bail if it errors
				os.lstat(os.path.join(module_dir, entry, '__init__.py'))
				importables.append(entry)
			except EnvironmentError:
				pass
		kids = {}
		for entry in importables:
			new_module = Module(entry, self._namepath)
			self._check_compat(new_module)
			for module_name in new_module.kids:
				kid = new_module.kids[module_name]
				kid['parent'] = new_module
				kids[kid['name']] = kid
			self.parents.append(entry)
		return kids

	def get_module_names(self):
		"""Convenience function to return the list of installed modules
		available

		@rtype: list
		@return: the installed module names available
		"""
		return self.module_names

	def get_class(self, modname):
		"""Retrieves a module class desired

		@type modname: string
		@param modname: the module class name
		"""
		if modname and modname in self.module_names:
			mod = self._modules[modname]['parent'].get_class(modname)
		else:
			raise InvalidModuleName("Module name '%s' is invalid or not"
				%modname + "found")
		return mod

	def get_description(self, modname):
		"""Retrieves the module class decription

		@type modname: string
		@param modname: the module class name
		@type string
		@return: the modules class decription
		"""
		if modname and modname in self.module_names:
			mod = self._modules[modname]['description']
		else:
			raise InvalidModuleName("Module name '%s' is invalid or not"
				%modname + "found")
		return mod

	def get_functions(self, modname):
		"""Retrieves the module class  exported function names

		@type modname: string
		@param modname: the module class name
		@type list
		@return: the modules class exported function names
		"""
		if modname and modname in self.module_names:
			mod = self._modules[modname]['functions']
		else:
			raise InvalidModuleName("Module name '%s' is invalid or not"
				%modname + "found")
		return mod

	def get_func_descriptions(self, modname):
		"""Retrieves the module class  exported functions descriptions

		@type modname: string
		@param modname: the module class name
		@type dictionary
		@return: the modules class exported functions descriptions
		"""
		if modname and modname in self.module_names:
			desc = self._modules[modname]['func_desc']
		else:
			raise InvalidModuleName("Module name '%s' is invalid or not"
				%modname + "found")
		return desc

	def get_opt_descriptions(self, modname):
		"""Retrieves the module class exported options descriptions

		@type modname: string
		@param modname: the module class name
		@type dictionary
		@return: the modules class exported options descriptions
		"""
		if modname and modname in self.module_names:
			desc = self._modules[modname].get('opt_desc')
		else:
			raise InvalidModuleName(
				"Module name '%s' is invalid or not found" % modname)
		return desc

	def get_spec(self, modname, var):
		"""Retrieves the module class exported spec variable

		@type modname: string
		@param modname: the module class name
		@type var: string
		@param var: the base level variable to return
		@type dictionary
		@return: the modules class exported options descriptions
		"""
		if modname and modname in self.module_names:
			value = self._modules[modname].get(var, None)
		else:
			raise InvalidModuleName(
				"Module name '%s' is invalid or not found" % modname)
		return value

	def _check_compat(self, module):
		if self.compat_versions:
			if not module.module_spec['version'] in self.compat_versions:
				raise ModuleVersionError(
					"Error loading '%s' plugin module: %s, version: %s\n"
					"Module is not compatible with the current application version\n"
					"Compatible module API versions are: %s"
					% (self._namepath, module.module_spec['name'],
						module.module_spec['version'], self.compat_versions))
