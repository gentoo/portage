#!/usr/bin/env bash
# Copyright 1999-2025 Gentoo Authors
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
	# MAPFILE is purposed as an array that undergoes two phases of assembly.
	# The first entails gathering the names of variables that are to be
	# unset. The second entails gathering the names of functions that are
	# to be unset.
	MAPFILE=()

	if has --exclude-init-phases "$@"; then
		MAPFILE+=(
			# Discard stale GNU Make POSIX Jobserver flags.
			MAKEFLAGS

			PORTAGE_DOCOMPRESS
			PORTAGE_DOCOMPRESS_SIZE_LIMIT
			PORTAGE_DOCOMPRESS_SKIP
			PORTAGE_DOSTRIP
			PORTAGE_DOSTRIP_SKIP
			S
			__E_DESTTREE
			__E_DOCDESTTREE
			__E_EXEDESTTREE
			__E_INSDESTTREE
		)
		if [[ -n ${PYTHONPATH} &&
			${PYTHONPATH%%:*} -ef ${PORTAGE_PYM_PATH} ]] ; then
			if [[ ${PYTHONPATH} == *:* ]] ; then
				export PYTHONPATH=${PYTHONPATH#*:}
			else
				MAPFILE+=( PYTHONPATH )
			fi
		fi

		# These variables contains build host specific configuration. We
		# want binpkgs generated on different sized hosts to be
		# identical, so strip them from the binpkg. It's also not needed
		# for installing / removing a package.
		unset MAKEOPTS NINJAOPTS
	fi

	MAPFILE+=(
		# Variables that can influence the behaviour of GNU coreutils.
		BLOCK_SIZE
		COLORTERM
		COLUMNS
		DF_BLOCK_SIZE
		DU_BLOCK_SIZE
		HOME
		LS_BLOCK_SIZE
		LS_COLORS
		POSIXLY_CORRECT
		PWD
		QUOTING_STYLE
		TABSIZE
		TERM
		TIME_STYLE
		TMPDIR

		# Miscellaneous variables inherited from the operating environment.
		DISPLAY
		EDITOR
		LESS
		LESSOPEN
		LOGNAME
		PAGER
		TERMCAP
		USER
		ftp_proxy
		http_proxy
		https_proxy
		no_proxy

		# Other variables inherited from the operating environment.
		"${!SSH_@}"
		"${!XDG_CONFIG_@}"
		"${!XDG_CURRENT_@}"
		"${!XDG_DATA_@}"
		"${!XDG_MENU_@}"
		"${!XDG_RUNTIME_@}"
		"${!XDG_SEAT_@}"
		"${!XDG_SESSION_@}"
		CVS_RSH
		ECHANGELOG_USER
		GPG_AGENT_INFO
		SHELL_SETS_TITLE
		STY
		WINDOW
		XAUTHORITY
		XDG_VTNR

		# Portage config variables and variables set directly by portage.
		ACCEPT_LICENSE
		BUILD_PREFIX
		DISTDIR
		DOC_SYMLINKS_DIR
		EBUILD_FORCE_TEST
		FAKEROOTKEY
		LD_PRELOAD
		NOCOLOR
		NO_COLOR
		PKGDIR
		PKGUSE
		PKG_LOGDIR
		PKG_TMPDIR
		PORTAGE_BASHRC_FILES
		PORTAGE_COMPRESS
		PORTAGE_COMPRESS_EXCLUDE_SUFFIXES
		PORTAGE_DOHTML_UNWARNED_SKIPPED_EXTENSIONS
		PORTAGE_DOHTML_UNWARNED_SKIPPED_FILES
		PORTAGE_DOHTML_WARN_ON_SKIPPED_FILES
		PORTAGE_QUIET
		PORTAGE_SANDBOX_DENY
		PORTAGE_SANDBOX_PREDICT
		PORTAGE_SANDBOX_READ
		PORTAGE_SANDBOX_WRITE
		PORTAGE_SOCKS5_PROXY
		PREROOTPATH
		ROOT
		ROOTPATH
		RPMDIR
		USE_EXPAND

		# Variables set directly in bash following ebuild.sh execution.
		COLS
		EBUILD_MASTER_PID
		ECLASS_DEPTH
		ENDCOL
		HOME
		LAST_E_CMD
		LAST_E_LEN
		MISC_FUNCTIONS_ARGS
		MOPREFIX
		PORTAGE_BASHRCS_SOURCED
		PORTAGE_COLOR_BAD
		PORTAGE_COLOR_BRACKET
		PORTAGE_COLOR_ERR
		PORTAGE_COLOR_GOOD
		PORTAGE_COLOR_HILITE
		PORTAGE_COLOR_INFO
		PORTAGE_COLOR_LOG
		PORTAGE_COLOR_NORMAL
		PORTAGE_COLOR_QAWARN
		PORTAGE_COLOR_WARN
		PORTAGE_NONFATAL
		QA_INTERCEPTORS
		RC_DOT_PATTERN
		RC_ENDCOL
		RC_INDENTATION
		TEMP
		TMP
		TMPDIR
		XARGS
		_RC_GET_KV_CACHE

		# User config variables.
		DOC_SYMLINKS_DIR
		INSTALL_MASK
		PKG_INSTALL_MASK

		# CCACHE and DISTCC configuration variables.
		"${!CCACHE_@}"
		"${!DISTCC_@}"
	)

	# Unset the collected variables before moving on to functions.
	unset -v "${MAPFILE[@]}"

	MAPFILE=(
		EXPORT_FUNCTIONS
		KV_major
		KV_micro
		KV_minor
		KV_to_int

		__abort_compile
		__abort_configure
		__abort_handler
		__abort_install
		__abort_prepare
		__abort_test
		__check_bash_version
		__dump_trace
		__dyn_clean
		__dyn_compile
		__dyn_configure
		__dyn_help
		__dyn_install
		__dyn_prepare
		__dyn_pretend
		__dyn_setup
		__dyn_test
		__dyn_unpack
		__ebuild_arg_to_phase
		__ebuild_main
		__ebuild_phase
		__ebuild_phase_funcs
		__ebuild_phase_with_hooks
		__eend
		__elog_base
		__eqaquote
		__eqatag
		__filter_readonly_variables
		__has_phase_defined_up_to
		__hasg
		__hasgq
		__helpers_die
		__preprocess_ebuild_env
		__qa_call
		__qa_source
		__quiet_mode
		__repo_attr
		__save_ebuild_env
		__sb_append_var
		__set_colors
		__source_all_bashrcs
		__source_env_files
		__start_distcc
		__strip_duplicate_slashes
		__try_source
		__unset_colors
		__vecho
		__ver_compare
		__ver_compare_int
		__ver_parse_range
		__ver_split

		adddeny
		addpredict
		addread
		addwrite
		assert
		best_version
		configparser
		contains_word
		debug-print
		debug-print-function
		debug-print-section
		default
		die
		diropts
		docinto
		docompress
		dostrip
		ebegin
		econf
		eend
		eerror
		einfo
		einfon
		einstall
		elog
		eqawarn
		ewarn
		exeinto
		exeopts
		find0
		get_KV
		has
		has_version
		hasq
		hasv
		inherit
		insinto
		insopts
		into
		libopts
		nonfatal
		portageq
		register_die_hook
		register_success_hook
		unpack
		use
		use_enable
		use_with
		useq
		usev

		# Defined by the "ebuild.sh" utility.
		${QA_INTERCEPTORS}
	)

	for REPLY in \
		pkg_{config,info,nofetch,postinst,preinst,pretend,postrm,prerm,setup} \
		src_{configure,compile,install,prepare,test,unpack}
	do
		MAPFILE+=( default_"${REPLY}" __eapi{0,1,2,4,6,8}_"${REPLY}" )
	done

	___eapi_has_version_functions && MAPFILE+=( ver_test ver_cut ver_rs )
	___eapi_has_einstalldocs && MAPFILE+=( einstalldocs )
	___eapi_has_eapply_user && MAPFILE+=( __readdir eapply_user )
	___eapi_has_get_libdir && MAPFILE+=( get_libdir )
	___eapi_has_in_iuse && MAPFILE+=( in_iuse )
	___eapi_has_eapply && MAPFILE+=( __eapply_patch eapply patch )
	___eapi_has_usex && MAPFILE+=( usex )
	___eapi_has_pipestatus && MAPFILE+=( pipestatus )
	___eapi_has_ver_replacing && MAPFILE+=( ver_replacing )
	___eapi_has_edo && MAPFILE+=( edo )

	# Destroy the collected functions.
	unset -f "${MAPFILE[@]}"

	# Clear out the triple underscore namespace as it is reserved by the PM.
	while IFS=' ' read -r _ _ REPLY; do
		if [[ ${REPLY} == ___* ]]; then
			unset -f "${REPLY}"
		fi
	done < <(declare -F)
	unset -v MAPFILE REPLY "${!___@}"

	declare -p
	declare -fp
)
