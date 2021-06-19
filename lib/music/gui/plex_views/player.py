"""
View: Player

:author: Doug Skrypa
"""

import sys
from base64 import b64encode
from io import BytesIO
from typing import Optional

from PySimpleGUI import Button, Image, ProgressBar, WIN_CLOSED
try:
    from vlc import Instance, MediaPlayer, Media, EventManager, Event, EventType
except (FileNotFoundError, OSError) as e:
    raise RuntimeError(
        'VLC Player is not installed, or the 32 bit version is installed and cannot be loaded from a 64 bit program'
    ) from e

from ...plex.server import LocalPlexServer
from ..base_view import event_handler, RenderArgs, Event, EventData
from ..icons import Icons
from ..popups.base import BasePopup
from ..popups.path_prompt import get_file_path
from .main import PlexView, DEFAULT_CONFIG

__all__ = ['PlexPlayerView', 'PlexPlayerPopup']
ON_WINDOWS = sys.platform.startswith('win')
DEFAULT_POPUP_SIZE = (600, 400)


class PlexPlayerView(PlexView, view_name='player'):
    def __init__(self, url: str = None, **kwargs):
        super().__init__(**kwargs)
        self.menu[0][1].insert(0, '&Open')
        self._init(url)

    def _init(self, url: str = None):
        if self.name == 'player':
            win_w, win_h = self.window.size
        else:
            win_w, win_h = self.config.get(f'popup_size:{self.name}', DEFAULT_POPUP_SIZE)
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
        self.url = url

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
        # self.video_image.Widget.bind('<Button-1>', self._handle_click)
        if self.url:
            # self.window.write_event_value()
            self.media = self.vlc_inst.media_new(self.url)  # type: Media
            self._start()

    # def _handle_click(self, event):
    #     print(event)

    def _start(self):
        self.vlc_player.set_media(self.media)
        self.vlc_player.play()
        self._length = getattr(self, '_duration', None)
        self.buttons['play_pause'].update(image_data=self.icons['pause'])
        self.stopped = False

    def _stopped(self, event):
        # TODO: Tell plex to incr play count
        self.progress.update(self._length, max=self._length)
        self.stopped = True
        self.buttons['play_pause'].update(image_data=self.icons['play'])

    def _time_changed(self, event):
        # self.log.info(f'_time_changed: {self._length=} {event.meta_type=} {event.type=} {event.obj=}')
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

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        self.video_image.expand(True, True)


class PlexPlayerPopup(
    PlexPlayerView,
    BasePopup,
    view_name='player_popup',
    primary=False,
    config_path='plex_gui_config.json',
    defaults=DEFAULT_CONFIG | {'remember_size:player_popup': True},
):
    def __init__(self, url: str = None, duration: int = None, plex: LocalPlexServer = None, **kwargs):
        BasePopup.__init__(self, **kwargs)
        self.plex: LocalPlexServer = plex or LocalPlexServer(config_path=self.config['config_path'])
        self._init(url)
        self._duration = duration

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
        kwargs['element_justification'] = 'center'
        return full_layout, kwargs


def img_to_b64(image) -> bytes:
    bio = BytesIO()
    image.save(bio, 'PNG')
    return b64encode(bio.getvalue())
