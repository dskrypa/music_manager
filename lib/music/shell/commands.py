
import logging
import shlex
from abc import ABC, abstractmethod
from datetime import datetime
from io import StringIO, BytesIO, TextIOBase, RawIOBase
from pathlib import Path
from sys import stdout as out, stderr as err
from typing import Dict, Iterable, List, Optional, Union, Type, Any

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
        self.ipod = cwd._ipod
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

    def _is_file(self, path: iPath, action: str) -> bool:
        if path.is_dir():
            self.error(f'{self.name}: cannot {action} {self._rel_to_cwd(path)!r}: Is a directory')
        elif not path.exists():
            self.error(f'{self.name}: cannot {action} {self._rel_to_cwd(path)!r}: No such file or directory')
        else:
            return True
        return False


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


class Lst(Ls, cmd='lst'):
    def __call__(self, **kwargs):
        kwargs['show_all'] = True
        kwargs['long'] = True
        return super().__call__(**kwargs)


class Cat(ShellCommand, cmd='cat'):
    parser = ShellArgParser('cat', description='Concatenate FILE(s) to standard output.')
    parser.add_argument('file', nargs='+', help='The files to print')

    def __call__(self, file: Iterable[str]):
        for path in self._rel_paths(file, False, True):
            if self._is_file(path, 'read'):
                with path.open('rb') as f:
                    contents = f.read()     # readline is slow right now
                self.stdout.write(contents.decode('utf-8', 'replace'))
                self.stdout.flush()


class Head(ShellCommand, cmd='head'):
    parser = ShellArgParser('head', description='Print the first 10 lines of each FILE to standard output.\nWith more than one FILE, precede each with a header giving the file name.')
    parser.add_argument('file', nargs='+', help='The files to print')
    head_count_group = parser.add_mutually_exclusive_group()
    head_count_group.add_argument('--lines', '-n', metavar='NUM', type=int, default=10, help='Print the first NUM lines instead of the first 10; with the leading \'-\', print all but the last NUM lines of each file')
    head_count_group.add_argument('--bytes', '-c', dest='byte_count', metavar='NUM', type=int, help='Print the first NUM bytes of each file; with the leading \'-\', print all but the last NUM bytes of each file')
    head_verbosity_group = parser.add_mutually_exclusive_group()
    head_verbosity_group.add_argument('--quiet', '-q', action='store_true', help='Never print headers giving file names')
    head_verbosity_group.add_argument('--verbose', '-v', action='store_true', help='Always print headers giving file names')

    def __call__(self, file: Iterable[str], lines=10, byte_count=None, quiet=False, verbose=False):
        for i, path in enumerate(self._rel_paths(file, False, True)):
            if self._is_file(path, 'read'):
                if (i or verbose) and not quiet:
                    self.print(f'\n==> {self._rel_to_cwd(path)} <==')

                with path.open('rb') as f:
                    if byte_count:
                        self.print(f.read(byte_count).decode('utf-8', 'replace'))
                    else:
                        self.print('\n'.join(f.read().decode('utf-8', 'replace').splitlines()[:lines]))


class Remove(ShellCommand, cmd='rm'):
    parser = ShellArgParser('rm', description='Remove (unlink) the FILE(s).')
    parser.add_argument('file', nargs='+', help='The files to delete')
    parser.add_argument('--dry_run', '-D', action='store_true', help='Print actions that would be taken instead of taking them')

    def __call__(self, file: Iterable[str], dry_run=False):
        prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
        for path in self._rel_paths(file, False, True):
            if self._is_file(path, 'remove'):
                self.print(f'{prefix} {path}')
                if not dry_run:
                    path.unlink()


class Stat(ShellCommand, cmd='stat'):
    parser = ShellArgParser('stat', description='Display file or file system status.')
    parser.add_argument('file', nargs='+', help='The files or directories to stat')
    parser.add_argument('--format', '-f', dest='out_fmt', choices=Printer.formats, default='yaml', help='The output format to use')

    def __call__(self, file: Iterable[str], out_fmt='yaml'):
        printer = Printer(out_fmt)
        for path in self._rel_paths(file, False, True):
            if path.exists():
                # noinspection PyUnresolvedReferences
                printer.pprint(path.stat().as_dict())
            else:
                self.error(f'{self.name}: cannot stat {self._rel_to_cwd(path)!r}: No such file or directory')


class Info(ShellCommand, cmd='info'):
    parser = ShellArgParser('info', description='Display device info')
    parser.add_argument('--format', '-f', dest='out_fmt', choices=Printer.formats, default='yaml', help='The output format to use')

    def __call__(self, out_fmt='yaml'):
        Printer(out_fmt).pprint(self.ipod.info)


class Touch(ShellCommand, cmd='touch'):
    parser = ShellArgParser('touch', description='Update the access and modification times of each FILE to the current time.')
    parser.add_argument('file', nargs='+', help='The files to update')

    def __call__(self, file: Iterable[str]):
        for path in self._rel_paths(file, False, True):
            if self._is_file(path, 'touch'):
                path.touch()


class Copy(ShellCommand, cmd='cp'):
    block_size = 10485760  # 10 MB
    parser = ShellArgParser('cp', description='Copy SOURCE to DEST, or multiple SOURCE(s) to DIRECTORY.')
    parser.add_argument('source', nargs='+', help='One or more files to be copied')
    parser.add_argument('dest', help='The target filename or directory')
    parser.add_argument('--mode', '-m', choices=('ipod', 'i2p', 'p2i'), default='ipod', help='Copy files locally on the ipod, from the ipod to PC, or from PC to the ipod')
    parser.add_argument('--dry_run', '-D', action='store_true', help='Print actions that would be taken instead of taking them')

    def _get_paths(self, source: Iterable[str], dest: str, mode: str = 'ipod'):
        if mode == 'i2p':
            sources = self._rel_paths(source)
            dest = Path(dest).resolve()
        elif mode == 'p2i':
            sources = [Path(p).resolve() for p in source]
            dest = self._rel_path(dest)
        elif mode == 'ipod':
            sources = self._rel_paths(source)
            dest = self._rel_path(dest)
        else:
            raise ExecutionError(self.name, f'Unexpected {mode=}')
        return sources, dest

    def __call__(self, source: Iterable[str], dest: str, mode: str = 'ipod', dry_run=False):
        sources, dest = self._get_paths(source, dest, mode)
        if len(sources) > 1 and not dest.is_dir():
            raise ExecutionError(self.name, 'When multiple source files are specified, dest must be a directory')

        prefix = '[DRY RUN] Would copy' if dry_run else 'Copying'
        for path in sources:
            if self._is_file(path, 'copy'):
                dest_file = dest.joinpath(path.name) if dest.is_dir() else dest
                self.print(f'{prefix} {path} -> {dest_file}')
                if not dry_run:
                    with path.open('rb') as src, dest_file.open('wb') as dst:
                        while buf := src.read(self.block_size):
                            dst.write(buf)


class Mkdir(ShellCommand, cmd='mkdir'):
    parser = ShellArgParser('mkdir', description='Create the DIRECTORY(ies), if they do not already exist.')
    parser.add_argument('directory', nargs='+', help='One or more directories to be created')
    parser.add_argument('--parents', '-p', action='store_true', help='Make parent directories as needed')
    parser.add_argument('--dry_run', '-D', action='store_true', help='Print actions that would be taken instead of taking them')

    def __call__(self, directory: Iterable[str], parents=False, dry_run=False):
        prefix = '[DRY RUN] Would create' if dry_run else 'Creating'
        for path in self._rel_paths(directory, False, True):
            if path.exists():
                self.error(f'{self.name}: cannot create {self._rel_to_cwd(path)!r}: File exists')
            else:
                self.print(f'{prefix} {self._rel_to_cwd(path)}')
                if not dry_run:
                    path.mkdir(parents=parents)

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
