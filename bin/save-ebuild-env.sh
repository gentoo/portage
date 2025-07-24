#!/usr/bin/env bash
# Copyright 1999-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# @FUNCTION: __save_ebuild_env
# @DESCRIPTION:
# echo the current environment to stdout, filtering out redundant info.
#
# --exclude-init-phases causes pkg_nofetch and src_* phase functions to
# be excluded from the output. These function are not needed for installation
# or removal of the packages, and can therefore be safely excluded.
#
__save_ebuild_env() (
	# REPLY is purposed as an array that undergoes two phases of assembly.
	# The first entails gathering the names of variables that are to be
	# unset. The second entails gathering the names of functions that are
	# to be unset. The REPLY variable is eventually unset in its own right.
	REPLY=()

	if has --exclude-init-phases "$@"; then
		REPLY+=(
			PORTAGE_DOCOMPRESS_SIZE_LIMIT PORTAGE_DOCOMPRESS_SKIP
			PORTAGE_DOSTRIP_SKIP PORTAGE_DOCOMPRESS PORTAGE_DOSTRIP
			S __E_DOCDESTTREE __E_EXEDESTTREE __E_INSDESTTREE
			__E_DESTTREE

			# Discard stale GNU Make POSIX Jobserver flags.
			MAKEFLAGS
		)
		if [[ -n ${PYTHONPATH} &&
			${PYTHONPATH%%:*} -ef ${PORTAGE_PYM_PATH} ]] ; then
			if [[ ${PYTHONPATH} == *:* ]] ; then
				export PYTHONPATH=${PYTHONPATH#*:}
			else
				REPLY+=( PYTHONPATH )
			fi
		fi
	fi

	REPLY+=(
		# variables that can influence the behaviour of GNU coreutils
		BLOCK_SIZE COLORTERM COLUMNS DF_BLOCK_SIZE DU_BLOCK_SIZE HOME
		LS_BLOCK_SIZE LS_COLORS POSIXLY_CORRECT PWD QUOTING_STYLE
		SHELL TIME_STYLE TABSIZE TMPDIR TERM TZ

		# misc variables inherited from the calling environment
		DISPLAY EDITOR LESSOPEN LOGNAME LESS PAGER TERMCAP USER
		ftp_proxy https_proxy http_proxy no_proxy

		# other variables inherited from the calling environment
		"${!SSH_@}" "${!XDG_CURRENT_@}" "${!XDG_RUNTIME_@}"
		"${!XDG_SESSION_@}" "${!XDG_CONFIG_@}" "${!XDG_DATA_@}"
		"${!XDG_MENU_@}" "${!XDG_SEAT_@}" CVS_RSH ECHANGELOG_USER
		GPG_AGENT_INFO STY WINDOW XAUTHORITY XDG_VTNR

		# portage config variables and variables set directly by portage
		ACCEPT_LICENSE BUILD_PREFIX COLS DOC_SYMLINKS_DIR DISTDIR
		EBUILD_FORCE_TEST EBUILD_MASTER_PID ECLASS_DEPTH ENDCOL
		FAKEROOTKEY HOME LAST_E_CMD LAST_E_LEN LD_PRELOAD
		MISC_FUNCTIONS_ARGS MOPREFIX NO_COLOR NOCOLOR
		PORTAGE_DOHTML_UNWARNED_SKIPPED_EXTENSIONS
		PORTAGE_DOHTML_UNWARNED_SKIPPED_FILES
		PORTAGE_DOHTML_WARN_ON_SKIPPED_FILES
		PORTAGE_COMPRESS_EXCLUDE_SUFFIXES PORTAGE_BASHRCS_SOURCED
		PORTAGE_SANDBOX_PREDICT PORTAGE_COLOR_BRACKET
		PORTAGE_SANDBOX_WRITE PORTAGE_BASHRC_FILES PORTAGE_COLOR_HILITE
		PORTAGE_COLOR_NORMAL PORTAGE_COLOR_QAWARN PORTAGE_SANDBOX_DENY
		PORTAGE_SANDBOX_READ PORTAGE_SOCKS5_PROXY PORTAGE_COLOR_GOOD
		PORTAGE_COLOR_INFO PORTAGE_COLOR_WARN PORTAGE_COLOR_BAD
		PORTAGE_COLOR_ERR PORTAGE_COLOR_LOG PORTAGE_COMPRESS
		PORTAGE_NONFATAL PORTAGE_QUIET PREROOTPATH PKG_LOGDIR
		PKG_TMPDIR PKGDIR PKGUSE QA_INTERCEPTORS RC_DOT_PATTERN
		RC_INDENTATION RC_ENDCOL ROOTPATH RPMDIR ROOT TMPDIR TEMP TMP
		USE_EXPAND XARGS _RC_GET_KV_CACHE

		# user config variables
		DOC_SYMLINKS_DIR INSTALL_MASK PKG_INSTALL_MASK

		# CCACHE and DISTCC config
		"${!CCACHE_@}" "${!DISTCC_@}"
	)

	# Unset the collected variables before moving on to functions.
	unset -v "${REPLY[@]}"

	REPLY=(
		EXPORT_FUNCTIONS KV_to_int KV_major KV_micro KV_minor

		__abort_configure __abort_compile __abort_handler
		__abort_install __abort_prepare __abort_test
		__check_bash_version __compose_bzip2_cmd __dyn_configure
		__dyn_compile __dyn_install __dyn_prepare __dyn_pretend
		__dump_trace __dyn_unpack __dyn_clean __dyn_setup __dyn_help
		__dyn_test __ebuild_phase_with_hooks __eapi7_ver_compare_int
		__eapi7_ver_parse_range __ebuild_arg_to_phase
		__ebuild_phase_funcs __eapi7_ver_compare __eapi7_ver_split
		__ebuild_phase __ebuild_main __elog_base __eqaquote __eqatag
		__eend __filter_readonly_variables __has_phase_defined_up_to
		__helpers_die __hasgq __hasg __preprocess_ebuild_env
		__quiet_mode __qa_source __qa_call __repo_attr
		__strip_duplicate_slashes __source_all_bashrcs
		__source_env_files __save_ebuild_env __sb_append_var
		__start_distcc __set_colors __try_source __unset_colors
		__unpack_tar __vecho

		addpredict addwrite adddeny addread assert best_version
		contains_word configparser debug-print-function
		debug-print-section debug-print docompress default diropts
		docinto dostrip die einstall eqawarn exeinto exeopts ebegin
		eerror einfon econf einfo ewarn eend elog find0 get_KV
		has_version hasq hasv has inherit insinto insopts into libopts
		nonfatal portageq register_success_hook register_die_hook
		use_enable use_with unpack useq usev use

		# Defined by the "ebuild.sh" utility.
		${QA_INTERCEPTORS}
	)

	for _ in \
		pkg_{config,info,nofetch,postinst,preinst,pretend,postrm,prerm,setup} \
		src_{configure,compile,install,prepare,test,unpack}
	do
		REPLY+=( default_"${_}" __eapi{0,1,2,4,6,8}_"${_}" )
	done

	___eapi_has_version_functions && REPLY+=( ver_test ver_cut ver_rs )
	___eapi_has_einstalldocs && REPLY+=( einstalldocs )
	___eapi_has_eapply_user && REPLY+=( __readdir eapply_user )
	___eapi_has_get_libdir && REPLY+=( get_libdir )
	___eapi_has_in_iuse && REPLY+=( in_iuse )
	___eapi_has_eapply && REPLY+=( __eapply_patch eapply patch )
	___eapi_has_usex && REPLY+=( usex )

	# Destroy the collected functions.
	unset -f "${REPLY[@]}"

	# Clear out the triple underscore namespace as it is reserved by the PM.
	while IFS=' ' read -r _ _ REPLY; do
		if [[ ${REPLY} == ___* ]]; then
			unset -f "${REPLY}"
		fi
	done < <(declare -F)
	unset -v REPLY "${!___@}"

	declare -p
	declare -fp
)
