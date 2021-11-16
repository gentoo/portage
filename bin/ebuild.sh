#!/bin/bash
# Copyright 1999-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# Make sure this isn't exported to scripts we execute.
unset BASH_COMPAT
declare -F ___in_portage_iuse >/dev/null && export -n -f ___in_portage_iuse

source "${PORTAGE_BIN_PATH}/isolated-functions.sh" || exit 1

# Set up the bash version compatibility level.  This does not disable
# features when running with a newer version, but makes it so that when
# bash changes behavior in an incompatible way, the older behavior is
# used instead.
__check_bash_version() {
	# Figure out which min version of bash we require.
	local maj min
	if ___eapi_bash_3_2 ; then
		maj=3 min=2
	elif ___eapi_bash_4_2 ; then
		maj=4 min=2
	elif ___eapi_bash_5_0 ; then
		maj=5 min=0
	else
		return
	fi

	# Make sure the active bash is sane.
	if [[ ${BASH_VERSINFO[0]} -lt ${maj} ]] ||
	   [[ ${BASH_VERSINFO[0]} -eq ${maj} && ${BASH_VERSINFO[1]} -lt ${min} ]] ; then
		die ">=bash-${maj}.${min} is required"
	fi

	# Set the compat level in case things change with newer ones.  We must not
	# export this into the env otherwise we might break  other shell scripts we
	# execute (e.g. ones in /usr/bin).
	BASH_COMPAT="${maj}.${min}"

	# The variable above is new to bash-4.3.  For older versions, we have to use
	# a compat knob.  Further, the compat knob only exists with older versions
	# (e.g. bash-4.3 has compat42 but not compat43).  This means we only need to
	# turn the knob with older EAPIs, and only when running newer bash versions:
	# there is no bash-3.3 (it went 3.2 to 4.0), and when requiring bash-4.2, the
	# var works with bash-4.3+, and you don't need to set compat to 4.2 when you
	# are already running 4.2.
	if ___eapi_bash_3_2 && [[ ${BASH_VERSINFO[0]} -gt 3 ]] ; then
		shopt -s compat32
	fi
}
__check_bash_version

if [[ $EBUILD_PHASE != depend ]] ; then
	source "${PORTAGE_BIN_PATH}/phase-functions.sh" || die
	source "${PORTAGE_BIN_PATH}/save-ebuild-env.sh" || die
	source "${PORTAGE_BIN_PATH}/phase-helpers.sh" || die
	source "${PORTAGE_BIN_PATH}/bashrc-functions.sh" || die
else
	# These dummy functions are for things that are likely to be called
	# in global scope, even though they are completely useless during
	# the "depend" phase.
	funcs="diropts docompress dostrip exeopts get_KV insopts
		KV_major KV_micro KV_minor KV_to_int
		libopts register_die_hook register_success_hook
		__strip_duplicate_slashes
		use useq usev use_with use_enable"
	___eapi_has_usex && funcs+=" usex"
	___eapi_has_in_iuse && funcs+=" in_iuse"
	___eapi_has_get_libdir && funcs+=" get_libdir"
	# These functions die because calls to them during the "depend" phase
	# are considered to be severe QA violations.
	funcs+=" best_version has_version portageq"
	___eapi_has_master_repositories && funcs+=" master_repositories"
	___eapi_has_repository_path && funcs+=" repository_path"
	___eapi_has_available_eclasses && funcs+=" available_eclasses"
	___eapi_has_eclass_path && funcs+=" eclass_path"
	___eapi_has_license_path && funcs+=" license_path"
	for x in ${funcs} ; do
		eval "${x}() { die \"\${FUNCNAME}() calls are not allowed in global scope\"; }"
	done
	unset funcs x

	# prevent the shell from finding external executables
	# note: we can't use empty because it implies current directory
	_PORTAGE_ORIG_PATH=${PATH}
	export PATH=/dev/null
	command_not_found_handle() {
		die "External commands disallowed while sourcing ebuild: ${*}"
	}
fi

# Don't use sandbox's BASH_ENV for new shells because it does
# 'source /etc/profile' which can interfere with the build
# environment by modifying our PATH.
unset BASH_ENV

# This is just a temporary workaround for portage-9999 users since
# earlier portage versions do not detect a version change in this case
# (9999 to 9999) and therefore they try execute an incompatible version of
# ebuild.sh during the upgrade.
export PORTAGE_BZIP2_COMMAND=${PORTAGE_BZIP2_COMMAND:-bzip2} 

# These two functions wrap sourcing and calling respectively.  At present they
# perform a qa check to make sure eclasses and ebuilds and profiles don't mess
# with shell opts (shopts).  Ebuilds/eclasses changing shopts should reset them 
# when they are done.

__qa_source() {
	local shopts=$(shopt) OLDIFS="$IFS"
	local retval
	source "$@"
	retval=$?
	set +e
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while sourcing '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while sourcing '$*'"
	return $retval
}

__qa_call() {
	local shopts=$(shopt) OLDIFS="$IFS"
	local retval
	"$@"
	retval=$?
	set +e
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while calling '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while calling '$*'"
	return $retval
}

EBUILD_SH_ARGS="$*"

shift $#

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOBIGNORE
if ___eapi_has_ENV_UNSET; then
	for x in ${ENV_UNSET}; do
		unset "${x}"
	done
	unset x
fi

[[ $PORTAGE_QUIET != "" ]] && export PORTAGE_QUIET

# sandbox support functions; defined prior to profile.bashrc srcing, since the profile might need to add a default exception (/usr/lib64/conftest fex)
__sb_append_var() {
	local _v=$1 ; shift
	local var="SANDBOX_${_v}"
	[[ -z $1 || -n $2 ]] && die "Usage: add$(LC_ALL=C tr "[:upper:]" "[:lower:]" <<< "${_v}") <colon-delimited list of paths>"
	export ${var}="${!var:+${!var}:}$1"
}
# bash-4 version:
# local var="SANDBOX_${1^^}"
# addread() { __sb_append_var ${0#add} "$@" ; }
addread()    { __sb_append_var READ    "$@" ; }
addwrite()   { __sb_append_var WRITE   "$@" ; }
adddeny()    { __sb_append_var DENY    "$@" ; }
addpredict() { __sb_append_var PREDICT "$@" ; }

addwrite "${PORTAGE_TMPDIR}/portage"
addread "/:${PORTAGE_TMPDIR}/portage"
[[ -n ${PORTAGE_GPG_DIR} ]] && addpredict "${PORTAGE_GPG_DIR}"

# Avoid sandbox violations in temporary directories.
if [[ -w $T ]] ; then
	export TEMP=$T
	export TMP=$T
	export TMPDIR=$T
elif [[ $SANDBOX_ON = 1 ]] ; then
	for x in TEMP TMP TMPDIR ; do
		[[ -n ${!x} ]] && addwrite "${!x}"
	done
	unset x
fi

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON=0

# Ensure that $PWD is sane whenever possible, to protect against
# exploitation of insecure search path for python -c in ebuilds.
# See bug #239560, bug #469338, and bug #595028.
# EAPI 8 requires us to use an empty directory here.
if [[ -d ${PORTAGE_BUILDDIR}/empty ]]; then
	cd "${PORTAGE_BUILDDIR}/empty" || die
else
	cd "${PORTAGE_PYM_PATH}" || \
		die "PORTAGE_PYM_PATH does not exist: '${PORTAGE_PYM_PATH}'"
fi

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022

# Sources all eclasses in parameters
declare -ix ECLASS_DEPTH=0
inherit() {
	ECLASS_DEPTH=$(($ECLASS_DEPTH + 1))
	if [[ ${ECLASS_DEPTH} -gt 1 ]]; then
		debug-print "*** Multiple Inheritence (Level: ${ECLASS_DEPTH})"

		# Since ECLASS_DEPTH > 1, the following variables are locals from the
		# previous inherit call in the call stack.
		if [[ -n ${ECLASS} && -n ${!__export_funcs_var} ]] ; then
			eqawarn "QA Notice: EXPORT_FUNCTIONS is called before inherit in ${ECLASS}.eclass."
			eqawarn "For compatibility with PMS and to avoid breakage with Pkgcore, only call"
			eqawarn "EXPORT_FUNCTIONS after inherit(s). Portage behavior may change in future."
		fi
	fi

	local -x ECLASS
	local __export_funcs_var
	local repo_location
	local location
	local potential_location
	local x
	local B_IUSE
	local B_REQUIRED_USE
	local B_DEPEND
	local B_RDEPEND
	local B_PDEPEND
	local B_BDEPEND
	local B_IDEPEND
	local B_PROPERTIES
	local B_RESTRICT
	while [ "$1" ]; do
		location=""
		potential_location=""

		ECLASS="$1"
		__export_funcs_var=__export_functions_$ECLASS_DEPTH
		unset $__export_funcs_var

		if [[ ${EBUILD_PHASE} != depend && ${EBUILD_PHASE} != nofetch && \
			${EBUILD_PHASE} != *rm && ${EMERGE_FROM} != "binary" && \
			-z ${_IN_INSTALL_QA_CHECK} ]]
		then
			# This is disabled in the *rm phases because they frequently give
			# false alarms due to INHERITED in /var/db/pkg being outdated
			# in comparison to the eclasses from the ebuild repository. It's
			# disabled for nofetch, since that can be called by repoman and
			# that triggers bug #407449 due to repoman not exporting
			# non-essential variables such as INHERITED.
			if ! has $ECLASS $INHERITED $__INHERITED_QA_CACHE ; then
				eqawarn "QA Notice: ECLASS '$ECLASS' inherited illegally in $CATEGORY/$PF $EBUILD_PHASE"
			fi
		fi

		for repo_location in "${PORTAGE_ECLASS_LOCATIONS[@]}"; do
			potential_location="${repo_location}/eclass/${1}.eclass"
			if [[ -f ${potential_location} ]]; then
				location="${potential_location}"
				debug-print "  eclass exists: ${location}"
				break
			fi
		done
		debug-print "inherit: $1 -> $location"
		[[ -z ${location} ]] && die "${1}.eclass could not be found by inherit()"

		# inherits in QA checks can't handle metadata assignments
		if [[ -z ${_IN_INSTALL_QA_CHECK} ]]; then
			#We need to back up the values of *DEPEND to B_*DEPEND
			#(if set).. and then restore them after the inherit call.

			#turn off glob expansion
			set -f

			# Retain the old data and restore it later.
			unset B_IUSE B_REQUIRED_USE B_DEPEND B_RDEPEND B_PDEPEND
			unset B_BDEPEND B_IDEPEND B_PROPERTIES B_RESTRICT
			[ "${IUSE+set}"       = set ] && B_IUSE="${IUSE}"
			[ "${REQUIRED_USE+set}" = set ] && B_REQUIRED_USE="${REQUIRED_USE}"
			[ "${DEPEND+set}"     = set ] && B_DEPEND="${DEPEND}"
			[ "${RDEPEND+set}"    = set ] && B_RDEPEND="${RDEPEND}"
			[ "${PDEPEND+set}"    = set ] && B_PDEPEND="${PDEPEND}"
			[ "${BDEPEND+set}"    = set ] && B_BDEPEND="${BDEPEND}"
			unset IUSE REQUIRED_USE DEPEND RDEPEND PDEPEND BDEPEND IDEPEND

			if ___eapi_has_accumulated_PROPERTIES; then
				[[ ${PROPERTIES+set} == set ]] && B_PROPERTIES=${PROPERTIES}
				unset PROPERTIES
			fi
			if ___eapi_has_accumulated_RESTRICT; then
				[[ ${RESTRICT+set} == set ]] && B_RESTRICT=${RESTRICT}
				unset RESTRICT
			fi

			#turn on glob expansion
			set +f
		fi

		__qa_source "$location" || die "died sourcing $location in inherit()"
		
		if [[ -z ${_IN_INSTALL_QA_CHECK} ]]; then
			#turn off glob expansion
			set -f

			# If each var has a value, append it to the global variable E_* to
			# be applied after everything is finished. New incremental behavior.
			[ "${IUSE+set}"         = set ] && E_IUSE+="${E_IUSE:+ }${IUSE}"
			[ "${REQUIRED_USE+set}" = set ] && E_REQUIRED_USE+="${E_REQUIRED_USE:+ }${REQUIRED_USE}"
			[ "${DEPEND+set}"       = set ] && E_DEPEND+="${E_DEPEND:+ }${DEPEND}"
			[ "${RDEPEND+set}"      = set ] && E_RDEPEND+="${E_RDEPEND:+ }${RDEPEND}"
			[ "${PDEPEND+set}"      = set ] && E_PDEPEND+="${E_PDEPEND:+ }${PDEPEND}"
			[ "${BDEPEND+set}"      = set ] && E_BDEPEND+="${E_BDEPEND:+ }${BDEPEND}"
			[ "${IDEPEND+set}"      = set ] && E_IDEPEND+="${E_IDEPEND:+ }${IDEPEND}"

			[ "${B_IUSE+set}"     = set ] && IUSE="${B_IUSE}"
			[ "${B_IUSE+set}"     = set ] || unset IUSE
			
			[ "${B_REQUIRED_USE+set}"     = set ] && REQUIRED_USE="${B_REQUIRED_USE}"
			[ "${B_REQUIRED_USE+set}"     = set ] || unset REQUIRED_USE

			[ "${B_DEPEND+set}"   = set ] && DEPEND="${B_DEPEND}"
			[ "${B_DEPEND+set}"   = set ] || unset DEPEND

			[ "${B_RDEPEND+set}"  = set ] && RDEPEND="${B_RDEPEND}"
			[ "${B_RDEPEND+set}"  = set ] || unset RDEPEND

			[ "${B_PDEPEND+set}"  = set ] && PDEPEND="${B_PDEPEND}"
			[ "${B_PDEPEND+set}"  = set ] || unset PDEPEND

			[ "${B_BDEPEND+set}"  = set ] && BDEPEND="${B_BDEPEND}"
			[ "${B_BDEPEND+set}"  = set ] || unset BDEPEND

			[ "${B_IDEPEND+set}"  = set ] && IDEPEND="${B_IDEPEND}"
			[ "${B_IDEPEND+set}"  = set ] || unset IDEPEND

			if ___eapi_has_accumulated_PROPERTIES; then
				[[ ${PROPERTIES+set} == set ]] &&
					E_PROPERTIES+=${E_PROPERTIES:+ }${PROPERTIES}
				[[ ${B_PROPERTIES+set} == set ]] &&
					PROPERTIES=${B_PROPERTIES}
				[[ ${B_PROPERTIES+set} == set ]] ||
					unset PROPERTIES
			fi
			if ___eapi_has_accumulated_RESTRICT; then
				[[ ${RESTRICT+set} == set ]] &&
					E_RESTRICT+=${E_RESTRICT:+ }${RESTRICT}
				[[ ${B_RESTRICT+set} == set ]] &&
					RESTRICT=${B_RESTRICT}
				[[ ${B_RESTRICT+set} == set ]] ||
					unset RESTRICT
			fi

			#turn on glob expansion
			set +f

			if [[ -n ${!__export_funcs_var} ]] ; then
				for x in ${!__export_funcs_var} ; do
					debug-print "EXPORT_FUNCTIONS: $x -> ${ECLASS}_$x"
					declare -F "${ECLASS}_$x" >/dev/null || \
						die "EXPORT_FUNCTIONS: ${ECLASS}_$x is not defined"
					eval "$x() { ${ECLASS}_$x \"\$@\" ; }" > /dev/null
				done
			fi
			unset $__export_funcs_var

			has $1 $INHERITED || export INHERITED="$INHERITED $1"
			if [[ ${ECLASS_DEPTH} -eq 1 ]]; then
				export PORTAGE_EXPLICIT_INHERIT="${PORTAGE_EXPLICIT_INHERIT} $1"
			fi
		fi

		shift
	done
	((--ECLASS_DEPTH)) # Returns 1 when ECLASS_DEPTH reaches 0.
	return 0
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {
	if [ -z "$ECLASS" ]; then
		die "EXPORT_FUNCTIONS without a defined ECLASS"
	fi
	eval $__export_funcs_var+=\" $*\"
}

PORTAGE_BASHRCS_SOURCED=0

# @FUNCTION: __source_all_bashrcs
# @DESCRIPTION:
# Source a relevant bashrc files and perform other miscellaneous
# environment initialization when appropriate.
#
# If EAPI is set then define functions provided by the current EAPI:
#
#  * default_* aliases for the current EAPI phase functions
#  * A "default" function which is an alias for the default phase
#    function for the current phase.
#
__source_all_bashrcs() {
	[[ $PORTAGE_BASHRCS_SOURCED = 1 ]] && return 0
	PORTAGE_BASHRCS_SOURCED=1
	local x

	local OCC="${CC}" OCXX="${CXX}"

	if [[ $EBUILD_PHASE != depend ]] ; then
		# source the existing profile.bashrcs.
		while read -r x; do
			__try_source "${x}"
		done <<<"${PORTAGE_BASHRC_FILES}"
	fi

	# The user's bashrc is the ONLY non-portage bit of code
	# that can change shopts without a QA violation.
	__try_source --no-qa "${PORTAGE_BASHRC}"

	if [[ $EBUILD_PHASE != depend ]] ; then
		__source_env_files --no-qa "${PM_EBUILD_HOOK_DIR}"
	fi

	[ ! -z "${OCC}" ] && export CC="${OCC}"
	[ ! -z "${OCXX}" ] && export CXX="${OCXX}"
}

# @FUNCTION: __source_env_files
# @USAGE: [--no-qa] <ENV_DIRECTORY>
# @DESCRIPTION:
# Source the files relevant to the current package from the given path.
# If --no-qa is specified, use source instead of __qa_source to source the
# files.
__source_env_files() {
	local argument=()
	if [[ $1 == --no-qa ]]; then
		argument=( --no-qa )
	shift
	fi
	for x in "${1}"/${CATEGORY}/{${PN},${PN}:${SLOT%/*},${P},${PF}}; do
		__try_source "${argument[@]}" "${x}"
	done
}

# @FUNCTION: __try_source
# @USAGE: [--no-qa] <FILE>
# @DESCRIPTION:
# If the path given as argument exists, source the file while preserving
# $-.
# If --no-qa is specified, source the file with source instead of __qa_source.
__try_source() {
	local qa=true
	if [[ $1 == --no-qa ]]; then
		qa=false
		shift
	fi
	if [[ -r $1 && -f $1 ]]; then
		local debug_on=false
		if [[ "$PORTAGE_DEBUG" == "1" ]] && [[ "${-/x/}" == "$-" ]]; then
			debug_on=true
		fi
		$debug_on && set -x
		# If $- contains x, then tracing has already been enabled
		# elsewhere for some reason. We preserve it's state so as
		# not to interfere.
		if ! ${qa} ; then
			source "${1}"
		else
			__qa_source "${1}"
		fi
		$debug_on && set +x
	fi
}
# === === === === === === === === === === === === === === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === === === === === === === === === === === === === ===

export SANDBOX_ON="1"
export S=${WORKDIR}/${P}

# Turn of extended glob matching so that g++ doesn't get incorrectly matched.
shopt -u extglob

if [[ ${EBUILD_PHASE} == depend ]] ; then
	QA_INTERCEPTORS="awk bash cc egrep equery fgrep g++
		gawk gcc grep javac java-config nawk perl
		pkg-config python python-config sed"
elif [[ ${EBUILD_PHASE} == clean* ]] ; then
	unset QA_INTERCEPTORS
else
	QA_INTERCEPTORS="autoconf automake aclocal libtoolize"
fi
# level the QA interceptors if we're in depend
if [[ -n ${QA_INTERCEPTORS} ]] ; then
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=$(type -Pf ${BIN})
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		if [[ ${EBUILD_PHASE} == depend ]] ; then
			FUNC_SRC="${BIN}() {
				if [ \$ECLASS_DEPTH -gt 0 ]; then
					eqawarn \"QA Notice: '${BIN}' called in global scope: eclass \${ECLASS}\"
				else
					eqawarn \"QA Notice: '${BIN}' called in global scope: \${CATEGORY}/\${PF}\"
				fi
			${BODY}
			}"
		elif has ${BIN} autoconf automake aclocal libtoolize ; then
			FUNC_SRC="${BIN}() {
				if ! has \${FUNCNAME[1]} eautoreconf eaclocal _elibtoolize \\
					eautoheader eautoconf eautomake autotools_run_tool \\
					autotools_check_macro autotools_get_subdirs \\
					autotools_get_auxdir ; then
					eqawarn \"QA Notice: '${BIN}' called by \${FUNCNAME[1]}: \${CATEGORY}/\${PF}\"
					eqawarn \"Use autotools.eclass instead of calling '${BIN}' directly.\"
				fi
			${BODY}
			}"
		else
			FUNC_SRC="${BIN}() {
				eqawarn \"QA Notice: '${BIN}' called by \${FUNCNAME[1]}: \${CATEGORY}/\${PF}\"
			${BODY}
			}"
		fi
		eval "$FUNC_SRC" || echo "error creating QA interceptor ${BIN}" >&2
	done
	unset BIN_PATH BIN BODY FUNC_SRC
fi

# Subshell/helper die support (must export for the die helper).
export EBUILD_MASTER_PID=${BASHPID:-$(__bashpid)}
trap 'exit 1' SIGTERM

if ! has "$EBUILD_PHASE" clean cleanrm depend && \
	! [[ $EMERGE_FROM = ebuild && $EBUILD_PHASE = setup ]] && \
	[ -f "${T}"/environment ] ; then
	# The environment may have been extracted from environment.bz2 or
	# may have come from another version of ebuild.sh or something.
	# In any case, preprocess it to prevent any potential interference.
	# NOTE: export ${FOO}=... requires quoting, unlike normal exports
	__preprocess_ebuild_env || \
		die "error processing environment"
	# Colon separated SANDBOX_* variables need to be cumulative.
	for x in SANDBOX_DENY SANDBOX_READ SANDBOX_PREDICT SANDBOX_WRITE ; do
		export PORTAGE_${x}="${!x}"
	done
	PORTAGE_SANDBOX_ON=${SANDBOX_ON}
	export SANDBOX_ON=1
	source "${T}"/environment || \
		die "error sourcing environment"
	# We have to temporarily disable sandbox since the
	# SANDBOX_{DENY,READ,PREDICT,WRITE} values we've just loaded
	# may be unusable (triggering in spurious sandbox violations)
	# until we've merged them with our current values.
	export SANDBOX_ON=0
	for x in SANDBOX_DENY SANDBOX_PREDICT SANDBOX_READ SANDBOX_WRITE ; do
		y="PORTAGE_${x}"
		if [ -z "${!x}" ] ; then
			export ${x}="${!y}"
		elif [ -n "${!y}" ] && [ "${!y}" != "${!x}" ] ; then
			# filter out dupes
			export ${x}="$(printf "${!y}:${!x}" | tr ":" "\0" | \
				sort -z -u | tr "\0" ":")"
		fi
		export ${x}="${!x%:}"
		unset PORTAGE_${x}
	done
	unset x y
	export SANDBOX_ON=${PORTAGE_SANDBOX_ON}
	unset PORTAGE_SANDBOX_ON
	[[ -n $EAPI ]] || EAPI=0
fi

if ___eapi_enables_globstar; then
	shopt -s globstar
fi

# Convert quoted paths to array.
eval "PORTAGE_ECLASS_LOCATIONS=(${PORTAGE_ECLASS_LOCATIONS})"

# Source the ebuild every time for FEATURES=noauto, so that ebuild
# modifications take effect immediately.
if ! has "$EBUILD_PHASE" clean cleanrm ; then
	if [[ $EBUILD_PHASE = setup && $EMERGE_FROM = ebuild ]] || \
		[[ $EBUILD_PHASE = depend || ! -f $T/environment || \
		-f $PORTAGE_BUILDDIR/.ebuild_changed || \
		" ${FEATURES} " == *" noauto "* ]] ; then
		# The bashrcs get an opportunity here to set aliases that will be expanded
		# during sourcing of ebuilds and eclasses.
		__source_all_bashrcs

		# When EBUILD_PHASE != depend, INHERITED comes pre-initialized
		# from cache. In order to make INHERITED content independent of
		# EBUILD_PHASE during inherit() calls, we unset INHERITED after
		# we make a backup copy for QA checks.
		__INHERITED_QA_CACHE=$INHERITED

		# Catch failed globbing attempts in case ebuild writer forgot to
		# escape '*' or likes.
		# Note: this needs to be done before unsetting EAPI.
		if ___eapi_enables_failglob_in_global_scope; then
			shopt -s failglob
		fi

		# *DEPEND and IUSE will be set during the sourcing of the ebuild.
		# In order to ensure correct interaction between ebuilds and
		# eclasses, they need to be unset before this process of
		# interaction begins.
		unset EAPI DEPEND RDEPEND PDEPEND BDEPEND PROPERTIES RESTRICT
		unset INHERITED IUSE REQUIRED_USE ECLASS E_IUSE E_REQUIRED_USE
		unset E_DEPEND E_RDEPEND E_PDEPEND E_BDEPEND E_IDEPEND E_PROPERTIES
		unset E_RESTRICT PROVIDES_EXCLUDE REQUIRES_EXCLUDE
		unset PORTAGE_EXPLICIT_INHERIT

		if [[ $PORTAGE_DEBUG != 1 || ${-/x/} != $- ]] ; then
			source "$EBUILD" || die "error sourcing ebuild"
		else
			set -x
			source "$EBUILD" || die "error sourcing ebuild"
			set +x
		fi

		if ___eapi_enables_failglob_in_global_scope; then
			shopt -u failglob
		fi

		[ "${EAPI+set}" = set ] || EAPI=0

		# export EAPI for helpers (especially since we unset it above)
		export EAPI

		if ___eapi_has_RDEPEND_DEPEND_fallback; then
			export RDEPEND=${RDEPEND-${DEPEND}}
			debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
		fi

		# add in dependency info from eclasses
		IUSE+="${IUSE:+ }${E_IUSE}"
		DEPEND+="${DEPEND:+ }${E_DEPEND}"
		RDEPEND+="${RDEPEND:+ }${E_RDEPEND}"
		PDEPEND+="${PDEPEND:+ }${E_PDEPEND}"
		BDEPEND+="${BDEPEND:+ }${E_BDEPEND}"
		REQUIRED_USE+="${REQUIRED_USE:+ }${E_REQUIRED_USE}"

		if ___eapi_has_accumulated_PROPERTIES; then
			PROPERTIES+=${PROPERTIES:+ }${E_PROPERTIES}
		fi
		if ___eapi_has_accumulated_RESTRICT; then
			RESTRICT+=${RESTRICT:+ }${E_RESTRICT}
		fi

		unset ECLASS E_IUSE E_REQUIRED_USE E_DEPEND E_RDEPEND E_PDEPEND
		unset E_BDEPEND E_PROPERTIES E_RESTRICT __INHERITED_QA_CACHE

		if [[ "${EBUILD_PHASE}" != "depend" ]] ; then
			PROPERTIES=${PORTAGE_PROPERTIES}
			RESTRICT=${PORTAGE_RESTRICT}
			[[ -e $PORTAGE_BUILDDIR/.ebuild_changed ]] && \
			rm "$PORTAGE_BUILDDIR/.ebuild_changed"
		fi

		# alphabetically ordered by $EBUILD_PHASE value
		case ${EAPI} in
			0|1)
				_valid_phases="src_compile pkg_config pkg_info src_install
					pkg_nofetch pkg_postinst pkg_postrm pkg_preinst pkg_prerm
					pkg_setup src_test src_unpack"
				;;
			2|3)
				_valid_phases="src_compile pkg_config src_configure pkg_info
					src_install pkg_nofetch pkg_postinst pkg_postrm pkg_preinst
					src_prepare pkg_prerm pkg_setup src_test src_unpack"
				;;
			*)
				_valid_phases="src_compile pkg_config src_configure pkg_info
					src_install pkg_nofetch pkg_postinst pkg_postrm pkg_preinst
					src_prepare pkg_prerm pkg_pretend pkg_setup src_test src_unpack"
				;;
		esac

		DEFINED_PHASES=
		for _f in $_valid_phases ; do
			if declare -F $_f >/dev/null ; then
				_f=${_f#pkg_}
				DEFINED_PHASES+=" ${_f#src_}"
			fi
		done
		[[ -n $DEFINED_PHASES ]] || DEFINED_PHASES=-

		unset _f _valid_phases

		if [[ $EBUILD_PHASE != depend ]] ; then

			if has distcc $FEATURES ; then
				[[ -n $DISTCC_LOG ]] && addwrite "${DISTCC_LOG%/*}"
			fi

			if has ccache $FEATURES ; then

				if [[ -n $CCACHE_DIR ]] ; then
					addread "$CCACHE_DIR"
					addwrite "$CCACHE_DIR"
				fi

				[[ -n $CCACHE_SIZE ]] && ccache -M $CCACHE_SIZE &> /dev/null
			fi
		fi
	fi
fi

if has nostrip ${FEATURES} ${PORTAGE_RESTRICT} || has strip ${PORTAGE_RESTRICT}
then
	export DEBUGBUILD=1
fi

if [[ $EBUILD_PHASE = depend ]] ; then
	export SANDBOX_ON="0"
	set -f

	metadata_keys=(
		DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE
		DESCRIPTION KEYWORDS INHERITED IUSE REQUIRED_USE PDEPEND BDEPEND
		EAPI PROPERTIES DEFINED_PHASES IDEPEND INHERIT
	)

	if ! ___eapi_has_BDEPEND; then
		unset BDEPEND
	fi
	if ! ___eapi_has_IDEPEND; then
		unset IDEPEND
	fi

	INHERIT=${PORTAGE_EXPLICIT_INHERIT}

	# The extra $(echo) commands remove newlines.
	for f in "${metadata_keys[@]}" ; do
		echo "${f}=$(echo ${!f})" >&${PORTAGE_PIPE_FD} || exit $?
	done
	exec {PORTAGE_PIPE_FD}>&-
	set +f
else
	# Note: readonly variables interfere with __preprocess_ebuild_env(), so
	# declare them only after it has already run.
	declare -r $PORTAGE_READONLY_METADATA $PORTAGE_READONLY_VARS
	if ___eapi_has_prefix_variables; then
		declare -r ED EPREFIX EROOT
	fi
	if ___eapi_has_BROOT; then
		declare -r BROOT
	fi

	# If ${EBUILD_FORCE_TEST} == 1 and USE came from ${T}/environment
	# then it might not have USE=test like it's supposed to here.
	if [[ ${EBUILD_PHASE} == test && ${EBUILD_FORCE_TEST} == 1 ]] &&
		___in_portage_iuse test && ! has test ${USE} ; then
		export USE="${USE} test"
	fi
	declare -r USE

	if [[ -n $EBUILD_SH_ARGS ]] ; then
		(
			# Don't allow subprocesses to inherit the pipe which
			# emerge uses to monitor ebuild.sh.
			if [[ -n ${PORTAGE_PIPE_FD} ]] ; then
				eval "exec ${PORTAGE_PIPE_FD}>&-"
				unset PORTAGE_PIPE_FD
			fi
			__ebuild_main ${EBUILD_SH_ARGS}
			exit 0
		)
		exit $?
	fi
fi

# Do not exit when ebuild.sh is sourced by other scripts.
true
