# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.CompositeTask import CompositeTask
from portage.dep import _repo_separator
from portage.output import colorize


class PackageMerge(CompositeTask):
    __slots__ = ("merge", "postinst_failure")

    def _should_show_status(self):
        return (
            not self.merge.build_opts.fetchonly
            and not self.merge.build_opts.pretend
            and not self.merge.build_opts.buildpkgonly
        )

    def _make_msg(self, pkg, action_desc, preposition, counter_str):
        pkg_color = "PKG_MERGE"
        if pkg.type_name == "binary":
            pkg_color = "PKG_BINARY_MERGE"

        msg = "{} {}{}".format(
            action_desc,
            counter_str,
            colorize(pkg_color, pkg.cpv + _repo_separator + pkg.repo),
        )

        if pkg.root_config.settings["ROOT"] != "/":
            msg += f" {preposition} {pkg.root}"

        return msg

    def _start(self):
        self.scheduler = self.merge.scheduler
        pkg = self.merge.pkg
        pkg_count = self.merge.pkg_count

        if pkg.installed:
            action_desc = "Uninstalling"
            preposition = "from"
            counter_str = ""
        else:
            action_desc = "Installing"
            preposition = "to"
            counter_str = "({} of {}) ".format(
                colorize("MERGE_LIST_PROGRESS", str(pkg_count.curval)),
                colorize("MERGE_LIST_PROGRESS", str(pkg_count.maxval)),
            )

        if self._should_show_status():
            msg = self._make_msg(pkg, action_desc, preposition, counter_str)
            self.merge.statusMessage(msg)

        task = self.merge.create_install_task()
        self._start_task(task, self._install_exit)

    def _install_exit(self, task):
        self.postinst_failure = getattr(task, "postinst_failure", None)

        pkg = self.merge.pkg
        pkg_count = self.merge.pkg_count

        if self.postinst_failure:
            action_desc = "Failed"
            preposition = "in"
            counter_str = ""
        else:
            action_desc = "Completed"
            preposition = "to"
            counter_str = "({} of {}) ".format(
                colorize("MERGE_LIST_PROGRESS", str(pkg_count.curval)),
                colorize("MERGE_LIST_PROGRESS", str(pkg_count.maxval)),
            )

        if self._should_show_status():
            msg = self._make_msg(pkg, action_desc, preposition, counter_str)
            self.merge.statusMessage(msg)

        self._final_exit(task)
        self.wait()
