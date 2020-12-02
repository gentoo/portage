# Copyright 2011-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class MergeOrderTestCase(TestCase):

	def testMergeOrder(self):
		ebuilds = {
			"app-misc/blocker-buildtime-a-1" : {},
			"app-misc/blocker-buildtime-unbuilt-a-1" : {
				"DEPEND" : "!app-misc/installed-blocker-a",
			},
			"app-misc/blocker-buildtime-unbuilt-hard-a-1" : {
				"EAPI"   : "2",
				"DEPEND" : "!!app-misc/installed-blocker-a",
			},
			"app-misc/blocker-update-order-a-1" : {},
			"app-misc/blocker-update-order-hard-a-1" : {},
			"app-misc/blocker-update-order-hard-unsolvable-a-1" : {},
			"app-misc/blocker-runtime-a-1" : {},
			"app-misc/blocker-runtime-b-1" : {},
			"app-misc/blocker-runtime-hard-a-1" : {},
			"app-misc/circ-buildtime-a-0": {},
			"app-misc/circ-buildtime-a-1": {
				"RDEPEND": "app-misc/circ-buildtime-b",
			},
			"app-misc/circ-buildtime-b-1": {
				"RDEPEND": "app-misc/circ-buildtime-c",
			},
			"app-misc/circ-buildtime-c-1": {
				"DEPEND": "app-misc/circ-buildtime-a",
			},
			"app-misc/circ-buildtime-unsolvable-a-1": {
				"RDEPEND": "app-misc/circ-buildtime-unsolvable-b",
			},
			"app-misc/circ-buildtime-unsolvable-b-1": {
				"RDEPEND": "app-misc/circ-buildtime-unsolvable-c",
			},
			"app-misc/circ-buildtime-unsolvable-c-1": {
				"DEPEND": "app-misc/circ-buildtime-unsolvable-a",
			},
			"app-misc/circ-post-runtime-a-1": {
				"PDEPEND": "app-misc/circ-post-runtime-b",
			},
			"app-misc/circ-post-runtime-b-1": {
				"RDEPEND": "app-misc/circ-post-runtime-c",
			},
			"app-misc/circ-post-runtime-c-1": {
				"RDEPEND": "app-misc/circ-post-runtime-a",
			},
			"app-misc/circ-runtime-a-1": {
				"RDEPEND": "app-misc/circ-runtime-b",
			},
			"app-misc/circ-runtime-b-1": {
				"RDEPEND": "app-misc/circ-runtime-c",
			},
			"app-misc/circ-runtime-c-1": {
				"RDEPEND": "app-misc/circ-runtime-a",
			},
			"app-misc/circ-satisfied-a-0": {
				"RDEPEND": "app-misc/circ-satisfied-b",
			},
			"app-misc/circ-satisfied-a-1": {
				"RDEPEND": "app-misc/circ-satisfied-b",
			},
			"app-misc/circ-satisfied-b-0": {
				"RDEPEND": "app-misc/circ-satisfied-c",
			},
			"app-misc/circ-satisfied-b-1": {
				"RDEPEND": "app-misc/circ-satisfied-c",
			},
			"app-misc/circ-satisfied-c-0": {
				"DEPEND": "app-misc/circ-satisfied-a",
				"RDEPEND": "app-misc/circ-satisfied-a",
			},
			"app-misc/circ-satisfied-c-1": {
				"DEPEND": "app-misc/circ-satisfied-a",
				"RDEPEND": "app-misc/circ-satisfied-a",
			},
			"app-misc/circ-direct-a-1": {
				"RDEPEND": "app-misc/circ-direct-b",
			},
			"app-misc/circ-direct-b-1": {
				"RDEPEND": "app-misc/circ-direct-a",
				"DEPEND": "app-misc/circ-direct-a",
			},
			"app-misc/circ-smallest-a-1": {
				"RDEPEND": "app-misc/circ-smallest-b",
			},
			"app-misc/circ-smallest-b-1": {
				"RDEPEND": "app-misc/circ-smallest-a",
			},
			"app-misc/circ-smallest-c-1": {
				"RDEPEND": "app-misc/circ-smallest-d",
			},
			"app-misc/circ-smallest-d-1": {
				"RDEPEND": "app-misc/circ-smallest-e",
			},
			"app-misc/circ-smallest-e-1": {
				"RDEPEND": "app-misc/circ-smallest-c",
			},
			"app-misc/circ-smallest-f-1": {
				"RDEPEND": "app-misc/circ-smallest-g app-misc/circ-smallest-a app-misc/circ-smallest-c",
			},
			"app-misc/circ-smallest-g-1": {
				"RDEPEND": "app-misc/circ-smallest-f",
			},
			"app-misc/installed-blocker-a-1" : {
				"EAPI"   : "2",
				"DEPEND" : "!app-misc/blocker-buildtime-a",
				"RDEPEND" : "!app-misc/blocker-runtime-a !app-misc/blocker-runtime-b !!app-misc/blocker-runtime-hard-a",
			},
			"app-misc/installed-old-version-blocks-a-1" : {
				"RDEPEND" : "!app-misc/blocker-update-order-a",
			},
			"app-misc/installed-old-version-blocks-a-2" : {},
			"app-misc/installed-old-version-blocks-hard-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-a",
			},
			"app-misc/installed-old-version-blocks-hard-a-2" : {},
			"app-misc/installed-old-version-blocks-hard-unsolvable-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-unsolvable-a",
			},
			"app-misc/installed-old-version-blocks-hard-unsolvable-a-2" : {
				"DEPEND"  : "app-misc/blocker-update-order-hard-unsolvable-a",
				"RDEPEND" : "",
			},
			"app-misc/some-app-a-1": {
				"RDEPEND": "app-misc/circ-runtime-a app-misc/circ-runtime-b",
			},
			"app-misc/some-app-b-1": {
				"RDEPEND": "app-misc/circ-post-runtime-a app-misc/circ-post-runtime-b",
			},
			"app-misc/some-app-c-1": {
				"RDEPEND": "app-misc/circ-buildtime-a app-misc/circ-buildtime-b",
			},
			"app-admin/eselect-python-20100321" : {},
			"sys-apps/portage-2.1.9.42" : {
				"DEPEND"  : "dev-lang/python",
				"RDEPEND" : "dev-lang/python",
			},
			"sys-apps/portage-2.1.9.49" : {
				"DEPEND"  : "dev-lang/python >=app-admin/eselect-python-20091230",
				"RDEPEND" : "dev-lang/python",
			},
			"dev-lang/python-3.1" : {},
			"dev-lang/python-3.2" : {},
			"virtual/libc-0" : {
				"RDEPEND" : "sys-libs/glibc",
			},
			"sys-devel/gcc-4.5.2" : {},
			"sys-devel/binutils-2.18" : {},
			"sys-devel/binutils-2.20.1" : {},
			"sys-libs/glibc-2.11" : {
				"DEPEND" : "virtual/os-headers sys-devel/gcc sys-devel/binutils",
				"RDEPEND": "",
			},
			"sys-libs/glibc-2.13" : {
				"DEPEND" : "virtual/os-headers sys-devel/gcc sys-devel/binutils",
				"RDEPEND": "",
			},
			"virtual/os-headers-0" : {
				"RDEPEND" : "sys-kernel/linux-headers",
			},
			"sys-kernel/linux-headers-2.6.38": {
				"DEPEND" : "app-arch/xz-utils",
				"RDEPEND": "",
			},
			"sys-kernel/linux-headers-2.6.39": {
				"DEPEND" : "app-arch/xz-utils",
				"RDEPEND": "",
			},
			"app-arch/xz-utils-5.0.1" : {},
			"app-arch/xz-utils-5.0.2" : {},
			"dev-util/pkgconfig-0.25-r2" : {},
			"kde-base/kdelibs-3.5.7" : {
				"PDEPEND" : "kde-misc/kdnssd-avahi",
			},
			"kde-misc/kdnssd-avahi-0.1.2" : {
				"DEPEND"  : "kde-base/kdelibs app-arch/xz-utils dev-util/pkgconfig",
				"RDEPEND" : "kde-base/kdelibs",
			},
			"kde-base/kdnssd-3.5.7" : {
				"DEPEND"  : "kde-base/kdelibs",
				"RDEPEND" : "kde-base/kdelibs",
			},
			"kde-base/libkdegames-3.5.7" : {
				"DEPEND"  : "kde-base/kdelibs",
				"RDEPEND" : "kde-base/kdelibs",
			},
			"kde-base/kmines-3.5.7" : {
				"DEPEND"  : "kde-base/libkdegames",
				"RDEPEND" : "kde-base/libkdegames",
			},
			"media-libs/mesa-9.1.3" : {
				"EAPI" : "5",
				"IUSE" : "+xorg",
				"DEPEND" : "xorg? ( x11-base/xorg-server:= )",
				"RDEPEND" : "xorg? ( x11-base/xorg-server:= )",
			},
			"media-video/libav-0.7_pre20110327" : {
				"EAPI" : "2",
				"IUSE" : "X +encode",
				"RDEPEND" : "!media-video/ffmpeg",
			},
			"media-video/ffmpeg-0.7_rc1" : {
				"EAPI" : "2",
				"IUSE" : "X +encode",
			},
			"virtual/ffmpeg-0.6.90" : {
				"EAPI" : "2",
				"IUSE" : "X +encode",
				"RDEPEND" : "|| ( >=media-video/ffmpeg-0.6.90_rc0-r2[X=,encode=] >=media-video/libav-0.6.90_rc[X=,encode=] )",
			},
			"x11-base/xorg-drivers-1.20-r2": {
				"EAPI": "7",
				"IUSE": "+video_cards_fbdev",
				"PDEPEND": "x11-base/xorg-server video_cards_fbdev? ( x11-drivers/xf86-video-fbdev )",
			},
			"x11-base/xorg-server-1.14.1" : {
				"EAPI" : "5",
				"SLOT": "0/1.14.1",
				"DEPEND" : "media-libs/mesa",
				"RDEPEND" : "media-libs/mesa",
				"PDEPEND": "x11-base/xorg-drivers",
			},
			"x11-drivers/xf86-video-fbdev-0.5.0-r1": {
				"EAPI": "7",
				"DEPEND": "x11-base/xorg-server",
				"RDEPEND": "x11-base/xorg-server:=",
			}
		}

		installed = {
			"app-misc/circ-direct-a-1": {
				"RDEPEND": "app-misc/circ-direct-b",
			},
			"app-misc/circ-direct-b-1": {
				"RDEPEND": "app-misc/circ-direct-a",
				"DEPEND": "app-misc/circ-direct-a",
			},
			"app-misc/circ-buildtime-a-0": {},
			"app-misc/circ-satisfied-a-0": {
				"RDEPEND": "app-misc/circ-satisfied-b",
			},
			"app-misc/circ-satisfied-b-0": {
				"RDEPEND": "app-misc/circ-satisfied-c",
			},
			"app-misc/circ-satisfied-c-0": {
				"DEPEND": "app-misc/circ-satisfied-a",
				"RDEPEND": "app-misc/circ-satisfied-a",
			},
			"app-misc/installed-blocker-a-1" : {
				"EAPI"   : "2",
				"DEPEND" : "!app-misc/blocker-buildtime-a",
				"RDEPEND" : "!app-misc/blocker-runtime-a !app-misc/blocker-runtime-b !!app-misc/blocker-runtime-hard-a",
			},
			"app-misc/installed-old-version-blocks-a-1" : {
				"RDEPEND" : "!app-misc/blocker-update-order-a",
			},
			"app-misc/installed-old-version-blocks-hard-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-a",
			},
			"app-misc/installed-old-version-blocks-hard-unsolvable-a-1" : {
				"EAPI"    : "2",
				"RDEPEND" : "!!app-misc/blocker-update-order-hard-unsolvable-a",
			},
			"sys-apps/portage-2.1.9.42" : {
				"DEPEND"  : "dev-lang/python",
				"RDEPEND" : "dev-lang/python",
			},
			"dev-lang/python-3.1" : {},
			"virtual/libc-0" : {
				"RDEPEND" : "sys-libs/glibc",
			},
			"sys-devel/binutils-2.18" : {},
			"sys-libs/glibc-2.11" : {
				"DEPEND" : "virtual/os-headers sys-devel/gcc sys-devel/binutils",
				"RDEPEND": "",
			},
			"virtual/os-headers-0" : {
				"RDEPEND" : "sys-kernel/linux-headers",
			},
			"sys-kernel/linux-headers-2.6.38": {
				"DEPEND" : "app-arch/xz-utils",
				"RDEPEND": "",
			},
			"app-arch/xz-utils-5.0.1" : {},
			"media-libs/mesa-9.1.3" : {
				"EAPI" : "5",
				"IUSE" : "+xorg",
				"USE": "xorg",
				"DEPEND" : "x11-base/xorg-server:0/1.14.1=",
				"RDEPEND" : "x11-base/xorg-server:0/1.14.1=",
			},
			"media-video/ffmpeg-0.7_rc1" : {
				"EAPI" : "2",
				"IUSE" : "X +encode",
				"USE" : "encode",
			},
			"virtual/ffmpeg-0.6.90" : {
				"EAPI" : "2",
				"IUSE" : "X +encode",
				"USE" : "encode",
				"RDEPEND" : "|| ( >=media-video/ffmpeg-0.6.90_rc0-r2[X=,encode=] >=media-video/libav-0.6.90_rc[X=,encode=] )",
			},
			"x11-base/xorg-drivers-1.20-r2": {
				"EAPI": "7",
				"IUSE": "+video_cards_fbdev",
				"USE": "video_cards_fbdev",
				"PDEPEND": "x11-base/xorg-server x11-drivers/xf86-video-fbdev",
			},
			"x11-base/xorg-server-1.14.1" : {
				"EAPI" : "5",
				"SLOT": "0/1.14.1",
				"DEPEND" : "media-libs/mesa",
				"RDEPEND" : "media-libs/mesa",
				"PDEPEND": "x11-base/xorg-drivers",
			},
			"x11-drivers/xf86-video-fbdev-0.5.0-r1": {
				"EAPI": "7",
				"DEPEND": "x11-base/xorg-server",
				"RDEPEND": "x11-base/xorg-server:0/1.14.1=",
			}
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/circ-direct-a", "app-misc/circ-direct-b"],
				success = True,
				all_permutations = True,
				mergelist = ["app-misc/circ-direct-a-1", "app-misc/circ-direct-b-1"],
			),
			ResolverPlaygroundTestCase(
				["app-misc/some-app-a"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/circ-runtime-a-1", "app-misc/circ-runtime-b-1", "app-misc/circ-runtime-c-1"), "app-misc/some-app-a-1"]),
			ResolverPlaygroundTestCase(
				["app-misc/some-app-a"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/circ-runtime-c-1", "app-misc/circ-runtime-b-1", "app-misc/circ-runtime-a-1"), "app-misc/some-app-a-1"]),
			# Test unsolvable circular dep that is RDEPEND in one
			# direction and DEPEND in the other.
			ResolverPlaygroundTestCase(
				["app-misc/circ-buildtime-unsolvable-a"],
				success = False,
				circular_dependency_solutions = {}),
			# Test optimal merge order for a circular dep that is
			# RDEPEND in one direction and DEPEND in the other.
			# This requires an installed instance of the DEPEND
			# package in order to be solvable.
			ResolverPlaygroundTestCase(
				["app-misc/some-app-c", "app-misc/circ-buildtime-a"],
				success = True,
				ambiguous_merge_order = True,
				# The following merge order assertion reflects optimal order for
				# a circular relationship which is DEPEND in one direction and
				# RDEPEND in the other.
				merge_order_assertions = (("app-misc/circ-buildtime-a-1", "app-misc/circ-buildtime-c-1"),),
				mergelist = [("app-misc/circ-buildtime-b-1", "app-misc/circ-buildtime-c-1", "app-misc/circ-buildtime-a-1"), "app-misc/some-app-c-1"]),
			# Test optimal merge order for a circular dep that is
			# RDEPEND in one direction and PDEPEND in the other.
			ResolverPlaygroundTestCase(
				["app-misc/some-app-b"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = ["app-misc/circ-post-runtime-a-1", ("app-misc/circ-post-runtime-b-1", "app-misc/circ-post-runtime-c-1"), "app-misc/some-app-b-1"]),
			# Test optimal merge order for a circular dep that is
			# RDEPEND in one direction and DEPEND in the other,
			# with all dependencies initially satisfied. Optimally,
			# the DEPEND/buildtime dep should be updated before the
			# package that depends on it, even though it's feasible
			# to update it later since it is already satisfied.
			ResolverPlaygroundTestCase(
				["app-misc/circ-satisfied-a", "app-misc/circ-satisfied-b", "app-misc/circ-satisfied-c"],
				success = True,
				all_permutations = True,
				ambiguous_merge_order = True,
				merge_order_assertions = (("app-misc/circ-satisfied-a-1", "app-misc/circ-satisfied-c-1"),),
				mergelist = [("app-misc/circ-satisfied-a-1", "app-misc/circ-satisfied-b-1", "app-misc/circ-satisfied-c-1")]),
			# In the case of multiple runtime cycles, where some cycles
			# may depend on smaller independent cycles, it's optimal
			# to merge smaller independent cycles before other cycles
			# that depend on them.
			ResolverPlaygroundTestCase(
				["app-misc/circ-smallest-a", "app-misc/circ-smallest-c", "app-misc/circ-smallest-f"],
				success = True,
				ambiguous_merge_order = True,
				all_permutations = True,
				mergelist = [('app-misc/circ-smallest-a-1', 'app-misc/circ-smallest-b-1'),
				('app-misc/circ-smallest-c-1', 'app-misc/circ-smallest-d-1', 'app-misc/circ-smallest-e-1'),
				('app-misc/circ-smallest-f-1', 'app-misc/circ-smallest-g-1')]),
			# installed package has buildtime-only blocker
			# that should be ignored
			ResolverPlaygroundTestCase(
				["app-misc/blocker-buildtime-a"],
				success = True,
				mergelist = ["app-misc/blocker-buildtime-a-1"]),
			# We're installing a package that an old version of
			# an installed package blocks. However, an update is
			# available to the old package. The old package should
			# be updated first, in order to solve the blocker without
			# any need for blocking packages to temporarily overlap.
			ResolverPlaygroundTestCase(
				["app-misc/blocker-update-order-a", "app-misc/installed-old-version-blocks-a"],
				success = True,
				all_permutations = True,
				mergelist = ["app-misc/installed-old-version-blocks-a-2", "app-misc/blocker-update-order-a-1"]),
			# This is the same as above but with a hard blocker. The hard
			# blocker is solved automatically since the update makes it
			# irrelevant.
			ResolverPlaygroundTestCase(
				["app-misc/blocker-update-order-hard-a", "app-misc/installed-old-version-blocks-hard-a"],
				success = True,
				all_permutations = True,
				mergelist = ["app-misc/installed-old-version-blocks-hard-a-2", "app-misc/blocker-update-order-hard-a-1"]),
			# This is similar to the above case except that it's unsolvable
			# due to merge order, unless bug 250286 is implemented so that
			# the installed blocker will be unmerged before installation
			# of the package it blocks (rather than after like a soft blocker
			# would be handled). The "unmerge before" behavior requested
			# in bug 250286 must be optional since essential programs or
			# libraries may be temporarily unavailable during a
			# non-overlapping update like this.
			ResolverPlaygroundTestCase(
				["app-misc/blocker-update-order-hard-unsolvable-a", "app-misc/installed-old-version-blocks-hard-unsolvable-a"],
				success = False,
				all_permutations = True,
				ambiguous_merge_order = True,
				merge_order_assertions = (('app-misc/blocker-update-order-hard-unsolvable-a-1', 'app-misc/installed-old-version-blocks-hard-unsolvable-a-2'),),
				mergelist = [('app-misc/blocker-update-order-hard-unsolvable-a-1', 'app-misc/installed-old-version-blocks-hard-unsolvable-a-2', '!!app-misc/blocker-update-order-hard-unsolvable-a')]),
			# The installed package has runtime blockers that
			# should cause it to be uninstalled. The uninstall
			# task is executed only after blocking packages have
			# been merged.
			# TODO: distinguish between install/uninstall tasks in mergelist
			ResolverPlaygroundTestCase(
				["app-misc/blocker-runtime-a", "app-misc/blocker-runtime-b"],
				success = True,
				all_permutations = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/blocker-runtime-a-1", "app-misc/blocker-runtime-b-1"), "[uninstall]app-misc/installed-blocker-a-1", ("!app-misc/blocker-runtime-a", "!app-misc/blocker-runtime-b")]),
			# We have a soft buildtime blocker against an installed
			# package that should cause it to be uninstalled. Note that with
			# soft blockers, the blocking packages are allowed to temporarily
			# overlap. This allows any essential programs/libraries provided
			# by both packages to be available at all times.
			# TODO: distinguish between install/uninstall tasks in mergelist
			ResolverPlaygroundTestCase(
				["app-misc/blocker-buildtime-unbuilt-a"],
				success = True,
				mergelist = ["app-misc/blocker-buildtime-unbuilt-a-1", "[uninstall]app-misc/installed-blocker-a-1", "!app-misc/installed-blocker-a"]),
			# We have a hard buildtime blocker against an installed
			# package that will not resolve automatically (unless
			# the option requested in bug 250286 is implemented).
			ResolverPlaygroundTestCase(
				["app-misc/blocker-buildtime-unbuilt-hard-a"],
				success = False,
				mergelist = ['app-misc/blocker-buildtime-unbuilt-hard-a-1', '!!app-misc/installed-blocker-a']),
			# An installed package has a hard runtime blocker that
			# will not resolve automatically (unless the option
			# requested in bug 250286 is implemented).
			ResolverPlaygroundTestCase(
				["app-misc/blocker-runtime-hard-a"],
				success = False,
				mergelist = ['app-misc/blocker-runtime-hard-a-1', '!!app-misc/blocker-runtime-hard-a']),
			# Test swapping of providers for a new-style virtual package,
			# which relies on delayed evaluation of disjunctive (virtual
			# and ||) deps as required to solve bug #264434. Note that
			# this behavior is not supported for old-style PROVIDE virtuals,
			# as reported in bug #339164.
			ResolverPlaygroundTestCase(
				["media-video/libav"],
				success=True,
				mergelist = ['media-video/libav-0.7_pre20110327', '[uninstall]media-video/ffmpeg-0.7_rc1', '!media-video/ffmpeg']),
			# Test that OS_HEADERS_PACKAGE_ATOM and LIBC_PACKAGE_ATOM
			# are merged asap, in order to account for implicit
			# dependencies. See bug #303567. Optimally, satisfied deps
			# are always merged after the asap nodes that depend on them.
			ResolverPlaygroundTestCase(
				["app-arch/xz-utils", "sys-kernel/linux-headers", "sys-devel/binutils", "sys-libs/glibc"],
				options = {"--complete-graph" : True},
				success = True,
				all_permutations = True,
				ambiguous_merge_order = True,
				mergelist = ['sys-kernel/linux-headers-2.6.39', 'sys-devel/gcc-4.5.2', 'sys-libs/glibc-2.13', ('app-arch/xz-utils-5.0.2', 'sys-devel/binutils-2.20.1')]),
			# Test asap install of PDEPEND for bug #180045.
			ResolverPlaygroundTestCase(
				["kde-base/kmines", "kde-base/kdnssd", "kde-base/kdelibs", "app-arch/xz-utils"],
				success = True,
				all_permutations = True,
				ambiguous_merge_order = True,
				merge_order_assertions = (
					('dev-util/pkgconfig-0.25-r2', 'kde-misc/kdnssd-avahi-0.1.2'),
					('kde-misc/kdnssd-avahi-0.1.2', 'kde-base/libkdegames-3.5.7'),
					('kde-misc/kdnssd-avahi-0.1.2', 'kde-base/kdnssd-3.5.7'),
					('kde-base/libkdegames-3.5.7', 'kde-base/kmines-3.5.7'),
				),
				mergelist = [('kde-base/kdelibs-3.5.7', 'dev-util/pkgconfig-0.25-r2', 'kde-misc/kdnssd-avahi-0.1.2', 'app-arch/xz-utils-5.0.2', 'kde-base/libkdegames-3.5.7', 'kde-base/kdnssd-3.5.7', 'kde-base/kmines-3.5.7')]),
			# Test satisfied circular DEPEND/RDEPEND with one := operator.
			# Both deps are already satisfied by installed packages, but
			# the := dep is given higher priority in merge order.
			ResolverPlaygroundTestCase(
				["media-libs/mesa", "x11-drivers/xf86-video-fbdev", "x11-base/xorg-server"],
				success=True,
				all_permutations = True,
				mergelist = ['x11-base/xorg-server-1.14.1', 'media-libs/mesa-9.1.3', 'x11-drivers/xf86-video-fbdev-0.5.0-r1']),
			# Test prioritization of the find_smallest_cycle function, which should
			# minimize the use of installed packages to break cycles. If installed
			# packages must be used to break cycles, then it should prefer to do this
			# for runtime dependencies over buildtime dependencies. If a package needs
			# to be uninstalled in order to solve a blocker, then it should prefer to
			# do this before it uses an installed package to break a cycle.
			ResolverPlaygroundTestCase(
				["app-misc/some-app-a", "app-misc/some-app-b", "app-misc/some-app-c", "app-misc/circ-buildtime-a", "app-misc/blocker-buildtime-unbuilt-a", "media-libs/mesa", "x11-base/xorg-server", "app-misc/circ-direct-a", "app-misc/circ-direct-b", "app-misc/circ-satisfied-a", "app-misc/circ-satisfied-b", "app-misc/circ-satisfied-c"],
				success = True,
				mergelist = ['app-misc/circ-post-runtime-a-1', 'app-misc/circ-post-runtime-c-1', 'app-misc/circ-post-runtime-b-1', 'app-misc/some-app-b-1', 'app-misc/circ-runtime-a-1', 'app-misc/circ-runtime-b-1', 'app-misc/circ-runtime-c-1', 'app-misc/some-app-a-1', 'app-misc/blocker-buildtime-unbuilt-a-1', '[uninstall]app-misc/installed-blocker-a-1', '!app-misc/installed-blocker-a', 'app-misc/circ-direct-a-1', 'app-misc/circ-direct-b-1', 'x11-base/xorg-server-1.14.1', 'media-libs/mesa-9.1.3', 'app-misc/circ-buildtime-a-1', 'app-misc/circ-buildtime-b-1', 'app-misc/circ-buildtime-c-1', 'app-misc/some-app-c-1', 'app-misc/circ-satisfied-a-1', 'app-misc/circ-satisfied-b-1', 'app-misc/circ-satisfied-c-1']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
