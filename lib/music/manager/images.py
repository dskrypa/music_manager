"""
Utilities for extracting and adding cover art.

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Union

from PIL import Image

from ds_tools.fs.paths import Paths
from ..files.album import iter_album_dirs, AlbumDir
from ..files.exceptions import TagException
from ..files.paths import sanitize_path
from ..files.track.track import SongFile

__all__ = ['extract_album_art', 'set_album_art', 'del_album_art']
log = logging.getLogger(__name__)


def extract_album_art(path: Paths, output: Union[Path, str]):
    output = Path(output)
    if not output.parent.exists():
        output.parent.mkdir(parents=True)
    if not output.suffix and not output.exists():
        output.mkdir()

    for i, album_dir in enumerate(iter_album_dirs(path)):
        if i and not output.is_dir():
            raise ValueError(f'When multiple album dirs are provided, output must be a directory - {output} is a file')

        song_file = next(iter(album_dir))  # type: SongFile
        try:
            cover_data, ext = song_file.get_cover_data()
        except (TagException, TypeError) as e:
            log.error(f'Unable to extract album art: {e}')
        else:
            if output.is_dir():
                out_file = output.joinpath(f'{sanitize_path(song_file.tag_album)}.{ext}')
            else:
                out_file = output

            log.info(f'Saving album art to {out_file}')
            with out_file.open('wb') as f:
                f.write(cover_data)


def set_album_art(path: Union[Path, str], image_path: Union[Path, str], max_width: int = 1200, dry_run: bool = False):
    image = Image.open(Path(image_path).expanduser().resolve())
    path = Path(path).expanduser().resolve()
    if path.is_file():
        SongFile(path).set_cover_data(image, dry_run, max_width)
    else:
        AlbumDir(path).set_cover_data(image, dry_run, max_width)


def del_album_art(path: Union[Path, str], dry_run: bool = False):
    path = Path(path).expanduser().resolve()
    if path.is_file():
        SongFile(path).del_cover_tag(True, dry_run)
    else:
        for song_file in AlbumDir(path):
            song_file.del_cover_tag(True, dry_run)
