# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
import operator
import types

from portage import eapi_is_supported

def eapi_has_iuse_defaults(eapi):
	return eapi != "0"

def eapi_has_iuse_effective(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi")

def eapi_has_slot_deps(eapi):
	return eapi != "0"

def eapi_has_slot_operator(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python")

def eapi_has_src_uri_arrows(eapi):
	return eapi not in ("0", "1")

def eapi_has_selective_src_uri_restriction(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6", "7")

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

def eapi_exports_EBUILD_PHASE_FUNC(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi")

def eapi_exports_PORTDIR(eapi):
	return eapi in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

def eapi_exports_ECLASSDIR(eapi):
	return eapi in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

def eapi_exports_REPOSITORY(eapi):
	return eapi in ("4-python", "5-progress")

def eapi_has_pkg_pretend(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_has_implicit_rdepend(eapi):
	return eapi in ("0", "1", "2", "3")

def eapi_has_dosed_dohard(eapi):
	return eapi in ("0", "1", "2", "3")

def eapi_has_required_use(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_has_required_use_at_most_one_of(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi")

def eapi_has_use_dep_defaults(eapi):
	return eapi not in ("0", "1", "2", "3")

def eapi_requires_posixish_locale(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress")

def eapi_has_repo_deps(eapi):
	return eapi in ("4-python", "5-progress")

def eapi_allows_dots_in_PN(eapi):
	return eapi in ("4-python", "5-progress")

def eapi_allows_dots_in_use_flags(eapi):
	return eapi in ("4-python", "5-progress")

def eapi_supports_stable_use_forcing_and_masking(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi")

def eapi_allows_directories_on_profile_level_and_repository_level(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-slot-abi", "5", "6")

def eapi_has_use_aliases(eapi):
	return eapi in ("4-python", "5-progress")

def eapi_has_automatic_unpack_dependencies(eapi):
	return eapi in ("5-progress",)

def eapi_allows_package_provided(eapi):
	return eapi in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

def eapi_has_bdepend(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

def eapi_has_idepend(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6", "7")

def eapi_empty_groups_always_true(eapi):
	return eapi in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

def eapi_path_variables_end_with_trailing_slash(eapi):
	return eapi in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

def eapi_has_broot(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

def eapi_has_sysroot(eapi):
	return eapi not in ("0", "1", "2", "3", "4", "4-python", "4-slot-abi",
			"5", "5-progress", "6")

_eapi_attrs = collections.namedtuple('_eapi_attrs',
	'allows_package_provided '
	'bdepend '
	'broot '
	'dots_in_PN dots_in_use_flags '
	'exports_AA '
	'exports_EBUILD_PHASE_FUNC '
	'exports_ECLASSDIR '
	'exports_KV '
	'exports_merge_type '
	'exports_PORTDIR '
	'exports_replace_vars '
	'feature_flag_test '
	'idepend iuse_defaults iuse_effective posixish_locale '
	'path_variables_end_with_trailing_slash '
	'prefix '
	'repo_deps required_use required_use_at_most_one_of '
	'selective_src_uri_restriction slot_operator slot_deps '
	'src_uri_arrows strong_blocks use_deps use_dep_defaults '
	'empty_groups_always_true sysroot')


_eapi_attr_func_prefixes = (
	'eapi_allows_',
	'eapi_has_',
	'eapi_requires_',
	'eapi_supports_',
	'eapi_',
)


def _eapi_func_decorator(func, attr_getter):
	def wrapper(eapi):
		return attr_getter(_get_eapi_attrs(eapi))
	wrapper.func = func
	wrapper.__doc__ = func.__doc__
	return wrapper


def _decorate_eapi_funcs():
	"""
	Decorate eapi_* functions so that they use _get_eapi_attrs(eapi)
	to cache results.
	"""
	decorated = {}
	for k, v in globals().items():
		if not (isinstance(v, types.FunctionType) and k.startswith(_eapi_attr_func_prefixes)):
			continue
		for prefix in _eapi_attr_func_prefixes:
			if k.startswith(prefix):
				attr_name = k[len(prefix):]
				if hasattr(_eapi_attrs, attr_name):
					decorated[k] = _eapi_func_decorator(v, operator.attrgetter(attr_name))
					break
	globals().update(decorated)


_decorate_eapi_funcs()


_eapi_attrs_cache = {}

def _get_eapi_attrs(eapi):
	"""
	When eapi is None then validation is not as strict, since we want the
	same to work for multiple EAPIs that may have slightly different rules.
	An unsupported eapi is handled the same as when eapi is None, which may
	be helpful for handling of corrupt EAPI metadata in essential functions
	such as pkgsplit.
	"""
	eapi_attrs = _eapi_attrs_cache.get(eapi)
	if eapi_attrs is not None:
		return eapi_attrs

	orig_eapi = eapi
	if eapi is not None and not eapi_is_supported(eapi):
		eapi = None

	eapi_attrs = _eapi_attrs(
		allows_package_provided=(eapi is None or eapi_allows_package_provided.func(eapi)),
		bdepend = (eapi is not None and eapi_has_bdepend.func(eapi)),
		broot = (eapi is None or eapi_has_broot.func(eapi)),
		dots_in_PN = (eapi is None or eapi_allows_dots_in_PN.func(eapi)),
		dots_in_use_flags = (eapi is None or eapi_allows_dots_in_use_flags.func(eapi)),
		empty_groups_always_true = (eapi is not None and eapi_empty_groups_always_true.func(eapi)),
		exports_AA = (eapi is not None and eapi_exports_AA.func(eapi)),
		exports_EBUILD_PHASE_FUNC = (eapi is None or eapi_exports_EBUILD_PHASE_FUNC.func(eapi)),
		exports_ECLASSDIR = (eapi is not None and eapi_exports_ECLASSDIR.func(eapi)),
		exports_KV = (eapi is not None and eapi_exports_KV.func(eapi)),
		exports_merge_type = (eapi is None or eapi_exports_merge_type.func(eapi)),
		exports_PORTDIR = (eapi is None or eapi_exports_PORTDIR.func(eapi)),
		exports_replace_vars = (eapi is None or eapi_exports_replace_vars.func(eapi)),
		feature_flag_test = False,
		idepend = (eapi is not None and eapi_has_idepend.func(eapi)),
		iuse_defaults = (eapi is None or eapi_has_iuse_defaults.func(eapi)),
		iuse_effective = (eapi is not None and eapi_has_iuse_effective.func(eapi)),
		path_variables_end_with_trailing_slash = (eapi is not None and
			eapi_path_variables_end_with_trailing_slash.func(eapi)),
		posixish_locale = (eapi is not None and eapi_requires_posixish_locale.func(eapi)),
		prefix = (eapi is None or eapi_supports_prefix.func(eapi)),
		repo_deps = (eapi is None or eapi_has_repo_deps.func(eapi)),
		required_use = (eapi is None or eapi_has_required_use.func(eapi)),
		required_use_at_most_one_of = (eapi is None or eapi_has_required_use_at_most_one_of.func(eapi)),
		selective_src_uri_restriction = (eapi is None or eapi_has_selective_src_uri_restriction.func(eapi)),
		slot_deps = (eapi is None or eapi_has_slot_deps.func(eapi)),
		slot_operator = (eapi is None or eapi_has_slot_operator.func(eapi)),
		src_uri_arrows = (eapi is None or eapi_has_src_uri_arrows.func(eapi)),
		strong_blocks = (eapi is None or eapi_has_strong_blocks.func(eapi)),
		sysroot = (eapi is None or eapi_has_sysroot.func(eapi)),
		use_deps = (eapi is None or eapi_has_use_deps.func(eapi)),
		use_dep_defaults = (eapi is None or eapi_has_use_dep_defaults.func(eapi))
	)

	_eapi_attrs_cache[orig_eapi] = eapi_attrs
	return eapi_attrs
