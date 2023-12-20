# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Aralosbd(Server):
    id = 'aralosbd'
    name = 'Aralos BD'
    lang = 'fr'
    long_strip_genres = ['Webtoon']

    base_url = 'https://aralosbd.fr'
    search_url = base_url + '/manga/query'
    manga_url = base_url + '/manga/display?id={0}'
    chapter_url = base_url + '/manga/chapter?id={0}'

    api_url = base_url + '/manga/api'
    api_search_url = base_url + '/manga/search'
    latest_updates_url = api_url + '?get=lastchapters&limit=12&order=desc&showReleased=1&showUnreleased=0'
    api_manga_url = api_url + '?get=manga&id={0}'
    api_chapters_url = api_url + '?get=chapters&manga={0}'
    api_chapter_url = api_url + '?get=pages&chapter={0}'

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
        if resp_data['error'] != 0:
            return None

        data = initial_data.copy()
        data.update(dict(
            authors=[author['name'] for author in resp_data['authors']],
            scanlators=[translator['name'] for translator in resp_data['translators']],
            genres=[tag['tag'] for tag in resp_data['tags']],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
        ))

        data['name'] = resp_data['main_title']
        data['cover'] = self.base_url + '/' + resp_data['icon']

        if 'Terminé' in data['genres']:
            data['status'] = 'complete'
            data['genres'].remove('Terminé')
        elif 'En cours' in data['genres']:
            data['status'] = 'ongoing'
            data['genres'].remove('En cours')
        elif 'En pause' in data['genres']:
            data['status'] = 'hiatus'
            data['genres'].remove('En pause')

        # Synopsis
        data['synopsis'] = resp_data['description']
        if resp_data['fulldescription']:
            data['synopsis'] += '\n\n' + resp_data['fulldescription']

        # Chapters
        r = self.session_get(
            self.api_chapters_url.format(data['slug']),
            headers={
                'Referer': self.manga_url.format(data['slug']),
            }
        )
        if r.status_code != 200:
            return data

        for chapter in reversed(r.json()):
            data['chapters'].append(dict(
                slug=chapter['chapter_id'],
                title=f"{chapter['chapter_number']} - {chapter['chapter_title']}",
                scanlators=[chapter['chapter_translator'], ] if chapter['chapter_translator'] else None,
                date=convert_date_string(chapter['chapter_date'].split()[0], '%Y-%m-%d'),
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data via API

        Currently, only pages are expected.
        """
        r = self.session_get(self.api_chapter_url.format(chapter_slug))
        if r.status_code != 200:
            return None

        resp_data = r.json()
        if resp_data['error'] != 0:
            return None

        data = dict(
            pages=[],
        )

        for link in resp_data['links']:
            data['pages'].append(dict(
                slug=None,
                image=link,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            f"{self.base_url}/{page['image']}",
            headers={
                'Referer': self.chapter_url.format(chapter_slug),
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
            name=f"{page['image'].split('?')[0].split('/')[-1]}.{mime_type.split('/')[-1]}",
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        """
        Returns list of latest mangas
        """
        r = self.session_get(
            self.latest_updates_url,
            headers={
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()
        if resp_data['error'] != 0:
            return None

        results = {}
        for chapter in resp_data['chapters']:
            if chapter['manga_id'] not in results:
                results[chapter['manga_id']] = dict(
                    slug=chapter['manga_id'],
                    name=chapter['manga_title'],
                    cover=self.base_url + '/' + chapter['icon'],
                    last_chapter=chapter['chapter_number'],
                )
            elif chapter['chapter_number'] > results[chapter['manga_id']]['last_chapter']:
                results[chapter['manga_id']]['last_chapter'] = chapter['chapter_number']

        return results.values()

    def get_most_populars(self):
        """
        Returns list of most viewed mangas
        """
        return self.search('', populars=True)

    def search(self, term, populars=False):
        if populars:
            filters = 'sort:allviews;limit:18;-id:3;order:desc'
        else:
            filters = f'title~{term};limit:18;order:asc'

        def get_page(num=0):
            r = self.session_get(
                self.api_search_url,
                params=dict(
                    s=f'{filters};page:{num}',
                ),
                headers={
                    'Referer': self.search_url,
                }
            )
            if r.status_code != 200:
                return None

            data = r.json()
            if data['error'] != 0:
                return None

            return data

        results = []
        more = True
        page_num = -1
        while more:
            page_num += 1
            data = get_page(page_num)
            if data is None:
                break

            for manga in data['mangas']:
                results.append(dict(
                    slug=manga['id'],
                    name=manga['title'],
                    cover=self.base_url + '/' + manga['icon'],
                    nb_chapters=manga['chapter_count'],
                ))

            more = page_num < data['page_count'] - 1

        return results
