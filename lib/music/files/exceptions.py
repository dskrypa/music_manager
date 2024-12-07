"""
:author: Doug Skrypa
"""

__all__ = [
    'InvalidAlbumDir', 'InvalidTagName', 'MusicException', 'TagException', 'TagNotFound', 'TagValueException',
    'UnsupportedTagForFileType', 'BPMCalculationError',
]


class MusicException(Exception):
    """Base Exception class for the music package"""


class TagException(MusicException):
    """Generic exception related to problems with tags"""


class TagNotFound(TagException):
    """Exception to be raised when a given tag cannot be found"""


class TagAccessException(TagException):
    """Exception to be raised when unable to access a given tag"""
    def __init__(self, tag, file_obj):
        self.tag = tag
        self.obj = file_obj


class UnsupportedTagForFileType(TagAccessException):
    """Exception to be raised when attempting to access a tag on an unsupported file type"""
    def __repr__(self):
        fmt = 'Accessing/modifying {!r} tags is not supported on {} because it is a {!r} file'
        return fmt.format(self.tag, self.obj, self.obj.ext)


class InvalidTagName(TagAccessException):
    """Exception to be raised when attempting to retrieve the value for a tag that does not exist"""
    def __repr__(self):
        return 'Invalid tag name {!r} for file {}'.format(self.tag, self.obj)


class TagValueException(TagException):
    """Exception to be raised when a tag with an unexpected value is encountered"""


class InvalidAlbumDir(MusicException):
    """Exception to be raised when an AlbumDir is initialized with an invalid directory"""


class BPMCalculationError(MusicException):
    """Raised when BPM cannot be calculated for a given track"""
