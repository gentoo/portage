#!/bin/bash
# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# @FUNCTION: save_ebuild_env
# @DESCRIPTION:
# echo the current environment to stdout, filtering out redundant info.
#
# --exclude-init-phases causes pkg_nofetch and src_* phase functions to
# be excluded from the output. These function are not needed for installation
# or removal of the packages, and can therefore be safely excluded.
#
save_ebuild_env() {
	(
	if has --exclude-init-phases $* ; then
		unset S _E_DOCDESTTREE_ _E_EXEDESTTREE_ \
			PORTAGE_DOCOMPRESS PORTAGE_DOCOMPRESS_SKIP
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
		pkg_prerm pkg_postrm ; do
		unset -f default_$x _eapi{0,1,2,3,4}_$x
	done
	unset x

	unset -f assert assert_sigpipe_ok \
		dump_trace die diefunc \
		quiet_mode vecho elog_base eqawarn elog \
		esyslog einfo einfon ewarn eerror ebegin _eend eend KV_major \
		KV_minor KV_micro KV_to_int get_KV unset_colors set_colors has \
		has_phase_defined_up_to \
		hasv hasq qa_source qa_call \
		addread addwrite adddeny addpredict _sb_append_var \
		use usev useq has_version portageq \
		best_version use_with use_enable register_die_hook \
		keepdir unpack strip_duplicate_slashes econf einstall \
		dyn_setup dyn_unpack dyn_clean into insinto exeinto docinto \
		insopts diropts exeopts libopts docompress \
		abort_handler abort_prepare abort_configure abort_compile \
		abort_test abort_install dyn_prepare dyn_configure \
		dyn_compile dyn_test dyn_install \
		dyn_preinst dyn_pretend dyn_help debug-print debug-print-function \
		debug-print-section helpers_die inherit EXPORT_FUNCTIONS \
		nonfatal register_success_hook remove_path_entry \
		save_ebuild_env filter_readonly_variables preprocess_ebuild_env \
		set_unless_changed unset_unless_changed source_all_bashrcs \
		ebuild_main ebuild_phase ebuild_phase_with_hooks \
		_ebuild_arg_to_phase _ebuild_phase_funcs default \
		_hasg _hasgq _unpack_tar \
		${QA_INTERCEPTORS}

	case "${EAPI}" in
		0|1|2|3|4|4-python|4-slot-abi) ;;
		*) unset -f usex ;;
	esac

	# portage config variables and variables set directly by portage
	unset ACCEPT_LICENSE BAD BRACKET BUILD_PREFIX COLS \
		DISTCC_DIR DISTDIR DOC_SYMLINKS_DIR \
		EBUILD_FORCE_TEST EBUILD_MASTER_PID \
		ECLASS_DEPTH ENDCOL FAKEROOTKEY \
		GOOD HILITE HOME \
		LAST_E_CMD LAST_E_LEN LD_PRELOAD MISC_FUNCTIONS_ARGS MOPREFIX \
		NOCOLOR NORMAL PKGDIR PKGUSE PKG_LOGDIR PKG_TMPDIR \
		PORTAGE_BASHRCS_SOURCED PORTAGE_COMPRESS \
		PORTAGE_COMPRESS_EXCLUDE_SUFFIXES \
		PORTAGE_DOHTML_UNWARNED_SKIPPED_EXTENSIONS \
		PORTAGE_DOHTML_UNWARNED_SKIPPED_FILES \
		PORTAGE_DOHTML_WARN_ON_SKIPPED_FILES \
		PORTAGE_NONFATAL PORTAGE_QUIET \
		PORTAGE_SANDBOX_DENY PORTAGE_SANDBOX_PREDICT \
		PORTAGE_SANDBOX_READ PORTAGE_SANDBOX_WRITE PREROOTPATH \
		QA_INTERCEPTORS \
		RC_DEFAULT_INDENT RC_DOT_PATTERN RC_ENDCOL RC_INDENTATION  \
		ROOT ROOTPATH RPMDIR TEMP TMP TMPDIR USE_EXPAND \
		WARN XARGS _RC_GET_KV_CACHE

	# user config variables
	unset DOC_SYMLINKS_DIR INSTALL_MASK PKG_INSTALL_MASK

	declare -p
	declare -fp
	if [[ ${BASH_VERSINFO[0]} == 3 ]]; then
		export
	fi
	)
}
