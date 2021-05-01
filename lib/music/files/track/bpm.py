"""
:author: Doug Skrypa
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Union

try:
    import ffmpeg
except ImportError:
    ffmpeg = None
try:
    import aubio
    from aubio import source, tempo
    from numpy import median, diff
except ImportError:
    aubio = None

from ...common.utils import find_ffmpeg

__all__ = ['get_bpm', 'BPMDetectionError']


def get_bpm(path: Union[str, Path], sample_rate=44100, window_size=1024, hop_size=512) -> int:
    if aubio is None:
        raise RuntimeError('aubio and numpy are required to calculate bpm')
    if not isinstance(path, Path):
        path = Path(path)

    if path.suffix != '.wav':
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
    else:
        return _get_bpm(path, sample_rate, window_size, hop_size)


def _get_bpm(path: Union[str, Path], sample_rate=44100, window_size=1024, hop_size=512) -> int:
    if isinstance(path, Path):
        path = path.as_posix()

    src = source(path, sample_rate, hop_size, channels=1)
    tempo_obj = tempo('specdiff', window_size, hop_size, src.samplerate)
    beats = [tempo_obj.get_last_s() for samples in src if len(samples) >= hop_size and tempo_obj(samples)]

    if len(beats) < 4:
        raise BPMDetectionError(f'Too few beats found in {path} to determine BPM')
    # noinspection PyTypeChecker
    return int(round(median(60 / diff(beats))))


class BPMDetectionError(Exception):
    """Exception to be raised when BPM could not be determined"""
