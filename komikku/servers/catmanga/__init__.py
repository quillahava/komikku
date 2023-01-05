# -*- coding: utf-8 -*-

# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
from datetime import datetime
import json
import re
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

#
# BEWARE: CatManga server is disabled
# Dead since 12/11/2021
#


class Catmanga(Server):
    id = 'catmanga'
    name = 'CatManga'
    lang = 'en'
    status = 'disabled'

    base_url = 'https://catmanga.org'
    search_url = base_url + '/search'
    mangas_url = base_url
    manga_url = base_url + '/series/{0}'
    chapter_url = base_url + '/series/{0}/{1}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        json_data = json.loads(soup.find(
            'script',
            id=re.compile('__NEXT_DATA__'),
            type='application/json'
        ).string)

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        props = json_data['props']['pageProps']['series']
        data['name'] = props['title']
        data['cover'] = props['cover_art']['source']

        # Details
        data['authors'] = props['authors']
        data['genres'] = props['genres']
        if props['status'] == 'completed':
            data['status'] = 'complete'
        elif props['status'] == 'dropped':
            data['status'] = 'suspended'
        else:
            data['status'] = props['status']

        data['synopsis'] = props['description']

        # Chapters + scanlators
        for chapter in props['chapters']:
            if title := chapter.get('title'):
                title = f"{chapter['number']} - {title}"
            else:
                title = f"Chapter {chapter['number']}"

            if chapter.get('date'):
                date = convert_date_string(chapter.get('date'), format='%B %d, %Y')
            else:
                date = datetime.today().strftime('%Y-%m-%d')

            data['chapters'].append(dict(
                slug=str(chapter['number']),
                title=title,
                date=date,
                scanlators=chapter.get('groups'),
            ))
            data['scanlators'] = list(set(data['scanlators']) | set(chapter.get('groups')))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(
            self.chapter_url.format(manga_slug, chapter_slug)
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        json_data = json.loads(soup.find(
            'script',
            id=re.compile('__NEXT_DATA__'),
            type='application/json'
        ).string)
        pages = json_data['props']['pageProps']['pages']

        data = dict(
            pages=[],
        )
        for page in pages:
            data['pages'].append(dict(
                slug=None,
                image=page,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """ Returns chapter page scan (image) content """
        r = self.session_get(page['image'])
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=page['image'].split('?')[0].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """ Returns manga absolute URL """
        return self.manga_url.format(slug)

    def get_most_populars(self):
        """ Returns list of all mangas """
        r = self.session_get(self.mangas_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        json_data = json.loads(soup.find(
            'script',
            id=re.compile('__NEXT_DATA__'),
            type='application/json'
        ).string)

        series = json_data['props']['pageProps']['series']
        results = []
        for manga in series:
            results.append(dict(
                slug=manga['series_id'],
                name=manga['title'],
            ))
        return results

    def search(self, term):
        return list(filter(lambda x: term.lower() in x['name'].lower(), self.get_most_populars()))
