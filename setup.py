
from pathlib import Path
from setuptools import setup

project_root = Path(__file__).resolve().parent

with project_root.joinpath('requirements.txt').open('r', encoding='utf-8') as f:
    requirements = f.read().splitlines()

with project_root.joinpath('readme.rst').open('r', encoding='utf-8') as f:
    long_description = f.read()


setup(
    name='music_manager',
    version='2020.02.15-6',
    author='Doug Skrypa',
    author_email='dskrypa@gmail.com',
    description='Music Manager',
    long_description=long_description,
    url='https://github.com/dskrypa/music_manager',
    packages=['lib/music_manager'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',    # Minimum due to use of f-strings
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
    ],
    python_requires='~=3.5',
    install_requires= requirements
)
