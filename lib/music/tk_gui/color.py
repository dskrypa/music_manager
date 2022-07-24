"""
Tkinter GUI popup: Style

:author: Doug Skrypa
"""

from __future__ import annotations

from colorsys import rgb_to_hls
from typing import Union, Optional

from PIL.ImageColor import getrgb

__all__ = ['color_to_rgb', 'get_hue', 'get_lightness', 'get_saturation', 'pick_fg']

RGB = HSL = tuple[int, int, int]
RGBA = tuple[int, int, int, int]
Color = Union[str, RGB, RGBA]


def color_to_rgb(color: Color) -> Union[RGB, RGBA]:
    if isinstance(color, tuple):
        return color
    try:
        return getrgb(color)
    except ValueError:
        if isinstance(color, str) and len(color) in (3, 4, 6, 8):
            return getrgb(f'#{color}')
        raise


def pick_fg(bg: Optional[Color]) -> Optional[str]:
    if not bg:
        return None
    elif get_lightness(bg) < 0.5:
        return '#ffffff'
    else:
        return '#000000'


def get_hue(color: Color) -> int:
    r, g, b, *a = color_to_rgb(color)
    value = rgb_to_hls(r / 255, g / 255, b / 255)[0]
    return round(value * 360)


def get_lightness(color: Color) -> float:
    r, g, b, *a = color_to_rgb(color)
    return rgb_to_hls(r / 255, g / 255, b / 255)[1]


def get_saturation(color: Color) -> float:
    r, g, b, *a = color_to_rgb(color)
    return rgb_to_hls(r / 255, g / 255, b / 255)[2]
