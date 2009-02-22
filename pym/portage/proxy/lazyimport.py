# Copyright 2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ['lazy_import']

import sys
import types
from portage.proxy.objectproxy import ObjectProxy

class _LazyImport(ObjectProxy):

	__slots__ = ('_scope', '_alias', '_name', '_target')

	def __init__(self, scope, alias, name):
		ObjectProxy.__init__(self)
		object.__setattr__(self, '_scope', scope)
		object.__setattr__(self, '_alias', alias)
		object.__setattr__(self, '_name', name)

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
