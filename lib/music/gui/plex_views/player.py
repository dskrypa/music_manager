"""
View: Player

https://github.com/PySimpleGUI/PySimpleGUI/blob/master/DemoPrograms/Demo_Media_Player_VLC_Based.py

:author: Doug Skrypa
"""

import sys
from base64 import b64encode
from io import BytesIO
from typing import Optional

from PySimpleGUI import Button, Image, ProgressBar
try:
    from vlc import Instance, MediaPlayer, Media, EventManager, Event, EventType
except (FileNotFoundError, OSError) as e:
    raise RuntimeError(
        'VLC Player is not installed, or the 32 bit version is installed and cannot be loaded from a 64 bit program'
    ) from e

from ..base_view import event_handler, RenderArgs, Event, EventData
from ..icons import Icons
from ..popups.path_prompt import get_file_path
from .main import PlexView

__all__ = ['PlexPlayerView']
ON_WINDOWS = sys.platform.startswith('win')


class PlexPlayerView(PlexView, view_name='player'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.menu[0][1].insert(0, '&Open')
        win_w, win_h = self._window_size
        self.video_image = Image(size=(win_w - 50, win_h - 90), key='video')
        self.vlc_inst = Instance()
        self.vlc_player = self.vlc_inst.media_player_new()  # type: MediaPlayer
        self.vlc_event_mgr = self.vlc_player.event_manager()  # type: EventManager
        self.vlc_event_mgr.event_attach(EventType.MediaPlayerEndReached, self._stopped)  # noqa
        self.vlc_event_mgr.event_attach(EventType.MediaPlayerTimeChanged, self._time_changed)  # noqa
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
            'start': img_to_b64(icons.draw('skip-start-circle')),
            'end': img_to_b64(icons.draw('skip-end-circle')),
        }
        button_size = (50, 50)
        self.buttons = {
            'start': Button(image_data=self.icons['start'], key='start', size=button_size),
            'back': Button(image_data=self.icons['back'], key='back', size=button_size),
            'play_pause': Button(image_data=self.icons['play'], key='play_pause', size=button_size),
            'stop': Button(image_data=self.icons['stop'], key='stop', size=button_size),
            'forward': Button(image_data=self.icons['forward'], key='forward', size=button_size),
            'end': Button(image_data=self.icons['end'], key='end', size=button_size),
        }
        self.progress = ProgressBar(0, size=(win_w - 10, 15), key='position')

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()

        layout = [
            [self.video_image],
            [self.progress],
            [b for b in self.buttons.values()],
        ]

        full_layout.extend(layout)
        return full_layout, kwargs

    def post_render(self):
        super().post_render()
        self.video_image.expand(True, True)
        if ON_WINDOWS:
            self.vlc_player.set_hwnd(self.video_image.Widget.winfo_id())
        else:
            self.vlc_player.set_xwindow(self.video_image.Widget.winfo_id())
        self.video_image.Widget.bind('<Button-1>', self._handle_click)

    def _handle_click(self, event):
        print(event)

    def _start(self):
        self.vlc_player.set_media(self.media)
        self.vlc_player.play()
        self._length = None
        self.buttons['play_pause'].update(image_data=self.icons['pause'])
        self.stopped = False

    def _stopped(self, event):
        self.progress.update(self._length, max=self._length)
        self.stopped = True
        self.buttons['play_pause'].update(image_data=self.icons['play'])

    def _time_changed(self, event):
        if self._length is None:
            self._length = self.vlc_player.get_length()
        self.progress.update(event.meta_type.value, max=self._length)

    @event_handler
    def start(self, event: Event, data: EventData):
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
    def play_pause(self, event: Event, data: EventData):
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
            self.buttons['play_pause'].update(image_data=self.icons['play'])
        elif self.stopped:
            if self.media:
                self._start()
        else:
            self.vlc_player.play()
            self.buttons['play_pause'].update(image_data=self.icons['pause'])

    @event_handler
    def open(self, event: Event, data: EventData):
        if path := get_file_path('Select a file to play', no_window=True):
            self.media = self.vlc_inst.media_new(path.as_posix())  # type: Media
            self._start()


def img_to_b64(image) -> bytes:
    bio = BytesIO()
    image.save(bio, 'PNG')
    return b64encode(bio.getvalue())
