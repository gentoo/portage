# Copyright 2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['lazyimport']

import sys
import types

try:
	import threading
except ImportError:
	import dummy_threading as threading

from portage.proxy.objectproxy import ObjectProxy

if sys.hexversion >= 0x3000000:
	basestring = str

_module_proxies = {}
_module_proxies_lock = threading.RLock()

def _preload_portage_submodules():
	"""
	Load lazily referenced portage submodules into memory,
	so imports won't fail during portage upgrade/downgrade.
	Note that this recursively loads only the modules that
	are lazily referenced by currently imported modules,
	so some portage submodules may still remain unimported
	after this function is called.
	"""
	while True:
		remaining = False
		for name in list(_module_proxies):
			if name.startswith('portage.'):
				remaining = True
				_unregister_module_proxy(name)
		if not remaining:
			break

def _register_module_proxy(name, proxy):
	_module_proxies_lock.acquire()
	try:
		proxy_list = _module_proxies.get(name)
		if proxy_list is None:
			proxy_list = []
			_module_proxies[name] = proxy_list
		proxy_list.append(proxy)
	finally:
		_module_proxies_lock.release()

def _unregister_module_proxy(name):
	"""
	Destroy all proxies that reference the give module name. Also, check
	for other proxies referenced by modules that have been imported and
	destroy those proxies too. This way, destruction of a single proxy
	can trigger destruction of all the rest.
	"""
	_module_proxies_lock.acquire()
	try:
		proxy_list = _module_proxies.get(name)
		if proxy_list is not None:
			# First delete this name from the dict so that
			# if this same thread reenters below, it won't
			# enter this path again.
			del _module_proxies[name]
			for proxy in proxy_list:
				object.__getattribute__(proxy, '_get_target')()

			modules = sys.modules
			for name, proxy_list in list(_module_proxies.items()):
				if name not in modules:
					continue
				# First delete this name from the dict so that
				# if this same thread reenters below, it won't
				# enter this path again.
				del _module_proxies[name]
				for proxy in proxy_list:
					object.__getattribute__(proxy, '_get_target')()
	finally:
		_module_proxies_lock.release()

class _LazyImport(ObjectProxy):

	__slots__ = ('_scope', '_alias', '_name', '_target')

	def __init__(self, scope, alias, name):
		ObjectProxy.__init__(self)
		object.__setattr__(self, '_scope', scope)
		object.__setattr__(self, '_alias', alias)
		object.__setattr__(self, '_name', name)
		_register_module_proxy(name, self)

	def _get_target(self):
		try:
			return object.__getattribute__(self, '_target')
		except AttributeError:
			pass
		name = object.__getattribute__(self, '_name')
		__import__(name)
		target = sys.modules[name]
		object.__setattr__(self, '_target', target)
		object.__getattribute__(self, '_scope')[
			object.__getattribute__(self, '_alias')] = target
		_unregister_module_proxy(name)
		return target

class _LazyImportFrom(_LazyImport):

	__slots__ = ('_attr_name',)

	def __init__(self, scope, name, attr_name, alias):
		object.__setattr__(self, '_attr_name', attr_name)
		_LazyImport.__init__(self, scope, alias, name)

	def _get_target(self):
		try:
			return object.__getattribute__(self, '_target')
		except AttributeError:
			pass
		name = object.__getattribute__(self, '_name')
		attr_name = object.__getattribute__(self, '_attr_name')
		__import__(name)
		target = getattr(sys.modules[name], attr_name)
		object.__setattr__(self, '_target', target)
		object.__getattribute__(self, '_scope')[
			object.__getattribute__(self, '_alias')] = target
		_unregister_module_proxy(name)
		return target

def lazyimport(scope, *args):
	"""
	Create a proxy in the given scope in order to performa a lazy import.

	Syntax         Result
	foo            import foo
	foo:bar,baz    from foo import bar, baz
	foo:bar@baz    from foo import bar as baz

	@param scope: the scope in which to place the import, typically globals()
	@type myfilename: dict
	@param args: module names to import
	@type args: strings
	"""

	modules = sys.modules

	for s in args:
		parts = s.split(':', 1)
		if len(parts) == 1:
			name = s

			if not name or not isinstance(name, basestring):
				raise ValueError(name)

			components = name.split('.')
			parent_scope = scope
			for i in range(len(components)):
				alias = components[i]
				if i < len(components) - 1:
					parent_name = ".".join(components[:i+1])
					__import__(parent_name)
					mod = modules.get(parent_name)
					if not isinstance(mod, types.ModuleType):
						# raise an exception
						__import__(name)
					parent_scope[alias] = mod
					parent_scope = mod.__dict__
					continue

				already_imported = modules.get(name)
				if already_imported is not None:
					parent_scope[alias] = already_imported
				else:
					parent_scope[alias] = \
						_LazyImport(parent_scope, alias, name)

		else:
			name, fromlist = parts
			already_imported = modules.get(name)
			fromlist = fromlist.split(',')
			for s in fromlist:
				alias = s.split('@', 1)
				if len(alias) == 1:
					alias = alias[0]
					attr_name = alias
				else:
					attr_name, alias = alias
				if already_imported is not None:
					try:
						scope[alias] = getattr(already_imported, attr_name)
					except AttributeError:
						raise ImportError('cannot import name %s' % attr_name)
				else:
					scope[alias] = \
						_LazyImportFrom(scope, name, attr_name, alias)
