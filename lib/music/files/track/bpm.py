"""
:author: Doug Skrypa
"""

from __future__ import annotations

from pathlib import Path
from shutil import copy
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

try:
    import ffmpeg
except ImportError:
    ffmpeg = None
try:
    import aubio
    from aubio import source, tempo  # noqa
    from numpy import median, diff  # noqa
except ImportError:
    aubio = None

from music.common.utils import find_ffmpeg

if TYPE_CHECKING:
    from music.typing import PathLike

__all__ = ['get_bpm', 'BPMDetectionError']


class BpmCalculator:
    __slots__ = ('sample_rate', 'window_size', 'hop_size')

    def __init__(self, sample_rate: int = 44100, window_size: int = 1024, hop_size: int = 512):
        self.sample_rate = sample_rate
        self.window_size = window_size
        self.hop_size = hop_size

    def get_bpm(self, path: PathLike) -> int:
        if aubio is None:
            raise RuntimeError('aubio and numpy are required to calculate bpm')

        if not isinstance(path, Path):
            path = Path(path)

        if path.suffix == '.wav':
            path_str = path.as_posix()
            if path_str.isascii():
                return self._get_bpm(path_str)
            else:
                return self._copy_and_get_bpm(path_str)
        else:
            return self._convert_and_get_bpm(path)

    def _get_bpm(self, path: str) -> int:
        src = source(path, self.sample_rate, self.hop_size, channels=1)
        tempo_obj = tempo('specdiff', self.window_size, self.hop_size, src.samplerate)
        beats = [tempo_obj.get_last_s() for samples in src if len(samples) >= self.hop_size and tempo_obj(samples)]

        if len(beats) < 4:
            raise BPMDetectionError(f'Too few beats found in {path} to determine BPM')

        return int(round(median(60 / diff(beats))))

    def _copy_and_get_bpm(self, path: PathLike) -> int:
        """
        Aubio (as of version 0.4.9) does not seem to support paths containing non-ASCII characters.  Rather than
        renaming files temporarily or creating temporary symlinks, which could be problematic, simply copy the file
        into a temp directory and analyze the temp file.
        """
        with TemporaryDirectory() as d:
            temp_path = Path(d).joinpath('temp.wav').as_posix()
            copy(path, temp_path)
            return self._get_bpm(temp_path)

    def _convert_and_get_bpm(self, path: Path) -> int:
        # This was easier than getting aubio installed on Windows with ffmpeg support built-in
        if ffmpeg is None:
            raise RuntimeError('ffmpeg-python is required to calculate bpm for non-WAV files')

        with TemporaryDirectory() as d:
            temp_path = Path(d).joinpath('temp.wav').as_posix()
            ffmpeg_obj = ffmpeg.input(path.as_posix())
            if self.sample_rate > 44100:
                ffmpeg_obj = ffmpeg_obj.output(temp_path, ar=44100)  # Aubio was choking on 96000 Hz FLACs
                self.sample_rate = 44100
            else:
                ffmpeg_obj = ffmpeg_obj.output(temp_path)
            ffmpeg_obj.run(quiet=True, cmd=find_ffmpeg())
            return self._get_bpm(temp_path)


def get_bpm(path: PathLike, sample_rate: int = 44100, window_size: int = 1024, hop_size: int = 512) -> int:
    return BpmCalculator(sample_rate, window_size, hop_size).get_bpm(path)


class BPMDetectionError(Exception):
    """Exception to be raised when BPM could not be determined"""
