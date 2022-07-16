# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Zeroscans(Server):
    id = 'zeroscans'
    name = 'Zero Scans'
    lang = 'en'

    base_url = 'https://zeroscans.com'
    api_url = base_url + '/swordflake'
    api_search_url = api_url + '/comics'
    api_manga_url = api_url + '/comic/{0}'
    api_chapter_url = api_url + '/comic/{0}/chapters/{1}'
    api_chapters_url = api_url + '/comic/{0}/chapters?sort=desc&page={1}'
    manga_url = base_url + '/comics/{0}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns comic data using API

        Initial data should contain at least comic's slug (provided by search)
        """
        r = self.session_get(self.api_manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        resp_data = r.json()['data']

        data = initial_data.copy()
        data.update(dict(
            name=resp_data['name'],
            authors=[],     # Not available
            scanlators=[],  # Not available
            genres=[genre['name'] for genre in resp_data['genres']],
            status=None,
            synopsis=resp_data['summary'],
            chapters=[],
            server_id=self.id,
            cover=resp_data['cover']['full'],
        ))

        # Status
        status = resp_data['statuses'][0]['slug']
        if status in ('new', 'ongoing'):
            data['status'] = 'ongoing'
        elif status == 'completed':
            data['status'] = 'complete'
        elif status == 'dropped':
            data['status'] = 'suspended'
        elif status == 'hiatus':
            data['status'] = 'hiatus'

        # Chapters
        id = resp_data['id']
        page = 1
        next_page = True
        chapters = []
        while next_page:
            r = self.session_get(self.api_chapters_url.format(id, page))
            if r.status_code != 200:
                chapters = []
                break

            resp_data = r.json()
            if not resp_data['success']:
                chapters = []
                break

            resp_data = resp_data['data']
            for chapter in resp_data['data']:
                chapters.append(dict(
                    slug=str(chapter['id']),
                    title=f'#{chapter["name"]}',
                    date=convert_date_string(chapter['created_at']),
                ))

            next_page = resp_data['next_page_url'] is not None
            page += 1

        data['chapters'] = list(reversed(chapters))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns comic chapter data using API

        Currently, only pages are expected.
        """
        r = self.session_get(self.api_chapter_url.format(manga_slug, chapter_slug))
        if r.status_code != 200:
            return None

        resp_data = r.json()
        if not resp_data['success']:
            return None

        data = dict(
            pages=[],
        )
        for url in resp_data['data']['chapter']['good_quality']:
            data['pages'].append(dict(
                slug=None,
                image=url,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(page['image'])
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

    def get_manga_url(self, slug, url):
        """
        Returns comic absolute URL
        """
        return self.manga_url.format(slug)

    def get_most_populars(self):
        return self.search('', True)

    def search(self, term, most_populars=False):
        r = self.session_get(self.api_search_url)
        if r.status_code != 200:
            return None

        data = r.json()
        if not data['success']:
            return None

        data = data['data']

        # Available keys in data: 'comics', 'genres', 'statuses', 'rankings'
        result = []
        for item in data['comics']:
            if not most_populars and term.lower() not in item['name'].lower():
                continue

            result.append(dict(
                name=item['name'],
                slug=item['slug'],
                # id=item['id'],
                # view_count=item['view_count'],
                # rating=item['rating'],
            ))

        if most_populars:
            result = sorted(result, key=lambda i: i['view_count'], reverse=True)

        return result
