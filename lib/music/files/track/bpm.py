"""
:author: Doug Skrypa
"""

from __future__ import annotations

from pathlib import Path
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


def get_bpm(path: PathLike, sample_rate: int = 44100, window_size: int = 1024, hop_size: int = 512) -> int:
    if aubio is None:
        raise RuntimeError('aubio and numpy are required to calculate bpm')
    if not isinstance(path, Path):
        path = Path(path)
    if path.suffix == '.wav':
        return _get_bpm(path.as_posix(), sample_rate, window_size, hop_size)

    # This was easier than getting aubio installed on Windows with ffmpeg support built-in
    if ffmpeg is None:
        raise RuntimeError('ffmpeg-python is required to calculate bpm for non-WAV files')

    with TemporaryDirectory() as d:
        temp_path = Path(d).joinpath('temp.wav').as_posix()
        ffmpeg_obj = ffmpeg.input(path.as_posix())
        if sample_rate > 44100:
            ffmpeg_obj = ffmpeg_obj.output(temp_path, ar=44100)  # Aubio was choking on 96000 Hz FLACs
            sample_rate = 44100
        else:
            ffmpeg_obj = ffmpeg_obj.output(temp_path)
        ffmpeg_obj.run(quiet=True, cmd=find_ffmpeg())
        return _get_bpm(temp_path, sample_rate, window_size, hop_size)


def _get_bpm(path: str, sample_rate: int = 44100, window_size: int = 1024, hop_size: int = 512) -> int:
    src = source(path, sample_rate, hop_size, channels=1)
    tempo_obj = tempo('specdiff', window_size, hop_size, src.samplerate)
    beats = [tempo_obj.get_last_s() for samples in src if len(samples) >= hop_size and tempo_obj(samples)]

    if len(beats) < 4:
        raise BPMDetectionError(f'Too few beats found in {path} to determine BPM')

    return int(round(median(60 / diff(beats))))


class BPMDetectionError(Exception):
    """Exception to be raised when BPM could not be determined"""
