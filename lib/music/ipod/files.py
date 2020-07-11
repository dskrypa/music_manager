
import logging
import struct
from typing import TYPE_CHECKING, Union

from pymobiledevice.afc import (
    AFC_FOPEN_RDONLY, AFC_FOPEN_RW, AFC_FOPEN_WRONLY, AFC_FOPEN_WR, AFC_FOPEN_APPEND, AFC_FOPEN_RDAPPEND, AFCClient,
    AFC_OP_READ, AFC_OP_WRITE, AFC_E_SUCCESS
)

from .exceptions import iPodIOException

if TYPE_CHECKING:
    from .ipod import iPod
    from .path import iPath

__all__ = ['iPodFile']
log = logging.getLogger(__name__)

FILE_MODES = {
    'r': AFC_FOPEN_RDONLY,
    'r+': AFC_FOPEN_RW,
    'w': AFC_FOPEN_WRONLY,
    'w+': AFC_FOPEN_WR,
    'a': AFC_FOPEN_APPEND,
    'a+': AFC_FOPEN_RDAPPEND,
}
MAXIMUM_READ_SIZE = 1 << 16
MAXIMUM_WRITE_SIZE = 1 << 15


class iPodFile:
    def __init__(self, path: 'iPath', mode: str = 'r', encoding=None):
        self._path = path
        self._mode = mode
        if mode.endswith('b'):
            self._encoding = None
            mode = mode[:-1]
        else:
            self._encoding = encoding or 'utf-8'
            if mode.endswith('t'):
                mode = mode[:-1]
        try:
            mode = FILE_MODES[mode]
        except KeyError as e:
            raise ValueError(f'Invalid mode={self._mode}')

        self._afc = path._ipod.afc  # type: AFCClient
        self._f = self._afc.file_open(path.as_posix(), mode)

    def read(self, size=-1):
        if size < 0:
            size = self._path.stat().st_size
        data = b''
        while size > 0:
            chunk_size = MAXIMUM_READ_SIZE if size > MAXIMUM_READ_SIZE else size
            self._afc.dispatch_packet(AFC_OP_READ, struct.pack('<QQ', self._f, chunk_size))
            status, chunk = self._afc.receive_data()
            if status != AFC_E_SUCCESS:
                raise iPodIOException(f'Error reading data - {status=!r}')
            size -= chunk_size
            data += chunk
        if self._encoding:
            data = data.decode(self._encoding)
        return data

    def write(self, data: Union[bytes, str]):
        if isinstance(data, str) and self._encoding:
            data = data.encode(self._encoding)

        hh = struct.pack('<Q', self._f)
        pos = 0
        remaining = len(data)
        while remaining:
            size = remaining if remaining < MAXIMUM_WRITE_SIZE else MAXIMUM_WRITE_SIZE
            chunk = data[pos:pos+size]
            self._afc.dispatch_packet(AFC_OP_WRITE, hh + chunk, this_length=48)
            status, chunk = self._afc.receive_data()
            if status != AFC_E_SUCCESS:
                raise iPodIOException(f'Error writing data - {status=!r}')
            remaining -= size

        return len(data)
