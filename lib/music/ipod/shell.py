
import logging
import shlex
import sys
from argparse import ArgumentParser
from cmd import Cmd
from datetime import datetime
from functools import cached_property, wraps
from itertools import count
from typing import Dict, Iterable, Optional, List

from tz_aware_dt import now
from ds_tools.output import colored, readable_bytes, Printer, Terminal

from .ipod import iPod
from .path import iPath

__all__ = ['iPodShell']
log = logging.getLogger(__name__)


class ArgError(Exception):
    pass


class _ShellArgParser(ArgumentParser):
    """Raises an exception on errors instead of exiting"""
    def error(self, message: str):
        self.print_usage(sys.stderr)
        raise ArgError(f'{self.prog}: error: {message}')


def cmd_command(func):
    name = func.__name__
    command = name[3:]

    @wraps(func)
    def wrapper(self, arg_str, **kwargs):
        parser = self._parsers[command]
        try:
            args = parser.parse_args(shlex.split(arg_str))
            for key, val in args._get_kwargs():
                kwargs.setdefault(key, val)
            return func(self, **kwargs)
        except ArgError as e:
            _stderr(e)
            return None
    return wrapper


class iPodShell(Cmd):
    def __init__(self, ipod: Optional[iPod] = None, completekey='tab', stdin=None, stdout=None):
        super().__init__(completekey=completekey, stdin=stdin, stdout=stdout)
        self.ipod = ipod or iPod.find()
        self._num = count()
        self._ps1 = '{} iPod[{}]: {} {}{} '.format(
            colored('{}', 11), colored(self.ipod.name, 14), colored('{}', 11), colored('{}', 10), colored('$', 11)
        )
        self.cwd = self.ipod.get_path('/')  # type: iPath
        # self.complete_cat = self._complete
        # self.complete_ls = self._complete
        self._printer = Printer('pseudo-json')
        self._term = Terminal()
        print(colored('=' * (self._term.width - 1), 6))

    def cmdloop(self, intro: Optional[str] = None):
        return super().cmdloop(intro or f'Interactive iPod Session - Connected to: {self.ipod}')

    @property
    def prompt(self):
        return self._ps1.format(now('[%H:%M:%S]'), self.cwd, next(self._num))

    def do_exit(self, arg_str):
        return True

    def do_quit(self, arg_str):
        return True

    def do_pwd(self, arg_str):
        print(self.cwd)

    # def _complete(self, text, line, begidx, endidx):
    #     print(f'_complete({text=!r}, {line=!r}, {begidx=!r}, {endidx=!r})')
    #     filename = text.split('/')[-1]
    #     dirname = '/'.join(text.split('/')[:-1])
    #     return [p.as_posix() for p in self.cwd.joinpath(dirname).iterdir() if p.name.startswith(filename)]

    @cached_property
    def _parsers(self) -> Dict[str, _ShellArgParser]:
        parsers = {}
        # fmt: off
        ls_parser = parsers['ls'] = _ShellArgParser('ls', description='List information about the FILEs (the current directory by default).')
        ls_parser.add_argument('file', nargs='*', help='The files or directorties to list')
        ls_parser.add_argument('--all', '-a', dest='show_all', action='store_true', help='do not ignore entries starting with .')
        ls_parser.add_argument('--long', '-l', action='store_true', help='use a long listing format')
        ls_parser.add_argument('-1', dest='one', action='store_true', help='use a long listing format')

        cd_parser = parsers['cd'] = _ShellArgParser('cd', description='Change the shell working directory.')
        cd_parser.add_argument('directory', help='The directory to be the new working directory')

        cat_parser = parsers['cat'] = _ShellArgParser('cat', description='Concatenate FILE(s) to standard output.')
        cat_parser.add_argument('file', nargs='+', help='The files to print')

        head_parser = parsers['head'] = _ShellArgParser('head', description='Print the first 10 lines of each FILE to standard output.\nWith more than one FILE, precede each with a header giving the file name.')
        head_parser.add_argument('file', nargs='+', help='The files to print')
        head_count_group = head_parser.add_mutually_exclusive_group()
        head_count_group.add_argument('--lines', '-n', metavar='NUM', type=int, default=10, help='Print the first NUM lines instead of the first 10; with the leading \'-\', print all but the last NUM lines of each file')
        head_count_group.add_argument('--bytes', '-c', dest='byte_count', metavar='NUM', type=int, help='Print the first NUM bytes of each file; with the leading \'-\', print all but the last NUM bytes of each file')
        head_verbosity_group = head_parser.add_mutually_exclusive_group()
        head_verbosity_group.add_argument('--quiet', '-q', action='store_true', help='Never print headers giving file names')
        head_verbosity_group.add_argument('--verbose', '-v', action='store_true', help='Always print headers giving file names')

        rm_parser = parsers['rm'] = _ShellArgParser('rm', description='Remove (unlink) the FILE(s).')
        rm_parser.add_argument('file', nargs='*', help='The files or directorties to list')
        # fmt: on
        return parsers

    def _rel_path(self, loc) -> iPath:
        # noinspection PyUnboundLocalVariable
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

    @cmd_command
    def do_cd(self, directory: str):
        path = self._rel_path(directory)
        # noinspection PyUnboundLocalVariable
        if path.is_dir():
            self.cwd = path.resolve()
        elif path.exists():
            _stderr(f'cd: {directory}: Not a directory')
        else:
            _stderr(f'cd: {directory}: No such file or directory')

    def do_stat(self, file):
        path = self._rel_path(file)
        if path.exists():
            # noinspection PyUnresolvedReferences
            self._printer.pprint(path.stat()._info)
        else:
            _stderr(f'stat: cannot stat {file}: No such file or directory')

    @cmd_command
    def do_ls(self, file: Iterable[str], show_all=False, long=False, one=False):
        def print_path(path, rel=None):
            rel = rel or self._rel_to_cwd(path)
            if long:
                perm_chars = 'dx' if sub_path.is_dir() else '--'
                stat = sub_path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                size = readable_bytes(stat.st_size)[:-1]
                perms = '{}rw-rw-rw-{}'.format(*perm_chars)
                print(f'{perms} {size:>7s} {mtime} {rel}')
            else:
                print(rel)

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
                    print('  '.join(rel for p, rel in contents))
            elif not path.exists():
                _stderr(f'ls: cannot access {self._rel_to_cwd(path)!r}: No such file or directory')
            else:
                print_path(path)

    def do_lst(self, arg_str):
        return self.do_ls(arg_str, show_all=True, long=True)

    def _is_file(self, path, cmd, action):
        if path.is_dir():
            _stderr(f'{cmd}: cannot {action} {self._rel_to_cwd(path)!r}: Is a directory')
        elif not path.exists():
            _stderr(f'{cmd}: cannot {action} {self._rel_to_cwd(path)!r}: No such file or directory')
        else:
            return True
        return False

    @cmd_command
    def do_cat(self, file: Iterable[str]):
        for path in self._rel_paths(file, False, True):
            if self._is_file(path, 'cat', 'read'):
                with path.open() as f:
                    contents = f.read()     # readline is slow right now
                sys.stdout.write(contents)
                sys.stdout.flush()

    @cmd_command
    def do_rm(self, file: Iterable[str]):
        for path in self._rel_paths(file, False, True):
            if self._is_file(path, 'rm', 'remove'):
                path.unlink()

    @cmd_command
    def do_head(self, file: Iterable[str], lines=10, byte_count=None, quiet=False, verbose=False):
        for i, path in enumerate(self._rel_paths(file, False, True)):
            if self._is_file(path, 'head', 'read'):
                if (i or verbose) and not quiet:
                    print(f'\n==> {self._rel_to_cwd(path)} <==')

                with path.open() as f:
                    if byte_count:
                        print(f.read(byte_count))
                    else:
                        print('\n'.join(f.read().splitlines()[:lines]))

    # def do_mkdir(self, p):
    #     print(self.afc.make_directory(p))
    #
    # def do_rmdir(self, p):
    #     return self.afc.remove_directory(p)
    #
    # def do_deviceinfo(self, p):
    #     for k, v in self.afc.get_device_infos().items():
    #         print(k, '\t:\t', v)
    #
    # def do_mv(self, p):
    #     t = p.split()
    #     return self.afc.file_rename(t[0], t[1])

    # def do_link(self, p):
    #     z = p.split()
    #     self.afc.make_link(AFC_SYMLINK, z[0], z[1])


def _stderr(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
