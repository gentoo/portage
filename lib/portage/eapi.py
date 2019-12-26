# Copyright 2010-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import collections

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
	'bdepend broot dots_in_PN dots_in_use_flags exports_EBUILD_PHASE_FUNC '
	'exports_PORTDIR exports_ECLASSDIR '
	'feature_flag_test '
	'iuse_defaults iuse_effective posixish_locale '
	'path_variables_end_with_trailing_slash '
	'repo_deps required_use required_use_at_most_one_of slot_operator slot_deps '
	'src_uri_arrows strong_blocks use_deps use_dep_defaults '
	'empty_groups_always_true sysroot')

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
		allows_package_provided=(eapi is None or eapi_allows_package_provided(eapi)),
		bdepend = (eapi is not None and eapi_has_bdepend(eapi)),
		broot = (eapi is None or eapi_has_broot(eapi)),
		dots_in_PN = (eapi is None or eapi_allows_dots_in_PN(eapi)),
		dots_in_use_flags = (eapi is None or eapi_allows_dots_in_use_flags(eapi)),
		empty_groups_always_true = (eapi is not None and eapi_empty_groups_always_true(eapi)),
		exports_EBUILD_PHASE_FUNC = (eapi is None or eapi_exports_EBUILD_PHASE_FUNC(eapi)),
		exports_PORTDIR = (eapi is None or eapi_exports_PORTDIR(eapi)),
		exports_ECLASSDIR = (eapi is not None and eapi_exports_ECLASSDIR(eapi)),
		feature_flag_test = False,
		iuse_defaults = (eapi is None or eapi_has_iuse_defaults(eapi)),
		iuse_effective = (eapi is not None and eapi_has_iuse_effective(eapi)),
		path_variables_end_with_trailing_slash = (eapi is not None and
			eapi_path_variables_end_with_trailing_slash(eapi)),
		posixish_locale = (eapi is not None and eapi_requires_posixish_locale(eapi)),
		repo_deps = (eapi is None or eapi_has_repo_deps(eapi)),
		required_use = (eapi is None or eapi_has_required_use(eapi)),
		required_use_at_most_one_of = (eapi is None or eapi_has_required_use_at_most_one_of(eapi)),
		slot_deps = (eapi is None or eapi_has_slot_deps(eapi)),
		slot_operator = (eapi is None or eapi_has_slot_operator(eapi)),
		src_uri_arrows = (eapi is None or eapi_has_src_uri_arrows(eapi)),
		strong_blocks = (eapi is None or eapi_has_strong_blocks(eapi)),
		sysroot = (eapi is None or eapi_has_sysroot(eapi)),
		use_deps = (eapi is None or eapi_has_use_deps(eapi)),
		use_dep_defaults = (eapi is None or eapi_has_use_dep_defaults(eapi))
	)

	_eapi_attrs_cache[orig_eapi] = eapi_attrs
	return eapi_attrs
