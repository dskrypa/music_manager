"""
View: Album + track tag values.  Allows editing, after which the view transitions to the diff view.

:author: Doug Skrypa
"""

import webbrowser
from dataclasses import fields
from functools import partial
from itertools import chain
from pathlib import Path
from urllib.parse import quote_plus

from PySimpleGUI import Text, HorizontalSeparator, Column, Button, Listbox
from tkinter import Frame

from ...common.utils import stars
from ...files.album import AlbumDir
from ...files.track.utils import stars_to_256
from ...manager.update import AlbumInfo, TrackInfo
from ..constants import LoadingSpinner
from ..elements.inputs import DarkInput as Input
from ..elements.menu import ContextualMenu
from ..progress import Spinner
from .base import event_handler, RenderArgs, Event, EventData
from .formatting import AlbumFormatter
from .main import MainView
from .popups.simple import popup_ok
from .popups.text import popup_error, popup_get_text
from .utils import split_key, update_color, open_in_file_manager

__all__ = ['AlbumView']


class AlbumView(MainView, view_name='album'):
    back_tooltip = 'Go back to edit'
    search_menu_options = {
        'google': 'Search Google for {selected!r}',
        'kpop.fandom': 'Search kpop.fandom.com for {selected!r}',
        'generasia': 'Search generasia for {selected!r}',
    }

    def __init__(self, album: AlbumDir, album_formatter: AlbumFormatter = None, editing: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.album = album
        self._albums = sorted(self.album.path.parent.iterdir())
        self._album_index = self._albums.index(self.album.path)
        self.album_formatter = album_formatter or AlbumFormatter(self, self.album)
        self.album_formatter.view = self
        self.editing = editing
        self.binds['<Control-w>'] = 'wiki_update'
        self.binds['<Control-e>'] = 'edit'
        self._image_path = None
        self._failed_validation = {}
        self._rating_callback_names = {}

    def _prepare_button_rows(self):
        bkw = {'size': (18, 1)}
        view_button_rows = [
            [
                Button('Clean & Add BPM', key='clean', **bkw),
                Button('View All Tags', key='all_tags', **bkw),
                Button('Wiki Update', key='wiki_update', **bkw),
            ],
            [
                Button('Edit', key='edit', **bkw),
                Button('Sync Ratings From...', key='sync_ratings::dst_album', **bkw),
                Button('Sync Ratings To...', key='sync_ratings::src_album', **bkw),
            ],
        ]
        edit_buttons = [Button('Review & Save Changes', key='save', **bkw), Button('Cancel', key='cancel', **bkw)]
        album_buttons = [
            Column(view_button_rows, key='col::view_buttons', visible=not self.editing, element_justification='center'),
            Column([edit_buttons], key='col::edit_buttons', visible=self.editing),
        ]
        open_button = Button(
            '\U0001f5c1',
            key='select_album',
            font=('Helvetica', 20),
            size=(10, 1),
            tooltip='Open',
            visible=not self.editing,
        )
        return [album_buttons, [open_button]]

    def _prepare_album_column(self, spinner: Spinner):
        spinner.update()
        search_menu = ContextualMenu(_search_for_selection, kw_key_opt_cb_map={'selected': self.search_menu_options})
        album_data_rows, album_binds = self.album_formatter.get_album_data_rows(self.editing, search_menu)
        spinner.update()
        album_data = [
            Column([[self.album_formatter.cover_image_thumbnail()]], key='col::album_cover'),
            Column(album_data_rows, key='col::album_data'),
        ]
        spinner.update()
        alb_col_rows = [album_data, [HorizontalSeparator()], *self._prepare_button_rows()]
        album_column = Column(
            alb_col_rows, vertical_alignment='top', element_justification='center', key='col::album_container'
        )
        return album_column, album_binds

    def _prepare_track_column(self, spinner: Spinner):
        track_rows = list(chain.from_iterable(tb.as_info_rows(self.editing) for tb in spinner(self.album_formatter)))
        return Column(track_rows, key='col::track_data', size=(685, 690), scrollable=True, vertical_scroll_only=True)

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        ele_binds = {}
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            album_path = self.album.path.as_posix()
            open_menu = ContextualMenu(self.open_in_file_manager, {album_path: 'Open in File Manager'})
            layout = [
                [Text('Album Path:'), Input(album_path, disabled=True, size=(150, 1), right_click_menu=open_menu)],
                [HorizontalSeparator()]
            ]
            album_column, album_binds = self._prepare_album_column(spinner)
            track_column = self._prepare_track_column(spinner)
            data_col = Column([[album_column, track_column]], key='col::all_data', justification='center', pad=(0, 0))
            layout.append([data_col])
            ele_binds.update(album_binds)

        workflow = self.as_workflow(
            layout,
            back_tooltip='Cancel Changes' if self.editing else 'View previous album',
            next_tooltip='Review & Save Changes' if self.editing else 'View next album',
            back_visible=bool(self.editing or self._album_index),
            next_visible=bool(self.editing or self._album_index < len(self._albums) - 1),
        )
        full_layout.append(workflow)

        return full_layout, kwargs, ele_binds

    def toggle_editing(self):
        self.editing = not self.editing
        for key, ele in self.window.key_dict.items():
            if can_toggle_editable(key, ele):
                ele.update(disabled=not self.editing)

        self.window['col::view_buttons'].update(visible=not self.editing)
        self.window['col::edit_buttons'].update(visible=self.editing)
        self.window['select_album'].update(visible=not self.editing)

        back_button = self.window['btn::back']
        back_button.update(visible=self.editing or self._album_index)
        back_button.set_tooltip('Cancel Changes' if self.editing else 'View previous album')

        next_button = self.window['btn::next']
        next_button.update(visible=self.editing or self._album_index < len(self._albums) - 1)
        next_button.set_tooltip('Review & Save Changes' if self.editing else 'View next album')

        self._toggle_rating_handlers()
        if self.editing:
            self.window.TKroot.bind('<Button-1>', self._handle_click)
        else:
            self.window.TKroot.unbind('<Button-1>')

    def _handle_click(self, event):
        widget = event.widget
        if isinstance(widget, Frame):
            widget.focus_set()

    def _toggle_rating_handlers(self):
        for track_formatter in self.album_formatter:
            val_key = track_formatter.key_for('val', 'rating')
            star_key = track_formatter.key_for('stars', 'rating')
            rating_ele = self.window[val_key]
            star_ele = self.window[star_key]
            if self.editing:
                star_ele.Widget.bind('<Button-1>', partial(self._handle_star_clicked, val_key, star_key))
                star_ele.Widget.bind('<B1-Motion>', partial(self._handle_star_clicked, val_key, star_key))
                self._rating_callback_names[val_key] = rating_ele.TKStringVar.trace_add(
                    'write', partial(self._handle_rating_edit, val_key, star_key)
                )
            else:
                try:
                    cb_name = self._rating_callback_names.pop(val_key)
                except KeyError:
                    pass
                else:
                    rating_ele.TKStringVar.trace_remove('write', cb_name)
                    star_ele.Widget.unbind('<Button-1>')
                    star_ele.Widget.unbind('<B1-Motion>')

    def _handle_star_clicked(self, val_key: str, star_key: str, event):
        # noinspection PyTypeChecker
        rating_ele = self.window[val_key]  # type: Input
        star_ele = self.window[star_key]
        rating = round(int(100 * event.x / star_ele.Widget.winfo_width()) / 10)
        rating_ele.update(10 if rating > 10 else 0 if rating < 0 else rating)
        rating_ele.validated(True)

    def _handle_rating_edit(self, val_key: str, star_key: str, tk_var_name: str, index, operation: str):
        # noinspection PyTypeChecker
        rating_ele = self.window[val_key]  # type: Input
        star_ele = self.window[star_key]  # type: Text

        if value := rating_ele.TKStringVar.get():
            try:
                value = int(value)
                stars_to_256(value, 10)
            except (ValueError, TypeError) as e:
                rating_ele.validated(False)
                popup_error(f'Invalid rating for track={split_key(val_key)[1]}:\n{e}', multiline=True, auto_size=True)
                value = 0
            else:
                rating_ele.validated(True)
        else:
            rating_ele.validated(True)
            value = 0
        star_ele.update(stars(value))

    @event_handler('add::*')
    def add_field_value(self, event: Event, data: EventData):
        key_type, obj, field = split_key(event)  # obj => album or a track path
        obj_str = 'the album' if obj == 'album' else Path(obj).name
        if not (new_value := popup_get_text(f'Enter a new {field} value to add to {obj_str}', title=f'Add {field}')):
            return

        if (album_info := self.album_formatter._new_album_info) is None:  # can't update listbox size without re-draw
            self.log.debug('Copying album_info to provide new field values...')
            album_info = self.album_formatter.album_info.copy()
            self.album_formatter.album_info = album_info

        info_obj = album_info if obj == 'album' else album_info.tracks[obj]
        if field == 'genre':
            self.log.debug(f'Adding genre={new_value!r} to {info_obj}')
            info_obj.add_genre(new_value)
            ele = self.window.key_dict[f'val::{event[5:]}']  # type: Listbox  # noqa
            values = ele.Values or []
            values.append(new_value)
            ele.update(values)
        else:
            info_fields = {f.name: f for f in fields(info_obj.__class__)}
            try:
                field_obj = info_fields[field]
            except KeyError:
                popup_ok(f'Invalid field to add a value', title='Invalid Field')
                return

            self.log.debug(f'Setting {info_obj}.{field} = {new_value!r}')
            setattr(info_obj, field, new_value)
            self.render()

    @event_handler
    def all_tags(self, event: Event, data: EventData):
        from .tags import AllTagsView

        return AllTagsView(self.album, self.album_formatter, last_view=self)

    @event_handler('Edit')
    def edit(self, event: Event, data: EventData):
        if not self.editing:
            self.toggle_editing()

    @event_handler
    def ctrl_left(self, event: Event, data: EventData):
        if not isinstance(self.window.find_element_with_focus(), Input):
            super().ctrl_left(event, data)

    @event_handler
    def ctrl_right(self, event: Event, data: EventData):
        if not isinstance(self.window.find_element_with_focus(), Input):
            super().ctrl_right(event, data)

    @event_handler('btn::back')
    def go_back(self, event: Event, data: EventData):
        if self.editing:
            self.handle_event('cancel', data)
        else:
            return AlbumView(AlbumDir(self._albums[self._album_index - 1]), last_view=self)

    @event_handler
    def cancel(self, event: Event, data: EventData):
        self.editing = False
        self.album_formatter.reset_changes()
        self.render()

    @event_handler('btn::next')
    def go_next(self, event: Event, data: EventData):
        if self.editing:
            self.handle_event('save', data)
        else:
            return AlbumView(AlbumDir(self._albums[self._album_index + 1]), last_view=self)

    @event_handler
    def save(self, event: Event, data: EventData):
        from .diff import AlbumDiffView

        self.toggle_editing()
        info_dict = {}
        info_dict['tracks'] = track_info_dict = {}
        info_fields = {f.name: f for f in fields(AlbumInfo)} | {f.name: f for f in fields(TrackInfo)}

        failed = []
        for data_key, value in data.items():
            # self.log.debug(f'Processing {data_key=!r}')
            if key_parts := split_key(data_key):
                key_type, obj, field = key_parts
                if key_type == 'val':
                    try:
                        value = info_fields[field].type(value)
                    except (KeyError, TypeError, ValueError):
                        pass
                    if obj == 'album':
                        info_dict[field] = value
                    else:
                        # self.log.debug(f'Processing {key_type=} {obj=} {field=} {value=}')
                        if field == 'rating':
                            if value:
                                try:
                                    stars_to_256(int(value), 10)
                                except ValueError as e:
                                    failed.append((data_key, f'Invalid rating for track={obj}:\n{e}'))
                            else:
                                continue

                        track_info_dict.setdefault(obj, {})[field] = value

        if failed:
            self.toggle_editing()
            for key, message in failed:
                self._register_validation_failed(key)
                popup_error(message, multiline=True, auto_size=True)
            return

        if self._image_path:
            info_dict['cover_path'] = self._image_path.as_posix()

        album_info = AlbumInfo.from_dict(info_dict)
        return AlbumDiffView(self.album, album_info, self.album_formatter, last_view=self)

    def _register_validation_failed(self, key: str):
        element = self.window[key]
        update_color(element, '#FFFFFF', '#781F1F')
        self._failed_validation[key] = element
        element.TKEntry.bind('<Key>', partial(self._edited_field, key))

    def _edited_field(self, key: str, event):
        self.log.debug(f'_edited_field({key=}, {event=})')
        if element := self._failed_validation.pop(key, None):
            element.TKEntry.unbind('<Key>')
            update_color(element, element.TextColor, element.BackgroundColor)

    @event_handler('Add Image')
    def replace_image(self, event: Event, data: EventData):
        if not self.editing:
            self.toggle_editing()

        if path := self.album_formatter.get_wiki_cover_choice():
            self.window['val::album::cover_path'].update(path.as_posix())
            # TODO: Update image data

    @event_handler('sync_ratings::*')
    def sync_ratings(self, event: Event, data: EventData):
        from .rating_sync import SyncRatingsView

        try:
            kwargs = {event.split('::', 1)[1]: self.album}
        except IndexError:
            kwargs = {}
        try:
            return SyncRatingsView(last_view=self, **kwargs)
        except ValueError as e:
            popup_error(str(e))

    @staticmethod
    def open_in_file_manager(key: str, selected: str = None):
        open_in_file_manager(key)


def can_toggle_editable(key, ele):
    if isinstance(key, str) and key.startswith(('val::', 'add::')) and key != 'val::album::mp4':
        return not isinstance(ele, Text)


def _search_for_selection(key: str, selected: str):
    quoted = quote_plus(selected)
    if key == 'kpop.fandom':
        webbrowser.open(f'https://kpop.fandom.com/wiki/Special:Search?scope=internal&query={quoted}')
    elif key == 'google':
        webbrowser.open(f'https://www.google.com/search?q={quoted}')
    elif key == 'generasia':
        url = f'https://www.generasia.com/w/index.php?title=Special%3ASearch&fulltext=Search&search={quoted}'
        webbrowser.open(url)
