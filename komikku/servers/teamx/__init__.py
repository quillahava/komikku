# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type


class Teamx(Server):
    id = 'teamx'
    name = 'Team-X'
    lang = 'ar'

    base_url = 'https://teamxnovel.com'
    search_url = base_url + '/ajax/search'
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

        soup = BeautifulSoup(r.text, 'lxml')

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

        data['name'] = soup.select_one('.author-info-title h1').text.strip()
        data['cover'] = soup.select_one('.whitebox > .text-right > img').get('src')

        # Details
        data['genres'] = [a_element.text.strip() for a_element in soup.select('.review-author-info > a')]

        for element in soup.select('.whitebox > .text-right .full-list-info'):
            label = element.small.text.strip()
            a_elements = element.select('small:nth-child(2) a')

            if label.startswith('الحالة'):
                value = a_elements[0].text.strip()
                if value in ('قادم قريبًا', 'مستمرة'):
                    data['status'] = 'ongoing'
                elif value == 'مكتمل':
                    data['status'] = 'complete'
                elif value == 'متوقف':
                    data['status'] = 'suspended'

            elif label.startswith('الرسام'):
                for a_element in a_elements:
                    value = a_element.text.strip()
                    if value not in data['authors']:
                        data['authors'].append(value)

            elif label.startswith('النوع'):
                for a_element in a_elements:
                    value = a_element.text.strip()
                    data['genres'].append(value)

        # Synopsis
        data['synopsis'] = soup.select_one('.review-content > p').text.strip()

        # Chapters
        first_chapter_url = soup.select_one('.lastend .inepcx:nth-child(1) a').get('href')
        r = self.session_get(first_chapter_url)
        if r.status_code != 200:
            return data

        soup = BeautifulSoup(r.text, 'lxml')

        for option_element in reversed(soup.select('#select_chapter option')):
            chapter_url = option_element.get('value')
            if not chapter_url:
                continue

            data['chapters'].append(dict(
                slug=chapter_url.split('/')[-1],
                title=' '.join(option_element.text.strip().split()),
                date=None,
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(manga_slug, chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        data = dict(
            pages=[],
        )
        for img_element in soup.select('.manga-chapter-img'):
            data['pages'].append(dict(
                image=img_element.get('src'),
                slug=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
            headers={
                'Referer': self.chapter_url.format(manga_slug, chapter_slug),
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
            name=page['image'].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        """
        Returns latest updates
        """
        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for a_element in soup.select('.imgu a'):
            results.append(dict(
                slug=a_element.get('href').split('/')[-1],
                name=a_element.img.get('alt'),
                cover=a_element.img.get('src'),
            ))

        return results

    def get_most_populars(self):
        """
        Returns most viewed mangas
        """
        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for a_element in soup.select('.swiper-slide .entry-image a'):
            results.append(dict(
                slug=a_element.get('href').split('/')[-1],
                name=a_element.img.get('alt'),
                cover=a_element.img.get('src'),
            ))

        return results

    def search(self, term):
        r = self.session_get(self.search_url, params=dict(keyword=term))
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for li_element in soup.select('li'):
            a_element = li_element.select_one('.result-info > a')
            results.append(dict(
                slug=a_element.get('href').split('/')[-1],
                name=a_element.text,
                cover=li_element.select_one('.image-parent img').get('src'),
            ))

        return results
