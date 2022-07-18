# -*- coding: utf-8 -*-

# Copyright (C) 2022 CakesTwix
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: CakesTwix <oleg.kiryazov@gmail.com>

from bs4 import BeautifulSoup
import logging
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

logger = logging.getLogger('komikku.servers.mangainua')


class Mangainua(Server):
    id = 'mangainua'
    name = 'Manga/in/ua'
    lang = 'uk'

    base_url = 'https://manga.in.ua'
    search_url = base_url + '/mangas/'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = {
                'User-Agent': USER_AGENT,
            }

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's URL (provided by search)
        """
        assert 'url' in initial_data, 'url is missing in initial data'

        r = self.session.get(initial_data['url'])
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, features='lxml')

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

        data['name'] = soup.find('span', class_='UAname').text
        data['cover'] = self.base_url + soup.find('figure').find('img')['src']

        for sidebar_header in soup.find_all('div', class_='item__full-sideba--header'):
            if sidebar_header.find('div', class_='item__full-sidebar--sub'):
                souped = sidebar_header.find('div', class_='item__full-sidebar--sub').text
            else:
                break

            if souped == 'Жанри:':
                # Genres
                data['genres'] = sidebar_header.find('span').text.split()
            elif souped == 'Переклад:':
                # Scanlators
                data['scanlators'] = sidebar_header.find('span').text.split()
            elif souped == 'Статус перекладу:':
                # Status
                status = sidebar_header.find('span').text
                if status == 'Закінчений':
                    data['status'] = 'complete'
                elif status == 'Триває':
                    data['status'] = 'ongoing'
            elif souped == 'break':
                break

        # Description
        data['synopsis'] = soup.find('div', class_='item__full-description').text

        # Chapters
        for chapter in soup.find('div', class_='linkstocomicsblock').find_all('div', class_='ltcitems'):
            if not chapter.find('a').get('class'):
                url = chapter.find('a')['href']
                slug = url.split('/')[-1].split('.')[0]

                data['chapters'].append(dict(
                    url=url,
                    slug=slug,
                    title=chapter.find('a').text.replace('НОВЕ', '')[1:],
                    date=convert_date_string(chapter.find('div', class_='ltcright').text, '%d.%m.%Y'),
                ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """

        r = self.session_get(chapter_url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, features='lxml')

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
    def get_manga_url(_slug, url):
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

        soup = BeautifulSoup(r.text, features='lxml')

        results = []
        for item in soup.find_all('div', class_='card card--big'):
            url = item.find('a').get('href')
            slug = url.split('/')[-1].split('.')[0]
            results.append(dict(
                url=url,
                slug=slug,  # unused
                name=item.find('a').get('title'),
            ))

        return results

    def search(self, term):
        r = self.session.post(self.search_url, data={'do': 'search', 'subaction': 'search', 'titleonly': '3', 'story': term})
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, features='lxml')

        results = []
        for item in soup.find_all('h3', class_='card__title'):
            url = item.find('a').get('href')
            slug = url.split('/')[-1].split('.')[0]
            results.append(dict(
                url=url,
                slug=slug,  # unused
                name=item.find('a').get('title'),
            ))

        return results
