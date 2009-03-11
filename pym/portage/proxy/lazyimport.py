# Copyright 2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ['lazyimport']

import sys
import types
from portage.proxy.objectproxy import ObjectProxy

_module_proxies = {}

def _register_module_proxy(name, proxy):
	proxy_list = _module_proxies.get(name)
	if proxy_list is None:
		proxy_list = []
		_module_proxies[name] = proxy_list
	proxy_list.append(proxy)

def _unregister_module_proxy(name):
	"""
	Destroy all proxies that reference the give module name. Also, check
	for other proxies referenced by modules that have been imported and
	destroy those proxies too. This way, destruction of a single proxy
	can trigger destruction of all the rest.
	"""
	proxy_list = _module_proxies.get(name)
	if proxy_list is not None:
		del _module_proxies[name]
		for proxy in proxy_list:
			object.__getattribute__(proxy, '_get_target')()

		modules = sys.modules
		for name, proxy_list in list(_module_proxies.iteritems()):
			if name not in modules:
				continue
			del _module_proxies[name]
			for proxy in proxy_list:
				object.__getattribute__(proxy, '_get_target')()

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

	__slots__ = ()

	def _get_target(self):
		try:
			return object.__getattribute__(self, '_target')
		except AttributeError:
			pass
		name = object.__getattribute__(self, '_name')
		components = name.split('.')
		parent_name = '.'.join(components[:-1])
		__import__(parent_name)
		target = getattr(sys.modules[parent_name], components[-1])
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
			for i in xrange(len(components)):
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
					orig = alias
				else:
					orig, alias = alias
				if already_imported is not None:
					try:
						scope[alias] = getattr(already_imported, orig)
					except AttributeError:
						raise ImportError('cannot import name %s' % orig)
				else:
					scope[alias] = _LazyImportFrom(scope, alias,
						name + '.' + orig)
