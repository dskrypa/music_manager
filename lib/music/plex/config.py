"""
Plex Config
"""

from __future__ import annotations

import json
import logging
from configparser import NoSectionError
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Generic, Type, TypeVar

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
T = TypeVar('T')


class ConfigEntry(Generic[T]):
    __slots__ = ('section', 'key', 'name', 'type', 'default', 'default_factory', '_required', 'inverse')

    def __init__(
        self,
        section: str,
        key: str = None,
        name: str = None,
        type: Type[T] | Callable[[Any], T] = None,  # noqa
        default: T = _NotSet,
        default_factory: Callable[[], T] = None,
        required: bool | ConfigEntry = False,
        inverse: bool = False,
    ):
        self.section = section
        self.key = key
        self.name = name or key
        self.type = type
        if default is not _NotSet and default_factory is not None:
            raise ValueError('Cannot mix default and default_factory')
        self.default = default
        self.default_factory = default_factory
        self._required = required
        self.inverse = inverse

    def __set_name__(self, owner: Type[PlexConfig], name: str):
        owner._FIELDS.add(name)
        if self.key is None:
            self.key = name
        if self.name is None:
            self.name = name

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

    def set_value(self, instance: PlexConfig, value: str | None):
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

        # plexapi.config.PlexConfig stores all configs in a redundant `.data` attribute that it populates during
        # initialization, and then uses in `.get()` instead of using the implementation in ConfigParser.  To allow
        # updates without needing to re-load the entire config file, the value needs to be stored in that data attr
        # as well.
        cfg.data.setdefault(section, {})[key] = value
        instance.save()

    def set_temp_value(self, instance: PlexConfig, value: Any):
        instance._temp_overrides[(self.section, self.key)] = value

    def __get__(self, instance: PlexConfig | None, owner: Type[PlexConfig]) -> T:
        if instance is None:
            return self

        value = self.get_value(instance)
        if not value and self.required(instance):
            value = self.prompt_for_value(instance)

        if not value:
            if self.default is not _NotSet:
                return self.default
            elif self.default_factory is not None:
                return self.default_factory()
        elif self.type is not None:  # Implied: value is truthy
            return self.type(value)

        return value

    def __set__(self, instance: PlexConfig, value: T):
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


class JsonConfigEntry(ConfigEntry):
    __slots__ = ()

    def get_value(self, instance: PlexConfig, allow_temp: bool = True) -> Any:
        raw_value = super().get_value(instance, allow_temp)
        if raw_value is not None:
            return json.loads(raw_value)
        return raw_value

    def __set__(self, instance: PlexConfig, value: T):
        if isinstance(value, set):
            value = sorted(value)
        self.set_value(instance, json.dumps(value, ensure_ascii=False))


class PlexConfig(ClearableCachedPropertyMixin):
    _FIELDS = set()

    # Connection Info
    url: str = ConfigEntry('auth', 'server_baseurl', 'server url', required=True)
    _token: str | None = ConfigEntry('auth', 'server_token')
    user: str | None = ConfigEntry('auth', 'myplex_username', 'username', required=_token, inverse=True)  # noqa

    #: Local mount point for Plex server media that matches the root for media paths as reported by Plex
    server_root: Path | None = ConfigEntry('custom', 'server_path_root', type=lambda p: Path(p).expanduser())
    #: Text to strip from track paths when mapping to a locally accessible path
    server_path_strip_prefix: str | None = ConfigEntry('custom')

    # Primary Library Section Names
    music_lib_name: str = ConfigEntry('custom', default='Music')
    tv_lib_name: str = ConfigEntry('custom', default='TV Shows')
    movies_lib_name: str = ConfigEntry('custom', default='Movies')

    #: List of playlists that are synced based on rules in this library
    externally_synced_playlists: set[str] = JsonConfigEntry('custom', type=set, default_factory=set)

    # Plex DB Retrieval Info
    db_ssh_key_path: Path | None = ConfigEntry('custom.db', 'ssh_key_path', type=lambda p: Path(p).expanduser())
    db_remote_dir: Path | None = ConfigEntry('custom.db', 'remote_db_dir')
    db_remote_user: str | None = ConfigEntry('custom.db', 'remote_user')
    db_remote_host: str | None = ConfigEntry('custom.db', 'remote_host')

    def __init__(self, path: PathLike = DEFAULT_CONFIG_PATH, dry_run: bool = False):
        self._temp_overrides = {}  # Overrides that should be used, but not saved
        self.load(path, dry_run)

    def save(self):
        log.debug(f'Saving Plex config to {self.path.as_posix()}')
        with self.path.open('w', encoding='utf-8') as f:
            self._config.write(f)

    def load(self, path: PathLike | None, dry_run: bool = None):
        if dry_run is not None:
            self.dry_run = dry_run  # noqa
        if path is not None:
            self.path = Path(path).expanduser().resolve()  # noqa
            self.clear_cached_properties()

    def update(self, path: PathLike | None, dry_run: bool = None, **kwargs):
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
