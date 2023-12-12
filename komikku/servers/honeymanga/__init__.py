# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Honeymanga(Server):
    id = 'honeymanga'
    name = 'Honey Manga'
    lang = 'uk'

    base_url = 'https://honey-manga.com.ua'
    manga_url = base_url + '/book/{0}'
    chapter_url = base_url + '/read/{0}/{1}'
    resource_url = 'https://hmvolumestorage.b-cdn.net/public-resources/{0}'

    api_base_url = 'https://{0}.api.honey-manga.com.ua'
    api_search_url = api_base_url.format('search') + '/v2/manga/pattern'
    api_list_url = api_base_url.format('data') + '/v2/manga/cursor-list'
    api_manga_url = api_base_url.format('data') + '/manga/{0}'
    api_chapters_url = api_base_url.format('data') + '/v2/chapter/cursor-list'
    api_chapter_url = api_base_url.format('data') + '/chapter/frames'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data via API

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(
            self.api_manga_url.format(initial_data['slug']),
            headers={
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()

        data = initial_data.copy()
        data.update(dict(
            name=resp_data['title'],
            cover=self.resource_url.format(resp_data['posterId']),
            authors=[],
            scanlators=[],  # Use teamId? Would require an additional query
            genres=resp_data['genresAndTags'],
            status=None,
            synopsis=resp_data['description'],
            chapters=[],
            server_id=self.id,
        ))

        # Authors
        for author in resp_data['authors']:
            if author not in data['authors']:
                data['authors'].append(author)
        for artist in resp_data['artists']:
            if artist not in data['authors']:
                data['authors'].append(artist)

        # Status
        if resp_data['titleStatus'] in ('Онгоінг', 'Анонс'):
            data['status'] = 'ongoing'
        elif resp_data['titleStatus'] == 'Завершено':
            data['status'] = 'complete'
        elif resp_data['titleStatus'] in ('Покинуто', 'Призупинено'):
            data['status'] = 'suspended'

        # Chapters
        data['chapters'] = list(reversed(self.get_manga_chapters_data(data['slug'])))

        return data

    def get_manga_chapters_data(self, manga_slug, page=1):
        """
        Returns manga chapters list via API
        """
        r = self.session_post(
            self.api_chapters_url,
            data={
                'mangaId': manga_slug,
                'sortOrder': 'DESC',
                'page': page,
                'pageSize': 45,
            },
            headers={
                'Referer': self.manga_url.format(manga_slug),
            }
        )
        if r.status_code != 200:
            return None

        chapters = []
        resp_data = r.json()
        for chapter in resp_data['data']:
            title = f'Том {chapter["volume"]} - Розділ {chapter["chapterNum"]}'
            if chapter['title'].lower().replace('-', '') not in ('', 'title'):
                # Not sure this restriction is exhaustive
                title += f'| {chapter["title"]}'

            chapters.append(dict(
                slug=chapter['id'],
                title=title,
                date=convert_date_string(chapter["lastUpdated"].split('T')[0], format='%Y-%m-%d'),
            ))

        if resp_data['cursorNext']:
            chapters += self.get_manga_chapters_data(manga_slug, resp_data['cursorNext']['page'])

        return chapters

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data via API

        Currently, only pages are expected.
        """
        r = self.session_post(
            self.api_chapter_url,
            data={
                'chapterId': chapter_slug,
            },
            headers={
                'Referer': self.chapter_url.format(chapter_slug, manga_slug),
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()

        data = dict(
            pages=[],
        )
        for index, resourceId in resp_data['resourceIds'].items():
            data['pages'].append(dict(
                slug=resourceId,
                index=int(index) + 1,
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            self.resource_url.format(page['slug']),
            headers={
                'Referer': self.chapter_url.format(chapter_slug, manga_slug),
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name='{0}.{1}'.format(page['index'], mime_type.split('/')[-1]),
        )

    def get_manga_list(self, orderby):
        r = self.session_post(
            self.api_list_url,
            json={
                'sort': {
                    'sortBy': orderby,
                    'sortOrder': 'DESC',
                },
                'page': 1,
                'pageSize': 30,
            },
            headers={
                'Origin': self.base_url,
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()

        results = []
        for item in resp_data['data']:
            results.append(dict(
                slug=item['id'],
                name=item['title'],
                cover=self.resource_url.format(item['posterId']),
                nb_chapters=int(item['chapters']),
            ))

        return results

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        """
        Returns list of latest mangas via API
        """
        return self.get_manga_list('lastUpdated')

    def get_most_populars(self):
        """
        Returns list of most liked mangas via API
        """
        return self.get_manga_list('likes')

    def search(self, term):
        r = self.session_get(
            self.api_search_url,
            params=dict(
                query=term,
            ),
            headers={
                'Origin': self.base_url,
                'Referer': self.base_url,
            }
        )
        if r.status_code not in (200, 201):
            return None

        data = r.json()

        results = []
        for item in data:
            results.append(dict(
                slug=item['id'],
                name=item['title'],
                cover=self.resource_url.format(item['posterId']),
                nb_chapters=int(item['chapters']),
            ))

        return results
