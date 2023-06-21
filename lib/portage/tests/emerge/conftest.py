# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

import pytest


_INSTALL_SOMETHING = """
S="${WORKDIR}"

pkg_pretend() {
	einfo "called pkg_pretend for $CATEGORY/$PF"
}

src_install() {
	einfo "installing something..."
	insinto /usr/lib/${P}
	echo "blah blah blah" > "${T}"/regular-file
	doins "${T}"/regular-file
	dosym regular-file /usr/lib/${P}/symlink || die

	# Test CONFIG_PROTECT
	insinto /etc
	newins "${T}"/regular-file ${PN}-${SLOT%/*}

	# Test code for bug #381629, using a copyright symbol encoded with latin-1.
	# We use $(printf "\\xa9") rather than $'\\xa9', since printf apparently
	# works in any case, while $'\\xa9' transforms to \\xef\\xbf\\xbd under
	# some conditions. TODO: Find out why it transforms to \\xef\\xbf\\xbd when
	# running tests for Python 3.2 (even though it's bash that is ultimately
	# responsible for performing the transformation).
	local latin_1_dir=/usr/lib/${P}/latin-1-$(printf "\\xa9")-directory
	insinto "${latin_1_dir}"
	echo "blah blah blah" > "${T}"/latin-1-$(printf "\\xa9")-regular-file || die
	doins "${T}"/latin-1-$(printf "\\xa9")-regular-file
	dosym latin-1-$(printf "\\xa9")-regular-file ${latin_1_dir}/latin-1-$(printf "\\xa9")-symlink || die

	call_has_and_best_version
}

pkg_config() {
	einfo "called pkg_config for $CATEGORY/$PF"
}

pkg_info() {
	einfo "called pkg_info for $CATEGORY/$PF"
}

pkg_preinst() {
	if ! ___eapi_best_version_and_has_version_support_-b_-d_-r; then
		# The BROOT variable is unset during pkg_* phases for EAPI 7,
		# therefore best/has_version -b is expected to fail if we attempt
		# to call it for EAPI 7 here.
		call_has_and_best_version
	fi
}

call_has_and_best_version() {
	local root_arg
	if ___eapi_best_version_and_has_version_support_-b_-d_-r; then
		root_arg="-b"
	else
		root_arg="--host-root"
	fi
	einfo "called ${EBUILD_PHASE_FUNC} for $CATEGORY/$PF"
	einfo "EPREFIX=${EPREFIX}"
	einfo "PORTAGE_OVERRIDE_EPREFIX=${PORTAGE_OVERRIDE_EPREFIX}"
	einfo "ROOT=${ROOT}"
	einfo "EROOT=${EROOT}"
	einfo "SYSROOT=${SYSROOT}"
	einfo "ESYSROOT=${ESYSROOT}"
	einfo "BROOT=${BROOT}"
	# Test that has_version and best_version work correctly with
	# prefix (involves internal ROOT -> EROOT calculation in order
	# to support ROOT override via the environment with EAPIs 3
	# and later which support prefix).
	if has_version $CATEGORY/$PN:$SLOT ; then
		einfo "has_version detects an installed instance of $CATEGORY/$PN:$SLOT"
		einfo "best_version reports that the installed instance is $(best_version $CATEGORY/$PN:$SLOT)"
	else
		einfo "has_version does not detect an installed instance of $CATEGORY/$PN:$SLOT"
	fi
	if [[ ${EPREFIX} != ${PORTAGE_OVERRIDE_EPREFIX} ]] ; then
		if has_version ${root_arg} $CATEGORY/$PN:$SLOT ; then
			einfo "has_version ${root_arg} detects an installed instance of $CATEGORY/$PN:$SLOT"
			einfo "best_version ${root_arg} reports that the installed instance is $(best_version ${root_arg} $CATEGORY/$PN:$SLOT)"
		else
			einfo "has_version ${root_arg} does not detect an installed instance of $CATEGORY/$PN:$SLOT"
		fi
	fi
}

"""

_AVAILABLE_EBUILDS = {
    "dev-libs/A-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "MISC_CONTENT": _INSTALL_SOMETHING,
        "RDEPEND": "flag? ( dev-libs/B[flag] )",
    },
    "dev-libs/B-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "MISC_CONTENT": _INSTALL_SOMETHING,
    },
    "dev-libs/C-1": {
        "EAPI": "7",
        "KEYWORDS": "~x86",
        "RDEPEND": "dev-libs/D[flag]",
        "MISC_CONTENT": _INSTALL_SOMETHING,
    },
    "dev-libs/D-1": {
        "EAPI": "7",
        "KEYWORDS": "~x86",
        "IUSE": "flag",
        "MISC_CONTENT": _INSTALL_SOMETHING,
    },
    "virtual/foo-0": {
        "EAPI": "5",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
    },
}

_INSTALLED_EBUILDS = {
    "dev-libs/A-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "RDEPEND": "flag? ( dev-libs/B[flag] )",
        "USE": "flag",
    },
    "dev-libs/B-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "USE": "flag",
    },
    "dev-libs/depclean-me-1": {
        "EAPI": "5",
        "IUSE": "",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "USE": "",
    },
    "app-misc/depclean-me-1": {
        "EAPI": "5",
        "IUSE": "",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "RDEPEND": "dev-libs/depclean-me",
        "USE": "",
    },
}


@pytest.fixture(params=SUPPORTED_GENTOO_BINPKG_FORMATS)
def playground(request):
    """Fixture that provides instances of ``ResolverPlayground``
    each one with one supported value for ``BINPKG_FORMAT``."""
    binpkg_format = request.param
    yield ResolverPlayground(
        ebuilds=_AVAILABLE_EBUILDS,
        installed=_INSTALLED_EBUILDS,
        debug=False,
        user_config={
            "make.conf": (f'BINPKG_FORMAT="{binpkg_format}"',),
        },
    )
