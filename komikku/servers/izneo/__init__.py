# Copyright (C) 2020-2024 tijder
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: tijder
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import base64
import datetime
import hashlib
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import requests

from komikku.servers import Server
from komikku.servers.utils import do_login
from komikku.servers.utils import get_buffer_mime_type


class Izneo(Server):
    id = 'izneo'
    name = 'Izneo'
    lang = 'en'
    status = 'disabled'

    long_strip_genres = ['Webtoon', ]
    has_login = True

    base_url = 'https://www.izneo.com'
    cover_base_url = 'https://image.izneo.com'
    api_base_url = base_url + '/{0}/api/web'
    login_url = base_url + '/{0}/login'
    api_login_url = api_base_url + '/login'
    manga_url = base_url + '/{0}/{1}/{2}/{3}'
    api_manga_url = api_base_url + '/serie/{1}'
    api_library_url = api_base_url + '/library-v2'
    api_volumes_url = api_base_url + '/serie/{1}/volumes/old/{2}/{3}'
    api_others_url = api_base_url + '/serie/{1}/others/old/{2}/{3}'
    api_chapters_url = api_base_url + '/serie/{1}/chapters/old/{2}/{3}'
    api_chapter_url = base_url + '/book/{0}'
    cover_url = cover_base_url + '/{0}/images/album/{1}.jpg?v={2}'
    cover_search_url = cover_base_url + '/{0}/images/album/{1}-170or260.jpg?v={2}'

    def __init__(self, username=None, password=None):
        if username and password:
            self.do_login(username, password)

    @do_login
    def get_manga_data(self, initial_data):
        """
        Returns comic data from API

        Initial data should contain at least comic's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial_data'
        r = self.session_get(self.api_manga_url.format(self.lang, initial_data['slug']))
        if r.status_code != 200:
            return None

        resp_data = r.json()

        data = initial_data.copy()
        data.update(dict(
            name=resp_data['name'],
            authors=[author['name'] for author in resp_data['authors']],
            scanlators=[],
            genres=[resp_data['genre']['name']],
            status='ongoing',
            chapters=[],
            synopsis=resp_data['synopsis'],
            cover=None,
            server_id=self.id,
            url=self.manga_url.format(self.lang, resp_data['shelf']['slug'], resp_data['genre']['slug'], resp_data['forUrl']),
        ))

        if cover_id := resp_data.get('cover'):
            data['cover'] = self.cover_url.format(self.lang, cover_id, resp_data.get('coverVersion', 'undefined'))
        if resp_data['isWebtoon']:
            data['genres'].append('Webtoon')

        # Volumes/Chapters/Others
        kinds = {
            'volumes': self.api_volumes_url,
            'chapters': self.api_chapters_url,
            'others': self.api_others_url,
        }
        limit = 20
        for kind, api_url in kinds.items():
            offset = 0
            while offset is not None:
                r = self.session_get(api_url.format(self.lang, initial_data['slug'], offset, limit))
                resp_data = r.json()
                if not resp_data['albums']:
                    offset = None
                    continue

                for item in resp_data['albums']:
                    if not item['inUserLibrary']:
                        continue

                    title = item['title']
                    if item['volume']:
                        title = '{0} - {1}'.format(item['volume'], title)

                    data['chapters'].append(dict(
                        slug=item['id'],
                        title=title,
                        date=datetime.datetime.fromtimestamp(item['version']).date(),
                    ))

                offset += limit

        return data

    @do_login
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns comic chapter data

        Currently, only pages are expected.
        """
        r = self.session_get(self.api_chapter_url.format(chapter_slug))
        if r.status_code != 200:
            return None

        resp_data = r.json()
        if resp_data['status'] != 'ok':
            return None

        data = dict(
            pages=[],
        )
        for page in r.json()['data']['pages']:
            data['pages'].append(dict(
                slug=None,
                image=page['src'],
                key=page['key'],
                iv=page['iv'],
            ))

        return data

    @do_login
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
            headers={
                'Origin': self.base_url,
                'Referer': self.base_url + '/',
            }
        )
        if r.status_code != 200:
            return None

        cipher = Cipher(algorithms.AES(base64.b64decode(page['key'])), modes.CBC(base64.b64decode(page['iv'])))
        decryptor = cipher.decryptor()
        content = decryptor.update(r.content) + decryptor.finalize()
        mime_type = get_buffer_mime_type(content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=content,
            mime_type=mime_type,
            name=page['image'].split('?')[0].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns comic absolute URL
        """
        return url

    @do_login
    def get_most_populars(self):
        """
        Returns all comics available in user's collection
        """
        return self.search('')

    def login(self, username, password):
        if not username or not password:
            return False

        cookie = requests.cookies.create_cookie(
            name='lang',
            value=self.lang,
            domain=urlparse(self.base_url).netloc,
            path='/',
            expires=(datetime.datetime.now() + datetime.timedelta(days=365)).timestamp(),
        )
        self.session.cookies.set_cookie(cookie)

        r = self.session_get(self.login_url.format(self.lang))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        r = self.session_post(
            self.api_login_url.format(self.lang),
            json={
                'login': username,
                'password': hashlib.md5(password.encode()).hexdigest(),
                'rememberMe': True,
            },
            headers={
                'Origin': self.base_url,
                'Referer': self.login_url.format(self.lang),
            }
        )

        self.save_session()

        return True

    @do_login
    def search(self, term):
        """
        Searches in user's collection
        """
        results = []
        offset = 0

        while offset is not None:
            r = self.session_post(
                self.api_library_url.format(self.lang),
                json={
                    "search": term,
                    "itemType": "series",
                    "order": "order-date",
                    "offset": offset,
                    "limit": 30,
                    "collection": None,
                    "genre": None,
                    "shelf": None,
                    "hide-marked-as-read": None,
                    "show-removed": False,
                },
                headers={
                    'Origin': self.base_url,
                    'Referer': self.base_url + '/{0}/bibliotheque'.format(self.lang),
                }
            )
            if r.status_code != 200:
                return None

            try:
                resp_data = r.json()
            except Exception:
                return None

            if not resp_data['totalSeries']:
                break

            for serie in resp_data['series']:
                results.append(dict(
                    name=serie['name'],
                    slug=serie['id'],
                    cover=self.cover_search_url.format(self.lang, serie['coverEan'], serie['version']),
                ))

            offset += resp_data['limit'][1]
            if offset > resp_data['totalSeries']:
                # No more comics to load
                offset = None

        return results


class Izneo_de(Izneo):
    id = 'izneo_de'
    name = 'Izneo'
    lang = 'de'
    status = 'disabled'


class Izneo_fr(Izneo):
    id = 'izneo_fr'
    name = 'Izneo'
    lang = 'fr'
    status = 'enabled'


class Yieha(Izneo):
    id = 'yieha:izneo'
    name = 'Yieha'
    lang = 'nl'
    status = 'disabled'
