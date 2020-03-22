
from pathlib import Path
from setuptools import setup

project_root = Path(__file__).resolve().parent

with project_root.joinpath('requirements.txt').open('r', encoding='utf-8') as f:
    requirements = f.read().splitlines()

with project_root.joinpath('readme.rst').open('r', encoding='utf-8') as f:
    long_description = f.read()


setup(
    name='music_manager',
    version='2020.03.22-3',
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
)
