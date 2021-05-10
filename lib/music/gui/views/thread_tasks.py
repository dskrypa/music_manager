"""
Utilities for working with a separate work thread where a gui prompt may be created by that thread.

:author: Doug Skrypa
"""

from queue import Empty
from threading import Thread
from typing import Callable

from ..base_view import GuiView
from ..constants import LoadingSpinner
from ..progress import Spinner


def start_task(func: Callable, args=(), kwargs=None, spinner_img=LoadingSpinner.blue_dots, **spin_kwargs):
    with Spinner(spinner_img, **spin_kwargs) as spinner:
        t = Thread(target=func, args=args, kwargs=kwargs)
        t.start()
        t.join(0.05)
        while t.is_alive():
            try:
                future, func, args, kwargs = GuiView.pending_prompts.get(timeout=0.05)
            except Empty:
                pass
            else:
                if future.set_running_or_notify_cancel():
                    try:
                        result = func(*args, **kwargs)
                    except Exception as e:
                        future.set_exception(e)
                    else:
                        future.set_result(result)

            spinner.update()
