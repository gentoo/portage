# Copyright 2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import subprocess
import os
import platform
from time import sleep

from portage.const import JOBSERVER_BINARY
from portage.exception import PortageException
from portage.process import find_binary


class JobServer:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.address = self.settings.get("PORTAGE_JOBSERVER_ADDRESS", None)
        self.port = self.settings.get("PORTAGE_JOBSERVER_PORT", None)
        self.max_jobs = self.settings.get("PORTAGE_JOBSERVER_MAX_JOBS", None)
        self.min_free_mem = self.settings.get("PORTAGE_JOBSERVER_MIN_FREE_MEMORY", None)
        self.system_load = self.settings.get("PORTAGE_JOBSERVER_MAX_SYSTEM_LOAD", None)
        self.delay = self.settings.get("PORTAGE_JOBSERVER_DELAY", None)
        self.network_sandbox = "network-sandbox" in self.settings.features
        if self.settings.get("PORTAGE_JOBSERVER_REMOTE", "false") == "true":
            self.remote = True
        else:
            self.remote = False

        if self.network_sandbox:
            if os.getuid() == 0 and platform.system() == "Linux":
                self.unshare_net = True
            else:
                self.unshare_net = False
        else:
            self.unshare_net = False

    def start(self) -> None:
        js_bin = find_binary(JOBSERVER_BINARY)
        if not js_bin:
            raise PortageException(f"Could not find job server binary {str(js_bin)}")
        cmd = [js_bin]
        if self.address:
            cmd.extend(["-a", self.address])
        if self.port:
            cmd.extend(["-p", self.port])
        if self.max_jobs:
            cmd.extend(["-j", self.max_jobs])
        if self.min_free_mem:
            cmd.extend(["-m", self.min_free_mem])
        if self.system_load:
            cmd.extend(["-l", self.system_load])
        if self.delay:
            cmd.extend(["-d", self.delay])
        if self.remote:
            cmd.extend(["-r"])
        if self.unshare_net:
            cmd.extend(["-S"])

        cmd.extend(["-P", str(os.getpid())])

        jobserver_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        sleep(1)
        r = jobserver_proc.poll()
        if (r is not None) and (r != 0):
            raise PortageException("Jobserver failed to start")
