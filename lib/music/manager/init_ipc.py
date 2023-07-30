"""
Helper for running the Music Manager GUI on Windows as a right-click menu action when multiple paths were selected,
since Windows invokes the target command once for each path instead of once with all paths.  Allows the first instance
to acquire a FileLock to be the primary instance, which will listen on a socket for a moment to collect paths from
any other instances that may have been started.
"""

from __future__ import annotations

import logging
from os import getpid
from selectors import DefaultSelector, EVENT_READ
from socket import socket
from time import monotonic
from typing import TYPE_CHECKING, Collection

from filelock import FileLock
from psutil import Process, NoSuchProcess

from ds_tools.fs.paths import get_user_cache_dir

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ['PathIPC', 'get_clean_paths']
log = logging.getLogger(__name__)


def get_clean_paths(max_wait: float, arg_paths: Collection[str]) -> list[str] | None:
    with PathIPC(max_wait) as path_ipc:
        return path_ipc.run(arg_paths)


class PathIPC:
    __slots__ = ('sock', 'active', 'port', 'max_wait')
    sock: socket
    active: bool
    port: int | None

    def __init__(self, max_wait: float):
        self.max_wait = max_wait

    def _get_active_port(self, active_path: Path) -> tuple[bool, int | None]:
        """
        Returns a tuple that indicates whether this process is the primary process, and the port to send to if it
        is not.
        """
        try:
            with active_path.open('r') as f:
                active_pid, port = map(int, f.read().split(','))
        except FileNotFoundError:
            log.debug(f"No active instance info was available - {active_path.as_posix()} doesn't exist")
            return True, None
        except OSError as e:
            log.debug(f'Assuming no other instance is active - unable to read {active_path.as_posix()}: {e}')
            return True, None
        try:
            active = not Process(active_pid).is_running()
        except NoSuchProcess:
            log.debug(f"Found pid={active_pid} and {port=} in {active_path.as_posix()} but that process doesn't exist")
            active = True
            port = None  # Don't re-use the old port (it may not be available anymore)

        return active, port

    def _init_primary(self, active_path: Path):
        sock = self.sock
        sock.bind(('localhost', 0))
        sock.listen(100)
        sock.setblocking(False)
        port = sock.getsockname()[1]
        pid = getpid()
        log.info(f'Primary instance with {pid=} {port=}')
        active_path.write_text(f'{pid},{port}')

    def __enter__(self) -> PathIPC:
        self.sock = socket()
        cache_dir = get_user_cache_dir('music_manager')
        active_path = cache_dir.joinpath('active_pid_port.txt')
        with FileLock(cache_dir.joinpath('init.lock').as_posix()):
            self.active, self.port = active, port = self._get_active_port(active_path)
            if active:
                self._init_primary(active_path)
            else:
                log.info(f'Follower instance with pid={getpid()} {port=}')

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sock.close()

    def run(self, arg_paths: Collection[str]) -> list[str] | None:
        if self.active:
            return list(arg_paths) + self._get_all_paths()
        else:
            self._send_paths(arg_paths)
            return None

    def _get_all_paths(self) -> list[str]:
        paths = []
        selector = DefaultSelector()

        def accept(sock, _mask):
            conn, addr = sock.accept()
            conn.setblocking(False)
            selector.register(conn, EVENT_READ, read)

        def read(conn, _mask):
            if data := conn.recv(2000):
                paths.append(data.decode('utf-8'))
                # log.debug(f'Received path={data!r} from other instance')
            else:
                selector.unregister(conn)
                conn.close()

        selector.register(self.sock, EVENT_READ, accept)
        start = monotonic()
        while (monotonic() - start) < self.max_wait:
            for key, mask in selector.select(0.1):
                key.data(key.fileobj, mask)

        return paths

    def _send_paths(self, arg_paths: Collection[str]):
        self.sock.connect(('localhost', self.port))
        for path in arg_paths:
            self.sock.send(path.encode('utf-8'))
