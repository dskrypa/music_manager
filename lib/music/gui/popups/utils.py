"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

import logging
import tkinter
from contextlib import contextmanager

from ..window import Window

__all__ = ['temp_hidden_window']
log = logging.getLogger(__name__)


@contextmanager
def temp_hidden_window(logger: logging.LoggerAdapter = None):
    """
    Creates and destroys a temporary Window similar to the way that FreeSimpleGUI does in
    :func:`popup_get_folder<FreeSimpleGUI.popup_get_folder>` while creating a file prompt. Mostly copied from that func.
    """
    logger = log if logger is None else logger
    if not Window.hidden_master_root:
        # if first window being created, make a throwaway, hidden master root.  This stops one user window from
        # becoming the child of another user window. All windows are children of this hidden window
        Window._IncrementOpenCount()
        Window.hidden_master_root = tkinter.Tk()
        Window.hidden_master_root.attributes('-alpha', 0)  # HIDE this window really really really
        try:
            Window.hidden_master_root.wm_overrideredirect(True)
        except Exception:
            logger.error('* Error performing wm_overrideredirect *', exc_info=True)
        Window.hidden_master_root.withdraw()

    root = tkinter.Toplevel()
    try:
        root.attributes('-alpha', 0)  # hide window while building it. makes for smoother 'paint'
        try:
            root.wm_overrideredirect(True)
        except Exception:
            logger.error('* Error performing wm_overrideredirect *', exc_info=True)
        root.withdraw()
    except Exception:
        pass

    yield root

    root.destroy()
    if Window.NumOpenWindows == 1:
        Window.NumOpenWindows = 0
        Window.hidden_master_root.destroy()
        Window.hidden_master_root = None
