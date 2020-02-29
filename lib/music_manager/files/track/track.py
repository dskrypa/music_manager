"""
:author: Doug Skrypa
"""

import logging
import re
from fnmatch import translate as fnmatch_to_regex_str
from pathlib import Path

import mutagen.id3._frames as id3_frames

from ds_tools.compat import cached_property
from ...utils.constants import tag_name_map
from .base import BaseSongFile

__all__ = ['SongFile']
log = logging.getLogger(__name__)


class SongFile(BaseSongFile):
    @classmethod
    def for_plex_track(cls, track, root):
        return cls(Path(root).joinpath(track.media[0].parts[0].file).resolve())

    @cached_property
    def extended_repr(self):
        try:
            info = '[{!r} by {}, in {!r}]'.format(self.tag_title, self.tag_artist, self.album_name_cleaned)
        except Exception as e:
            info = ''
        return '<{}({!r}){}>'.format(self.__class__.__name__, self.rel_path, info)

    @cached_property
    def album_from_dir(self):
        album = self.path.parent.name
        if album.lower().startswith(self.tag_artist.lower()):
            album = album[len(self.tag_artist):].strip()
        if album.startswith('- '):
            album = album[1:].strip()
        m = re.match(r'^\[\d{4}[0-9.]*\] (.*)$', album)     # Begins with date
        if m:
            album = m.group(1).strip()
        m = re.match(r'(.*)\s*\[.*Album\]', album)          # Ends with Xth Album
        if m:
            album = m.group(1).strip()
        return album

    @cached_property
    def in_competition_album(self):
        try:
            album_artist = self.tag_text('album_artist')
        except Exception:
            return False
        else:
            if album_artist.lower().startswith('produce'):
                if album_artist.split()[-1].isdigit():
                    return True
        return False

    @cached_property
    def _is_full_ost(self):
        album_artist = self.tag_text('album_artist', default='').lower()
        album_name = self.album_name_cleaned
        full_ost = album_name.endswith('OST') and 'part' not in album_name.lower()
        # noinspection PyUnresolvedReferences
        alb_dir = self.album_dir_obj
        multiple_artists = len({f.tag_artist for f in alb_dir}) > 1
        return full_ost and album_artist == 'various artists' and multiple_artists and len(alb_dir) > 2

    def _cleanup_album_name(self, album):
        m = re.match(r'^\[\d{4}[0-9.]*\](.*)', album, re.IGNORECASE)
        if m:
            album = m.group(1).strip()

        m = re.match(r'(.*)\s*\[.*Album(?: repackage)?\]', album, re.IGNORECASE)
        if m:
            album = m.group(1).strip()

        m = re.match(r'^(.*?)-?\s*(?:the)?\s*[0-9](?:st|nd|rd|th)\s+\S*\s*album\s*(?:repackage)?\s*(.*)$', album, re.I)
        if m:
            album = ' '.join(map(str.strip, m.groups())).strip()

        m = re.search(r'((?:^|\s+)\d+\s*집(?:$|\s+))', album)  # {num}집 == nth album
        if m:
            album = album.replace(m.group(1), ' ').strip()

        m = re.match(r'(.*)(\s-\s*(?:EP|Single))$', album, re.IGNORECASE)
        if m:
            album = m.group(1)

        m = re.match(r'^(.*)\sO\.S\.T\.?(\s.*|$)', album, re.IGNORECASE)
        if m:
            album = '{} OST{}'.format(*m.groups())

        for pat in ('^(.*) `(.*)`$', '^(.*) - (.*)$'):
            m = re.match(pat, album)
            if m:
                group, title = m.groups()
                if group in self.tag_artist:
                    album = title
                break

        return album.replace(' : ', ': ').strip()

    @cached_property
    def album_name_cleaned(self):
        cleaned = self._cleanup_album_name(self.tag_text('album'))
        return cleaned if cleaned else self.tag_text('album')

    def _extract_album_part(self, title):
        part = None
        m = re.match(r'^(.*)\s+((?:Part|Code No)\.?\s*\d+)$', title, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            part = m.group(2).strip()

        if title.endswith(' -'):
            title = title[:-1].strip()
        return title, part

    @cached_property
    def album_name_cleaned_plus_and_part(self):
        return self._extract_album_part(self.album_name_cleaned)

    @cached_property
    def album_name_cleaner(self):
        album = self.album_name_cleaned
        m = re.match(r'(.*)(\((?:vol.?|volume) (?:\d+|[ivx]+)\))$', album, re.IGNORECASE)
        if m:
            album = m.group(1)
        return album

    @cached_property
    def dir_name_cleaned(self):
        return self._cleanup_album_name(self.path.parent.name)

    @cached_property
    def dir_name_cleaned_plus_and_part(self):
        return self._extract_album_part(self.dir_name_cleaned)

    @cached_property
    def _artist_path(self):
        bad = (
            'album', 'single', 'soundtrack', 'collaboration', 'solo', 'christmas', 'download', 'compilation',
            'unknown_fixme', 'mixtape'
        )
        artist_path = self.path.parents[1]
        lc_name = artist_path.name.lower()
        if not any(i in lc_name for i in bad):
            return artist_path

        artist_path = artist_path.parent
        lc_name = artist_path.name.lower()
        if not any(i in lc_name for i in bad):
            return artist_path
        log.debug('Unable to determine artist path for {}'.format(self))
        return None

    @cached_property
    def album_type_dir(self):
        return self.path.parents[1].name

    def update_tags(self, tag_ids, value, patterns=None, partial=False, dry_run=False):
        if partial and not patterns:
            raise ValueError('Unable to perform partial tag update without any patterns')
        if patterns:
            patterns = [re.compile(fnmatch_to_regex_str(p)[4:-3]) if isinstance(p, str) else p for p in patterns]

        prefix, repl_msg, set_msg = ('[DRY RUN] Would ', 'replace', 'set') if dry_run else ('', 'Replacing', 'Setting')

        should_save = False
        for tag_id in tag_ids:
            tag_name = tag_name_map.get(tag_id)
            if not tag_name:
                raise ValueError(f'Invalid tag ID: {tag_id}')
            tag_repr = f'{tag_id}/{tag_name}'

            current_vals = self.tags_for_id(tag_id)
            if not current_vals:
                if self._tag_type == 'mp3':
                    try:
                        frame_cls = getattr(id3_frames, tag_id.upper())
                    except AttributeError as e:
                        raise ValueError(f'Invalid tag ID: {tag_id!r} (no frame class found for it)') from e
                else:
                    raise ValueError(f'Adding new tags to non-MP3s is not currently supported for {self}')

                log.info(f'{prefix}{set_msg} {tag_repr} = {value!r} in file: {self.filename}')
                should_save = True
                if not dry_run:
                    self.tags.add(frame_cls(text=value))
            else:
                if len(current_vals) > 1:
                    log.warning(f'Found multiple values for {tag_repr} in {self.filename} - using first value')

                current_val = current_vals[0]
                current_text = current_val.text[0]
                new_text = current_text
                if partial:
                    for pat in patterns:
                        new_text = pat.sub(value, new_text)
                else:
                    if patterns:
                        if any(pat.search(current_text) for pat in patterns):
                            new_text = value
                    else:
                        new_text = value

                if new_text != current_text:
                    log.info(f'{prefix}{repl_msg} {tag_repr} {current_text!r} with {new_text!r} in {self.filename}')
                    should_save = True
                    if not dry_run:
                        current_vals[0].text[0] = new_text

        if should_save:
            if not dry_run:
                self.save()
        else:
            log.log(19, f'Nothing to change for {self.filename}')
