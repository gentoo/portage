# The image that CI runs the tests in. It has a current bash and every Python
# in the test matrix, each with the test dependencies in /opt/python/<version>.

FROM gentoo/portage:latest AS repo

FROM gentoo/stage3:latest

RUN --mount=type=bind,from=repo,source=/var/db/repos/gentoo,target=/var/db/repos/gentoo <<EOF
set -eux

slots="3.9 3.10 3.11 3.12 3.13 3.14 3.15"

# Pre-releases of the newest slot carry no keywords. Exclude the live ebuild.
mkdir -p /etc/portage/package.accept_keywords
echo "<dev-lang/python-3.15.9999:3.15 **" > /etc/portage/package.accept_keywords/python

# Name pypy3-exe-bin, so that dev-lang/pypy does not pull in pypy3-exe, which
# takes hours to build.
MAKEOPTS="-j$(nproc)" emerge --getbinpkg --noreplace --quiet-build \
	app-misc/pax-utils dev-build/meson dev-libs/libxml2 dev-libs/libxslt \
	dev-vcs/git '=dev-lang/pypy3-exe-bin-3.11*' dev-lang/pypy:3.11 \
	$(printf 'dev-lang/python:%s ' ${slots})

# Use uv to populate the virtual environments, since the pip that ensurepip
# installs no longer supports Python 3.9.
python -m venv /opt/uv
/opt/uv/bin/pip install --no-cache-dir uv

venv() {
	/opt/uv/bin/uv venv --python "$1" "/opt/python/$2"
	# setuptools is needed for 3.12+ because of
	# https://github.com/mesonbuild/meson/issues/7702.
	/opt/uv/bin/uv pip install --no-cache --python "/opt/python/$2" \
		pytest pytest-rerunfailures pytest-xdist setuptools
}
for slot in ${slots}; do
	venv "python${slot}" "${slot}"
done
venv pypy3.11 pypy-3.11

# The uid that owns the workspace on GitHub's runners.
useradd --uid 1001 runner

rm -rf /var/cache/binpkgs/* /var/cache/distfiles/*
EOF

USER runner
