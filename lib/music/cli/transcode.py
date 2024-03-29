"""
Transcode audio files in bulk
"""

import logging
from functools import cached_property
from pathlib import Path
from shutil import copy
from subprocess import check_call
from typing import Iterator

from cli_command_parser import Command, Counter, Positional, Option, ParamGroup, Flag, inputs as i, main
from mutagen import File

from ds_tools.fs.paths import unique_path
from music.files.track.track import SongFile
from music.__version__ import __author_email__, __version__, __author__, __url__  # noqa


log = logging.getLogger(__name__)

BIT_DEPTH_SAMPLE_FMT_MAP = {16: 's16', 24: 's32'}
SAMPLE_RATES = (44_100, 48_000, 88_200, 96_000, 176_400, 192_000, 352_800, 384_000)


class Transcode(Command, description='Transcode FLACs between bit depths and bit rates', error_handler=None):
    src_path: Path = Positional(type=i.Path(type='dir'), help='Input directory containing one or more music files')
    dst_path: Path = Option(
        '--output', '-o', type=i.Path(type='dir', exists=False), help='Output directory (default: based on depth/rate)'
    )
    with ParamGroup(required=True):
        depth: int = Option('-d', choices=BIT_DEPTH_SAMPLE_FMT_MAP, help='Output bit depth')
        rate: int = Option('-r', choices=SAMPLE_RATES, help='Output sample rate (in kHz)')

    verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
    dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')
    no_check = Flag('-C', name_mode='-', help='Do not check bit depth/rate before transcoding')
    out_fmt = Option('-f', choices=('flac', 'mp3', 'wav', 'mp4', 'ogg'), help='Output format (default: same as input)')

    def main(self):
        from ds_tools.logging import init_logging

        init_logging(self.verbose, log_path=None, names=None, millis=True)

        for src_file, dst_file, is_audio in self.process_albums(self.src_path):
            if is_audio and self._should_transcode(src_file, dst_file):
                self._transcode_file(src_file, dst_file)
            else:
                self._copy_file(src_file, dst_file)

    def process_albums(self, src_dir: Path) -> Iterator[tuple[Path, Path, bool]]:
        log.debug(f'Processing src_dir={src_dir.as_posix()}')
        found_album = False
        for path in src_dir.iterdir():
            if path.is_dir():
                found_album = True
                if not any(p.is_dir() for p in path.iterdir()):
                    yield from self.process_album(path)
                else:
                    yield from self.process_albums(path)

        if not found_album:
            yield from self.process_album(src_dir)

    def process_album(self, src_dir: Path) -> Iterator[tuple[Path, Path, bool]]:
        log.debug(f'Processing album dir={src_dir.as_posix()}')
        dst_dir = self._pick_dst_path(src_dir)
        if not self.dry_run and not dst_dir.exists():
            dst_dir.mkdir(parents=True)

        for src_file in src_dir.iterdir():
            dst_file = dst_dir.joinpath(src_file.name)
            if self.out_fmt:
                dst_file = dst_file.with_suffix(f'.{self.out_fmt}')
            is_audio = File(src_file) is not None
            # log.debug(f'{src_file=} {is_audio=}')
            yield src_file, dst_file, is_audio

    def _should_transcode(self, src_file: Path, dst_file: Path) -> bool:
        if self.no_check:
            return True

        track = SongFile(src_file)
        src_bits, src_rate = track.bits_per_sample, track.sample_rate
        dst_bits, dst_rate = self.depth, self.rate

        too_low = src_bits < dst_bits or src_rate < dst_rate
        if too_low:
            log.warning(
                f'Transcoding would result in up-sampling for {src_file.as_posix()}'
                f' - bits per sample={src_bits}, sample rate={src_rate:,d} Hz',
                extra={'color': 'red'},
            )
            return False

        if src_bits == dst_bits and src_rate == dst_rate:
            return src_file.suffix != dst_file.suffix

        return True

    def _copy_file(self, src_file: Path, dst_file: Path):
        prefix = '[DRY RUN] Would copy' if self.dry_run else 'Copying'
        log_src = src_file.relative_to(self.src_path).as_posix()
        log.info(f'{prefix} {log_src} -> {dst_file.as_posix()}')
        if not self.dry_run:
            copy(src_file, dst_file)

    def _transcode_file(self, src_file: Path, dst_file: Path):
        prefix = '[DRY RUN] Would transcode' if self.dry_run else 'Transcoding'
        log_src = src_file.relative_to(self.src_path).as_posix()
        log.info(f'{prefix} {log_src} -> {dst_file.as_posix()}')
        if not self.dry_run:
            command = ['ffmpeg', '-i', src_file.as_posix(), *self.common_args, dst_file.as_posix()]
            check_call(command)

    def _pick_dst_path(self, src_path: Path) -> Path:
        if self.dst_path:
            if src_path == self.src_path:
                return self.dst_path

            rel_path = src_path.relative_to(self.src_path)
            dst_dir = self.dst_path.joinpath(rel_path)
        else:
            dst_dir = src_path.parent

        dst_name = f'{src_path.name} [{self.name_suffix}]'
        return unique_path(dst_dir, dst_name)

    @cached_property
    def name_suffix(self) -> str:
        name_parts = []
        if self.depth:
            name_parts.append(f'{self.depth}b')
        if self.rate:
            name_parts.append(self._format_rate())

        return '-'.join(name_parts)

    def _format_rate(self) -> str:
        khz = self.rate / 1000
        ikhz = int(khz)
        if ikhz == khz:
            return f'{ikhz}kHz'
        return f'{khz:.1f}kHz'

    @cached_property
    def common_args(self) -> list[str]:
        args = []
        if self.depth:
            args += ['-sample_fmt', BIT_DEPTH_SAMPLE_FMT_MAP[self.depth]]
        if self.rate:
            args += ['-ar', str(self.rate)]
        args += ['-c:v', 'copy']
        return args
