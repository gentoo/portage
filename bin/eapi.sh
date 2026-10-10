#!/usr/bin/env bash
# Copyright 2012-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# EBUILD PHASES

___eapi_default_src_test_runs_serial()  [[ ${1-${EAPI-0}} == [0-4] ]]
___eapi_has_pkg_pretend()               [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_has_src_configure()             [[ ${1-${EAPI-0}} != [01]  ]]
___eapi_has_src_prepare()               [[ ${1-${EAPI-0}} != [01]  ]]
___eapi_uses_S_WORKDIR_fallback()       [[ ${1-${EAPI-0}} == [0-3] ]]

# DEPENDENCY VARIABLES

___eapi_has_BDEPEND()                   [[ ${1-${EAPI-0}} != [0-6] ]]
___eapi_has_IDEPEND()                   [[ ${1-${EAPI-0}} != [0-7] ]]
___eapi_uses_RDEPEND_as_DEPEND()        [[ ${1-${EAPI-0}} == [0-3] ]]

# ROOT AND PREFIX VARIABLES

___eapi_has_BROOT()                     [[ ${1-${EAPI-0}} != [0-6] ]]
___eapi_has_SYSROOT()                   [[ ${1-${EAPI-0}} != [0-6] ]]
___eapi_has_prefix_vars()               [[ ${1-${EAPI-0}} != [0-2] ]]

# METADATA VARIABLES

___eapi_accumulates_PROPERTIES()        [[ ${1-${EAPI-0}} != [0-7] ]]
___eapi_accumulates_RESTRICT()          [[ ${1-${EAPI-0}} != [0-7] ]]

# LEGACY VARIABLES

___eapi_has_legacy_desttree_vars()      [[ ${1-${EAPI-0}} == [0-6] ]]
___eapi_has_legacy_repo_vars()          [[ ${1-${EAPI-0}} == [0-6] ]]

# HELPER PRESENCE

___eapi_has_docompress()                [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_has_doheader()                  [[ ${1-${EAPI-0}} != [0-4] ]]
___eapi_has_dostrip()                   [[ ${1-${EAPI-0}} != [0-6] ]]
___eapi_has_eapply()                    [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_has_eapply_user()               [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_has_edo()                       [[ ${1-${EAPI-0}} != [0-8] ]]
___eapi_has_einstalldocs()              [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_has_get_libdir()                [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_has_in_iuse()                   [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_has_nonfatal()                  [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_has_pipestatus()                [[ ${1-${EAPI-0}} != [0-8] ]]
___eapi_has_usex()                      [[ ${1-${EAPI-0}} != [0-4] ]]

# REMOVED HELPERS

___eapi_has_assert()                    [[ ${1-${EAPI-0}} == [0-8] ]]
___eapi_has_dohard()                    [[ ${1-${EAPI-0}} == [0-3] ]]
___eapi_has_dohtml()                    [[ ${1-${EAPI-0}} == [0-6] ]]
___eapi_has_domo()                      [[ ${1-${EAPI-0}} == [0-8] ]]
___eapi_has_dosed()                     [[ ${1-${EAPI-0}} == [0-3] ]]
___eapi_has_einstall()                  [[ ${1-${EAPI-0}} == [0-5] ]]
___eapi_has_hasq()                      [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_has_hasv()                      [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_has_useq()                      [[ ${1-${EAPI-0}} == [0-7] ]]

# HELPER ARGUMENTS

___eapi_dodoc_has_recursive()           [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_dosym_has_relative()            [[ ${1-${EAPI-0}} != [0-7] ]]
___eapi_newins_reads_stdin()            [[ ${1-${EAPI-0}} != [0-4] ]]
___eapi_use_enable_empty_third_arg()    [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_usev_has_false_arg()            [[ ${1-${EAPI-0}} != [0-7] ]]

# HELPER BEHAVIOUR

___eapi_die_supports_nonfatal()         [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_doconfd_uses_insopts()          [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_doenvd_uses_insopts()           [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_doheader_uses_insopts()         [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_doinitd_uses_exeopts()          [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_doins_preserves_symlinks()      [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_dolib_uses_libopts()            [[ ${1-${EAPI-0}} == [0-6] ]]
___eapi_domo_uses_into()                [[ ${1-${EAPI-0}} == [0-6] ]]
___eapi_helpers_die_on_failure()        [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_keepdir_is_strict()             [[ ${1-${EAPI-0}} != [0-7] ]]

# VERSION HELPERS

___eapi_has_ver_helpers()               [[ ${1-${EAPI-0}} != [0-6] ]]
___eapi_has_ver_replacing()             [[ ${1-${EAPI-0}} != [0-8] ]]
___eapi_version_query_has_host_root()   [[ ${1-${EAPI-0}} == [56]  ]]
___eapi_version_query_has_root_opts()   [[ ${1-${EAPI-0}} != [0-6] ]]

# ECONF DEFAULTS

___eapi_econf_disables_dep_tracking()   [[ ${1-${EAPI-0}} != [0-3] ]]
___eapi_econf_disables_silent_rules()   [[ ${1-${EAPI-0}} != [0-4] ]]
___eapi_econf_disables_static()         [[ ${1-${EAPI-0}} != [0-7] ]]
___eapi_econf_sets_datarootdir()        [[ ${1-${EAPI-0}} != [0-7] ]]
___eapi_econf_sets_docdirs()            [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_econf_sets_sysroot()            [[ ${1-${EAPI-0}} != [0-6] ]]

# UNPACK FEATURES

___eapi_unpack_allows_abs_paths()       [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_unpack_matches_case()           [[ ${1-${EAPI-0}} == [0-5] ]]
___eapi_unpack_supports_7z()            [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_unpack_supports_lha()           [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_unpack_supports_rar()           [[ ${1-${EAPI-0}} == [0-7] ]]
___eapi_unpack_supports_txz()           [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_unpack_supports_xz()            [[ ${1-${EAPI-0}} != [0-2] ]]

# SHELL AND ENVIRONMENT

___eapi_enables_global_failglob()       [[ ${1-${EAPI-0}} != [0-5] ]]
___eapi_has_ENV_UNSET()                 [[ ${1-${EAPI-0}} != [0-6] ]]
___eapi_uses_bash_3_2()                 [[ ${1-${EAPI-0}} == [0-5] ]]
___eapi_uses_bash_4_2()                 [[ ${1-${EAPI-0}} == [67]  ]]
___eapi_uses_bash_5_0()                 [[ ${1-${EAPI-0}} == 8     ]]
___eapi_uses_bash_5_3()                 [[ ${1-${EAPI-0}} != [0-8] ]]
