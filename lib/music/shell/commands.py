
import logging
import shlex
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from functools import cached_property, wraps
from io import StringIO, BytesIO, TextIOBase, RawIOBase
from sys import stdout as out, stderr as err
from typing import Dict, Iterable, List, Optional, Union, AnyStr, Type, Any

from ds_tools.output import colored, readable_bytes, Printer
from pymobiledevice.afc.exceptions import iOSError

from ..ipod import iPath
from .argparse import ShellArgParser
from .exceptions import ArgError, ExitLoop, UnknownCommand, ExecutionError

__all__ = ['run_shell_command']
log = logging.getLogger(__name__)
IO = Union[TextIOBase, RawIOBase]


def run_shell_command(cwd: iPath, input_str: str) -> Optional[iPath]:
    name, *raw_args = shlex.split(input_str)
    try:
        cmd_cls = ShellCommand._commands[name]
    except KeyError:
        raise UnknownCommand(name)
    # noinspection PyUnresolvedReferences
    kwargs = cmd_cls.parser.parse_kwargs(raw_args)
    try:
        return cmd_cls(cwd)(**kwargs)
    except iOSError as e:
        raise ExecutionError(name, e)


class ShellCommand(ABC):
    _commands: Dict[str, Type['ShellCommand']] = {}
    name: Optional[str] = None

    # noinspection PyMethodOverriding
    def __init_subclass__(cls, cmd):
        cls.name = cmd
        ShellCommand._commands[cmd] = cls

    def __init__(self, cwd: iPath, stdin: Optional[IO] = None, stdout: IO = out, stderr: IO = err):
        self.cwd = cwd
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    @abstractmethod
    def __call__(self, **kwargs) -> Optional[iPath]:
        raise NotImplementedError

    @property
    @abstractmethod
    def parser(self) -> ShellArgParser:
        raise NotImplementedError

    def print(self, text: Any):
        if not isinstance(text, str):
            text = str(text)
        self.stdout.write(text + '\n')

    def error(self, text: Any):
        if not isinstance(text, str):
            text = str(text)
        self.stderr.write(text + '\n')

    def _rel_path(self, loc) -> iPath:
        # noinspection PyUnboundLocalVariable,PyUnresolvedReferences
        if '*' in loc and (paths := list(self.cwd.glob(loc))) and len(paths) == 1:
            return paths[0]
        return self.cwd.joinpath(loc) if loc else self.cwd

    def _rel_paths(self, locs: Iterable[str], allow_cwd=True, required=False) -> List[iPath]:
        paths = []
        for loc in locs:
            paths.extend(self.cwd.glob(loc))
        if not paths:
            if allow_cwd:
                paths.append(self.cwd)
            elif required:
                raise ArgError('At least one file must be specified')
        return paths

    def _rel_to_cwd(self, path: iPath) -> str:
        try:
            return path.relative_to(self.cwd).as_posix()
        except Exception:
            return path.as_posix()


class Exit(ShellCommand, cmd='exit'):
    parser = ShellArgParser('exit', description='Exit the shell')

    def __call__(self, **kwargs):
        raise ExitLoop


class Help(ShellCommand, cmd='help'):
    parser = ShellArgParser('help', description='Print help information')

    def __call__(self, **kwargs):
        self.print('Available commands:')
        for name, cls in sorted(self._commands.items()):
            self.print(f'{name}: {cls.parser.description}')


class Pwd(ShellCommand, cmd='pwd'):
    parser = ShellArgParser('pwd', description='Print the current working directory')

    def __call__(self, **kwargs):
        self.print(self.cwd)


class Cd(ShellCommand, cmd='cd'):
    parser = ShellArgParser('cd', description='Change the shell working directory.')
    parser.add_argument('directory', help='The directory to be the new working directory')

    def __call__(self, directory):
        path = self._rel_path(directory)
        # noinspection PyUnboundLocalVariable
        if path.is_dir():
            return path.resolve()
        elif path.exists():
            self.error(f'cd: {directory}: Not a directory')
        else:
            self.error(f'cd: {directory}: No such file or directory')


class Ls(ShellCommand, cmd='ls'):
    parser = ShellArgParser('ls', description='List information about the FILEs (the current directory by default).')
    parser.add_argument('file', nargs='*', help='The files or directorties to list')
    parser.add_argument('--all', '-a', dest='show_all', action='store_true', help='do not ignore entries starting with .')
    parser.add_argument('--long', '-l', action='store_true', help='use a long listing format')
    parser.add_argument('-1', dest='one', action='store_true', help='use a long listing format')

    def __call__(self, file: Iterable[str], show_all=False, long=False, one=False):
        def print_path(path, rel=None):
            rel = rel or self._rel_to_cwd(path)
            if long:
                perm_chars = 'dx' if path.is_dir() else '--'
                stat = path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                size = readable_bytes(stat.st_size)[:-1]
                perms = '{}rw-rw-rw-{}'.format(*perm_chars)
                self.print(f'{perms} {size:>7s} {mtime} {rel}')
            else:
                self.print(rel)

        for path in self._rel_paths(file):
            if path.is_dir():
                contents = [
                    (p, colored(self._rel_to_cwd(p), 11 if p.is_dir() else None))
                    for p in path.iterdir()
                    if show_all or not p.name.startswith('.')
                ]
                if long or one:
                    for sub_path, rel in contents:
                        print_path(sub_path, rel)
                else:
                    self.print('  '.join(rel for p, rel in contents))
            elif not path.exists():
                self.error(f'ls: cannot access {self._rel_to_cwd(path)!r}: No such file or directory')
            else:
                print_path(path)


#
# def cmd_command(func):
#     name = func.__name__
#     command = name[3:]
#
#     @wraps(func)
#     def wrapper(self, arg_str, **kwargs):
#         parser = self._parsers[command]
#         try:
#             args = parser.parse_args(shlex.split(arg_str))
#             for key, val in args._get_kwargs():
#                 kwargs.setdefault(key, val)
#             return func(self, **kwargs)
#         except ArgError as e:
#             if e.args and e.args[0]:
#                 _stderr(e)
#             return None
#     return wrapper
#
#
#
# class iPodShell(_iPodShell):
#     @cached_property
#     def _parsers(self) -> Dict[str, ShellArgParser]:
#         # TODO: Move these closer to their functions somehow... probably need to refactor to have each cmd be a class
#         parsers = {}
#         # fmt: off
#         cat_parser = parsers['cat'] = ShellArgParser('cat', description='Concatenate FILE(s) to standard output.')
#         cat_parser.add_argument('file', nargs='+', help='The files to print')
#
#         head_parser = parsers['head'] = ShellArgParser('head', description='Print the first 10 lines of each FILE to standard output.\nWith more than one FILE, precede each with a header giving the file name.')
#         head_parser.add_argument('file', nargs='+', help='The files to print')
#         head_count_group = head_parser.add_mutually_exclusive_group()
#         head_count_group.add_argument('--lines', '-n', metavar='NUM', type=int, default=10, help='Print the first NUM lines instead of the first 10; with the leading \'-\', print all but the last NUM lines of each file')
#         head_count_group.add_argument('--bytes', '-c', dest='byte_count', metavar='NUM', type=int, help='Print the first NUM bytes of each file; with the leading \'-\', print all but the last NUM bytes of each file')
#         head_verbosity_group = head_parser.add_mutually_exclusive_group()
#         head_verbosity_group.add_argument('--quiet', '-q', action='store_true', help='Never print headers giving file names')
#         head_verbosity_group.add_argument('--verbose', '-v', action='store_true', help='Always print headers giving file names')
#
#         rm_parser = parsers['rm'] = ShellArgParser('rm', description='Remove (unlink) the FILE(s).')
#         rm_parser.add_argument('file', nargs='*', help='The files or directorties to list')
#
#         stat_parser = parsers['stat'] = ShellArgParser('stat', description='Display file or file system status.')
#         stat_parser.add_argument('file', help='The files to stat')
#         stat_parser.add_argument('--format', '-f', dest='out_fmt', choices=Printer.formats, default='yaml', help='The output format to use')
#
#         info_parser = parsers['info'] = ShellArgParser('info', description='Display device info')
#         info_parser.add_argument('--format', '-f', dest='out_fmt', choices=Printer.formats, default='yaml', help='The output format to use')
#
#         cp_parser = parsers['cp'] = ShellArgParser('cp', description='Copy SOURCE to DEST, or multiple SOURCE(s) to DIRECTORY.')
#         cp_parser.add_argument('source', nargs='+', help='One or more files to be copied')
#         cp_parser.add_argument('dest', help='The target filename or directory')
#         cp_parser.add_argument('--mode', '-m', choices=('ipod', 'i2p', 'p2i'), default='ipod', help='Copy files locally on the ipod, from the ipod to PC, or from PC to the ipod')
#         # fmt: on
#         return parsers
#
#     @cmd_command
#     def do_info(self, out_fmt='yaml'):
#         Printer(out_fmt).pprint(self.ipod.info)
#
#     @cmd_command
#     def do_stat(self, file: str, out_fmt='yaml'):
#         path = self._rel_path(file)
#         if path.exists():
#             # noinspection PyUnresolvedReferences
#             Printer(out_fmt).pprint(path.stat().as_dict())
#         else:
#             _stderr(f'stat: cannot stat {file}: No such file or directory')
#
#     def do_lst(self, arg_str):
#         return self.do_ls(arg_str, show_all=True, long=True)
#
#     def _is_file(self, path, cmd, action):
#         if path.is_dir():
#             _stderr(f'{cmd}: cannot {action} {self._rel_to_cwd(path)!r}: Is a directory')
#         elif not path.exists():
#             _stderr(f'{cmd}: cannot {action} {self._rel_to_cwd(path)!r}: No such file or directory')
#         else:
#             return True
#         return False
#
#     @cmd_command
#     def do_cat(self, file: Iterable[str]):
#         for path in self._rel_paths(file, False, True):
#             if self._is_file(path, 'cat', 'read'):
#                 with path.open('rb') as f:
#                     contents = f.read()     # readline is slow right now
#                 sys.stdout.write(contents.decode('utf-8', 'replace'))
#                 sys.stdout.flush()
#
#     @cmd_command
#     def do_rm(self, file: Iterable[str]):
#         for path in self._rel_paths(file, False, True):
#             if self._is_file(path, 'rm', 'remove'):
#                 path.unlink()
#
#     @cmd_command
#     def do_head(self, file: Iterable[str], lines=10, byte_count=None, quiet=False, verbose=False):
#         for i, path in enumerate(self._rel_paths(file, False, True)):
#             if self._is_file(path, 'head', 'read'):
#                 if (i or verbose) and not quiet:
#                     print(f'\n==> {self._rel_to_cwd(path)} <==')
#
#                 with path.open('rb') as f:
#                     if byte_count:
#                         print(f.read(byte_count).decode('utf-8', 'replace'))
#                     else:
#                         print('\n'.join(f.read().decode('utf-8', 'replace').splitlines()[:lines]))
#
#     def do_touch(self, file: str):
#         path = self._rel_path(file)
#         if self._is_file(path, 'touch', 'touch'):
#             path.touch()
#
#     @cmd_command
#     def do_cp(self, source: Iterable[str], dest: str, mode: str = 'ipod'):
#         pass

    # def do_mkdir(self, p):
    #     print(self.afc.make_directory(p))
    #
    # def do_rmdir(self, p):
    #     return self.afc.remove_directory(p)
    #
    # def do_mv(self, p):
    #     t = p.split()
    #     return self.afc.file_rename(t[0], t[1])

    # def do_link(self, p):
    #     z = p.split()
    #     self.afc.make_link(AFC_SYMLINK, z[0], z[1])
