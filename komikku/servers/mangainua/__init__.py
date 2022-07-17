# -*- coding: utf-8 -*-

# Copyright (C) 2022 CakesTwix
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: CakesTwix <oleg.kiryazov@gmail.com>

from datetime import datetime
import requests
from bs4 import BeautifulSoup as bs
from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type



headers = {
    'User-Agent': USER_AGENT,
}


class Mangainua(Server):
    id = 'mangainua'
    name = 'Manga.in.ua'
    lang = 'ua'

    base_url = 'https://manga.in.ua'
    search_url = base_url + '/mangas/'

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

        r = self.session.get(initial_data['slug'])
        if r.status_code != 200:
            return None


        soup = bs(r.text, features="lxml")

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

        data['name'] = soup.find('span', class_='UAname').get_text()
        data['url'] = initial_data['slug']
        data['cover'] = self.base_url + soup.find('figure').find('img')['src']

        for sidebar_header in soup.find_all('div', class_='item__full-sideba--header'):
            if sidebar_header.find('div', class_='item__full-sidebar--sub'):
                souped = sidebar_header.find('div', class_='item__full-sidebar--sub').get_text()
            else:
                break

            if souped == 'Жанри:':
                # Genres
                data['genres'] = sidebar_header.find('span').get_text().split()
            elif souped == 'Переклад:':
                # Translators
                data['scanlators'] = sidebar_header.find('span').get_text().split() 
            elif souped == 'Статус перекладу:':
                status = sidebar_header.find('span').get_text()
                if status == 'Закінчений':
                    data['status'] = 'complete'
                elif status == 'Триває':
                    data['status'] = 'ongoing'
            elif souped == 'break':
                break

        # Description
        data['synopsis'] = soup.find('div', class_='item__full-description').get_text()

        # Chapters
        for chapter in soup.find('div', class_='linkstocomicsblock').find_all('div', class_='ltcitems'):
            if not chapter.find('a').get("class"):

                data['chapters'].append(dict(
                    slug=chapter.find('a')['href'],
                    title=chapter.find('a').get_text().replace('НОВЕ', '')[1:],
                    date=datetime.strptime(chapter.find('div', class_='ltcright').get_text(), "%d.%m.%Y").date(),
                ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data from API

        Currently, only pages are expected.
        """

        r = self.session_get(chapter_slug)
        if r.status_code != 200:
            return None

        soup = bs(r.text, features="lxml")

        pages = soup.find('div', class_='comics')
        image_paths = [tag['data-src'] for tag in pages.find_all('img')]

        data = dict(
            pages=[],
        )
        for path in image_paths:
            data['pages'].append(dict(
                slug=None,
                image=self.base_url + path,
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
        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        soup = bs(r.text, features="lxml")
        return [dict(slug=item.find('a').get('href'), name=item.find('a')['title']) for item in soup.find_all('div', class_='card card--big')]

    def search(self, term):
        r = self.session.post(self.search_url, data={'do': 'search', 'subaction': 'search', 'titleonly': '3', 'story': term})
        if r.status_code != 200:
            return None

        soup = bs(r.text, features="lxml")

        return [dict(slug=item.find('a').get('href'), name=item.find('a').get('title')) for item in soup.find_all('h3', class_='card__title')]
