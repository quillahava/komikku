# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

#
# API doc: https://api.mangadex.org
#

from gettext import gettext as _
from functools import lru_cache
import html
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from uuid import UUID

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.exceptions import NotFoundError
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

logger = logging.getLogger('komikku.servers.mangadex')

SERVER_NAME = 'MangaDex'

CHAPTERS_PER_REQUEST = 100
SEARCH_RESULTS_LIMIT = 100


class Mangadex(Server):
    id = 'mangadex'
    name = SERVER_NAME
    lang = 'en'
    lang_code = 'en'
    is_nsfw = True
    long_strip_genres = ['Long Strip', ]

    base_url = 'https://mangadex.org'
    api_base_url = 'https://api.mangadex.org'
    api_manga_base = api_base_url + '/manga'
    api_manga_url = api_manga_base + '/{0}'
    api_chapter_base = api_base_url + '/chapter'
    api_chapter_url = api_chapter_base + '/{0}'
    api_author_base = api_base_url + '/author'
    api_cover_url = api_base_url + '/cover/{0}'
    api_scanlator_base = api_base_url + '/group'
    api_server_url = api_base_url + '/at-home/server/{0}'

    manga_url = base_url + '/title/{0}'
    page_image_url = '{0}/data/{1}/{2}'
    cover_url = 'https://uploads.mangadex.org/covers/{0}/{1}.256.jpg'

    filters = [
        {
            'key': 'ratings',
            'type': 'select',
            'name': _('Rating'),
            'description': _('Filter by content ratings'),
            'value_type': 'multiple',
            'options': [
                {'key': 'safe', 'name': _('Safe'), 'default': True},
                {'key': 'suggestive', 'name': _('Suggestive'), 'default': True},
                {'key': 'erotica', 'name': _('Erotica'), 'default': False},
                {'key': 'pornographic', 'name': _('Pornographic'), 'default': False},
            ]
        },
        {
            'key': 'statuses',
            'type': 'select',
            'name': _('Status'),
            'description': _('Filter by statuses'),
            'value_type': 'multiple',
            'options': [
                {'key': 'ongoing', 'name': _('Ongoing'), 'default': False},
                {'key': 'completed', 'name': _('Completed'), 'default': False},
                {'key': 'hiatus', 'name': _('Paused'), 'default': False},
                {'key': 'cancelled', 'name': _('Canceled'), 'default': False},
            ]
        },
        {
            'key': 'publication_demographics',
            'type': 'select',
            'name': _('Publication Demographic'),
            'description': _('Filter by publication demographics'),
            'value_type': 'multiple',
            'options': [
                {'key': 'shounen', 'name': _('Shounen'), 'default': False},
                {'key': 'shoujo', 'name': _('Shoujo'), 'default': False},
                {'key': 'josei', 'name': _('Josei'), 'default': False},
                {'key': 'seinen', 'name': _('Seinen'), 'default': False},
            ]
        },
    ]

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

            retry = Retry(total=5, backoff_factor=1, respect_retry_after_header=False, status_forcelist=Retry.RETRY_AFTER_STATUS_CODES)
            self.session.mount(self.api_base_url, HTTPAdapter(max_retries=retry))

    @staticmethod
    def get_group_name(group_id, groups_list):
        """Get group name from group id"""
        matching_group = [group for group in groups_list if group['id'] == group_id]

        return matching_group[0]['name']

    def __convert_old_slug(self, slug, type):
        # Removing this will break manga that were added before the change to the manga slug
        slug = slug.split('/')[0]
        try:
            return str(UUID(slug, version=4))
        except ValueError:
            r = self.session_post(self.api_base_url + '/legacy/mapping', json={
                'type': type,
                'ids': [int(slug)],
            })
            if r.status_code != 200:
                return None

            for result in r.json():
                if result['result'] == 'ok' and str(result['data']['attributes']['legacyId']) == slug:
                    return result['data']['attributes']['newId']

            return None

    def __get_manga_title(self, attributes):
        # Check if title is available in server language
        if self.lang_code in attributes['title']:
            return attributes['title'][self.lang_code]

        # Fallback to English title
        if 'en' in attributes['title']:
            return attributes['title']['en']

        # Search in alternative titles
        # NOTE: Some weird stuff can happen here. For ex., French translations that are in German!
        for alt_title in attributes['altTitles']:
            if self.lang_code in alt_title:
                return alt_title[self.lang_code]

            if 'en' in alt_title:
                return alt_title['en']

        # Last resort
        if len(attributes['title']) > 0:
            return list(attributes['title'].values())[0]

        return None

    @lru_cache(maxsize=1)
    def __get_chapter_json(self, chapter_slug):
        r = self.session_get(self.api_server_url.format(chapter_slug))
        if r.status_code != 200:
            return None

        return r.json()

    def get_manga_data(self, initial_data):
        """
        Returns manga data from API

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        slug = self.__convert_old_slug(initial_data['slug'], type='manga')
        if slug is None:
            raise NotFoundError

        r = self.session_get(self.api_manga_url.format(slug), params={'includes[]': ['author', 'artist', 'cover_art']})
        if r.status_code != 200:
            return None

        resp_json = r.json()

        data = initial_data.copy()
        data.update(dict(
            slug=slug,
            authors=[],
            scanlators=[],
            genres=[],
            status=None,
            cover=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
        ))

        attributes = resp_json['data']['attributes']

        _name = self.__get_manga_title(attributes)
        data['name'] = html.unescape(_name)
        assert data['name'] is not None

        for relationship in resp_json['data']['relationships']:
            if relationship['type'] == 'author':
                data['authors'].append(relationship['attributes']['name'])
            elif relationship['type'] == 'cover_art':
                data['cover'] = self.cover_url.format(slug, relationship['attributes']['fileName'])

        # NOTE: not suitable translations for genres
        data['genres'] = [tag['attributes']['name']['en'] for tag in attributes['tags']]

        if attributes['status'] == 'ongoing':
            data['status'] = 'ongoing'
        elif attributes['status'] == 'completed':
            data['status'] = 'complete'
        elif attributes['status'] == 'cancelled':
            data['status'] = 'suspended'
        elif attributes['status'] == 'hiatus':
            data['status'] = 'hiatus'

        if self.lang_code in attributes['description']:
            data['synopsis'] = html.unescape(attributes['description'][self.lang_code])
        elif 'en' in attributes['description']:
            # Fall back to english synopsis
            data['synopsis'] = html.unescape(attributes['description']['en'])
        else:
            logger.warning('{}: No synopsis', data['name'])

        data['chapters'] += self.resolve_chapters(data['slug'])

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data from API

        Currently, only pages are expected.
        """
        r = self.session_get(self.api_chapter_url.format(chapter_slug), params={'includes[]': ['scanlation_group']})
        if r.status_code == 404:
            raise NotFoundError
        if r.status_code != 200:
            return None

        data = r.json()['data']

        attributes = data['attributes']
        title = f'#{attributes["chapter"]}'
        if attributes['title']:
            title = f'{title} - {attributes["title"]}'

        scanlators = [rel['attributes']['name'] for rel in data['relationships'] if rel['type'] == 'scanlation_group']
        data = dict(
            slug=chapter_slug,
            title=title,
            pages=[dict(index=page, image=None) for page in range(0, attributes['pages'])],
            date=convert_date_string(attributes['publishAt'].split('T')[0], format='%Y-%m-%d'),
            scanlators=scanlators,
        )

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        chapter_json = self.__get_chapter_json(chapter_slug)
        if chapter_json is None:
            self.__get_chapter_json.cache_clear()
            return None

        server_url = chapter_json['baseUrl']
        chapter_hash = chapter_json['chapter']['hash']
        slug = None
        if 'data' in chapter_json['chapter']:
            slug = chapter_json['chapter']['data'][page['index']]
        else:
            slug = chapter_json['chapter']['dataSaver'][page['index']]

        r = self.session_get(self.page_image_url.format(server_url, chapter_hash, slug))
        if r.status_code != 200:
            self.__get_chapter_json.cache_clear()
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=slug,
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self, ratings=None, statuses=None, publication_demographics=None):
        params = {
            'limit': SEARCH_RESULTS_LIMIT,
            'contentRating[]': ratings,
            'translatedLanguage[]': [self.lang_code],
            'order[publishAt]': 'desc',
            'includeFutureUpdates': '0',
            'includeFuturePublishAt': '0',
            'includeEmptyPages': '0',
            'includes[]': ['manga'],  # expand manga relationships with their attributes
        }

        r = self.session_get(self.api_chapter_base, params=params)
        if r.status_code != 200:
            return None

        results = []
        manga_slugs = set()
        for result in r.json()['data']:
            for relationship in result['relationships']:
                if relationship['type'] != 'manga':
                    continue

                slug = relationship['id']
                if slug in manga_slugs:
                    continue

                if name := self.__get_manga_title(relationship['attributes']):
                    results.append(dict(
                        slug=slug,
                        name=name,
                    ))
                    manga_slugs.add(slug)
                else:
                    logger.warning(f'Ignoring result {slug}, missing name')

        return results

    def get_most_populars(self, ratings=None, statuses=None, publication_demographics=None):
        return self.search('', ratings)

    def resolve_chapters(self, manga_slug):
        chapters = []
        offset = 0

        while True:
            r = self.session_get(self.api_chapter_base, params={
                'manga': manga_slug,
                'translatedLanguage[]': [self.lang_code],
                'limit': CHAPTERS_PER_REQUEST,
                'offset': offset,
                'order[chapter]': 'asc',
                'includes[]': ['scanlation_group'],
                'contentRating[]': ['safe', 'suggestive', 'erotica', 'pornographic'],
            })
            if r.status_code == 204:
                break
            if r.status_code != 200:
                return None

            results = r.json()['data']

            for chapter in results:
                attributes = chapter['attributes']

                title = f'#{attributes["chapter"]}'
                if attributes['title']:
                    title = f'{title} - {attributes["title"]}'

                scanlators = [rel['attributes']['name'] for rel in chapter['relationships'] if rel['type'] == 'scanlation_group']

                data = dict(
                    slug=chapter['id'],
                    title=title,
                    date=convert_date_string(attributes['publishAt'].split('T')[0], format='%Y-%m-%d'),
                    scanlators=scanlators,
                )
                chapters.append(data)

            if len(results) < CHAPTERS_PER_REQUEST:
                break

            offset += CHAPTERS_PER_REQUEST

        return chapters

    def search(self, term, ratings=None, statuses=None, publication_demographics=None):
        params = {
            'limit': SEARCH_RESULTS_LIMIT,
            'contentRating[]': ratings,
            'status[]': statuses,
            'publicationDemographic[]': publication_demographics,
            'availableTranslatedLanguage[]': [self.lang_code, ],
            'order[followedCount]': 'desc',
        }
        if term:
            params['title'] = term

        r = self.session_get(self.api_manga_base, params=params)
        if r.status_code != 200:
            return None

        results = []
        for result in r.json()['data']:
            name = self.__get_manga_title(result['attributes'])

            if name:
                results.append(dict(
                    slug=result['id'],
                    name=name,
                ))
            else:
                logger.warning('Ignoring result {}, missing name'.format(result['id']))

        return results


class Mangadex_cs(Mangadex):
    id = 'mangadex_cs'
    name = SERVER_NAME
    lang = 'cs'
    lang_code = 'cs'


class Mangadex_de(Mangadex):
    id = 'mangadex_de'
    name = SERVER_NAME
    lang = 'de'
    lang_code = 'de'


class Mangadex_es(Mangadex):
    id = 'mangadex_es'
    name = SERVER_NAME
    lang = 'es'
    lang_code = 'es'


class Mangadex_es_419(Mangadex):
    id = 'mangadex_es_419'
    name = SERVER_NAME
    lang = 'es_419'
    lang_code = 'es-la'


class Mangadex_fr(Mangadex):
    id = 'mangadex_fr'
    name = SERVER_NAME
    lang = 'fr'
    lang_code = 'fr'


class Mangadex_id(Mangadex):
    id = 'mangadex_id'
    name = SERVER_NAME
    lang = 'id'
    lang_code = 'id'


class Mangadex_it(Mangadex):
    id = 'mangadex_it'
    name = SERVER_NAME
    lang = 'it'
    lang_code = 'it'


class Mangadex_ja(Mangadex):
    id = 'mangadex_ja'
    name = SERVER_NAME
    lang = 'ja'
    lang_code = 'ja'


class Mangadex_ko(Mangadex):
    id = 'mangadex_ko'
    name = SERVER_NAME
    lang = 'ko'
    lang_code = 'kr'


class Mangadex_nl(Mangadex):
    id = 'mangadex_nl'
    name = SERVER_NAME
    lang = 'nl'
    lang_code = 'nl'


class Mangadex_pl(Mangadex):
    id = 'mangadex_pl'
    name = SERVER_NAME
    lang = 'pl'
    lang_code = 'pl'


class Mangadex_pt(Mangadex):
    id = 'mangadex_pt'
    name = SERVER_NAME
    lang = 'pt'
    lang_code = 'pt'


class Mangadex_pt_br(Mangadex):
    id = 'mangadex_pt_br'
    name = SERVER_NAME
    lang = 'pt_BR'
    lang_code = 'pt-br'


class Mangadex_ru(Mangadex):
    id = 'mangadex_ru'
    name = SERVER_NAME
    lang = 'ru'
    lang_code = 'ru'


class Mangadex_th(Mangadex):
    id = 'mangadex_th'
    name = SERVER_NAME
    lang = 'th'
    lang_code = 'th'


class Mangadex_uk(Mangadex):
    id = 'mangadex_uk'
    name = SERVER_NAME
    lang = 'uk'
    lang_code = 'uk'


class Mangadex_vi(Mangadex):
    id = 'mangadex_vi'
    name = SERVER_NAME
    lang = 'vi'
    lang_code = 'vi'


class Mangadex_zh_hans(Mangadex):
    id = 'mangadex_zh_hans'
    name = SERVER_NAME
    lang = 'zh_Hans'
    lang_code = 'zh'


class Mangadex_zh_hant(Mangadex):
    id = 'mangadex_zh_hant'
    name = SERVER_NAME
    lang = 'zh_Hant'
    lang_code = 'zh-hk'
