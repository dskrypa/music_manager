"""
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tk_gui.popups.style import StylePopup
from tk_gui.options import GuiOptions, BoolOption, PopupOption, ListboxOption, DirectoryOption, SubmitOption

if TYPE_CHECKING:
    from tk_gui import GuiConfig, Layout

__all__ = ['ConfigUpdater']
log = logging.getLogger(__name__)


class ConfigUpdater:
    __slots__ = ('config',)

    def __init__(self, config: GuiConfig):
        self.config = config

    def update(self):
        config = self.config
        log.debug(f'Preparing options view for {config.data=}')
        results = GuiOptions(self.build_layout()).run_popup()
        log.debug(f'Options view {results=}')
        if save := results.pop('save', False):
            config.update(results, ignore_none=True, ignore_empty=True)
        return save, results

    def build_layout(self) -> Layout:
        kwargs = {'label_size': (16, 1), 'size': (30, None)}
        yield from self._window_rows(kwargs)
        yield from self._directory_rows(kwargs)
        rm_kwargs = kwargs | {'extendable': True, 'prompt_name': 'tag to remove'}
        yield [ListboxOption('rm_tags', 'Tags to Remove', self.config.get('rm_tags', []), **rm_kwargs)]
        yield [SubmitOption('save', 'Save')]

    def _window_rows(self, kwargs):
        yield [
            BoolOption('remember_pos', 'Remember Last Window Position', self.config.remember_position),
            BoolOption('remember_size', 'Remember Last Window Size', self.config.remember_size),
        ]
        style_kwargs = kwargs | {'popup_kwargs': {'show_buttons': True}}
        yield [PopupOption('style', 'Style', StylePopup, default=self.config.style, **style_kwargs)]

    def _directory_rows(self, kwargs):
        for kw in ('Input', 'Output', 'Library', 'Archive', 'Skipped'):
            key = f'{kw.lower()}_base_dir'
            yield [DirectoryOption(key, f'{kw} Directory', default=self.config.get(key), **kwargs)]
