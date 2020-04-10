
from pathlib import Path
from setuptools import setup

project_root = Path(__file__).resolve().parent

with project_root.joinpath('requirements.txt').open('r', encoding='utf-8') as f:
    requirements = f.read().splitlines()

with project_root.joinpath('readme.rst').open('r', encoding='utf-8') as f:
    long_description = f.read()

optional_dependencies = {
    'bpm': [                    # Used for BPM calculation; on Win10 with Python 3.8, requires VS 2019 build tools:
        'aubio',                # https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2019
        'ffmpeg-python'         # Also requires: https://ffmpeg.org/download.html
    ],
}

setup(
    name='music_manager',
    version='2020.04.10',
    author='Doug Skrypa',
    author_email='dskrypa@gmail.com',
    description='Music Manager',
    long_description=long_description,
    url='https://github.com/dskrypa/music_manager',
    packages=['lib/music_manager'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',    # Due to use of walrus operator
    ],
    python_requires='~=3.8',
    install_requires=requirements,
    extras_require=optional_dependencies
)
