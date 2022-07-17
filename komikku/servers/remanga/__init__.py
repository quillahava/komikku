# -*- coding: utf-8 -*-

# Copyright (C) 2022 CakesTwix
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: CakesTwix <oleg.kiryazov@gmail.com>

from datetime import datetime
import requests
import re
from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type

SERVER_NAME = 'Remanga'

headers = {
    'User-Agent': USER_AGENT,
}

tags_remove = re.compile(r'<[^>]+>')

class Remanga(Server):
    id = 'remanga'
    name = SERVER_NAME
    lang = 'ru'

    base_url = 'https://remanga.org'
    base_url_manga = base_url + '/manga/{0}'

    api_base_url = 'https://api.remanga.org'
    api_manga_url = base_url + '/api/titles/{0}/'
    
    api_chapters_photo = api_base_url + '/api/titles/chapters/'
    api_chapter_url = api_chapters_photo + '?branch_id={0}&page={1}'
    
    api_search_url = base_url + '/api/search/?query={0}'
    api_most_populars_url = base_url + '/api/search/catalog/?ordering=-rating&count=50&page={0}'


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
        data['url'] = self.base_url_manga.format(resp_data['dir'])
        data['cover'] = self.base_url + resp_data['img']['high']

        # Translators
        data['scanlators'] = [publisher['name'] for publisher in resp_data['publishers']]

        # Genres
        data['genres'] = [genre['name'] for genre in resp_data['genres']]

        # Status
        if resp_data['status']['id'] == 1:
            data['status'] = 'ongoing'
        elif resp_data['status']['id'] == 0:
            data['status'] = 'complete'
        elif resp_data['status']['id'] == 2:
            data['status'] = 'suspended'

        # Description
        data['synopsis'] = tags_remove.sub('', resp_data['description'])

        # Chapters
        page = 1
        list_chapters = {'content': ""}
        while list_chapters['content'] != []:
            list_chapters = self.session_get(self.api_chapter_url.format(str(resp_data['branches'][0]['id']), str(page))).json()
            for chapter in list_chapters['content']:
                title = '#{0}'.format(chapter['chapter'])
                if chapter['name']:
                    title = '{0} - {1}'.format(title, chapter['name'])

                data['chapters'].append(dict(
                    slug=chapter['id'],
                    title=title,
                    date=datetime.strptime(chapter['upload_date'][:-7], "%Y-%m-%dT%H:%M:%S").date(),
                ))
            page += 1

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data from API

        Currently, only pages are expected.
        """

        r = self.session_get(self.api_chapters_photo + str(chapter_slug))
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

    @staticmethod
    def get_manga_url(_, url):
        """
        Returns manga absolute URL
        """
        return url

    def get_most_populars(self):
        """
        Returns most popular mangas (bayesian rating)
        """
        r = self.session_get(self.api_most_populars_url)
        return self._get_mangas(r)

    def search(self, term):
        r = self.session_get(self.api_search_url.format(term))
        return self._get_mangas(r)

    def _get_mangas(self, r):
        if r.status_code != 200:
            return None
        resp_data = r.json()['content']
        return [dict(slug=item['dir'], name=item['rus_name']) for item in resp_data]
