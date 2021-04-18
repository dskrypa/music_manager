#!/usr/bin/env python

import sys
from pathlib import Path

THIS_PATH = Path(__file__).resolve()
sys.path.insert(0, THIS_PATH.parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

import logging

from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from music.__version__ import __author_email__, __version__, __author__, __url__

log = logging.getLogger(__name__)


def parser():
    # fmt: off
    parser = ArgParser(description='Music Manager GUI')
    with parser.add_subparser('action', 'open', help='Open directly to the Album view for the given path') as open_parser:
        open_parser.add_argument('album_path', help='The path to the album to open')

    with parser.add_subparser('action', 'clean', help='Open directly to the Clean view for the given path') as clean_parser:
        clean_parser.add_argument('path', nargs='+', help='The directory containing files to clean')
        clean_parser.add_argument('--multi_instance_wait', '-w', type=int, default=1, help='Seconds to wait for multiple instances started at the same time to collaborate on paths')

    with parser.add_subparser('action', 'configure', help='Configure registry entries for right-click actions') as config_parser:
        config_parser.include_common_args('dry_run')

    parser.include_common_args('verbosity')
    parser.add_common_arg('--match_log', action='store_true', help='Enable debug logging for the album match processing logger')
    # fmt: on
    return parser


@wrap_main
def main():
    args = parser().parse_args(req_subparser_value=False)

    from ds_tools.logging import init_logging
    init_logging(args.verbose, names=None, millis=True)

    if args.action == 'configure':
        configure(args)
    else:
        launch_gui(args)


def launch_gui(args):
    if args.action == 'clean':
        if (clean_paths := get_clean_paths(args.multi_instance_wait, args.path)) is None:
            log.debug('Exiting non-primary clean process')
            return

    from PySimpleGUI import theme

    from music.common.prompts import set_ui_mode, UIMode
    from music.files.patches import apply_mutagen_patches
    from music.gui.patches import patch_all
    from music.gui.views.main import MainView

    apply_mutagen_patches()
    patch_all()
    # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
    if args.match_log:
        logging.getLogger('music.manager.wiki_match.matching').setLevel(logging.DEBUG)

    set_ui_mode(UIMode.GUI)
    theme('SystemDefaultForReal')

    start_kwargs = dict(title='Music Manager', resizable=True, size=(1700, 750), element_justification='center')
    if args.action == 'open':
        start_kwargs['init_event'] = ('init_view', {'view': 'album', 'path': args.album_path})
    elif args.action == 'clean':
        start_kwargs['init_event'] = ('init_view', {'view': 'clean', 'path': clean_paths})  # noqa
        log.debug(f'Clean paths={args.path}')

    MainView.start(**start_kwargs)


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


def configure(args):
    import platform
    if (system := platform.system()) != 'Windows':
        raise RuntimeError(f'Automatic right-click menu integration is not supported on {system=!r}')

    dry_run = args.dry_run
    venv_exe = sys.executable[0].upper() + sys.executable[1:]
    expected = {
        'Update Album Tags': f'"{venv_exe}" "{THIS_PATH}" open "%L" -vv',
        'Clean Tags': f'"{venv_exe}" "{THIS_PATH}" clean "%1" -vv',
    }
    for location in ('*\\shell', 'Directory\\shell', 'Directory\\Background\\shell'):
        for entry, command in expected.items():
            maybe_set_key(f'{location}\\{entry}\\command', command, dry_run)
            if entry == 'Clean Tags':
                maybe_set_key(f'{location}\\{entry}', 'Player', dry_run, 'MultiSelectModel')
                # maybe_set_key(f'*\\shell\\Clean Tags', 'Player', dry_run, 'MultiSelectModel')

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
        log.info(f'Already contains expected value: HKEY_CLASSES_ROOT\\{key_path}')


if __name__ == '__main__':
    main()
