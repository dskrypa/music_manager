
import logging
import os
import plistlib
import shlex
import sys
from argparse import ArgumentParser
from cmd import Cmd
from datetime import datetime
from functools import cached_property, wraps
from pprint import pprint
from typing import Dict, Iterable, Optional

from ds_tools.output import colored, readable_bytes

from .ipod import iPod
from .path import iPath

__all__ = ['iPodShell']
log = logging.getLogger(__name__)


def cmd_command(func):
    name = func.__name__
    command = name[3:]

    @wraps(func)
    def wrapper(self, arg_str):
        parser = self._parsers.get(command)
        args = parser.parse_args(shlex.split(arg_str))
        return func(self, **args.__dict__)
    return wrapper


class iPodShell(Cmd):
    def __init__(self, ipod: Optional[iPod] = None, completekey='tab', stdin=None, stdout=None):
        super().__init__(completekey=completekey, stdin=stdin, stdout=stdout)
        self.ipod = ipod or iPod.find()
        self.cwd = self.ipod.get_path('/')  # type: iPath
        self.complete_cat = self._complete
        self.complete_ls = self._complete

    def cmdloop(self, intro: Optional[str] = None):
        return super().cmdloop(intro or f'Interactive iPod Session - Connected to: {self.ipod}')

    @property
    def prompt(self):
        return f'iPod: {self.cwd} $ '

    def do_exit(self, arg_str):
        return True

    def do_quit(self, arg_str):
        return True

    def do_pwd(self, arg_str):
        print(self.cwd)

    def _complete(self, text, line, begidx, endidx):
        filename = text.split('/')[-1]
        dirname = '/'.join(text.split('/')[:-1])
        return [p.as_posix() for p in self.cwd.joinpath(dirname).iterdir() if p.name.startswith(filename)]

    @cached_property
    def _parsers(self) -> Dict[str, ArgumentParser]:
        parsers = {}

        ls_parser = parsers['ls'] = ArgumentParser(description='List information about the FILEs (the current directory by default).')
        ls_parser.add_argument('file', nargs='*', help='The files or directorties to list')
        ls_parser.add_argument('--all', '-a', dest='show_all', action='store_true', help='do not ignore entries starting with .')
        ls_parser.add_argument('--long', '-l', action='store_true', help='use a long listing format')
        ls_parser.add_argument('-1', dest='one', action='store_true', help='use a long listing format')

        cd_parser = parsers['cd'] = ArgumentParser(description='Change the shell working directory.')
        cd_parser.add_argument('directory', help='The directory to be the new working directory')

        cat_parser = parsers['cat'] = ArgumentParser(description='Concatenate FILE(s) to standard output.')
        cat_parser.add_argument('file', nargs='+', help='The files to print')

        return parsers

    def _rel_path(self, loc) -> iPath:
        return self.cwd.joinpath(loc) if loc else self.cwd

    def _rel_to_cwd(self, path: iPath) -> str:
        try:
            return path.relative_to(self.cwd).as_posix()
        except Exception:
            return path.as_posix()

    def do_link(self, p):
        z = p.split()
        self.afc.make_link(AFC_SYMLINK, z[0], z[1])

    @cmd_command
    def do_cd(self, directory: str):
        path = self._rel_path(directory)
        if path.is_dir():
            self.cwd = path
        elif path.exists():
            print(f'cd: {directory}: Not a directory', file=sys.stderr)
        else:
            print(f'cd: {directory}: No such file or directory', file=sys.stderr)

    def do_stat(self, file):
        path = self._rel_path(file)
        pprint(self.afc.get_file_info(path))

    @cmd_command
    def do_ls(self, file: Iterable[str], show_all=False, long=False, one=False):
        paths = [self._rel_path(f) for f in file] or [self.cwd]

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

        for path in paths:
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
                print(f'ls: cannot access {self._rel_to_cwd(path)!r}: No such file or directory', file=sys.stderr)
            else:
                print_path(path)

    @cmd_command
    def do_cat(self, file: Iterable[str]):
        paths = [self._rel_path(f) for f in file]
        if not paths:
            print('At least one file must be specified', file=sys.stderr)
            return

        for path in paths:
            if path.is_dir():
                print(f'cat: {self._rel_to_cwd(path)}: Is a directory', file=sys.stderr)
            elif path.exists():
                with path.open() as f:
                    contents = f.read()     # readline is slow right now
                sys.stdout.write(contents)
                sys.stdout.flush()
            else:
                print(f'cat: {self._rel_to_cwd(path)}: No such file or directory', file=sys.stderr)

    def do_rm(self, p):
        f = self.afc.get_file_info(self.cwd + '/' + p)
        if f['st_ifmt'] == 'S_IFDIR':
            d = self.afc.remove_directory(self.cwd + '/' + p)
        else:
            d = self.afc.file_remove(self.cwd + '/' + p)

    def do_pull(self, user_args):
        args = user_args.split()
        if len(args) != 2:
            out = '.'
            path = user_args
        else:
            out = args[1]
            path = args[0]

        f = self.afc.get_file_info(self.cwd + '/' + path)
        if not f:
            print('Source file does not exist..')
            return

        out_path = out + '/' + path
        if f['st_ifmt'] == 'S_IFDIR':
            if not os.path.isdir(out_path):
                os.makedirs(out_path, MODEMASK)

            for d in self.afc.read_directory(path):
                if d == '.' or d == '..' or d == '':
                    continue
                self.do_pull(path + '/' + d + ' ' + out)
        else:
            data = self.afc.get_file_contents(self.cwd + '/' + path)
            if data:
                if data and path.endswith('.plist'):
                    z = parsePlist(data)
                    plistlib.writePlist(z, out_path)
                else:
                    out_dir = os.path.dirname(out_path)
                    if not os.path.exists(out_dir):
                        os.makedirs(out_dir, MODEMASK)
                    with open(out_path, 'wb+') as f:
                        f.write(data)

    def do_push(self, p):
        fromTo = p.split()
        if len(fromTo) != 2:
            return
        print('from %s to %s' % (fromTo[0], fromTo[1]))
        if os.path.isdir(fromTo[0]):
            self.afc.make_directory(os.path.join(fromTo[1]))
            for x in os.listdir(fromTo[0]):
                if x.startswith('.'):
                    continue
                path = os.path.join(fromTo[0],x)
                self.do_push(path + ' ' + fromTo[1]+ '/' + path)
        else:
            if not fromTo[0].startswith('.'):
                data = open(fromTo[0], 'rb').read()
                self.afc.set_file_contents(self.cwd + '/' + fromTo[1], data)

    def do_head(self, p):
        print(self.afc.get_file_contents(self.cwd + '/' + p)[:32])

    def do_hexdump(self, p):
        t = p.split(' ')
        l = 0
        if len(t) < 1:
            return
        if len(t) == 2:
            l = int(t[1])
        z = self.afc.get_file_contents(self.cwd + '/' + t[0])
        if not z:
            return
        if l:
            z = z[:l]
        hexdump(z)

    def do_mkdir(self, p):
        print(self.afc.make_directory(p))

    def do_rmdir(self, p):
        return self.afc.remove_directory(p)

    def do_infos(self, p):
        for k, v in self.afc.get_device_infos().items():
            print(k, '\t:\t',v)

    def do_mv(self, p):
        t = p.split()
        return self.afc.file_rename(t[0], t[1])


if __name__ == '__main__':
    parser = ArgumentParser(description='AFC Shell')
    parser.add_argument('--debug', '-d', action='store_true', help='Show debug logging')
    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s %(lineno)d %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    ipod = iPod.find()
    shell = iPodShell(ipod)
    shell.cmdloop(f'Interactive iPod Session - Connected to: {ipod}')
