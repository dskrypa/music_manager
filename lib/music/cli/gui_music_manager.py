import logging
from pathlib import Path

from cli_command_parser import Command, Counter, SubCommand, ParamGroup, Flag, Positional, Option, main  # noqa

from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa

log = logging.getLogger(__name__)


class MusicManagerGui(Command, description='Music Manager GUI'):
    sub_cmd = SubCommand(required=False)
    with ParamGroup('Common') as group:
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
        match_log = Flag(help='Enable debug logging for the album match processing logger')

    def _init_command_(self):
        from ds_tools.logging import init_logging
        init_logging(self.verbose, names=None, millis=True, set_levels={'PIL': 30})

    def main(self):
        self.run_gui()

    def run_gui(self, init_event=None):
        from music.gui.music_manager_views.main import MainView

        self.patch_and_set_mode()

        try:
            MainView.start(
                title='Music Manager',
                resizable=True,
                size=(1700, 750),
                element_justification='center',
                init_event=init_event,
            )
        except Exception:
            log.critical('Exiting run_gui due to unhandled exception', exc_info=True)
            raise

    def patch_and_set_mode(self):
        from music.common.prompts import set_ui_mode, UIMode
        from music.files.patches import apply_mutagen_patches
        from music.gui.patches import patch_all

        apply_mutagen_patches()
        patch_all()
        # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
        if self.match_log:
            from music.manager.wiki_match import mlog  # It may not have been imported before this point

            mlog.setLevel(logging.NOTSET)

        set_ui_mode(UIMode.GUI)


class Open(MusicManagerGui, help='Open directly to the Album view for the given path'):
    album_path = Positional(help='The path to the album to open')

    def main(self):
        self.run_gui(('init_view', {'view': 'album', 'path': self.album_path}))


class Clean(MusicManagerGui, help='Open directly to the Clean view for the given path'):
    path = Positional(nargs='+', help='The directory containing files to clean')
    with ParamGroup('Wait Options', mutually_exclusive=True):
        multi_instance_wait: int = Option('-w', default=1, help='Seconds to wait for multiple instances started at the same time to collaborate on paths')
        no_wait = Flag('-W', help='Do not wait for other instances')

    def main(self):
        if self.no_wait:
            clean_paths = self.path
        elif (clean_paths := get_clean_paths(self.multi_instance_wait, self.path)) is None:
            log.debug('Exiting non-primary clean process')
            return

        log.debug(f'Clean paths={clean_paths}')
        self.run_gui(('init_view', {'view': 'clean', 'path': clean_paths}))


class Configure(MusicManagerGui, help='Configure registry entries for right-click actions'):
    dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')

    def main(self):
        from music.registry import configure_music_manager_gui

        configure_music_manager_gui(self.dry_run)


def get_clean_paths(max_wait: int, arg_paths):
    from os import getpid
    from selectors import DefaultSelector, EVENT_READ
    from socket import socket
    from time import monotonic
    from filelock import FileLock
    from psutil import Process, NoSuchProcess
    from ds_tools.fs.paths import get_user_cache_dir

    cache_dir = Path(get_user_cache_dir('music_manager'))
    with FileLock(cache_dir.joinpath('init.lock').as_posix()):
        pid = getpid()
        active_path = cache_dir.joinpath('active_pid_port.txt')
        try:
            with active_path.open('r') as f:
                active_pid, port = map(int, f.read().split(','))
        except OSError:
            active = True
        else:
            try:
                active = not Process(active_pid).is_running()
            except NoSuchProcess:
                active = True

        sock = socket()
        if active:
            sock.bind(('localhost', 0))
            sock.listen(100)
            sock.setblocking(False)
            port = sock.getsockname()[1]
            log.info(f'Primary instance with {pid=} {port=}')
            with active_path.open('w') as f:
                f.write(f'{pid},{port}')
        else:
            log.info(f'Follower instance with {pid=} {port=}')

    if active:
        paths = list(arg_paths)
        selector = DefaultSelector()

        def accept(sock, mask):
            conn, addr = sock.accept()
            conn.setblocking(False)
            selector.register(conn, EVENT_READ, read)

        def read(conn, mask):
            if data := conn.recv(2000):
                paths.append(data.decode('utf-8'))
                # log.debug(f'Received path={data!r} from other instance')
            else:
                selector.unregister(conn)
                conn.close()

        selector.register(sock, EVENT_READ, accept)
        start = monotonic()
        while (monotonic() - start) < max_wait:
            for key, mask in selector.select(0.1):
                key.data(key.fileobj, mask)
    else:
        paths = None
        sock.connect(('localhost', port))
        for path in arg_paths:
            sock.send(path.encode('utf-8'))

    sock.close()
    return paths
