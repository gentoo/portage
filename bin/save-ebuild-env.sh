#!/bin/bash
# Copyright 1999-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# @FUNCTION: __save_ebuild_env
# @DESCRIPTION:
# echo the current environment to stdout, filtering out redundant info.
#
# --exclude-init-phases causes pkg_nofetch and src_* phase functions to
# be excluded from the output. These function are not needed for installation
# or removal of the packages, and can therefore be safely excluded.
#
__save_ebuild_env() {
	(
	if has --exclude-init-phases $* ; then
		unset S _E_DESTTREE _E_INSDESTTREE _E_DOCDESTTREE_ _E_EXEDESTTREE_ \
			PORTAGE_DOCOMPRESS_SIZE_LIMIT PORTAGE_DOCOMPRESS \
			PORTAGE_DOCOMPRESS_SKIP PORTAGE_DOSTRIP PORTAGE_DOSTRIP_SKIP
		if [[ -n $PYTHONPATH &&
			${PYTHONPATH%%:*} -ef $PORTAGE_PYM_PATH ]] ; then
			if [[ $PYTHONPATH == *:* ]] ; then
				export PYTHONPATH=${PYTHONPATH#*:}
			else
				unset PYTHONPATH
			fi
		fi
	fi

	# misc variables inherited from the calling environment
	unset COLORTERM DISPLAY EDITOR LESS LESSOPEN LOGNAME LS_COLORS PAGER \
		TERM TERMCAP USER ftp_proxy http_proxy no_proxy

	# other variables inherited from the calling environment
	unset CVS_RSH ECHANGELOG_USER GPG_AGENT_INFO \
	SSH_AGENT_PID SSH_AUTH_SOCK STY WINDOW XAUTHORITY

	# CCACHE and DISTCC config
	unset ${!CCACHE_*} ${!DISTCC_*}

	# There's no need to bloat environment.bz2 with internally defined
	# functions and variables, so filter them out if possible.

	for x in pkg_setup pkg_nofetch src_unpack src_prepare src_configure \
		src_compile src_test src_install pkg_preinst pkg_postinst \
		pkg_prerm pkg_postrm pkg_config pkg_info pkg_pretend ; do
		unset -f default_$x __eapi{0,1,2,3,4}_$x
	done
	unset x

	unset -f assert __assert_sigpipe_ok \
		__dump_trace die \
		__quiet_mode __vecho __elog_base eqawarn elog \
		einfo einfon ewarn eerror ebegin __eend eend KV_major \
		KV_minor KV_micro KV_to_int get_KV has \
		__has_phase_defined_up_to \
		hasv hasq __qa_source __qa_call \
		addread addwrite adddeny addpredict __sb_append_var \
		use usev useq has_version portageq \
		best_version use_with use_enable register_die_hook \
		unpack __strip_duplicate_slashes econf einstall \
		__dyn_setup __dyn_unpack __dyn_clean \
		into insinto exeinto docinto \
		insopts diropts exeopts libopts docompress dostrip \
		__abort_handler __abort_prepare __abort_configure __abort_compile \
		__abort_test __abort_install __dyn_prepare __dyn_configure \
		__dyn_compile __dyn_test __dyn_install \
		__dyn_pretend __dyn_help \
		debug-print debug-print-function \
		debug-print-section __helpers_die inherit EXPORT_FUNCTIONS \
		nonfatal register_success_hook \
		__hasg __hasgq \
		__save_ebuild_env __set_colors __filter_readonly_variables \
		__preprocess_ebuild_env \
		__repo_attr __source_all_bashrcs \
		__ebuild_main __ebuild_phase __ebuild_phase_with_hooks \
		__ebuild_arg_to_phase __ebuild_phase_funcs default \
		__unpack_tar __unset_colors \
		__source_env_files __try_source __check_bash_version \
		__bashpid __start_distcc \
		__eqaquote __eqatag \
		${QA_INTERCEPTORS}

	___eapi_has_usex && unset -f usex
	___eapi_has_master_repositories && unset -f master_repositories
	___eapi_has_repository_path && unset -f repository_path
	___eapi_has_available_eclasses && unset -f available_eclasses
	___eapi_has_eclass_path && unset -f eclass_path
	___eapi_has_license_path && unset -f license_path
	___eapi_has_package_manager_build_user && unset -f package_manager_build_user
	___eapi_has_package_manager_build_group && unset -f package_manager_build_group

	# Clear out the triple underscore namespace as it is reserved by the PM.
	unset -f $(compgen -A function ___)
	unset ${!___*}

	# portage config variables and variables set directly by portage
	unset ACCEPT_LICENSE BUILD_PREFIX COLS \
		DISTDIR DOC_SYMLINKS_DIR \
		EBUILD_FORCE_TEST EBUILD_MASTER_PID \
		ECLASS_DEPTH ENDCOL FAKEROOTKEY \
		HOME \
		LAST_E_CMD LAST_E_LEN LD_PRELOAD MISC_FUNCTIONS_ARGS MOPREFIX \
		NOCOLOR PKGDIR PKGUSE PKG_LOGDIR PKG_TMPDIR \
		PORTAGE_BASHRC_FILES PORTAGE_BASHRCS_SOURCED \
		PORTAGE_COLOR_BAD PORTAGE_COLOR_BRACKET PORTAGE_COLOR_ERR \
		PORTAGE_COLOR_GOOD PORTAGE_COLOR_HILITE PORTAGE_COLOR_INFO \
		PORTAGE_COLOR_LOG PORTAGE_COLOR_NORMAL PORTAGE_COLOR_QAWARN \
		PORTAGE_COLOR_WARN \
		PORTAGE_COMPRESS PORTAGE_COMPRESS_EXCLUDE_SUFFIXES \
		PORTAGE_DOHTML_UNWARNED_SKIPPED_EXTENSIONS \
		PORTAGE_DOHTML_UNWARNED_SKIPPED_FILES \
		PORTAGE_DOHTML_WARN_ON_SKIPPED_FILES \
		PORTAGE_NONFATAL PORTAGE_QUIET \
		PORTAGE_SANDBOX_DENY PORTAGE_SANDBOX_PREDICT \
		PORTAGE_SANDBOX_READ PORTAGE_SANDBOX_WRITE \
		PORTAGE_SOCKS5_PROXY PREROOTPATH \
		QA_INTERCEPTORS \
		RC_DEFAULT_INDENT RC_DOT_PATTERN RC_ENDCOL RC_INDENTATION  \
		ROOT ROOTPATH RPMDIR TEMP TMP TMPDIR USE_EXPAND \
		XARGS _RC_GET_KV_CACHE

	# user config variables
	unset DOC_SYMLINKS_DIR INSTALL_MASK PKG_INSTALL_MASK

	declare -p
	declare -fp
	if [[ ${BASH_VERSINFO[0]} == 3 ]]; then
		export
	fi
	)
}
