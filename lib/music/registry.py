"""

"""

import logging
import platform
import sys
from pathlib import Path
from winreg import HKEY_CLASSES_ROOT, OpenKey, QueryValue, CreateKeyEx, SetValue, REG_SZ, KEY_WRITE, KEY_READ
from winreg import QueryValueEx, SetValueEx

__all__ = []
log = logging.getLogger(__name__)


def configure_music_manager_gui(dry_run: bool):
    _verify_runtime()

    command_str = _get_command_str()

    add_context_command('*\\shell', 'Update Album Tags', 'open "%L" -vv', command_str, dry_run)
    add_context_command('Directory\\shell', 'Update Album Tags', 'open "%L" -vv', command_str, dry_run)
    # add_context_command('Directory\\Background\\shell', 'Update Album Tags', 'open "%L" -vv', command_str, dry_run)

    add_context_command('*\\shell', 'Clean Tags', 'clean "%1" -vv', command_str, dry_run)
    add_context_command('Directory\\shell', 'Clean Tags', 'clean "%1" -vv', command_str, dry_run)
    # add_context_command('Directory\\shell', 'Clean Tags', 'clean "%1" -vv -W', command_str, dry_run)
    # add_context_command('Directory\\Background\\shell', 'Clean Tags', 'clean "%1" -vv', command_str, dry_run)
    # if entry == 'Clean Tags':
    #     maybe_set_key(f'{hkcr_path}\\{entry}', 'Player', dry_run, 'MultiSelectModel')
    #     maybe_set_key(f'*\\shell\\Clean Tags', 'Player', dry_run, 'MultiSelectModel')

    # maybe_set_key(f'SystemFileAssociations\\audio\\shell\\Clean Song Tags\\command', expected['Clean Tags'], dry_run)
    # maybe_set_key(
    #     f'SystemFileAssociations\\Directory.Audio\\shell\\Clean Song Tags\\command', expected['Clean Tags'], dry_run
    # )
    # send_to_dir = Path('~/AppData/Roaming/Microsoft/Windows/SendTo').expanduser()


def _verify_runtime():
    if (system := platform.system()) != 'Windows':
        raise RuntimeError(f'Automatic right-click menu integration is not supported on {system=!r}')
    elif not sys.argv:
        raise RuntimeError(f'Unable to determine arguments used to run this program')


def add_context_command(
    hkcr_path: str, display_text: str, cmd_args: str, command_str: str = None, dry_run: bool = False
):
    if command_str is None:
        command_str = _get_command_str()

    command = f'{command_str} {cmd_args}'
    maybe_set_key(f'{hkcr_path}\\{display_text}\\command', command, dry_run)


def _get_command_str() -> str:
    command = Path(sys.argv[0]).resolve()
    if not command.exists() and command.with_suffix('.exe').exists():
        command = command.with_suffix('.exe')

    if command.suffix.lower() == '.exe':
        command_str = f'"{command}"'
    else:
        venv_exe = sys.executable[0].upper() + sys.executable[1:]
        command_str = f'"{venv_exe}" "{command}"'

    return command_str


def maybe_set_key(key_path: str, expected: str, dry_run: bool = False, var_name: str = None):
    value = get_value(key_path, var_name)
    if value != expected:
        set_value(key_path, expected, dry_run, var_name)
    else:
        log.info(f'Already contains expected value: HKEY_CLASSES_ROOT\\{key_path} = {expected!r}')


def get_value(key_path: str, var_name: str = None):
    try:
        with OpenKey(HKEY_CLASSES_ROOT, key_path, 0, KEY_READ) as entry_key:
            if var_name:
                value = QueryValueEx(entry_key, var_name)[0]
            else:
                value = QueryValue(entry_key, None)
    except FileNotFoundError:
        value = None

    return value


def set_value(key_path: str, value: str, dry_run: bool = False, var_name: str = None):
    prefix = '[DRY RUN] Would set' if dry_run else 'Setting'
    suffix = f'[{var_name!r}]' if var_name else ''
    log.info(f'{prefix} HKEY_CLASSES_ROOT\\{key_path}{suffix} = {value!r}')
    if not dry_run:
        with CreateKeyEx(HKEY_CLASSES_ROOT, key_path, 0, KEY_WRITE) as entry_key:
            if var_name:
                SetValueEx(entry_key, var_name, 0, REG_SZ, value)
            else:
                SetValue(entry_key, None, REG_SZ, expected)  # noqa
