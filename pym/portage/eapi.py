# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import collections

def eapi_has_iuse_defaults(eapi):
	return eapi != "0"

def eapi_has_slot_deps(eapi):
	return eapi != "0"

def eapi_has_src_uri_arrows(eapi):
	return eapi not in ("0", "1")

def eapi_has_use_deps(eapi):
	return eapi not in ("0", "1")

def eapi_has_strong_blocks(eapi):
	return eapi not in ("0", "1")

def eapi_has_src_prepare_and_src_configure(eapi):
	return eapi not in ("0", "1")

def eapi_supports_prefix(eapi):
	return eapi not in ("0", "1", "2")

def eapi_exports_AA(eapi):
	return eapi in ("0", "1", "2", "3")

def eapi_exports_KV(eapi):
	return eapi in ("0", "1", "2", "3")

def eapi_exports_merge_type(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_exports_replace_vars(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_exports_REPOSITORY(eapi):
	return eapi in ("4-python",)

def eapi_has_pkg_pretend(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_has_implicit_rdepend(eapi):
	return eapi in ("0", "1", "2", "3")

def eapi_has_dosed_dohard(eapi):
	return eapi in ("0", "1", "2", "3")

def eapi_has_required_use(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_has_use_dep_defaults(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_has_repo_deps(eapi):
	return eapi in ("4-python",)

def eapi_allows_dots_in_PN(eapi):
	return eapi in ("4-python",)

def eapi_allows_dots_in_use_flags(eapi):
	return eapi in ("4-python",)

_eapi_attrs = collections.namedtuple('_eapi_attrs',
	'dots_in_PN dots_in_use_flags iuse_defaults '
	'repo_deps required_use slot_deps '
	'src_uri_arrows strong_blocks use_deps use_dep_defaults')

_eapi_attrs_cache = {}

def _get_eapi_attrs(eapi):
	"""
	When eapi is None then validation is not as strict, since we want the
	same to work for multiple EAPIs that may have slightly different rules.
	"""
	eapi_attrs = _eapi_attrs_cache.get(eapi)
	if eapi_attrs is not None:
		return eapi_attrs

	eapi_attrs = _eapi_attrs(
		dots_in_PN = (eapi is None or eapi_allows_dots_in_PN(eapi)),
		dots_in_use_flags = (eapi is None or eapi_allows_dots_in_use_flags(eapi)),
		iuse_defaults = (eapi is None or eapi_has_iuse_defaults(eapi)),
		repo_deps = (eapi is None or eapi_has_repo_deps(eapi)),
		required_use = (eapi is None or eapi_has_required_use(eapi)),
		slot_deps = (eapi is None or eapi_has_slot_deps(eapi)),
		src_uri_arrows = (eapi is None or eapi_has_src_uri_arrows(eapi)),
		strong_blocks = (eapi is None or eapi_has_strong_blocks(eapi)),
		use_deps = (eapi is None or eapi_has_use_deps(eapi)),
		use_dep_defaults = (eapi is None or eapi_has_use_dep_defaults(eapi))
	)

	_eapi_attrs_cache[eapi] = eapi_attrs
	return eapi_attrs
