
import logging
from typing import Iterable

from pypod.shell.argparse import ShellArgParser
from pypod.shell.commands.base import ShellCommand

from ds_tools.output import Table, SimpleColumn
from .constants import ID3_TAG_DISPLAY_NAME_MAP
from .files.track.track import SongFile
from .files.track.utils import tag_repr

log = logging.getLogger(__name__)


class TrackTags(ShellCommand, cmd='tags'):
    parser = ShellArgParser('tags', description='Print music file tag info')
    parser.add_argument('file', nargs='+', help='One or more files for which tag info should be printed')

    def __call__(self, file: Iterable[str]):
        tbl = Table(SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Value'), update_width=True)
        rows = []
        for path in self._rel_paths(file, False, True):
            music_file = SongFile(path)
            for tag, val in sorted(music_file.tags.items()):
                if len(tag) > 4:
                    tag = tag[:4]
                rows.append(
                    {'Tag': tag, 'Tag Name': ID3_TAG_DISPLAY_NAME_MAP.get(tag, '[unknown]'), 'Value': tag_repr(val)}
                )

        if rows:
            tbl.print_rows(rows)
