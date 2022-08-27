# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
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
    api_search_url = base_url + '/manga/search'
    api_chapters_url = base_url + '/manga/api?get=chapters&manga={0}'
    api_chapter_url = base_url + '/manga/api?get=pages&chapter={0}'

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
            self.manga_url.format(initial_data['slug']),
            headers={
                'Referer': self.search_url,
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

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

        info_element = soup.find('div', class_='manga-info')

        data['name'] = info_element.find('span', class_='title-text').text.strip()
        data['cover'] = self.base_url + info_element.find('img', class_='icon-image').get('src')

        # Details
        for a_element in info_element.find_all('a', class_='author'):
            data['authors'].append(a_element.text.strip())

        for a_element in info_element.find_all('a', class_='manga-tag'):
            data['genres'].append(a_element.text.strip())

        for a_element in info_element.find_all('a', class_='translator'):
            data['scanlators'].append(a_element.text.strip())

        view_mode = info_element.find('span', class_='view-mode-text').text.strip()
        # Add 'Webtoon' reading mode in genres if missing
        if view_mode in ('Webtoon',) and view_mode not in data['genres']:
            data['genres'].append(view_mode)

        data['status'] = 'complete' if 'Terminé' in data['genres'] else 'ongoing'

        # Synopsis
        data['synopsis'] = soup.find('div', class_='description-text').text.strip()

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
        if resp_data['error']:
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
            if data['error']:
                return None

            return data

        results = []
        page_num = 0
        while True:
            data = get_page(page_num)
            if data is None:
                break

            for manga in data['mangas']:
                results.append(dict(
                    slug=manga['id'],
                    name=manga['title'],
                ))

            if page_num == data['page_count'] - 1:
                break

            page_num += 1

        return results
