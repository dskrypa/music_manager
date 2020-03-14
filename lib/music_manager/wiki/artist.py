"""
Artist wiki pages.

:author: Doug Skrypa
"""

import logging
from datetime import datetime
from traceback import format_exc

from ordered_set import OrderedSet

from ds_tools.compat import cached_property
from wiki_nodes.http import MediaWikiClient
from wiki_nodes.nodes import Table, List, Link, String, CompoundNode, Template
from ..text.extraction import partition_enclosed
from ..text.name import Name
from .base import PersonOrGroup
from .discography import DiscographyEntryFinder, Discography, DiscographyMixin
from .disco_entry import DiscoEntry, DiscoEntryType
from .parsing.generasia import parse_generasia_album_name

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup, DiscographyMixin):
    _categories = ()

    @cached_property
    def name(self):
        names = self.names
        if not names:
            raise AttributeError(f'This {self.__class__.__name__} has no \'name\' attribute')
        if len(names) == 1:
            return next(iter(names))
        _name = self._name.lower()
        candidate = None
        for name in names:
            if _name in (name.eng_lower, name.non_eng):
                if name.english and name.non_eng:
                    return name
                else:
                    candidate = name
        return candidate or next(iter(names))

    @cached_property
    def names(self):
        names = OrderedSet()
        for site, artist_page in self._pages.items():
            if site == 'kpop.fandom.com':
                pass
            elif site == 'en.wikipedia.org':
                pass
            elif site == 'www.generasia.com':
                names.update(self._process_generasia_name(artist_page))
            elif site == 'wiki.d-addicts.com':
                pass
            else:
                log.debug(f'No name extraction is configured for {artist_page}')
        if not names:
            names.add(Name(self._name))
        return names

    def _process_generasia_name(self, artist_page):
        # From intro ===========================================================================================
        first_string = artist_page.intro[0].value
        name = first_string[:first_string.rindex(')') + 1]
        # log.debug(f'Found name: {name}')
        first_part, paren_part, _ = partition_enclosed(name, reverse=True)
        try:
            parts = tuple(map(str.strip, paren_part.split(', and')))
        except Exception:
            yield Name.from_parts((first_part, paren_part))
        else:
            if len(parts) == 1:
                yield Name.from_parts((first_part, paren_part))
            else:
                for part in parts:
                    try:
                        part = part[:part.rindex(')') + 1]
                    except ValueError:
                        log.error(f'Error splitting part={part!r}')
                        raise
                    else:
                        part_a, part_b, _ = partition_enclosed(part, reverse=True)
                        try:
                            romanized, alias = part_b.split(' or ')
                        except ValueError:
                            yield Name.from_parts((first_part, part_a, part_b))
                        else:
                            yield Name.from_parts((first_part, part_a, romanized))
                            yield Name.from_parts((alias, part_a, romanized))

        # From profile =========================================================================================
        try:
            section = artist_page.sections.find('Profile')
        except KeyError:
            pass
        else:
            profile = section.content.as_mapping(multiline=False)
            for key in ('Stage Name', 'Real Name'):
                try:
                    value = profile[key].value
                except KeyError:
                    pass
                else:
                    yield Name.from_enclosed(value)

    def _finder_with_entries(self):
        finder = DiscographyEntryFinder()
        for site, artist_page in self._pages.items():
            client = MediaWikiClient(site)
            if site == 'www.generasia.com':
                self._process_generasia_disco_sections(client, artist_page, finder)
            elif site == 'wiki.d-addicts.com':
                self._process_drama_wiki_disco_sections(client, artist_page, finder)
            elif site == 'kpop.fandom.com':
                self._process_kpop_fandom_disco_sections(client, artist_page, finder)
            elif site == 'en.wikipedia.org':
                self._process_wikipedia_disco_sections(client, artist_page, finder)
            else:
                log.debug(f'No discography entry extraction is configured for {artist_page}')
        return finder

    def _process_generasia_disco_sections(self, client, artist_page, finder):
        for section_prefix in ('', 'Korean ', 'Japanese ', 'International '):
            try:
                section = artist_page.sections.find(f'{section_prefix}Discography')
            except KeyError:
                continue
            lang = section_prefix.strip() if section_prefix in ('Korean ', 'Japanese ') else None
            for alb_type, alb_type_section in section.children.items():
                if 'video' in alb_type.lower():
                    continue
                de_type = DiscoEntryType.for_name(alb_type)
                content = alb_type_section.content
                for entry in content.iter_flat():
                    try:
                        self._process_generasia_disco_entry(client, artist_page, finder, de_type, entry, lang)
                    except Exception as e:
                        msg = f'Unexpected error processing section={section} entry={entry}: {format_exc()}'
                        log.error(msg, extra={'color': 'red'})

    def _process_generasia_disco_entry(self, client, artist_page, finder, de_type, entry, lang=None):
        log.debug(f'Processing {parse_generasia_album_name(entry)!r}')
        entry_type = de_type                                    # Except for collabs with a different primary artist
        entry_link = next(entry.find_all(Link, True), None)     # Almost always the 1st link
        song_title = entry_link.show if entry_link else None

        """
        [YYYY.MM.DD] {Album title: romanized OR english} [(repackage)]
        [YYYY.MM.DD] {Album title: romanized (english)} [(hangul)]
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])]
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])] (collaborators)
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])] (primary artist feat. collaborators)
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])] (feat. collaborators)
        [YYYY.MM.DD] {primary artist} - {Album title: romanized OR english} (#track_num track title (feat. collaborators))
        [YYYY.MM.DD] {primary artist} - {Album title: romanized OR english} (#track_num track title feat. collaborators)
        """

        parts = len(entry)
        if parts == 2:
            # [date] title
            pass
        elif parts >= 3:
            if isinstance(entry[2], String):
                entry_2 = entry[2].value
                if check_type(entry, 3, Link) and de_type == DiscoEntryType.Collaboration:
                    if entry_2 == '-':
                        # 1st link = primary artist, 2nd link = disco entry
                        entry_type = DiscoEntryType.Feature
                        entry_link = entry[3]
                        if check_type(entry, 4, String) and not entry[4].lower.startswith('(feat'):
                            # [date] primary - album (song (feat artists))
                            song_title = entry[4].value[1:].partition('(')[0]
                    elif entry_2 == '(' and check_type(entry, 4, String) and entry[4].lower.startswith('feat'):
                        # [date] single (primary feat collaborators)
                        pass

        first_str = entry[0].value
        date = datetime.strptime(first_str[:first_str.index(']')], '[%Y.%m.%d').date()
        # noinspection PyTypeChecker
        disco_entry = DiscoEntry(
            artist_page, entry, type_=entry_type, lang=lang, date=date, link=entry_link, song=song_title
        )
        if entry_link:
            finder.add_entry_link(client, entry_link, disco_entry)
        else:
            if isinstance(entry[1], String):
                disco_entry.title = entry[1].value
            finder.add_entry(disco_entry, entry)

    def _process_kpop_fandom_disco_sections(self, client, artist_page, finder):
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            return

        if section.depth == 1:
            for alb_type, alb_type_section in section.children.items():
                try:
                    self._process_kpop_fandom_disco_section(client, artist_page, finder, alb_type_section, alb_type)
                except Exception as e:
                    msg = f'Unexpected error processing section={section}: {format_exc()}'
                    log.error(msg, extra={'color': 'red'})
        elif section.depth == 2:  # key = language, value = sub-section
            for lang, lang_section in section.children.items():
                for alb_type, alb_type_section in lang_section.children.items():
                    # log.debug(f'{at_section}: {at_section.content}')
                    try:
                        self._process_kpop_fandom_disco_section(
                            client, artist_page, finder, alb_type_section, alb_type, lang
                        )
                    except Exception as e:
                        msg = f'Unexpected error processing section={section}: {format_exc()}'
                        log.error(msg, extra={'color': 'red'})
        else:
            log.warning(f'Unexpected section depth: {section.depth}')

    def _process_kpop_fandom_disco_section(self, client, artist_page, finder, section, alb_type, lang=None):
        content = section.content
        if type(content) is CompoundNode:  # A template for splitting the discography into
            content = content[0]  # columns follows the list of albums in this section
        for entry in content.iter_flat():
            # {primary artist} - {album or single} [(with collabs)] (year)
            if isinstance(entry, String):
                year_str = entry.value.rsplit(maxsplit=1)[1]
            else:
                year_str = entry[-1].value.split()[-1]

            year = datetime.strptime(year_str, '(%Y)').year
            disco_entry = DiscoEntry(artist_page, entry, type_=alb_type, lang=lang, year=year)

            if isinstance(entry, CompoundNode):
                links = list(entry.find_all(Link, True))
                if alb_type == 'Features':
                    # {primary artist} - {album or single} [(with collabs)] (year)
                    if isinstance(entry[1], String):
                        entry_1 = entry[1].value.strip()
                        if entry_1 == '-' and check_type(entry, 2, Link):
                            link = entry[2]
                            links = [link]
                            disco_entry.title = link.show
                        elif entry_1.startswith('-'):
                            disco_entry.title = entry_1[1:].strip(' "')
                    elif isinstance(entry[1], Link):
                        disco_entry.title = entry[1].show
                else:
                    if isinstance(entry[0], Link):
                        disco_entry.title = entry[0].show
                    elif isinstance(entry[0], String):
                        disco_entry.title = entry[0].value.strip(' "')

                if links:
                    for link in links:
                        finder.add_entry_link(client, link, disco_entry)
                else:
                    finder.add_entry(disco_entry, entry)
            elif isinstance(entry, String):
                disco_entry.title = entry.value.split('(')[0].strip(' "')
                finder.add_entry(disco_entry, entry)
            else:
                log.warning(f'On page={artist_page}, unexpected type for entry={entry!r}')

    def _process_drama_wiki_disco_sections(self, client, artist_page, finder):
        try:
            section = artist_page.sections.find('TV Show Theme Songs')
        except KeyError:
            return
        # Typical format: {song title} [by {member}] - {soundtrack title} ({year})
        for entry in section.content.iter_flat():
            year = datetime.strptime(entry[-1].value.split()[-1], '(%Y)').year
            disco_entry = DiscoEntry(artist_page, entry, type_='Soundtrack', year=year)
            links = list(entry.find_all(Link, True))
            if not finder.add_entry_links(client, links, disco_entry):
                if isinstance(entry[-2], String):
                    disco_entry.title = entry[-2].value
                finder.add_entry(disco_entry, entry)

    def _process_wikipedia_disco_sections(self, client, artist_page, finder):
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            log.debug(f'No discography section found for {artist_page}')
            return
        try:
            disco_page_link_tmpl = section.content[0]
        except Exception as e:
            log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
            return

        if isinstance(disco_page_link_tmpl, Template) and disco_page_link_tmpl.name.lower() == 'main':
            try:
                disco_page_title = disco_page_link_tmpl.value[0].value
            except Exception as e:
                log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
            else:
                disco_entity = Discography.from_page(client.get_page(disco_page_title))
                disco_entity._process_entries(finder)
        else:
            log.debug(f'Unexpected discography section format on {artist_page}')


def check_type(node, index, cls):
    try:
        return isinstance(node[index], cls)
    except (IndexError, KeyError, TypeError):
        return False


class Singer(Artist):
    _categories = ('singer', 'actor', 'actress', 'member', 'rapper')


class Group(Artist):
    _categories = ('group',)

    @cached_property
    def members(self):
        # TODO: Handle no links / incomplete links
        for site, page in self._pages.items():
            try:
                content = page.sections.find('Members').content
            except (KeyError, AttributeError):
                continue

            if type(content) is CompoundNode:
                for node in content:
                    if isinstance(node, (Table, List)):
                        content = node
                        break

            titles = []
            if isinstance(content, Table):
                for row in content:
                    name = row.get('Name', row.get('name'))
                    if name:
                        if isinstance(name, Link):
                            titles.append(name.title)
                        elif isinstance(name, String):
                            titles.append(name.value)
                        else:
                            log.warning(f'Unexpected name type: {name!r}')
            elif isinstance(content, List):
                for entry in content.iter_flat():
                    if isinstance(entry, Link):
                        titles.append(entry.title)
                    elif isinstance(entry, CompoundNode):
                        link = next(entry.find_all(Link, True), None)
                        if link:
                            titles.append(link.title)
                    elif isinstance(entry, String):
                        titles.append(entry.value)
                    else:
                        log.warning(f'Unexpected name type: {entry!r}')

            if titles:
                client = MediaWikiClient(site)
                pages = client.get_pages(titles)
                return [Singer.from_page(member) for member in pages.values()]
        return []

    @cached_property
    def sub_units(self):
        # TODO: implement
        return None
