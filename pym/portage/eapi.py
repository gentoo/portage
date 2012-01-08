# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

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
