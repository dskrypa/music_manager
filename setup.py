#!/usr/bin/env python

from pathlib import Path
from setuptools import setup

project_root = Path(__file__).resolve().parent

with project_root.joinpath('requirements.txt').open('r', encoding='utf-8') as f:
    requirements = f.read().splitlines()

with project_root.joinpath('readme.rst').open('r', encoding='utf-8') as f:
    long_description = f.read()

about = {}
with project_root.joinpath('lib', 'music', '__version__.py').open('r', encoding='utf-8') as f:
    exec(f.read(), about)

optional_dependencies = {
    'dev': [                                            # Development env requirements
        'pre-commit',
        'ipython',
    ],
    'bpm': [                    # Used for BPM calculation; on Win10 with Python 3.8, requires VS 2019 build tools:
        'aubio',                # https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2019
        'ffmpeg-python'         # Also requires: https://ffmpeg.org/download.html + ffmpeg in PATH
    ],
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
    packages=['lib/music'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',    # Due to use of walrus operator
    ],
    python_requires='~=3.8',
    install_requires=requirements,
    extras_require=optional_dependencies,
)
