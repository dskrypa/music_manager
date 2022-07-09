#!/usr/bin/env python

from itertools import chain
from pathlib import Path
from setuptools import setup, find_packages

project_root = Path(__file__).resolve().parent
requirements = project_root.joinpath('requirements.txt').read_text('utf-8').splitlines()
long_description = project_root.joinpath('readme.rst').read_text('utf-8')

about = {}
with project_root.joinpath('lib', 'music', '__version__.py').open('r', encoding='utf-8') as f:
    exec(f.read(), about)

optional_dependencies = {
    'dev': ['pre-commit', 'ipython'],   # Development env requirements
    'bpm': [                    # Used for BPM calculation; on Win10 with Python 3.8, requires VS 2019 build tools:
        'aubio',                # https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2019
        'ffmpeg-python',        # Also requires: https://ffmpeg.org/download.html + ffmpeg in PATH
        'numpy',
    ],
    'ipod': ['pypod@ git+https://github.com/dskrypa/pypod'],
    'gui': ['filelock', 'psutil', 'pysimplegui', 'screeninfo', 'lark'],
}
optional_dependencies['ALL'] = sorted(set(chain.from_iterable(optional_dependencies.values())))

script_entry_points = {
    'clock': 'main',
    'gui_music_manager': 'MusicManagerGui.parse_and_run',
    'ipod_shell': 'main',
    'music_manager': 'main',
    'plex_manager': 'PlexManager.parse_and_run',
    'plex_manager_gui': 'PlexManagerGui.parse_and_run',
}


setup(
    name=about['__title__'],
    version=about['__version__'],
    author=about['__author__'],
    author_email=about['__author_email__'],
    description=about['__description__'],
    long_description=long_description,
    url=about['__url__'],
    project_urls={'Source': about['__url__']},
    packages=find_packages('lib'),
    package_dir={'': 'lib'},
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',  # Due to use of match/case
    ],
    python_requires='~=3.10',
    install_requires=requirements,
    extras_require=optional_dependencies,
    entry_points={'console_scripts': [f'{m}=music.cli.{m}:{f}' for m, f in script_entry_points.items()]},
)
