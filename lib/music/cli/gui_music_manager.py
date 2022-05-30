import logging
import sys
from pathlib import Path

from cli_command_parser import Command, Counter, SubCommand, ParamGroup, Flag, Positional, Option

from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa

log = logging.getLogger(__name__)


class MusicManagerGui(Command, description='Music Manager GUI'):
    sub_cmd = SubCommand(required=False)
    with ParamGroup('Common') as group:
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
        match_log = Flag(help='Enable debug logging for the album match processing logger')

    def __init__(self):
        from ds_tools.logging import init_logging
        init_logging(self.verbose, names=None, millis=True, set_levels={'PIL': 30})

    def main(self):
        self.run_gui()

    def run_gui(self, init_event=None):
        from music.gui.music_manager_views.main import MainView

        patch_and_set_mode(self.match_log)

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
        configure(self.dry_run)


def patch_and_set_mode(match_log: bool):
    from music.common.prompts import set_ui_mode, UIMode
    from music.files.patches import apply_mutagen_patches
    from music.gui.patches import patch_all

    apply_mutagen_patches()
    patch_all()
    # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
    if match_log:
        logging.getLogger('music.manager.wiki_match.matching').setLevel(logging.DEBUG)

    set_ui_mode(UIMode.GUI)


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


def configure(dry_run: bool):
    import platform
    if (system := platform.system()) != 'Windows':
        raise RuntimeError(f'Automatic right-click menu integration is not supported on {system=!r}')
    elif not sys.argv:
        raise RuntimeError(f'Unable to determine arguments used to run this program')

    command = Path(sys.argv[0]).resolve()
    if not command.exists() and command.with_suffix('.exe').exists():
        command = command.with_suffix('.exe')
    if command.suffix.lower() == '.exe':
        command_str = f'"{command}"'
    else:
        venv_exe = sys.executable[0].upper() + sys.executable[1:]
        command_str = f'"{venv_exe}" "{command}"'

    expected = {'Update Album Tags': f'{command_str} open "%L" -vv', 'Clean Tags': f'{command_str} clean "%1" -vv'}
    locations = (
        '*\\shell',
        'Directory\\shell',
        # 'Directory\\Background\\shell',
    )
    for location in locations:
        for entry, command in expected.items():
            # if entry == 'Clean Tags' and not location.startswith('*'):
            #     command += ' -W'
            maybe_set_key(f'{location}\\{entry}\\command', command, dry_run)
            # if entry == 'Clean Tags':
            #     maybe_set_key(f'{location}\\{entry}', 'Player', dry_run, 'MultiSelectModel')
            #     maybe_set_key(f'*\\shell\\Clean Tags', 'Player', dry_run, 'MultiSelectModel')

    # maybe_set_key(f'SystemFileAssociations\\audio\\shell\\Clean Song Tags\\command', expected['Clean Tags'], dry_run)
    # maybe_set_key(
    #     f'SystemFileAssociations\\Directory.Audio\\shell\\Clean Song Tags\\command', expected['Clean Tags'], dry_run
    # )
    # send_to_dir = Path('~/AppData/Roaming/Microsoft/Windows/SendTo').expanduser()


def maybe_set_key(key_path: str, expected: str, dry_run: bool = False, var_name: str = None):
    from winreg import HKEY_CLASSES_ROOT, OpenKey, QueryValue, CreateKeyEx, SetValue, REG_SZ, KEY_WRITE, KEY_READ
    from winreg import QueryValueEx, SetValueEx
    try:
        with OpenKey(HKEY_CLASSES_ROOT, key_path, 0, KEY_READ) as entry_key:
            if var_name:
                value = QueryValueEx(entry_key, var_name)[0]
            else:
                value = QueryValue(entry_key, None)
    except FileNotFoundError:
        value = None

    if value != expected:
        prefix = '[DRY RUN] Would set' if dry_run else 'Setting'
        if var_name:
            log.info(f'{prefix} HKEY_CLASSES_ROOT\\{key_path}[{var_name!r}] = {expected!r}')
        else:
            log.info(f'{prefix} HKEY_CLASSES_ROOT\\{key_path} = {expected!r}')

        if not dry_run:
            with CreateKeyEx(HKEY_CLASSES_ROOT, key_path, 0, KEY_WRITE) as entry_key:
                if var_name:
                    SetValueEx(entry_key, var_name, 0, REG_SZ, expected)
                else:
                    SetValue(entry_key, None, REG_SZ, expected)  # noqa
    else:
        log.info(f'Already contains expected value: HKEY_CLASSES_ROOT\\{key_path} = {expected!r}')
