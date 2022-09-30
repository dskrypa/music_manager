"""
Plex Config
"""

from __future__ import annotations

import logging
from configparser import NoSectionError
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Type, Any, Optional, Union, Callable

from plexapi import DEFAULT_CONFIG_PATH, PlexConfig as PlexApiConfig
from plexapi.myplex import MyPlexAccount

from ds_tools.caching.mixins import ClearableCachedPropertyMixin

from ..common.prompts import get_input, getpass, UIMode

if TYPE_CHECKING:
    from .typing import PathLike

__all__ = ['config', 'PlexConfig', 'ConfigEntry']
log = logging.getLogger(__name__)

_NotSet = object()


class ConfigEntry:
    __slots__ = ('section', 'key', 'name', 'type', 'default', '_required', 'inverse')

    def __init__(
        self,
        section: str,
        key: str,
        name: str = None,
        type: Callable = None,  # noqa
        default: Any = _NotSet,
        required: Union[bool, ConfigEntry] = False,
        inverse: bool = False,
    ):
        self.section = section
        self.key = key
        self.name = name or key
        self.type = type
        self.default = default
        self._required = required
        self.inverse = inverse

    def __set_name__(self, owner: Type[PlexConfig], name: str):
        owner._FIELDS.add(name)

    def required(self, instance: PlexConfig) -> bool:
        required = self._required
        if not isinstance(required, ConfigEntry):
            return required
        required = required.__get__(instance, instance.__class__)
        return not required if self.inverse else required

    def get_value(self, instance: PlexConfig) -> Any:
        if '.' in self.section:
            return instance._config.data.get(self.section, {}).get(self.key)
        return instance._config.get(f'{self.section}.{self.key}')

    def prompt_for_value(self, instance: PlexConfig) -> Any:
        try:
            value = get_input(f'Please enter your Plex {self.name}: ', parser=lambda s: s.strip() if s else s)
        except EOFError as e:
            raise RuntimeError('Unable to read stdin (this is often caused by piped input)') from e
        if not value:
            raise ValueError(f'Invalid {self.name}')
        self.set_value(instance, value)
        return value

    def set_value(self, instance: PlexConfig, value: Any):
        cfg = instance._config
        try:
            cfg.set(self.section, self.key, value)
        except NoSectionError:
            cfg.add_section(self.section)
            cfg.set(self.section, self.key, value)

        instance.save()

    def __get__(self, instance: Optional[PlexConfig], owner: Type[PlexConfig]):
        if instance is None:
            return self
        value = self.get_value(instance)
        if not value and self.required(instance):
            value = self.prompt_for_value(instance)
        if not value and self.default is not _NotSet:
            value = self.default
        elif value and self.type is not None:
            value = self.type(value)
        return value

    def __set__(self, instance: PlexConfig, value: Any):
        old_value = self.get_value(instance)
        if old_value and value:
            if get_input(f'Found {self.name}={old_value!r} in {instance.path} - overwrite with {self.name}={value!r}?'):
                self.set_value(instance, value)
        elif not old_value and not value and self.required(instance):
            self.prompt_for_value(instance)

    def __delete__(self, instance: PlexConfig):
        instance._config.remove_option(self.section, self.key)
        instance.save()


class PlexConfig(ClearableCachedPropertyMixin):
    _FIELDS = set()

    # Connection Info
    url: str = ConfigEntry('auth', 'server_baseurl', 'server url', required=True)
    _token: Optional[str] = ConfigEntry('auth', 'server_token')
    user: Optional[str] = ConfigEntry('auth', 'myplex_username', 'username', required=_token, inverse=True)  # noqa

    #: Local mount point for Plex server media that matches the root for media paths as reported by Plex
    server_root: Optional[Path] = ConfigEntry('custom', 'server_path_root', type=Path)

    # Primary Library Section Names
    music_lib_name: str = ConfigEntry('custom', 'music_lib_name', default='Music')
    tv_lib_name: str = ConfigEntry('custom', 'tv_lib_name', default='TV Shows')
    movies_lib_name: str = ConfigEntry('custom', 'movies_lib_name', default='Movies')

    # Plex DB Retrieval Info
    db_ssh_key_path: Optional[Path] = ConfigEntry('custom.db', 'ssh_key_path', type=lambda p: Path(p).expanduser())
    db_remote_dir: Optional[Path] = ConfigEntry('custom.db', 'remote_db_dir')
    db_remote_user: Optional[str] = ConfigEntry('custom.db', 'remote_user')
    db_remote_host: Optional[str] = ConfigEntry('custom.db', 'remote_host')

    def __init__(self, path: PathLike = DEFAULT_CONFIG_PATH, dry_run: bool = False):
        self.load(path, dry_run)

    def save(self):
        log.debug(f'Saving Plex config to {self.path.as_posix()}')
        with self.path.open('w', encoding='utf-8') as f:
            self._config.write(f)

    def load(self, path: Optional[PathLike], dry_run: bool = None):
        if dry_run is not None:
            self.dry_run = dry_run  # noqa
        if path is not None:
            self.path = Path(path).expanduser().resolve()  # noqa
            self.clear_cached_properties()

    def update(self, path: Optional[PathLike], dry_run: bool = None, **kwargs):
        self.load(path, dry_run)
        if bad := ', '.join(map(repr, (k for k in kwargs if k not in self._FIELDS))):
            raise KeyError(f'Invalid config keys: {bad}')
        for key, val in kwargs.items():
            setattr(self, key, val)

    @cached_property
    def _config(self) -> PlexApiConfig:
        log.debug(f'Reading PlexAPI config from {self.path}')
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.touch()
        return PlexApiConfig(self.path)  # noqa

    @cached_property
    def token(self) -> str:
        if token := self._token:
            return token

        if UIMode.current() == UIMode.GUI:
            prompt = (
                f'Please enter the Plex password for account={self.user}\n'
                f'Note: your password will not be stored - it will only be used to obtain a server token.\n'
                f'That token will be stored in {self.path.as_posix()}'
            )
        else:
            prompt = 'Plex password:'

        if password := getpass(prompt, title='Plex Manager - Authentication Required'):
            account = MyPlexAccount(self.user, password)
            del password
        else:
            raise RuntimeError('Password was not provided')

        self._token = token = account._token
        return token

    def reset_token(self):
        log.debug(f'Deleting old token from config in {self.path.as_posix()}')
        del self._token
        del self.__dict__['token']

    @cached_property
    def primary_lib_names(self) -> dict[str, str]:
        return {'music': self.music_lib_name, 'tv': self.tv_lib_name, 'movies': self.movies_lib_name}


config: PlexConfig = PlexConfig()
