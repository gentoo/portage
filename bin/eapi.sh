#!/bin/bash
# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# PHASES

___eapi_has_pkg_pretend() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_has_src_prepare() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1)$ ]]
}

___eapi_has_src_configure() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1)$ ]]
}

___eapi_default_src_test_disables_parallel_jobs() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi)$ ]]
}

___eapi_has_S_WORKDIR_fallback() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

# VARIABLES

___eapi_has_prefix_variables() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2)$ || " ${FEATURES} " == *" force-prefix "* ]]
}

___eapi_has_HDEPEND() {
	[[ ${1-${EAPI-0}} =~ ^(5-hdepend)$ ]]
}

___eapi_has_RDEPEND_DEPEND_fallback() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

# HELPERS PRESENCE

___eapi_has_dohard() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_has_dosed() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_has_einstall() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_has_dohtml_deprecated() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_has_docompress() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_has_nonfatal() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_has_doheader() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi)$ ]]
}

___eapi_has_usex() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi)$ ]]
}

___eapi_has_get_libdir() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_has_einstalldocs() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_has_eapply() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_has_eapply_user() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_has_in_iuse() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_has_master_repositories() {
	[[ ${1-${EAPI-0}} =~ ^(5-progress)$ ]]
}

___eapi_has_repository_path() {
	[[ ${1-${EAPI-0}} =~ ^(5-progress)$ ]]
}

___eapi_has_available_eclasses() {
	[[ ${1-${EAPI-0}} =~ ^(5-progress)$ ]]
}

___eapi_has_eclass_path() {
	[[ ${1-${EAPI-0}} =~ ^(5-progress)$ ]]
}

___eapi_has_license_path() {
	[[ ${1-${EAPI-0}} =~ ^(5-progress)$ ]]
}

___eapi_has_package_manager_build_user() {
	[[ ${1-${EAPI-0}} =~ ^(5-progress)$ ]]
}

___eapi_has_package_manager_build_group() {
	[[ ${1-${EAPI-0}} =~ ^(5-progress)$ ]]
}

# HELPERS BEHAVIOR

___eapi_best_version_and_has_version_support_--host-root() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi)$ ]]
}

___eapi_unpack_supports_xz() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2)$ ]]
}

___eapi_unpack_supports_txz() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_econf_passes_--disable-dependency-tracking() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_econf_passes_--disable-silent-rules() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi)$ ]]
}

___eapi_econf_passes_--docdir_and_--htmldir() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_use_enable_and_use_with_support_empty_third_argument() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_dodoc_supports_-r() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_doins_and_newins_preserve_symlinks() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_newins_supports_reading_from_standard_input() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi)$ ]]
}

___eapi_helpers_can_die() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3)$ ]]
}

___eapi_unpack_is_case_sensitive() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend)$ ]]
}

___eapi_unpack_supports_absolute_paths() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend)$ ]]
}

___eapi_die_can_respect_nonfatal() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

# OTHERS

___eapi_enables_failglob_in_global_scope() {
	[[ ! ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_enables_globstar() {
	[[ ${1-${EAPI-0}} =~ ^(4-python|5-progress)$ ]]
}

___eapi_bash_3_2() {
	[[ ${1-${EAPI-0}} =~ ^(0|1|2|3|4|4-python|4-slot-abi|5|5-hdepend|5-progress)$ ]]
}

___eapi_bash_4_2() {
	[[ ${1-${EAPI-0}} =~ ^(6)$ ]]
}
