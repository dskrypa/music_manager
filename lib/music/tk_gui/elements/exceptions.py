"""
Exceptions related to TK GUI elements.
"""

from ..exceptions import TkGuiException

__all__ = ['ElementGroupError', 'NoActiveGroup', 'BadGroupCombo']


class ElementGroupError(TkGuiException):
    """Exceptions related to grouped Elements"""


class NoActiveGroup(ElementGroupError):
    """Exception raised when there is no active RadioGroup"""


class BadGroupCombo(ElementGroupError):
    """Exception raised when a bad combination of group members/choices are provided"""
