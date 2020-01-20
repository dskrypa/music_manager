#!/usr/bin/env python3
"""
Flask server for updating song metadata

:author: Doug Skrypa
"""

import argparse
import logging
import signal
import socket
import sys
import traceback
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

import eventlet
from flask import Flask, request, render_template, redirect, Response, url_for
from flask_socketio import SocketIO
from requests import Session
from werkzeug.http import HTTP_STATUS_CODES as codes

flask_dir = Path(__file__).resolve().parent
sys.path.append(flask_dir.parents[1].as_posix())
from ds_tools.logging import init_logging
from ds_tools.music import (
    iter_music_files, load_tags, iter_music_albums, iter_categorized_music_files, tag_repr, apply_mutagen_patches,
    TagException, iter_album_dirs, RM_TAGS_ID3, RM_TAGS_MP4, NoPrimaryArtistError, WikiSoundtrack
)

apply_mutagen_patches()

log = logging.getLogger(__name__)

socketio = None
shutdown_pw = None
stopped = False
server_port = None
app = Flask(
    __name__,
    static_folder=flask_dir.joinpath('static').as_posix(),
    template_folder=flask_dir.joinpath('templates').as_posix()
)
app.config.update(PROPAGATE_EXCEPTIONS=True, JSONIFY_PRETTYPRINT_REGULAR=True)


@app.route('/shutdown', methods=['POST'])
def shutdown_server():
    user_ip = request.environ.get('REMOTE_ADDR')
    data = request.get_json()
    if data.get('password') == shutdown_pw:
        log.info('Stopping server...')
        socketio.stop()
    else:
        log.info('Rejecting unauthorized stop request from {}'.format(user_ip))
        return Response(status=403)


@app.route('/')
def home():
    url = url_for('.process_songs')
    log.info('Redirecting from / to {}'.format(url))
    return redirect(url)


@app.route('/update_songs/')
def update_songs():
    raise ResponseException(501, 'Not available yet.')


@app.route('/process_songs/', methods=['GET', 'POST'])
def process_songs():
    req_is_post = request.method == 'POST'
    params = {}
    for param in ('src_path', 'dest_path', 'include_osts'):
        value = request.form.get(param)
        if value is None:
            value = request.args.get(param)
        if value is not None:
            if isinstance(value, str):
                value = value.strip()
                if value:
                    params[param] = value
            else:
                params[param] = value

    if req_is_post:
        redirect_to = url_for('.process_songs')
        if params:
            redirect_to += '?' + urlencode(params, True)
        return redirect(redirect_to)

    if not params.get('src_path'):
        return render_template('layout.html', form_values={})

    src_path = Path(params.get('src_path'))
    dest_path = Path(params['dest_path']) if params.get('dest_path') else None
    include_osts = params.get('include_osts')

    form_values = {'src_path': src_path, 'dest_path': dest_path}
    render_vars = {
        'form_values': form_values,
        'section_order': [('name', 'Field'), ('score', 'Score'), ('original', 'Original'), ('new', 'Proposed')]
    }

    if not src_path.exists():
        raise ResponseException(400, 'The source path {} does not exist!'.format(src_path.as_posix()))
    if dest_path and dest_path.is_file():
        raise ResponseException(400, 'The destination path {} is invalid!'.format(dest_path.as_posix()))

    render_vars['results'] = match_wiki(src_path, include_osts)
    return render_template('layout.html', **render_vars)


def set_ost_filter(path, include_osts=False):
    if include_osts:
        WikiSoundtrack._search_filters = None
    else:
        ost_filter = set()
        for f in iter_music_files(path):
            ost_filter.add(f.album_name_cleaned)
            ost_filter.add(f.dir_name_cleaned)

        WikiSoundtrack._search_filters = ost_filter

    log.debug('OST Search Filter: {}'.format(WikiSoundtrack._search_filters))


def match_wiki(path, include_osts):
    set_ost_filter(path, include_osts)
    rows = []
    for music_file in iter_music_files(path):
        track = int(music_file.track_num) if music_file.track_num else ''
        disk = int(music_file.disk_num) if music_file.disk_num else ''
        track_row = {
            'path': music_file.path.as_posix(),
            'error': None,
            'fields': {
                'artist': {
                    'original': music_file.tag_artist, 'new': music_file.tag_artist, 'score': None
                },
                'album': {
                    'original': music_file.album_name_cleaned, 'new': music_file.album_name_cleaned, 'score': None
                },
                'album_type': {
                    'original': music_file.album_type_dir, 'new': music_file.album_type_dir, 'score': None
                },
                'title': {
                    'original': music_file.tag_title, 'new': music_file.tag_title, 'score': None
                },
                'track': {
                    'original': track, 'new': track, 'score': None
                },
                'disk': {
                    'original': disk, 'new': disk, 'score': None
                },
            }
        }

        fields = track_row['fields']
        try:
            try:
                fields['artist']['new'] = music_file.wiki_artist.qualname if music_file.wiki_artist else ''
            except NoPrimaryArtistError as e:
                pass

            fields['album']['new'] = music_file.wiki_album.title() if music_file.wiki_album else ''
            fields['album']['score'] = music_file.wiki_scores.get('album', -1)
            fields['album_type']['new'] = music_file.wiki_album.album_type if music_file.wiki_album else ''
            fields['title']['new'] = music_file.wiki_song.long_name if music_file.wiki_song else ''
            fields['title']['score'] = music_file.wiki_scores.get('song', -1)
            fields['track']['new'] = int(music_file.wiki_song.num) if music_file.wiki_song else ''
            fields['disk']['new'] = int(music_file.wiki_song.disk) if music_file.wiki_song else ''
        except Exception as e:
            log.error('Error processing {}: {}'.format(music_file, e), extra={'color': (15, 9)})
            log.log(19, traceback.format_exc())
            track_row['error'] = traceback.format_exc()

        rows.append(track_row)

    tracks_by_artist_album = defaultdict(lambda: defaultdict(list))
    for row in rows:
        fields = row['fields']
        artist = fields['artist']['original']
        album = fields['album']['original']

        for name, field in fields.items():
            field['name'] = name

        # columns = []
        # columns = [[], [], [], []]
        # for field, vals in sorted(fields.items()):
        #     # columns.append((field, vals['original'], vals['new'], vals['score']))
        #     _row = (field, vals['original'], vals['new'], vals['score'])
        #     for i, val in enumerate(_row):
        #         columns[i].append(val)
        # tracks_by_artist_album[artist][album].append((row['path'], columns))
        tracks_by_artist_album[artist][album].append(row)
    return tracks_by_artist_album


class ResponseException(Exception):
    def __init__(self, code, reason):
        super().__init__()
        self.code = code
        self.reason = reason
        if isinstance(reason, Exception):
            log.error(traceback.format_exc())
        log.error(self.reason)

    def __repr__(self):
        return '<{}({}, {!r})>'.format(type(self).__name__, self.code, self.reason)

    def __str__(self):
        return '{}: [{}] {}'.format(type(self).__name__, self.code, self.reason)

    def as_response(self):
        # noinspection PyUnresolvedReferences
        rendered = render_template('layout.html', error_code=codes[self.code], error=self.reason)
        return Response(rendered, self.code)


@app.errorhandler(ResponseException)
def handle_response_exception(err):
    return err.as_response()


def start_server(run_args):
    log.info('Starting Flask server on port={}'.format(run_args['port']))
    global socketio, shutdown_pw, server_port
    server_port = run_args['port']
    shutdown_pw = str(uuid.uuid4())
    socketio = SocketIO(app, async_mode='eventlet')
    socketio.run(app, **run_args)


def stop_server():
    with Session() as session:
        log.info('Telling local server to shutdown...')
        try:
            resp = session.post(
                'http://localhost:{}/shutdown'.format(server_port), json={'password': shutdown_pw}, timeout=1
            )
        except Exception as e:
            log.debug('Shutdown request timed out (this is expected)')
        else:
            log.debug('Shutdown response: {} - {}'.format(resp, resp.text))


def stop_everything():
    global stopped
    if not stopped:
        stop_server()
        stopped = True


def handle_signals(sig_num=None, frame=None):
    log.info('Caught signal {} - shutting down'.format(sig_num))
    stop_everything()
    sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Music Manager Flask Server')
    parser.add_argument('--use_hostname', '-u', action='store_true', help='Use hostname instead of localhost/127.0.0.1')
    parser.add_argument('--port', '-p', type=int, help='Port to use', required=True)
    parser.add_argument('--verbose', '-v', action='count', help='Print more verbose log info (may be specified multiple times to increase verbosity)')
    args = parser.parse_args()
    init_logging(args.verbose, names=None, log_path=None)

    flask_logger = logging.getLogger('flask.app')
    for handler in logging.getLogger().handlers:
        if handler.name == 'stderr':
            flask_logger.addHandler(handler)
            break

    run_args = {'port': args.port}
    if args.use_hostname:
        run_args['host'] = socket.gethostname()

    signal.signal(signal.SIGTERM, handle_signals)
    signal.signal(signal.SIGINT, handle_signals)

    try:
        start_server(run_args)
        # app.run(**run_args)
    except Exception as e:
        log.debug(traceback.format_exc())
        log.error(e)
