"""
View: Album + track tag values.  Allows editing, after which the view transitions to the diff view.

:author: Doug Skrypa
"""

import threading
from dataclasses import fields
# from functools import partial
from itertools import chain
from pathlib import Path
from tkinter import Frame, Listbox as TkListbox

from PySimpleGUI import Text, HorizontalSeparator, Column, Button, Listbox

from ds_tools.utils.misc import num_suffix
from ...common.ratings import stars_to_256
from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ...manager.update import AlbumInfo, TrackInfo
from ...text.extraction import split_enclosed
from ..base_view import event_handler, RenderArgs, Event, EventData
from ..elements.inputs import ExtInput
from ..popups.path_prompt import get_directory
from ..popups.simple import popup_ok, popup_input_invalid
from ..popups.text import popup_error, popup_get_text
from ..progress import Spinner
# from ..utils import update_color
from .formatting import AlbumFormatter
from .main import MainView
from .utils import split_key

__all__ = ['AlbumView']


class AlbumView(MainView, view_name='album'):
    back_tooltip = 'Go back to edit'
    # _log_clicks = True

    # TODO: Undo/redo?
    # TODO: Find/replace
    def __init__(self, album: AlbumDir, album_formatter: AlbumFormatter = None, editing: bool = False, **kwargs):
        super().__init__(expand_on_resize=['col::all_data', 'col::album_container', 'col::track_data'], **kwargs)
        self._edit_event = threading.Event()
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

    @property
    def editing(self) -> bool:
        return self._edit_event.is_set()

    @editing.setter
    def editing(self, value: bool):
        if value:
            self._edit_event.set()
        else:
            self._edit_event.clear()

    def _prepare_button_rows(self):
        bkw = {'size': (18, 1)}
        view_button_rows = [
            [
                Button('Clean & Add BPM', key='clean', **bkw),
                Button('View All Tags', key='all_tags', **bkw),
                Button('Edit', key='edit', **bkw),
                Button('Wiki Update', key='wiki_update', **bkw),
            ],
            [
                Button('Sync Ratings From...', key='sync_ratings::dst_album', **bkw),
                Button('Sync Ratings To...', key='sync_ratings::src_album', **bkw),
                Button('Copy Tags From...', key='copy_data', **bkw),
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
        album_data = [
            Column([[self.album_formatter.cover_image_thumbnail]], key='col::album_cover'),
            Column(self.album_formatter.get_album_data_rows(self.editing), key='col::album_data'),
        ]
        spinner.update()
        alb_col_rows = [album_data, [HorizontalSeparator()], *self._prepare_button_rows()]
        album_column = Column(
            alb_col_rows, vertical_alignment='top', element_justification='center', key='col::album_container'
        )
        return album_column

    def _prepare_track_column(self, spinner: Spinner):
        track_rows = list(chain.from_iterable(tb.as_info_rows(self.editing) for tb in spinner(self.album_formatter)))
        win_w, win_h = self._window_size
        size = (max(685, win_w - 1010), win_h - 60)
        return Column(track_rows, key='col::track_data', size=size, scrollable=True, vertical_scroll_only=True)

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        with Spinner() as spinner:
            album_path = self.album.path.as_posix()
            layout = [
                [Text('Album Path:'), ExtInput(album_path, disabled=True, size=(150, 1), path=album_path)],
                [HorizontalSeparator()]
            ]
            album_column = self._prepare_album_column(spinner)
            track_column = self._prepare_track_column(spinner)
            data_col = Column([[album_column, track_column]], key='col::all_data', justification='center', pad=(0, 0))
            layout.append([data_col])

        workflow = self.as_workflow(
            layout,
            back_tooltip='Cancel Changes' if self.editing else 'View previous album',
            next_tooltip='Review & Save Changes' if self.editing else 'View next album',
            back_visible=bool(self.editing or self._album_index),
            next_visible=bool(self.editing or self._album_index < len(self._albums) - 1),
        )
        full_layout.append(workflow)

        return full_layout, kwargs

    def post_render(self):
        super().post_render()
        if self.editing:
            self._configure_tk_binds()

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

        self._configure_tk_binds()

    def _configure_tk_binds(self):
        if self.editing:
            self.window.TKroot.bind('<Button-1>', _handle_click)
        else:
            self.window.TKroot.unbind('<Button-1>')

    def _flip_name_parts(self, key):
        element = self.window[key]  # type: ExtInput  # noqa
        try:
            a, b = split_enclosed(element.value, maxsplit=1)
        except ValueError:
            popup_error(f'Unable to split {element.value}')
        else:
            element.update(f'{b} ({a})')

    # def _register_validation_failed(self, key: str, element=None):
    #     element = element or self.window[key]
    #     self._failed_validation[key] = (element, element.Widget.cget('fg'), element.Widget.cget('bg'))
    #     if isinstance(element, ExtInput):
    #         element.validated(False)
    #     else:
    #         update_color(element, '#FFFFFF', '#781F1F')
    #
    #     element.TKEntry.bind('<Key>', partial(self._edited_field, key))
    #
    # def _edited_field(self, key: str, event):
    #     self.log.debug(f'_edited_field({key=}, {event=})')
    #     if failed := self._failed_validation.pop(key, None):
    #         element, orig_fg, orig_bg = failed
    #         element.TKEntry.unbind('<Key>')
    #         update_color(element, orig_fg, orig_bg)

    @event_handler('Add Image')
    def replace_image(self, event: Event, data: EventData):
        if not self.editing:
            self.toggle_editing()

        if path := self.album_formatter.get_wiki_cover_choice():
            self.window['val::album::cover_path'].update(path.as_posix())
            self.window['img::album::cover-thumb'].image = path

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
            indexes = list(ele.get_indexes())
            values = ele.Values or []
            values.append(new_value)
            indexes.append(len(values) - 1)
            ele.update(values, set_to_index=indexes)
            list_box = ele.TKListbox  # type: TkListbox
            height = list_box.cget('height')
            if (val_count := len(values)) and val_count != height:
                list_box.configure(height=val_count)
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

    @event_handler('Edit')
    def edit(self, event: Event, data: EventData):
        if not self.editing:
            self.toggle_editing()

    @event_handler
    def cancel(self, event: Event, data: EventData):
        self.editing = False
        self.album_formatter.reset_changes()
        self.render()

    @event_handler
    def ctrl_left(self, event: Event, data: EventData):
        if not isinstance(self.window.find_element_with_focus(), ExtInput):
            super().ctrl_left(event, data)

    @event_handler
    def ctrl_right(self, event: Event, data: EventData):
        if not isinstance(self.window.find_element_with_focus(), ExtInput):
            super().ctrl_right(event, data)

    # region Switch View Handlers

    @event_handler('btn::back')
    def go_back(self, event: Event, data: EventData):
        if self.editing:
            return self.cancel('cancel', data)
        else:
            return AlbumView(AlbumDir(self._albums[self._album_index - 1]), last_view=self)

    @event_handler('btn::next')
    def go_next(self, event: Event, data: EventData):
        if self.editing:
            return self.save('save', data)
        else:
            return AlbumView(AlbumDir(self._albums[self._album_index + 1]), last_view=self)

    @event_handler
    def save(self, event: Event, data: EventData):
        from .diff import AlbumDiffView

        self.toggle_editing()
        info_dict = {}
        info_dict['tracks'] = track_info_dict = {}
        info_fields = {f.name: f for f in fields(AlbumInfo)} | {f.name: f for f in fields(TrackInfo)}

        # TODO: On manual edit of number/type, auto update numbered type
        failed = []
        for data_key, value in data.items():
            # self.log.debug(f'Processing {data_key=} {value=}')
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
                self.window[key].validated(False)  # noqa  # only Rating elements are validated right now
                # self._register_validation_failed(key)
                popup_error(message, multiline=True, auto_size=True)
            return

        if self._image_path:
            info_dict['cover_path'] = self._image_path.as_posix()

        album_info = AlbumInfo.from_dict(info_dict)
        if album_info.number and album_info.type and not album_info.numbered_type:
            album_info.numbered_type = f'{album_info.number}{num_suffix(album_info.number)} {album_info.type.real_name}'

        return AlbumDiffView(self.album, album_info, self.album_formatter, last_view=self)

    @event_handler
    def all_tags(self, event: Event, data: EventData):
        from .tags import AllTagsView

        return AllTagsView(self.album, self.album_formatter, last_view=self)

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

    @event_handler
    def copy_data(self, event: Event, data: EventData):
        from .diff import AlbumDiffView

        if self.editing:
            self.toggle_editing()

        prompt = f'Select data source for {self.album.name}'
        last_dir = self._get_last_dir('sync_src')
        if path := get_directory(prompt, no_window=True, initial_folder=last_dir):
            try:
                album_dir = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=cls.log)  # noqa
                return
            else:
                if path != last_dir:
                    self.config['last_dir:sync_src'] = path.as_posix()
        else:
            return

        src_info = AlbumInfo.from_album_dir(album_dir)
        dst_info = AlbumInfo.from_album_dir(self.album)

        album_fields = tuple(f.name for f in fields(AlbumInfo) if f.name not in ('tracks', '_date', '_type', 'mp4'))
        for field in album_fields:
            setattr(dst_info, field, getattr(src_info, field))

        track_fields = tuple(f.name for f in fields(TrackInfo))
        for src_track, dst_track in zip(src_info.tracks.values(), dst_info.tracks.values()):
            for field in track_fields:
                setattr(dst_track, field, getattr(src_track, field))

        options = {'no_album_move': True, 'add_genre': False}
        return AlbumDiffView(self.album, dst_info, self.album_formatter, last_view=self, options=options)

    # endregion


def can_toggle_editable(key, ele):
    if isinstance(key, str) and key.startswith(('val::', 'add::')) and key != 'val::album::mp4':
        return not isinstance(ele, Text)


def _handle_click(event):
    widget = event.widget
    if isinstance(widget, Frame):
        widget.focus_set()
