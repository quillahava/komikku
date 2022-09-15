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


class Grisebouille(Server):
    id = 'grisebouille'
    name = 'Grise Bouille'
    lang = 'fr'

    long_strip_genres = ['Long Strip', ]

    base_url = 'https://grisebouille.net'
    search_url = base_url + '/categories.html'
    manga_url = base_url + '/category/{0}/'
    chapter_url = base_url + '/{0}/'
    cover_url = base_url + '/content/img/{0}.png'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content
        """
        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = initial_data.copy()
        data.update(dict(
            authors=['Gee', ],
            scanlators=[],
            genres=['Humour', 'Long Strip'],
            status='ongoing',
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=self.cover_url,
        ))

        data['name'] = soup.select_one('title').text.split('|')[0].strip().encode('iso-8859-1').decode()
        data['cover'] = self.cover_url.format(data['slug'])

        data['synopsis'] = soup.select_one('#article > p:nth-child(3)').text.strip().encode('iso-8859-1').decode()

        # Chapters
        for a_element in reversed(soup.select('#article > div > div > ul > li > a')):
            date, title = a_element.text.strip().encode('iso-8859-1').decode().split(' — ')
            data['chapters'].append(dict(
                slug=a_element.get('href').split('/')[-2],
                title=title,
                date=convert_date_string(date, '%Y-%m-%d'),
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(chapter_slug))
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )
        for img_element in soup.select('#article > p > img'):
            url = img_element.get('src')
            if not url.startswith(self.base_url):
                continue

            data['pages'].append(dict(
                slug=None,
                image=img_element.get('src'),
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
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_most_populars(self):
        return self.search()

    def search(self, term=None):
        r = self.session_get(self.search_url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = []
        for item in soup.find_all('div', class_='item-1-3 l-item-1-2 s-item-1-1'):
            slug = item.a.get('href').split('/')[-2]
            if slug not in ('comic-trip', 'depeches-melba', 'tu-sais-quoi'):
                continue

            name = item.a.img.get('title').encode('iso-8859-1').decode()
            if term and term.lower() not in name.lower():
                continue

            data.append(dict(
                slug=item.a.get('href').split('/')[-2],
                name=item.a.img.get('title').encode('iso-8859-1').decode(),
            ))

        return data
