#!/bin/bash
# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

ebuild_phase() {
	declare -F "$1" >/dev/null && qa_call $1
}

ebuild_phase_with_hooks() {
	local x phase_name=${1}
	for x in {pre_,,post_}${phase_name} ; do
		ebuild_phase ${x}
	done
}

dyn_pretend() {
	if [[ -e $PORTAGE_BUILDDIR/.pretended ]] ; then
		vecho ">>> It appears that '$PF' is already pretended; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.pretended' to force pretend."
		return 0
	fi
	ebuild_phase pre_pkg_pretend
	ebuild_phase pkg_pretend
	>> "$PORTAGE_BUILDDIR/.pretended" || \
		die "Failed to create $PORTAGE_BUILDDIR/.pretended"
	ebuild_phase post_pkg_pretend
}

dyn_setup() {
	if [[ -e $PORTAGE_BUILDDIR/.setuped ]] ; then
		vecho ">>> It appears that '$PF' is already setup; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.setuped' to force setup."
		return 0
	fi
	ebuild_phase pre_pkg_setup
	ebuild_phase pkg_setup
	>> "$PORTAGE_BUILDDIR/.setuped" || \
		die "Failed to create $PORTAGE_BUILDDIR/.setuped"
	ebuild_phase post_pkg_setup
}

dyn_unpack() {
	if [[ -f ${PORTAGE_BUILDDIR}/.unpacked ]] ; then
		vecho ">>> WORKDIR is up-to-date, keeping..."
		return 0
	fi
	if [ ! -d "${WORKDIR}" ]; then
		install -m${PORTAGE_WORKDIR_MODE:-0700} -d "${WORKDIR}" || die "Failed to create dir '${WORKDIR}'"
	fi
	cd "${WORKDIR}" || die "Directory change failed: \`cd '${WORKDIR}'\`"
	ebuild_phase pre_src_unpack
	vecho ">>> Unpacking source..."
	ebuild_phase src_unpack
	>> "$PORTAGE_BUILDDIR/.unpacked" || \
		die "Failed to create $PORTAGE_BUILDDIR/.unpacked"
	vecho ">>> Source unpacked in ${WORKDIR}"
	ebuild_phase post_src_unpack
}

dyn_clean() {
	if [ -z "${PORTAGE_BUILDDIR}" ]; then
		echo "Aborting clean phase because PORTAGE_BUILDDIR is unset!"
		return 1
	elif [ ! -d "${PORTAGE_BUILDDIR}" ] ; then
		return 0
	fi
	if has chflags $FEATURES ; then
		chflags -R noschg,nouchg,nosappnd,nouappnd "${PORTAGE_BUILDDIR}"
		chflags -R nosunlnk,nouunlnk "${PORTAGE_BUILDDIR}" 2>/dev/null
	fi

	rm -rf "${PORTAGE_BUILDDIR}/image" "${PORTAGE_BUILDDIR}/homedir"
	rm -f "${PORTAGE_BUILDDIR}/.installed"

	if [[ $EMERGE_FROM = binary ]] || \
		! has keeptemp $FEATURES && ! has keepwork $FEATURES ; then
		rm -rf "${T}"
	fi

	if [[ $EMERGE_FROM = binary ]] || ! has keepwork $FEATURES; then
		rm -f "$PORTAGE_BUILDDIR"/.{ebuild_changed,logid,pretended,setuped,unpacked,prepared} \
			"$PORTAGE_BUILDDIR"/.{configured,compiled,tested,packaged} \
			"$PORTAGE_BUILDDIR"/.die_hooks \
			"$PORTAGE_BUILDDIR"/.ipc_{in,out,lock} \
			"$PORTAGE_BUILDDIR"/.exit_status

		rm -rf "${PORTAGE_BUILDDIR}/build-info"
		rm -rf "${WORKDIR}"
	fi

	if [ -f "${PORTAGE_BUILDDIR}/.unpacked" ]; then
		find "${PORTAGE_BUILDDIR}" -type d ! -regex "^${WORKDIR}" | sort -r | tr "\n" "\0" | $XARGS -0 rmdir &>/dev/null
	fi

	# do not bind this to doebuild defined DISTDIR; don't trust doebuild, and if mistakes are made it'll
	# result in it wiping the users distfiles directory (bad).
	rm -rf "${PORTAGE_BUILDDIR}/distdir"

	# Some kernels, such as Solaris, return EINVAL when an attempt
	# is made to remove the current working directory.
	cd "$PORTAGE_BUILDDIR"/../..
	rmdir "$PORTAGE_BUILDDIR" 2>/dev/null

	true
}

abort_handler() {
	local msg
	if [ "$2" != "fail" ]; then
		msg="${EBUILD}: ${1} aborted; exiting."
	else
		msg="${EBUILD}: ${1} failed; exiting."
	fi
	echo
	echo "$msg"
	echo
	eval ${3}
	#unset signal handler
	trap - SIGINT SIGQUIT
}

abort_prepare() {
	abort_handler src_prepare $1
	rm -f "$PORTAGE_BUILDDIR/.prepared"
	exit 1
}

abort_configure() {
	abort_handler src_configure $1
	rm -f "$PORTAGE_BUILDDIR/.configured"
	exit 1
}

abort_compile() {
	abort_handler "src_compile" $1
	rm -f "${PORTAGE_BUILDDIR}/.compiled"
	exit 1
}

abort_test() {
	abort_handler "dyn_test" $1
	rm -f "${PORTAGE_BUILDDIR}/.tested"
	exit 1
}

abort_install() {
	abort_handler "src_install" $1
	rm -rf "${PORTAGE_BUILDDIR}/image"
	exit 1
}

has_phase_defined_up_to() {
	local phase
	for phase in unpack prepare configure compile install; do
		has ${phase} ${DEFINED_PHASES} && return 0
		[[ ${phase} == $1 ]] && return 1
	done
	# We shouldn't actually get here
	return 1
}

dyn_prepare() {

	if [[ -e $PORTAGE_BUILDDIR/.prepared ]] ; then
		vecho ">>> It appears that '$PF' is already prepared; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.prepared' to force prepare."
		return 0
	fi

	if [[ -d $S ]] ; then
		cd "${S}"
	elif has $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to prepare; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	trap abort_prepare SIGINT SIGQUIT

	ebuild_phase pre_src_prepare
	vecho ">>> Preparing source in $PWD ..."
	ebuild_phase src_prepare
	>> "$PORTAGE_BUILDDIR/.prepared" || \
		die "Failed to create $PORTAGE_BUILDDIR/.prepared"
	vecho ">>> Source prepared."
	ebuild_phase post_src_prepare

	trap - SIGINT SIGQUIT
}

dyn_configure() {

	if [[ -e $PORTAGE_BUILDDIR/.configured ]] ; then
		vecho ">>> It appears that '$PF' is already configured; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.configured' to force configuration."
		return 0
	fi

	if [[ -d $S ]] ; then
		cd "${S}"
	elif has $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to configure; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	trap abort_configure SIGINT SIGQUIT

	ebuild_phase pre_src_configure

	vecho ">>> Configuring source in $PWD ..."
	ebuild_phase src_configure
	>> "$PORTAGE_BUILDDIR/.configured" || \
		die "Failed to create $PORTAGE_BUILDDIR/.configured"
	vecho ">>> Source configured."

	ebuild_phase post_src_configure

	trap - SIGINT SIGQUIT
}

dyn_compile() {

	if [[ -e $PORTAGE_BUILDDIR/.compiled ]] ; then
		vecho ">>> It appears that '${PF}' is already compiled; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.compiled' to force compilation."
		return 0
	fi

	if [[ -d $S ]] ; then
		cd "${S}"
	elif has $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to compile; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	trap abort_compile SIGINT SIGQUIT

	if has distcc $FEATURES && has distcc-pump $FEATURES ; then
		if [[ -z $INCLUDE_SERVER_PORT ]] || [[ ! -w $INCLUDE_SERVER_PORT ]] ; then
			eval $(pump --startup)
			trap "pump --shutdown" EXIT
		fi
	fi

	ebuild_phase pre_src_compile

	vecho ">>> Compiling source in $PWD ..."
	ebuild_phase src_compile
	>> "$PORTAGE_BUILDDIR/.compiled" || \
		die "Failed to create $PORTAGE_BUILDDIR/.compiled"
	vecho ">>> Source compiled."

	ebuild_phase post_src_compile

	trap - SIGINT SIGQUIT
}

dyn_test() {

	if [[ -e $PORTAGE_BUILDDIR/.tested ]] ; then
		vecho ">>> It appears that ${PN} has already been tested; skipping."
		vecho ">>> Remove '${PORTAGE_BUILDDIR}/.tested' to force test."
		return
	fi

	if [ "${EBUILD_FORCE_TEST}" == "1" ] ; then
		# If USE came from ${T}/environment then it might not have USE=test
		# like it's supposed to here.
		! has test ${USE} && export USE="${USE} test"
	fi

	trap "abort_test" SIGINT SIGQUIT
	if [ -d "${S}" ]; then
		cd "${S}"
	else
		cd "${WORKDIR}"
	fi

	if ! has test $FEATURES && [ "${EBUILD_FORCE_TEST}" != "1" ]; then
		vecho ">>> Test phase [not enabled]: ${CATEGORY}/${PF}"
	elif has test $RESTRICT; then
		einfo "Skipping make test/check due to ebuild restriction."
		vecho ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	else
		local save_sp=${SANDBOX_PREDICT}
		addpredict /
		ebuild_phase pre_src_test
		ebuild_phase src_test
		>> "$PORTAGE_BUILDDIR/.tested" || \
			die "Failed to create $PORTAGE_BUILDDIR/.tested"
		ebuild_phase post_src_test
		SANDBOX_PREDICT=${save_sp}
	fi

	trap - SIGINT SIGQUIT
}

dyn_install() {
	[ -z "$PORTAGE_BUILDDIR" ] && die "${FUNCNAME}: PORTAGE_BUILDDIR is unset"
	if has noauto $FEATURES ; then
		rm -f "${PORTAGE_BUILDDIR}/.installed"
	elif [[ -e $PORTAGE_BUILDDIR/.installed ]] ; then
		vecho ">>> It appears that '${PF}' is already installed; skipping."
		vecho ">>> Remove '${PORTAGE_BUILDDIR}/.installed' to force install."
		return 0
	fi
	trap "abort_install" SIGINT SIGQUIT
	ebuild_phase pre_src_install
	rm -rf "${PORTAGE_BUILDDIR}/image"
	mkdir "${PORTAGE_BUILDDIR}/image"
	if [[ -d $S ]] ; then
		cd "${S}"
	elif has $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to install; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	vecho
	vecho ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D

	# Reset exeinto(), docinto(), insinto(), and into() state variables
	# in case the user is running the install phase multiple times
	# consecutively via the ebuild command.
	export DESTTREE=/usr
	export INSDESTTREE=""
	export _E_EXEDESTTREE_=""
	export _E_DOCDESTTREE_=""

	ebuild_phase src_install
	>> "$PORTAGE_BUILDDIR/.installed" || \
		die "Failed to create $PORTAGE_BUILDDIR/.installed"
	vecho ">>> Completed installing ${PF} into ${D}"
	vecho
	ebuild_phase post_src_install

	cd "${PORTAGE_BUILDDIR}"/build-info
	set -f
	local f x
	IFS=$' \t\n\r'
	for f in CATEGORY DEFINED_PHASES FEATURES INHERITED IUSE REQUIRED_USE \
		PF PKGUSE SLOT KEYWORDS HOMEPAGE DESCRIPTION ; do
		x=$(echo -n ${!f})
		[[ -n $x ]] && echo "$x" > $f
	done
	if [[ $CATEGORY != virtual ]] ; then
		for f in ASFLAGS CBUILD CC CFLAGS CHOST CTARGET CXX \
			CXXFLAGS EXTRA_ECONF EXTRA_EINSTALL EXTRA_MAKE \
			LDFLAGS LIBCFLAGS LIBCXXFLAGS ; do
			x=$(echo -n ${!f})
			[[ -n $x ]] && echo "$x" > $f
		done
	fi
	echo "${USE}"       > USE
	echo "${EAPI:-0}"   > EAPI
	set +f

	# local variables can leak into the saved environment.
	unset f

	save_ebuild_env --exclude-init-phases | filter_readonly_variables \
		--filter-path --filter-sandbox --allow-extra-vars > environment
	assert "save_ebuild_env failed"

	${PORTAGE_BZIP2_COMMAND} -f9 environment

	cp "${EBUILD}" "${PF}.ebuild"
	[ -n "${PORTAGE_REPO_NAME}" ]  && echo "${PORTAGE_REPO_NAME}" > repository
	if has nostrip ${FEATURES} ${RESTRICT} || has strip ${RESTRICT}
	then
		>> DEBUGBUILD
	fi
	trap - SIGINT SIGQUIT
}

dyn_preinst() {
	if [ -z "${D}" ]; then
		eerror "${FUNCNAME}: D is unset"
		return 1
	fi
	ebuild_phase_with_hooks pkg_preinst
}

dyn_help() {
	echo
	echo "Portage"
	echo "Copyright 1999-2010 Gentoo Foundation"
	echo
	echo "How to use the ebuild command:"
	echo
	echo "The first argument to ebuild should be an existing .ebuild file."
	echo
	echo "One or more of the following options can then be specified.  If more"
	echo "than one option is specified, each will be executed in order."
	echo
	echo "  help        : show this help screen"
	echo "  pretend     : execute package specific pretend actions"
	echo "  setup       : execute package specific setup actions"
	echo "  fetch       : download source archive(s) and patches"
	echo "  digest      : create a manifest file for the package"
	echo "  manifest    : create a manifest file for the package"
	echo "  unpack      : unpack sources (auto-dependencies if needed)"
	echo "  prepare     : prepare sources (auto-dependencies if needed)"
	echo "  configure   : configure sources (auto-fetch/unpack if needed)"
	echo "  compile     : compile sources (auto-fetch/unpack/configure if needed)"
	echo "  test        : test package (auto-fetch/unpack/configure/compile if needed)"
	echo "  preinst     : execute pre-install instructions"
	echo "  postinst    : execute post-install instructions"
	echo "  install     : install the package to the temporary install directory"
	echo "  qmerge      : merge image into live filesystem, recording files in db"
	echo "  merge       : do fetch, unpack, compile, install and qmerge"
	echo "  prerm       : execute pre-removal instructions"
	echo "  postrm      : execute post-removal instructions"
	echo "  unmerge     : remove package from live filesystem"
	echo "  config      : execute package specific configuration actions"
	echo "  package     : create a tarball package in ${PKGDIR}/All"
	echo "  rpm         : build a RedHat RPM package"
	echo "  clean       : clean up all source and temporary files"
	echo
	echo "The following settings will be used for the ebuild process:"
	echo
	echo "  package     : ${PF}"
	echo "  slot        : ${SLOT}"
	echo "  category    : ${CATEGORY}"
	echo "  description : ${DESCRIPTION}"
	echo "  system      : ${CHOST}"
	echo "  c flags     : ${CFLAGS}"
	echo "  c++ flags   : ${CXXFLAGS}"
	echo "  make flags  : ${MAKEOPTS}"
	echo -n "  build mode  : "
	if has nostrip ${FEATURES} ${RESTRICT} || has strip ${RESTRICT} ;
	then
		echo "debug (large)"
	else
		echo "production (stripped)"
	fi
	echo "  merge to    : ${ROOT}"
	echo
	if [ -n "$USE" ]; then
		echo "Additionally, support for the following optional features will be enabled:"
		echo
		echo "  ${USE}"
	fi
	echo
}

# @FUNCTION: _ebuild_arg_to_phase
# @DESCRIPTION:
# Translate a known ebuild(1) argument into the precise
# name of it's corresponding ebuild phase.
_ebuild_arg_to_phase() {
	[ $# -ne 2 ] && die "expected exactly 2 args, got $#: $*"
	local eapi=$1
	local arg=$2
	local phase_func=""

	case "$arg" in
		pretend)
			! has $eapi 0 1 2 3 3_pre2 && \
				phase_func=pkg_pretend
			;;
		setup)
			phase_func=pkg_setup
			;;
		nofetch)
			phase_func=pkg_nofetch
			;;
		unpack)
			phase_func=src_unpack
			;;
		prepare)
			! has $eapi 0 1 && \
				phase_func=src_prepare
			;;
		configure)
			! has $eapi 0 1 && \
				phase_func=src_configure
			;;
		compile)
			phase_func=src_compile
			;;
		test)
			phase_func=src_test
			;;
		install)
			phase_func=src_install
			;;
		preinst)
			phase_func=pkg_preinst
			;;
		postinst)
			phase_func=pkg_postinst
			;;
		prerm)
			phase_func=pkg_prerm
			;;
		postrm)
			phase_func=pkg_postrm
			;;
	esac

	[[ -z $phase_func ]] && return 1
	echo "$phase_func"
	return 0
}

_ebuild_phase_funcs() {
	[ $# -ne 2 ] && die "expected exactly 2 args, got $#: $*"
	local eapi=$1
	local phase_func=$2
	local default_phases="pkg_nofetch src_unpack src_prepare src_configure
		src_compile src_install src_test"
	local x y default_func=""

	for x in pkg_nofetch src_unpack src_test ; do
		declare -F $x >/dev/null || \
			eval "$x() { _eapi0_$x \"\$@\" ; }"
	done

	case $eapi in

		0|1)

			if ! declare -F src_compile >/dev/null ; then
				case $eapi in
					0)
						src_compile() { _eapi0_src_compile "$@" ; }
						;;
					*)
						src_compile() { _eapi1_src_compile "$@" ; }
						;;
				esac
			fi

			for x in $default_phases ; do
				eval "default_$x() {
					die \"default_$x() is not supported with EAPI='$eapi' during phase $phase_func\"
				}"
			done

			eval "default() {
				die \"default() is not supported with EAPI='$eapi' during phase $phase_func\"
			}"

			;;

		*)

			declare -F src_configure >/dev/null || \
				src_configure() { _eapi2_src_configure "$@" ; }

			declare -F src_compile >/dev/null || \
				src_compile() { _eapi2_src_compile "$@" ; }

			has $eapi 2 3 3_pre2 || declare -F src_install >/dev/null || \
				src_install() { _eapi4_src_install "$@" ; }

			if has $phase_func $default_phases ; then

				_eapi2_pkg_nofetch   () { _eapi0_pkg_nofetch          "$@" ; }
				_eapi2_src_unpack    () { _eapi0_src_unpack           "$@" ; }
				_eapi2_src_prepare   () { true                             ; }
				_eapi2_src_test      () { _eapi0_src_test             "$@" ; }
				_eapi2_src_install   () { die "$FUNCNAME is not supported" ; }

				for x in $default_phases ; do
					eval "default_$x() { _eapi2_$x \"\$@\" ; }"
				done

				eval "default() { _eapi2_$phase_func \"\$@\" ; }"

				case $eapi in
					2|3)
						;;
					*)
						eval "default_src_install() { _eapi4_src_install \"\$@\" ; }"
						[[ $phase_func = src_install ]] && \
							eval "default() { _eapi4_$phase_func \"\$@\" ; }"
						;;
				esac

			else

				for x in $default_phases ; do
					eval "default_$x() {
						die \"default_$x() is not supported in phase $default_func\"
					}"
				done

				eval "default() {
					die \"default() is not supported with EAPI='$eapi' during phase $phase_func\"
				}"

			fi

			;;
	esac
}
