"""
This module implements file IO functionality for files that exist on an iPod and are accessed via an AFC client as if
they were native files opened via :func:`open`.

:author: Doug Skrypa
"""

import logging
import struct
from io import UnsupportedOperation, RawIOBase, BufferedReader, BufferedWriter, BufferedRWPair, TextIOWrapper
from typing import TYPE_CHECKING
from weakref import finalize

# noinspection PyPackageRequirements
from pymobiledevice.afc import AFCClient
from pymobiledevice.afc.constants import (
    AFC_FOPEN_RDONLY, AFC_FOPEN_RW, AFC_FOPEN_WRONLY, AFC_FOPEN_WR, AFC_FOPEN_APPEND, AFC_FOPEN_RDAPPEND,
    AFC_OP_READ, AFC_OP_WRITE, AFC_E_SUCCESS
)

from .exceptions import iPodIOException, iPodFileClosed

if TYPE_CHECKING:
    from .path import iPath

__all__ = ['open_ipod_file']
log = logging.getLogger(__name__)

FILE_MODES = {
    'r': AFC_FOPEN_RDONLY,
    'r+': AFC_FOPEN_RW,
    'w': AFC_FOPEN_WRONLY,
    'w+': AFC_FOPEN_WR,
    'a': AFC_FOPEN_APPEND,
    'a+': AFC_FOPEN_RDAPPEND,
}
CAN_READ = (AFC_FOPEN_RDONLY, AFC_FOPEN_RW, AFC_FOPEN_WR, AFC_FOPEN_RDAPPEND)
CAN_WRITE = (AFC_FOPEN_RW, AFC_FOPEN_WRONLY, AFC_FOPEN_WR, AFC_FOPEN_APPEND, AFC_FOPEN_RDAPPEND)
MAXIMUM_READ_SIZE = 1 << 16
MAXIMUM_WRITE_SIZE = 1 << 15


def open_ipod_file(path: 'iPath', mode: str = 'r', encoding=None, newline=None):
    orig_mode = mode
    if mode.endswith('b'):
        encoding = None
        newline = b'\n'
        mode = mode[:-1]
    else:
        encoding = encoding or 'utf-8'
        newline = newline or '\n'
        if mode.endswith('t'):
            mode = mode[:-1]
    try:
        mode = FILE_MODES[mode]
    except KeyError as e:
        raise ValueError(f'Invalid mode={orig_mode}')

    if encoding:
        read = mode in CAN_READ
        write = mode in CAN_WRITE
        if read and write:
            buffered = iBufferedRWPair(iPodIOBase(path, AFC_FOPEN_RDONLY), iPodIOBase(path, mode))
        elif write:
            buffered = iBufferedWriter(iPodIOBase(path, mode))
        else:
            buffered = iBufferedReader(iPodIOBase(path, mode))
        # noinspection PyTypeChecker
        return iTextIOWrapper(buffered, encoding=encoding, newline=newline)
    else:
        return iPodIOBase(path, mode)


class iPodIOBase(RawIOBase):
    def __init__(self, path: 'iPath', mode: int):
        self.encoding = None
        self._mode = mode
        self._path = path
        self._afc = path._ipod.afc  # type: AFCClient
        self._f = self._afc.file_open(path.as_posix(), mode)
        self.__finalizer = finalize(self, self.__close)

    def fileno(self):
        return self._f

    @property
    def closed(self):
        return self._f is None

    def __close(self):
        if not self.closed:
            self._afc.file_close(self._f)
            self._f = None

    def close(self):
        if self.__finalizer.detach():
            self.__close()

    def read(self, size=-1) -> bytes:
        if self.closed:
            raise iPodFileClosed(self._path)
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
        return data

    def write(self, data: bytes):
        if self.closed:
            raise iPodFileClosed(self._path)

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

    def flush(self):
        return None

    def isatty(self):
        return False

    def readable(self):
        return not self.closed and self._mode in CAN_READ

    def writable(self):
        return not self.closed and self._mode in CAN_WRITE

    def seekable(self):
        return True

    def seek(self, offset, whence=0):
        return self._afc.file_seek(self._f, offset, whence)

    def tell(self):
        return self._afc.file_tell(self._f)

    def truncate(self, size=None):
        raise UnsupportedOperation


# noinspection PyUnresolvedReferences
class BufferedIOMixin:
    def read(self, size=-1):
        return self.raw.read(size)

    def write(self, data):
        return self.raw.write(data)

    def readline(self, size=-1):
        return self.raw.readline(size)


class iBufferedReader(BufferedIOMixin, BufferedReader):
    pass


class iBufferedWriter(BufferedIOMixin, BufferedWriter):
    pass


class iBufferedRWPair(BufferedIOMixin, BufferedRWPair):
    pass


class iTextIOWrapper(TextIOWrapper):
    def read(self, size=-1):
        return self.buffer.read(size).decode(self.encoding)

    def write(self, data: str):
        return self.buffer.write(data.encode(self.encoding))

    def readline(self, size=-1):
        return self.buffer.readline(size).decode(self.encoding)
