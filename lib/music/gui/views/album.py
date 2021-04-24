"""
View: Album + track tag values.  Allows editing, after which the view transitions to the diff view.

:author: Doug Skrypa
"""

from concurrent import futures
from dataclasses import fields
from itertools import chain
from pathlib import Path

from PySimpleGUI import Text, HorizontalSeparator, Column, Button, popup_get_text

from ds_tools.fs.paths import get_user_cache_dir
from ...files.album import AlbumDir
from ...manager.update import AlbumInfo, TrackInfo
from ..constants import LoadingSpinner
from ..progress import Spinner
from .base import event_handler, RenderArgs, Event, EventData
from .formatting import AlbumBlock
from .main import MainView
from .popups.simple import popup_ok
from .utils import split_key, DarkInput as Input

__all__ = ['AlbumView']


class AlbumView(MainView, view_name='album'):
    back_tooltip = 'Go back to edit'

    def __init__(self, album: AlbumDir, album_block: AlbumBlock = None, editing: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.album = album
        self.album_block = album_block or AlbumBlock(self, self.album)
        self.album_block.view = self
        self.editing = editing
        self.binds['<Control-w>'] = 'wiki_update'
        self.binds['<Control-e>'] = 'edit'
        self._image_path = None

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        ele_binds = {}
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout = [
                [Text('Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))],
                [HorizontalSeparator()],
            ]
            spinner.update()
            bkw = {'size': (18, 1)}
            view_buttons = [
                Button('Edit', key='edit', **bkw),
                Button('View All Tags', key='all_tags', **bkw),
                Button('Wiki Update', key='wiki_update', **bkw),
            ]
            edit_buttons = [Button('Review & Save Changes', key='save', **bkw), Button('Cancel', key='cancel', **bkw)]
            album_data_rows, album_binds = self.album_block.get_album_data_rows(self.editing)
            ele_binds.update(album_binds)
            album_data = [
                Column([[self.album_block.cover_image_thumbnail()]], key='col::album_cover'),
                Column(album_data_rows, key='col::album_data'),
            ]
            album_buttons = [
                Column([view_buttons], key='col::view_buttons', visible=not self.editing),
                Column([edit_buttons], key='col::edit_buttons', visible=self.editing),
            ]
            alb_col = [album_data, [HorizontalSeparator()], album_buttons]
            album_container = Column(
                alb_col, vertical_alignment='top', element_justification='center', key='col::album_container'
            )
            track_rows = list(chain.from_iterable(tb.as_info_rows(self.editing) for tb in spinner(self.album_block)))
            track_data = Column(
                track_rows, key='col::track_data', size=(685, 690), scrollable=True, vertical_scroll_only=True
            )
            data_col = Column([[album_container, track_data]], key='col::all_data', justification='center', pad=(0, 0))
            layout.append([data_col])

        workflow = self.as_workflow(
            layout, back_tooltip='Cancel Changes', next_tooltip='Review & Save Changes', visible=self.editing
        )
        full_layout.append(workflow)

        return full_layout, kwargs, ele_binds

    def toggle_editing(self):
        self.editing = not self.editing
        always_ro = {'val::album::mp4'}
        for key, ele in self.window.key_dict.items():
            if isinstance(key, str) and key.startswith(('val::', 'add::')) and key not in always_ro:
                ele.update(disabled=not self.editing)

        self.window['col::view_buttons'].update(visible=not self.editing)
        self.window['col::edit_buttons'].update(visible=self.editing)
        self.window['btn::back'].update(visible=self.editing)
        self.window['btn::next'].update(visible=self.editing)

    def handle_event(self, event: Event, data: EventData):
        if not self.editing and (event == 'btn::back' or event == 'btn::next'):
            return None
        elif event.startswith('add::'):
            data['listbox_key'] = event.replace('add::', 'val::', 1)
            key_type, obj, field = split_key(event)
            data.update(object=obj, field=field)
            event = 'add_field_value'

        return super().handle_event(event, data)

    @event_handler
    def add_field_value(self, event: Event, data: EventData):
        obj = data['object']  # album or a track path
        field = data['field']

        obj_str = 'the album' if obj == 'album' else Path(obj).name
        new_value = popup_get_text(f'Enter a new {field} value to add to {obj_str}', title=f'Add {field}')
        if new_value is not None:
            new_value = new_value.strip()
        if not new_value:
            return

        if (album_info := self.album_block._new_album_info) is None:  # can't update listbox size without re-draw
            self.log.debug('Copying album_info to provide new field values...')
            album_info = self.album_block.album_info.copy()
            self.album_block.album_info = album_info

        info_obj = album_info if obj == 'album' else album_info.tracks[obj]
        if field == 'genre':
            self.log.debug(f'Adding genre={new_value!r} to {info_obj}')
            info_obj.add_genre(new_value)
            self.render()
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

        return AllTagsView(self.album, self.album_block, last_view=self)

    @event_handler('btn::back')
    def cancel(self, event: Event, data: EventData):
        self.editing = False
        self.album_block.reset_changes()
        self.render()

    @event_handler('Edit')
    def edit(self, event: Event, data: EventData):
        if not self.editing:
            self.toggle_editing()

    @event_handler('btn::next')
    def save(self, event: Event, data: EventData):
        from .diff import AlbumDiffView

        self.toggle_editing()
        info_dict = {}
        info_dict['tracks'] = track_info_dict = {}
        info_fields = {f.name: f for f in fields(AlbumInfo)} | {f.name: f for f in fields(TrackInfo)}

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
                        track_info_dict.setdefault(obj, {})[field] = value

        if self._image_path:
            info_dict['cover_path'] = self._image_path.as_posix()

        album_info = AlbumInfo.from_dict(info_dict)
        return AlbumDiffView(self.album, album_info, self.album_block, last_view=self)

    def _get_cover_images(self) -> dict[str, bytes]:
        urls = self.album_block.wiki_image_urls
        client = self.album_block.wiki_client
        images = {}
        with Spinner(LoadingSpinner.blue_dots, message='Downloading images...') as spinner:
            with futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_objs = {executor.submit(client.get_image, title): title for title in urls}
                for future in futures.as_completed(future_objs):
                    title = future_objs[future]
                    images[title] = future.result()
                    spinner.update()

        return images

    @event_handler
    def replace_image(self, event: Event, data: EventData):
        if not self.editing:
            self.toggle_editing()

        from .popups.choose_image import choose_image

        client = self.album_block.wiki_client
        images = self._get_cover_images()
        if title := choose_image(images):
            cover_dir = Path(get_user_cache_dir('music_manager/cover_art'))
            name = title.split(':', 1)[1] if title.lower().startswith('file:') else title
            path = cover_dir.joinpath(name)
            if not path.is_file():
                img_data = client.get_image(title)
                with path.open('wb') as f:
                    f.write(img_data)
            self._image_path = path
            self.window['val::album::cover_path'].update(path.as_posix())
