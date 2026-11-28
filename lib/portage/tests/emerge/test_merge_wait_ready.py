# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from collections import deque
from types import SimpleNamespace

from _emerge.Scheduler import Scheduler
from portage.tests import TestCase


def scheduler(queue, jobs=0, source_jobs=0, merges=(), flush=False):
    sched = Scheduler.__new__(Scheduler)
    sched._merge_wait_queue = deque(
        SimpleNamespace(is_system_pkg=system) for system in queue
    )
    sched._jobs = jobs
    sched._source_jobs = source_jobs
    sched._task_queues = SimpleNamespace(merge=list(merges))
    sched._flush_merge_wait_queue = flush
    return sched


class MergeWaitReadyTestCase(TestCase):
    def testEmptyQueue(self):
        self.assertFalse(scheduler([])._merge_wait_ready())

    def testBinaryJobsDoNotHoldMerges(self):
        # Only binary packages are being extracted, so nothing is
        # building and the merge can go ahead.
        self.assertTrue(scheduler([False], jobs=3)._merge_wait_ready())
        self.assertTrue(
            scheduler([False], jobs=3, merges=[object()])._merge_wait_ready()
        )

    def testSourceBuildHoldsMerges(self):
        self.assertFalse(scheduler([False], jobs=3, source_jobs=1)._merge_wait_ready())

    def testSystemPackageWaitsForEverything(self):
        self.assertFalse(scheduler([True], jobs=1)._merge_wait_ready())
        self.assertFalse(scheduler([True], merges=[object()])._merge_wait_ready())
        self.assertTrue(scheduler([True])._merge_wait_ready())

    def testFlush(self):
        self.assertTrue(
            scheduler([False], jobs=2, source_jobs=2, flush=True)._merge_wait_ready()
        )
