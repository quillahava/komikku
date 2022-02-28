# -*- coding: utf-8 -*-

# Copyright (C) 2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Supported servers:
# GTO The Great Site [IT]
# Lupi Team [IT]
# Phoenix Scans [IT]

import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class PizzaReader(Server):
    base_url: str

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data from API

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(self.base_url + '/api/comics/' + initial_data['slug'])
        if r.status_code != 200:
            return None

        resp_data = r.json()['comic']

        data = initial_data.copy()
        data.update(dict(
            name=resp_data['title'],
            cover=resp_data['thumbnail_small'],
            authors=[],
            scanlators=[],  # not available
            genres=[genre['name'] for genre in resp_data['genres']],
            status=None,
            synopsis=resp_data['description'],
            chapters=[],
            server_id=self.id,
        ))

        if resp_data['author']:
            data['authors'].append(resp_data['author'])
        if resp_data['artist'] and resp_data['artist'] not in data['authors']:
            data['authors'].append(resp_data['artist'])

        if resp_data['status'].lower().startswith(('in corso', 'on going')):
            data['status'] = 'ongoing'
        else:
            data['status'] = 'complete'

        # Chapters
        for chapter in reversed(resp_data['chapters']):
            data['chapters'].append(dict(
                slug=chapter['slug_lang_vol_ch_sub'],
                url=chapter['url'],
                title=chapter['full_title'],
                scanlators=[team['name'] for team in chapter['teams'] if team],
                date=convert_date_string(chapter['published_on'].split('T')[0], format='%Y-%m-%d'),
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        r = self.session_get(self.base_url + '/api' + chapter_url)
        if r.status_code != 200:
            return None

        data = dict(
            pages=[],
        )
        for url in r.json()['chapter']['pages']:
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
            name=page['image'].split('?')[0].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return f'{self.base_url}/comics/{slug}'

    def get_most_populars(self):
        r = self.session_get(self.base_url + '/api/comics')
        if r.status_code != 200:
            return None

        resp_data = r.json()
        results = []

        for item in resp_data['comics']:
            results.append(dict(
                slug=item['slug'],
                name=item['title'],
            ))

        return results

    def search(self, term):
        r = self.session_get(self.base_url + '/api/search/' + term)
        if r.status_code != 200:
            return None

        resp_data = r.json()
        results = []

        for item in resp_data['comics']:
            results.append(dict(
                slug=item['slug'],
                name=item['title'],
            ))

        return results
