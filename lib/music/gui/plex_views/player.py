"""
View: Player

:author: Doug Skrypa
"""

import os
import sys
from base64 import b64encode
from functools import partial
from io import BytesIO
from pathlib import Path
from time import monotonic
from tkinter import Menu, Tk, Event as TkEvent
from typing import Optional, Union
from urllib.parse import urlencode

from plexapi.audio import Track
from plexapi.video import Movie, Episode
from PySimpleGUI import Button, Image, ProgressBar, WIN_CLOSED
try:
    from vlc import Instance, MediaPlayer, Media, EventManager, Event as VlcEvent, EventType
except (FileNotFoundError, OSError) as e:
    raise RuntimeError(
        'VLC Player is not installed, or the 32 bit version is installed and cannot be loaded from a 64 bit program'
    ) from e

from ...plex.server import LocalPlexServer
from ..base_view import event_handler, RenderArgs, Event, EventData
from ..icons import Icons
from ..popups.base import BasePopup
from ..popups.simple import popup_ok
from ..popups.path_prompt import get_file_path
from ..progress import Spinner
from .main import PlexView, DEFAULT_CONFIG

__all__ = ['PlexPlayerView', 'PlexPlayerPopup']
ON_WINDOWS = sys.platform.startswith('win')
DEFAULT_POPUP_SIZE = (600, 400)
StreamablePlexObj = Union[Track, Movie, Episode]


class PlexPlayerView(PlexView, view_name='player'):
    def __init__(self, plex_obj: StreamablePlexObj = None, **kwargs):
        super().__init__(**kwargs)
        self.menu[0][1].insert(0, '&Open')
        self._init(plex_obj)

    def _init(self, plex_obj: StreamablePlexObj = None):
        if self.name == 'player':
            win_w, win_h = self.window.size
        else:
            win_w, win_h = self.config.get(f'popup_size:{self.name}', DEFAULT_POPUP_SIZE)
        self.video_image = Image(size=(win_w - 2, win_h - 90), key='video', pad=(0, 0))
        inst_args = [
            # '--video-on-top'
        ]
        self.vlc_inst = Instance(inst_args)  # type: Instance
        self.vlc_player = self.vlc_inst.media_player_new()  # type: MediaPlayer
        self.vlc_player.video_set_mouse_input(False)
        self.vlc_player.video_set_key_input(False)
        self.vlc_event_mgr = self.vlc_player.event_manager()  # type: EventManager
        self.vlc_event_mgr.event_attach(EventType.MediaPlayerEndReached, self._stopped)  # noqa
        self.vlc_event_mgr.event_attach(EventType.MediaPlayerTimeChanged, self._time_changed)  # noqa
        self.vlc_event_mgr.event_attach(EventType.MediaPlayerEncounteredError, self._player_error)  # noqa
        self.media = None  # type: Optional[Media]
        self.stopped = True
        self._length = None
        icons = Icons(40)
        self.icons = {
            'play': img_to_b64(icons.draw('play-circle')),
            'pause': img_to_b64(icons.draw('pause-circle')),
            'stop': img_to_b64(icons.draw('stop-circle')),
            'back': img_to_b64(icons.draw('skip-backward-circle')),
            'forward': img_to_b64(icons.draw('skip-forward-circle')),
            'beginning': img_to_b64(icons.draw('skip-start-circle')),
            'end': img_to_b64(icons.draw('skip-end-circle')),
        }
        button_size = (50, 50)
        self.buttons = {
            'beginning': Button(image_data=self.icons['beginning'], key='beginning', size=button_size),
            'back': Button(image_data=self.icons['back'], key='back', size=button_size),
            'play_pause': Button(image_data=self.icons['play'], key='play_pause', size=button_size),
            'stop': Button(image_data=self.icons['stop'], key='stop', size=button_size),
            'forward': Button(image_data=self.icons['forward'], key='forward', size=button_size),
            'end': Button(image_data=self.icons['end'], key='end', size=button_size),
        }
        self.progress = ProgressBar(0, size=(win_w - 10, 15), key='position')
        self.plex_obj = plex_obj
        self.spinner = None
        self._last_click = 0
        self._full_screen = False

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        layout = [
            [self.video_image],
            [self.progress],
            [b for b in self.buttons.values()],
        ]
        full_layout.extend(layout)
        kwargs['margins'] = (0, 0)
        kwargs['element_padding'] = (0, 0)
        return full_layout, kwargs

    def post_render(self):
        super().post_render()
        self.video_image.expand(True, True)
        if ON_WINDOWS:
            self.vlc_player.set_hwnd(self.video_image.Widget.winfo_id())
        else:
            self.vlc_player.set_xwindow(self.video_image.Widget.winfo_id())
        self.progress.Widget.bind('<Button-1>', self._handle_seek_click)
        self.video_image.Widget.bind('<Double-Button-1>', self._handle_double_click)
        self.video_image.Widget.bind('<Button-1>', self._handle_left_click)
        self.video_image.Widget.bind('<Button-3>', self._handle_right_click)
        if self.plex_obj:
            # url = self._get_stream_url()
            url = self._get_local_path()
            self.log.info(f'Beginning stream with {url=}')
            self.media = self.vlc_inst.media_new(url)  # type: Media
            self._start()

    def _get_local_path(self) -> str:
        root = self.plex.server_root
        if ON_WINDOWS:
            if isinstance(root, Path):  # Path does not work for network shares in Windows
                root = root.as_posix()
            if root.startswith('/') and not root.startswith('//'):
                root = '/' + root
        rel_path = self.plex_obj.media[0].parts[0].file
        return os.path.join(root, rel_path[1:] if rel_path.startswith('/') else rel_path)

    def _get_stream_url(self) -> str:
        """
        Unused - Could not find way to craft a URL that would not result in transcoding...
        Maybe should use this if it's possible to play without transcoding, otherwise play local file?

        https://github.com/Arcanemagus/plex-api/wiki/Plex-Web-API-Overview

        TODO: (Maybe) Look into crafting an M3U8 from these:
            /video/:/transcode/universal/decision
            /video/:/transcode/universal/start.mpd
            /video/:/transcode/universal/session/{session}/{1,0}/header
            /video/:/transcode/universal/session/{session}/{1,0}/{n}.m4s
        """
        # return self.plex_obj.getStreamURL()
        plex_obj = self.plex_obj
        params = {
            'path': plex_obj.key,
            'offset': 0,
            'copyts': 1,
            'protocol': 'http',
            'mediaIndex': 0,
            # 'X-Plex-Platform': 'Desktop',
            'X-Plex-Platform': 'Chrome',
            'directPlay': 1,
            'directStream': 1,
            # 'fastSeek': 1,
            # 'location': 'lan',
            # 'directStreamAudio': 1,
            # 'subtitles': 'none',
        }
        stream_type = 'audio' if plex_obj.TYPE == 'track' else 'video'
        return plex_obj._server.url(
            f'/{stream_type}/:/transcode/universal/start.m3u8?{urlencode(params)}', includeToken=True
        )

    def _handle_seek_click(self, event: TkEvent):
        if length_ms := self._length:
            seek_ms = int(length_ms * event.x / self.progress.Widget.winfo_width())  # noqa
            self.log.debug(f'Seeking to {seek_ms=:,d}')
            self.vlc_player.set_time(seek_ms)
            self.progress.update(seek_ms, max=length_ms)

    def _handle_double_click(self, event: TkEvent):
        if monotonic() - self._last_click < 0.5:
            self.play_pause()  # Un-pause

        self._toggle_full_screen()

    def _toggle_full_screen(self, event = None):
        tk_root = self.window.TKroot  # type: Tk
        full_screen = not self._full_screen
        tk_root.attributes('-fullscreen', full_screen)
        button = next(iter(self.buttons.values()))
        if self._full_screen:
            tk_root.unbind('<Escape>')
            self.progress.unhide_row()
            button.unhide_row()
        else:
            tk_root.bind('<Escape>', self._toggle_full_screen)
            self.progress.hide_row()
            button.hide_row()

        self.video_image.expand(True, True)
        self._full_screen = full_screen

    def _handle_left_click(self, event: TkEvent):
        self._last_click = monotonic()
        self.play_pause()

    def _handle_right_click(self, event: TkEvent):
        menu = Menu(self.video_image.Widget.master, tearoff=0)

        crop_menu = Menu(menu)
        ratios = ('Default', '16:10', '16:9', '4:3', '1.85:1', '2.21:1', '2.35:1', '2.39:1', '5:3', '5:4', '1:1')
        values = ('default', '16:10', '16:9', '4:3', '37:20', '11:5', '47:20', '43:18', '5:3', '5:4', '1:1')
        for ratio, value in zip(ratios, values):
            crop_menu.add_command(label=ratio, command=partial(self._crop, value))
        menu.add_cascade(label='Crop', menu=crop_menu)

        try:
            menu.tk_popup(event.x_root, event.y_root)  # noqa
        finally:
            menu.grab_release()

    def _crop(self, ratio: str):
        """WidthxHeight+Left+Top"""
        self.vlc_player.video_set_crop_geometry(None if ratio == 'default' else ratio)
        # TODO: Save crop ratio for a given show & load on start play

    def _start(self):
        if self.plex_obj and not isinstance(self.plex_obj, Track):
            self.spinner = Spinner(parent=self.window)
        self.vlc_player.set_media(self.media)
        self.vlc_player.play()
        self._length = self.plex_obj.duration if self.plex_obj else None
        self.buttons['play_pause'].update(image_data=self.icons['pause'])
        self.stopped = False

    def _player_error(self, event):  # event type: VlcEvent (VLC doesn't like annotations on this for some reason)
        if self.spinner is not None:
            self.spinner.close()
            self.spinner = None
            popup_ok(f'Player encountered an error:\n{event.meta_type=}\n{event.type=}\n{event.obj=}')

    def _stopped(self, event):  # event type: VlcEvent (VLC doesn't like annotations on this for some reason)
        # TODO: Tell plex to incr play count
        # TODO: Tell plex the pause/stop position for movies/episodes
        self.stopped = True
        self.buttons['play_pause'].update(image_data=self.icons['play'])
        self.progress.update(0)

    def _time_changed(self, event):  # event type: VlcEvent (VLC doesn't like annotations on this for some reason)
        # self.log.info(f'_time_changed: {self._length=} {event.meta_type=} {event.type=} {event.obj=}')
        if self._length is None:
            self._length = self.vlc_player.get_length()
        self.progress.update(event.meta_type.value, max=self._length)
        if self.spinner is not None:
            self.spinner.close()
            self.spinner = None

    # region Media Navigation

    @event_handler
    def beginning(self, event: Event, data: EventData):
        if self.vlc_player.is_playing():
            self.vlc_player.set_time(0)
        elif self.media:
            self._start()

    @event_handler
    def back(self, event: Event, data: EventData):
        if self.vlc_player.is_playing():
            self.vlc_player.set_time(self.vlc_player.get_time() - 5000)

    @event_handler
    def stop(self, event: Event, data: EventData):
        self.stopped = True
        if self.vlc_player.is_playing():
            self.vlc_player.stop()
            self.buttons['play_pause'].update(image_data=self.icons['play'])

    @event_handler
    def forward(self, event: Event, data: EventData):
        if self.vlc_player.is_playing():
            self.vlc_player.set_time(self.vlc_player.get_time() + 5000)

    @event_handler
    def end(self, event: Event, data: EventData):
        self.vlc_player.set_time(self.vlc_player.get_length())

    @event_handler
    def play_pause(self, event: Event = None, data: EventData = None):
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
            self.buttons['play_pause'].update(image_data=self.icons['play'])
        elif self.stopped:
            if self.media:
                self._start()
        else:
            self.vlc_player.play()
            self.buttons['play_pause'].update(image_data=self.icons['pause'])

    # endregion

    @event_handler
    def open(self, event: Event, data: EventData):
        if path := get_file_path('Select a file to play', no_window=True):
            self.media = self.vlc_inst.media_new(path.as_posix())  # type: Media
            self.plex_obj = None
            self._start()

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        self.video_image.expand(True, True)
        # TODO: Show: self.vlc_player.video_get_scale()


class PlexPlayerPopup(
    PlexPlayerView,
    BasePopup,
    view_name='player_popup',
    primary=False,
    config_path='plex_gui_config.json',
    defaults=DEFAULT_CONFIG | {'remember_size:player_popup': True},
):
    def __init__(self, plex_obj: StreamablePlexObj = None, plex: LocalPlexServer = None, **kwargs):
        BasePopup.__init__(self, **kwargs)
        self.plex: LocalPlexServer = plex or LocalPlexServer(config_path=self.config['config_path'])
        self._init(plex_obj)

    def __next__(self) -> tuple[Event, EventData]:
        # self.log.debug(f'[View#{self._view_num}] Calling self.window.read...', extra={'color': 11})
        event, data = self.window.read(self.read_timeout_ms)
        # self.log.debug(f'[View#{self._view_num}] Read {event=}', extra={'color': 10})
        if event == 'Exit' or event == WIN_CLOSED:
            if self.vlc_player.is_playing():
                self.vlc_player.stop()
                self.vlc_inst.release()
            raise StopIteration
        return event, data

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        kwargs['size'] = DEFAULT_POPUP_SIZE
        kwargs['resizable'] = True
        kwargs['keep_on_top'] = False
        kwargs['element_justification'] = 'center'
        return full_layout, kwargs


def img_to_b64(image) -> bytes:
    bio = BytesIO()
    image.save(bio, 'PNG')
    return b64encode(bio.getvalue())
