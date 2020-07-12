
import logging
from errno import ENOENT, EINVAL
from functools import cached_property, partialmethod
from pathlib import Path, PurePosixPath
from stat import S_IFDIR, S_IFCHR, S_IFBLK, S_IFREG, S_IFIFO, S_IFLNK, S_IFSOCK
from typing import Union, Optional

from pymobiledevice.afc import AFCClient, AFC_HARDLINK

from .files import open_ipod_file

__all__ = ['iPath']
log = logging.getLogger(__name__)

STAT_MODES = {
    'S_IFDIR': S_IFDIR,
    'S_IFCHR': S_IFCHR,
    'S_IFBLK': S_IFBLK,
    'S_IFREG': S_IFREG,
    'S_IFIFO': S_IFIFO,
    'S_IFLNK': S_IFLNK,
    'S_IFSOCK': S_IFSOCK,
}


class iPath(Path, PurePosixPath):
    __slots__ = ('_ipod',)

    def __new__(cls, *args, ipod=None, **kwargs):
        # noinspection PyUnresolvedReferences
        self = cls._from_parts(args, init=False)
        self._init(ipod)
        return self

    def _init(self, ipod=None, template: Optional['iPath'] = None):
        self._closed = False
        if template is not None:
            self._ipod = template._ipod
            self._accessor = template._accessor
        else:
            if ipod is None:
                ipod = iPod.find()
            self._ipod = ipod
            self._accessor = iPodAccessor(ipod)

    open = partialmethod(open_ipod_file)


def _str(path: Union[Path, str]) -> str:
    if isinstance(path, Path):
        return path.as_posix()
    return path


class iPodAccessor:
    def __init__(self, ipod):
        self.ipod = ipod
        self.afc = ipod.afc  # type: AFCClient

    def stat(self, path):
        if stat_dict := self.afc.get_file_info(_str(path)):
            return iPodStatResult(stat_dict)
        raise FileNotFoundError(ENOENT, f'The system cannot find the file specified')

    lstat = stat

    def listdir(self, path):
        return self.afc.read_directory(_str(path))

    def open(self, *args, **kwargs):
        raise NotImplementedError

    def scandir(self, path):
        if not isinstance(path, iPath):
            path = iPath(path, ipod=self.ipod)
        for sub_path in path.iterdir():
            # noinspection PyTypeChecker
            yield iPodScandirEntry(sub_path.relative_to(path))

    def chmod(self, *args, **kwargs):
        raise NotImplementedError

    lchmod = chmod

    def mkdir(self, path, mode=None, **kwargs):
        return self.afc.make_directory(_str(path))

    def rmdir(self, path):
        return self.afc.remove_directory(_str(path))

    def unlink(self, path):
        return self.afc.file_remove(_str(path))

    def link_to(self, src, dest, **kwargs):
        return self.afc.make_link(_str(src), _str(dest), AFC_HARDLINK)

    def symlink(self, src, dest, **kwargs):
        return self.afc.make_link(_str(src), _str(dest))  # default is symlink

    def rename(self, src, dest, **kwargs):
        return self.afc.file_rename(_str(src), _str(dest))

    replace = rename  # note: os.replace will overwrite the dest if it exists (I guess rename won't?)

    def utime(self, *args, **kwargs):
        raise NotImplementedError

    def readlink(self, path):
        path = _str(path)
        if info := self.afc.get_file_info(path):
            if info['st_ifmt'] == 'S_IFLNK':
                return info['LinkTarget']
            raise OSError(EINVAL, f'Not a link: {path}')
        raise OSError(EINVAL, f'Path does not exist: {path}')


class iPodStatResult:
    def __init__(self, info):
        self._info = info

    def __repr__(self):
        return 'iPodStatResult[{}]'.format(', '.join(f'{k}={getattr(self, k)!r}' for k in sorted(self._info)))

    def __getattr__(self, item: str):
        try:
            value = self._info[item]
        except KeyError:
            raise AttributeError(f'iPodStatResult has no attribute {item!r}') from None

        if item.endswith('time'):
            return int(value) // 1_000_000_000
        else:
            try:
                return int(value)
            except (ValueError, TypeError):
                return value

    @property
    def st_mode(self):
        try:
            return STAT_MODES[self.st_ifmt]
        except KeyError:
            raise AttributeError('Unable to convert {self.st_ifmt=!r} to st_mode')


class iPodScandirEntry:
    def __init__(self, path: iPath):
        self._path = path

    @cached_property
    def path(self):
        return self._path.as_posix()

    @property
    def name(self):
        return self._path.name

    @cached_property
    def _stat(self):
        return self._path.stat()

    def stat(self, *, follow_symlinks=True):
        return self._stat

    def inode(self):
        return None

    def is_dir(self):
        return self._path.is_dir()

    def is_file(self):
        return self._path.is_file()

    def is_symlink(self):
        return self._path.is_symlink()


# Down here due to circular dependency
from .ipod import iPod
