# SOCKSv5 proxy manager for network-sandbox
# Copyright 2015-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import asyncio
import errno
import os
import socket
from typing import Union

import portage

portage.proxy.lazyimport.lazyimport(
    globals(),
    "portage.util._eventloop.global_event_loop:global_event_loop",
)

import portage.data
from portage import _python_interpreter
from portage.data import portage_gid, portage_uid, userpriv_groups
from portage.process import atexit_register, spawn


class ProxyManager:
    """
    A class to start and control a single running SOCKSv5 server process
    for Portage.
    """

    def __init__(self):
        self.socket_path = None
        self._proc = None
        self._proc_waiter = None

    def start(self, settings):
        """
        Start the SOCKSv5 server.

        @param settings: Portage settings instance (used to determine
        paths)
        @type settings: portage.config
        """

        tmpdir = os.path.join(settings["PORTAGE_TMPDIR"], "portage")
        ensure_dirs_kwargs = {}
        if portage.secpass >= 1:
            ensure_dirs_kwargs["gid"] = portage_gid
            ensure_dirs_kwargs["mode"] = 0o70
            ensure_dirs_kwargs["mask"] = 0
        portage.util.ensure_dirs(tmpdir, **ensure_dirs_kwargs)

        self.socket_path = os.path.join(
            tmpdir, ".portage.%d.net.sock" % portage.getpid()
        )
        server_bin = os.path.join(settings["PORTAGE_BIN_PATH"], "socks5-server.py")
        spawn_kwargs = {}
        # The portage_uid check solves EPERM failures in Travis CI.
        if portage.data.secpass > 1 and os.geteuid() != portage_uid:
            spawn_kwargs.update(
                uid=portage_uid, gid=portage_gid, groups=userpriv_groups, umask=0o077
            )
        self._proc = spawn(
            [_python_interpreter, server_bin, self.socket_path],
            returnproc=True,
            **spawn_kwargs,
        )

    def stop(self) -> Union[None, asyncio.Future]:
        """
        Stop the SOCKSv5 server.

        If there is a running asyncio event loop then asyncio.Future is
        returned which should be used to wait for the server process
        to exit.
        """
        future = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._proc is not None:
            self._proc.terminate()
            if loop is None:
                # In this case spawn internals would have used
                # portage's global loop when attaching a waiter to
                # self._proc, so we are obligated to use that.
                global_event_loop().run_until_complete(self._proc.wait())
            else:
                if self._proc_waiter is None:
                    self._proc_waiter = asyncio.ensure_future(
                        self._proc.wait(), loop=loop
                    )
                future = asyncio.shield(self._proc_waiter)

        if loop is not None and future is None:
            future = loop.create_future()
            future.set_result(None)

        self.socket_path = None
        self._proc = None
        self._proc_waiter = None
        return future

    def is_running(self):
        """
        Check whether the SOCKSv5 server is running.

        @return: True if the server is running, False otherwise
        """
        return self.socket_path is not None

    async def ready(self):
        """
        Wait for the proxy socket to become ready. This method is a coroutine.
        """
        if self._proc_waiter is None:
            self._proc_waiter = asyncio.ensure_future(self._proc.wait())

        while True:
            if self._proc_waiter.done():
                raise OSError(3, "No such process")

            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self.socket_path)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
                await asyncio.sleep(0.2)
            else:
                break
            finally:
                s.close()


proxy = ProxyManager()


def get_socks5_proxy(settings):
    """
    Get UNIX socket path for a SOCKSv5 proxy. A new proxy is started if
    one isn't running yet, and an atexit event is added to stop the proxy
    on exit.

    @param settings: Portage settings instance (used to determine paths)
    @type settings: portage.config
    @return: (string) UNIX socket path
    """

    if not proxy.is_running():
        proxy.start(settings)
        atexit_register(proxy.stop)

    return proxy.socket_path
