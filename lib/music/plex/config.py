"""
Plex Config
"""

from __future__ import annotations

import logging
from configparser import NoSectionError
from pathlib import Path
from typing import TYPE_CHECKING, Type, Any, Optional, Union, Callable

from plexapi import DEFAULT_CONFIG_PATH, PlexConfig as PlexApiConfig
from plexapi.myplex import MyPlexAccount

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin
from ds_tools.output.color import colored

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

    def get_value(self, instance: PlexConfig, allow_temp: bool = True) -> Any:
        section, key = self.section, self.key
        if allow_temp:
            try:
                return instance._temp_overrides[(section, key)]
            except KeyError:
                pass
        if '.' in section:
            return instance._config.data.get(section, {}).get(key)
        return instance._config.get(f'{section}.{key}')

    def prompt_for_value(self, instance: PlexConfig) -> Any:
        prompt = f'Please enter your Plex {colored(self.name, 11)}: '
        try:
            value = get_input(prompt, parser=lambda s: s.strip() if s else s)
        except EOFError as e:
            raise RuntimeError('Unable to read stdin (this is often caused by piped input)') from e
        if not value:
            raise ValueError(f'Invalid {self.name}')
        self.set_value(instance, value)
        return value

    def set_value(self, instance: PlexConfig, value: Any):
        """Save a new value for this config option.  If a temporary override existed, it will be cleared."""
        section, key = self.section, self.key
        try:
            del instance._temp_overrides[(section, key)]
        except KeyError:
            pass
        cfg = instance._config
        try:
            cfg.set(section, key, value)
        except NoSectionError:
            cfg.add_section(section)
            cfg.set(section, key, value)

        instance.save()

    def set_temp_value(self, instance: PlexConfig, value: Any):
        instance._temp_overrides[(self.section, self.key)] = value

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
        old_value = self.get_value(instance, False)
        if old_value and value:
            old, new = colored(repr(old_value), 9), colored(repr(value), 10)
            config_loc = colored(instance.path, 11)
            if get_input(f'Found {self.name}={old} in {config_loc} - overwrite with {self.name}={new}?'):
                self.set_value(instance, value)
            else:
                self.set_temp_value(instance, value)
        elif value:
            self.set_value(instance, value)
        elif not old_value and not value and self.required(instance):
            self.prompt_for_value(instance)

    def __delete__(self, instance: PlexConfig):
        section, key = self.section, self.key
        try:
            del instance._temp_overrides[(section, key)]
        except KeyError:  # If it wasn't in temp overrides, then it should be removed from the file
            instance._config.remove_option(section, key)
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
        self._temp_overrides = {}  # Overrides that should be used, but not saved
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
