"""
Star rating utilities

:author: Doug Skrypa
"""

from typing import Optional, Union

__all__ = ['RATING_RANGES', 'stars', 'stars_from_256', 'stars_to_256', 'star_fill_counts']

Rating = Union[int, float]
RATING_RANGES = [(1, 31, 15), (32, 95, 64), (96, 159, 128), (160, 223, 196), (224, 255, 255)]


def stars(rating: Rating, out_of: int = 10, num_stars: int = 5, chars=('\u2605', '\u2730'), half='\u00BD') -> str:
    filled, half_count, empty = star_fill_counts(rating, out_of, num_stars, half)
    a, b = chars
    return (a * filled) + (half if half_count else '') + (b * empty)


def star_fill_counts(rating: Rating, out_of: int = 10, num_stars: int = 5, half=None) -> tuple[int, int, int]:
    if out_of < 1:
        raise ValueError('out_of must be > 0')

    filled, remainder = map(int, divmod(num_stars * rating, out_of))
    if half and remainder:
        empty = num_stars - filled - 1
        half = 1
    else:
        empty = num_stars - filled
        half = 0
    return filled, half, empty


def stars_from_256(rating: int, out_of: int = 5) -> Optional[int]:
    if not (0 <= rating <= 255):
        raise ValueError(f'{rating=} is outside the range of 0-255')
    elif out_of == 256:
        return int(rating)
    elif out_of not in (5, 10):
        raise ValueError(f'{out_of=} is invalid - must be 5, 10, or 256')
    elif rating == 0:
        return None

    for stars_5, (a, b, c) in enumerate(RATING_RANGES, 1):
        if a <= rating <= b:
            if out_of == 5:
                return stars_5
            a, b, c = RATING_RANGES[stars_5 - 1]
            if stars_5 == 1 and rating < c:
                return 1
            stars_10 = stars_5 * 2
            return stars_10 + 1 if rating > c else stars_10


def stars_to_256(rating: Rating, out_of: int = 5) -> Optional[int]:
    """
    This implementation uses the same values specified in the following link, except for 1 star, which uses 15
    instead of 1: https://en.wikipedia.org/wiki/ID3#ID3v2_rating_tag_issue

    :param rating: The number of stars to set (out of 5/10/256)
    :param out_of: The max value to use for mapping from 0-`out_of` to 0-255.  Only supports 5, 10, and 256.
    :return: The rating mapped to a value between 0 and 255
    """
    if not (0 <= rating <= out_of):
        raise ValueError(f'{rating=} is outside the range of 0-{out_of}')
    elif out_of == 256:
        return int(rating)
    elif out_of not in (5, 10):
        raise ValueError(f'{out_of=} is invalid - must be 5, 10, or 256')
    elif rating == 0:
        return None
    elif (int_rating := int(rating)) == (0 if out_of == 5 else 1):
        return 1
    elif out_of == 5:
        base, extra = int_rating, int(int_rating != rating)
        if extra and int_rating + 0.5 != rating:
            raise ValueError(f'Star ratings {out_of=} must be a multiple of 0.5; invalid value: {rating}')
    else:
        base, extra = divmod(int_rating, 2)

    return RATING_RANGES[base - 1][2] + extra
