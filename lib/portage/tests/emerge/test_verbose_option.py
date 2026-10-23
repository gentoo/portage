# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import shlex

from _emerge.main import parse_opts, verbose_level
from portage.tests import TestCase


class VerboseOptionTestCase(TestCase):
    def _level(self, cmdline):
        return parse_opts(shlex.split(cmdline), silent=True)[1].get("--verbose")

    def test_repeated_v_raises_the_level(self):
        for cmdline, level in (
            ("dev-libs/A", None),
            ("-v dev-libs/A", 1),
            ("--verbose dev-libs/A", 1),
            ("--verbose y dev-libs/A", 1),
            ("-vv dev-libs/A", 2),
            ("-v -v dev-libs/A", 2),
            ("-v --verbose dev-libs/A", 2),
            ("-avv dev-libs/A", 2),
            ("-pvv dev-libs/A", 2),
            ("-vpv dev-libs/A", 2),
            ("-vvv dev-libs/A", 3),
        ):
            with self.subTest(cmdline=cmdline):
                self.assertEqual(self._level(cmdline), level)

    def test_n_resets_the_level(self):
        for cmdline, level in (
            ("-vv --verbose n dev-libs/A", None),
            ("-vv --verbose=n dev-libs/A", None),
            ("-vv --verbose n -v dev-libs/A", 1),
        ):
            with self.subTest(cmdline=cmdline):
                self.assertEqual(self._level(cmdline), level)

    def test_other_short_options_survive_repeated_v(self):
        opts = parse_opts(["-pvv", "dev-libs/A"], silent=True)[1]
        self.assertIn("--pretend", opts)

    def test_default_opts_and_cmdline_take_the_higher_level(self):
        for default_opts, cmdline, level in (
            ("-v", "-v", 1),
            ("-v", "-vv", 2),
            ("-vv", "-v", 2),
            ("-v", "", 1),
            ("", "-vv", 2),
            ("-vv", "--verbose=n -v", 1),
            ("-vv", "--verbose=n", None),
        ):
            with self.subTest(default_opts=default_opts, cmdline=cmdline):
                combined = self._level(f"{default_opts} {cmdline}")
                if combined is not None:
                    combined = verbose_level(combined, self._level(cmdline) or 0)
                self.assertEqual(combined, level)
