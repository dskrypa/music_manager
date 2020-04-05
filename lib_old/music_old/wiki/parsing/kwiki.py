"""
:author: Doug Skrypa
"""

import logging
import re
from collections import defaultdict
from itertools import chain
from urllib.parse import urlparse

from bs4.element import NavigableString, Tag

from ds_tools.unicode import LangCat
from ds_tools.utils import (
    ParentheticalParser, DASH_CHARS, num_suffix, QMARKS, unsurround, normalize_roman_numerals, has_nested
)
from ds_tools.utils.soup import soupify
from ...name_processing import has_parens, parse_name, split_name, str2list, categorize_langs
from ..utils import synonym_pattern, get_page_category, normalize_href
from .common import (
    album_num_type, first_side_info_val, LANG_ABBREV_MAP, link_tuples, NUM2INT, parse_track_info, parse_date,
    TrackListParser, split_artist_list, parse_tracks_from_table
)
from .exceptions import NoTrackListException, WikiEntityParseException, UnexpectedDateFormat, TrackInfoParseException

__all__ = ['find_group_members', 'parse_album_page', 'parse_album_tracks', 'parse_aside', 'parse_discography_section']
log = logging.getLogger(__name__)


def parse_album_tracks(uri_path, clean_soup, intro_links, artists, compilation=False, client=None):
    """
    Parse the Track List section of a Kpop Wiki album/single page.

    :param str uri_path: The uri_path of the page to include in log messages
    :param clean_soup: The cleaned up bs4 soup for the page content
    :param list intro_links: List of tuples of (text, href) containing links from the intro
    :return list: List of dicts of album parts/editions/disks, with a track list per section
    """
    track_list_span = clean_soup.find('span', id='Track_list') or clean_soup.find('span', id='Tracklist')
    if not track_list_span:
        raise NoTrackListException('Unable to find track list for album {}'.format(uri_path))

    h2 = track_list_span.find_parent('h2')
    if not h2:
        raise WikiEntityParseException('Unable to find track list header for album {}'.format(uri_path))

    try:
        disk_rx = parse_album_tracks._disk_rx
    except AttributeError:
        disk_rx = parse_album_tracks._disk_rx = re.compile(
            r'^(?:Dis[ck]|CD)\s*(\S+)\s*[{}]?\s*(.*)$'.format(DASH_CHARS + ':'), re.IGNORECASE
        )

    unexpected_num_fmt = 'Unexpected disk number format for {}: {!r}'
    parser = ParentheticalParser(False)
    track_lists = []
    section, language, links, disk = None, None, [], 1
    super_section = None
    last_section_idx = None
    for section_idx, ele in enumerate(h2.next_siblings):
        if isinstance(ele, NavigableString):
            continue

        ele_name = ele.name
        if ele_name == 'h2':
            break
        elif ele_name == 'table' and 'tracklist' in ele.get('class'):
            tracks = parse_tracks_from_table(ele, uri_path, client)
            track_lists.append({
                'section': section,
                'tracks': tracks, 'links': links, 'disk': disk, 'language': language
            })
            section, language, links = None, None, []
        elif ele_name in ('ol', 'ul'):
            # log.debug('Processing section={!r} on {}'.format(section, uri_path))
            if section and (section if isinstance(section, str) else section[0]).lower().startswith('dvd'):
                section, links = None, []
                continue

            tracks = []
            for i, li in enumerate(ele.find_all('li')):
                track_links = link_tuples(li.find_all('a'))
                all_links = tuple(set(list(track_links) + intro_links))
                try:
                    track = parse_track_info(
                        i + 1, li.text, uri_path, include={'links': track_links, 'disk': disk}, links=all_links,
                        compilation=compilation, artist=artists, client=client
                    )
                except ValueError as e:
                    if LangCat.categorize(li.text) == LangCat.MIX and not has_nested(li.text):
                        try:
                            track_name, track_time = map(str.strip, li.text.rsplit('-', 1))
                        except ValueError as e1:
                            raise WikiEntityParseException('Error splitting {!r} from {}'.format(li.text, uri_path)) from e1

                        if track_name.startswith('"') and track_name.endswith('"'):
                            track_name = unsurround(track_name)
                            name_parts = LangCat.sort(LangCat.split(track_name))
                            eng_parts, cjk_parts = [], []
                            while name_parts:
                                part = name_parts.pop(0)
                                if LangCat.categorize(part) == LangCat.ENG:
                                    eng_parts.append(part)
                                else:
                                    cjk_parts.append(part)
                                    cjk_parts.extend(name_parts)
                                    break

                            eng_name = ' '.join(eng_parts)
                            if len(cjk_parts) > 1:
                                cjk_name = '({})'.format(' '.join(cjk_parts))
                            else:
                                cjk_name = ' '.join(cjk_parts)

                            if cjk_name:
                                track_name = '{} {}'.format(eng_name, cjk_name)
                            else:
                                track_name = eng_name

                            if track_time:
                                track_name = '{} - {}'.format(track_name, track_time)

                            track = parse_track_info(
                                i + 1, track_name, uri_path, include={'links': track_links, 'disk': disk},
                                links=all_links, compilation=compilation, artist=artists, client=client
                            )
                        else:
                            raise WikiEntityParseException('Error parsing track={!r} on {}'.format(li.text, uri_path))
                    else:
                        raise WikiEntityParseException('Error parsing track={!r} on {}'.format(li.text, uri_path))

                tracks.append(track)

            track_lists.append({
                'section': section,
                'tracks': tracks, 'links': links, 'disk': disk, 'language': language
            })
            section, language, links = None, None, []
        else:
            for junk in ele.find_all(class_='editsection'):
                junk.extract()
            if last_section_idx and section_idx - last_section_idx == 2:
                super_section = [section] if isinstance(section, str) else section
                # log.debug('Updated super_section={!r}'.format(super_section))
            section = ele.text.strip()
            last_section_idx = section_idx
            # log.debug('Found section={} on page={}: {!r}'.format(section_idx, uri_path, section))
            if section.lower().startswith('cd+dvd'):
                section, links = None, []
                continue

            links = link_tuples(ele.find_all('a'))
            if has_parens(section):
                try:
                    section = parser.parse(section)
                except Exception as e:
                    pass
                else:
                    if super_section:
                        section = super_section + section
                    for i, sec_part in enumerate(section):
                        lc_sec_part = sec_part.lower()
                        if 'ver' in lc_sec_part:
                            language = next((lng for abrv, lng in LANG_ABBREV_MAP.items() if abrv in lc_sec_part), None)
                            if language:
                                section.pop(i)
                                break
                        else:
                            language = next((lng for abrv, lng in LANG_ABBREV_MAP.items() if abrv == lc_sec_part), None)
                            if language:
                                section.pop(i)
                                break
            else:
                lc_section = section.lower()
                language = next((lng for abrv, lng in LANG_ABBREV_MAP.items() if abrv in lc_section), None)
                if super_section:
                    section = super_section + [section]
                    if language:
                        lc_lang = language.lower()
                        for i, sec_part in enumerate(section):
                            if lc_lang in sec_part.lower():
                                section.pop(i)
                                break

            disk_section = section if not section or isinstance(section, str) else section[0]
            lc_disk_section = disk_section.lower().strip() if disk_section else ''
            if disk_section and lc_disk_section.startswith(('disk', 'disc', 'cd')) and lc_disk_section != 'cd':
                m = disk_rx.match(disk_section)
                if not m:
                    raise WikiEntityParseException(unexpected_num_fmt.format(uri_path, disk_section))

                update_section = True
                disk_raw = m.group(1).strip().lower()
                try:
                    disk = NUM2INT[disk_raw]
                except KeyError as e:
                    if lc_disk_section == 'cd only':
                        update_section = False
                    else:
                        try:
                            disk = int(disk_raw)
                        except (TypeError, ValueError) as e1:
                            raise WikiEntityParseException(unexpected_num_fmt.format(uri_path, m.group(1))) from e1

                if update_section:
                    disk_section = m.group(2).strip() or None
                    # log.debug('Adding disk_section={!r} to section={!r}'.format(disk_section, section))
                    if isinstance(section, str):
                        section = disk_section
                    else:
                        if not disk_section:
                            section.pop(0)
                            if not section:
                                section = None
                        else:
                            section[0] = disk_section
            else:
                disk = 1

    return track_lists


def parse_album_page(uri_path, clean_soup, side_info, client):
    """
    :param clean_soup: The :attr:`WikiEntity._clean_soup` value for an album
    :param dict side_info: Parsed 'aside' element contents
    :return list: List of dicts representing the albums found on the given page
    """
    bad_intro_fmt = 'Unexpected album intro sentence format in {}: {!r}'
    album0 = {}
    album1 = {}
    intro_text = clean_soup.text.strip()
    try:
        intro_rx = parse_album_page._intro_rx
        title_rx = parse_album_page._title_rx
    except AttributeError:
        intro_rx = parse_album_page._intro_rx = re.compile(r'^(.*?)\s+is\s+(?:an?|the)\s+(.*?)\.\s')
        title_rx = parse_album_page._title_rx = re.compile(
            r'^The \S+ Album ([{}])(.*)\1(.*)'.format(QMARKS + "'"), re.IGNORECASE
        )

    # TODO: Handle deluxe edition as repackage: https://kpop.fandom.com/wiki/My_Voice

    intro_match = intro_rx.match(intro_text)
    if not intro_match:
        raise WikiEntityParseException(bad_intro_fmt.format(uri_path, intro_text[:200]))

    orig_title_part = title_part = intro_match.group(1).strip()
    m = title_rx.match(title_part)
    if m:
        title_part = ''.join(m.groups()[1:])
        log.debug('Changed pre-parsed title from {!r} to {!r}'.format(orig_title_part, title_part))
    # log.debug('{}: intro match group(len={}): {!r}'.format(uri_path, len(intro_match.group(1)), intro_match.group(1)))
    album0['title_parts'] = parse_name(title_part)  # base, cjk, stylized, aka, info
    details_str = intro_match.group(2)
    details_str = details_str.replace('full length', 'full-length').replace('mini-album', 'mini album')
    details = list(details_str.split())
    if (details[0] == 'repackage') or (details[0] == 'new' and details[1] == 'edition'):
        album0['repackage'] = True
        for i, ele in enumerate(details):
            if ele.endswith(('\'s', 'S\'', 's\'')):
                artist_idx = i
                break
        else:
            raise WikiEntityParseException(bad_intro_fmt.format(uri_path, intro_text[:200]))

        try:
            album0['num'], album0['type'] = album_num_type(details[artist_idx:])
        except ValueError as e:
            raise WikiEntityParseException(bad_intro_fmt.format(uri_path, intro_text[:200])) from e

        for i, a in enumerate(clean_soup.find_all('a')):
            if details_str.endswith(a.text):
                href = (a.get('href') or '')[6:]
                if href:
                    try:
                        raw, cats = client.get_entity_base(href)
                        category = get_page_category(client.url_for(uri_path), cats, no_debug=True)
                    except Exception as e:
                        pass
                    else:
                        if category in ('album', 'soundtrack'):
                            album0['repackage_of_href'] = href
                            album0['repackage_of_title'] = a.text
                            break
            elif i > 2:
                break
        else:
            fmt = 'Unable to find link to repackaged version of {}; details={}'
            raise WikiEntityParseException(fmt.format(uri_path, details))
    elif (details[0] == 'original' and details[1] == 'soundtrack') or (details[0].lower() in ('ost', 'soundtrack')):
        album0['num'] = None
        album0['type'] = 'OST'
        album0['repackage'] = False
    else:
        album0['repackage'] = False
        try:
            album0['num'], album0['type'] = album_num_type(details)
        except ValueError as e:
            raise WikiEntityParseException(bad_intro_fmt.format(uri_path, intro_text[:200])) from e

        try:
            repkg_rx = parse_album_page._repkg_rx
        except AttributeError:
            repkg_rx = parse_album_page._repkg_rx = re.compile(
                'A repackage titled (.*?)(?:,[^,]+,)? (?:was|will be) released'
            )
        repkg_match = repkg_rx.search(intro_text)
        if repkg_match:
            repkg_title = repkg_match.group(1)
            # log.debug('repackage of uri_path={!r} is titled {!r}'.format(uri_path, repkg_title))
            releases = side_info.get('released', [])
            repkg_dt = next((dt for dt, note in releases if note and note.lower() == 'repackage'), None)
            if repkg_dt:
                album1['title_parts'] = parse_name(repkg_title)   # base, cjk, stylized, aka, info
                album1['length'] = next((val for val, note in side_info.get('length', []) if note == 'repackage'), None)
                album1['num'] = album0['num']
                album1['type'] = album0['type']
                album1['repackage'] = True
                album1['repackage_of_href'] = uri_path
                album1['repackage_of_title'] = repkg_title
                album0['repackage_href'] = uri_path
                album0['repackage_title'] = repkg_title
                album1['released'] = repkg_dt
                album1['links'] = []
            else:
                for a in clean_soup.find_all('a'):
                    if a.text == repkg_title:
                        href = a.get('href')
                        if href:
                            album0['repackage_href'] = href[6:]
                            album0['repackage_title'] = repkg_title
                        break
                else:
                    raise WikiEntityParseException('Unable to find link to repackaged version of {}'.format(uri_path))
        elif 'repackage of the album was released' in intro_text:
            for a in clean_soup.find_all('a'):
                href = a.get('href')
                if href and a.text and 'repackage' in a.text:
                    repkg_title = a.get('title')
                    album0['repackage_href'] = href[6:]
                    album0['repackage_title'] = repkg_title
                    break

    links = []
    for ele in clean_soup.children:
        if isinstance(ele, NavigableString):
            continue
        elif ele.name in ('h1', 'h2', 'h3', 'h4'):
            break
        links.extend(link_tuples(ele.find_all('a')))
        # links.extend((a.text, a.get('href')) for a in ele.find_all('a'))
    album0['links'] = links
    album0['released'] = first_side_info_val(side_info, 'released')
    album0['length'] = first_side_info_val(side_info, 'length')
    album0['name'] = side_info.get('name')

    albums = [album0, album1] if album1 else [album0]

    # artists_raw = side_info.get('artists_raw')
    artists_raw = side_info.get('artist')
    artists = []
    if artists_raw:
        _anchors = tuple(clean_soup.find_all('a'))
        for _raw_artist in artists_raw:
            artists.extend(split_artist_list(_raw_artist, uri_path, _anchors, client=client)[0])
    # else:
    #     artists = side_info.get('artist', {})

    for album in albums:
        album['artists'] = artists

    try:
        track_lists = parse_album_tracks(
            uri_path, clean_soup, links, artists, 'compilation' in album0['type'].lower(), client=client
        )
    except NoTrackListException as e:
        if not album1 and 'single' in album0['type'].lower():
            eng, cjk = album0['title_parts'][:2]
            title_info = album0['title_parts'][-1]
            _name = '{} ({})'.format(eng, cjk)
            if title_info:
                _name = ' '.join(chain((_name,), map('({})'.format, title_info)))
            album0['tracks'] = {
                'section': None, 'tracks': [
                    # {'name_parts': (eng, cjk), 'num': 1, 'length': album0['length'] or '-1:00', 'misc': title_info},
                    parse_track_info(1, _name, uri_path, album0['length'] or '-1:00', client=client)
                ]
            }
            album0['fake_track_list'] = True
        else:
            raise e
    else:
        if album1:
            if len(track_lists) != 2:
                err_msg = 'Unexpected track section count for original+repackage combined page {}'.format(uri_path)
                raise WikiEntityParseException(err_msg)
            for i, album in enumerate(albums):
                album['tracks'] = track_lists[i]
        else:
            if len(track_lists) == 1:
                album0['tracks'] = track_lists[0]
            else:
                album0['track_lists'] = track_lists

    return albums


def parse_aside(aside, uri_path):
    """
    Parse the 'aside' element from a wiki page into a more easily used data format

    :param aside: Beautiful soup 'aside' element
    :return dict: The parsed data
    """
    try:
        comma_fix_rx = parse_aside._comma_fix_rx
        date_comment_rx = parse_aside._date_comment_rx
        len_rx = parse_aside._len_rx
        len_comment_rx = parse_aside._len_comment_rx
        br_split_rx = parse_aside._br_split_rx
    except AttributeError:
        comma_fix_rx = parse_aside._comma_fix_rx = re.compile(r'\s+,')
        date_comment_rx = parse_aside._date_comment_rx = re.compile(r'^(\S+ \d+\s*, \d{4})\s*\((.*)\)$')
        len_rx = parse_aside._len_rx = re.compile(r'^\d*:?\d+:\d{2}$')
        len_comment_rx = parse_aside._len_comment_rx = re.compile(r'^(\d*:?\d+:\d{2})\s*\((.*)\)$')
        br_split_rx = parse_aside._br_split_rx = re.compile(r'<br/?>')

    unexpected_date_fmt = 'Unexpected release date format in: {}'
    parsed = {}
    for ele in aside.children:
        tag_type = ele.name
        if isinstance(ele, NavigableString) or tag_type in ('figure', 'section'):    # newline/image/footer
            continue

        key = ele.get('data-source')
        if not key or key == 'image':
            continue
        elif tag_type == 'h2':
            value = ele.text
        else:
            val_ele = list(ele.children)[-1]
            if isinstance(val_ele, NavigableString):
                val_ele = val_ele.previous_sibling

            if key == 'released':
                value = []
                for s in val_ele.stripped_strings:
                    cleaned_date = comma_fix_rx.sub(',', s)
                    try:
                        dt = parse_date(cleaned_date, source=val_ele)
                    except Exception as e:
                        if value and not value[-1][1]:
                            value[-1] = (value[-1][0], unsurround(s))
                        else:
                            m = date_comment_rx.match(s)
                            if m:
                                cleaned_date = comma_fix_rx.sub(',', m.group(1))
                                try:
                                    dt = parse_date(cleaned_date, source=val_ele)
                                except UnexpectedDateFormat as e1:
                                    raise e1
                                except Exception as e1:
                                    raise UnexpectedDateFormat(unexpected_date_fmt.format(val_ele)) from e1
                                else:
                                    value.append((dt, m.group(2)))
                            else:
                                if isinstance(e, UnexpectedDateFormat):
                                    raise e
                                raise UnexpectedDateFormat(unexpected_date_fmt.format(val_ele)) from e
                    else:
                        value.append((dt, None))
            elif key == 'length':
                value = []
                for s in val_ele.stripped_strings:
                    if len_rx.match(s):
                        value.append((s, None))
                    else:
                        m = len_comment_rx.match(s)
                        if m:
                            value.append(tuple(m.groups()))
                        elif value and value[-1] and not value[-1][1]:
                            value[-1] = (value[-1][0], unsurround(s))
                        else:
                            raise WikiEntityParseException('Unexpected length format on {} in: {}'.format(uri_path, val_ele))
            elif key == 'artist':
                value = list(map(str.strip, (soupify(line).text for line in br_split_rx.split(str(val_ele)))))
                # parsed['artists_raw'] = val_strs
                # anchors = list(val_ele.find_all('a'))
                # if anchors:
                #     value = dict(link_tuples(anchors))
                # else:
                #     value = {name: None for name in val_strs}
            elif key in ('agency', 'associated', 'composer', 'current', 'label', 'writer'):
                anchors = list(val_ele.find_all('a'))
                if anchors:
                    value = dict(link_tuples(anchors))
                    # value = {a.text: a.get('href') for a in anchors}
                else:
                    ele_children = list(val_ele.children)
                    if not isinstance(ele_children[0], NavigableString) and ele_children[0].name == 'ul':
                        value = {li.text: None for li in ele_children[0].find_all('li')}
                    else:
                        value = {name: None for name in str2list(val_ele.text)}
            elif key in ('format', ):
                ele_children = list(val_ele.children)
                if not isinstance(ele_children[0], NavigableString) and ele_children[0].name == 'ul':
                    value = [li.text for li in ele_children[0].find_all('li')]
                else:
                    value = str2list(val_ele.text)
            elif key == 'birth_name':
                try:
                    value = [split_name(s) for s in val_ele.stripped_strings]
                except ValueError as e:
                    value = []
                    for s in val_ele.stripped_strings:
                        for s_part in s.split(','):
                            value.append(split_name(s_part))
            else:
                value = val_ele.text
        parsed[key] = value
    return parsed


def parse_discography_entry(artist, ele, album_type, lang, type_idx, links):
    ele_text = ele.text.strip()
    try:
        parsed = ParentheticalParser().parse(ele_text)
    except Exception as e:
        log.warning('Unhandled discography entry format {!r} for {}'.format(ele_text, artist), extra={'red': True})
        return None

    # log.debug('Parsed {!r} => {}'.format(ele_text, parsed))
    # links = link_tuples(ele.find_all('a'))
    linkd = dict(links)
    try:
        num_type_rx = parse_discography_entry._num_type_rx
        song_list_rx = parse_discography_entry._song_list_rx
        year_rx = parse_discography_entry._year_rx
    except AttributeError:
        num_type_rx = parse_discography_entry._num_type_rx = re.compile(r'_\d$')
        song_list_rx = parse_discography_entry._song_list_rx = re.compile(r'^(["\']).+?\1 with .*$', re.IGNORECASE)
        year_rx = parse_discography_entry._year_rx = re.compile(r'((?:19|20)\d{2})')

    base_type = album_type and (album_type[:-2] if num_type_rx.search(album_type) else album_type).lower() or ''
    is_feature = base_type in ('features', 'collaborations_and_features')
    if is_feature and parsed[0].endswith('-'):
        primary_artist = parsed.pop(0)[:-1].strip()
        primary_uri = links[0][1] if links and links[0][0] == primary_artist else None
        # log.debug('Primary artist={}, links[0]={}'.format(primary_artist, links[0] if links else None))
    else:
        primary_artist = artist.english_name
        primary_uri = artist._uri_path

    year = int(parsed.pop()) if len(parsed[-1]) == 4 and parsed[-1].isdigit() else None
    year_was_last = year is not None
    try:
        if year is None and len(parsed[-2]) == 4 and parsed[-2].isdigit():
            year = int(parsed.pop(-2))
    except IndexError as e:
        years = year_rx.findall(ele_text)   # Live album with year in title may not have a separate (year)
        if len(years) == 1:
            year = int(years[0])
        else:
            log.debug('No year could be determined for {!r} from artist={}'.format(ele_text, artist))

    track_info = None
    title = parsed.pop(0)
    if ele_text.startswith('[') and not title.startswith('[') and not any(']' in part for part in parsed):
        title = '[{}]'.format(title)                    # Special case for albums '[+ +]' / '[X X]'
    elif not is_feature and len(parsed) == 1 and ele_text.endswith('"{}"'.format(parsed[0])):
        title = '{} "{}"'.format(title, parsed.pop(0))  # Special case for album name ending in quoted word
    elif 'singles' in base_type:
        try:
            track_info = parse_track_info(1, title, ele, client=artist._client, links=links)
        except TrackInfoParseException as e:
            if ':' in title and all(val.isdigit() for val in title.split(':')):
                track_info = {'num': 1, 'length': '-1:00', 'name_parts': (title,)}
            else:
                msg = '{}: Error processing single {!r} from {!r}'.format(artist, title, ele)
                raise WikiEntityParseException(msg) from e

        # log.debug('{!r} is a single - track info: {}'.format(title, track_info))
        if len(track_info['name_parts']) == 1:
            title = track_info['name_parts'][0]
        else:
            eng, cjk = track_info['name_parts']
            title = '{} ({})'.format(eng, cjk) if eng and cjk else eng or cjk
            if track_info.get('language'):
                title += ' ({} ver.)'.format(track_info['language'])

    # log.debug('year={!r}, base_type={!r}, title={!r}, remaining={}'.format(year, base_type, title, parsed))
    collabs, misc_info, songs = [], [], []
    for item in parsed:
        lc_item = item.lower()
        if lc_item.startswith(('with ', 'feat. ', 'feat ', 'as ')) or 'feat.' in lc_item:
            for collab in str2list(item, pat='^(?:with|feat\.?|as) | and |,|;|&| feat\.? | featuring | with '):
                try:
                    soloist, of_group = collab.split(' of ')
                except Exception as e:
                    try:
                        collabs.append({'artist': split_name(collab), 'artist_href': linkd.get(collab)})
                    except ValueError as e1:
                        soloist, of_group = split_name(collab, no_lang_check=True)
                        collabs.append({
                            'artist': split_name(soloist), 'artist_href': linkd.get(soloist),
                            'of_group': split_name(of_group), 'group_href': linkd.get(of_group),
                        })
                else:
                    collabs.append({
                        'artist': split_name(soloist), 'artist_href': linkd.get(soloist),
                        'of_group': split_name(of_group), 'group_href': linkd.get(of_group),
                    })
        elif base_type == 'osts' or song_list_rx.match(item):
            _tracks, _collabs = TrackListParser().parse(item, artist.url, tuple(ele.find_all('a')), artist._client)
            fmt = 'Found OST/song disco entry on {}: {} - tracks: {}, collabs: {}'
            log.log(8, fmt.format(artist.url, item, _tracks, _collabs))
            collabs.extend(_collabs)
            for track in _tracks:
                track['from_ost'] = base_type == 'osts'
                songs.append(track)
        else:
            misc_info.append(item)

    is_repackage = False
    if misc_info:
        for i, value in enumerate(misc_info):
            if value.lower() == 'repackage':
                is_repackage = True
                misc_info.pop(i)
                break

    if misc_info:
        if len(misc_info) > 1:
            log.debug('Unexpected misc_info length for {} - {!r}: {}'.format(artist, ele_text, misc_info))
        elif len(misc_info) == 1 and year_was_last:
            value = misc_info[0]
            lc_value = value.lower()
            lc_misc_parts = lc_value.split()
            misc_parts = value.split()
            replaced_part = False
            for i, lc_part in enumerate(lc_misc_parts):
                if lc_part in LANG_ABBREV_MAP:
                    misc_parts[i] = LANG_ABBREV_MAP[lc_part]
                    replaced_part = True
                    break

            title = '{} ({})'.format(title, ' '.join(misc_parts) if replaced_part else value)
            misc_info = []
        elif len(misc_info) == 1 and any(val in misc_info for val in ('pre-debut', 'digital')):
            pass
        else:
            fmt = '{}: Unexpected misc content in discography entry {!r} => title={!r}, misc: {}'
            log.debug(fmt.format(artist, ele_text, title, misc_info), extra={'color': 100})

    collab_names, collab_hrefs = set(), set()
    for collab in collabs:
        # log.debug('Collaborator for {}: {}'.format(title, collab))
        collab_names.add(collab['artist'][0])
        collab_hrefs.add(collab['artist_href'])
        of_group = collab.get('of_group')
        if of_group:
            collab_names.add(of_group[0])
            collab_hrefs.add(collab.get('group_href'))

    if artist.english_name not in collab_names or artist._uri_path not in collab_hrefs:
        if primary_artist != artist.english_name:
            collabs.append({'artist': (artist.english_name, artist.cjk_name), 'artist_href': artist._uri_path})
            collab_names.add(artist.english_name)
            collab_hrefs.add(artist._uri_path)

    is_feature_or_collab = base_type in ('features', 'collaborations', 'collaborations_and_features')
    is_ost = base_type in ('ost', 'osts')
    non_artist_links = [lnk for lnk in links if lnk[1] and lnk[1] != primary_uri and lnk[1] not in collab_hrefs]
    if non_artist_links:
        if len(non_artist_links) > 1:
            fmt = 'Too many non-artist links found in {}: {}\nFrom li: {}\nParsed parts: {}\nbase_type={}'
            raise WikiEntityParseException(fmt.format(artist.url, non_artist_links, ele, parsed, base_type))

        link_text, link_href = non_artist_links[0]
        if title != link_text and not is_feature_or_collab:
            # if is_feature_or_collab: likely a feature / single with a link to a collaborator
            # otherwise, it may contain an indication of the version of the album
            try:
                synonym_pats = parse_discography_entry._synonym_pats
            except AttributeError:
                pat_sets = defaultdict(set)
                for abbrev, canonical in LANG_ABBREV_MAP.items():
                    pat_sets[canonical].add(abbrev)
                synonym_pats = parse_discography_entry._synonym_pats = list(pat_sets.values()) + ['()[]-~']

            # if not any(title.replace('(', c).replace(')', c) == link_text for c in '-~'):
            if not (link_text.startswith(title) and any(c in link_text for c in '-~([')):
                if not synonym_pattern(link_text, synonym_pats).match(title):
                    log.debug('Unexpected first link text {!r} for album {!r}'.format(link_text, title))

        if link_href.startswith(('http://', 'https://')):
            url = urlparse(link_href)
            if url.hostname == 'en.wikipedia.org':
                uri_path = url.path[6:]
                wiki = 'en.wikipedia.org'
                # Probably a collaboration song, so title is likely a song and not the album title
            else:
                log.debug('Found link from {}\'s discography to unexpected site: {}'.format(artist, link_href))
                uri_path = None
                wiki = artist._client.host
                # wiki = 'kpop.fandom.com'
        else:
            uri_path = link_href or None
            wiki = artist._client.host
            # wiki = 'kpop.fandom.com'
    else:
        if is_ost:
            try:
                ost_rx = parse_discography_entry._ost_rx
            except AttributeError:
                ost_rx = parse_discography_entry._ost_rx = re.compile('(.*? OST).*')
            m = ost_rx.match(title)
            if m:
                non_part_title = m.group(1).strip()
                uri_path = non_part_title.replace(' ', '_')
            else:
                uri_path = title.replace(' ', '_')
            wiki = 'wiki.d-addicts.com'
        elif is_feature_or_collab:
            uri_path = None
            # wiki = 'kpop.fandom.com'
            wiki = artist._client.host
            # Probably a collaboration song, so title is likely a song and not the album title
        else:
            uri_path = None
            # wiki = 'kpop.fandom.com'
            wiki = artist._client.host
            # May be an album without a link, or a repackage detailed on the same page as the original

    info = {
        'title': normalize_roman_numerals(title), 'primary_artist': (primary_artist, primary_uri), 'type': album_type,
        'base_type': base_type, 'year': year, 'collaborators': collabs, 'misc_info': misc_info, 'language': lang,
        'uri_path': uri_path, 'wiki': wiki, 'is_feature_or_collab': is_feature_or_collab, 'is_ost': is_ost,
        'is_repackage': is_repackage, 'num': '{}{}'.format(type_idx, num_suffix(type_idx)),
        'track_info': track_info or songs
    }
    return info


def parse_discography_section(artist, clean_soup):
    try:
        discography_h2 = clean_soup.find('span', id='Discography').parent
    except AttributeError as e:
        log.log(9, 'No page content / discography was found for {}'.format(artist))
        return []

    entries = []
    h_levels = {'h3': 'language', 'h4': 'type'}
    lang, album_type = 'Korean', 'Unknown'
    ele = discography_h2.next_sibling
    tds = None
    while True:
        while not isinstance(ele, Tag):     # Skip past NavigableString objects
            if ele is None:
                if tds is not None:
                    try:
                        td = next(tds)
                    except StopIteration:
                        return entries
                    if td:
                        ele = td.find('h3')
                        lang = next(ele.children).get('id')
                        # log.debug('Processing next cell in discography table for {}: {}'.format(artist, ele.text))
                    else:
                        ele = None
                        # log.debug('No more cells in discography table for {}'.format(artist))
                else:
                    return entries
            ele = ele.next_sibling

        # log.debug('Processing {} in discography for {}: {}'.format(ele.name, artist, ele.text if ele.name not in ('ul', 'table', 'div') else '[{}]'.format(ele.name)))
        val_type = h_levels.get(ele.name)
        if val_type == 'language':  # *almost* always h3, but sometimes type is h3
            val = next(ele.children).get('id')
            val_lc = val.lower()
            if any(v in val_lc for v in ('album', 'single', 'collaboration', 'feature', 'mixtapes', 'osts')):
                h_levels[ele.name] = 'type'
                album_type = val
            else:
                lang = val
        elif val_type == 'type':
            album_type = next(ele.children).get('id')
        elif ele.name == 'ul':
            li_eles = list(ele.children)
            last_li = None
            from_ul = 0
            top_level_li_eles = li_eles.copy()
            num = 0
            while li_eles:
                li = li_eles.pop(0)
                if li in top_level_li_eles:
                    num += 1
                ul = li.find('ul')
                if ul:
                    try:
                        ul.extract()  # remove nested list from tree
                    except AttributeError as e:
                        log.error('{}: Error processing discography in ele: {}'.format(artist.url, ele))
                        raise e
                    nested_lis = list(ul.children)
                    _from_ul = len(nested_lis)
                    li_eles = nested_lis + li_eles  # insert elements from the nested list at top
                else:
                    _from_ul = 0

                links = link_tuples(li.find_all('a'))
                if not links and last_li and from_ul:
                    links = tuple((text, href) for text, href in link_tuples(last_li.find_all('a')) if text in li)
                entry = parse_discography_entry(artist, li, album_type, lang, num, links)
                if entry:
                    # log.debug('Adding disco entry for {}: type={} lang={} li={}'.format(artist, album_type, lang, li))
                    entries.append(entry)
                if _from_ul:
                    from_ul = _from_ul
                else:
                    from_ul -= 1
                last_li = li
        elif ele.name == 'table':
            tds = iter(ele.find_all('td'))
            ele = next(tds).find('h3')
            lang = next(ele.children).get('id')
            # log.debug('Processing first cell in discography table for {}: {}'.format(artist, ele.text))
        elif ele.name in ('h2', 'div'):
            break

        if ele.next_sibling is None and tds is not None:
            try:
                td = next(tds)
            except StopIteration:
                return entries
            if td:
                ele = td.find('h3')
                lang = next(ele.children).get('id')
                # log.debug('Processing next cell in discography table for {}: {}'.format(artist, ele.text))
            else:
                ele = None
                # log.debug('No more cells in discography table for {}'.format(artist))
        else:
            ele = ele.next_sibling
    return entries


def find_group_members(artist, clean_soup):
    """
    Find names and links to members of a group.

    :param WikiGroup artist:
    :param clean_soup: The :attr:`WikiEntity._clean_soup` value for an artist
    :return: Generator that yields 2-tuples of (uri_path, name (None|str|2-tuple of (eng, cjk)))
    """
    try:
        member_li_rx = find_group_members._member_li_rx
    except AttributeError:
        member_li_rx = find_group_members._member_li_rx = [
            re.compile(r'^([^(]+)\(([^,;]+)[,;]\s+([^,;]+)\)\s*-.*'),
            re.compile(r'(.*?)\s*-\s*(.*)'),
            re.compile(r'^(.*?)\s*\(([^;]+);\s*(.*)\)$'),
            re.compile(r'^[^()]+\([^()]+\)$'),
        ]

    members_span = clean_soup.find('span', id='Members')
    if members_span:
        members_h2 = members_span.parent
        members_container = members_h2
        for sibling in members_h2.next_siblings:
            if sibling.name in ('ul', 'table'):
                members_container = sibling
                break

        if members_container.name == 'ul':
            for li in members_container.find_all('li'):
                li_text = li.text.strip()
                a = li.find('a')
                href = normalize_href(a.get('href') if a else None)
                if href:
                    yield href, None
                else:
                    m = member_li_rx[0].match(li_text)
                    if m:
                        a, b, cjk = m.groups()
                        yield None, split_name((a if len(a) > len(b) else b, cjk))
                    else:
                        m = member_li_rx[1].match(li_text)
                        if m:
                            yield None, list(map(str.strip, m.groups()))[0]
                        else:
                            m = member_li_rx[2].match(li_text)
                            if m:
                                parts = m.groups()
                                langs = categorize_langs(parts)
                                if langs[0] == langs[2] == LangCat.ENG and langs[1] in LangCat.asian_cats:
                                    yield None, (parts[0], parts[1])
                                else:
                                    fmt = 'Unexpected member list item format on {}: {!r}'
                                    raise WikiEntityParseException(fmt.format(artist.url, li_text))
                            elif member_li_rx[3].match(li_text):
                                yield None, split_name(li_text)
                            else:
                                fmt = 'Unexpected member list item format on {}: {!r}'
                                raise WikiEntityParseException(fmt.format(artist.url, li_text))
        elif members_container.name == 'table':
            for tr in members_container.find_all('tr'):
                if tr.find('th'):
                    continue
                a = tr.find('a')
                href = normalize_href(a.get('href') if a else None)
                # log.debug('{}: Found member tr={}, href={!r}'.format(artist, tr, href))
                if href:
                    yield href, None
                else:
                    yield None, list(map(str.strip, (td.text.strip() for td in tr.find_all('td'))))[0]
    else:
        members_h2 = clean_soup.find('span', id='Graduated_members').parent
        for sibling in members_h2.next_siblings:
            if sibling.name == 'h3':
                pass  # Group name
            elif sibling.name == 'ul':
                for li in sibling.find_all('li'):
                    a = li.find('a')
                    href = normalize_href(a.get('href') if a else None)
                    if href:
                        yield href, None
                    else:
                        m = member_li_rx[0].match(li.text)
                        if m:
                            a, b, cjk = m.groups()
                            yield None, split_name((a if len(a) > len(b) else b, cjk))
                        else:
                            yield None, split_name(li.text)
                            # m = self._member_li_rx1.match(li.text)
                            # try:
                            #     yield None, list(map(str.strip, m.groups()))[0]
                            # except AttributeError as e:
                            #     yield None, split_name(li.text)
            elif sibling.name == 'h2':
                if not sibling.find('span', id='Past_members'):
                    break