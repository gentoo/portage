# Copyright 2013-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import logging

from portage import os
from portage.package.ebuild.fetch import ContentHashLayout
from portage.util._async.FileCopier import FileCopier
from _emerge.CompositeTask import CompositeTask

logger = logging.getLogger(__name__)


class DeletionTask(CompositeTask):
    __slots__ = ("distfile", "distfile_path", "config")

    def _start(self):
        if self.config.options.recycle_dir is not None:
            recycle_path = os.path.join(self.config.options.recycle_dir, self.distfile)
            if self.config.options.dry_run:
                logger.info(
                    f"dry-run: move '{self.distfile}' from distfiles to recycle"
                )
            else:
                logger.debug(f"move '{self.distfile}' from distfiles to recycle")
                try:
                    # note: distfile_path can be a symlink here
                    os.rename(os.path.realpath(self.distfile_path), recycle_path)
                except OSError as e:
                    if e.errno != errno.EXDEV:
                        logger.error(
                            ("rename %s from distfiles to " "recycle failed: %s")
                            % (self.distfile, e)
                        )
                else:
                    self._delete_links()
                    self._async_wait()
                    return

                self._start_task(
                    FileCopier(
                        src_path=self.distfile_path,
                        dest_path=recycle_path,
                        background=False,
                    ),
                    self._recycle_copier_exit,
                )
                return

        success = True

        if self.config.options.dry_run:
            logger.info(f"dry-run: delete '{self.distfile}' from distfiles")
        else:
            logger.debug(f"delete '{self.distfile}' from distfiles")
            try:
                os.unlink(self.distfile_path)
            except OSError as e:
                if e.errno not in (errno.ENOENT, errno.ESTALE):
                    logger.error(f"{self.distfile} unlink failed in distfiles: {e}")
                    success = False

        if success:
            self._delete_links()
        else:
            self.returncode = 1

        self._async_wait()

    def _recycle_copier_exit(self, copier):
        self._assert_current(copier)
        if self._was_cancelled():
            self.wait()
            return

        success = True
        if copier.returncode == os.EX_OK:
            try:
                os.unlink(copier.src_path)
            except OSError as e:
                if e.errno not in (errno.ENOENT, errno.ESTALE):
                    logger.error(f"{self.distfile} unlink failed in distfiles: {e}")
                    success = False

        else:
            logger.error(
                ("%s copy from distfiles " "to recycle failed: %s")
                % (self.distfile, copier.future.exception())
            )
            success = False

        if success:
            self._delete_links()
        else:
            self.returncode = 1

        self._current_task = None
        self.wait()

    def _delete_links(self):
        success = True
        for layout in self.config.layouts:
            if isinstance(layout, ContentHashLayout) and not self.distfile.digests:
                logger.debug(f"_delete_links: '{self.distfile}' has no digests")
                continue
            distfile_path = os.path.join(
                self.config.options.distfiles, layout.get_path(self.distfile)
            )
            try:
                os.unlink(distfile_path)
            except OSError as e:
                if e.errno not in (errno.ENOENT, errno.ESTALE):
                    logger.error(f"{self.distfile} unlink failed in distfiles: {e}")
                    success = False

        if success:
            self._success()
            self.returncode = os.EX_OK
        else:
            self.returncode = 1

    def _success(self):
        cpv = "unknown"
        if self.config.distfiles_db is not None:
            cpv = self.config.distfiles_db.get(self.distfile, cpv)

        self.config.delete_count += 1
        self.config.log_success(f"{cpv}\t{self.distfile}\tremoved")

        if self.config.distfiles_db is not None:
            try:
                del self.config.distfiles_db[self.distfile]
            except KeyError:
                pass
            else:
                logger.debug(f"drop '{self.distfile}' from distfiles db")

        if self.config.content_db is not None:
            self.config.content_db.remove(self.distfile)

        if self.config.deletion_db is not None:
            try:
                del self.config.deletion_db[self.distfile]
            except KeyError:
                pass
            else:
                logger.debug(f"drop '{self.distfile}' from deletion db")
