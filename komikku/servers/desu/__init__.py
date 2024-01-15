# Copyright (C) 2020-2024 GrownNed
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: GrownNed <grownned@gmail.com>

from datetime import datetime
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type

SERVER_NAME = 'Desu'

headers = {
    'User-Agent': USER_AGENT,
}


class Desu(Server):
    id = 'desu'
    name = SERVER_NAME
    lang = 'ru'
    is_nsfw = True

    base_url = 'https://desu.me'
    api_url = base_url + '/manga/api/'
    api_latest_updates_url = base_url + '/manga/api?limit=50&order=updated'
    api_most_populars_url = base_url + '/manga/api?limit=50&order=popular'
    api_manga_url = base_url + '/manga/api/{0}'
    api_chapter_url = base_url + '/manga/api/{0}/chapter/{1}'
    api_search_url = base_url + '/manga/api?limit=50&search={0}'

    manga_title_css_selector = 'h1 > span.name'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = headers

    def get_manga_data(self, initial_data):
        """
        Returns manga data from API

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(self.api_manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        resp_data = r.json()['response']

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
        ))

        data['name'] = resp_data['russian']
        data['url'] = resp_data['url']
        data['cover'] = resp_data['image']['original']

        if resp_data.get('translators'):
            data['scanlators'] = [t['name'] for t in resp_data['translators']]
        data['genres'] = [genre['russian'] for genre in resp_data['genres']]
        if resp_data['status'] == 'ongoing':
            data['status'] = 'ongoing'
        elif resp_data['status'] == 'released':
            data['status'] = 'complete'
        data['synopsis'] = resp_data['description']

        for chapter in reversed(resp_data['chapters']['list']):
            title = '#{0}'.format(chapter['ch'])
            if chapter['title']:
                title = '{0} - {1}'.format(title, chapter['title'])

            data['chapters'].append(dict(
                slug=chapter['id'],
                title=title,
                date=datetime.fromtimestamp(chapter['date']).date(),
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data from API

        Currently, only pages are expected.
        """
        r = self.session_get(self.api_chapter_url.format(manga_slug, chapter_slug))
        if r.status_code != 200:
            return None

        resp_data = r.json()['response']

        data = dict(
            pages=[],
        )
        for page in resp_data['pages']['list']:
            data['pages'].append(dict(
                slug=None,
                image=page['img'],
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(page['image'], headers={'Referer': self.base_url})
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=page['image'].split('/')[-1],
        )

    @staticmethod
    def get_manga_url(slug, url):
        """
        Returns manga absolute URL
        """
        return url

    def get_latest_updates(self):
        """
        Returns latest updated mangas
        """
        return self.search('', orderby='updated')

    def get_most_populars(self):
        """
        Returns most popular mangas (bayesian rating)
        """
        return self.search('', orderby='popular')

    def search(self, term, orderby=None):
        params = dict(
            limit=50,
        )
        if orderby is not None:
            params['order'] = orderby
        else:
            params['search'] = term

        r = self.session_get(self.api_url, params=params, headers={'Referer': self.base_url})
        if r.status_code != 200:
            return None

        resp_data = r.json()['response']

        return [dict(
            slug=item['id'],
            name=item['russian'],
            cover=item['image']['preview'],
            last_chapter=item['chapters']['updated']['ch'],
        ) for item in resp_data]
