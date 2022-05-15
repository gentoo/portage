# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.CompositeTask import CompositeTask
from portage.dep import _repo_separator
from portage.output import colorize


class PackageMerge(CompositeTask):
    __slots__ = ("merge", "postinst_failure")

    def _start(self):

        self.scheduler = self.merge.scheduler
        pkg = self.merge.pkg
        pkg_count = self.merge.pkg_count
        pkg_color = "PKG_MERGE"
        if pkg.type_name == "binary":
            pkg_color = "PKG_BINARY_MERGE"

        if pkg.installed:
            action_desc = "Uninstalling"
            preposition = "from"
            counter_str = ""
        else:
            action_desc = "Installing"
            preposition = "to"
            colorized_curval = colorize("MERGE_LIST_PROGRESS", str(pkg_count.curval))
            colorized_maxval = colorize("MERGE_LIST_PROGRESS", str(pkg_count.maxval))
            counter_str = f"({colorized_curval} of {colorized_maxval}) "

        msg = f"{action_desc} {counter_str}{colorize(pkg_color, f'{pkg.cpv}{_repo_separator}{pkg.repo}')}"

        if pkg.root_config.settings["ROOT"] != "/":
            msg += f" {preposition} {pkg.root}"

        if (
            not self.merge.build_opts.fetchonly
            and not self.merge.build_opts.pretend
            and not self.merge.build_opts.buildpkgonly
        ):
            self.merge.statusMessage(msg)

        task = self.merge.create_install_task()
        self._start_task(task, self._install_exit)

    def _install_exit(self, task):
        self.postinst_failure = getattr(task, "postinst_failure", None)
        self._final_exit(task)
        self.wait()
