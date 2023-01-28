#!/usr/bin/env python

from importlib import import_module
from pathlib import Path


def import_main(file_name: str, package: str = 'music.cli'):
    module_name = f'{package}.{Path(file_name).stem}'
    try:
        return import_module(module_name).main
    except ImportError:
        import sys
        from os import environ, name
        from site import addsitedir

        ON_WINDOWS = name == 'nt'
        SITE_PKGS = '{}/site-packages'.format('Lib' if ON_WINDOWS else f'lib/python3.{sys.version_info.minor}')
        PROJ_PATH = Path(__file__).resolve().parents[1]
        VENV_PATH = next((p for p in (PROJ_PATH.joinpath(vd) for vd in ('venv', '.venv')) if p.exists()), None)

        if (VIRTUAL_ENV := environ.get('VIRTUAL_ENV')) and (path := Path(VIRTUAL_ENV).joinpath(SITE_PKGS)).exists():
            # A venv is active, but a different interpreter was used, so we need to add the venv's site-packages
            addsitedir(path.as_posix())
        elif VENV_PATH and (path := VENV_PATH.joinpath(SITE_PKGS)).exists():
            addsitedir(path.as_posix())
        elif VENV_PATH:
            from subprocess import call

            bin_path = VENV_PATH.joinpath('Scripts' if ON_WINDOWS else 'bin')
            environ.update(
                PYTHONHOME='', VIRTUAL_ENV=VENV_PATH.as_posix(), PATH=f'{bin_path.as_posix()}:{environ["PATH"]}'
            )
            cmd = [bin_path.joinpath('python.exe' if ON_WINDOWS else 'python').as_posix()] + sys.argv
            sys.exit(call(cmd, env=environ))

        try:
            return import_module(module_name).main
        except ImportError:
            print(f'Unable to run {__file__} due to no active venv - please activate it or create one', file=sys.stderr)
            sys.exit(1)
