
import logging
from weakref import finalize

from pymobiledevice.afc import AFCClient
from pymobiledevice.lockdown import LockdownClient
from pymobiledevice.usbmux import USBMux

from ds_tools.compat import cached_property
from ds_tools.caching import DictAttrProperty

__all__ = ['iPod']
log = logging.getLogger(__name__)


class iPod:
    _instance = None
    name = DictAttrProperty('info', 'DeviceName')
    version = DictAttrProperty('info', 'ProductVersion')

    def __init__(self, udid):
        self.udid = udid
        self.__finalizer = finalize(self, self.__close)

    def __repr__(self):
        return f'<{self.__class__.__name__}[name={self.name!r}, version={self.version}]>'

    @classmethod
    def find(cls) -> 'iPod':
        if cls._instance is None:
            device = USBMux().find_device()
            log.debug(f'Found {device=}')
            cls._instance = cls(device.serial)
        return cls._instance

    @cached_property
    def _lockdown(self):
        client = LockdownClient(self.udid)
        client.startService('com.apple.afc')
        return client

    @cached_property
    def afc(self) -> AFCClient:
        return AFCClient(self._lockdown)

    def close(self):
        if self.__finalizer.detach():
            self.__close()

    def __close(self):
        if 'afc' in self.__dict__:
            log.debug('Stopping afc service...')
            self.afc.stop_session()
            del self.__dict__['afc']
        # if '_lockdown' in self.__dict__:
        #     log.debug('Stopping lockdown client...')
        #     # This always results in an exception; the response seems to always be: {'Request': 'StopSession'}
        #     self._lockdown.stop_session()
        #     del self.__dict__['_lockdown']

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @cached_property
    def info(self):
        return self._lockdown.allValues

    def get_path(self, path: str) -> 'iPath':
        return iPath(path, ipod=self)


# Down here due to circular import
from .path import iPath
