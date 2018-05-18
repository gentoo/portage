# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'iter_iuse_vars',
)


def iter_iuse_vars(env):
	"""
	Iterate over (key, value) pairs of profile variables that contribute
	to implicit IUSE for EAPI 5 and later.

	@param env: Ebuild environment
	@type env: Mapping
	@rtype: iterator
	@return: iterator over (key, value) pairs of profile variables
	"""

	for k in ('IUSE_IMPLICIT', 'USE_EXPAND_IMPLICIT', 'USE_EXPAND_UNPREFIXED', 'USE_EXPAND'):
		v = env.get(k)
		if v is not None:
			yield (k, v)

	use_expand_implicit = frozenset(env.get('USE_EXPAND_IMPLICIT', '').split())

	for v in env.get('USE_EXPAND_UNPREFIXED', '').split() + env.get('USE_EXPAND', '').split():
		if v in use_expand_implicit:
			k = 'USE_EXPAND_VALUES_' + v
			v = env.get(k)
			if v is not None:
				yield (k, v)
