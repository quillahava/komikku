# -*- coding: utf-8 -*-

# Copyright (C) 2022 CakesTwix
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: CakesTwix <oleg.kiryazov@gmail.com>

import logging
import re
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

logger = logging.getLogger('komikku.servers.remanga')

re_tags_remove = re.compile(r'<[^>]+>')


class Remanga(Server):
    id = 'remanga'
    name = 'Remanga'
    lang = 'ru'

    base_url = 'https://remanga.org'
    manga_url = base_url + '/manga/{0}'

    api_base_url = 'https://api.remanga.org'
    api_search_url = api_base_url + '/api/search/'
    api_most_populars_url = api_base_url + '/api/search/catalog/'
    api_manga_url = api_base_url + '/api/titles/{0}/'
    api_chapters_url = api_base_url + '/api/titles/chapters/'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = {
                'User-Agent': USER_AGENT,
            }

    def get_manga_data(self, initial_data):
        """
        Returns manga data from API

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(
            self.api_manga_url.format(initial_data['slug']),
            headers={
                'content-type': 'application/json',
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()['content']

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

        data['name'] = resp_data['rus_name']
        data['cover'] = self.base_url + resp_data['img']['high']

        # Details
        data['scanlators'] = [publisher['name'] for publisher in resp_data['publishers']]
        data['genres'] = [genre['name'] for genre in resp_data['genres']]

        if resp_data['status']['id'] == 1:
            data['status'] = 'ongoing'
        elif resp_data['status']['id'] == 0:
            data['status'] = 'complete'
        elif resp_data['status']['id'] == 2:
            data['status'] = 'suspended'

        # Synopsis
        data['synopsis'] = re_tags_remove.sub('', resp_data['description'])

        # Chapters
        chapters = []
        branch_id = resp_data['branches'][0]['id']
        page = 1
        while True:
            r = self.session_get(
                self.api_chapters_url,
                params=dict(
                    branch_id=branch_id,
                    page=page,
                ),
                headers={
                    'content-type': 'application/json',
                }
            )
            if r.status_code != 200:
                # Return all chapters or nothing
                return data

            resp_data = r.json()['content']
            if not resp_data:
                break

            for chapter in resp_data:
                title = '#{0}'.format(chapter['chapter'])
                if chapter['name']:
                    title = '{0} - {1}'.format(title, chapter['name'])

                chapters.append(dict(
                    slug=str(chapter['id']),  # must be a string
                    title=title,
                    date=convert_date_string(chapter['upload_date'][:-16], '%Y-%m-%d'),
                ))
            page += 1

        data['chapters'] = list(reversed(chapters))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data from API

        Currently, only pages are expected.
        """
        r = self.session_get(
            self.api_chapters_url + str(chapter_slug),
            headers={
                'content-type': 'application/json',
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()['content']

        data = dict(
            pages=[],
        )
        for page in resp_data['pages']:
            if isinstance(page, list):
                for page_list in page:
                    data['pages'].append(dict(
                        slug=None,
                        image=page_list['link'],
                    ))
            else:
                data['pages'].append(dict(
                    slug=None,
                    image=page['link'],
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

    def get_manga_url(self, slug, _url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_most_populars(self):
        """
        Returns most popular mangas (bayesian rating)
        """
        r = self.session_get(
            self.api_most_populars_url,
            params={
                'ordering': '-rating',
                'count': 50,
            },
            headers={
                'content-type': 'application/json',
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()['content']
        return [dict(slug=item['dir'], name=item['rus_name']) for item in resp_data]

    def search(self, term):
        r = self.session_get(
            self.api_search_url,
            params={
                'query': term,
            },
            headers={
                'content-type': 'application/json',
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()['content']
        return [dict(slug=item['dir'], name=item['rus_name']) for item in resp_data]
